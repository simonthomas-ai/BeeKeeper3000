# Hornet3000 → Beekeeper-Monitor bridge

The local Node.js adapter transfers selected **metadata only** from Hornet3000 to the authenticated Beekeeper-Monitor receiver. The payload excludes image/audio bytes, camera filenames, GPS coordinates, API credentials and free text. Source species labels are always converted to `unverified_candidate:`; an upstream model status can never assert expert confirmation.

## Requirements

- Node.js 22 LTS (Node.js 20+ may work, but CI currently tests Node.js 22).
- Hornet3000's authenticated local API at `GET /api/events?limit=100`.
- Beekeeper-Monitor's local receiver and PWA.
- Separate source API key and random receiver token (at least 24 characters). Never reuse credentials.

## Start the local receiver (PowerShell)

In the Beekeeper-Monitor checkout:

```powershell
$bytes = New-Object byte[] 32
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($bytes)
$rng.Dispose()
$env:VESPAGUARD_INGEST_TOKEN = [Convert]::ToBase64String($bytes)
$env:VESPAGUARD_INGEST_DB = "$env:LOCALAPPDATA\BeeKeeper-Monitor\events.sqlite3"
python -m integrations.local_ingest
```

Keep the receiver bound to `127.0.0.1:8765`. Open the local station PWA at [http://127.0.0.1:8765/](http://127.0.0.1:8765/). Do not expose the HTTP listener directly to the public internet. For remote operation use a private VPN and a separately reviewed HTTPS reverse proxy.

## Start the bridge (second PowerShell window)

In the BeeKeeper3000 checkout:

```powershell
$env:HORNET3000_URL = "http://127.0.0.1:8787"
$env:HORNET3000_API_KEY = "YOUR_HORNET3000_API_KEY"
$env:BEEKEEPER_MONITOR_INGEST_URL = "http://127.0.0.1:8765/api/v1/events"
$env:BEEKEEPER_MONITOR_INGEST_TOKEN = "PASTE_THE_RECEIVER_TOKEN"
$env:BRIDGE_STATE_FILE = "$env:LOCALAPPDATA\BeeKeeper-Monitor\bridge-state.json"
$env:POLL_INTERVAL_MS = "10000"
cd monitor-bridge
npm test
npm start
```

Run the local receiver and bridge under separate service identities or terminal sessions. Do not put the secrets in source files, screenshots, support logs or commits.

## Reliability and checkpoint rules

- Event IDs are checkpointed only after the receiver confirms HTTP 202 with `{"accepted":true}`.
- If the checkpoint write fails, the in-memory ID is rolled back and will be retried on the next poll.
- A crash after receiver commit but before checkpoint write can replay the event. The Monitor's SQLite receiver uses a canonical event hash and unique key to make that replay logically idempotent. If the local state file is temporarily unwritable, the in-memory checkpoint is rolled back and the next poll retries.
- Bridge state is written atomically to a private state file; invalid or oversized state is rejected rather than silently treated as empty.
- Source and receiver JSON responses are size-bounded; redirects are rejected; requests time out.
- All source detections remain unverified candidates until human/expert review.

## Important source API limitation

Hornet3000 currently exposes only the latest 100 events through `GET /api/events?limit=100`; there is no documented cursor/sequence catch-up contract in this repository. The bridge therefore cannot guarantee lossless historical delivery if more than 100 events arrive between polls or before a station reconnects. No client-side retry can recover events that the source API no longer returns. Lossless backfill requires a source-side monotonic sequence or opaque cursor with paginated catch-up and retention. See [BeeKeeper3000 issue #7](https://github.com/simonthomas-ai/BeeKeeper3000/issues/7).

## Verification boundary

The bridge CI runs Node syntax checks and unit tests. The Monitor CI separately exercises authenticated ingestion, SQLite persistence, PWA visibility, browser tests and WebKit/iPhone emulation. CI does not establish a successful connection to a specific live Hornet3000 station, camera or radio; perform a local end-to-end test with test data before deployment.
