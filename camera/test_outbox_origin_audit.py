import contextlib
import io
from contextlib import closing
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from camera.audit_outbox_origins import MAX_PAYLOAD_BYTES, OutboxAuditError, audit_database, main


def camera_event(event_id="event-001"):
    return {
        "id": event_id,
        "observed_at": "2026-11-28T12:00:00Z",
        "station_id": "station-test",
        "species": "vespa_velutina_candidate",
        "confidence": 0.8,
        "prey_detected": False,
        "origin": "camera",
    }


def make_database(path, rows):
    with closing(sqlite3.connect(path)) as db, db:
        db.execute(
            """CREATE TABLE outbox (
                event_id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (
                    strftime('%Y-%m-%dT%H:%M:%fZ','now')
                )
            )"""
        )
        db.executemany(
            "INSERT INTO outbox(event_id, payload_json) VALUES(?, ?)",
            rows,
        )


class OutboxOriginAuditTests(unittest.TestCase):
    def test_empty_outbox_is_reported_without_claiming_authentication(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.sqlite3"
            make_database(path, [])
            report = audit_database(path)
        self.assertEqual(report["assessment"], "EMPTY_OUTBOX")
        self.assertEqual(report["counts"]["total"], 0)
        self.assertIn("not proof", report["note"])

    def test_explicit_structurally_valid_camera_rows_are_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "camera.sqlite3"
            event = camera_event()
            make_database(path, [(event["id"], json.dumps(event))])
            report = audit_database(path)
        self.assertEqual(report["assessment"], "STRUCTURALLY_COMPATIBLE_NOT_AUTHENTICATED")
        self.assertEqual(report["counts"]["explicit_camera_valid"], 1)
        self.assertEqual(report["counts"]["legacy_missing_origin"], 0)

    def test_legacy_rows_without_origin_block_preflight(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legacy.sqlite3"
            event = camera_event("private-event-id")
            del event["origin"]
            make_database(path, [(event["id"], json.dumps(event))])
            report = audit_database(path)
        self.assertEqual(report["assessment"], "BLOCKED_REQUIRES_MANUAL_REVIEW")
        self.assertEqual(report["counts"]["legacy_missing_origin"], 1)
        self.assertEqual(report["counts"]["explicit_camera_valid"], 0)

    def test_non_camera_origins_are_not_reclassified(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manual.sqlite3"
            event = camera_event()
            event["origin"] = "manual_observation"
            make_database(path, [(event["id"], json.dumps(event))])
            report = audit_database(path)
        self.assertEqual(report["counts"]["non_camera_origin"], 1)
        self.assertEqual(report["assessment"], "BLOCKED_REQUIRES_MANUAL_REVIEW")

    def test_invalid_json_and_invalid_schema_are_counted_without_payload_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "invalid.sqlite3"
            event = camera_event("row-mismatch")
            event["id"] = "different-id"
            make_database(path, [
                ("bad-json", "{not-json"),
                ("row-mismatch", json.dumps(event)),
            ])
            report = audit_database(path)
        self.assertEqual(report["counts"]["invalid_json"], 1)
        self.assertEqual(report["counts"]["invalid_schema"], 1)
        self.assertEqual(report["assessment"], "BLOCKED_REQUIRES_MANUAL_REVIEW")

    def test_audit_does_not_change_database_bytes_or_create_sidecars(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "readonly.sqlite3"
            event = camera_event()
            make_database(path, [(event["id"], json.dumps(event))])
            before = path.read_bytes()
            report = audit_database(path)
            after = path.read_bytes()
            self.assertEqual(report["counts"]["total"], 1)
            self.assertEqual(before, after)
            self.assertFalse(Path(str(path) + "-wal").exists())
            self.assertFalse(Path(str(path) + "-journal").exists())

    def test_nonempty_wal_is_rejected_to_avoid_an_incomplete_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "wal.sqlite3"
            make_database(path, [])
            Path(str(path) + "-wal").write_bytes(b"not-a-clean-checkpoint")
            with self.assertRaisesRegex(OutboxAuditError, "non-empty WAL"):
                audit_database(path)

    def test_oversized_payload_is_counted_without_json_parsing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "oversized.sqlite3"
            make_database(path, [("large", " " * (MAX_PAYLOAD_BYTES + 1))])
            report = audit_database(path)
        self.assertEqual(report["counts"]["invalid_schema"], 1)
        self.assertEqual(report["assessment"], "BLOCKED_REQUIRES_MANUAL_REVIEW")

    def test_nonempty_rollback_journal_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "journal.sqlite3"
            make_database(path, [])
            Path(str(path) + "-journal").write_bytes(b"unfinished-transaction")
            with self.assertRaisesRegex(OutboxAuditError, "rollback journal"):
                audit_database(path)

    def test_missing_database_is_not_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing.sqlite3"
            with self.assertRaises(OutboxAuditError):
                audit_database(path)
            self.assertFalse(path.exists())

    def test_cli_emits_counts_only_and_returns_manual_review_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "private.sqlite3"
            event = camera_event("secret-event-id")
            event["station_id"] = "private-station-identifier"
            del event["origin"]
            make_database(path, [(event["id"], json.dumps(event))])
            output = io.StringIO()
            with patch("sys.argv", ["audit_outbox_origins", "--database", str(path)]):
                with contextlib.redirect_stdout(output):
                    result = main()
        rendered = output.getvalue()
        self.assertEqual(result, 2)
        self.assertIn('"legacy_missing_origin": 1', rendered)
        self.assertNotIn("secret-event-id", rendered)
        self.assertNotIn("private-station-identifier", rendered)
        self.assertNotIn(str(path), rendered)


    def test_symlink_database_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target.sqlite3"
            link = Path(tmp) / "linked.sqlite3"
            make_database(target, [])
            try:
                link.symlink_to(target)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"symlink creation unavailable on this runner: {exc}")
            with self.assertRaisesRegex(OutboxAuditError, "symbolic links or junctions"):
                audit_database(link)

    def test_symlinked_parent_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real_dir = root / "real"
            real_dir.mkdir()
            target = real_dir / "outbox.sqlite3"
            make_database(target, [])
            parent_link = root / "alias"
            try:
                parent_link.symlink_to(real_dir, target_is_directory=True)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"directory symlink creation unavailable on this runner: {exc}")
            with self.assertRaisesRegex(OutboxAuditError, "symbolic links or junctions"):
                audit_database(parent_link / target.name)

    def test_symlinked_wal_sidecar_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            database = root / "outbox.sqlite3"
            sidecar_target = root / "sidecar-target"
            make_database(database, [])
            sidecar_target.write_bytes(b"sidecar")
            wal = Path(str(database) + "-wal")
            try:
                wal.symlink_to(sidecar_target)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"sidecar symlink creation unavailable on this runner: {exc}")
            with self.assertRaisesRegex(OutboxAuditError, "WAL sidecar must not be a symbolic link or junction"):
                audit_database(database)


    def test_generated_column_cannot_hide_from_schema_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "generated.sqlite3"
            with closing(sqlite3.connect(path)) as db, db:
                db.execute(
                    """CREATE TABLE outbox (
                        event_id TEXT PRIMARY KEY,
                        payload_json TEXT NOT NULL,
                        created_at TEXT NOT NULL DEFAULT (
                            strftime('%Y-%m-%dT%H:%M:%fZ','now')
                        ),
                        hidden_extra TEXT GENERATED ALWAYS AS (payload_json) VIRTUAL
                    )"""
                )
                event = camera_event()
                db.execute(
                    "INSERT INTO outbox(event_id, payload_json) VALUES(?, ?)",
                    (event["id"], json.dumps(event)),
                )
            with self.assertRaisesRegex(OutboxAuditError, "unsupported schema"):
                audit_database(path)

    def test_virtual_table_named_outbox_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "virtual.sqlite3"
            with closing(sqlite3.connect(path)) as db, db:
                try:
                    db.execute("CREATE VIRTUAL TABLE outbox USING fts5(event_id, payload_json)")
                except sqlite3.OperationalError as exc:
                    self.skipTest(f"SQLite FTS5 is unavailable: {exc}")
                event = camera_event()
                db.execute(
                    "INSERT INTO outbox(event_id, payload_json) VALUES(?, ?)",
                    (event["id"], json.dumps(event)),
                )
            with self.assertRaisesRegex(
                OutboxAuditError, "ordinary three-column SQLite table"
            ):
                audit_database(path)


if __name__ == "__main__":
    unittest.main()
