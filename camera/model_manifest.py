"""Fail-closed ONNX model manifest and provenance validation."""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

from .model_artifacts import MAX_MODEL_BYTES

_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_SPDX = re.compile(r"^[A-Za-z0-9.+-]{2,80}$")

MAX_MANIFEST_BYTES = 1024 * 1024
MAX_DATASET_PROVENANCE_BYTES = 16 * 1024 * 1024
MAX_DATASET_PROVENANCE_ROWS = 100_000
MAX_DATASET_PROVENANCE_LINE_BYTES = 64 * 1024
_DATASET_REVISION = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64}|sha256:[0-9a-f]{64})$")
_DATASET_LICENSES = {"CC0-1.0", "CC-BY-4.0", "LicenseRef-ExplicitPermission"}
_DATASET_LICENSE_EVIDENCE = {
    "CC0-1.0": "https://creativecommons.org/publicdomain/zero/1.0/",
    "CC-BY-4.0": "https://creativecommons.org/licenses/by/4.0/",
}


class ModelManifestError(ValueError):
    pass


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ModelManifestError("duplicate JSON key in model manifest")
        result[key] = value
    return result


@dataclass(frozen=True)
class ModelClass:
    label: str
    threshold: float
    prey_detected: bool


@dataclass(frozen=True)
class TrainingDataSource:
    source_url: str
    revision: str
    license_id: str
    license_review_status: str
    license_evidence_url: str
    training_use_allowed: bool
    redistribution_allowed: bool
    reviewed_by: str
    reviewed_at: str


@dataclass(frozen=True)
class ModelManifest:
    path: Path
    model_path: Path
    model_sha256: str
    model_version: str
    model_source_url: str
    model_license: str
    license_review_status: str
    license_evidence_url: str
    license_reviewed_by: str
    license_reviewed_at: str
    inference_use_allowed: bool
    redistribution_allowed: bool
    dataset_manifest_path: Path
    dataset_manifest_sha256: str
    training_data_sources: tuple[TrainingDataSource, ...]
    inference_status: str
    input_name: str
    width: int
    height: int
    resize_mode: str
    box_format: str
    boxes_output: str | None
    scores_output: str | None
    class_ids_output: str | None
    detections_output: str | None
    classes: dict[int, ModelClass]



def _unique_dataset_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ModelManifestError("duplicate JSON key in dataset provenance")
        result[key] = value
    return result


