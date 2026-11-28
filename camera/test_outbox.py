import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from camera.outbox import SQLiteOutbox, OutboxFull, OutboxError


def event(event_id, species="vespa_velutina_candidate"):
    return {"id": event_id, "observed_at": "2026-11-20T00:00:00Z", "station_id": "station-1", "species": species, "confidence": 0.8, "prey_detected": False, "origin": "camera"}


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

    def test_offline_restart_retry_and_acknowledgement(self):
        """Failed sends must remain queued across restart; only acknowledged IDs leave."""
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "private" / "outbox.sqlite3")
            offline = SQLiteOutbox(path, max_rows=3)
            offline.enqueue(event("offline-001"))
            offline.enqueue(event("offline-002"))
            self.assertEqual([x["id"] for x in offline.pending()], ["offline-001", "offline-002"])

            # A connection failure cannot acknowledge either pending event.
            del offline
            recovered = SQLiteOutbox(path, max_rows=3)
            self.assertEqual(recovered.count(), 2)
            self.assertFalse(recovered.enqueue(event("offline-001")))
            self.assertEqual(recovered.count(), 2)

            # After transport recovery, only the confirmed event is removed.
            self.assertTrue(recovered.acknowledge("offline-001"))
            restarted = SQLiteOutbox(path, max_rows=3)
            self.assertEqual([x["id"] for x in restarted.pending()], ["offline-002"])
            self.assertFalse(restarted.acknowledge("offline-001"))
            self.assertTrue(restarted.acknowledge("offline-002"))
            self.assertEqual(SQLiteOutbox(path).count(), 0)

    def test_full_queue_survives_restart_without_data_loss(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "private" / "outbox.sqlite3")
            box = SQLiteOutbox(path, max_rows=2)
            box.enqueue(event("oldest"))
            box.enqueue(event("second"))
            with self.assertRaises(OutboxFull):
                box.enqueue(event("overflow"))
            restarted = SQLiteOutbox(path, max_rows=2)
            self.assertEqual([x["id"] for x in restarted.pending()], ["oldest", "second"])
            self.assertFalse(restarted.enqueue(event("oldest")))
            collision = event("oldest")
            collision["confidence"] = 0.9
            with self.assertRaises(OutboxError):
                restarted.enqueue(collision)
            self.assertTrue(restarted.acknowledge("oldest"))
            self.assertTrue(SQLiteOutbox(path, max_rows=2).enqueue(event("overflow")))
            self.assertEqual([x["id"] for x in SQLiteOutbox(path, max_rows=2).pending()],
                             ["second", "overflow"])

    def test_migrates_legacy_camera_rows_to_explicit_origin(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "legacy.sqlite3")
            legacy = event("legacy-camera")
            del legacy["origin"]
            with sqlite3.connect(path) as db:
                db.execute("""CREATE TABLE outbox (
                    event_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                )""")
                db.execute(
                    "INSERT INTO outbox(event_id, payload_json) VALUES(?, ?)",
                    (legacy["id"], json.dumps(legacy, sort_keys=True, separators=(",", ":"))),
                )

            box = SQLiteOutbox(path)
            migrated = box.pending(10)
            self.assertEqual(len(migrated), 1)
            self.assertEqual(migrated[0]["origin"], "camera")

    def test_refuses_to_reclassify_manual_or_unknown_existing_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "unexpected.sqlite3")
            unexpected = event("unexpected")
            unexpected["origin"] = "manual_observation"
            with sqlite3.connect(path) as db:
                db.execute("""CREATE TABLE outbox (
                    event_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                )""")
                db.execute(
                    "INSERT INTO outbox(event_id, payload_json) VALUES(?, ?)",
                    (unexpected["id"], json.dumps(unexpected, sort_keys=True, separators=(",", ":"))),
                )

            with self.assertRaises(OutboxError):
                SQLiteOutbox(path)

    def test_requires_explicit_camera_origin(self):
        with tempfile.TemporaryDirectory() as tmp:
            box = SQLiteOutbox(str(Path(tmp) / "outbox.sqlite3"))
            for origin in ("manual_observation", "unknown", None):
                payload = event("invalid-" + str(origin))
                payload["origin"] = origin
                with self.subTest(origin=origin), self.assertRaises(ValueError):
                    box.enqueue(payload)
            missing = event("missing")
            del missing["origin"]
            with self.assertRaises(ValueError):
                box.enqueue(missing)

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
