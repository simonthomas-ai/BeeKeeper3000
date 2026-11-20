# Hornet3000 source API cursor contract

This document defines the source-side API required for lossless bridge catch-up. The current repository contains the bridge client but does not contain the Hornet3000 HTTP server implementation. Therefore this is an implementation contract, not a claim that the source endpoint already supports it.

## Request

`GET /api/events?limit=100`

`GET /api/events?limit=100&cursor=<opaque-token>`

Headers:

- `X-API-Key: <source API key>`
- `Accept: application/json`

Rules:

- `limit` is an integer from 1 through 100. The server must reject values outside this range.
- Omitted cursor means the initial position before the oldest retained sequence.
- Cursor is opaque to clients, URL-safe, no more than 512 characters, and bound to the same logical event stream and station authorization scope.
- The server must reject malformed, expired, tampered or wrong-scope cursors with a non-success response; it must not silently treat them as an initial request.

## Response

HTTP 200 JSON:

```json
{
  "events": [
    {
      "id": "stable-source-event-id",
      "observed_at": "2026-11-20T10:00:00Z",
      "station_id": "yard_cam_north",
      "species": "Vespa velutina",
      "confidence": 0.83,
      "prey_detected": false
    }
  ],
  "next_cursor": "opaque-position-after-last-returned-event",
  "has_more": true
}
```

- `events` is ordered strictly by a monotonically increasing committed sequence, oldest first. The sequence need not be exposed in event JSON.
- Each event has an immutable, globally unique and stable `id`. Reusing an ID for different event contents is prohibited.
- `next_cursor` is always a non-empty opaque token of at most 512 characters, including an empty page. It represents the exact position after the last returned event. For an empty initial page, return a stable beginning sentinel (for example, an encoded sequence zero); do not move the cursor to an unobserved future position.
- `has_more` is true only when another event exists immediately after the returned page at request time.
- The next request with `cursor=next_cursor` returns events strictly after that position, never replays earlier sequence positions except where a caller intentionally reuses an older cursor.
- Maximum response body size is 2 MiB. The server should return a smaller page if needed rather than exceed this limit.
- The server must not return image/audio bytes, local file paths, camera credentials, private keys or personal free text in event objects.

## Consistency and retention

- Allocate the sequence atomically when the event is durably committed.
- A committed event must become visible to pagination only after its transaction commits.
- Pagination must use a stable total order. Concurrent new events may appear on subsequent pages if their committed sequence is greater than the cursor; none may be inserted later with a sequence lower than an already-issued cursor.
- Retain events long enough for the maximum supported offline period and bridge outage. Retention must not delete unforwarded events before the bridge can recover them. For a nationwide deployment, retention needs explicit disk bounds, monitoring, and an agreed offline recovery objective.
- Cursors must remain valid across process restarts and deployments for at least the configured event-retention period. Do not encode in-memory offsets.
- Provide a documented recovery path when a cursor falls behind retention: explicit error with earliest retained sequence and a visible operator intervention. Never silently skip to the newest event.

## Bridge processing semantics

- The bridge stores the cursor locally with its forwarded-ID set.
- It forwards every event in a page to the authenticated Monitor and waits for each durable `202 {"accepted":true}` acknowledgement.
- It checkpoints the page cursor only after the entire page succeeds.
- If a request or checkpoint fails part-way through a page, the page is fetched again. Already acknowledged events are skipped using stable IDs; receiver idempotency protects the crash window between server commit and local state update.
- A malformed event blocks cursor advancement and must create an operator-visible error. It must not be silently skipped.
- The bridge supports `BRIDGE_REQUIRE_CURSOR=true` to prevent production deployments from silently running in latest-100 fallback mode.

## Acceptance tests for the source API

1. Generate at least 250 committed test events and retrieve them in pages of 100, 100 and 50, preserving strict sequence and unique IDs.
2. Disconnect the client after each page, restart the source server, resume from the saved cursor and prove no missing event.
3. Insert new events while catch-up is in progress and verify stable sequence ordering.
4. Test duplicate, malformed, expired and wrong-scope cursors. No malformed cursor may reset to the beginning or newest page.
5. Retention expiry must return an explicit recoverable error and earliest retained position.
6. Test API-key authorization, request timeouts, size limits, rate limiting and no sensitive media/GPS fields.
7. Run an end-to-end test with a local Monitor receiver and assert each source ID maps to exactly one logical receiver event.

Only after these tests pass against the actual Hornet3000 service can bridge issue #7 be closed.
