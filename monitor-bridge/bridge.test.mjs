import test from 'node:test';
import assert from 'node:assert/strict';
import { toMonitorEvent, forwardBatch, pollOnce } from './bridge.mjs';

const token = 'test-only-monitor-token-long-enough-123456';
const event = {
  id: 'event-1',
  observed_at: '2026-11-20T07:00:00Z',
  station_id: 'yard-cam',
  species: 'vespa_velutina',
  confidence: 0.83,
  status: 'unverified',
  image_path: '/private/capture.jpg',
  latitude: 51.2,
  longitude: 6.8,
  prey_detected: true
};

test('maps event metadata without image or GPS', () => {
  const mapped = toMonitorEvent(event);
  assert.equal(mapped.kind, 'camera_detection');
  assert.equal(mapped.device_id, 'yard-cam');
  assert.equal(mapped.payload.label, 'unverified_candidate:vespa_velutina');
  assert.equal(mapped.payload.confidence, 0.83);
  assert.equal(mapped.payload.prey_detected, true);
  assert.equal('image_path' in mapped.payload, false);
  assert.equal('latitude' in mapped.payload, false);
  assert.equal('longitude' in mapped.payload, false);
});

test('rejects invalid confidence, identity and timestamps', () => {
  assert.equal(toMonitorEvent({ ...event, confidence: 2 }), null);
  assert.equal(toMonitorEvent({ ...event, confidence: true }), null);
  assert.equal(toMonitorEvent({ ...event, observed_at: '2026-11-20T07:00:00' }), null);
  assert.equal(toMonitorEvent({ ...event, id: '' }), null);
  assert.equal(toMonitorEvent({ ...event, id: 'x'.repeat(129) }), null);
  assert.equal(toMonitorEvent({ ...event, species: '' }), null);
});

test('forwardBatch marks an event only after durable receiver acknowledgement and is idempotent in memory', async () => {
  const state = new Set();
  let accepted = 0;
  let persisted = 0;
  const fetchImpl = async (_url, options) => {
    const payload = JSON.parse(options.body);
    assert.equal(payload.payload.label, 'unverified_candidate:vespa_velutina');
    assert.equal('latitude' in payload.payload, false);
    accepted++;
    return new Response(JSON.stringify({ accepted: true }), {
      status: 202, headers: { 'content-type': 'application/json' }
    });
  };
  const options = {
    url: 'http://127.0.0.1:8765/api/v1/events',
    token,
    fetchImpl,
    persist: async () => { persisted++; }
  };
  assert.equal(await forwardBatch([event], state, options), 1);
  assert.equal(await forwardBatch([event], state, options), 0);
  assert.equal(accepted, 1);
  assert.equal(persisted, 1);
  assert.equal(state.has(event.id), true);
});

test('does not mark event as forwarded when receiver rejects or fails to commit', async () => {
  const state = new Set();
  const options = {
    url: 'http://127.0.0.1:8765/api/v1/events',
    token,
    persist: async () => assert.fail('state must not be persisted'),
    fetchImpl: async () => new Response(JSON.stringify({ accepted: false }), {
      status: 503, headers: { 'content-type': 'application/json' }
    })
  };
  await assert.rejects(forwardBatch([event], state, options), /not committed/);
  assert.equal(state.has(event.id), false);
});

test('rejects malformed or oversized acknowledgements', async () => {
  for (const body of ['not-json', 'x'.repeat(4097)]) {
    const state = new Set();
    await assert.rejects(forwardBatch([event], state, {
      url: 'http://127.0.0.1:8765/api/v1/events',
      token,
      persist: async () => {},
      fetchImpl: async () => new Response(body, { status: 202 })
    }), /acknowledgement/);
    assert.equal(state.has(event.id), false);
  }
});

test('pollOnce bounds source API response size', async () => {
  await assert.rejects(
    pollOnce(new Set(), {
      url: 'http://127.0.0.1:8787/api/events?limit=100',
      timeoutMs: 1000,
      fetchImpl: async () => new Response('x'.repeat(2 * 1024 * 1024 + 1), { status: 200 })
    }),
    /exceeds 2097152 bytes/
  );
});
