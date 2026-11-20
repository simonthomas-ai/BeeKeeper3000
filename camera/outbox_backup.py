"""Safe SQLite backup/verify/restore helpers for the local camera outbox."""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


class OutboxBackupError(RuntimeError):
    pass


def _validate(path: str | Path) -> None:
    source = Path(path).expanduser().resolve(strict=True)
    if not source.is_file():
        raise OutboxBackupError("outbox database is not a regular file")
    try:
        with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=5) as db:
            result = db.execute("PRAGMA integrity_check").fetchone()
            if result != ("ok",):
                raise OutboxBackupError("SQLite integrity check failed")
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "outbox" not in tables:
                raise OutboxBackupError("camera outbox table is missing")
            columns = {row[1] for row in db.execute("PRAGMA table_info(outbox)")}
            if not {"event_id", "payload_json", "created_at"}.issubset(columns):
                raise OutboxBackupError("camera outbox schema is incomplete")
    except sqlite3.Error as exc:
        raise OutboxBackupError("cannot verify camera outbox database") from exc


def verify(source: str | Path) -> None:
    _validate(source)


def backup(source: str | Path, destination: str | Path) -> Path:
    src = Path(source).expanduser().resolve(strict=True)
    dst = Path(destination).expanduser().resolve()
    if src == dst or dst.exists():
        raise OutboxBackupError("backup destination must be a new file")
    _validate(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sqlite3.connect(src, timeout=5) as source_db, sqlite3.connect(dst) as target_db:
            source_db.backup(target_db)
        _validate(dst)
        return dst
    except Exception:
        try:
            dst.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def restore(source: str | Path, destination: str | Path) -> Path:
    verify(source)
    src = Path(source).expanduser().resolve(strict=True)
    dst = Path(destination).expanduser().resolve()
    if src == dst or dst.exists():
        raise OutboxBackupError("restore destination must be a new file")
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sqlite3.connect(src, timeout=5) as source_db, sqlite3.connect(dst) as target_db:
            source_db.backup(target_db)
        _validate(dst)
        return dst
    except Exception:
        try:
            dst.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify and copy a BeeKeeper camera outbox database")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("backup", "verify", "restore"):
        cmd = sub.add_parser(name)
        if name == "restore":
            cmd.add_argument("--backup", required=True)
            cmd.add_argument("--destination", required=True)
        else:
            cmd.add_argument("--source", required=True)
            if name == "backup":
                cmd.add_argument("--destination", required=True)
    args = parser.parse_args()
    if args.command == "backup":
        print(backup(args.source, args.destination))
    elif args.command == "verify":
        verify(args.source)
        print("Camera outbox backup integrity and schema verified.")
    else:
        print(restore(args.backup, args.destination))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
