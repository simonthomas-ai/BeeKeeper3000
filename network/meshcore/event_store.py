"""Persistent local store for signed MeshCore station events.

Stores only verified metadata and receiver-local station coordinates. Never
stores radio credentials, media, source filenames or exact coordinates from
the wire envelope (which deliberately contains none).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import stat
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping

from network.triangulation import Bearing, Estimate, triangulate

_HEX32 = re.compile(r"^[0-9a-f]{32}$")
_HEX128 = re.compile(r"^[0-9a-f]{128}$")
_EVENT_TYPES = {"sighting", "bearing", "station_heartbeat", "expert_verification"}
_TAXA = {"unknown", "Vespa_velutina", "Vespa_crabro", "other"}
_VERIFICATION = {"unverified", "photo_reviewed", "expert_confirmed", "rejected"}


class MeshCoreStoreError(ValueError):
    """Invalid or conflicting event in the local radio event store."""


class SQLiteMeshCoreEventStore:
    """SQLite-backed idempotent sink compatible with MeshCoreEventReceiver."""

    def __init__(self, path: str, *, retention_days: int = 30, max_rows: int = 100_000):
        if not isinstance(path, str) or not path.strip():
            raise ValueError("A database path is required")
        if not 1 <= retention_days <= 3650:
            raise ValueError("retention_days must be between 1 and 3650")
        if type(max_rows) is not int or not 100 <= max_rows <= 2_000_000:
            raise ValueError("max_rows must be between 100 and 2000000")

        target = Path(path).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = str(target)
        self.retention_days = retention_days
        self.max_rows = max_rows

        if os.name == "posix":
            parent = target.parent.stat()
            if parent.st_uid != os.getuid():
                raise PermissionError("database directory must be owned by the service account")
            if stat.S_IMODE(parent.st_mode) & 0o077:
                raise PermissionError("database directory must be private (mode 0700)")

        self._initialize()
        self._secure_files()

    def _secure_files(self):
        if os.name != "posix":
            # Windows ACLs must be configured for the service account separately.
            return
        for candidate in (self.path, self.path + "-wal", self.path + "-shm"):
            try:
                os.chmod(candidate, 0o600)
            except FileNotFoundError:
                pass

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            self._secure_files()
            db.execute("PRAGMA busy_timeout=5000")
            db.execute("PRAGMA foreign_keys=ON")
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
                CREATE TABLE IF NOT EXISTS radio_events (
                    event_id TEXT PRIMARY KEY,
                    station_hash TEXT NOT NULL,
                    station_id TEXT,
                    event_type TEXT NOT NULL,
                    candidate_taxon TEXT NOT NULL,
                    verification_status TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    observed_at TEXT NOT NULL,
                    observed_epoch REAL NOT NULL,
                    expires_at TEXT NOT NULL,
                    signing_key_id TEXT NOT NULL,
                    signature TEXT NOT NULL,
                    bearing_deg REAL,
                    bearing_sigma_deg REAL,
                    station_latitude REAL,
                    station_longitude REAL,
                    received_at TEXT NOT NULL,
                    event_json TEXT NOT NULL
                )
            """)
            db.execute("CREATE INDEX IF NOT EXISTS idx_radio_received ON radio_events(received_at)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_radio_bearing_time ON radio_events(observed_epoch, event_type)")

    @staticmethod
    def _validate_event(event: Mapping) -> tuple[str, str, str, str, str, float, str, float, str, str, str]:
        if not isinstance(event, Mapping):
            raise MeshCoreStoreError("event must be a mapping")
        allowed = {
            "schema_version", "event_id", "station_id", "observed_at", "expires_at",
            "event_type", "candidate_taxon", "confidence", "verification_status",
            "signature_key_id", "signature", "bearing_deg", "bearing_sigma_deg",
        }
        if set(event) - allowed:
            raise MeshCoreStoreError("event contains fields outside the signed radio contract")
        required = allowed - {"bearing_deg", "bearing_sigma_deg"}
        if required - set(event):
            raise MeshCoreStoreError("event is missing required signed fields")
        if event["schema_version"] != 1:
            raise MeshCoreStoreError("unsupported event schema")
        event_id = event["event_id"]
        station_hash = event["station_id"]
        key_id = event["signature_key_id"]
        signature = event["signature"]
        if not isinstance(event_id, str) or not _HEX32.fullmatch(event_id):
            raise MeshCoreStoreError("invalid event identifier")
        if not isinstance(station_hash, str) or not _HEX32.fullmatch(station_hash):
            raise MeshCoreStoreError("invalid station hash")
        if not isinstance(key_id, str) or not _HEX32.fullmatch(key_id):
            raise MeshCoreStoreError("invalid signing-key fingerprint")
        if not isinstance(signature, str) or not _HEX128.fullmatch(signature):
            raise MeshCoreStoreError("invalid event signature")
        if event["event_type"] not in _EVENT_TYPES or event["candidate_taxon"] not in _TAXA:
            raise MeshCoreStoreError("unsupported event type or taxon")
        if event["verification_status"] not in _VERIFICATION:
            raise MeshCoreStoreError("unsupported verification status")
        confidence = event["confidence"]
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            raise MeshCoreStoreError("invalid confidence")

        def parse_time(value, field):
            if not isinstance(value, str) or len(value) > 40:
                raise MeshCoreStoreError(f"invalid {field}")
            try:
                stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as exc:
                raise MeshCoreStoreError(f"invalid {field}") from exc
            if stamp.tzinfo is None or stamp.utcoffset() is None:
                raise MeshCoreStoreError(f"{field} must include timezone")
            return stamp.astimezone(timezone.utc)

        observed = parse_time(event["observed_at"], "observed_at")
        expires = parse_time(event["expires_at"], "expires_at")
        if expires <= observed:
            raise MeshCoreStoreError("event expiry must follow observation time")
        return (
            event_id, station_hash, event["event_type"], event["candidate_taxon"],
            event["verification_status"], confidence_number,
            observed.isoformat(), observed.timestamp(),
            expires.isoformat(), key_id, signature,
        )

    def __call__(self, event: Mapping, bearing: Bearing | None = None) -> bool:
        validated = self._validate_event(event)
        (event_id, station_hash, event_type, taxon, verification, confidence,
         observed_at, observed_epoch, expires_at, key_id, signature) = validated

        if event_type == "bearing" and bearing is None:
            raise MeshCoreStoreError("bearing event requires receiver-local station coordinates")
        if event_type != "bearing" and bearing is not None:
            raise MeshCoreStoreError("only bearing events may carry receiver-local coordinates")

        station_id = latitude = longitude = azimuth = sigma = None
        if bearing is not None:
            if not isinstance(bearing.station_id, str) or not bearing.station_id or len(bearing.station_id) > 128:
                raise MeshCoreStoreError("invalid resolved station ID")
            for value, low, high, name in (
                (bearing.latitude, -90, 90, "latitude"),
                (bearing.longitude, -180, 180, "longitude"),
                (bearing.azimuth_deg, 0, 359.999999, "bearing"),
                (bearing.sigma_deg, 0.5, 45, "bearing uncertainty"),
            ):
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
                    raise MeshCoreStoreError(f"invalid local {name}")
            if bearing.observed_at != event["observed_at"]:
                raise MeshCoreStoreError("local bearing timestamp does not match signed event")
            station_id = bearing.station_id
            latitude = float(bearing.latitude)
            longitude = float(bearing.longitude)
            azimuth = float(bearing.azimuth_deg)
            sigma = float(bearing.sigma_deg)

        event_json = json.dumps(dict(event), sort_keys=True, separators=(",", ":"), allow_nan=False)
        received_at = datetime.now(timezone.utc).isoformat()
        record = (
            event_id, station_hash, station_id, event_type, taxon, verification, confidence,
            observed_at, observed_epoch, expires_at, key_id, signature,
            azimuth, sigma, latitude, longitude, received_at, event_json,
        )
        with self._db() as db:
            cursor = db.execute("""
                INSERT OR IGNORE INTO radio_events (
                    event_id, station_hash, station_id, event_type, candidate_taxon,
                    verification_status, confidence, observed_at, observed_epoch,
                    expires_at, signing_key_id, signature, bearing_deg,
                    bearing_sigma_deg, station_latitude, station_longitude,
                    received_at, event_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, record)
            if cursor.rowcount == 0:
                previous = db.execute(
                    """SELECT station_hash, station_id, event_type, candidate_taxon,
                              verification_status, confidence, observed_at, expires_at,
                              signing_key_id, signature, bearing_deg, bearing_sigma_deg,
                              station_latitude, station_longitude, event_json
                       FROM radio_events WHERE event_id = ?""",
                    (event_id,),
                ).fetchone()
                expected = (
                    station_hash, station_id, event_type, taxon, verification, confidence,
                    observed_at, expires_at, key_id, signature, azimuth, sigma,
                    latitude, longitude, event_json,
                )
                if previous != expected:
                    raise MeshCoreStoreError("event ID collision or station registry changed for an existing event")
            db.execute("DELETE FROM radio_events WHERE received_at < ?", (cutoff,))
            db.execute("""
                DELETE FROM radio_events WHERE event_id IN (
                    SELECT event_id FROM radio_events
                    ORDER BY received_at DESC LIMIT -1 OFFSET ?
                )
            """, (self.max_rows,))
            return cursor.rowcount == 1

    def list_events(self, limit: int = 100) -> list[dict]:
        if not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        with self._db() as db:
            rows = db.execute(
                """SELECT event_id, station_hash, station_id, event_type,
                          candidate_taxon, verification_status, confidence,
                          observed_at, expires_at, signing_key_id, bearing_deg,
                          bearing_sigma_deg, station_latitude, station_longitude
                   FROM radio_events ORDER BY received_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        keys = (
            "event_id", "station_hash", "station_id", "event_type", "candidate_taxon",
            "verification_status", "confidence", "observed_at", "expires_at",
            "signing_key_id", "bearing_deg", "bearing_sigma_deg",
            "station_latitude", "station_longitude",
        )
        return [dict(zip(keys, row)) for row in rows]

    def recent_bearings(self, *, window_seconds: int = 1800, now_epoch: float | None = None) -> list[Bearing]:
        if not 1 <= window_seconds <= 7 * 24 * 60 * 60:
            raise ValueError("window_seconds must be between 1 second and 7 days")
        now = datetime.now(timezone.utc).timestamp() if now_epoch is None else float(now_epoch)
        cutoff = now - window_seconds
        with self._db() as db:
            rows = db.execute(
                """SELECT station_id, station_latitude, station_longitude,
                          bearing_deg, bearing_sigma_deg, observed_at
                   FROM radio_events
                   WHERE event_type = 'bearing' AND observed_epoch >= ?
                   ORDER BY observed_epoch DESC""",
                (cutoff,),
            ).fetchall()
        latest_by_station = {}
        for station_id, lat, lon, azimuth, sigma, observed_at in rows:
            if station_id and station_id not in latest_by_station:
                latest_by_station[station_id] = Bearing(
                    station_id=station_id,
                    latitude=lat,
                    longitude=lon,
                    azimuth_deg=azimuth,
                    sigma_deg=sigma,
                    observed_at=observed_at.replace("+00:00", "Z"),
                )
        return list(latest_by_station.values())

    def triangulate_recent(self, *, window_seconds: int = 1800,
                           max_rms_error_m: float = 250.0) -> Estimate:
        bearings = self.recent_bearings(window_seconds=window_seconds)
        return triangulate(
            bearings,
            max_rms_error_m=max_rms_error_m,
            max_time_delta_sec=window_seconds,
        )

    def purge_expired(self) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=self.retention_days)).isoformat()
        with self._db() as db:
            cursor = db.execute("DELETE FROM radio_events WHERE received_at < ?", (cutoff,))
            return cursor.rowcount

    def count(self) -> int:
        with self._db() as db:
            return int(db.execute("SELECT COUNT(*) FROM radio_events").fetchone()[0])
