import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from camera.model_manifest import load_manifest, ModelManifestError


class ManifestTests(unittest.TestCase):
    def make(self, tmp, **changes):
        model = Path(tmp) / "detector.onnx"
        model.write_bytes(b"synthetic model file for hash checks")
        data = {
            "manifest_version": 1, "model_file": "detector.onnx",
            "model_sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
            "model_version": "0.0-test", "model_source_url": "https://example.org/model",
            "model_license": "MIT", "license_review_status": "approved", "inference_status": "experimental",
            "input": {"name": "images", "width": 640, "height": 640, "color": "RGB", "layout": "NCHW", "scale": "0..1"},
            "outputs": {"boxes": "boxes", "scores": "scores", "class_ids": "classes", "box_format": "xyxy_normalized_post_nms"},
            "classes": [{"id": 0, "label": "vespa_velutina_candidate", "threshold": 0.8, "prey_detected": False}],
        }
        data.update(changes)
        target = Path(tmp) / "manifest.json"
        target.write_text(json.dumps(data), encoding="utf-8")
        return target

    def test_valid_manifest_and_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = load_manifest(self.make(tmp))
            self.assertEqual(manifest.classes[0].label, "vespa_velutina_candidate")

    def test_rejects_unreviewed_license_and_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make(tmp, license_review_status="not-reviewed")
            with self.assertRaises(ModelManifestError):
                load_manifest(path)
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make(tmp, model_sha256="0" * 64)
            with self.assertRaises(ModelManifestError):
                load_manifest(path)

    def test_accepts_ultralytics_post_nms_matrix_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make(tmp)
            data = json.loads(path.read_text(encoding="utf-8"))
            data["input"]["resize_mode"] = "letterbox"
            data["outputs"] = {
                "detections": "output0",
                "box_format": "xyxy_pixels_nms_matrix6"
            }
            path.write_text(json.dumps(data), encoding="utf-8")
            manifest = load_manifest(path)
            self.assertEqual(manifest.box_format, "xyxy_pixels_nms_matrix6")
            self.assertEqual(manifest.detections_output, "output0")
            self.assertEqual(manifest.resize_mode, "letterbox")

    def test_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            outside = parent / "outside.onnx"
            outside.write_bytes(b"outside")
            path = self.make(tmp, model_file="../outside.onnx")
            with self.assertRaises(ModelManifestError):
                load_manifest(path)


if __name__ == "__main__":
    unittest.main()
