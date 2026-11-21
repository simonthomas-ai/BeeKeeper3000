import fs from 'node:fs/promises';
import { constants as fsConstants } from 'node:fs';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { fileURLToPath } from 'node:url';

const sourceUrl = (process.env.HORNET3000_URL || 'http://127.0.0.1:8787').replace(/\/$/, '');
const sourceKey = process.env.HORNET3000_API_KEY || '';
const monitorUrl = (process.env.BEEKEEPER_MONITOR_INGEST_URL || 'http://127.0.0.1:8765/api/v1/events').replace(/\/$/, '');
const monitorToken = process.env.BEEKEEPER_MONITOR_INGEST_TOKEN || '';
const requestedInterval = Number(process.env.POLL_INTERVAL_MS || 10000);
const intervalMs = Number.isFinite(requestedInterval)
  ? Math.min(3600000, Math.max(2000, requestedInterval))
  : Number.NaN;
export function parseCursorRequirement(value = process.env.BRIDGE_REQUIRE_CURSOR) {
  if (value === undefined || value === '') return true;
  if (typeof value !== 'string') {
    throw new Error('BRIDGE_REQUIRE_CURSOR must be true or false');
  }
  const normalized = value.toLowerCase();
  if (normalized === 'true') return true;
  if (normalized === 'false') return false;
  throw new Error('BRIDGE_REQUIRE_CURSOR must be true or false');
}

const requireCursor = parseCursorRequirement();
const statePath = path.resolve(process.env.BRIDGE_STATE_FILE || './monitor-bridge-state.json');
const maxSeen = 10000;
export const MAX_STATE_BYTES = 2 * 1024 * 1024;
const maxSourceResponseBytes = 2 * 1024 * 1024;
const maxReceiverResponseBytes = 4096;
let busy = false;

function checkedEndpoint(name, value) {
  const url = new URL(value);
  const loopbackHosts = new Set(['127.0.0.1', 'localhost', '[::1]']);
  if (url.protocol !== 'https:' && !(url.protocol === 'http:' && loopbackHosts.has(url.hostname))) {
    throw new Error(`${name} must use HTTPS outside loopback`);
  }
  if (url.username || url.password || url.search || url.hash) {
    throw new Error(`${name} must not contain credentials, query parameters or fragments`);
  }
  return url;
}

export function requiredConfig() {
  if (!sourceKey || sourceKey.length < 16) throw new Error('HORNET3000_API_KEY must contain at least 16 characters');
  if (monitorToken.length < 24) throw new Error('BEEKEEPER_MONITOR_INGEST_TOKEN must contain at least 24 characters');
  checkedEndpoint('HORNET3000_URL', sourceUrl);
  checkedEndpoint('BEEKEEPER_MONITOR_INGEST_URL', monitorUrl);
  if (!monitorUrl.endsWith('/api/v1/events')) {
    throw new Error('BEEKEEPER_MONITOR_INGEST_URL must end with /api/v1/events');
  }
  if (!Number.isFinite(intervalMs) || intervalMs < 2000 || intervalMs > 3600000) {
    throw new Error('POLL_INTERVAL_MS must be between 2000 and 3600000');
  }
  return true;
}

export async function readState(file = statePath) {
  let handle;
  try {
    // Open once and validate/read through the same descriptor. O_NOFOLLOW is
    // applied where the operating system supports it (POSIX), preventing a
    // symlink swap between a path check and the subsequent read.
    const flags = fsConstants.O_RDONLY | (fsConstants.O_NOFOLLOW || 0);
    handle = await fs.open(file, flags);
    const stat = await handle.stat();
    if (!stat.isFile() || stat.size > MAX_STATE_BYTES) {
      throw new Error('Bridge state file is invalid or exceeds 2 MiB');
    }
    // Bound the read even if another process grows the opened file after fstat.
    const buffer = Buffer.allocUnsafe(MAX_STATE_BYTES + 1);
    let bytesRead = 0;
    while (bytesRead < buffer.length) {
      const result = await handle.read(
        buffer, bytesRead, buffer.length - bytesRead, bytesRead
      );
      if (result.bytesRead === 0) break;
      bytesRead += result.bytesRead;
    }
    if (bytesRead > MAX_STATE_BYTES) {
      throw new Error('Bridge state file exceeds 2 MiB');
    }
    const value = JSON.parse(buffer.subarray(0, bytesRead).toString('utf8'));
    if (!value || ![1, 2].includes(value.version) || !Array.isArray(value.forwardedIds) ||
        value.forwardedIds.length > maxSeen ||
        !value.forwardedIds.every(x => typeof x === 'string' && /^[\x21-\x7E]{1,128}$/.test(x))) {
      throw new Error('Bridge state file has an unsupported structure');
    }
    const cursor = value.version === 2 ? value.cursor : null;
    if (cursor !== null && (typeof cursor !== 'string' || cursor.length < 1 || cursor.length > 512)) {
      throw new Error('Bridge state cursor is invalid');
    }
    const state = new Set(value.forwardedIds);
    state.cursor = cursor;
    return state;
  } catch (error) {
    if (error.code === 'ENOENT') {
      const empty = new Set();
      empty.cursor = null;
      return empty;
    }
    throw error;
  } finally {
    if (handle) await handle.close();
  }
}

