"""Fail-closed validator and deterministic group splitter for image labels."""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import random
import re
import sys
import tempfile
import zipfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse


CLASS_NAMES = (
    "vespa_velutina",
    "vespa_crabro",
    "other_vespidae",
    "apis_mellifera",
    "bombus_spp",
    "syrphidae",
    "other_insect",
)
_PSEUDONYMOUS_LABELER_ID = re.compile(r"^reviewer:[A-Za-z0-9][A-Za-z0-9._:-]{7,79}$")
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
RIGHTS_BASES = {"CC0-1.0", "CC-BY-4.0", "LicenseRef-ExplicitPermission"}
LICENSE_URLS = {
    "CC0-1.0": "https://creativecommons.org/publicdomain/zero/1.0/",
    "CC-BY-4.0": "https://creativecommons.org/licenses/by/4.0/",
}
SPLIT_RATIOS = {"train": 0.70, "val": 0.15, "test": 0.15}
MAX_ZIP_ENTRIES = 100_000
MAX_ZIP_BYTES = 50 * 1024 * 1024 * 1024
MAX_ZIP_FILE_BYTES = 80_000_000


class DatasetValidationError(ValueError):
    """The local dataset does not satisfy its reviewed export contract."""


def _unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DatasetValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _https_url(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise DatasetValidationError(f"{field} must be an HTTPS URL")
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise DatasetValidationError(
            f"{field} must be a credential-free HTTPS URL without query or fragment"
        )
    return value


def _relative_image_path(value: object) -> PurePosixPath:
    if not isinstance(value, str) or "\\" in value or not value:
        raise DatasetValidationError("image must be a relative POSIX path under images/")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
        or len(path.parts) < 2
        or path.parts[0] != "images"
        or Path(path.name).suffix.lower() not in IMAGE_SUFFIXES
    ):
        raise DatasetValidationError("image must be a clean supported path under images/")
    return path


