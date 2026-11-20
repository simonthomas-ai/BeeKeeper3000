import { test } from "node:test";
import { strict as assert } from "node:assert";
import { confidenceScore, makeStationId, toSourceEvent, validateSourceEvent } from "./core.mjs";

const sample = {
  id: "mobile-test-123456",
  observed_at: "2026-11-20T12:00:00Z",
  station_id: "mobile-0123456789abcdef",
  species: "Vespa velutina (Verdacht)",
  confidence: 0.55,
  prey_detected: false,
};

test("maps observer confidence levels to bounded numeric values", () => {
  assert.equal(confidenceScore("low"), 0.25);
  assert.equal(confidenceScore("medium"), 0.55);
  assert.equal(confidenceScore("high"), 0.85);
  assert.throws(() => confidenceScore("certain"));
});

test("validates the exact six-field Source API event contract", () => {
  assert.deepEqual(validateSourceEvent({ ...sample }), sample);
});

test("rejects GPS, media and arbitrary extra fields from network event", () => {
  assert.throws(() => validateSourceEvent({ ...sample, latitude: 51.2 }));
  assert.throws(() => validateSourceEvent({ ...sample, image: "base64" }));
});

test("rejects invalid IDs, timezone-free timestamps and out-of-range confidence", () => {
  assert.throws(() => validateSourceEvent({ ...sample, id: "has space" }));
  assert.throws(() => validateSourceEvent({ ...sample, observed_at: "2026-11-20T12:00:00" }));
  assert.throws(() => validateSourceEvent({ ...sample, confidence: 1.5 }));
  assert.throws(() => validateSourceEvent({ ...sample, prey_detected: 0 }));
});

test("metadata export strips every local-only field", () => {
  const exported = toSourceEvent({
    event_id: sample.id,
    ...sample,
    private: { note: "private", photo: "blob", location: { latitude: 1 } },
  });
  assert.deepEqual(Object.keys(exported).sort(), [
    "id", "observed_at", "station_id", "species", "confidence", "prey_detected",
  ].sort());
  assert.equal("private" in exported, false);
  assert.deepEqual(exported, sample);
});

test("creates stable technical mobile station IDs", () => {
  assert.equal(makeStationId("0123456789ABCDEF"), "mobile-0123456789abcdef");
  assert.throws(() => makeStationId("not-a-uuid"));
});