export async function writeState(ids, file = statePath) {
  if (!(ids instanceof Set)) throw new Error('Bridge state must be a Set');
  const cursor = ids.cursor ?? null;
  if (cursor !== null && (typeof cursor !== 'string' || cursor.length < 1 || cursor.length > 512)) {
    throw new Error('Bridge cursor must be a non-empty string of at most 512 characters');
  }
  const stableIds = [...ids].slice(-maxSeen);
  if (!stableIds.every(id => typeof id === 'string' && /^[\x21-\x7E]{1,128}$/.test(id))) {
    throw new Error('Bridge event IDs must be printable ASCII strings of 1..128 characters');
  }
  const data = JSON.stringify({
    version: 2,
    updatedAt: new Date().toISOString(),
    forwardedIds: stableIds,
    cursor
  }, null, 2);
  if (Buffer.byteLength(data, 'utf8') > MAX_STATE_BYTES) {
    throw new Error('Bridge state exceeds the configured 2 MiB size limit');
  }
  const directory = path.dirname(file);
  await fs.mkdir(directory, { recursive: true, mode: 0o700 });
  const temp = `${file}.${process.pid}.${randomUUID()}.tmp`;
  let handle;
  try {
    handle = await fs.open(temp, 'wx', 0o600);
    await handle.writeFile(data, 'utf8');
    await handle.sync();
    await handle.close();
    handle = null;
    await fs.rename(temp, file);
    if (process.platform !== 'win32') {
      const dirHandle = await fs.open(directory, 'r');
      try { await dirHandle.sync(); } finally { await dirHandle.close(); }
    }
  } catch (error) {
    if (handle) await handle.close().catch(() => {});
    await fs.rm(temp, { force: true }).catch(() => {});
    throw error;
  }
}

export async function readJsonLimited(response, maxBytes = maxSourceResponseBytes, label = 'API') {
  const declaredLength = Number(response.headers?.get?.('content-length') || 0);
  if (Number.isFinite(declaredLength) && declaredLength > maxBytes) {
    throw new Error(`${label} response exceeds the configured size limit`);
  }
  if (!response.body) throw new Error(`${label} response body is empty`);
  const chunks = [];
  let total = 0;
  for await (const chunk of response.body) {
    const part = Buffer.from(chunk);
    total += part.byteLength;
    if (total > maxBytes) {
      try { await response.body.cancel(); } catch { /* response already closed */ }
      throw new Error(`${label} response exceeds the configured size limit`);
    }
    chunks.push(part);
  }
  try {
    return JSON.parse(Buffer.concat(chunks).toString('utf8'));
  } catch {
    throw new Error(`${label} returned invalid JSON`);
  }
}

export function toMonitorEvent(event) {
  if (!event || typeof event !== 'object' ||
      typeof event.id !== 'string' || !/^[\x21-\x7E]{1,128}$/.test(event.id) ||
      typeof event.species !== 'string' || event.species.trim().length === 0 ||
      event.species.length > 160) return null;
  const confidence = event.confidence;
  if (typeof confidence !== 'number' || !Number.isFinite(confidence) || confidence < 0 || confidence > 1) return null;
  const timestamp = typeof event.observed_at === 'string' ? event.observed_at : '';
  if (timestamp.length > 40 || !Number.isFinite(Date.parse(timestamp)) || !/(Z|[+-]\d\d:\d\d)$/.test(timestamp)) return null;
  const rawStation = typeof event.station_id === 'string' ? event.station_id : '';
  const station = rawStation.toLowerCase().replace(/[^a-z0-9._-]/g, '_').slice(0, 80) || 'hornet3000-local';
  const species = event.species.toLowerCase().replace(/[^a-z0-9_-]/g, '_').slice(0, 80);
  if (!species) return null;
  return {
    kind: 'camera_detection',
    device_id: station,
    timestamp,
    source: 'hornet3000',
    schema_version: 1,
    payload: {
      label: `unverified_candidate:${species}`,
      confidence,
      origin_event_id: event.id,
      // Source/model fields are never allowed to claim expert confirmation.
      verification_status: 'unverified',
      prey_detected: event.prey_detected === true
    }
  };
}

