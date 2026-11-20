# BeeKeeper3000 source-journal backup and recovery

The source journal is operational data. Back it up while the service is running
using SQLite's online backup API; copying only the main database file is not a
supported backup method because SQLite may be using WAL sidecars.

## Create and verify a backup

Create a private destination directory first. On Linux/macOS:

~~~sh
install -d -m 700 "$HOME/.local/share/beekeeper3000/backups"
python -m network.source_backup backup --source "$HOME/.local/share/beekeeper3000/source-events.sqlite3" --destination "$HOME/.local/share/beekeeper3000/backups/source-$(date -u +%Y%m%dT%H%M%SZ).sqlite3"
~~~

On Windows PowerShell, use a directory under
%LOCALAPPDATA%\BeeKeeper3000\backups, protected by the same restrictive
current-user/SYSTEM NTFS ACL as the station data directory:

~~~powershell
$backupDir = Join-Path $env:LOCALAPPDATA "BeeKeeper3000\backups"
New-Item -ItemType Directory -Force $backupDir | Out-Null
$stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$source = Join-Path $env:LOCALAPPDATA "BeeKeeper3000\data\source-events.sqlite3"
$destination = Join-Path $backupDir "source-$stamp.sqlite3"
python -m network.source_backup backup --source $source --destination $destination
~~~

The command verifies SQLite integrity and the expected source-journal schema
before and after the snapshot. It uses a temporary file and atomically reserves
the destination without overwriting an existing file. On POSIX, the backup
directory must be owned by the service account and have mode 0700; the database
file is restricted to mode 0600. On Windows, use the station installer's NTFS
ACL and BitLocker or another encrypted volume.

## Verify and restore

~~~sh
python -m network.source_backup verify --source /path/to/source-backup.sqlite3
python -m network.source_backup restore --backup /path/to/source-backup.sqlite3 --destination /path/to/new-source-events.sqlite3
~~~

Restore always creates a new database and refuses to overwrite an existing
file. Stop the station before manually replacing its active database, preserve
the original separately, and verify the restored file before restarting.

This backup covers only the BeeKeeper source journal. Back up the Monitor
database and bridge checkpoint separately. The DPAPI-protected Windows station
secret file is machine/user-bound and must be handled as a separate recovery
artifact; copying it to another Windows account or host does not make it
portable. Backups contain sensitive station metadata and require a defined
retention, access-control and encryption policy.
