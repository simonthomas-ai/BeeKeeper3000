"""Safe SQLite backup/verify/restore helpers for the local camera outbox."""
from __future__ import annotations

import argparse
import os
import sqlite3
from contextlib import closing
from pathlib import Path

from network.backup_permissions import assert_private_directory


class OutboxBackupError(RuntimeError):
    pass


def _validate(path: str | Path) -> None:
    source = Path(path).expanduser().resolve(strict=True)
    if not source.is_file():
        raise OutboxBackupError("outbox database is not a regular file")
    try:
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=5)) as db:
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


def _new_destination(path: str | Path) -> Path:
    raw = Path(path).expanduser()
    if raw.is_symlink():
        raise OutboxBackupError("backup destination must not be a symbolic link")
    return raw.resolve()


def _copy_to_new_database(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    assert_private_directory(destination.parent)
    reserved = False
    try:
        descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        reserved = True
        with closing(sqlite3.connect(source, timeout=5)) as source_db, closing(
            sqlite3.connect(destination, timeout=5)
        ) as target_db:
            source_db.backup(target_db)
        if os.name == "posix":
            os.chmod(destination, 0o600)
        _validate(destination)
        return destination
    except FileExistsError as exc:
        raise OutboxBackupError("backup destination must be a new file") from exc
    except Exception:
        if reserved:
            try:
                destination.unlink(missing_ok=True)
            except OSError:
                pass
        raise


def backup(source: str | Path, destination: str | Path) -> Path:
    src = Path(source).expanduser().resolve(strict=True)
    dst = _new_destination(destination)
    if src == dst or dst.exists():
        raise OutboxBackupError("backup destination must be a new file")
    _validate(src)
    return _copy_to_new_database(src, dst)


def restore(source: str | Path, destination: str | Path) -> Path:
    src = Path(source).expanduser().resolve(strict=True)
    dst = _new_destination(destination)
    if src == dst or dst.exists():
        raise OutboxBackupError("restore destination must be a new file")
    _validate(src)
    return _copy_to_new_database(src, dst)


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
