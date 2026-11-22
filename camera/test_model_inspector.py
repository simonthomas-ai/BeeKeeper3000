import hashlib
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from camera.model_inspector import inspect_model


class FakeNode:
    def __init__(self, name, node_type, shape):
        self.name = name
        self.type = node_type
        self.shape = shape


class FakeSession:
    def __init__(self, path, providers):
        self.path = path
        self.requested_providers = providers

    def get_providers(self):
        return ["CPUExecutionProvider"]

    def get_inputs(self):
        return [FakeNode("images", "tensor(float)", ["batch", 3, 640, 640])]

    def get_outputs(self):
        return [FakeNode("output0", "tensor(float)", [1, 300, 6])]


class ModelInspectorTests(unittest.TestCase):
    def test_reports_hash_graph_io_and_does_not_claim_approval(self):
        model_bytes = b"local model fixture"
        fake_runtime = types.SimpleNamespace(
            __version__="test-runtime",
            get_available_providers=lambda: ["CPUExecutionProvider"],
            InferenceSession=FakeSession,
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "detector.onnx"
            path.write_bytes(model_bytes)
            with patch.dict(sys.modules, {"onnxruntime": fake_runtime}):
                result = inspect_model(path)

        self.assertEqual(result["size_bytes"], len(model_bytes))
        self.assertEqual(result["sha256"], hashlib.sha256(model_bytes).hexdigest())
        self.assertEqual(result["inputs"][0]["shape"], ["batch", 3, 640, 640])
        self.assertEqual(result["outputs"][0]["name"], "output0")
        self.assertFalse(result["activation_manifest_generated"])
        self.assertIn("no inference", result["note"])

    def test_rejects_non_onnx_files_before_loading_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "weights.pt"
            path.write_bytes(b"not an ONNX file")
            with self.assertRaisesRegex(ValueError, "regular .onnx file"):
                inspect_model(path)


if __name__ == "__main__":
    unittest.main()
