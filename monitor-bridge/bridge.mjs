import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const sourceUrl = (process.env.HORNET3000_URL || 'http://127.0.0.1:8787').replace(/\/$/, '');
const sourceKey = process.env.HORNET3000_API_KEY || '';
const monitorUrl = (process.env.BEEKEEPER_MONITOR_INGEST_URL || 'http://127.0.0.1:8765/api/v1/events').replace(/\/$/, '');
const monitorToken = process.env.BEEKEEPER_MONITOR_INGEST_TOKEN || '';
const requestedInterval = Number(process.env.POLL_INTERVAL_MS || 10000);
const intervalMs = Number.isFinite(requestedInterval)
  ? Math.min(300000, Math.max(2000, Math.trunc(requestedInterval)))
  : 10000;
const statePath = path.resolve(process.env.BRIDGE_STATE_FILE || './monitor-bridge-state.json');
const maxSeen = 10000;
const maxSourceResponseBytes = 2 * 1024 * 1024;
const maxReceiverResponseBytes = 4096;
let busy = false;

function requiredConfig() {
  if (!sourceKey) throw new Error('HORNET3000_API_KEY is required');
  if (monitorToken.length < 24) throw new Error('BEEKEEPER_MONITOR_INGEST_TOKEN must contain at least 24 characters');
  for (const [name, value] of [['HORNET3000_URL', sourceUrl], ['BEEKEEPER_MONITOR_INGEST_URL', monitorUrl]]) {
    const url = new URL(value);
    const loopback = ['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname);
    if (url.protocol !== 'https:' && !loopback) {
      throw new Error(`${name} must use HTTPS outside loopback`);
    }
  }
}

async function readState() {
  try {
    const value = JSON.parse(await fs.readFile(statePath, 'utf8'));
    return new Set(Array.isArray(value.forwardedIds)
      ? value.forwardedIds.filter(x => typeof x === 'string' && x.length <= 128).slice(-maxSeen)
      : []);
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
    return new Set();
  }
}

async function writeState(ids) {
  const data = JSON.stringify({
    version: 1,
    updatedAt: new Date().toISOString(),
    forwardedIds: [...ids].slice(-maxSeen)
  }, null, 2);
  const temp = `${statePath}.tmp`;
  await fs.writeFile(temp, data, { mode: 0o600 });
  await fs.rename(temp, statePath);
}

export function toMonitorEvent(event) {
  if (!event || typeof event !== 'object' ||
      typeof event.id !== 'string' || event.id.length < 1 || event.id.length > 128 ||
      typeof event.species !== 'string' || !event.species.trim() || event.species.length > 80) return null;
  if (typeof event.confidence === 'boolean') return null;
  const confidence = Number(event.confidence);
  if (!Number.isFinite(confidence) || confidence < 0 || confidence > 1) return null;
  const timestamp = typeof event.observed_at === 'string' ? event.observed_at : '';
  if (!Number.isFinite(Date.parse(timestamp)) || !/(Z|[+-]\d\d:\d\d)$/.test(timestamp)) return null;
  const station = typeof event.station_id === 'string' && event.station_id.trim()
    ? event.station_id.trim().slice(0, 128)
    : 'hornet3000-local';
  const species = event.species.toLowerCase().replace(/[^a-z0-9_-]/g, '_').slice(0, 80);
  if (!species) return null;
  const status = typeof event.status === 'string' && event.status.trim()
    ? event.status.trim().slice(0, 64)
    : 'unverified';
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
      verification_status: status,
      prey_detected: event.prey_detected === true
    }
  };
}

async function readJsonLimited(response, maxBytes, sourceName) {
  const declared = Number(response.headers?.get?.('content-length') || 0);
  if (Number.isFinite(declared) && declared > maxBytes) {
    throw new Error(`${sourceName} response exceeds ${maxBytes} bytes`);
  }
  if (!response.body?.getReader) {
    const text = await response.text();
    if (Buffer.byteLength(text, 'utf8') > maxBytes) throw new Error(`${sourceName} response is too large`);
    return JSON.parse(text);
  }
  const reader = response.body.getReader();
  const chunks = [];
  let total = 0;
  try {
    while (true) {
      const part = await reader.read();
      if (part.done) break;
      total += part.value.byteLength;
      if (total > maxBytes) {
        await reader.cancel();
        throw new Error(`${sourceName} response exceeds ${maxBytes} bytes`);
      }
      chunks.push(Buffer.from(part.value));
    }
  } finally {
    reader.releaseLock();
  }
  return JSON.parse(Buffer.concat(chunks, total).toString('utf8'));
}

export async function forwardBatch(events, state, options = {}) {
  if (!Array.isArray(events) || !(state instanceof Set)) {
    throw new TypeError('forwardBatch requires an event array and a Set state');
  }
  const targetUrl = options.url || monitorUrl;
  const token = options.token || monitorToken;
  const persist = options.persist || writeState;
  const send = options.fetchImpl || fetch;
  const timeoutMs = options.timeoutMs || 8000;
  if (!token || token.length < 24) throw new Error('Monitor ingestion token is missing or too short');

  let forwarded = 0;
  for (const event of events) {
    if (!event || typeof event.id !== 'string' || state.has(event.id)) continue;
    const mapped = toMonitorEvent(event);
    if (!mapped) continue;
    const response = await send(targetUrl, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(mapped),
      signal: AbortSignal.timeout(timeoutMs)
    });
    let acknowledgement;
    try {
      acknowledgement = await readJsonLimited(response, maxReceiverResponseBytes, 'Monitor receiver');
    } catch {
      throw new Error('Monitor receiver returned an invalid or oversized acknowledgement');
    }
    if (response.status !== 202 || acknowledgement?.accepted !== true) {
      throw new Error(`Monitor ingestion was not committed (HTTP ${response.status})`);
    }
    state.add(event.id);
    if (state.size > maxSeen) {
      const recent = [...state].slice(-maxSeen);
      state.clear();
      for (const id of recent) state.add(id);
    }
    forwarded++;
    // Only mark an ID after the receiver confirms durable acceptance.
    // Replays after a crash are safe because the receiver deduplicates canonical events.
    await persist(state);
  }
  return forwarded;
}

export async function pollOnce(state, options = {}) {
  if (!state) state = await readState();
  const fetchImpl = options.fetchImpl || fetch;
  const url = options.url || `${sourceUrl}/api/events?limit=100`;
  const response = await fetchImpl(url, {
    headers: { 'X-API-Key': sourceKey, Accept: 'application/json' },
    signal: AbortSignal.timeout(options.timeoutMs || 8000)
  });
  if (!response.ok) throw new Error(`Hornet3000 API failed: HTTP ${response.status}`);
  const body = await readJsonLimited(response, maxSourceResponseBytes, 'Hornet3000');
  if (!body || !Array.isArray(body.events)) throw new Error('Hornet3000 API response has no events array');
  return forwardBatch(body.events, state, options.forwardOptions || {});
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
    } finally {
      busy = false;
    }
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
