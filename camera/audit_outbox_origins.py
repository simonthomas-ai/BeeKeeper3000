"""Read-only, count-only preflight for legacy camera outbox databases.

Run this against a clean, stopped backup before upgrading to an origin-enforcing
station build. The tool never migrates, repairs, or writes to the database.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sqlite3
import stat
from datetime import datetime
from pathlib import Path


LEGACY_KEYS = frozenset({
    "id", "observed_at", "station_id", "species", "confidence", "prey_detected"
})
CURRENT_KEYS = LEGACY_KEYS | {"origin"}
EVENT_ID = re.compile(r"^[\x21-\x7e]{1,128}$")
STATION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$")
MAX_PAYLOAD_BYTES = 64 * 1024


class OutboxAuditError(RuntimeError):
    """A safe, non-sensitive diagnostic failure."""


def _is_link_or_junction(path: Path) -> bool:
    """Return whether a path component is a symlink or (where supported) junction."""
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        return bool(is_junction()) if callable(is_junction) else False
    except OSError as exc:
        raise OutboxAuditError("database path components could not be inspected") from exc


def _valid_camera_event(event: dict, row_id: object) -> bool:
    if set(event) != CURRENT_KEYS or event.get("origin") != "camera":
        return False

    event_id = event.get("id")
    if not isinstance(event_id, str) or not EVENT_ID.fullmatch(event_id):
        return False
    if event_id != row_id:
        return False

    station_id = event.get("station_id")
    if not isinstance(station_id, str) or not STATION_ID.fullmatch(station_id):
        return False

    observed_at = event.get("observed_at")
    if not isinstance(observed_at, str) or not 1 <= len(observed_at) <= 40:
        return False
    try:
        timestamp = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        return False

    species = event.get("species")
    if not isinstance(species, str) or not 1 <= len(species.strip()) <= 160:
        return False
    if any(ord(char) < 32 or ord(char) == 127 for char in species):
        return False

    confidence = event.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        return False
    try:
        confidence_number = float(confidence)
    except (OverflowError, TypeError, ValueError):
        return False
    if not math.isfinite(confidence_number) or not 0 <= confidence_number <= 1:
        return False
    return type(event.get("prey_detected")) is bool


def audit_database(database: str | Path) -> dict:
    """Inspect an already stopped/checkpointed SQLite copy without modifying it."""
    candidate = Path(database).expanduser()
    absolute_candidate = candidate if candidate.is_absolute() else Path.cwd() / candidate
    try:
        # Check every supplied path component before resolve(). Checking only the
        # final component misses a symlinked parent directory.
        for component in (absolute_candidate, *absolute_candidate.parents):
            if _is_link_or_junction(component):
                raise OutboxAuditError(
                    "database path must not traverse symbolic links or junctions"
                )
        target = absolute_candidate.resolve(strict=True)
        details = target.stat()
    except OSError as exc:
        raise OutboxAuditError("database does not exist or cannot be read") from exc
    if not stat.S_ISREG(details.st_mode):
        raise OutboxAuditError("database must be a regular file")

    # immutable=1 prevents SQLite from creating locks or sidecars. A non-empty
    # WAL means the supplied file is not a clean standalone backup; refuse to
    # produce a potentially incomplete report.
    try:
        for suffix, label in (("-wal", "WAL"), ("-journal", "rollback journal")):
            sidecar = Path(str(target) + suffix)
            if _is_link_or_junction(sidecar):
                raise OutboxAuditError(
                    f"{label} sidecar must not be a symbolic link or junction"
                )
            if sidecar.exists() and sidecar.stat().st_size > 0:
                raise OutboxAuditError(
                    f"non-empty {label} sidecar found; stop the station and create a consistent backup"
                )
    except OSError as exc:
        raise OutboxAuditError("database sidecar could not be inspected") from exc

    uri = target.as_uri() + "?mode=ro&immutable=1"
    try:
        db = sqlite3.connect(uri, uri=True, timeout=1)
    except sqlite3.Error as exc:
        raise OutboxAuditError("database could not be opened read-only") from exc

    counts = {
        "total": 0,
        "explicit_camera_valid": 0,
        "legacy_missing_origin": 0,
        "non_camera_origin": 0,
        "invalid_json": 0,
        "invalid_schema": 0,
    }
    cursor = None
    try:
        pragma_cursor = db.execute("PRAGMA query_only=ON")
        pragma_cursor.close()
        table_cursor = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='outbox'"
        )
        try:
            table = table_cursor.fetchone()
        finally:
            table_cursor.close()
        if table is None:
            raise OutboxAuditError("outbox table is missing")
        # PRAGMA table_info() hides generated/hidden columns and does not
        # distinguish an ordinary table from a virtual table. Require the exact
        # three-column SQLiteOutbox shape before trusting this file as an outbox.
        shape_cursor = db.execute("PRAGMA table_list('outbox')")
        try:
            shapes = shape_cursor.fetchall()
        finally:
            shape_cursor.close()
        if (
            len(shapes) != 1
            or shapes[0][2] != "table"
            or shapes[0][3] != 3
        ):
            raise OutboxAuditError(
                "outbox table has an unsupported schema; expected an ordinary three-column SQLite table"
            )

        columns_cursor = db.execute("PRAGMA table_xinfo(outbox)")
        try:
            columns = [
                (row[1], str(row[2]).upper(), row[3], row[5], row[6])
                for row in columns_cursor.fetchall()
            ]
        finally:
            columns_cursor.close()
        expected_columns = [
            ("event_id", "TEXT", 0, 1, 0),
            ("payload_json", "TEXT", 1, 0, 0),
            ("created_at", "TEXT", 1, 0, 0),
        ]
        if columns != expected_columns:
            raise OutboxAuditError("outbox table has an unsupported schema")

        cursor = db.execute(
            "SELECT event_id, length(CAST(payload_json AS BLOB)), "
            "substr(CAST(payload_json AS BLOB), 1, ?) FROM outbox ORDER BY event_id",
            (MAX_PAYLOAD_BYTES + 1,),
        )
        while True:
            batch = cursor.fetchmany(256)
            if not batch:
                break
            for row_id, payload_size, payload_json in batch:
                counts["total"] += 1
                if payload_size is None or payload_size > MAX_PAYLOAD_BYTES:
                    counts["invalid_schema"] += 1
                    continue
                try:
                    event = json.loads(payload_json)
                except (TypeError, ValueError, UnicodeDecodeError):
                    counts["invalid_json"] += 1
                    continue
                if not isinstance(event, dict):
                    counts["invalid_schema"] += 1
                    continue
                keys = set(event)
                if "origin" not in event:
                    if keys == LEGACY_KEYS:
                        counts["legacy_missing_origin"] += 1
                    else:
                        counts["invalid_schema"] += 1
                    continue
                if event.get("origin") != "camera":
                    counts["non_camera_origin"] += 1
                    continue
                if _valid_camera_event(event, row_id):
                    counts["explicit_camera_valid"] += 1
                else:
                    counts["invalid_schema"] += 1
    except sqlite3.Error as exc:
        raise OutboxAuditError("database could not be inspected read-only") from exc
    finally:
        if cursor is not None:
            cursor.close()
            cursor = None
        db.close()
        db = None

    blocked = sum(
        counts[key]
        for key in (
            "legacy_missing_origin",
            "non_camera_origin",
            "invalid_json",
            "invalid_schema",
        )
    )
    if blocked:
        assessment = "BLOCKED_REQUIRES_MANUAL_REVIEW"
    elif counts["total"] == 0:
        assessment = "EMPTY_OUTBOX"
    else:
        assessment = "STRUCTURALLY_COMPATIBLE_NOT_AUTHENTICATED"

    return {
        "schema_version": 1,
        "assessment": assessment,
        "counts": counts,
        "note": (
            "Read-only aggregate counts only. No IDs, station names, payloads, or paths are emitted. "
            "origin=camera is client-supplied metadata, not proof of a physical camera producer. "
            "This report does not authorize or perform migration."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only, count-only preflight for a stopped camera outbox backup."
    )
    parser.add_argument("--database", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = audit_database(args.database)
    except OutboxAuditError as exc:
        print(json.dumps({"schema_version": 1, "assessment": "ERROR", "error": str(exc)}))
        return 3

    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 2 if report["assessment"] == "BLOCKED_REQUIRES_MANUAL_REVIEW" else 0


if __name__ == "__main__":
    raise SystemExit(main())
