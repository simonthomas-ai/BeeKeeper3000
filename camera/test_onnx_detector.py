import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from camera.onnx_detector import DetectorError, OnnxDetector
from camera.model_manifest import ModelClass


class FakeSession:
    def __init__(self, outputs, input_names=("images",), output_names=None):
        self.values = outputs
        self.input_names = input_names
        self.output_names = output_names or tuple(outputs.keys())
        self.feed = None

    def get_inputs(self):
        return [SimpleNamespace(name=name) for name in self.input_names]

    def get_outputs(self):
        return [SimpleNamespace(name=name) for name in self.output_names]

    def run(self, names, feed):
        self.feed = feed
        return [self.values[name] for name in names]


class OnnxDetectorTests(unittest.TestCase):
    def make_detector(self, outputs, *, matrix=False, input_names=("images",), output_names=None):
        session = FakeSession(outputs, input_names=input_names, output_names=output_names)
        ort = types.SimpleNamespace(
            SessionOptions=lambda: SimpleNamespace(
                intra_op_num_threads=0, inter_op_num_threads=0, execution_mode=None
            ),
            ExecutionMode=SimpleNamespace(ORT_SEQUENTIAL=1),
            InferenceSession=lambda *args, **kwargs: session,
        )
        manifest = SimpleNamespace(
            model_path=Path("fake.onnx"),
            input_name="images",
            detections_output="output0" if matrix else None,
            boxes_output=None if matrix else "boxes",
            scores_output=None if matrix else "scores",
            class_ids_output=None if matrix else "class_ids",
            width=640, height=640, resize_mode="stretch",
            box_format="xyxy_pixels_nms_matrix6" if matrix else "xyxy_normalized_post_nms",
            classes={
                0: ModelClass("vespa_velutina_candidate", 0.8, False),
                1: ModelClass("vespa_crabro_candidate", 0.75, False),
            },
        )
        with patch.dict(sys.modules, {"onnxruntime": ort}):
            detector = OnnxDetector(manifest)
        return detector, session

    def test_normalized_outputs_filter_unknown_low_score_and_invalid_boxes(self):
        detector, session = self.make_detector({
            "boxes": np.asarray([
                [0.1, 0.1, 0.5, 0.5],
                [0.1, 0.1, 0.5, 0.5],
                [0.7, 0.7, 0.6, 0.8],
                [np.nan, 0.1, 0.5, 0.5],
                [0.1, 0.1, 0.5, 0.5],
            ], dtype=np.float32),
            "scores": np.asarray([0.95, 0.2, 0.99, 0.99, 0.99], dtype=np.float32),
            "class_ids": np.asarray([0, 0, 0, 0, 99], dtype=np.float32),
        })
        result = detector.detect(np.zeros((80, 100, 3), dtype=np.uint8))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].species, "vespa_velutina_candidate")
        self.assertEqual(session.feed["images"].shape, (1, 3, 640, 640))

    def test_matrix6_pixel_outputs_are_decoded(self):
        detector, _ = self.make_detector({
            "output0": np.asarray([[10, 20, 100, 120, 0.9, 1]], dtype=np.float32)
        }, matrix=True)
        result = detector.detect(np.zeros((100, 100, 3), dtype=np.uint8))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].species, "vespa_crabro_candidate")

    def test_matrix6_rejects_wrong_shape(self):
        detector, _ = self.make_detector({"output0": np.asarray([[1, 2, 3, 4, 0.9]], dtype=np.float32)}, matrix=True)
        with self.assertRaises(DetectorError):
            detector.detect(np.zeros((100, 100, 3), dtype=np.uint8))

    def test_rejects_graph_input_name_mismatch(self):
        with self.assertRaises(DetectorError):
            self.make_detector({
                "boxes": np.zeros((1, 4), dtype=np.float32),
                "scores": np.zeros((1,), dtype=np.float32),
                "class_ids": np.zeros((1,), dtype=np.float32),
            }, input_names=("wrong",))

    def test_rejects_bad_frame_shape(self):
        detector, _ = self.make_detector({
            "boxes": np.zeros((0, 4), dtype=np.float32),
            "scores": np.zeros((0,), dtype=np.float32),
            "class_ids": np.zeros((0,), dtype=np.float32),
        })
        with self.assertRaises(ValueError):
            detector.detect(np.zeros((10, 10), dtype=np.uint8))


if __name__ == "__main__":
    unittest.main()
