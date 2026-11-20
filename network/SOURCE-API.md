# Durable Hornet3000 source API

This is a small, independently runnable source-side event journal for installations whose original Hornet3000 HTTP server is not available in this repository. It implements the API expected by `monitor-bridge/bridge.mjs`; it does **not** retrofit the missing C++ 1.6.0 service or automatically connect a camera/model pipeline. A trusted producer must POST validated detections to this service.

## Run on Windows PowerShell

Use separate randomly generated values for the source API key and cursor-signing secret:

```powershell
$apiBytes = New-Object byte[] 32
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($apiBytes)
$env:HORNET3000_API_KEY = [Convert]::ToBase64String($apiBytes)

$cursorBytes = New-Object byte[] 32
$rng.GetBytes($cursorBytes)
$rng.Dispose()
$env:HORNET3000_CURSOR_SECRET = [Convert]::ToBase64String($cursorBytes)

$env:HORNET3000_EVENT_DB = "$env:LOCALAPPDATA\BeeKeeper3000\source-events.sqlite3"
$env:HORNET3000_EVENT_RETENTION_DAYS = "30"
$env:HORNET3000_EVENT_MAX_ROWS = "250000"
python -m network.source_api
```

Python 3.11+; the source API uses only the Python standard library. Create a local application data directory protected by the Windows service account ACL. The application does not configure NTFS ACLs or encrypt SQLite itself. Use BitLocker or an encrypted volume.

Linux/macOS:

```sh
export HORNET3000_API_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
export HORNET3000_CURSOR_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
export HORNET3000_EVENT_DB="$HOME/.local/share/beekeeper3000/source-events.sqlite3"
mkdir -p "$HOME/.local/share/beekeeper3000"
chmod 700 "$HOME/.local/share/beekeeper3000"
python -m network.source_api
```

The listener binds only to `127.0.0.1:8787`. Do not expose its HTTP listener publicly. Remote access needs a separately reviewed authenticated VPN/TLS gateway. Never commit secrets, database files, camera material or GPS tracks.

## API contract

Every request includes `X-API-Key`.

- `POST /api/events` stores one strict metadata-only observation. An exact replay returns `200` with `duplicate: true`; a new insert returns `201`.
- `GET /api/events?limit=100&cursor=start` begins at the oldest event still inside the configured retention window. Omitting `cursor` has the same meaning.
- `GET /api/events?limit=100&cursor=<opaque-token>` resumes after a signed cursor.
- An exact duplicate POST returns `200`; reuse of an immutable ID with changed content returns `409`; a full journal returns `503` without dropping retained records.
- Pages are 1–100 events, oldest first, with `events`, `next_cursor` and `has_more`, matching the bridge contract.
- Cursors use HMAC-SHA256 and are tied to this event stream. Malformed or forged cursors return 400. A previously issued cursor behind retention returns 410 with `earliest_sequence` and a signed `earliest_cursor`; the operator must explicitly accept the retention gap before resuming. The service never silently resets a stale cursor. A new consumer using `start` begins at the oldest record still retained.

The strict event schema accepts only `id`, `observed_at`, `station_id`, `species`, `confidence` and `prey_detected`. It rejects image/audio data, file paths, GPS coordinates, credentials, arbitrary free text and expert-verification claims. The bridge subsequently maps model output to `unverified_candidate`.

## Reliability and storage

- SQLite write transactions allocate monotonically increasing `AUTOINCREMENT` sequence numbers.
- Stable source IDs are unique. Exact duplicate payloads are idempotent; the same ID with changed content is rejected.
- Cursor sequence and retained-event boundary are persisted. Sequence numbers do not reset when retention removes every row.
- Retention is age-bounded and enforced during writes and page reads; maximum row count is bounded. At capacity the service fails closed rather than evicting events that a bridge may not yet have consumed.
- Maximum request body is 32 KiB; maximum page response is 2 MiB. Request workers, queue, body deadline and per-IP rate-limit state are bounded.
- SQLite is not encrypted by this application. POSIX data directories must be owned by the service account and mode 0700; SQLite files/sidecars are mode 0600. Windows deployments must set explicit NTFS ACLs.

## Connect the bridge

In the BeeKeeper3000 checkout, point the existing bridge at `http://127.0.0.1:8787`, set `HORNET3000_API_KEY` to the source API key, and set the independent Monitor receiver URL/token. Use `BRIDGE_REQUIRE_CURSOR=true`; the bridge now fails closed rather than silently falling back to a lossy latest-100 feed.

A separate producer/inference component still needs to POST accepted candidate events to this API. No live camera or classifier is wired to it by this module.

## Tests

```sh
python -m unittest network.test_source_api -v
python -m unittest network.test_source_api network.test_triangulation -v
```

The suite tests 250-event pagination, restart/resume, tampered/stale cursors, retention, duplicate delivery, capacity, authentication and privacy-field rejection. These are software tests, not radio coverage or field-validation tests.
