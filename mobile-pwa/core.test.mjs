import { test } from "node:test";
import { strict as assert } from "node:assert";
import {
  assertPhotoDimensions,
  inspectPhotoFile,
  MAX_PHOTO_BYTES,
  MAX_PHOTO_PIXELS,
  preparePhotoBlob,
  confidenceScore,
  makeStationId,
  toSourceEvent,
  validateSourceEvent,
  waitForOrientationSample
} from "./core.mjs";

const sample = {
  id: "mobile-test-123456",
  observed_at: "2026-11-20T12:00:00Z",
  station_id: "mobile-0123456789abcdef",
  species: "Vespa velutina (Verdacht)",
  confidence: 0.55,
  prey_detected: false,
  origin: "manual_observation",
};

function concatBytes(parts) {
  const size = parts.reduce((sum, part) => sum + part.length, 0);
  const output = new Uint8Array(size);
  let offset = 0;
  for (const part of parts) {
    output.set(part, offset);
    offset += part.length;
  }
  return output;
}

function pngFixture(width, height, { animated = false } = {}) {
  const encoder = new TextEncoder();
  const signature = new Uint8Array([137,80,78,71,13,10,26,10]);
  const ihdr = new Uint8Array(25);
  const ihdrView = new DataView(ihdr.buffer);
  ihdrView.setUint32(0, 13, false);
  ihdr.set(encoder.encode("IHDR"), 4);
  ihdrView.setUint32(8, width, false);
  ihdrView.setUint32(12, height, false);
  ihdr[16] = 8;
  ihdr[17] = 2;
  const end = new Uint8Array(12);
  end.set(encoder.encode("IEND"), 4);
  const parts = [signature, ihdr];
  if (animated) {
    const animation = new Uint8Array(20);
    const view = new DataView(animation.buffer);
    view.setUint32(0, 8, false);
    animation.set(encoder.encode("acTL"), 4);
    view.setUint32(8, 1, false);
    parts.push(animation);
  }
  parts.push(end);
  return concatBytes(parts);
}

function jpegFixture(width, height, { multiPicture = false } = {}) {
  const parts = [new Uint8Array([0xff,0xd8])];
  if (multiPicture) {
    parts.push(new Uint8Array([0xff,0xe2,0x00,0x08,0x4d,0x50,0x46,0x00,0x00,0x00]));
  }
  parts.push(new Uint8Array([
    0xff,0xc0,0x00,0x07,0x08,
    (height >>> 8) & 0xff,height & 0xff,
    (width >>> 8) & 0xff,width & 0xff,
    0xff,0xd9
  ]));
  return concatBytes(parts);
}

function webpFixture(width, height, { animated = false } = {}) {
  const encoder = new TextEncoder();
  const bytes = new Uint8Array(30);
  const view = new DataView(bytes.buffer);
  bytes.set(encoder.encode("RIFF"), 0);
  view.setUint32(4, bytes.length - 8, true);
  bytes.set(encoder.encode("WEBP"), 8);
  bytes.set(encoder.encode("VP8X"), 12);
  view.setUint32(16, 10, true);
  bytes[20] = animated ? 0x02 : 0;
  const w = width - 1, h = height - 1;
  bytes[24] = w & 0xff;
  bytes[25] = (w >>> 8) & 0xff;
  bytes[26] = (w >>> 16) & 0xff;
  bytes[27] = h & 0xff;
  bytes[28] = (h >>> 8) & 0xff;
  bytes[29] = (h >>> 16) & 0xff;
  return bytes;
}

function fileFromBytes(type, bytes) {
  const snapshot = bytes.slice();
  return {
    type,
    size: snapshot.length,
    async arrayBuffer() {
      return snapshot.slice().buffer;
    }
  };
}

test("validates photo bitmap dimensions against the configured pixel budget", () => {
  assert.deepEqual(assertPhotoDimensions(4000, 4000), { width: 4000, height: 4000 });
  assert.equal(MAX_PHOTO_PIXELS, 16_000_000);
  assert.throws(() => assertPhotoDimensions(4001, 4000), /16 Megapixel/);
  assert.throws(() => assertPhotoDimensions(0, 100), /Bildabmessungen/);
  assert.throws(() => assertPhotoDimensions(100, NaN), /Bildabmessungen/);
  assert.throws(() => assertPhotoDimensions(1.5, 100), /Bildabmessungen/);
});

