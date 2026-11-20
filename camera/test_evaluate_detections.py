import json
import tempfile
import unittest
from pathlib import Path

from camera.evaluate_detections import EvaluationError, evaluate, load_records


class DetectionEvaluationTests(unittest.TestCase):
    def record(self, image_id="img-1", gt=None, pred=None):
        return {
            "image_id": image_id,
            "image_sha256": "a" * 64,
            "ground_truth": gt or [],
            "predictions": pred or [],
        }

    def run_eval(self, rows, **kwargs):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "annotations.jsonl"
            path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
            records, _ = load_records(path)
            return evaluate(records, **kwargs)

    def test_perfect_prediction_scores_one(self):
        box = [10, 10, 30, 30]
        report = self.run_eval([self.record(gt=[{"class_id": 0, "bbox_xyxy": box}],
                                       pred=[{"class_id": 0, "confidence": 0.95, "bbox_xyxy": box}])])
        row = report["classes"]["0"]
        self.assertEqual((row["tp"], row["fp"], row["fn"]), (1, 0, 0))
        self.assertEqual(row["precision"], 1.0)
        self.assertEqual(row["recall"], 1.0)
        self.assertEqual(row["ap_at_iou"], 1.0)

    def test_duplicate_prediction_is_false_positive(self):
        box = [10, 10, 30, 30]
        report = self.run_eval([self.record(
            gt=[{"class_id": 0, "bbox_xyxy": box}],
            pred=[{"class_id": 0, "confidence": 0.95, "bbox_xyxy": box},
                  {"class_id": 0, "confidence": 0.90, "bbox_xyxy": box}]
        )])
        row = report["classes"]["0"]
        self.assertEqual((row["tp"], row["fp"], row["fn"]), (1, 1, 0))

    def test_wrong_class_is_fp_and_fn(self):
        box = [10, 10, 30, 30]
        report = self.run_eval([self.record(
            gt=[{"class_id": 0, "bbox_xyxy": box}],
            pred=[{"class_id": 1, "confidence": 0.95, "bbox_xyxy": box}]
        )])
        self.assertEqual(report["classes"]["0"]["fn"], 1)
        self.assertEqual(report["classes"]["1"]["fp"], 1)

    def test_confidence_and_iou_thresholds_apply(self):
        box = [10, 10, 30, 30]
        report = self.run_eval([self.record(
            gt=[{"class_id": 0, "bbox_xyxy": box}],
            pred=[{"class_id": 0, "confidence": 0.2, "bbox_xyxy": box}]
        )], confidence_threshold=0.5)
        self.assertEqual(report["classes"]["0"]["fn"], 1)
        self.assertEqual(report["classes"]["0"]["predictions_at_threshold"], 0)

    def test_rejects_duplicate_image_and_invalid_coordinates(self):
        row = self.record()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "annotations.jsonl"
            path.write_text(json.dumps(row) + "\n" + json.dumps(row) + "\n", encoding="utf-8")
            with self.assertRaises(EvaluationError):
                load_records(path)
        bad = self.record(gt=[{"class_id": 0, "bbox_xyxy": [5, 5, 5, 9]}])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "annotations.jsonl"
            path.write_text(json.dumps(bad) + "\n", encoding="utf-8")
            with self.assertRaises(EvaluationError):
                load_records(path)


if __name__ == "__main__":
    unittest.main()
