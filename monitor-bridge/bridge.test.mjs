import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { toMonitorEvent, forwardBatch, readJsonLimited, pollOnce, fetchWithRetry, retryDelayMs, readState, writeState, parseCursorRequirement } from './bridge.mjs';

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

test('production requires cursor pagination by default and legacy mode must be explicit', () => {
  assert.equal(parseCursorRequirement(undefined), true);
  assert.equal(parseCursorRequirement(''), true);
  assert.equal(parseCursorRequirement('true'), true);
  assert.equal(parseCursorRequirement('false'), false);
  assert.throws(() => parseCursorRequirement('yes'), /must be true or false/);
});

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
      return new Response(JSON.stringify({ accepted: true }), { status: 202, headers: { 'content-type': 'application/json' } });
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

test('does not checkpoint an event when the receiver does not confirm persistence', async () => {
  const state = new Set();
  const options = {
    endpoint: 'http://127.0.0.1:8765/api/v1/events',
    token: 'test-only-token-long-enough-123',
    fetchImpl: async () => new Response(JSON.stringify({ accepted: false }), {
      status: 202, headers: { 'content-type': 'application/json' }
    }),
    saveState: async () => assert.fail('state must not be persisted')
  };
  await assert.rejects(() => forwardBatch([sampleEvent], state, options), /durable event storage/);
  assert.equal(state.has('event-1'), false);
});

test('rolls back in-memory checkpoint when state file write fails', async () => {
  const state = new Set();
  const options = {
    endpoint: 'http://127.0.0.1:8765/api/v1/events',
    token: 'test-only-token-long-enough-123',
    fetchImpl: async () => new Response(JSON.stringify({ accepted: true }), {
      status: 202, headers: { 'content-type': 'application/json' }
    }),
    saveState: async () => { throw new Error('disk unavailable'); }
  };
  await assert.rejects(() => forwardBatch([sampleEvent], state, options), /disk unavailable/);
  assert.equal(state.has('event-1'), false);
});

test('rejects missing, invalid and oversized receiver acknowledgements', async () => {
  const badBodies = [
    new Response(null, { status: 202 }),
    new Response('{broken', { status: 202 }),
    new Response(JSON.stringify({ accepted: false }), { status: 202 }),
    new Response('x'.repeat(4097), { status: 202 })
  ];
  for (const response of badBodies) {
    const state = new Set();
    await assert.rejects(() => forwardBatch([sampleEvent], state, {
      endpoint: 'http://127.0.0.1:8765/api/v1/events',
      token: 'test-only-token-long-enough-123',
      fetchImpl: async () => response,
      saveState: async () => assert.fail('invalid acknowledgement must not be checkpointed')
    }));
    assert.equal(state.has('event-1'), false);
  }
});

test('pollOnce rejects source responses larger than the configured limit', async () => {
  await assert.rejects(() => pollOnce(new Set(), {
    sourceUrl: 'http://127.0.0.1:8787',
    sourceKey: 'test-source-api-key-long-enough',
    fetchImpl: async () => new Response('x'.repeat(2 * 1024 * 1024 + 1), { status: 200 })
  }), /size limit/);
});

test('direct CLI startup reaches configuration validation on this operating system', () => {
  const entry = fileURLToPath(new URL('./bridge.mjs', import.meta.url));
  const result = spawnSync(process.execPath, [entry], {
    encoding: 'utf8',
    timeout: 5000,
    env: {
      ...process.env,
      HORNET3000_API_KEY: '',
      BEEKEEPER_MONITOR_INGEST_TOKEN: ''
    }
  });
  assert.equal(result.error, undefined, result.error?.message);
  assert.equal(result.status, 1, result.stdout + '\\n' + result.stderr);
  assert.match(result.stderr, /HORNET3000_API_KEY/);
});

