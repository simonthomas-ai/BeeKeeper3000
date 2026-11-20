"""Bounded, persistent metadata-only SQLite outbox."""
from __future__ import annotations

import json
import os
import sqlite3
import stat
from pathlib import Path


class OutboxError(RuntimeError):
    pass


class OutboxFull(OutboxError):
    pass


class SQLiteOutbox:
    def __init__(self, path: str, *, max_rows: int = 10_000):
        if not isinstance(path, str) or not path.strip():
            raise ValueError("outbox database path is required")
        if type(max_rows) is not int or not 1 <= max_rows <= 1_000_000:
            raise ValueError("max_rows must be between 1 and 1000000")
        target = Path(path).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = str(target)
        self.max_rows = max_rows
        if os.name == "posix":
            details = target.parent.stat()
            if details.st_uid != os.getuid():
                raise PermissionError("outbox directory must belong to the service account")
            os.chmod(target.parent, 0o700)
        self._initialize()
        self._secure()

    def _secure(self):
        if os.name == "posix":
            for file in (self.path, self.path + "-wal", self.path + "-shm"):
                try:
                    os.chmod(file, 0o600)
                except FileNotFoundError:
                    pass

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.execute("PRAGMA busy_timeout=5000")
        db.execute("PRAGMA synchronous=FULL")
        db.execute("PRAGMA secure_delete=ON")
        return db

    def _initialize(self):
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS outbox (
                event_id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            )""")
        self._secure()

    def enqueue(self, event: dict) -> bool:
        if not isinstance(event, dict) or set(event) != {
            "id", "observed_at", "station_id", "species", "confidence", "prey_detected"
        }:
            raise ValueError("outbox accepts only the strict source event schema")
        canonical = json.dumps(event, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
        event_id = event.get("id")
        if not isinstance(event_id, str) or not event_id:
            raise ValueError("event id is required")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT payload_json FROM outbox WHERE event_id=?", (event_id,)).fetchone()
            if existing:
                if existing[0] != canonical:
                    raise OutboxError("event ID collision with different payload")
                return False
            count = int(db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0])
            if count >= self.max_rows:
                raise OutboxFull("outbox is full; pending events were not deleted")
            db.execute("INSERT INTO outbox(event_id,payload_json) VALUES(?,?)", (event_id, canonical))
        self._secure()
        return True

    def pending(self, limit: int = 100) -> list[dict]:
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("pending limit must be between 1 and 1000")
        with self._connect() as db:
            rows = db.execute("SELECT payload_json FROM outbox ORDER BY created_at,event_id LIMIT ?", (limit,)).fetchall()
        self._secure()
        try:
            return [json.loads(row[0]) for row in rows]
        except json.JSONDecodeError as exc:
            raise OutboxError("stored outbox row is corrupt") from exc

    def acknowledge(self, event_id: str) -> bool:
        if not isinstance(event_id, str) or not event_id:
            raise ValueError("event_id is required")
        with self._connect() as db:
            cursor = db.execute("DELETE FROM outbox WHERE event_id=?", (event_id,))
        self._secure()
        return cursor.rowcount == 1

    def count(self) -> int:
        with self._connect() as db:
            result = int(db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0])
        self._secure()
        return result
