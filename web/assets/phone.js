/* SPDX-License-Identifier: GPL-3.0-or-later · SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende */
'use strict';
/* Hornet3000 – Handy-Kamera. Nimmt Bild und Ton mit den Bordmitteln des Browsers auf (getUserMedia +
   MediaRecorder) und sendet sie fortlaufend an den eigenen Server. Keine App, keine Installation. */

const $ = s => document.querySelector(s);
const CHUNK_MS = 2000;

// Reihenfolge nach Verbreitung/Qualität: Android-Chrome liefert webm, iOS-Safari (ab 14.3) mp4.
// isTypeSupported() entscheidet je nach Gerät selbst, welcher Eintrag tatsächlich greift.
const MIME_CANDIDATES = [
  'video/webm;codecs=vp9,opus', 'video/webm;codecs=vp8,opus', 'video/webm',
  'video/mp4;codecs="avc1,mp4a"', 'video/mp4',
];

function pickMime() {
  if (typeof MediaRecorder === 'undefined') return null;
  for (const m of MIME_CANDIDATES) {
    try { if (MediaRecorder.isTypeSupported(m)) return m; } catch { /* älterer Browser kennt den Typ nicht */ }
  }
  return null;
}

function deviceLabel() {
  const ua = navigator.userAgent;
  if (/iPhone|iPad|iPod/.test(ua)) return 'iPhone/iPad (Safari)';
  if (/Android/.test(ua)) { const m = ua.match(/Android [\d.]+;\s*([^;)]+)/); return (m ? m[1].trim() : 'Android') + ' (Chrome)'; }
  return navigator.platform || 'Handy';
}

const S = { stream: null, recorder: null, ws: null, mime: null, facing: 'environment', wake: null,
            running: false, stopped: true, reconnectDelay: 1500, bytesSent: 0, chunksSent: 0, startTs: 0 };

function setBadge(state, text) {
  $('#dot').className = 'dot' + (state ? ' ' + state : '');
  $('#badge-text').textContent = text;
}
function showError(msg) {
  const e = $('#err'); e.textContent = msg; e.classList.remove('hidden');
}
function clearError() { $('#err').classList.add('hidden'); $('#err').textContent = ''; }

async function login() {
  const p = new URLSearchParams(location.search);
  const t = p.get('t');
  if (t) {
    try { await fetch('/api/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token: t }) }); }
    catch { /* unten als "nicht angemeldet" sichtbar */ }
    history.replaceState(null, '', location.pathname);
  }
  try {
    const r = await fetch('/api/session', { credentials: 'same-origin' });
    const j = await r.json();
    return !!j.authed;
  } catch { return false; }
}

async function requestWake() {
  try { S.wake = await navigator.wakeLock.request('screen'); } catch { /* z. B. iOS < 16.4 oder Akkusparmodus */ }
}
document.addEventListener('visibilitychange', async () => {
  if (S.running && document.visibilityState === 'visible' && (!S.wake || S.wake.released)) await requestWake();
});

function statConstraints() {
  return {
    video: { facingMode: { ideal: S.facing }, width: { ideal: 1280 }, height: { ideal: 720 }, frameRate: { ideal: 15, max: 20 } },
    audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false },
  };
}

async function openCamera() {
  if (S.stream) { S.stream.getTracks().forEach(t => t.stop()); }
  S.stream = await navigator.mediaDevices.getUserMedia(statConstraints());
  const video = $('#preview');
  video.srcObject = S.stream;
  video.classList.toggle('rear', S.facing === 'environment');
  const vt = S.stream.getVideoTracks()[0];
  const settings = vt ? vt.getSettings() : {};
  $('#codec-info').textContent = `${S.mime.split(';')[0]} · ${settings.width || '?'}×${settings.height || '?'} · ${Math.round(settings.frameRate || 0)} fps`;
}

function connectWs() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${proto}://${location.host}/ws/phone`);
  ws.binaryType = 'arraybuffer';
  S.ws = ws;
  ws.addEventListener('open', () => {
    ws.send(JSON.stringify({ mimeType: S.mime, device: deviceLabel() }));
    setBadge('ok', 'verbunden');
    clearError();
    S.reconnectDelay = 1500;
    startRecorder();
  });
  ws.addEventListener('message', ev => {
    try { const j = JSON.parse(ev.data); if (j.error) showError(j.error); } catch { /* keine JSON-Nachricht */ }
  });
  ws.addEventListener('close', ev => {
    setBadge('bad', 'getrennt');
    stopRecorderOnly();
    if (ev.code === 4401) { showError('Anmeldung abgelaufen – Seite neu laden.'); return; }
    if (ev.code === 4409) { showError('Die Kamera-Quelle ist auf dem Server nicht auf „Handy“ eingestellt.'); return; }
    scheduleReconnect();
  });
  ws.addEventListener('error', () => { try { ws.close(); } catch { /* close folgt über 'close' */ } });
}