test('bounded retry policy honours Retry-After for transient server responses', async () => {
  const statuses = [
    new Response('busy', { status: 503, headers: { 'retry-after': '2.5' } }),
    new Response('rate limited', { status: 429, headers: { 'retry-after': '0' } }),
    new Response('ok', { status: 200 })
  ];
  const sleeps = [];
  let calls = 0;
  const response = await fetchWithRetry('https://example.invalid', {}, {
    maxAttempts: 3,
    fetchImpl: async () => { calls++; return statuses.shift(); },
    sleep: async ms => sleeps.push(ms)
  });
  assert.equal(response.status, 200);
  assert.equal(calls, 3);
  assert.deepEqual(sleeps, [2500, 0]);
});

test('permanent 4xx responses are not retried', async () => {
  let calls = 0;
  let waits = 0;
  const response = await fetchWithRetry('https://example.invalid', {}, {
    fetchImpl: async () => { calls++; return new Response('unauthorized', { status: 401 }); },
    sleep: async () => { waits++; }
  });
  assert.equal(response.status, 401);
  assert.equal(calls, 1);
  assert.equal(waits, 0);
});

test('network errors receive bounded exponential retry delays', async () => {
  const sleeps = [];
  let calls = 0;
  await assert.rejects(() => fetchWithRetry('https://example.invalid', {}, {
    maxAttempts: 3,
    fetchImpl: async () => { calls++; throw new Error('socket timeout'); },
    sleep: async ms => sleeps.push(ms)
  }), /socket timeout/);
  assert.equal(calls, 3);
  assert.deepEqual(sleeps, [500, 1000]);
  assert.equal(retryDelayMs(new Response(null, { status: 503, headers: { 'retry-after': '120' } }), 1), 60000);
});

test('forwardBatch retries a temporary receiver failure before checkpointing', async () => {
  const state = new Set();
  const sleeps = [];
  let calls = 0;
  const count = await forwardBatch([sampleEvent], state, {
    endpoint: 'http://127.0.0.1:8765/api/v1/events',
    token: 'test-only-token-long-enough-123',
    maxAttempts: 3,
    sleep: async ms => sleeps.push(ms),
    fetchImpl: async () => {
      calls++;
      if (calls === 1) return new Response('temporary error', { status: 503 });
      return new Response(JSON.stringify({ accepted: true }), {
        status: 202, headers: { 'content-type': 'application/json' }
      });
    },
    saveState: async () => {}
  });
  assert.equal(count, 1);
  assert.equal(calls, 2);
  assert.equal(sleeps.length, 1);
  assert.equal(state.has('event-1'), true);
});

test('pollOnce retries a rate-limited source API', async () => {
  const sleeps = [];
  let calls = 0;
  const result = await pollOnce(new Set(), {
    sourceUrl: 'http://127.0.0.1:8787',
    sourceKey: 'test-source-api-key-long-enough',
    token: 'test-only-monitor-token-long-enough-123',
    maxAttempts: 3,
    sleep: async ms => sleeps.push(ms),
    fetchImpl: async () => {
      calls++;
      if (calls === 1) return new Response('rate limited', { status: 429, headers: { 'retry-after': '0' } });
      return new Response(JSON.stringify({ events: [] }), {
        status: 200, headers: { 'content-type': 'application/json' }
      });
    }
  });
  assert.equal(result, 0);
  assert.equal(calls, 2);
  assert.deepEqual(sleeps, [0]);
});


function cursorEvent(index) {
  return {
    ...sampleEvent,
    id: `source-event-${index}`,
    station_id: 'station_north',
    observed_at: '2026-11-20T10:00:00Z'
  };
}

