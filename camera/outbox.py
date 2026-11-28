"""Bounded, persistent metadata-only SQLite outbox and detection cooldowns."""
from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path


class OutboxError(RuntimeError):
    pass


class OutboxFull(OutboxError):
    pass


_LEGACY_SOURCE_EVENT_KEYS = frozenset({
    "id", "observed_at", "station_id", "species", "confidence", "prey_detected"
})
_SOURCE_EVENT_KEYS = _LEGACY_SOURCE_EVENT_KEYS | {"origin"}
_EVENT_ID = re.compile(r"^[\x21-\x7e]{1,128}$")
_STATION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$")


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

    @contextmanager
    def _connection(self):
        """Commit/rollback the SQLite transaction and always close the handle.

        sqlite3.Connection as a context manager does not close the connection;
        explicit close is required for deterministic cleanup on Windows.
        """
        db = self._connect()
        try:
            with db:
                yield db
        finally:
            db.close()

    def _initialize(self):
        with self._connection() as db:
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
            # Older releases of scripts/import_local_media.py wrote untagged
            # local-media candidates to this same outbox. Their origin cannot be
            # reconstructed from the legacy schema. Never promote them to camera;
            # fail closed and let the transaction preserve the original row.
            db.execute("BEGIN IMMEDIATE")
            self._migrate_legacy_camera_events(db)
        self._secure()

    @staticmethod
    def _migrate_legacy_camera_events(db) -> None:
        rows = db.execute("SELECT event_id, payload_json FROM outbox ORDER BY event_id").fetchall()
        for event_id, payload_json in rows:
            try:
                event = json.loads(payload_json)
            except (TypeError, json.JSONDecodeError) as exc:
                raise OutboxError("existing outbox row contains invalid JSON") from exc
            if isinstance(event, dict) and set(event) == _LEGACY_SOURCE_EVENT_KEYS:
                raise OutboxError(
                    "legacy outbox row has no verifiable origin; manual review required"
                )
            try:
                normalized_id, canonical = SQLiteOutbox._canonical_event(event)
            except (TypeError, ValueError, OverflowError) as exc:
                raise OutboxError("existing outbox row has an unsupported event schema") from exc
            if normalized_id != event_id:
                raise OutboxError("existing outbox row ID does not match its payload")
            if canonical != payload_json:
                db.execute(
                    "UPDATE outbox SET payload_json=? WHERE event_id=?",
                    (canonical, event_id),
                )

    @staticmethod
    def _canonical_event(event: dict) -> tuple[str, str]:
        if not isinstance(event, dict) or set(event) != _SOURCE_EVENT_KEYS:
            raise ValueError("outbox accepts only the strict camera source event schema")
        if event.get("origin") != "camera":
            raise ValueError("camera outbox accepts only explicit origin=camera")

        event_id = event.get("id")
        if not isinstance(event_id, str) or not _EVENT_ID.fullmatch(event_id):
            raise ValueError("event id must be 1..128 printable ASCII characters")
        station_id = event.get("station_id")
        if not isinstance(station_id, str) or not _STATION_ID.fullmatch(station_id):
            raise ValueError("station_id must be a short technical identifier")

        observed_at = event.get("observed_at")
        if not isinstance(observed_at, str) or not 1 <= len(observed_at) <= 40:
            raise ValueError("observed_at must be an ISO-8601 timestamp")
        try:
            timestamp = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("observed_at must be a valid ISO-8601 timestamp") from exc
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("observed_at must include an explicit timezone")

        species = event.get("species")
        if not isinstance(species, str) or not 1 <= len(species.strip()) <= 160:
            raise ValueError("event species must contain 1..160 characters")
        if any(ord(char) < 32 or ord(char) == 127 for char in species):
            raise ValueError("event species contains control characters")

        confidence = event.get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise ValueError("confidence must be numeric")
        try:
            confidence_number = float(confidence)
        except (OverflowError, TypeError, ValueError) as exc:
            raise ValueError("confidence must be finite") from exc
        if not math.isfinite(confidence_number) or not 0 <= confidence_number <= 1:
            raise ValueError("confidence must be finite and within 0..1")
        if type(event.get("prey_detected")) is not bool:
            raise ValueError("prey_detected must be boolean")

        normalized = dict(event)
        normalized["species"] = species.strip()
        normalized["confidence"] = confidence_number
        canonical = json.dumps(
            normalized, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":")
        )
        return event_id, canonical

    def enqueue(self, event: dict) -> bool:
        """Insert an event without applying a detection cooldown."""
        event_id, canonical = self._canonical_event(event)
        with self._connection() as db:
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
        with self._connection() as db:
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
        with self._connection() as db:
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
        with self._connection() as db:
            cursor = db.execute("DELETE FROM outbox WHERE event_id=?", (event_id,))
        self._secure()
        return cursor.rowcount == 1

    def count(self) -> int:
        with self._connection() as db:
            result = int(db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0])
        self._secure()
        return result
