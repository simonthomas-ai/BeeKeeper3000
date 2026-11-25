"""Bounded, integrity-checked reads for local ONNX artifacts."""
from __future__ import annotations

import hashlib
import hmac
import os
import stat
from pathlib import Path

MAX_MODEL_BYTES = 128 * 1024 * 1024


class ModelArtifactError(ValueError):
    """Raised when a local ONNX artifact is unsafe or fails integrity checks."""


def read_model_artifact(
    path: str | Path, *, expected_sha256: str | None = None
) -> tuple[Path, bytes, str]:
    """Read one bounded byte snapshot and optionally verify its expected digest."""
    candidate = Path(path).expanduser()
    if candidate.is_symlink():
        raise ModelArtifactError("model path must not be a symbolic link")

    try:
        model_path = candidate.resolve(strict=True)
        if not model_path.is_file() or model_path.suffix.lower() != ".onnx":
            raise ModelArtifactError("model path must be a regular .onnx file")
        with model_path.open("rb") as handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise ModelArtifactError("model path must be a regular .onnx file")
            if before.st_size > MAX_MODEL_BYTES:
                raise ModelArtifactError(
                    f"ONNX model exceeds maximum supported size of {MAX_MODEL_BYTES} bytes"
                )
            payload = handle.read(MAX_MODEL_BYTES + 1)
            after = os.fstat(handle.fileno())
    except ModelArtifactError:
        raise
    except OSError as exc:
        raise ModelArtifactError("cannot read local ONNX model") from exc

    if len(payload) > MAX_MODEL_BYTES:
        raise ModelArtifactError(
            f"ONNX model exceeds maximum supported size of {MAX_MODEL_BYTES} bytes"
        )
    if len(payload) != before.st_size or after.st_size != before.st_size:
        raise ModelArtifactError("ONNX model changed or was truncated while being read")

    digest = hashlib.sha256(payload).hexdigest()
    if expected_sha256 is not None and (
        not isinstance(expected_sha256, str)
        or not hmac.compare_digest(digest, expected_sha256)
    ):
        raise ModelArtifactError("ONNX model SHA-256 mismatch at load time")
    return model_path, payload, digest