test('cursor pagination catches up a backlog larger than one hundred events', async () => {
  const events = Array.from({ length: 205 }, (_, index) => cursorEvent(index + 1));
  const state = new Set();
  state.cursor = null;
  const sourceRequests = [];
  const receiverPosts = [];
  const saved = [];

  const count = await pollOnce(state, {
    sourceUrl: 'http://127.0.0.1:8787',
    sourceKey: 'test-source-api-key-long-enough',
    token: 'test-only-monitor-token-long-enough-123',
    saveState: async current => saved.push({ cursor: current.cursor, ids: [...current] }),
    fetchImpl: async (url, options) => {
      const parsed = new URL(url);
      if (parsed.pathname === '/api/events') {
        const cursor = parsed.searchParams.get('cursor');
        sourceRequests.push(cursor);
        const offset = cursor === null || cursor === 'start' ? 0 : Number(cursor);
        const page = events.slice(offset, offset + 100);
        return new Response(JSON.stringify({
          events: page,
          next_cursor: String(offset + page.length),
          has_more: offset + page.length < events.length
        }), { status: 200, headers: { 'content-type': 'application/json' } });
      }
      if (parsed.pathname === '/api/v1/events') {
        receiverPosts.push(JSON.parse(options.body).payload.origin_event_id);
        return new Response(JSON.stringify({ accepted: true }), {
          status: 202, headers: { 'content-type': 'application/json' }
        });
      }
      throw new Error('Unexpected test URL: ' + url);
    }
  });

  assert.equal(count, 205);
  assert.equal(receiverPosts.length, 205);
  assert.equal(new Set(receiverPosts).size, 205);
  assert.deepEqual(sourceRequests, ['start', '100', '200']);
  assert.equal(state.cursor, '205');
  assert.equal(state.size, 205);
  assert.ok(saved.some(item => item.cursor === '100'));
  assert.ok(saved.some(item => item.cursor === '200'));
  assert.ok(saved.some(item => item.cursor === '205'));
});

test('cursor catch-up resumes from the persisted cursor on the next poll', async () => {
  const state = new Set(['source-event-1']);
  state.cursor = '100';
  const sourceRequests = [];
  const receiverPosts = [];
  const count = await pollOnce(state, {
    sourceUrl: 'http://127.0.0.1:8787',
    sourceKey: 'test-source-api-key-long-enough',
    token: 'test-only-monitor-token-long-enough-123',
    saveState: async () => {},
    fetchImpl: async (url, options) => {
      const parsed = new URL(url);
      if (parsed.pathname === '/api/events') {
        sourceRequests.push(parsed.searchParams.get('cursor'));
        return new Response(JSON.stringify({
          events: [cursorEvent(101)],
          next_cursor: '101',
          has_more: false
        }), { status: 200 });
      }
      receiverPosts.push(JSON.parse(options.body).payload.origin_event_id);
      return new Response(JSON.stringify({ accepted: true }), { status: 202 });
    }
  });
  assert.equal(count, 1);
  assert.deepEqual(sourceRequests, ['100']);
  assert.deepEqual(receiverPosts, ['source-event-101']);
  assert.equal(state.cursor, '101');
});

test('partial cursor page failure retries without advancing the page checkpoint', async () => {
  const state = new Set();
  state.cursor = null;
  let receiverAttempt = 0;
  const sent = [];
  const options = {
    sourceUrl: 'http://127.0.0.1:8787',
    sourceKey: 'test-source-api-key-long-enough',
    token: 'test-only-monitor-token-long-enough-123',
    maxAttempts: 1,
    saveState: async () => {},
    fetchImpl: async (url, init) => {
      const parsed = new URL(url);
      if (parsed.pathname === '/api/events') {
        return new Response(JSON.stringify({
          events: [cursorEvent(1), cursorEvent(2)],
          next_cursor: '2',
          has_more: false
        }), { status: 200 });
      }
      const id = JSON.parse(init.body).payload.origin_event_id;
      sent.push(id);
      receiverAttempt++;
      if (receiverAttempt === 2) return new Response('temporary failure', { status: 503 });
      return new Response(JSON.stringify({ accepted: true }), { status: 202 });
    }
  };

  await assert.rejects(() => pollOnce(state, options), /HTTP 503/);
  assert.equal(state.cursor, null);
  assert.equal(state.has('source-event-1'), true);
  assert.equal(state.has('source-event-2'), false);

  const count = await pollOnce(state, options);
  assert.equal(count, 1);
  assert.equal(state.cursor, '2');
  assert.deepEqual(sent, ['source-event-1', 'source-event-2', 'source-event-2']);
});

test('cursor page with invalid event does not advance and lose that event', async () => {
  const state = new Set();
  state.cursor = null;
  await assert.rejects(() => pollOnce(state, {
    sourceUrl: 'http://127.0.0.1:8787',
    sourceKey: 'test-source-api-key-long-enough',
    token: 'test-only-monitor-token-long-enough-123',
    fetchImpl: async url => new Response(JSON.stringify({
      events: [{ ...cursorEvent(1), confidence: 8 }],
      next_cursor: '1',
      has_more: false
    }), { status: new URL(url).pathname === '/api/events' ? 200 : 202 }),
    saveState: async () => {}
  }), /invalid source event/);
  assert.equal(state.cursor, null);
});

