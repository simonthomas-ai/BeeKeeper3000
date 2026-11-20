"""Bounded, persistent metadata-only SQLite outbox and detection cooldowns."""
from __future__ import annotations

import json
import math
import os
import sqlite3
import time
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
            db.execute("""CREATE TABLE IF NOT EXISTS detection_cooldowns (
                species TEXT NOT NULL,
                prey_detected INTEGER NOT NULL CHECK (prey_detected IN (0, 1)),
                last_emitted_epoch REAL NOT NULL,
                PRIMARY KEY (species, prey_detected)
            )""")
        self._secure()

    @staticmethod
    def _canonical_event(event: dict) -> tuple[str, str]:
        if not isinstance(event, dict) or set(event) != {
            "id", "observed_at", "station_id", "species", "confidence", "prey_detected"
        }:
            raise ValueError("outbox accepts only the strict source event schema")
        canonical = json.dumps(
            event, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":")
        )
        event_id = event.get("id")
        if not isinstance(event_id, str) or not event_id:
            raise ValueError("event id is required")
        species = event.get("species")
        if not isinstance(species, str) or not species.strip() or len(species) > 160:
            raise ValueError("event species must be a non-empty label of at most 160 characters")
        if type(event.get("prey_detected")) is not bool:
            raise ValueError("prey_detected must be boolean")
        return event_id, canonical

    def enqueue(self, event: dict) -> bool:
        """Insert an event without applying a detection cooldown."""
        event_id, canonical = self._canonical_event(event)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT payload_json FROM outbox WHERE event_id=?", (event_id,)
            ).fetchone()
            if existing:
                if existing[0] != canonical:
                    raise OutboxError("event ID collision with different payload")
                return False
            count = int(db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0])
            if count >= self.max_rows:
                raise OutboxFull("outbox is full; pending events were not deleted")
            db.execute(
                "INSERT INTO outbox(event_id,payload_json) VALUES(?,?)",
                (event_id, canonical),
            )
        self._secure()
        return True

    def enqueue_if_due(
        self,
        event: dict,
        *,
        cooldown_seconds: float,
        now_epoch: float | None = None,
    ) -> bool:
        """Atomically apply a persistent species cooldown and enqueue an event."""
        event_id, canonical = self._canonical_event(event)
        if (
            isinstance(cooldown_seconds, bool)
            or not isinstance(cooldown_seconds, (int, float))
            or not math.isfinite(float(cooldown_seconds))
            or not 0 <= float(cooldown_seconds) <= 86_400
        ):
            raise ValueError("cooldown_seconds must be finite and between 0 and 86400")
        current = time.time() if now_epoch is None else now_epoch
        if (
            isinstance(current, bool)
            or not isinstance(current, (int, float))
            or not math.isfinite(float(current))
            or current < 0
        ):
            raise ValueError("now_epoch must be a finite non-negative timestamp")

        species = event["species"].strip()
        prey = int(event["prey_detected"])
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            last = db.execute(
                "SELECT last_emitted_epoch FROM detection_cooldowns "
                "WHERE species=? AND prey_detected=?",
                (species, prey),
            ).fetchone()
            # A backwards clock adjustment deliberately keeps the cooldown active.
            if last is not None and float(current) - float(last[0]) < float(cooldown_seconds):
                return False

            existing = db.execute(
                "SELECT payload_json FROM outbox WHERE event_id=?", (event_id,)
            ).fetchone()
            if existing:
                if existing[0] != canonical:
                    raise OutboxError("event ID collision with different payload")
                return False

            count = int(db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0])
            if count >= self.max_rows:
                raise OutboxFull("outbox is full; pending events were not deleted")

            db.execute(
                "INSERT INTO outbox(event_id,payload_json) VALUES(?,?)",
                (event_id, canonical),
            )
            db.execute(
                """INSERT INTO detection_cooldowns
                   (species,prey_detected,last_emitted_epoch) VALUES(?,?,?)
                   ON CONFLICT(species,prey_detected) DO UPDATE
                   SET last_emitted_epoch=excluded.last_emitted_epoch""",
                (species, prey, float(current)),
            )
        self._secure()
        return True

    def pending(self, limit: int = 100) -> list[dict]:
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("pending limit must be between 1 and 1000")
        with self._connect() as db:
            rows = db.execute(
                "SELECT payload_json FROM outbox ORDER BY created_at,event_id LIMIT ?",
                (limit,),
            ).fetchall()
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
