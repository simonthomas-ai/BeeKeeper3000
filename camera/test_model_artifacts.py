import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from camera.model_artifacts import (
    MAX_MODEL_BYTES,
    ModelArtifactError,
    read_model_artifact,
)


class ModelArtifactTests(unittest.TestCase):
    def test_returns_bounded_snapshot_and_sha256(self):
        payload = b"small onnx test fixture"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "candidate.onnx"
            path.write_bytes(payload)
            resolved, actual, digest = read_model_artifact(path)
        self.assertEqual(resolved.name, "candidate.onnx")
        self.assertEqual(actual, payload)
        self.assertEqual(digest, hashlib.sha256(payload).hexdigest())

    def test_rejects_oversized_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "large.onnx"
            path.write_bytes(b"x" * 5)
            with patch("camera.model_artifacts.MAX_MODEL_BYTES", 4):
                with self.assertRaisesRegex(ModelArtifactError, "exceeds maximum"):
                    read_model_artifact(path)

    def test_rejects_load_time_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "candidate.onnx"
            path.write_bytes(b"model bytes")
            with self.assertRaisesRegex(ModelArtifactError, "SHA-256 mismatch"):
                read_model_artifact(path, expected_sha256="0" * 64)

    def test_rejects_symbolic_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target.onnx"
            alias = Path(tmp) / "alias.onnx"
            target.write_bytes(b"model bytes")
            try:
                alias.symlink_to(target)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"symbolic links are unavailable: {exc}")
            with self.assertRaisesRegex(ModelArtifactError, "symbolic link"):
                read_model_artifact(alias)

    def test_rejects_non_onnx_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "weights.pt"
            path.write_bytes(b"not onnx")
            with self.assertRaisesRegex(ModelArtifactError, "regular .onnx file"):
                read_model_artifact(path)


if __name__ == "__main__":
    unittest.main()
