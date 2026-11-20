"""Tests for consistent and non-overwriting source journal backups."""
import sqlite3, tempfile, unittest
from pathlib import Path
from network.source_backup import backup_database, restore_database, verify_database
from network.source_event_store import SQLiteSourceEventStore

class SourceBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source.sqlite3"
        self.store = SQLiteSourceEventStore(str(self.source))
        self.store.append({
            "id": "backup-test-1", "observed_at": "2026-11-20T10:00:00Z",
            "station_id": "station_north", "species": "vespa_velutina",
            "confidence": 0.91, "prey_detected": False,
        })

    def tearDown(self):
        self.temp.cleanup()

    def test_backup_and_restore_preserve_events(self):
        backup = self.root / "backups" / "source-backup.sqlite3"
        backup.parent.mkdir(mode=0o700)
        backup_database(self.source, backup)
        self.assertEqual(verify_database(backup)["events"], 1)
        restored = self.root / "restored.sqlite3"
        restore_database(backup, restored)
        self.assertEqual(verify_database(restored)["events"], 1)
        with sqlite3.connect(restored) as db:
            row = db.execute("SELECT event_id FROM source_events WHERE event_id='backup-test-1'").fetchone()
        self.assertIsNotNone(row)

    def test_backup_restore_preserves_tombstone_against_deleted_event_replay(self):
        self.assertTrue(self.store.delete("backup-test-1"))
        backup = self.root / "backups" / "source-erasure-backup.sqlite3"
        backup.parent.mkdir(mode=0o700)
        backup_database(self.source, backup)
        restored = self.root / "restored-erasure.sqlite3"
        restore_database(backup, restored)
        reopened = SQLiteSourceEventStore(str(restored))
        self.assertEqual(reopened.count(), 0)
        with self.assertRaises(Exception):
            reopened.append({
                "id": "backup-test-1", "observed_at": "2026-11-20T10:00:00Z",
                "station_id": "station_north", "species": "vespa_velutina",
                "confidence": 0.91, "prey_detected": False,
            })

    def test_refuses_to_overwrite_existing_backup(self):
        destination = self.root / "existing.sqlite3"
        destination.write_bytes(b"keep-me")
        with self.assertRaises(FileExistsError):
            backup_database(self.source, destination)
        self.assertEqual(destination.read_bytes(), b"keep-me")

    def test_rejects_non_source_database(self):
        invalid = self.root / "not-source.sqlite3"
        with sqlite3.connect(invalid) as db:
            db.execute("CREATE TABLE unrelated (id INTEGER)")
        with self.assertRaises(sqlite3.DatabaseError):
            verify_database(invalid)

    def test_rejects_corrupt_snapshot(self):
        corrupt = self.root / "corrupt.sqlite3"
        corrupt.write_bytes(b"not a sqlite database")
        with self.assertRaises(sqlite3.DatabaseError):
            restore_database(corrupt, self.root / "restored.sqlite3")

if __name__ == "__main__":
    unittest.main()
