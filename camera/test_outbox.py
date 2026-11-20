import tempfile
import unittest
from pathlib import Path
from camera.outbox import SQLiteOutbox, OutboxFull, OutboxError


def event(event_id, species="vespa_velutina_candidate"):
    return {"id": event_id, "observed_at": "2026-11-20T00:00:00Z", "station_id": "station-1", "species": species, "confidence": 0.8, "prey_detected": False}


class OutboxTests(unittest.TestCase):
    def test_persistence_dedupe_ack_and_capacity(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "private" / "outbox.sqlite3")
            box = SQLiteOutbox(path, max_rows=2)
            self.assertTrue(box.enqueue(event("a")))
            self.assertFalse(box.enqueue(event("a")))
            self.assertEqual(box.count(), 1)
            self.assertEqual(SQLiteOutbox(path, max_rows=2).pending(10)[0]["id"], "a")
            box.enqueue(event("b"))
            with self.assertRaises(OutboxFull):
                box.enqueue(event("c"))
            self.assertTrue(box.acknowledge("a"))
            self.assertFalse(box.acknowledge("a"))
            self.assertEqual(box.count(), 1)

    def test_rejects_payload_with_media_or_extra_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            box = SQLiteOutbox(str(Path(tmp) / "outbox.sqlite3"))
            payload = event("a")
            payload["image_path"] = "secret.jpg"
            with self.assertRaises(ValueError):
                box.enqueue(payload)

    def test_event_id_conflict_is_not_silently_deduplicated(self):
        with tempfile.TemporaryDirectory() as tmp:
            box = SQLiteOutbox(str(Path(tmp) / "outbox.sqlite3"))
            box.enqueue(event("same"))
            other = event("same")
            other["confidence"] = 0.9
            with self.assertRaises(OutboxError):
                box.enqueue(other)

    def test_detection_cooldown_survives_outbox_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "outbox.sqlite3")
            first = SQLiteOutbox(path)
            self.assertTrue(first.enqueue_if_due(
                event("first"), cooldown_seconds=30, now_epoch=1000
            ))
            restarted = SQLiteOutbox(path)
            self.assertFalse(restarted.enqueue_if_due(
                event("second"), cooldown_seconds=30, now_epoch=1029
            ))
            self.assertTrue(restarted.enqueue_if_due(
                event("third"), cooldown_seconds=30, now_epoch=1030
            ))
            self.assertEqual(restarted.count(), 2)

    def test_full_outbox_does_not_advance_cooldown(self):
        with tempfile.TemporaryDirectory() as tmp:
            box = SQLiteOutbox(str(Path(tmp) / "outbox.sqlite3"), max_rows=1)
            self.assertTrue(box.enqueue_if_due(
                event("first", "vespa_velutina_candidate"),
                cooldown_seconds=30, now_epoch=1000
            ))
            with self.assertRaises(OutboxFull):
                box.enqueue_if_due(
                    event("second", "vespa_crabro_candidate"),
                    cooldown_seconds=30, now_epoch=1010
                )
            box.acknowledge("first")
            self.assertTrue(box.enqueue_if_due(
                event("third", "vespa_crabro_candidate"),
                cooldown_seconds=30, now_epoch=1011
            ))

    def test_rejects_invalid_cooldown_and_clock(self):
        with tempfile.TemporaryDirectory() as tmp:
            box = SQLiteOutbox(str(Path(tmp) / "outbox.sqlite3"))
            for index, invalid in enumerate((-1, float("nan"), True, 86401)):
                with self.assertRaises(ValueError):
                    box.enqueue_if_due(event("bad-" + str(index)), cooldown_seconds=invalid)
            with self.assertRaises(ValueError):
                box.enqueue_if_due(event("bad-clock"), cooldown_seconds=30, now_epoch=float("inf"))


if __name__ == "__main__":
    unittest.main()
