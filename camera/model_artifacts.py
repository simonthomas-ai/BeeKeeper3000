"""Bounded, integrity-checked reads for local ONNX artifacts."""
from __future__ import annotations

import errno
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
    """Read one bounded byte snapshot and optionally verify its expected digest.

    On platforms that expose O_NOFOLLOW, the final path component is opened
    without following a symlink. The open file descriptor is then the sole
    source of bytes and size metadata, so replacing the pathname after open
    cannot change the snapshot being hashed or passed to ONNX Runtime.
    """
    candidate = Path(path).expanduser()
    if candidate.is_symlink():
        raise ModelArtifactError("model path must not be a symbolic link")
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    if candidate.suffix.lower() != ".onnx":
        raise ModelArtifactError("model path must be a regular .onnx file")

    nofollow = getattr(os, "O_NOFOLLOW", 0)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | nofollow
    descriptor = None
    try:
        try:
            descriptor = os.open(candidate, flags)
        except OSError as exc:
            if nofollow and exc.errno == errno.ELOOP:
                raise ModelArtifactError(
                    "model path must not be a symbolic link"
                ) from exc
            raise

        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ModelArtifactError("model path must be a regular .onnx file")
        if before.st_size > MAX_MODEL_BYTES:
            raise ModelArtifactError(
                f"ONNX model exceeds maximum supported size of {MAX_MODEL_BYTES} bytes"
            )

        handle = os.fdopen(descriptor, "rb", closefd=True)
        descriptor = None
        with handle:
            payload = handle.read(MAX_MODEL_BYTES + 1)
            after = os.fstat(handle.fileno())
    except ModelArtifactError:
        raise
    except OSError as exc:
        raise ModelArtifactError("cannot read local ONNX model") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)

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
    return candidate.absolute(), payload, digest
