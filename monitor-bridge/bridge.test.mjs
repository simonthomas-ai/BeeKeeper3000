import test from 'node:test';
import assert from 'node:assert/strict';
import { toMonitorEvent } from './bridge.mjs';

test('maps event metadata without image or GPS', () => {
  const mapped = toMonitorEvent({ id: 'event-1', observed_at: '2026-11-20T07:00:00Z',
    station_id: 'yard-cam', species: 'vespa_velutina', confidence: 0.83,
    status: 'unverified', image_path: '/private/capture.jpg', lat: 51.2, lon: 6.8,
    prey_detected: true });
  assert.equal(mapped.kind, 'camera_detection');
  assert.equal(mapped.device_id, 'yard-cam');
  assert.equal(mapped.payload.label, 'unverified_candidate:vespa_velutina');
  assert.equal(mapped.payload.confidence, 0.83);
  assert.equal(mapped.payload.prey_detected, true);
  assert.equal('image_path' in mapped.payload, false);
  assert.equal('lat' in mapped.payload, false);
  assert.equal('lon' in mapped.payload, false);
});

test('rejects invalid confidence and timestamps', () => {
  assert.equal(toMonitorEvent({ id: 'x', species: 'hornet', observed_at: '2026-11-20T07:00:00Z', confidence: 2 }), null);
  assert.equal(toMonitorEvent({ id: 'x', species: 'hornet', observed_at: '2026-11-20T07:00:00', confidence: 0.5 }), null);
});
