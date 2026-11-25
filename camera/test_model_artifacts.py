import hashlib
import os
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

    @unittest.skipUnless(getattr(os, "O_NOFOLLOW", 0), "O_NOFOLLOW is unavailable")
    def test_rejects_symlink_swapped_in_after_initial_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target.onnx"
            alias = Path(tmp) / "alias.onnx"
            target.write_bytes(b"model bytes")
            alias.write_bytes(b"initial regular file")
            original_is_symlink = Path.is_symlink

            def swap_after_check(candidate):
                if candidate == alias:
                    alias.unlink()
                    alias.symlink_to(target)
                    return False
                return original_is_symlink(candidate)

            with patch.object(Path, "is_symlink", swap_after_check):
                with self.assertRaisesRegex(ModelArtifactError, "symbolic link"):
                    read_model_artifact(alias)

    @unittest.skipIf(os.name == "nt", "open-file replacement semantics differ on Windows")
    def test_reads_the_open_descriptor_snapshot_after_path_replacement(self):
        original = b"approved model bytes"
        replacement = b"different model bytes"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "candidate.onnx"
            replacement_path = Path(tmp) / "replacement.onnx"
            path.write_bytes(original)
            replacement_path.write_bytes(replacement)
            real_open = os.open

            def open_then_replace(candidate, flags):
                descriptor = real_open(candidate, flags)
                if Path(candidate) == path:
                    os.replace(replacement_path, path)
                return descriptor

            with patch("camera.model_artifacts.os.open", side_effect=open_then_replace):
                _, payload, digest = read_model_artifact(
                    path, expected_sha256=hashlib.sha256(original).hexdigest()
                )

        self.assertEqual(payload, original)
        self.assertEqual(digest, hashlib.sha256(original).hexdigest())

    def test_rejects_non_onnx_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "weights.pt"
            path.write_bytes(b"not onnx")
            with self.assertRaisesRegex(ModelArtifactError, "regular .onnx file"):
                read_model_artifact(path)


if __name__ == "__main__":
    unittest.main()