const RETRYABLE_HTTP_STATUSES = new Set([408, 425, 429, 500, 502, 503, 504]);
const DEFAULT_MAX_ATTEMPTS = 4;
const MAX_RETRY_AFTER_MS = 60_000;

export function retryDelayMs(response, attempt, nowMs = Date.now()) {
  const value = response?.headers?.get?.('retry-after');
  if (value) {
    const trimmed = value.trim();
    let requested = Number.NaN;
    if (/^\d+(?:\.\d+)?$/.test(trimmed)) {
      requested = Number(trimmed) * 1000;
    } else {
      const at = Date.parse(trimmed);
      if (Number.isFinite(at)) requested = Math.max(0, at - nowMs);
    }
    if (Number.isFinite(requested) && requested >= 0) {
      return Math.min(MAX_RETRY_AFTER_MS, requested);
    }
  }
  const safeAttempt = Math.max(1, Math.min(8, Math.trunc(attempt) || 1));
  return Math.min(8000, 500 * (2 ** (safeAttempt - 1)));
}

export async function fetchWithRetry(url, initOrFactory, options = {}) {
  const fetchImpl = options.fetchImpl || fetch;
  const sleep = options.sleep || (ms => new Promise(resolve => setTimeout(resolve, ms)));
  const maxAttempts = options.maxAttempts ?? DEFAULT_MAX_ATTEMPTS;
  if (!Number.isInteger(maxAttempts) || maxAttempts < 1 || maxAttempts > 6) {
    throw new Error('maxAttempts must be between 1 and 6');
  }

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    let response;
    try {
      const init = typeof initOrFactory === 'function' ? initOrFactory(attempt) : initOrFactory;
      response = await fetchImpl(url, init);
    } catch (error) {
      if (attempt === maxAttempts) throw error;
      await sleep(retryDelayMs(null, attempt));
      continue;
    }

    if (!RETRYABLE_HTTP_STATUSES.has(response.status) || attempt === maxAttempts) {
      return response;
    }

    const delay = retryDelayMs(response, attempt);
    try {
      await response.body?.cancel();
    } catch {
      // Response may already have been consumed or closed.
    }
    await sleep(delay);
  }
  throw new Error('HTTP retry loop exited unexpectedly');
}

export async function forwardBatch(events, state, options = {}) {
  if (!Array.isArray(events) || events.length > 1000) throw new Error('Invalid or oversized event batch');
  if (!state || typeof state.has !== 'function' || typeof state.add !== 'function' ||
      typeof state.delete !== 'function' || typeof state.clear !== 'function') {
    throw new Error('A valid bridge state Set is required');
  }
  const endpoint = options.endpoint || monitorUrl;
  const token = options.token || monitorToken;
  const fetchImpl = options.fetchImpl || fetch;
  const save = options.saveState || writeState;
  if (typeof token !== 'string' || token.length < 24) throw new Error('Monitor ingestion token is missing or too short');

  let forwarded = 0;
  for (const event of events) {
    if (!event || typeof event.id !== 'string' || event.id.length < 1 || event.id.length > 128) {
      if (options.rejectInvalid) throw new Error('Cursor page contains an event without a valid stable ID');
      continue;
    }
    if (state.has(event.id)) continue;
    const mapped = toMonitorEvent(event);
    if (!mapped) {
      if (options.rejectInvalid) throw new Error(`Cursor page contains invalid source event ${event.id}`);
      continue;
    }
    const response = await fetchWithRetry(endpoint, () => ({
      method: 'POST',
      redirect: 'error',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(mapped),
      signal: AbortSignal.timeout(options.timeoutMs || 8000)
    }), {
      fetchImpl,
      sleep: options.sleep,
      maxAttempts: options.maxAttempts
    });
    if (response.status !== 202) {
      await response.body?.cancel().catch(() => {});
      throw new Error(`Monitor ingestion failed: HTTP ${response.status}`);
    }
    const acknowledgement = await readJsonLimited(response, maxReceiverResponseBytes, 'Monitor receiver');
    if (!acknowledgement || acknowledgement.accepted !== true) {
      throw new Error('Monitor receiver did not confirm durable event storage');
    }

    // Persist state only after durable receiver acknowledgement. Roll back the
    // in-memory set if the checkpoint write fails, so the next poll retries;
    // the receiver store makes that replay idempotent.
    const previousIds = [...state];
    state.add(event.id);
    if (state.size > maxSeen) {
      const recent = [...state].slice(-maxSeen);
      state.clear();
      for (const id of recent) state.add(id);
    }
    try {
      await save(state);
    } catch (error) {
      state.clear();
      for (const id of previousIds.slice(-maxSeen)) state.add(id);
      throw error;
    }
    forwarded++;
  }
  return forwarded;
}

