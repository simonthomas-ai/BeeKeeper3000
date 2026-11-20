# BeeKeeper3000 local station quick start (Windows 10/11)

This starts the three software services already implemented:

1. Beekeeper-Monitor local PWA + authenticated SQLite receiver.
2. BeeKeeper3000 authenticated SQLite source journal.
3. BeeKeeper3000 Node.js bridge with cursor pagination required.

It does not install drivers or start an original Hornet3000 C++ daemon, camera driver, AI detector, MeshCore radio or Freenet node. Those components are not yet connected in the published source tree.

## Requirements

- Windows 10/11, current user profile.
- Python 3.11 or newer.
- Node.js 20 or newer.
- Local clones of both repositories, preferably sibling directories named BeeKeeper3000 and Beekeeper-Monitor.
- PowerShell 5.1 or newer.

## Start

Open PowerShell in the BeeKeeper3000 checkout:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\Start-BeeKeeperStation.ps1 -MonitorRepo "C:\path\to\Beekeeper-Monitor"
```

The Monitor path may be omitted when Beekeeper-Monitor is a sibling directory beside BeeKeeper3000.

First start creates three independent random secrets and stores them as Windows DPAPI-protected SecureString values under:

`%LOCALAPPDATA%\BeeKeeper3000\station-secrets.clixml`

Only the current Windows user can decrypt them. Do not copy this file to another Windows account or machine. Keeping it is necessary: the signed source cursor key and bridge checkpoint must survive service restarts. Deleting or replacing the secrets while an existing checkpoint is active invalidates that checkpoint.

The launcher applies a restrictive user/SYSTEM ACL to the local state directory. SQLite databases, bridge state and service logs are kept under `%LOCALAPPDATA%\BeeKeeper3000\`. They are not application-encrypted; use BitLocker or an encrypted volume.

## Open and stop

Open the local PWA on the same PC:

`http://127.0.0.1:8765/`

The source API is loopback-only on port 8787. Do not publish either HTTP service to the public internet.

Stop processes started by this launcher:

```powershell
.\scripts\Stop-BeeKeeperStation.ps1
```

The stop script checks the recorded executable and command line before terminating a PID. It does not kill an unrelated process if a PID has been reused.

The launcher is a per-user process supervisor, not a Windows Service and not an automatic startup task. Re-run it after login to start the station again. Logs are retained locally; apply a rotation/retention policy before long-term unattended use.

## Create a verified local backup

With both services running, create a consistent snapshot of the BeeKeeper source
journal and Monitor event database, plus the bridge checkpoint:

```powershell
.\scripts\Backup-BeeKeeperStation.ps1 -MonitorRepo "C:\path\to\Beekeeper-Monitor"
```

The script writes a timestamped backup set under
`%LOCALAPPDATA%\BeeKeeper3000\backups\`, verifies both SQLite snapshots,
validates and copies the bridge checkpoint when present, and writes a SHA-256
manifest. It stages the set privately and publishes it only after all required
steps succeed. It refuses backup paths outside the protected station directory.
The DPAPI secret file is intentionally excluded; it is user/machine-bound and
must be protected and recovered separately. Backups contain sensitive station
metadata; use BitLocker and define a retention policy. See
[SOURCE-JOURNAL-BACKUP.md](SOURCE-JOURNAL-BACKUP.md) for standalone verification
and restore commands.

## Validation without starting services

```powershell
.\scripts\Start-BeeKeeperStation.ps1 -MonitorRepo "C:\path\to\Beekeeper-Monitor" -ValidateOnly
```

This checks repository files, Python and Node versions and creates no secrets or processes.

## Current end-to-end boundary

The source API, bridge and Monitor receiver are local software components. A trusted detector/producer still has to POST validated metadata to the source API. MeshCore's signed bearing receiver and local triangulation store are a separate module; bearing data is not automatically added to the Monitor event list. Real camera, radio, three-station field, restart/backlog and public network gateway acceptance tests remain required before operational deployment.
