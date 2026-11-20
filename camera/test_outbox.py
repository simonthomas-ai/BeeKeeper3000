import tempfile
import unittest
from pathlib import Path
from camera.outbox import SQLiteOutbox, OutboxFull, OutboxError


def event(event_id):
    return {"id": event_id, "observed_at": "2026-11-20T00:00:00Z", "station_id": "station-1", "species": "vespa_velutina_candidate", "confidence": 0.8, "prey_detected": False}


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


if __name__ == "__main__":
    unittest.main()
