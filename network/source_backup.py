"""Consistent, non-overwriting SQLite backup/restore for the source journal."""
from __future__ import annotations
import argparse, os, sqlite3, tempfile
from pathlib import Path
from network.backup_permissions import assert_private_directory

_REQUIRED = {
    "source_events": {"sequence", "event_id", "payload_hash", "payload_json", "created_at"},
    "source_meta": {"key", "value"},
}

def _readonly_uri(path: Path) -> str:
    return path.as_uri() + "?mode=ro"

def _check_directory(path: Path) -> None:
    assert_private_directory(path)

def verify_database(path: str | os.PathLike) -> dict:
    """Verify SQLite integrity and the expected BeeKeeper source-journal schema."""
    database = Path(path).expanduser().resolve()
    if not database.is_file():
        raise FileNotFoundError(f"SQLite database not found: {database}")
    connection = sqlite3.connect(_readonly_uri(database), uri=True, timeout=5)
    try:
        result = connection.execute("PRAGMA quick_check").fetchone()
        if not result or result[0] != "ok":
            raise sqlite3.DatabaseError("SQLite quick_check failed")
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if not set(_REQUIRED).issubset(tables):
            raise sqlite3.DatabaseError("database is not a BeeKeeper source journal")
        for table, required in _REQUIRED.items():
            columns = {row[1] for row in connection.execute(
                f"PRAGMA table_info({table})").fetchall()}
            if not required.issubset(columns):
                raise sqlite3.DatabaseError(f"source journal table {table} has an incompatible schema")
        count = int(connection.execute("SELECT COUNT(*) FROM source_events").fetchone()[0])
        return {"valid": True, "events": count, "integrity": "ok"}
    finally:
        connection.close()

def _snapshot(source_path: str | os.PathLike, destination_path: str | os.PathLike) -> Path:
    source = Path(source_path).expanduser().resolve()
    raw_destination = Path(destination_path).expanduser()
    if raw_destination.is_symlink():
        raise ValueError("destination must not be a symbolic link")
    destination = raw_destination.resolve()
    if source == destination:
        raise ValueError("source and destination must be different files")
    if not source.is_file():
        raise FileNotFoundError(f"SQLite source not found: {source}")
    if destination.exists():
        raise FileExistsError(f"destination already exists; refusing to overwrite: {destination}")
    _check_directory(destination.parent)
    verify_database(source)
    fd, temp_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".partial",
                                     dir=destination.parent)
    os.close(fd)
    temporary = Path(temp_name)
    reserved = False
    try:
        if os.name == "posix":
            os.chmod(temporary, 0o600)
        source_db = sqlite3.connect(_readonly_uri(source), uri=True, timeout=5)
        destination_db = sqlite3.connect(str(temporary), timeout=5)
        try:
            source_db.backup(destination_db, pages=256, sleep=0.05)
            check = destination_db.execute("PRAGMA quick_check").fetchone()
            if not check or check[0] != "ok":
                raise sqlite3.DatabaseError("snapshot integrity check failed")
            destination_db.commit()
        finally:
            destination_db.close()
            source_db.close()
        verify_database(temporary)
        with temporary.open("rb+") as handle:
            handle.flush()
            os.fsync(handle.fileno())
        final_fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(final_fd)
        reserved = True
        os.replace(temporary, destination)
        if os.name == "posix":
            os.chmod(destination, 0o600)
            directory_fd = os.open(destination.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        return destination
    except Exception:
        if reserved:
            try:
                destination.unlink()
            except FileNotFoundError:
                pass
        raise
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass

def backup_database(source_path, backup_path) -> Path:
    """Create a consistent SQLite online backup without overwriting a prior file."""
    return _snapshot(source_path, backup_path)

def restore_database(backup_path, destination_path) -> Path:
    """Restore a verified snapshot to a new database file; never overwrite."""
    verify_database(backup_path)
    return _snapshot(backup_path, destination_path)

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Back up, verify or restore the BeeKeeper3000 source journal.")
    commands = parser.add_subparsers(dest="command", required=True)
    backup = commands.add_parser("backup")
    backup.add_argument("--source", required=True)
    backup.add_argument("--destination", required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--source", required=True)
    restore = commands.add_parser("restore")
    restore.add_argument("--backup", required=True)
    restore.add_argument("--destination", required=True)
    args = parser.parse_args(argv)
    if args.command == "backup":
        path = backup_database(args.source, args.destination)
    elif args.command == "verify":
        result = verify_database(args.source)
        print(f"Database verified: events={result['events']}, integrity=ok")
        return 0
    else:
        path = restore_database(args.backup, args.destination)
    result = verify_database(path)
    print(f"Operation complete: {path} (events={result['events']}, integrity=ok)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
