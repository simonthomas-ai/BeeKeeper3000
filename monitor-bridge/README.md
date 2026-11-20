# Hornet3000 → Beekeeper-Monitor bridge

The local Node.js adapter transfers selected **metadata only** from Hornet3000 to the authenticated Beekeeper-Monitor receiver. The payload excludes image/audio bytes, camera filenames, GPS coordinates, API credentials and free text. Source species labels are always converted to `unverified_candidate:`; an upstream model status can never assert expert confirmation.

## Requirements

- Node.js 22 LTS (Node.js 20+ may work, but CI currently tests Node.js 22).
- Hornet3000's authenticated local API at `GET /api/events?limit=100`; lossless delivery requires the cursor contract in [SOURCE-CURSOR-CONTRACT.md](./SOURCE-CURSOR-CONTRACT.md).
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
# Set true only after Hornet3000 implements the cursor contract; otherwise the bridge stops rather than using a lossy latest-100 feed.
$env:BRIDGE_REQUIRE_CURSOR = "true"
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

## Cursor catch-up and current source limitation

The bridge now supports source-side opaque cursor pagination. It persists a version-2 checkpoint containing a cursor and bounded forwarded-ID set, accepts existing version-1 state files, processes multiple 100-event pages per poll, and advances a cursor only after every event in that page has been acknowledged by the Monitor. If a partial page fails, the cursor remains at the previous page boundary; previously accepted events are skipped on replay and the receiver's idempotent hash prevents duplicate rows. Cursor-mode pages reject invalid events rather than advancing past them.

The existing Hornet3000 API in this repository still exposes only `GET /api/events?limit=100`; the source-side cursor implementation is not present here. Until that API returns `events`, `next_cursor` and `has_more` according to [SOURCE-CURSOR-CONTRACT.md](./SOURCE-CURSOR-CONTRACT.md), the default backward-compatible bridge mode falls back to the latest-100 feed and is **not lossless**. Set `BRIDGE_REQUIRE_CURSOR=true` to make production operation fail closed unless the cursor contract is available. Do not mark issue #7 complete until the source API, retention and backlog acceptance tests exist. No client-side retry can recover records already omitted by the source API. See [BeeKeeper3000 issue #7](https://github.com/simonthomas-ai/BeeKeeper3000/issues/7).

## Verification boundary

The bridge CI runs Node syntax checks and unit tests. The Monitor CI separately exercises authenticated ingestion, SQLite persistence, PWA visibility, browser tests and WebKit/iPhone emulation. CI does not establish a successful connection to a specific live Hornet3000 station, camera or radio; perform a local end-to-end test with test data before deployment.
