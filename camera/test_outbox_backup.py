import tempfile
import unittest
from pathlib import Path
from camera.outbox import SQLiteOutbox
from camera.outbox_backup import backup, verify, restore, OutboxBackupError


class OutboxBackupTests(unittest.TestCase):
    def test_backup_verify_restore_to_new_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.sqlite3"
            box = SQLiteOutbox(str(source))
            event = {"id":"evt-1","observed_at":"2026-11-20T00:00:00Z","station_id":"station-1","species":"vespa_candidate","confidence":0.8,"prey_detected":False}
            box.enqueue(event)
            backup_path = backup(source, root / "backup.sqlite3")
            verify(backup_path)
            restored = restore(backup_path, root / "restore.sqlite3")
            self.assertEqual(SQLiteOutbox(str(restored)).pending(10), [event])
            with self.assertRaises(OutboxBackupError):
                restore(backup_path, restored)

    def test_refuses_wrong_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            wrong = Path(tmp) / "wrong.sqlite3"
            import sqlite3
            with sqlite3.connect(wrong) as db:
                db.execute("CREATE TABLE not_outbox(value TEXT)")
            with self.assertRaises(OutboxBackupError):
                verify(wrong)


if __name__ == "__main__":
    unittest.main()
