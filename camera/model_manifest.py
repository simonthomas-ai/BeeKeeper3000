"""Fail-closed ONNX model manifest and provenance validation."""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_SPDX = re.compile(r"^[A-Za-z0-9.+-]{2,80}$")


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
class ModelManifest:
    path: Path
    model_path: Path
    model_sha256: str
    model_version: str
    model_source_url: str
    model_license: str
    license_review_status: str
    input_name: str
    width: int
    height: int
    boxes_output: str
    scores_output: str
    class_ids_output: str
    classes: dict[int, ModelClass]


def load_manifest(path: str | Path, *, verify_model: bool = True) -> ModelManifest:
    manifest_path = Path(path).expanduser().resolve(strict=True)
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ModelManifestError("cannot read UTF-8 JSON model manifest") from exc
    if not isinstance(raw, dict) or raw.get("manifest_version") != 1:
        raise ModelManifestError("unsupported model manifest version")
    model_file = raw.get("model_file")
    if not isinstance(model_file, str) or not model_file or Path(model_file).is_absolute():
        raise ModelManifestError("model_file must be a non-empty relative path")
    model_root = manifest_path.parent.resolve()
    try:
        model_path = (model_root / model_file).resolve()
        model_path.relative_to(model_root)
    except (OSError, ValueError) as exc:
        raise ModelManifestError("model_file must stay inside the manifest directory") from exc
    if not model_path.is_file():
        raise ModelManifestError("model_file is missing or is not a regular file")

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
    if parsed_source is None or parsed_source.scheme != "https" or not parsed_source.netloc:
        raise ModelManifestError("model_source_url must be an HTTPS provenance URL")
    if not isinstance(license_id, str) or not _SPDX.fullmatch(license_id):
        raise ModelManifestError("model_license must be an SPDX-like identifier")
    if license_review not in {"approved", "public-domain"}:
        raise ModelManifestError("model license must be explicitly reviewed before inference")
    if raw.get("inference_status") not in {"experimental", "independently_validated"}:
        raise ModelManifestError("inference_status must be experimental or independently_validated")
    if raw.get("inference_status") == "independently_validated":
        report = raw.get("validation_report_url")
        if not isinstance(report, str) or not report.startswith("https://"):
            raise ModelManifestError("independent validation requires a public validation_report_url")

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
    if outputs.get("box_format") != "xyxy_normalized_post_nms":
        raise ModelManifestError("output boxes must be normalized xyxy after model-side NMS")
    output_names = [outputs.get("boxes"), outputs.get("scores"), outputs.get("class_ids")]
    if any(not isinstance(item, str) or not item.strip() for item in output_names) or len(set(output_names)) != 3:
        raise ModelManifestError("distinct boxes, scores and class_ids output names are required")

    class_rows = raw.get("classes")
    if not isinstance(class_rows, list) or not class_rows:
        raise ModelManifestError("at least one class mapping is required")
    classes: dict[int, ModelClass] = {}
    for row in class_rows:
        if not isinstance(row, dict) or type(row.get("id")) is not int:
            raise ModelManifestError("each class requires an integer id")
        cid = row["id"]
        label = row.get("label")
        threshold = row.get("threshold")
        prey = row.get("prey_detected", False)
        if cid in classes or not isinstance(label, str) or not label.strip() or len(label) > 160:
            raise ModelManifestError("duplicate class id or invalid class label")
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not math.isfinite(float(threshold)) or not 0 <= float(threshold) <= 1:
            raise ModelManifestError("class threshold must be finite and in 0..1")
        if type(prey) is not bool:
            raise ModelManifestError("prey_detected must be boolean")
        classes[cid] = ModelClass(label.strip(), float(threshold), prey)

    return ModelManifest(
        manifest_path, model_path, digest, version.strip(), source, license_id, license_review,
        input_name.strip(), width, height, output_names[0], output_names[1], output_names[2], classes
    )
