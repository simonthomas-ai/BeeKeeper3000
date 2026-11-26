"""Build model-manifest v2 provenance from a validated local field-dataset ZIP.

The converter never downloads sources, trains a model, or activates inference.
A separate source-rights review file is mandatory; user annotation attestation
is never promoted into a legal/source-level approval.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from camera.model_manifest import (
    MAX_DATASET_PROVENANCE_BYTES,
    MAX_DATASET_PROVENANCE_LINE_BYTES,
    MAX_DATASET_PROVENANCE_ROWS,
)
from training.multilabel_dataset import (
    DatasetValidationError,
    LICENSE_URLS,
    MAX_ZIP_BYTES,
    validate_dataset_archive,
)

MAX_SOURCE_REVIEW_BYTES = 1024 * 1024
MAX_SOURCE_REVIEW_ROWS = 256
MAX_CONVERTER_ARCHIVE_BYTES = MAX_ZIP_BYTES + 128 * 1024 * 1024
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_REVISION = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64}|sha256:[0-9a-f]{64})$")
_REVIEWER = re.compile(r"^reviewer:[A-Za-z0-9][A-Za-z0-9._:-]{7,79}$")
_LOCAL_CAPTURE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{7,79}$")
_LOCAL_SOURCE = re.compile(r"^local-capture://[A-Za-z0-9][A-Za-z0-9._-]{7,79}$")
_ALLOWED_LICENSES = {"CC0-1.0", "CC-BY-4.0", "LicenseRef-ExplicitPermission"}
_SOURCE_REVIEW_FIELDS = {
    "source_url",
    "revision",
    "license",
    "license_review_status",
    "license_evidence_url",
    "training_use_allowed",
    "redistribution_allowed",
    "reviewed_by",
    "reviewed_at",
    "review_kind",
}


class ProvenanceBuildError(ValueError):
    """A dataset or separate source-rights review cannot produce safe provenance."""


def _unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProvenanceBuildError("duplicate JSON key in source-rights review")
        result[key] = value
    return result


def _read_bounded_regular_file(path: str | Path, limit: int, field: str) -> bytes:
    candidate = Path(path).expanduser()
    if candidate.is_symlink():
        raise ProvenanceBuildError(f"{field} must not be a symbolic link")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(str(candidate), flags)
    except OSError as exc:
        raise ProvenanceBuildError(f"cannot safely open {field}") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ProvenanceBuildError(f"{field} must be a regular file")
        if before.st_size < 1 or before.st_size > limit:
            raise ProvenanceBuildError(f"{field} is empty or exceeds its size limit")
        chunks = []
        total = 0
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            while True:
                chunk = handle.read(min(1024 * 1024, limit + 1 - total))
                if not chunk:
                    break
                total += len(chunk)
                if total > limit:
                    raise ProvenanceBuildError(f"{field} exceeds its size limit")
                chunks.append(chunk)
            after = os.fstat(descriptor)
        try:
            path_after = os.stat(candidate, follow_symlinks=False)
        except OSError as exc:
            raise ProvenanceBuildError(f"{field} changed while being read") from exc
        identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        path_identity = (path_after.st_dev, path_after.st_ino, path_after.st_size, path_after.st_mtime_ns)
        if (
            not stat.S_ISREG(path_after.st_mode)
            or identity_before != identity_after
            or identity_before != path_identity
            or total != before.st_size
        ):
            raise ProvenanceBuildError(f"{field} changed while being read")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _snapshot_archive(source: str | Path, destination: Path) -> tuple[str, int]:
    """Copy one stable bounded archive snapshot and hash the exact copied bytes."""
    candidate = Path(source).expanduser()
    if candidate.is_symlink():
        raise ProvenanceBuildError("dataset archive must not be a symbolic link")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(str(candidate), flags)
    except OSError as exc:
        raise ProvenanceBuildError("cannot safely open dataset archive") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ProvenanceBuildError("dataset archive must be a regular file")
        if before.st_size < 1 or before.st_size > MAX_CONVERTER_ARCHIVE_BYTES:
            raise ProvenanceBuildError("dataset archive is empty or exceeds the converter size limit")
        digest = hashlib.sha256()
        total = 0
        with os.fdopen(descriptor, "rb", closefd=False) as source_file, destination.open("xb") as target:
            while True:
                chunk = source_file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_CONVERTER_ARCHIVE_BYTES:
                    raise ProvenanceBuildError("dataset archive exceeds the converter size limit")
                digest.update(chunk)
                target.write(chunk)
            after = os.fstat(descriptor)
        try:
            path_after = os.stat(candidate, follow_symlinks=False)
        except OSError as exc:
            raise ProvenanceBuildError("dataset archive changed while being copied") from exc
        identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        path_identity = (path_after.st_dev, path_after.st_ino, path_after.st_size, path_after.st_mtime_ns)
        if (
            not stat.S_ISREG(path_after.st_mode)
            or identity_before != identity_after
            or identity_before != path_identity
            or total != before.st_size
        ):
            raise ProvenanceBuildError("dataset archive changed while being copied")
        return digest.hexdigest(), total
    finally:
        os.close(descriptor)


def _timezone_timestamp(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ProvenanceBuildError(f"{field} must be a timezone-aware ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProvenanceBuildError(f"{field} must be a timezone-aware ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ProvenanceBuildError(f"{field} must include a timezone")
    return value


def _public_https(value: object, field: str) -> str:
    message = f"{field} must be a credential-free HTTPS URL without query or fragment"
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 2048
        or value != value.strip()
        or any(ord(char) <= 0x20 or ord(char) == 0x7F for char in value)
        or "?" in value
        or "#" in value
    ):
        raise ProvenanceBuildError(message)
    try:
        parsed = urlparse(value)
        parsed.port
    except ValueError as exc:
        raise ProvenanceBuildError(message) from exc
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ProvenanceBuildError(message)
    return value


def _load_source_reviews(path: str | Path) -> dict[tuple[str, str], dict]:
    payload = _read_bounded_regular_file(path, MAX_SOURCE_REVIEW_BYTES, "source-rights review")
    try:
        document = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_json_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ProvenanceBuildError, RecursionError) as exc:
        raise ProvenanceBuildError("source-rights review must be unique-key UTF-8 JSON") from exc
    if (
        not isinstance(document, dict)
        or set(document) != {"format_version", "sources"}
        or type(document.get("format_version")) is not int
        or document["format_version"] != 1
    ):
        raise ProvenanceBuildError("source-rights review must use format_version 1")
    entries = document.get("sources")
    if not isinstance(entries, list) or not entries or len(entries) > MAX_SOURCE_REVIEW_ROWS:
        raise ProvenanceBuildError(f"source-rights review must contain 1 to {MAX_SOURCE_REVIEW_ROWS} sources")

    result = {}
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise ProvenanceBuildError(f"source-rights review entry {index} must be an object")
        source_url = entry.get("source_url")
        is_local = isinstance(source_url, str) and _LOCAL_SOURCE.fullmatch(source_url) is not None
        expected_fields = _SOURCE_REVIEW_FIELDS if not is_local else _SOURCE_REVIEW_FIELDS - {"revision"}
        if set(entry) != expected_fields:
            raise ProvenanceBuildError(f"source-rights review entry {index} has missing or unknown fields")
        if is_local:
            parsed = urlparse(source_url)
            if parsed.path or parsed.params or parsed.query or parsed.fragment or parsed.username or parsed.password:
                raise ProvenanceBuildError(f"source-rights review entry {index} has an invalid local-capture source")
        else:
            source_url = _public_https(source_url, f"source-rights review entry {index} source_url")

        license_id = entry.get("license")
        if license_id not in _ALLOWED_LICENSES:
            raise ProvenanceBuildError(f"source-rights review entry {index} uses an unsupported license")
        if is_local != (license_id == "LicenseRef-ExplicitPermission"):
            raise ProvenanceBuildError(
                f"source-rights review entry {index} must pair local-capture only with explicit permission"
            )
        if is_local:
            revision = None
        else:
            revision = entry.get("revision")
            if not isinstance(revision, str) or not _REVISION.fullmatch(revision):
                raise ProvenanceBuildError(
                    f"source-rights review entry {index} revision must be a full commit SHA or SHA-256 digest"
                )

        status = entry.get("license_review_status")
        if status not in {"approved", "public-domain"}:
            raise ProvenanceBuildError(f"source-rights review entry {index} is not explicitly reviewed")
        if status == "public-domain" and license_id != "CC0-1.0":
            raise ProvenanceBuildError("public-domain status is only valid for CC0-1.0")
        if license_id == "LicenseRef-ExplicitPermission" and status != "approved":
            raise ProvenanceBuildError("explicit permission requires approved source-rights review")

        evidence = entry.get("license_evidence_url")
        if is_local:
            if evidence is not None:
                raise ProvenanceBuildError("private permission evidence must not be embedded as a URL")
        else:
            evidence = _public_https(evidence, f"source-rights review entry {index} license_evidence_url")
            if evidence.rstrip("/") != LICENSE_URLS[license_id].rstrip("/"):
                raise ProvenanceBuildError("license evidence URL does not match the canonical license")

        if entry.get("training_use_allowed") is not True:
            raise ProvenanceBuildError("source-rights review must explicitly permit training use")
        redistribution = entry.get("redistribution_allowed")
        if type(redistribution) is not bool:
            raise ProvenanceBuildError("redistribution_allowed must be an explicit boolean")
        reviewer = entry.get("reviewed_by")
        if not isinstance(reviewer, str) or not _REVIEWER.fullmatch(reviewer):
            raise ProvenanceBuildError("source-rights reviewer must use reviewer:<opaque-id>")
        reviewed_at = _timezone_timestamp(entry.get("reviewed_at"), "source-rights reviewed_at")
        if entry.get("review_kind") != "source_rights":
            raise ProvenanceBuildError("review_kind must explicitly be source_rights")

        key = (source_url, license_id)
        if key in result:
            raise ProvenanceBuildError("duplicate or ambiguous source-rights review entry")
        result[key] = {
            "source_url": source_url,
            "revision": revision,
            "license": license_id,
            "license_review_status": status,
            "license_evidence_url": evidence,
            "training_use_allowed": True,
            "redistribution_allowed": redistribution,
            "reviewed_by": reviewer,
            "reviewed_at": reviewed_at,
        }
    return result


def _source_for_row(row: dict) -> tuple[str, str]:
    rights = row["rights"]
    license_id = rights["basis"]
    source = rights["source"]
    if source.casefold() in {"eigene feldaufnahme", "own field capture"}:
        if license_id != "LicenseRef-ExplicitPermission":
            raise ProvenanceBuildError("local field captures require LicenseRef-ExplicitPermission")
        session_id = row["capture_session_id"]
        if not isinstance(session_id, str) or not _LOCAL_CAPTURE_ID.fullmatch(session_id):
            raise ProvenanceBuildError("local capture session ID is not a safe opaque identifier")
        return f"local-capture://{session_id}", license_id
    if license_id == "LicenseRef-ExplicitPermission":
        raise ProvenanceBuildError("explicit permission is reserved for opaque local field captures")
    return _public_https(source, "annotation rights source"), license_id


def build_provenance(archive_path: str | Path, source_review_path: str | Path) -> dict:
    """Return deterministic provenance and source rows from one validated ZIP snapshot."""
    with tempfile.TemporaryDirectory(prefix="beekeeper-provenance-") as temporary:
        snapshot = Path(temporary) / "validated-input.zip"
        archive_digest, archive_size = _snapshot_archive(archive_path, snapshot)
        rows = validate_dataset_archive(snapshot)
        if not rows or len(rows) > MAX_DATASET_PROVENANCE_ROWS:
            raise ProvenanceBuildError("validated dataset has no images or exceeds the provenance row limit")
        source_reviews = _load_source_reviews(source_review_path)

        provenance_rows = []
        source_rows: dict[tuple[str, str, str], dict] = {}
        used_reviews = set()
        for row in rows:
            source_url, license_id = _source_for_row(row)
            review_key = (source_url, license_id)
            review = source_reviews.get(review_key)
            if review is None:
                raise ProvenanceBuildError(
                    "a validated image has no separate source-rights review entry"
                )
            if review["reviewed_by"] == row["reviewed_by"]:
                raise ProvenanceBuildError(
                    "source-rights reviewer must be distinct from the per-image label reviewer"
                )
            revision = f"sha256:{archive_digest}" if source_url.startswith("local-capture://") else review["revision"]
            if source_url.startswith("local-capture://") and revision != f"sha256:{archive_digest}":
                raise ProvenanceBuildError("local capture revision must bind to the exact archive snapshot")

            source_key = (source_url, revision, license_id)
            source_rows[source_key] = {
                "source_url": source_url,
                "revision": revision,
                "license": license_id,
                "license_review_status": review["license_review_status"],
                "license_evidence_url": review["license_evidence_url"],
                "training_use_allowed": True,
                "redistribution_allowed": review["redistribution_allowed"],
                "reviewed_by": review["reviewed_by"],
                "reviewed_at": review["reviewed_at"],
            }
            output_row = {
                "image": row["image"],
                "image_sha256": row["image_sha256"],
                "source_url": source_url,
                "revision": revision,
                "license": license_id,
                "license_review_status": review["license_review_status"],
                "training_use_allowed": True,
                "redistribution_allowed": review["redistribution_allowed"],
                "reviewed_by": row["reviewed_by"],
                "reviewed_at": row["reviewed_at"],
            }
            if license_id == "CC-BY-4.0":
                output_row["attribution"] = row["rights"]["attribution"].strip()
            elif license_id == "LicenseRef-ExplicitPermission":
                output_row["permission_ref"] = row["rights"]["permission_ref"].strip()
            provenance_rows.append(output_row)
            used_reviews.add(review_key)

        if used_reviews != set(source_reviews):
            raise ProvenanceBuildError("source-rights review contains unused or unreferenced entries")
        if len(source_rows) > MAX_SOURCE_REVIEW_ROWS:
            raise ProvenanceBuildError("validated dataset references too many distinct reviewed sources")

        provenance_rows.sort(key=lambda item: item["image"])
        source_list = [source_rows[key] for key in sorted(source_rows)]
        provenance_bytes = b"".join(
            (json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
            for row in provenance_rows
        )
        if len(provenance_bytes) > MAX_DATASET_PROVENANCE_BYTES:
            raise ProvenanceBuildError("generated provenance exceeds the model-manifest size limit")
        if any(
            len(line) > MAX_DATASET_PROVENANCE_LINE_BYTES
            for line in provenance_bytes.splitlines()
        ):
            raise ProvenanceBuildError("generated provenance contains an oversized JSONL row")
        sources_document = {
            "format_version": 1,
            "training_data_sources": source_list,
        }
        sources_bytes = (
            json.dumps(sources_document, sort_keys=True, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")
        return {
            "archive_sha256": archive_digest,
            "archive_size_bytes": archive_size,
            "image_count": len(provenance_rows),
            "source_count": len(source_list),
            "provenance_bytes": provenance_bytes,
            "sources_bytes": sources_bytes,
        }


def write_outputs(result: dict, output_dir: str | Path) -> None:
    """Write both outputs into a new directory; never overwrite existing files."""
    destination = Path(output_dir).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir(exist_ok=False)
    try:
        (destination / "provenance.jsonl").write_bytes(result["provenance_bytes"])
        (destination / "training_data_sources.json").write_bytes(result["sources_bytes"])
    except OSError:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build model-manifest v2 provenance from a validated local dataset ZIP."
    )
    parser.add_argument("--archive", required=True, help="Local field-dataset ZIP export")
    parser.add_argument("--source-review", required=True, help="Separate source-rights review JSON")
    parser.add_argument("--output-dir", required=True, help="New, non-existing local output directory")
    args = parser.parse_args(argv)
    try:
        result = build_provenance(args.archive, args.source_review)
        write_outputs(result, args.output_dir)
    except (DatasetValidationError, ProvenanceBuildError, OSError, zipfile.BadZipFile) as exc:
        print(f"Provenance conversion blocked: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({
        "archive_sha256": result["archive_sha256"],
        "validated_images": result["image_count"],
        "reviewed_sources": result["source_count"],
        "provenance_rows": result["image_count"],
        "ai_status": "BLOCKED",
        "model_activated": False,
        "training_started": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