test('cursor mode rejects a source API that silently downgrades to latest-100', async () => {
  const state = new Set();
  state.cursor = 'opaque-cursor-100';
  await assert.rejects(() => pollOnce(state, {
    sourceUrl: 'http://127.0.0.1:8787',
    sourceKey: 'test-source-api-key-long-enough',
    token: 'test-only-monitor-token-long-enough-123',
    fetchImpl: async () => new Response(JSON.stringify({ events: [] }), { status: 200 })
  }), /pagination disappeared/);
});

test('cursor mode rejects non-advancing cursors while more events remain', async () => {
  const state = new Set();
  state.cursor = 'cursor-100';
  await assert.rejects(() => pollOnce(state, {
    sourceUrl: 'http://127.0.0.1:8787',
    sourceKey: 'test-source-api-key-long-enough',
    token: 'test-only-monitor-token-long-enough-123',
    fetchImpl: async () => new Response(JSON.stringify({
      events: [cursorEvent(101)],
      next_cursor: 'cursor-100',
      has_more: true
    }), { status: 200 })
  }), /did not advance/);
});

test('version-one bridge state migrates safely to version two with a null cursor', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'beekeeper-bridge-state-'));
  const file = join(directory, 'state.json');
  try {
    await writeFile(file, JSON.stringify({ version: 1, forwardedIds: ['old-event'] }));
    const state = await readState(file);
    assert.equal(state.has('old-event'), true);
    assert.equal(state.cursor, null);
    state.cursor = 'cursor-7';
    await writeState(state, file);
    const persisted = JSON.parse(await readFile(file, 'utf8'));
    assert.equal(persisted.version, 2);
    assert.equal(persisted.cursor, 'cursor-7');
    assert.deepEqual(persisted.forwardedIds, ['old-event']);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test('corrupt bridge state fails closed instead of resetting the source cursor', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'beekeeper-bridge-corrupt-'));
  const file = join(directory, 'state.json');
  try {
    await writeFile(file, '{"version":2,"forwardedIds":["ok"],"cursor":42}');
    await assert.rejects(() => readState(file), /cursor is invalid/);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});


test('strict production mode refuses latest-100 source responses', async () => {
  const state = new Set();
  state.cursor = null;
  await assert.rejects(() => pollOnce(state, {
    requireCursor: true,
    sourceUrl: 'http://127.0.0.1:8787',
    sourceKey: 'test-source-api-key-long-enough',
    token: 'test-only-monitor-token-long-enough-123',
    fetchImpl: async () => new Response(JSON.stringify({ events: [] }), { status: 200 })
  }), /refusing a lossy downgrade/);
});

test('cursor response cannot claim more events with an empty page', async () => {
  const state = new Set();
  state.cursor = 'cursor-10';
  await assert.rejects(() => pollOnce(state, {
    sourceUrl: 'http://127.0.0.1:8787',
    sourceKey: 'test-source-api-key-long-enough',
    token: 'test-only-monitor-token-long-enough-123',
    fetchImpl: async () => new Response(JSON.stringify({
      events: [],
      next_cursor: 'cursor-11',
      has_more: true
    }), { status: 200 })
  }), /empty page/);
});

test('cursor response must advance when a final page contains an event', async () => {
  const state = new Set();
  state.cursor = 'cursor-10';
  await assert.rejects(() => pollOnce(state, {
    sourceUrl: 'http://127.0.0.1:8787',
    sourceKey: 'test-source-api-key-long-enough',
    token: 'test-only-monitor-token-long-enough-123',
    fetchImpl: async () => new Response(JSON.stringify({
      events: [cursorEvent(11)],
      next_cursor: 'cursor-10',
      has_more: false
    }), { status: 200 })
  }), /did not advance/);
  assert.equal(state.cursor, 'cursor-10');
});

