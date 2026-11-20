"""Durable, bounded and idempotent SQLite source journal with cursor pagination."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping

from .source_cursors import CursorExpired, CursorError
from .source_events import SourceEventError, validate_source_event


class SourceStoreError(RuntimeError):
    """Persistence failure in the source event journal."""


class SourceConflictError(SourceStoreError):
    """A stable source event ID was reused with different content."""


class SourceCapacityError(SourceStoreError):
    """The bounded source journal is full; no unforwarded event was evicted."""


class SourceDeletedError(SourceStoreError):
    """A source event ID was previously erased and cannot be replayed."""


class SQLiteSourceEventStore:
    """Append-only source journal. Never evicts unforwarded events to make space."""

    def __init__(self, path: str, *, retention_days: int = 30, max_rows: int = 250_000):
        if not isinstance(path, str) or not path.strip():
            raise ValueError("database path is required")
        if type(retention_days) is not int or not 1 <= retention_days <= 3650:
            raise ValueError("retention_days must be between 1 and 3650")
        if type(max_rows) is not int or not 100 <= max_rows <= 5_000_000:
            raise ValueError("max_rows must be between 100 and 5000000")
        target = Path(path).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = str(target)
        self.retention_days = retention_days
        self.max_rows = max_rows
        self._secure_files(check_directory=True)
        self._initialize()
        self._secure_files()

    def _secure_files(self, check_directory=False):
        if os.name != "posix":
            # Windows service installations must configure NTFS ACLs explicitly.
            return
        parent = Path(self.path).parent
        if check_directory:
            details = parent.stat()
            if details.st_uid != os.getuid():
                raise PermissionError("source database directory must belong to the service account")
            if stat.S_IMODE(details.st_mode) & 0o077:
                raise PermissionError("source database directory must be private (mode 0700)")
        for name in (self.path, self.path + "-wal", self.path + "-shm"):
            try:
                os.chmod(name, 0o600)
            except FileNotFoundError:
                pass

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            self._secure_files()
            db.execute("PRAGMA busy_timeout=5000")
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("PRAGMA secure_delete=ON")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
            self._secure_files()

    def _initialize(self):
        with self._db() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""
                CREATE TABLE IF NOT EXISTS source_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    payload_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            db.execute("CREATE INDEX IF NOT EXISTS idx_source_created ON source_events(created_at)")
            db.execute("""
                CREATE TABLE IF NOT EXISTS source_tombstones (
                    event_id TEXT PRIMARY KEY,
                    sequence INTEGER NOT NULL,
                    deleted_at TEXT NOT NULL
                )
            """)
            db.execute("CREATE INDEX IF NOT EXISTS idx_source_tombstones_deleted ON source_tombstones(deleted_at)")
            db.execute("""
                CREATE TABLE IF NOT EXISTS source_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            max_sequence = int(db.execute(
                "SELECT COALESCE(MAX(sequence), 0) FROM source_events"
            ).fetchone()[0])
            earliest = db.execute(
                "SELECT MIN(sequence) FROM ("
                "SELECT sequence FROM source_events UNION ALL "
                "SELECT sequence FROM source_tombstones)"
            ).fetchone()[0]
            sqlite_sequence = db.execute(
                "SELECT seq FROM sqlite_sequence WHERE name='source_events'"
            ).fetchone()
            allocated_sequence = int(sqlite_sequence[0]) if sqlite_sequence else 0
            db.execute(
                "INSERT OR IGNORE INTO source_meta(key, value) VALUES('last_sequence', ?)",
                (str(max_sequence),),
            )
            db.execute(
                "INSERT OR IGNORE INTO source_meta(key, value) VALUES('earliest_sequence', ?)",
                (str(earliest if earliest is not None else max_sequence + 1),),
            )
            # Reconcile metadata without resetting AUTOINCREMENT after all
            # retained rows have expired. Cursors from an older process must
            # never become valid again because a retention purge emptied the table.
            prior_last = int(db.execute(
                "SELECT CAST(value AS INTEGER) FROM source_meta WHERE key='last_sequence'"
            ).fetchone()[0])
            last_sequence = max(max_sequence, allocated_sequence, prior_last)
            db.execute(
                "UPDATE source_meta SET value=? WHERE key='last_sequence'",
                (str(last_sequence),),
            )
            retained_earliest = earliest if earliest is not None else last_sequence + 1
            db.execute(
                "UPDATE source_meta SET value=? WHERE key='earliest_sequence'",
                (str(retained_earliest),),
            )

    def append(self, value: Mapping) -> tuple[dict, bool]:
        try:
            event = validate_source_event(value)
        except SourceEventError:
            raise
        canonical = json.dumps(
            event, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        created = datetime.now(timezone.utc).isoformat()
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            tombstone = db.execute(
                "SELECT 1 FROM source_tombstones WHERE event_id=?",
                (event["id"],),
            ).fetchone()
            if tombstone is not None:
                raise SourceDeletedError("source event ID was previously deleted and cannot be replayed")
            existing = db.execute(
                "SELECT payload_hash, sequence, payload_json FROM source_events WHERE event_id=?",
                (event["id"],),
            ).fetchone()
            if existing is not None:
                if existing[0] != digest or existing[2] != canonical:
                    raise SourceConflictError("source event ID was reused with different content")
                return {"sequence": existing[1], "event": event}, False

            cutoff = (datetime.now(timezone.utc) - timedelta(days=self.retention_days)).isoformat()
            db.execute("DELETE FROM source_events WHERE created_at < ?", (cutoff,))
            db.execute("DELETE FROM source_tombstones WHERE deleted_at < ?", (cutoff,))
            earliest_retained = db.execute(
                "SELECT MIN(sequence) FROM ("
                "SELECT sequence FROM source_events UNION ALL "
                "SELECT sequence FROM source_tombstones)"
            ).fetchone()[0]
            previous_last = int(db.execute(
                "SELECT CAST(value AS INTEGER) FROM source_meta WHERE key='last_sequence'"
            ).fetchone()[0])
            db.execute(
                "UPDATE source_meta SET value=? WHERE key='earliest_sequence'",
                (str(earliest_retained if earliest_retained is not None else previous_last + 1),),
            )
            count = int(db.execute("SELECT COUNT(*) FROM source_events").fetchone()[0])
            if count >= self.max_rows:
                raise SourceCapacityError(
                    "source journal is at capacity; unforwarded records are never evicted"
                )
            cursor = db.execute(
                "INSERT INTO source_events(event_id, payload_hash, payload_json, created_at) "
                "VALUES(?, ?, ?, ?)",
                (event["id"], digest, canonical, created),
            )
            sequence = int(cursor.lastrowid)
            db.execute(
                "UPDATE source_meta SET value=? WHERE key='last_sequence'",
                (str(sequence),),
            )
            db.execute(
                "UPDATE source_meta SET value=? WHERE key='earliest_sequence' "
                "AND CAST(value AS INTEGER) > ?",
                (str(sequence), sequence),
            )
            return {"sequence": sequence, "event": event}, True

    def start_sequence(self) -> int:
        """Return the position immediately before the earliest retained event.

        A new consumer cannot recover data that has already expired. Starting
        at the retention boundary is distinct from replaying an old signed
        cursor, which must return CursorExpired instead of silently skipping.
        """
        self.purge_expired()
        with self._db() as db:
            earliest = int(db.execute(
                "SELECT CAST(value AS INTEGER) FROM source_meta WHERE key='earliest_sequence'"
            ).fetchone()[0])
            return max(0, earliest - 1)

    def page(self, after_sequence: int, limit: int) -> dict:
        if type(after_sequence) is not int or after_sequence < 0:
            raise CursorError("cursor sequence must be a non-negative integer")
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        # Enforce the declared retention window on reads as well as writes.
        # The earliest_sequence watermark is updated before the page snapshot,
        # so an offline consumer receives an explicit 410 instead of stale data.
        self.purge_expired()
        with self._db() as db:
            db.execute("BEGIN")
            last_sequence = int(db.execute(
                "SELECT CAST(value AS INTEGER) FROM source_meta WHERE key='last_sequence'"
            ).fetchone()[0])
            earliest_sequence = int(db.execute(
                "SELECT CAST(value AS INTEGER) FROM source_meta WHERE key='earliest_sequence'"
            ).fetchone()[0])
            if after_sequence > last_sequence:
                raise CursorError("cursor is ahead of the source journal")
            if after_sequence < earliest_sequence - 1:
                raise CursorExpired(earliest_sequence)
            rows = db.execute(
                "SELECT sequence, payload_json FROM source_events "
                "WHERE sequence > ? ORDER BY sequence ASC LIMIT ?",
                (after_sequence, limit + 1),
            ).fetchall()
        has_more = len(rows) > limit
        selected = rows[:limit]
        events = [json.loads(row[1]) for row in selected]
        next_sequence = int(selected[-1][0]) if selected else after_sequence
        return {
            "events": events,
            "next_sequence": next_sequence,
            "has_more": has_more,
        }

    def purge_expired(self, *, now=None) -> int:
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise ValueError("now must include timezone")
        cutoff = (now.astimezone(timezone.utc) - timedelta(days=self.retention_days)).isoformat()
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            deleted = db.execute(
                "DELETE FROM source_events WHERE created_at < ?", (cutoff,)
            ).rowcount
            # Tombstones prevent delayed retries from resurrecting erased event IDs.
            # They share the configured retention horizon to keep the ledger bounded.
            db.execute("DELETE FROM source_tombstones WHERE deleted_at < ?", (cutoff,))
            earliest = db.execute(
                "SELECT MIN(sequence) FROM ("
                "SELECT sequence FROM source_events UNION ALL "
                "SELECT sequence FROM source_tombstones)"
            ).fetchone()[0]
            last = int(db.execute(
                "SELECT CAST(value AS INTEGER) FROM source_meta WHERE key='last_sequence'"
            ).fetchone()[0])
            db.execute(
                "UPDATE source_meta SET value=? WHERE key='earliest_sequence'",
                (str(earliest if earliest is not None else last + 1),),
            )
            return deleted

    def delete(self, event_id: str) -> bool:
        """Erase one event and retain a bounded tombstone against delayed replay.

        The sequence watermark is deliberately not moved for explicit deletion:
        cursor consumers can continue past the intentional hole. Retention expiry
        still advances the earliest-sequence watermark and raises 410 for stale
        cursors. A downstream Monitor copy or backup is not erased by this method.
        """
        if (
            not isinstance(event_id, str)
            or not 1 <= len(event_id) <= 128
            or any(ord(char) < 33 or ord(char) > 126 for char in event_id)
        ):
            raise ValueError("event_id must be 1..128 printable ASCII characters")
        now = datetime.now(timezone.utc).isoformat()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=self.retention_days)).isoformat()
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM source_tombstones WHERE deleted_at < ?", (cutoff,))
            existing = db.execute(
                "SELECT sequence FROM source_events WHERE event_id=?", (event_id,)
            ).fetchone()
            if existing is None:
                return False
            tombstones = int(db.execute("SELECT COUNT(*) FROM source_tombstones").fetchone()[0])
            if tombstones >= self.max_rows * 2:
                raise SourceCapacityError(
                    "source deletion ledger is at capacity; event was not deleted"
                )
            db.execute(
                "INSERT INTO source_tombstones(event_id, sequence, deleted_at) VALUES(?, ?, ?)",
                (event_id, int(existing[0]), now),
            )
            deleted = db.execute(
                "DELETE FROM source_events WHERE event_id=?", (event_id,)
            ).rowcount
            return deleted == 1

    def count(self) -> int:
        with self._db() as db:
            return int(db.execute("SELECT COUNT(*) FROM source_events").fetchone()[0])