test("reads JPEG, PNG and WebP dimensions from bounded headers", async () => {
  assert.deepEqual(await inspectPhotoFile(fileFromBytes("image/png", pngFixture(1200, 900))), {
    type: "image/png", width: 1200, height: 900
  });
  assert.deepEqual(await inspectPhotoFile(fileFromBytes("image/jpeg", jpegFixture(4032, 3024))), {
    type: "image/jpeg", width: 4032, height: 3024
  });
  assert.deepEqual(await inspectPhotoFile(fileFromBytes("image/webp", webpFixture(1600, 1200))), {
    type: "image/webp", width: 1600, height: 1200
  });
});

test("rejects oversized image headers before invoking the browser decoder", async () => {
  const file = fileFromBytes("image/png", pngFixture(5000, 5000));
  let decodeCalls = 0;
  let canvasCalls = 0;
  await assert.rejects(
    preparePhotoBlob(file, {
      decodeImage: async () => { decodeCalls += 1; return { width: 5000, height: 5000 }; },
      createCanvas: () => { canvasCalls += 1; return {}; }
    }),
    /16 Megapixel/
  );
  assert.equal(decodeCalls, 0);
  assert.equal(canvasCalls, 0);
});

test("rejects unsupported, mismatched and oversized files before decoding", async () => {
  let reads = 0;
  const unsupported = {
    type: "image/heic",
    size: 10,
    async arrayBuffer() { reads += 1; return new ArrayBuffer(10); }
  };
  await assert.rejects(inspectPhotoFile(unsupported), /Nur JPEG/);
  const oversized = {
    type: "image/jpeg",
    size: MAX_PHOTO_BYTES + 1,
    async arrayBuffer() { reads += 1; return new ArrayBuffer(0); }
  };
  await assert.rejects(inspectPhotoFile(oversized), /8 MB/);
  await assert.rejects(inspectPhotoFile(fileFromBytes("image/jpeg", pngFixture(100, 100))), /JPEG-Bild ist ungültig/);
  assert.equal(reads, 0);
});

test("rejects animated PNG/WebP and multi-picture JPEG before decoding", async () => {
  await assert.rejects(inspectPhotoFile(fileFromBytes("image/png", pngFixture(100, 100, { animated: true }))), /Animierte PNG/);
  await assert.rejects(inspectPhotoFile(fileFromBytes("image/webp", webpFixture(100, 100, { animated: true }))), /Animierte WebP/);
  await assert.rejects(inspectPhotoFile(fileFromBytes("image/jpeg", jpegFixture(100, 100, { multiPicture: true }))), /Mehrbild-JPEG/);
});

test("rechecks decoded dimensions and closes a bitmap if decoder output differs", async () => {
  const file = fileFromBytes("image/png", pngFixture(100, 100));
  let closed = 0;
  let canvasCalls = 0;
  await assert.rejects(
    preparePhotoBlob(file, {
      decodeImage: async () => ({ width: 5000, height: 5000, close() { closed += 1; } }),
      createCanvas: () => { canvasCalls += 1; return {}; }
    }),
    /16 Megapixel/
  );
  assert.equal(closed, 1);
  assert.equal(canvasCalls, 0);
});

test("preflights before decoding, resizes locally and closes the bitmap", async () => {
  const file = fileFromBytes("image/png", pngFixture(4000, 3000));
  let closed = 0;
  let drawn = false;
  const canvas = {
    width: 0,
    height: 0,
    getContext() {
      return { drawImage() { drawn = true; } };
    },
    toBlob(callback, type) {
      callback(new Blob(["sanitized"], { type }));
    }
  };
  const blob = await preparePhotoBlob(file, {
    decodeImage: async () => ({ width: 4000, height: 3000, close() { closed += 1; } }),
    createCanvas: () => canvas
  });
  assert.equal(blob.type, "image/jpeg");
  assert.equal(canvas.width, 1600);
  assert.equal(canvas.height, 1200);
  assert.equal(drawn, true);
  assert.equal(closed, 1);
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