export async function pollOnce(state, options = {}) {
  const currentState = state || await readState();
  if (!(currentState instanceof Set)) throw new Error('Bridge state must be a Set');
  if (currentState.cursor === undefined) currentState.cursor = null;

  const endpoint = options.sourceUrl || sourceUrl;
  const apiKey = options.sourceKey || sourceKey;
  const fetchImpl = options.fetchImpl || fetch;
  const save = options.saveState || writeState;
  const maxPages = options.maxPages ?? 100;
  if (!Number.isInteger(maxPages) || maxPages < 1 || maxPages > 1000) {
    throw new Error('maxPages must be between 1 and 1000');
  }

  async function fetchPage(cursor) {
    const url = new URL(`${endpoint}/api/events`);
    url.searchParams.set('limit', '100');
    if (cursor !== null) url.searchParams.set('cursor', cursor);
    const response = await fetchWithRetry(url.toString(), () => ({
      redirect: 'error',
      headers: { 'X-API-Key': apiKey, Accept: 'application/json' },
      signal: AbortSignal.timeout(options.timeoutMs || 8000)
    }), {
      fetchImpl,
      sleep: options.sleep,
      maxAttempts: options.maxAttempts
    });
    if (!response.ok) throw new Error(`Hornet3000 API failed: HTTP ${response.status}`);
    const body = await readJsonLimited(response, maxSourceResponseBytes, 'Hornet3000');
    if (!body || !Array.isArray(body.events) || body.events.length > 100) {
      throw new Error('Hornet3000 API response has no valid events array or exceeds the 100-event page');
    }
    return body;
  }

  let body = await fetchPage(currentState.cursor ?? null);
  const hasCursorFields = Object.hasOwn(body, 'next_cursor') || Object.hasOwn(body, 'has_more');

  // Backward-compatible mode for the old limit=100 API. It cannot guarantee
  // lossless delivery. Once a cursor has been checkpointed, never silently
  // downgrade to the lossy API.
  if (!hasCursorFields) {
    if ((options.requireCursor ?? requireCursor) || currentState.cursor !== null) {
      throw new Error('Hornet3000 cursor pagination disappeared; refusing a lossy downgrade');
    }
    currentState.paginationMode = 'legacy-latest-100';
    return forwardBatch(body.events, currentState, options);
  }

  const saveCursor = async nextCursor => {
    const previous = currentState.cursor ?? null;
    currentState.cursor = nextCursor;
    try {
      await save(currentState);
    } catch (error) {
      currentState.cursor = previous;
      throw error;
    }
  };

  let forwarded = 0;
  for (let pageNumber = 1; ; pageNumber++) {
    if (
      typeof body.has_more !== 'boolean' ||
      typeof body.next_cursor !== 'string' ||
      body.next_cursor.length < 1 ||
      body.next_cursor.length > 512
    ) {
      throw new Error('Hornet3000 cursor response must contain has_more and a non-empty next_cursor');
    }

    const previousCursor = currentState.cursor ?? null;
    if (body.has_more && body.events.length === 0) {
      throw new Error('Hornet3000 cursor page claims more events but returned an empty page');
    }
    if ((body.has_more || body.events.length > 0) && body.next_cursor === previousCursor) {
      throw new Error('Hornet3000 cursor did not advance past returned events');
    }

    // In cursor mode, invalid events must stop the page. Advancing past one
    // would make it permanently unrecoverable and violate lossless catch-up.
    forwarded += await forwardBatch(body.events, currentState, {
      ...options,
      rejectInvalid: true
    });
    await saveCursor(body.next_cursor);

    if (!body.has_more || pageNumber >= maxPages) return forwarded;
    body = await fetchPage(body.next_cursor);
    if (!Object.hasOwn(body, 'next_cursor') || !Object.hasOwn(body, 'has_more')) {
      throw new Error('Hornet3000 stopped returning cursor pagination during catch-up');
    }
  }
}

async function main() {
  requiredConfig();
  const state = await readState();
  console.log(`Monitor bridge active; polling ${sourceUrl}/api/events -> ${monitorUrl}`);
  const tick = async () => {
    if (busy) return;
    busy = true;
    try {
      const count = await pollOnce(state, { requireCursor });
      if (count) console.log(`Forwarded ${count} event(s); metadata only.`);
    } catch (error) {
      console.error(`Bridge cycle failed: ${error.message}`);
    } finally { busy = false; }
  };
  await tick();
  setInterval(tick, intervalMs);
}

const entryPath = process.argv[1] ? path.resolve(process.argv[1]) : '';
if (entryPath && entryPath === path.resolve(fileURLToPath(import.meta.url))) {
  main().catch(error => {
    console.error(error.message);
    process.exitCode = 1;
  });
}
