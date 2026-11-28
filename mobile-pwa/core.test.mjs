import { test } from "node:test";
import { strict as assert } from "node:assert";
import { assertPhotoDimensions, MAX_PHOTO_PIXELS, confidenceScore, makeStationId, toSourceEvent, validateSourceEvent, waitForOrientationSample } from "./core.mjs";

const sample = {
  id: "mobile-test-123456",
  observed_at: "2026-11-20T12:00:00Z",
  station_id: "mobile-0123456789abcdef",
  species: "Vespa velutina (Verdacht)",
  confidence: 0.55,
  prey_detected: false,
  origin: "manual_observation",
};

test("validates photo bitmap dimensions against the configured pixel budget", () => {
  assert.deepEqual(assertPhotoDimensions(4000, 4000), { width: 4000, height: 4000 });
  assert.equal(MAX_PHOTO_PIXELS, 16_000_000);
  assert.throws(() => assertPhotoDimensions(4001, 4000), /16 Megapixel/);
  assert.throws(() => assertPhotoDimensions(0, 100), /Bildabmessungen/);
  assert.throws(() => assertPhotoDimensions(100, NaN), /Bildabmessungen/);
  assert.throws(() => assertPhotoDimensions(1.5, 100), /Bildabmessungen/);
});

test("maps observer confidence levels to bounded numeric values", () => {
  assert.equal(confidenceScore("low"), 0.25);
  assert.equal(confidenceScore("medium"), 0.55);
  assert.equal(confidenceScore("high"), 0.85);
  assert.throws(() => confidenceScore("certain"));
});

test("validates the exact seven-field Source API event contract", () => {
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
  assert.throws(() => validateSourceEvent({ ...sample, origin: "camera" }));
});

test("metadata export strips every local-only field", () => {
  const exported = toSourceEvent({
    event_id: sample.id,
    ...sample,
    private: { note: "private", photo: "blob", location: { latitude: 1 } },
  });
  assert.deepEqual(Object.keys(exported).sort(), [
    "id", "observed_at", "station_id", "species", "confidence", "prey_detected", "origin",
  ].sort());
  assert.equal("private" in exported, false);
  assert.deepEqual(exported, sample);
});

test("creates stable technical mobile station IDs", () => {
  assert.equal(makeStationId("0123456789ABCDEF"), "mobile-0123456789abcdef");
  assert.throws(() => makeStationId("not-a-uuid"));
});


function orientationTarget(){
 const listeners=new Map();
 return {
  addEventListener(type,fn){if(!listeners.has(type))listeners.set(type,new Set());listeners.get(type).add(fn)},
  removeEventListener(type,fn){listeners.get(type)?.delete(fn)},
  emit(type,event){for(const fn of [...(listeners.get(type)||[])])fn(event)},
  listenerCount(type){return listeners.get(type)?.size||0}
 };
}

test("orientation capture ignores an uninitialized first event and accepts the next valid sample", async()=>{
 const target=orientationTarget();
 let timeoutHandler,cleared=false;
 const pending=waitForOrientationSample(target,{
  timeoutMs:5000,
  now:()=>"2026-11-21T10:00:00.000Z",
  setTimer:fn=>{timeoutHandler=fn;return 1},
  clearTimer:id=>{assert.equal(id,1);cleared=true}
 });
 target.emit("deviceorientation",{alpha:null,beta:null,gamma:null});
 assert.equal(target.listenerCount("deviceorientation"),1);
 target.emit("deviceorientation",{alpha:42.5,beta:-2,gamma:3,absolute:true});
 assert.deepEqual(await pending,{
  alpha_deg:42.5,beta_deg:-2,gamma_deg:3,absolute:true,
  captured_at:"2026-11-21T10:00:00.000Z",
  status:"raw_uncalibrated_not_for_triangulation"
 });
 assert.equal(target.listenerCount("deviceorientation"),0);
 assert.equal(cleared,true);
 assert.equal(typeof timeoutHandler,"function");
});

test("orientation capture rejects after timeout and always removes its listener",async()=>{
 const target=orientationTarget();
 let timeoutHandler,cleared=false;
 const pending=waitForOrientationSample(target,{
  timeoutMs:5000,
  setTimer:fn=>{timeoutHandler=fn;return 7},
  clearTimer:id=>{assert.equal(id,7);cleared=true}
 });
 target.emit("deviceorientation",{alpha:null});
 assert.equal(target.listenerCount("deviceorientation"),1);
 timeoutHandler();
 await assert.rejects(pending,/Keine Sensordaten empfangen/);
 assert.equal(target.listenerCount("deviceorientation"),0);
 assert.equal(cleared,true);
});

test("orientation helper rejects invalid targets and timeout values",()=>{
 assert.throws(()=>waitForOrientationSample(null),/Event-Listener/);
 const target=orientationTarget();
 assert.throws(()=>waitForOrientationSample(target,{timeoutMs:50}),/Timeout/);
});

test("orientation capture ignores non-finite and out-of-range azimuths, sanitizes optional axes",async()=>{
 const target=orientationTarget();
 const pending=waitForOrientationSample(target,{
  timeoutMs:5000,
  now:()=>"2026-11-21T11:00:00.000Z",
  setTimer:()=>1,
  clearTimer:()=>{}
 });
 for(const event of [
  null,
  {alpha:NaN},
  {alpha:Infinity},
  {alpha:-0.01},
  {alpha:360.01}
 ]){
  target.emit("deviceorientation",event);
  assert.equal(target.listenerCount("deviceorientation"),1);
 }
 target.emit("deviceorientation",{alpha:360,beta:NaN,gamma:Infinity,absolute:1});
 assert.deepEqual(await pending,{
  alpha_deg:360,beta_deg:null,gamma_deg:null,absolute:false,
  captured_at:"2026-11-21T11:00:00.000Z",
  status:"raw_uncalibrated_not_for_triangulation"
 });
 assert.equal(target.listenerCount("deviceorientation"),0);
});