def _validate_dataset_provenance(
    payload: bytes, sources: tuple[TrainingDataSource, ...]
) -> None:
    """Validate every per-image provenance row and bind it to a reviewed source."""
    try:
        lines = payload.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ModelManifestError("dataset provenance must be UTF-8 JSONL") from exc
    if not lines or len(lines) > MAX_DATASET_PROVENANCE_ROWS:
        raise ModelManifestError(
            f"dataset provenance must contain 1 to {MAX_DATASET_PROVENANCE_ROWS} image rows"
        )

    source_by_key = {
        (source.source_url, source.revision, source.license_id): source
        for source in sources
    }
    used_sources = set()
    seen_images = set()
    seen_digests = set()
    required = {
        "image", "image_sha256", "source_url", "revision", "license",
        "license_review_status", "training_use_allowed", "redistribution_allowed",
        "reviewed_by", "reviewed_at",
    }
    optional = {"attribution", "permission_ref"}

    for line_number, line in enumerate(lines, start=1):
        if not line.strip() or len(line.encode("utf-8")) > MAX_DATASET_PROVENANCE_LINE_BYTES:
            raise ModelManifestError(
                f"dataset provenance line {line_number} is blank or exceeds the line-size limit"
            )
        try:
            row = json.loads(line, object_pairs_hook=_unique_dataset_object)
        except (json.JSONDecodeError, ModelManifestError, RecursionError) as exc:
            raise ModelManifestError(
                f"dataset provenance line {line_number} is not valid unique-key JSON"
            ) from exc
        if not isinstance(row, dict) or not required.issubset(row) or set(row) - required - optional:
            raise ModelManifestError(
                f"dataset provenance line {line_number} has unknown or missing fields"
            )

        image = row["image"]
        if not isinstance(image, str) or not image or "\\" in image:
            raise ModelManifestError(
                f"dataset provenance line {line_number} image must be a clean relative POSIX path under images/"
            )
        image_path = PurePosixPath(image)
        if (
            image_path.is_absolute()
            or image_path.as_posix() != image
            or len(image_path.parts) < 2
            or image_path.parts[0] != "images"
            or any(part in {"", ".", ".."} for part in image_path.parts)
            or re.match(r"^[A-Za-z]:", image)
        ):
            raise ModelManifestError(
                f"dataset provenance line {line_number} image must be a clean relative POSIX path under images/"
            )
        if image in seen_images:
            raise ModelManifestError(f"dataset provenance line {line_number} duplicates an image path")
        seen_images.add(image)

        image_digest = row["image_sha256"]
        if not isinstance(image_digest, str) or not _SHA256.fullmatch(image_digest):
            raise ModelManifestError(
                f"dataset provenance line {line_number} image_sha256 must be 64 lowercase hexadecimal characters"
            )
        if image_digest in seen_digests:
            raise ModelManifestError(f"dataset provenance line {line_number} duplicates image bytes")
        seen_digests.add(image_digest)

        source_url = row["source_url"]
        revision = row["revision"]
        license_id = row["license"]
        if not all(isinstance(value, str) for value in (source_url, revision, license_id)):
            raise ModelManifestError(
                f"dataset provenance line {line_number} source_url, revision and license must be strings"
            )
        source_key = (source_url, revision, license_id)
        source = source_by_key.get(source_key)
        if source is None:
            raise ModelManifestError(
                f"dataset provenance line {line_number} does not reference an approved training_data_sources entry"
            )
        if row["license_review_status"] != source.license_review_status:
            raise ModelManifestError(
                f"dataset provenance line {line_number} license review status does not match its source"
            )
        if (
            type(row["training_use_allowed"]) is not bool
            or not row["training_use_allowed"]
            or row["training_use_allowed"] != source.training_use_allowed
        ):
            raise ModelManifestError(
                f"dataset provenance line {line_number} does not explicitly permit training use"
            )
        if (
            type(row["redistribution_allowed"]) is not bool
            or row["redistribution_allowed"] != source.redistribution_allowed
        ):
            raise ModelManifestError(
                f"dataset provenance line {line_number} redistribution status does not match its source"
            )
        reviewer = row["reviewed_by"]
        if not isinstance(reviewer, str) or not reviewer.strip() or len(reviewer.strip()) > 160:
            raise ModelManifestError(
                f"dataset provenance line {line_number} reviewed_by must be a bounded reviewer identifier"
            )
        reviewed_at = row["reviewed_at"]
        if not isinstance(reviewed_at, str):
            raise ModelManifestError(
                f"dataset provenance line {line_number} reviewed_at must be a timezone-aware ISO-8601 timestamp"
            )
        try:
            reviewed_stamp = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ModelManifestError(
                f"dataset provenance line {line_number} reviewed_at must be a timezone-aware ISO-8601 timestamp"
            ) from exc
        if reviewed_stamp.tzinfo is None or reviewed_stamp.utcoffset() is None:
            raise ModelManifestError(
                f"dataset provenance line {line_number} reviewed_at must include a timezone"
            )

        if license_id == "CC-BY-4.0":
            attribution = row.get("attribution")
            if not isinstance(attribution, str) or not attribution.strip() or len(attribution.strip()) > 500:
                raise ModelManifestError(
                    f"dataset provenance line {line_number} requires CC-BY attribution"
                )
        elif "attribution" in row and (
            not isinstance(row["attribution"], str) or len(row["attribution"]) > 500
        ):
            raise ModelManifestError(
                f"dataset provenance line {line_number} attribution must be a bounded string"
            )
        if license_id == "LicenseRef-ExplicitPermission":
            permission_ref = row.get("permission_ref")
            if not isinstance(permission_ref, str) or not permission_ref.strip() or len(permission_ref.strip()) > 200:
                raise ModelManifestError(
                    f"dataset provenance line {line_number} requires a bounded permission_ref"
                )
        elif "permission_ref" in row:
            raise ModelManifestError(
                f"dataset provenance line {line_number} permission_ref is only valid for explicit permission"
            )
        used_sources.add(source_key)

    if used_sources != set(source_by_key):
        raise ModelManifestError("training_data_sources contains entries not referenced by per-image provenance")


