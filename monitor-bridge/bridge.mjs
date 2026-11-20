import fs from 'node:fs/promises';
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
const statePath = path.resolve(process.env.BRIDGE_STATE_FILE || './monitor-bridge-state.json');
const maxSeen = 10000;
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

async function readState() {
  try {
    const stat = await fs.stat(statePath);
    if (!stat.isFile() || stat.size > 1024 * 1024) throw new Error('Bridge state file is invalid or exceeds 1 MiB');
    const value = JSON.parse(await fs.readFile(statePath, 'utf8'));
    if (!value || value.version !== 1 || !Array.isArray(value.forwardedIds) ||
        value.forwardedIds.length > maxSeen ||
        !value.forwardedIds.every(x => typeof x === 'string' && x.length > 0 && x.length <= 128)) {
      throw new Error('Bridge state file has an unsupported structure');
    }
    return new Set(value.forwardedIds);
  } catch (error) {
    if (error.code === 'ENOENT') return new Set();
    throw error;
  }
}

async function writeState(ids, file = statePath) {
  const stableIds = [...ids].slice(-maxSeen);
  const data = JSON.stringify({ version: 1, updatedAt: new Date().toISOString(), forwardedIds: stableIds }, null, 2);
  const directory = path.dirname(file);
  await fs.mkdir(directory, { recursive: true, mode: 0o700 });
  const temp = `${file}.${process.pid}.${randomUUID()}.tmp`;
  try {
    await fs.writeFile(temp, data, { mode: 0o600, flag: 'wx' });
    await fs.rename(temp, file);
  } catch (error) {
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
    if (!event || typeof event.id !== 'string' || event.id.length < 1 || event.id.length > 128 || state.has(event.id)) continue;
    const mapped = toMonitorEvent(event);
    if (!mapped) continue;
    const response = await fetchImpl(endpoint, {
      method: 'POST',
      redirect: 'error',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(mapped),
      signal: AbortSignal.timeout(8000)
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
  if (!state) state = await readState();
  const endpoint = options.sourceUrl || sourceUrl;
  const apiKey = options.sourceKey || sourceKey;
  const fetchImpl = options.fetchImpl || fetch;
  const response = await fetchImpl(`${endpoint}/api/events?limit=100`, {
    redirect: 'error',
    headers: { 'X-API-Key': apiKey, Accept: 'application/json' },
    signal: AbortSignal.timeout(8000)
  });
  if (!response.ok) throw new Error(`Hornet3000 API failed: HTTP ${response.status}`);
  const body = await readJsonLimited(response, maxSourceResponseBytes, 'Hornet3000');
  if (!body || !Array.isArray(body.events) || body.events.length > 100) {
    throw new Error('Hornet3000 API response has no valid events array or exceeds the 100-event page');
  }
  return forwardBatch(body.events, state, options);
}

async function main() {
  requiredConfig();
  const state = await readState();
  console.log(`Monitor bridge active; polling ${sourceUrl}/api/events -> ${monitorUrl}`);
  const tick = async () => {
    if (busy) return;
    busy = true;
    try {
      const count = await pollOnce(state);
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