function scheduleReconnect() {
  if (!S.running) return;
  setBadge('', `neuer Versuch in ${Math.round(S.reconnectDelay / 1000)} s …`);
  setTimeout(() => { if (S.running) connectWs(); }, S.reconnectDelay);
  S.reconnectDelay = Math.min(15000, S.reconnectDelay * 1.6);
}

function startRecorder() {
  if (!S.stream || S.ws?.readyState !== WebSocket.OPEN) return;
  const rec = new MediaRecorder(S.stream, { mimeType: S.mime, videoBitsPerSecond: 1_500_000, audioBitsPerSecond: 64_000 });
  S.recorder = rec;
  rec.ondataavailable = async e => {
    if (!e.data || !e.data.size || S.ws?.readyState !== WebSocket.OPEN) return;
    const buf = await e.data.arrayBuffer();
    try {
      S.ws.send(buf);
      S.bytesSent += buf.byteLength; S.chunksSent++;
      renderStats();
    } catch { /* Senden fehlgeschlagen – die nächste Chunk-Runde oder der Reconnect übernimmt */ }
  };
  rec.start(CHUNK_MS);
}

function stopRecorderOnly() {
  if (S.recorder && S.recorder.state !== 'inactive') { try { S.recorder.stop(); } catch { /* bereits beendet */ } }
  S.recorder = null;
}

function renderStats() {
  const secs = Math.max(1, (Date.now() - S.startTs) / 1000);
  const kbps = Math.round((S.bytesSent * 8) / secs / 1000);
  $('#stats').textContent = `${S.chunksSent} Stücke gesendet · ø ${kbps} kbit/s · seit ${Math.round(secs)} s`;
}

async function start() {
  clearError();
  S.mime = pickMime();
  if (!S.mime) { showError('Dieser Browser unterstützt keine Videoaufnahme (MediaRecorder fehlt). Bitte Safari bzw. Chrome aktuell halten.'); return; }
  if (!window.isSecureContext) { showError('Diese Seite läuft nicht über https – der Browser verweigert dann den Kamerazugriff. „Adresse der App“ in der Einrichtung auf https:// setzen.'); return; }
  try { await openCamera(); }
  catch (e) {
    const m = { NotAllowedError: 'Kamera-/Mikrofonzugriff wurde verweigert. In den Website-Einstellungen des Browsers erlauben und neu laden.',
               NotFoundError: 'Keine Kamera gefunden.', NotReadableError: 'Kamera wird bereits von einer anderen App benutzt.' }[e.name];
    showError(m || `Kamera konnte nicht gestartet werden (${e.name}).`); return;
  }
  S.running = true; S.stopped = false; S.startTs = Date.now(); S.bytesSent = 0; S.chunksSent = 0;
  $('#btn-start').classList.add('hidden'); $('#btn-stop').classList.remove('hidden'); $('#btn-flip').classList.remove('hidden');
  $('#precheck').classList.add('hidden');
  await requestWake();
  setBadge('', 'verbinde …');
  connectWs();
}

function stop() {
  S.running = false;
  if (S.ws) { try { S.ws.close(1000); } catch { /* egal, wird ohnehin verworfen */ } S.ws = null; }
  stopRecorderOnly();
  if (S.stream) { S.stream.getTracks().forEach(t => t.stop()); S.stream = null; }
  if (S.wake) { try { S.wake.release(); } catch { /* bereits freigegeben */ } S.wake = null; }
  setBadge('', 'beendet');
  $('#btn-start').classList.remove('hidden'); $('#btn-stop').classList.add('hidden'); $('#btn-flip').classList.add('hidden');
  $('#precheck').classList.remove('hidden');
  $('#codec-info').textContent = ''; $('#stats').textContent = '';
}

async function flip() {
  S.facing = S.facing === 'environment' ? 'user' : 'environment';
  stopRecorderOnly();
  try { await openCamera(); } catch (e) { showError(`Kamera konnte nicht gewechselt werden (${e.name}).`); return; }
  if (S.ws && S.ws.readyState === WebSocket.OPEN) startRecorder();
}

$('#btn-start').addEventListener('click', start);
$('#btn-stop').addEventListener('click', stop);
$('#btn-flip').addEventListener('click', flip);
window.addEventListener('pagehide', () => { if (S.running) stop(); });

(async () => {
  const authed = await login();
  if (!authed) {
    const msg = document.createElement('p'), b = document.createElement('b');
    b.textContent = 'Anmeldung fehlgeschlagen.';
    msg.append(b, ' Diese Seite bitte über den Link bzw. QR-Code aus der Einrichtung öffnen (Reiter „Einrichtung“ → „Handy als Kamera“).');
    $('#login').replaceChildren(msg);
    return;
  }
  $('#login').classList.add('hidden');
  $('#app').classList.remove('hidden');
  if (!navigator.mediaDevices?.getUserMedia) {
    showError('Dieser Browser unterstützt keinen Kamerazugriff über die Webseite.');
    $('#btn-start').setAttribute('disabled', '');
  }
})();