def load_manifest(path: str | Path, *, verify_model: bool = True) -> ModelManifest:
    manifest_path = Path(path).expanduser().resolve(strict=True)
    try:
        # Read at most one byte beyond the limit so a malformed or hostile
        # local manifest cannot trigger an unbounded allocation.
        with manifest_path.open("rb") as handle:
            raw_bytes = handle.read(MAX_MANIFEST_BYTES + 1)
        if len(raw_bytes) > MAX_MANIFEST_BYTES:
            raise ModelManifestError(
                f"model manifest exceeds maximum supported size of {MAX_MANIFEST_BYTES} bytes"
            )
        raw = json.loads(raw_bytes.decode("utf-8"), object_pairs_hook=_unique_object)
    except ModelManifestError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ModelManifestError("cannot read bounded UTF-8 JSON model manifest") from exc
    if not isinstance(raw, dict) or type(raw.get("manifest_version")) is not int or raw.get("manifest_version") != 2:
        raise ModelManifestError("unsupported model manifest version")
    model_file = raw.get("model_file")
    if not isinstance(model_file, str) or not model_file or Path(model_file).is_absolute():
        raise ModelManifestError("model_file must be a non-empty relative path")
    model_root = manifest_path.parent.resolve()
    candidate = model_root / model_file
    cursor = model_root
    for part in Path(model_file).parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ModelManifestError("model_file must not traverse symbolic links")
    try:
        model_path = candidate.resolve()
        model_path.relative_to(model_root)
    except (OSError, ValueError) as exc:
        raise ModelManifestError("model_file must stay inside the manifest directory") from exc
    if not model_path.is_file():
        raise ModelManifestError("model_file is missing or is not a regular file")

    try:
        model_size = model_path.stat().st_size
    except OSError as exc:
        raise ModelManifestError("cannot stat model file") from exc
    if model_size > MAX_MODEL_BYTES:
        raise ModelManifestError(
            f"ONNX model exceeds maximum supported size of {MAX_MODEL_BYTES} bytes"
        )

    digest = raw.get("model_sha256")
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        raise ModelManifestError("model_sha256 must be 64 lowercase hexadecimal characters")
    if verify_model:
        hasher = hashlib.sha256()
        with model_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(chunk)
        if hasher.hexdigest() != digest:
            raise ModelManifestError("ONNX model SHA-256 mismatch")

    version = raw.get("model_version")
    source = raw.get("model_source_url")
    license_id = raw.get("model_license")
    license_review = raw.get("license_review_status")
    if not isinstance(version, str) or not version.strip() or len(version) > 100:
        raise ModelManifestError("model_version is required")
    parsed_source = urlparse(source) if isinstance(source, str) else None
    if (parsed_source is None or parsed_source.scheme != "https" or not parsed_source.netloc
            or parsed_source.username or parsed_source.password):
        raise ModelManifestError("model_source_url must be a credential-free HTTPS provenance URL")
    if not isinstance(license_id, str) or not _SPDX.fullmatch(license_id):
        raise ModelManifestError("model_license must be an SPDX-like identifier")
    if not isinstance(license_review, str) or license_review not in {"approved", "public-domain"}:
        raise ModelManifestError("model license must be explicitly reviewed before inference")

    evidence_url = raw.get("license_evidence_url")
    evidence = urlparse(evidence_url) if isinstance(evidence_url, str) else None
    if (evidence is None or evidence.scheme != "https" or not evidence.netloc
            or evidence.username or evidence.password):
        raise ModelManifestError("license_evidence_url must be a credential-free HTTPS source")
    reviewer = raw.get("license_reviewed_by")
    if not isinstance(reviewer, str) or not reviewer.strip() or len(reviewer) > 160:
        raise ModelManifestError("license_reviewed_by must identify the responsible reviewer")
    reviewed_at = raw.get("license_reviewed_at")
    if not isinstance(reviewed_at, str):
        raise ModelManifestError("license_reviewed_at must be an ISO-8601 timestamp")
    try:
        reviewed_stamp = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ModelManifestError("license_reviewed_at must be an ISO-8601 timestamp") from exc
    if reviewed_stamp.tzinfo is None or reviewed_stamp.utcoffset() is None:
        raise ModelManifestError("license_reviewed_at must include a timezone")
    inference_use_allowed = raw.get("inference_use_allowed")
    redistribution_allowed = raw.get("redistribution_allowed")
    if type(inference_use_allowed) is not bool or type(redistribution_allowed) is not bool:
        raise ModelManifestError("inference_use_allowed and redistribution_allowed must be explicit booleans")
    if not inference_use_allowed:
        raise ModelManifestError("model license review does not permit inference use")
    inference_status = raw.get("inference_status")
    if not isinstance(inference_status, str) or inference_status not in {"experimental", "independently_validated"}:
        raise ModelManifestError("inference_status must be experimental or independently_validated")
    if inference_status == "independently_validated":
        report = raw.get("validation_report_url")
        if not isinstance(report, str) or not report.startswith("https://"):
            raise ModelManifestError("independent validation requires a public validation_report_url")

    dataset_manifest_file = raw.get("dataset_manifest_file")
    dataset_manifest_digest = raw.get("dataset_manifest_sha256")
    if (
        not isinstance(dataset_manifest_file, str)
        or not dataset_manifest_file
        or "\\" in dataset_manifest_file
    ):
        raise ModelManifestError("dataset_manifest_file must be a clean relative POSIX path")
    dataset_relative_path = PurePosixPath(dataset_manifest_file)
    if (
        dataset_relative_path.is_absolute()
        or dataset_relative_path.as_posix() != dataset_manifest_file
        or any(part in {"", ".", ".."} for part in dataset_relative_path.parts)
        or re.match(r"^[A-Za-z]:", dataset_manifest_file)
    ):
        raise ModelManifestError("dataset_manifest_file must be a clean relative POSIX path")
    if not isinstance(dataset_manifest_digest, str) or not _SHA256.fullmatch(dataset_manifest_digest):
        raise ModelManifestError("dataset_manifest_sha256 must be 64 lowercase hexadecimal characters")
    dataset_cursor = model_root
    for part in dataset_relative_path.parts:
        dataset_cursor = dataset_cursor / part
        if dataset_cursor.is_symlink():
            raise ModelManifestError("dataset provenance manifest must not traverse symbolic links")
    try:
        dataset_manifest_path = model_root.joinpath(*dataset_relative_path.parts).resolve()
        dataset_manifest_path.relative_to(model_root)
    except (OSError, ValueError) as exc:
        raise ModelManifestError("dataset provenance manifest must stay inside the model directory") from exc
    if not dataset_manifest_path.is_file():
        raise ModelManifestError("dataset provenance manifest is missing or is not a regular file")
    try:
        with dataset_manifest_path.open("rb") as handle:
            dataset_manifest_bytes = handle.read(MAX_DATASET_PROVENANCE_BYTES + 1)
    except OSError as exc:
        raise ModelManifestError("cannot read bounded dataset provenance manifest") from exc
    if len(dataset_manifest_bytes) > MAX_DATASET_PROVENANCE_BYTES:
        raise ModelManifestError(
            f"dataset provenance manifest exceeds maximum supported size of {MAX_DATASET_PROVENANCE_BYTES} bytes"
        )
    if hashlib.sha256(dataset_manifest_bytes).hexdigest() != dataset_manifest_digest:
        raise ModelManifestError("dataset provenance manifest SHA-256 mismatch")

    raw_sources = raw.get("training_data_sources")
    if not isinstance(raw_sources, list) or not raw_sources or len(raw_sources) > 256:
        raise ModelManifestError("training_data_sources must contain 1 to 256 reviewed dataset sources")
    training_data_sources = []
    seen_sources = set()
    for row in raw_sources:
        if not isinstance(row, dict):
            raise ModelManifestError("each training_data_sources entry must be an object")
        source_url = row.get("source_url")
        parsed_dataset_source = urlparse(source_url) if isinstance(source_url, str) else None
        if (parsed_dataset_source is None or parsed_dataset_source.scheme != "https"
                or not parsed_dataset_source.netloc or parsed_dataset_source.username
                or parsed_dataset_source.password or parsed_dataset_source.query
                or parsed_dataset_source.fragment):
            raise ModelManifestError("dataset source_url must be credential-free HTTPS without query or fragment")
        revision = row.get("revision")
        if not isinstance(revision, str) or not _DATASET_REVISION.fullmatch(revision.strip()):
            raise ModelManifestError("dataset revision must be a full Git commit SHA or SHA-256 archive digest")
        revision = revision.strip()
        source_key = (source_url, revision, row.get("license"))
        if source_key in seen_sources:
            raise ModelManifestError("duplicate training dataset source and revision")
        seen_sources.add(source_key)
        dataset_license = row.get("license")
        if not isinstance(dataset_license, str) or not _SPDX.fullmatch(dataset_license):
            raise ModelManifestError("training dataset license must be an SPDX-like identifier")
        if dataset_license not in _DATASET_LICENSES:
            raise ModelManifestError("training dataset license is not in the supported reviewed-license allowlist")
        dataset_review = row.get("license_review_status")
        if not isinstance(dataset_review, str) or dataset_review not in {"approved", "public-domain"}:
            raise ModelManifestError("training dataset license must be explicitly reviewed before inference")
        evidence_url = row.get("license_evidence_url")
        parsed_evidence = urlparse(evidence_url) if isinstance(evidence_url, str) else None
        if (parsed_evidence is None or parsed_evidence.scheme != "https"
                or not parsed_evidence.netloc or parsed_evidence.username
                or parsed_evidence.password or parsed_evidence.query
                or parsed_evidence.fragment):
            raise ModelManifestError("dataset license_evidence_url must be credential-free HTTPS without query or fragment")
        canonical_evidence = _DATASET_LICENSE_EVIDENCE.get(dataset_license)
        if canonical_evidence and evidence_url.rstrip("/") != canonical_evidence.rstrip("/"):
            raise ModelManifestError("dataset license_evidence_url does not match the supported license")
        training_allowed = row.get("training_use_allowed")
        redistribution_allowed_dataset = row.get("redistribution_allowed")
        if type(training_allowed) is not bool or type(redistribution_allowed_dataset) is not bool:
            raise ModelManifestError("dataset training_use_allowed and redistribution_allowed must be explicit booleans")
        if not training_allowed:
            raise ModelManifestError("training dataset license review does not permit training use")
        dataset_reviewer = row.get("reviewed_by")
        if not isinstance(dataset_reviewer, str) or not dataset_reviewer.strip() or len(dataset_reviewer) > 160:
            raise ModelManifestError("dataset reviewed_by must identify the responsible reviewer")
        dataset_reviewed_at = row.get("reviewed_at")
        if not isinstance(dataset_reviewed_at, str):
            raise ModelManifestError("dataset reviewed_at must be an ISO-8601 timestamp")
        try:
            dataset_reviewed_stamp = datetime.fromisoformat(dataset_reviewed_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ModelManifestError("dataset reviewed_at must be an ISO-8601 timestamp") from exc
        if dataset_reviewed_stamp.tzinfo is None or dataset_reviewed_stamp.utcoffset() is None:
            raise ModelManifestError("dataset reviewed_at must include a timezone")
        training_data_sources.append(TrainingDataSource(
            source_url=source_url,
            revision=revision,
            license_id=dataset_license,
            license_review_status=dataset_review,
            license_evidence_url=evidence_url,
            training_use_allowed=training_allowed,
            redistribution_allowed=redistribution_allowed_dataset,
            reviewed_by=dataset_reviewer.strip(),
            reviewed_at=dataset_reviewed_at,
        ))

    _validate_dataset_provenance(dataset_manifest_bytes, tuple(training_data_sources))

    input_spec = raw.get("input")
    outputs = raw.get("outputs")
    if not isinstance(input_spec, dict) or not isinstance(outputs, dict):
        raise ModelManifestError("input and outputs specifications are required")
    width, height = input_spec.get("width"), input_spec.get("height")
    if type(width) is not int or type(height) is not int or not 32 <= width <= 4096 or not 32 <= height <= 4096:
        raise ModelManifestError("input width and height must be integers from 32 to 4096")
    if input_spec.get("color") != "RGB" or input_spec.get("layout") != "NCHW" or input_spec.get("scale") != "0..1":
        raise ModelManifestError("only RGB/NCHW/0..1 preprocessing is supported")
    input_name = input_spec.get("name")
    if not isinstance(input_name, str) or not input_name.strip():
        raise ModelManifestError("ONNX input name is required")
    resize_mode = input_spec.get("resize_mode", "stretch")
    if not isinstance(resize_mode, str) or resize_mode not in {"stretch", "letterbox"}:
        raise ModelManifestError("resize_mode must be stretch or letterbox")
    box_format = outputs.get("box_format")
    boxes_output = scores_output = class_ids_output = detections_output = None
    if box_format == "xyxy_normalized_post_nms":
        output_names = [outputs.get("boxes"), outputs.get("scores"), outputs.get("class_ids")]
        if any(not isinstance(item, str) or not item.strip() for item in output_names) or len(set(output_names)) != 3:
            raise ModelManifestError("distinct boxes, scores and class_ids output names are required")
        boxes_output, scores_output, class_ids_output = output_names
    elif box_format == "xyxy_pixels_nms_matrix6":
        detections_output = outputs.get("detections")
        if not isinstance(detections_output, str) or not detections_output.strip():
            raise ModelManifestError("detections output name is required for matrix6 format")
    else:
        raise ModelManifestError("unsupported output box format")

    class_rows = raw.get("classes")
    if not isinstance(class_rows, list) or not class_rows:
        raise ModelManifestError("at least one class mapping is required")
    classes: dict[int, ModelClass] = {}
    labels: set[str] = set()
    for row in class_rows:
        if not isinstance(row, dict) or type(row.get("id")) is not int:
            raise ModelManifestError("each class requires an integer id")
        cid = row["id"]
        label = row.get("label")
        threshold = row.get("threshold")
        prey = row.get("prey_detected", False)
        if (
            cid in classes
            or not isinstance(label, str)
            or not label.strip()
            or len(label) > 160
            or label.strip() in labels
        ):
            raise ModelManifestError("duplicate class id/label or invalid class label")
        labels.add(label.strip())
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not math.isfinite(float(threshold)) or not 0 <= float(threshold) <= 1:
            raise ModelManifestError("class threshold must be finite and in 0..1")
        if type(prey) is not bool:
            raise ModelManifestError("prey_detected must be boolean")
        classes[cid] = ModelClass(label.strip(), float(threshold), prey)

    return ModelManifest(
        path=manifest_path,
        model_path=model_path,
        model_sha256=digest,
        model_version=version.strip(),
        model_source_url=source,
        model_license=license_id,
        license_review_status=license_review,
        license_evidence_url=evidence_url,
        license_reviewed_by=reviewer.strip(),
        license_reviewed_at=reviewed_at,
        inference_use_allowed=inference_use_allowed,
        redistribution_allowed=redistribution_allowed,
        dataset_manifest_path=dataset_manifest_path,
        dataset_manifest_sha256=dataset_manifest_digest,
        training_data_sources=tuple(training_data_sources),
        inference_status=inference_status,
        input_name=input_name.strip(),
        width=width,
        height=height,
        resize_mode=resize_mode,
        box_format=box_format,
        boxes_output=boxes_output,
        scores_output=scores_output,
        class_ids_output=class_ids_output,
        detections_output=detections_output,
        classes=classes,
    )
