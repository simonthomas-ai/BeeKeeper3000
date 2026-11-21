import json
import tempfile
import unittest
from pathlib import Path

from camera.evaluate_events import (
    EventEvaluationError,
    evaluate_sessions,
    load_sessions,
)


class EventEvaluationTests(unittest.TestCase):
    MODEL_SHA = "b" * 64

    def session(
        self,
        *,
        session_id="session-1",
        camera_id="cam-1",
        start="2026-11-20T10:00:00Z",
        duration=3600,
        ground_truth=None,
        predictions=None,
        model_sha=None,
        review_status="verified",
    ):
        return {
            "session_id": session_id,
            "camera_id": camera_id,
            "model_sha256": model_sha or self.MODEL_SHA,
            "start_time_utc": start,
            "duration_seconds": duration,
            "ground_truth_review_status": review_status,
            "reviewer_id": "reviewer-pseudonym-1",
            "ground_truth_events": ground_truth or [],
            "predicted_events": predictions or [],
        }

    def run_file(self, rows, **kwargs):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sessions.jsonl"
            path.write_text(
                "\n".join(json.dumps(row) for row in rows) + "\n",
                encoding="utf-8",
            )
            sessions, digest, model_sha = load_sessions(path)
            report = evaluate_sessions(sessions, **kwargs)
            return report, digest, model_sha

    def event(self, event_id, class_id, start, end, confidence=None):
        item = {
            "event_id": event_id,
            "class_id": class_id,
            "start_seconds": start,
            "end_seconds": end,
        }
        if confidence is not None:
            item["confidence"] = confidence
        return item

    def test_perfect_event_match_and_camera_hour_accounting(self):
        ground_truth = [self.event("gt-1", 0, 10, 12)]
        predictions = [self.event("pred-1", 0, 10.2, 12.2, 0.95)]
        report, digest, model_sha = self.run_file([
            self.session(ground_truth=ground_truth, predictions=predictions)
        ])
        row = report["overall"]
        self.assertEqual((row["tp"], row["fp"], row["fn"]), (1, 0, 0))
        self.assertEqual(row["precision"], 1.0)
        self.assertEqual(row["recall"], 1.0)
        self.assertEqual(report["monitoring_camera_hours"], 1.0)
        self.assertEqual(row["false_alarms_per_camera_hour"], 0.0)
        self.assertEqual(report["model_sha256"], self.MODEL_SHA)
        self.assertEqual(len(digest), 64)
        self.assertEqual(model_sha, self.MODEL_SHA)

    def test_duplicate_track_event_counts_as_false_alarm(self):
        target = self.event("gt-1", 0, 10, 12)
        predictions = [
            self.event("pred-1", 0, 10, 12, 0.95),
            self.event("pred-2", 0, 10, 12, 0.90),
        ]
        report, _, _ = self.run_file([
            self.session(ground_truth=[target], predictions=predictions)
        ])
        self.assertEqual((report["overall"]["tp"], report["overall"]["fp"]), (1, 1))
        self.assertEqual(report["overall"]["false_alarms_per_camera_hour"], 1.0)

    def test_wrong_class_is_one_false_positive_and_one_false_negative(self):
        target = self.event("gt-1", 0, 10, 12)
        prediction = self.event("pred-1", 1, 10, 12, 0.95)
        report, _, _ = self.run_file([
            self.session(ground_truth=[target], predictions=[prediction])
        ])
        self.assertEqual(report["classes"]["0"]["fn"], 1)
        self.assertEqual(report["classes"]["1"]["fp"], 1)

    def test_confidence_and_temporal_iou_thresholds_are_applied(self):
        target = self.event("gt-1", 0, 10, 12)
        low_confidence = self.event("pred-1", 0, 10, 12, 0.2)
        report, _, _ = self.run_file([
            self.session(ground_truth=[target], predictions=[low_confidence])
        ], confidence_threshold=0.5)
        self.assertEqual(report["overall"]["fn"], 1)
        self.assertEqual(report["overall"]["predicted_events_at_threshold"], 0)

        poor_overlap = self.event("pred-2", 0, 11, 13, 0.9)
        report, _, _ = self.run_file([
            self.session(ground_truth=[target], predictions=[poor_overlap])
        ], temporal_iou_threshold=0.75)
        self.assertEqual(report["overall"]["fp"], 1)
        self.assertEqual(report["overall"]["fn"], 1)

    def test_false_alarm_rate_uses_sum_of_non_overlapping_camera_hours(self):
        first = self.session(
            session_id="s1",
            start="2026-11-20T10:00:00Z",
            duration=1800,
            predictions=[self.event("p1", 0, 10, 11, 0.9)],
        )
        second = self.session(
            session_id="s2",
            start="2026-11-20T10:30:00Z",
            duration=1800,
            predictions=[self.event("p2", 0, 20, 21, 0.9)],
        )
        report, _, _ = self.run_file([first, second])
        self.assertEqual(report["monitoring_camera_hours"], 1.0)
        self.assertEqual(report["overall"]["false_alarms_per_camera_hour"], 2.0)

    def test_overlapping_sessions_from_same_camera_are_rejected(self):
        first = self.session(session_id="s1", start="2026-11-20T10:00:00Z", duration=3600)
        second = self.session(session_id="s2", start="2026-11-20T10:30:00Z", duration=3600)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sessions.jsonl"
            path.write_text(json.dumps(first) + "\n" + json.dumps(second) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(EventEvaluationError, "overlapping monitoring sessions"):
                load_sessions(path)

    def test_rejects_mixed_model_hash_and_unreviewed_ground_truth(self):
        valid = self.session()
        changed_hash = self.session(session_id="s2", start="2026-11-20T11:00:00Z", model_sha="c" * 64)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sessions.jsonl"
            path.write_text(json.dumps(valid) + "\n" + json.dumps(changed_hash) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(EventEvaluationError, "exactly one model SHA-256"):
                load_sessions(path)

        unreviewed = self.session(review_status="automatic")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sessions.jsonl"
            path.write_text(json.dumps(unreviewed) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(EventEvaluationError, "human-reviewed"):
                load_sessions(path)

    def test_rejects_timezone_naive_sessions_and_invalid_event_intervals(self):
        invalid_time = self.session(start="2026-11-20T10:00:00")
        invalid_interval = self.session(
            ground_truth=[self.event("gt-1", 0, -1, 1)]
        )
        for row in (invalid_time, invalid_interval):
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "sessions.jsonl"
                path.write_text(json.dumps(row) + "\n", encoding="utf-8")
                with self.subTest(row=row), self.assertRaises(EventEvaluationError):
                    load_sessions(path)

    def test_undefined_class_metrics_are_null_not_zero(self):
        row = self.session()
        report, _, _ = self.run_file([row])
        self.assertEqual(report["classes"], {})
        self.assertIsNone(report["overall"]["precision"])
        self.assertIsNone(report["overall"]["recall"])


if __name__ == "__main__":
    unittest.main()
