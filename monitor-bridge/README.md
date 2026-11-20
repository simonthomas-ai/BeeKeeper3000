# Hornet3000 → Beekeeper-Monitor bridge

This local Node.js adapter polls Hornet3000 `GET /api/events?limit=100` and forwards **validated metadata only** to the Monitor receiver `POST /api/v1/events`. Images, audio, GPS coordinates, camera credentials and source API keys are never copied into the event payload. Species labels are prefixed `unverified_candidate:`; model confidence is not proof of species identity.

## Requirements

- Node.js 20+; no third-party npm runtime dependencies.
- Hornet3000's authenticated local API running and returning `{ "events": [...] }`.
- Beekeeper-Monitor checkout with Python 3.12+ and its SQLite receiver.
- A unique random receiver token (at least 24 characters). Do not reuse the Hornet3000 API key.

## Local setup

PowerShell, in the Beekeeper-Monitor checkout:

```powershell
$bytes = New-Object byte[] 32
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($bytes)
$rng.Dispose()
$env:VESPAGUARD_INGEST_TOKEN = [Convert]::ToBase64String($bytes)
$env:VESPAGUARD_INGEST_DB = "$env:LOCALAPPDATA\BeeKeeper-Monitor\events.sqlite3"
python -m integrations.local_ingest
```

Open `http://127.0.0.1:8765/` to access the local PWA and its authenticated station-event panel. Keep this listener on loopback; never expose plain HTTP to the internet.

In a second PowerShell window, from `BeeKeeper3000\monitor-bridge`:

```powershell
$env:HORNET3000_URL = "http://127.0.0.1:8787"
$env:HORNET3000_API_KEY = "YOUR_HORNET3000_API_KEY"
$env:BEEKEEPER_MONITOR_INGEST_URL = "http://127.0.0.1:8765/api/v1/events"
$env:BEEKEEPER_MONITOR_INGEST_TOKEN = "PASTE_THE_RECEIVER_TOKEN"
$env:BRIDGE_STATE_FILE = "$env:LOCALAPPDATA\BeeKeeper-Monitor\bridge-state.json"
$env:POLL_INTERVAL_MS = "10000"
npm test
npm start
```

Node.js stores the forwarded-ID state file with owner-only permissions where supported. The bridge handles Windows entry-point paths correctly and only marks an event as forwarded after the receiver returns HTTP 202 with `{"accepted":true}`. A crash between receiver commit and local checkpoint can replay an event; the SQLite receiver's canonical-event hash prevents duplicate rows.

## Data-loss boundary

The current Hornet3000 API contract exposes only the most recent 100 events. This bridge cannot guarantee complete backfill if more than 100 events arrive between polls or before first startup. No client-only change can recover events that the source API no longer returns. Lossless operation requires a source-side stable cursor/sequence contract (for example, `after=<opaque cursor>` plus a returned `next_cursor`) and retention long enough for offline stations. Until that API exists, treat the bridge as a best-effort recent-window adapter, not a lossless event bus.

## Security boundary

- Use HTTPS for non-loopback endpoints; loopback HTTP is permitted for local-only deployments.
- Use separate source and receiver credentials.
- Limit network access to trusted stations/VPN peers.
- Preserve the bridge state file and receiver database in protected local storage.
- The receiver commits metadata to SQLite and exposes authenticated local list/delete routes. Its security and retention boundary is documented in [Beekeeper-Monitor](https://github.com/simonthomas-ai/Beekeeper-Monitor/blob/main/integrations/LOCAL-INGESTION.md).
- Database encryption at rest, encrypted off-device backups and a deployment-specific privacy review are still required for multi-station operation.