def _parse_timestamp(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DatasetValidationError(f"{field} must be a timezone-aware ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DatasetValidationError(
            f"{field} must be a timezone-aware ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DatasetValidationError(f"{field} must include a timezone")
    return value


def _validate_rights(rights: object, row_number: int) -> str | None:
    prefix = f"line {row_number} rights"
    if not isinstance(rights, dict):
        raise DatasetValidationError(f"{prefix} must be an object")
    allowed_rights_fields = {
        "source", "basis", "status", "publication_allowed",
        "evidence_url", "attribution", "permission_ref",
    }
    if set(rights) - allowed_rights_fields:
        raise DatasetValidationError(f"{prefix} contains unsupported fields")
    source = rights.get("source")
    if not isinstance(source, str) or not source.strip() or len(source.strip()) > 200:
        raise DatasetValidationError(f"{prefix}.source must be a non-empty bounded value")
    source = source.strip()
    basis = rights.get("basis")
    if not isinstance(basis, str) or not basis.strip() or len(basis.strip()) > 120:
        raise DatasetValidationError(f"{prefix}.basis must be a non-empty bounded value")
    basis = basis.strip()
    if basis not in RIGHTS_BASES:
        raise DatasetValidationError(
            f"{prefix}.basis must be CC0-1.0, CC-BY-4.0, or LicenseRef-ExplicitPermission"
        )
    if rights.get("status") != "training_approved":
        raise DatasetValidationError(f"{prefix}.status must be training_approved")
    if "publication_allowed" in rights:
        if type(rights["publication_allowed"]) is not bool or not rights["publication_allowed"]:
            raise DatasetValidationError(f"{prefix}.publication_allowed must be true")
    if basis in LICENSE_URLS:
        if "evidence_url" not in rights:
            raise DatasetValidationError(f"{prefix}.evidence_url is required for the selected license")
        evidence_url = _https_url(rights["evidence_url"], f"{prefix}.evidence_url")
        if evidence_url.rstrip("/") != LICENSE_URLS[basis].rstrip("/"):
            raise DatasetValidationError(f"{prefix}.evidence_url does not match its license basis")
    elif "evidence_url" in rights:
        _https_url(rights["evidence_url"], f"{prefix}.evidence_url")

    if basis == "CC-BY-4.0":
        attribution = rights.get("attribution")
        if not isinstance(attribution, str) or not attribution.strip() or len(attribution.strip()) > 500:
            raise DatasetValidationError(f"{prefix}.attribution is required for CC-BY-4.0")
    if basis == "LicenseRef-ExplicitPermission":
        permission_ref = rights.get("permission_ref")
        if (
            not isinstance(permission_ref, str)
            or not permission_ref.strip()
            or len(permission_ref.strip()) > 200
        ):
            raise DatasetValidationError(f"{prefix}.permission_ref is required and must be bounded")

    generic_sources = {"eigene feldaufnahme", "own field capture"}
    if source.casefold() in generic_sources:
        return None
    parsed = urlparse(source)
    if (
        parsed.scheme == "https"
        and parsed.netloc
        and not parsed.username
        and not parsed.password
        and not parsed.query
        and not parsed.fragment
    ):
        return source
    raise DatasetValidationError(
        f"{prefix}.source must be a credential-free HTTPS URL or explicit local-capture label"
    )


def _safe_file(root: Path, relative: PurePosixPath) -> Path:
    cursor = root
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise DatasetValidationError(f"symbolic links are not allowed: {relative}")
    try:
        resolved = cursor.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise DatasetValidationError(f"image is missing or escapes dataset root: {relative}") from exc
    if not resolved.is_file():
        raise DatasetValidationError(f"image is not a regular file: {relative}")
    return resolved


def validate_dataset(dataset_root: str | Path) -> list[dict]:
    """Validate every manifest entry and require an exact inventory of images/."""
    root = Path(dataset_root).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise DatasetValidationError("dataset root must be a directory")
    images_root = root / "images"
    if not images_root.is_dir() or images_root.is_symlink():
        raise DatasetValidationError("dataset must contain a real images/ directory")
    manifest_path = root / "annotations.jsonl"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise DatasetValidationError("dataset must contain annotations.jsonl")

    rows = []
    seen_paths: set[str] = set()
    seen_hashes: dict[str, str] = {}
    known_classes = set(CLASS_NAMES)
    try:
        lines = manifest_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise DatasetValidationError("annotations.jsonl must be readable UTF-8") from exc
    if not lines:
        raise DatasetValidationError("annotations.jsonl must contain reviewed examples")

    for row_number, line in enumerate(lines, start=1):
        try:
            row = json.loads(line, object_pairs_hook=_unique_json_object)
        except (json.JSONDecodeError, DatasetValidationError) as exc:
            raise DatasetValidationError(f"line {row_number} is not valid unique-key JSON") from exc
        if not isinstance(row, dict):
            raise DatasetValidationError(f"line {row_number} must be a JSON object")
        allowed_fields = {
            "image", "labels", "captured_at", "capture_session_id",
            "labeler_id", "review_status", "reviewed_by", "reviewed_at", "rights",
        }
        required_fields = {
            "image", "labels", "captured_at", "capture_session_id",
            "review_status", "reviewed_by", "reviewed_at", "rights",
        }
        if set(row) - allowed_fields or not required_fields.issubset(row):
            raise DatasetValidationError(f"line {row_number} has missing or unknown fields")

        image_path = _relative_image_path(row["image"]).as_posix()
        if image_path in seen_paths:
            raise DatasetValidationError(f"line {row_number} duplicates image path {image_path}")
        seen_paths.add(image_path)
        image_file = _safe_file(root, PurePosixPath(image_path))
        hasher = hashlib.sha256()
        with image_file.open("rb") as source_file:
            for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
                hasher.update(chunk)
        digest = hasher.hexdigest()
        if digest in seen_hashes:
            raise DatasetValidationError(
                f"line {row_number} duplicates image bytes from {seen_hashes[digest]}"
            )
        seen_hashes[digest] = image_path

        labels = row["labels"]
        if (
            not isinstance(labels, list)
            or any(not isinstance(label, str) or label not in known_classes for label in labels)
            or len(labels) != len(set(labels))
        ):
            raise DatasetValidationError(
                f"line {row_number} labels must be unique known class slugs; [] is valid"
            )
        captured_at = _parse_timestamp(row["captured_at"], f"line {row_number} captured_at")
        reviewed_by = row["reviewed_by"]
        if (
            not isinstance(reviewed_by, str)
            or not _PSEUDONYMOUS_LABELER_ID.fullmatch(reviewed_by)
        ):
            raise DatasetValidationError(
                f"line {row_number} reviewed_by must use reviewer:<opaque-id>; names, emails and URLs are not allowed"
            )
        reviewed_at = _parse_timestamp(row["reviewed_at"], f"line {row_number} reviewed_at")
        captured_stamp = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
        reviewed_stamp = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
        if reviewed_stamp < captured_stamp:
            raise DatasetValidationError(
                f"line {row_number} reviewed_at must not precede captured_at"
            )
        session_id = row["capture_session_id"]
        if not isinstance(session_id, str) or not session_id.strip() or len(session_id) > 160:
            raise DatasetValidationError(f"line {row_number} capture_session_id is required")
        labeler_id = row.get("labeler_id")
        if labeler_id is not None and (
            not isinstance(labeler_id, str) or not _PSEUDONYMOUS_LABELER_ID.fullmatch(labeler_id)
        ):
            raise DatasetValidationError(
                f"line {row_number} labeler_id must use reviewer:<opaque-id>; names, emails and URLs are not allowed"
            )
        if row["review_status"] != "approved":
            raise DatasetValidationError(f"line {row_number} review_status must be approved")
        source = _validate_rights(row["rights"], row_number)
        rows.append({
            "image": image_path,
            "image_sha256": digest,
            "labels": list(labels),
            "captured_at": captured_at,
            "capture_session_id": session_id,
            "labeler_id": labeler_id,
            "review_status": row["review_status"],
            "reviewed_by": reviewed_by,
            "reviewed_at": reviewed_at,
            "rights": dict(row["rights"]),
            "source": source,
        })

    actual_paths = set()
    for item in images_root.rglob("*"):
        if item.is_symlink():
            raise DatasetValidationError(f"symbolic links are not allowed: {item}")
        if item.is_file():
            relative = item.relative_to(root).as_posix()
            if item.suffix.lower() not in IMAGE_SUFFIXES:
                raise DatasetValidationError(f"unsupported file in images/: {relative}")
            actual_paths.add(relative)
    if actual_paths != seen_paths:
        missing = sorted(seen_paths - actual_paths)
        unlisted = sorted(actual_paths - seen_paths)
        raise DatasetValidationError(
            f"manifest/image inventory mismatch: missing={len(missing)} unlisted={len(unlisted)}"
        )
    return rows


class _DisjointGroups:
    def __init__(self, count: int):
        self.parents = list(range(count))

    def find(self, value: int) -> int:
        while self.parents[value] != value:
            self.parents[value] = self.parents[self.parents[value]]
            value = self.parents[value]
        return value

    def join(self, first: int, second: int) -> None:
        root_first, root_second = self.find(first), self.find(second)
        if root_first != root_second:
            self.parents[root_second] = root_first


def create_split_plan(
    rows: list[dict], *, seed: int = 42, ratios: dict[str, float] | None = None
) -> dict:
    """Keep shared capture sessions and source URLs in one deterministic split."""
    ratios = SPLIT_RATIOS if ratios is None else ratios
    if set(ratios) != set(SPLIT_RATIOS) or any(
        isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0
        for value in ratios.values()
    ):
        raise DatasetValidationError("ratios must define positive train, val, and test values")
    if any(not math.isfinite(value) for value in ratios.values()):
        raise DatasetValidationError("ratios must be finite")
    total_ratio = sum(ratios.values())
    if not math.isfinite(total_ratio):
        raise DatasetValidationError("ratio total must be finite")
    normalized = {name: value / total_ratio for name, value in ratios.items()}
    if type(seed) is not int or not 0 <= seed <= 2_147_483_647:
        raise DatasetValidationError("seed must be an integer in 0..2147483647")
    if not rows:
        raise DatasetValidationError("cannot split an empty dataset")

    groups = _DisjointGroups(len(rows))
    owner_by_key: dict[tuple[str, str], int] = {}
    for index, row in enumerate(rows):
        for key in (("session", row["capture_session_id"]), ("source", row["source"])):
            if key[0] == "source" and not key[1]:
                continue
            if key in owner_by_key:
                groups.join(index, owner_by_key[key])
            else:
                owner_by_key[key] = index

    components: dict[int, list[int]] = defaultdict(list)
    for index in range(len(rows)):
        components[groups.find(index)].append(index)
    component_rows = list(components.values())
    if len(component_rows) < len(SPLIT_RATIOS):
        raise DatasetValidationError(
            "at least three independent capture-session/source groups are required"
        )

    rng = random.Random(seed)
    rng.shuffle(component_rows)
    component_rows.sort(key=len, reverse=True)
    split_names = ("train", "val", "test")
    targets = {name: normalized[name] * len(rows) for name in split_names}
    assigned: dict[str, list[int]] = {name: [] for name in split_names}
    for component_index, component in enumerate(component_rows):
        if component_index < len(split_names):
            split_name = split_names[component_index]
        else:
            split_name = min(
                split_names,
                key=lambda name: (
                    len(assigned[name]) / targets[name],
                    split_names.index(name),
                ),
            )
        assigned[split_name].extend(component)

    assignment = {
        rows[index]["image"]: split
        for split, indices in assigned.items()
        for index in indices
    }
    summary = {}
    for split, indices in assigned.items():
        counts = Counter(label for index in indices for label in rows[index]["labels"])
        summary[split] = {
            "images": len(indices),
            "groups": sum(
                1 for component in component_rows
                if component and assignment[rows[component[0]]["image"]] == split
            ),
            "positive_labels": {name: counts.get(name, 0) for name in CLASS_NAMES},
            "negative_images": sum(not rows[index]["labels"] for index in indices),
        }
    return {
        "format_version": 1,
        "seed": seed,
        "ratios": normalized,
        "splits": assignment,
        "summary": summary,
    }


def _safe_zip_member(name: str) -> PurePosixPath | None:
    if not name or "\\" in name or "\x00" in name:
        raise DatasetValidationError("ZIP contains an unsafe path")
    if name.endswith("/"):
        path = PurePosixPath(name[:-1])
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise DatasetValidationError("ZIP path traversal is not allowed")
        if path.as_posix() != "images" and (
            len(path.parts) < 1 or path.parts[0] != "images"
        ):
            raise DatasetValidationError("ZIP may contain only images/ and annotations.jsonl")
        return path
    path = PurePosixPath(name)
    if path.is_absolute() or path.as_posix() != name:
        raise DatasetValidationError("ZIP contains an unsafe path")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise DatasetValidationError("ZIP path traversal is not allowed")
    if path.as_posix() == "annotations.jsonl":
        return path
    if len(path.parts) < 2 or path.parts[0] != "images":
        raise DatasetValidationError("ZIP may contain only images/ and annotations.jsonl")
    if Path(path.name).suffix.lower() not in IMAGE_SUFFIXES:
        raise DatasetValidationError("ZIP contains an unsupported image file")
    return path


def validate_dataset_archive(dataset_archive: str | Path) -> list[dict]:
    """Validate and extract a ZIP export without following archive links."""
    archive_path = Path(dataset_archive).expanduser().resolve(strict=True)
    if not archive_path.is_file() or archive_path.suffix.lower() != ".zip":
        raise DatasetValidationError("dataset archive must be a .zip file")
    try:
        with tempfile.TemporaryDirectory(prefix="beekeeper-dataset-") as temporary:
            root = Path(temporary)
            total_bytes = 0
            seen_names: set[str] = set()
            with zipfile.ZipFile(archive_path, "r") as archive:
                members = archive.infolist()
                if len(members) > MAX_ZIP_ENTRIES:
                    raise DatasetValidationError("ZIP contains too many entries")
                for member in members:
                    name = member.filename
                    if name in seen_names:
                        raise DatasetValidationError(f"ZIP contains duplicate path: {name}")
                    seen_names.add(name)
                    member_path = _safe_zip_member(name)
                    if member.flag_bits & 0x1:
                        raise DatasetValidationError("encrypted ZIP members are not allowed")
                    mode = (member.external_attr >> 16) & 0xFFFF
                    if mode and (mode & 0o170000) == 0o120000:
                        raise DatasetValidationError("symbolic links are not allowed in ZIP")
                    if member_path is not None and name.endswith("/"):
                        continue
                    if member.file_size < 0 or member.file_size > MAX_ZIP_FILE_BYTES:
                        raise DatasetValidationError("ZIP member exceeds the safe image size")
                    total_bytes += member.file_size
                    if total_bytes > MAX_ZIP_BYTES:
                        raise DatasetValidationError("ZIP archive exceeds the safe total size")
                    destination = root.joinpath(*member_path.parts)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(member, "r") as source, destination.open("xb") as target:
                        remaining = member.file_size
                        while remaining:
                            chunk = source.read(min(1024 * 1024, remaining))
                            if not chunk:
                                break
                            target.write(chunk)
                            remaining -= len(chunk)
                        if remaining:
                            raise DatasetValidationError("ZIP member is truncated")
            return validate_dataset(root)
    except zipfile.BadZipFile as exc:
        raise DatasetValidationError("dataset archive is not a valid ZIP") from exc
    except (OSError, RuntimeError) as exc:
        raise DatasetValidationError(f"cannot safely extract dataset ZIP: {exc}") from exc


@contextlib.contextmanager
def prepared_dataset(dataset: str | Path):
    """Yield a directory for directory datasets or a safely extracted ZIP."""
    source = Path(dataset).expanduser()
    if source.is_dir():
        yield source.resolve()
    elif source.is_file() and source.suffix.lower() == ".zip":
        archive_path = source.resolve()
        with tempfile.TemporaryDirectory(prefix="beekeeper-dataset-") as temporary:
            root = Path(temporary)
            try:
                with zipfile.ZipFile(archive_path, "r") as archive:
                    members = archive.infolist()
                    if len(members) > MAX_ZIP_ENTRIES:
                        raise DatasetValidationError("ZIP contains too many entries")
                    total_bytes = 0
                    seen_names: set[str] = set()
                    for member in members:
                        name = member.filename
                        if name in seen_names:
                            raise DatasetValidationError(f"ZIP contains duplicate path: {name}")
                        seen_names.add(name)
                        member_path = _safe_zip_member(name)
                        if member.flag_bits & 0x1:
                            raise DatasetValidationError("encrypted ZIP members are not allowed")
                        mode = (member.external_attr >> 16) & 0xFFFF
                        if mode and (mode & 0o170000) == 0o120000:
                            raise DatasetValidationError("symbolic links are not allowed in ZIP")
                        if name.endswith("/"):
                            continue
                        if member.file_size < 0 or member.file_size > MAX_ZIP_FILE_BYTES:
                            raise DatasetValidationError("ZIP member exceeds the safe image size")
                        total_bytes += member.file_size
                        if total_bytes > MAX_ZIP_BYTES:
                            raise DatasetValidationError("ZIP archive exceeds the safe total size")
                        destination = root.joinpath(*member_path.parts)
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        with archive.open(member, "r") as source_file, destination.open("xb") as target:
                            remaining = member.file_size
                            while remaining:
                                chunk = source_file.read(min(1024 * 1024, remaining))
                                if not chunk:
                                    break
                                target.write(chunk)
                                remaining -= len(chunk)
                            if remaining:
                                raise DatasetValidationError("ZIP member is truncated")
            except zipfile.BadZipFile as exc:
                raise DatasetValidationError("dataset archive is not a valid ZIP") from exc
            except (OSError, RuntimeError) as exc:
                raise DatasetValidationError(f"cannot safely extract dataset ZIP: {exc}") from exc
            yield root
    else:
        raise DatasetValidationError("dataset must be a directory or .zip archive")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate an approved local multi-label dataset and make a grouped split plan."
    )
    parser.add_argument("--dataset", required=True, help="Local dataset root or safe .zip export")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", help="Optional path for the split plan JSON")
    args = parser.parse_args(argv)
    try:
        with prepared_dataset(args.dataset) as dataset_root:
            rows = validate_dataset(dataset_root)
        report = create_split_plan(rows, seed=args.seed)
        rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
        if args.output:
            output_path = Path(args.output).expanduser().resolve()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open("x", encoding="utf-8") as output_file:
                output_file.write(rendered)
        safe_summary = {
            "format_version": report["format_version"],
            "seed": report["seed"],
            "ratios": report["ratios"],
            "validated_images": len(rows),
            "split_plan_sha256": hashlib.sha256(
                json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            "summary": report["summary"],
        }
        print(json.dumps(safe_summary, indent=2, sort_keys=True))
    except (DatasetValidationError, OSError) as exc:
        print(f"Dataset validation failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
