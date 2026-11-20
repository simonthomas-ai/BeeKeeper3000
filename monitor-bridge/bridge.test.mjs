import test from 'node:test';
import assert from 'node:assert/strict';
import { toMonitorEvent, forwardBatch, readJsonLimited } from './bridge.mjs';

const sampleEvent = {
  id: 'event-1',
  observed_at: '2026-11-20T07:00:00Z',
  station_id: 'Yard Cam / North',
  species: 'Vespa velutina',
  confidence: 0.83,
  status: 'expert_confirmed',
  image_path: '/private/capture.jpg',
  lat: 51.2,
  lon: 6.8,
  prey_detected: true
};

test('maps only metadata and never trusts upstream verification state', () => {
  const mapped = toMonitorEvent(sampleEvent);
  assert.equal(mapped.kind, 'camera_detection');
  assert.equal(mapped.device_id, 'yard_cam___north');
  assert.equal(mapped.payload.label, 'unverified_candidate:vespa_velutina');
  assert.equal(mapped.payload.confidence, 0.83);
  assert.equal(mapped.payload.prey_detected, true);
  assert.equal(mapped.payload.verification_status, 'unverified');
  assert.equal('image_path' in mapped.payload, false);
  assert.equal('lat' in mapped.payload, false);
  assert.equal('lon' in mapped.payload, false);
});

test('rejects invalid confidence, timestamps, IDs and species labels', () => {
  assert.equal(toMonitorEvent({ ...sampleEvent, confidence: 2 }), null);
  assert.equal(toMonitorEvent({ ...sampleEvent, confidence: '0.5' }), null);
  assert.equal(toMonitorEvent({ ...sampleEvent, observed_at: '2026-11-20T07:00:00' }), null);
  assert.equal(toMonitorEvent({ ...sampleEvent, id: 'x'.repeat(129) }), null);
  assert.equal(toMonitorEvent({ ...sampleEvent, species: '   ' }), null);
});

test('bounds and sanitizes station identity', () => {
  const mapped = toMonitorEvent({ ...sampleEvent, station_id: '  roof/camera  ' });
  assert.equal(mapped.device_id, '__roof_camera__');
  assert.ok(mapped.device_id.length <= 80);
});

test('forwardBatch is logically idempotent and persists only successful sends', async () => {
  const state = new Set();
  const saved = [];
  const sent = [];
  const count = await forwardBatch([sampleEvent, sampleEvent], state, {
    endpoint: 'http://127.0.0.1:8765/api/v1/events',
    token: 'test-only-token-long-enough-123',
    fetchImpl: async (url, options) => {
      sent.push({ url, options, payload: JSON.parse(options.body) });
      return new Response(null, { status: 202 });
    },
    saveState: async current => saved.push([...current])
  });
  assert.equal(count, 1);
  assert.equal(sent.length, 1);
  assert.equal(sent[0].options.redirect, 'error');
  assert.equal(sent[0].payload.payload.verification_status, 'unverified');
  assert.deepEqual(saved, [['event-1']]);
  assert.equal(state.has('event-1'), true);
});

test('failed ingestion does not mark event as forwarded', async () => {
  const state = new Set();
  await assert.rejects(() => forwardBatch([sampleEvent], state, {
    token: 'test-only-token-long-enough-123',
    fetchImpl: async () => new Response(null, { status: 503 }),
    saveState: async () => assert.fail('state must not be persisted after failure')
  }), /HTTP 503/);
  assert.equal(state.has('event-1'), false);
});

test('rejects unbounded or malformed source JSON responses', async () => {
  const good = new Response(JSON.stringify({ events: [] }), { status: 200 });
  assert.deepEqual(await readJsonLimited(good), { events: [] });
  const large = new Response('x'.repeat(1025), { status: 200 });
  await assert.rejects(() => readJsonLimited(large, 1024), /size limit/);
  const invalid = new Response('{broken', { status: 200 });
  await assert.rejects(() => readJsonLimited(invalid), /invalid JSON/);
});

test('rejects oversized event batch', async () => {
  await assert.rejects(() => forwardBatch(new Array(1001).fill(sampleEvent), new Set()), /oversized/);
});
