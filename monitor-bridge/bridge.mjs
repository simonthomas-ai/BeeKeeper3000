import fs from 'node:fs/promises';
import path from 'node:path';

const sourceUrl = (process.env.HORNET3000_URL || 'http://127.0.0.1:8787').replace(/\/$/, '');
const sourceKey = process.env.HORNET3000_API_KEY || '';
const monitorUrl = (process.env.BEEKEEPER_MONITOR_INGEST_URL || 'http://127.0.0.1:8765/api/v1/events').replace(/\/$/, '');
const monitorToken = process.env.BEEKEEPER_MONITOR_INGEST_TOKEN || '';
const intervalMs = Math.max(2000, Number(process.env.POLL_INTERVAL_MS || 10000));
const statePath = path.resolve(process.env.BRIDGE_STATE_FILE || './monitor-bridge-state.json');
const maxSeen = 10000;
let busy = false;

function requiredConfig() {
  if (!sourceKey) throw new Error('HORNET3000_API_KEY is required');
  if (monitorToken.length < 24) throw new Error('BEEKEEPER_MONITOR_INGEST_TOKEN must contain at least 24 characters');
  for (const [name, value] of [['HORNET3000_URL', sourceUrl], ['BEEKEEPER_MONITOR_INGEST_URL', monitorUrl]]) {
    const url = new URL(value);
    if (url.protocol !== 'https:' && !['127.0.0.1', 'localhost', '::1'].includes(url.hostname)) {
      throw new Error(`${name} must use HTTPS outside loopback`);
    }
  }
}

async function readState() {
  try {
    const value = JSON.parse(await fs.readFile(statePath, 'utf8'));
    return new Set(Array.isArray(value.forwardedIds) ? value.forwardedIds.filter(x => typeof x === 'string') : []);
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
    return new Set();
  }
}

async function writeState(ids) {
  const data = JSON.stringify({ version: 1, updatedAt: new Date().toISOString(), forwardedIds: [...ids].slice(-maxSeen) }, null, 2);
  const temp = `${statePath}.tmp`;
  await fs.writeFile(temp, data, { mode: 0o600 });
  await fs.rename(temp, statePath);
}

export function toMonitorEvent(event) {
  if (!event || typeof event !== 'object' || typeof event.id !== 'string' || typeof event.species !== 'string') return null;
  const confidence = Number(event.confidence);
  if (!Number.isFinite(confidence) || confidence < 0 || confidence > 1) return null;
  const timestamp = typeof event.observed_at === 'string' ? event.observed_at : '';
  if (!Number.isFinite(Date.parse(timestamp)) || !/(Z|[+-]\d\d:\d\d)$/.test(timestamp)) return null;
  const station = typeof event.station_id === 'string' && event.station_id ? event.station_id : 'hornet3000-local';
  const species = event.species.toLowerCase().replace(/[^a-z0-9_-]/g, '_').slice(0, 80);
  return {
    kind: 'camera_detection', device_id: station.slice(0, 128), timestamp,
    source: 'hornet3000', schema_version: 1,
    payload: {
      label: `unverified_candidate:${species}`, confidence,
      origin_event_id: event.id,
      verification_status: typeof event.status === 'string' ? event.status : 'unverified',
      prey_detected: event.prey_detected === true
    }
  };
}

export async function forwardBatch(events, state) {
  let forwarded = 0;
  for (const event of events) {
    if (!event || typeof event.id !== 'string' || state.has(event.id)) continue;
    const mapped = toMonitorEvent(event);
    if (!mapped) continue;
    const response = await fetch(monitorUrl, {
      method: 'POST',
      headers: { Authorization: `Bearer ${monitorToken}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(mapped), signal: AbortSignal.timeout(8000)
    });
    if (response.status !== 202) throw new Error(`Monitor ingestion failed: HTTP ${response.status}`);
    state.add(event.id);
    if (state.size > maxSeen) {
      const recent = [...state].slice(-maxSeen);
      state.clear();
      for (const id of recent) state.add(id);
    }
    forwarded++;
    await writeState(state);
  }
  return forwarded;
}

export async function pollOnce(state) {
  if (!state) state = await readState();
  const response = await fetch(`${sourceUrl}/api/events?limit=100`, {
    headers: { 'X-API-Key': sourceKey, Accept: 'application/json' }, signal: AbortSignal.timeout(8000)
  });
  if (!response.ok) throw new Error(`Hornet3000 API failed: HTTP ${response.status}`);
  const body = await response.json();
  if (!body || !Array.isArray(body.events)) throw new Error('Hornet3000 API response has no events array');
  return forwardBatch(body.events, state);
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

if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(new URL(import.meta.url).pathname))
  main().catch(error => { console.error(error.message); process.exitCode = 1; });
