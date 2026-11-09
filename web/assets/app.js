'use strict';
/* Hornet3000 Wächter – Oberfläche. Reines JavaScript, keine externen Abhängigkeiten. */

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
function el(tag, attrs = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === false || v == null) continue;
    if (k === 'class') n.className = v;
    else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v === true ? '' : v);
  }
  for (const k of kids.flat()) n.append(k instanceof Node ? k : document.createTextNode(String(k)));
  return n;
}

const DISPLAY = { vvel: 'Asiatische Hornisse', vcra: 'Europäische Hornisse', amel: 'Honigbiene', vespsp: 'Wespe', vzon: 'Klasse vzon' };
const TABS = ['live', 'alarme', 'funk', 'einrichtung', 'wissen'];
const S = { status: null, sound: localStorage.getItem('sound') === '1', audio: null, wake: null, es: null,
            unseen: 0, barAlert: null, tab: 'live', authed: false, titleTimer: null, setup: null };

/* ---------- Hilfen ---------- */
const fmtTime = ts => new Date(ts * 1000).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' });
const fmtClock = ts => new Date(ts * 1000).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
function ago(ts) {
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 60) return `vor ${Math.round(s)} s`;
  if (s < 3600) return `vor ${Math.round(s / 60)} Min.`;
  if (s < 86400) return `vor ${Math.round(s / 3600)} Std.`;
  return `vor ${Math.round(s / 86400)} Tg.`;
}
const pct = v => `${Math.round((v || 0) * 100)} %`;
function toast(msg, ms = 3800) {
  $$('.toast').forEach(t => t.remove());
  const t = el('div', { class: 'toast', role: 'status' }, msg);
  document.body.append(t);
  setTimeout(() => t.remove(), ms);
}
async function api(path, opts = {}) {
  const headers = opts.body ? { 'Content-Type': 'application/json' } : {};
  const r = await fetch(path, { credentials: 'same-origin', headers, ...opts });
  if (r.status === 401) { showLogin(); throw new Error('Anmeldung erforderlich'); }
  if (!r.ok) {
    let m = r.statusText;
    try { m = (await r.json()).detail || m; } catch { /* leer */ }
    throw new Error(m);
  }
  return r.json();
}

/* ---------- Anmeldung ---------- */
function showLogin() {
  S.authed = false;
  $$('.view').forEach(v => v.classList.remove('on'));
  $('#login').hidden = false;
  $('.tabs').hidden = true;
  setLive(false);
  if (S.es) { S.es.close(); S.es = null; }
}
$('#login-form').addEventListener('submit', async e => {
  e.preventDefault();
  const err = $('#login-err');
  err.hidden = true;
  try {
    await api('/api/login', { method: 'POST', body: JSON.stringify({ token: $('#token').value.trim() }) });
    $('#token').value = '';
    boot();
  } catch (x) { err.textContent = x.message === 'Anmeldung erforderlich' ? 'Zugangsschlüssel falsch.' : x.message; err.hidden = false; }
});
$('#btn-logout').addEventListener('click', async () => { await fetch('/api/logout', { method: 'POST' }); showLogin(); });

/* ---------- Routing ---------- */
function route() {
  if (!S.authed) return;
  const h = location.hash.slice(1);
  const m = h.match(/^alarm-(\d+)$/);
  const tab = m ? 'alarme' : h === 'kanaele' ? 'einrichtung' : TABS.includes(h) ? h : 'live';
  show(tab);
  if (m) openDetail(+m[1]);
}
function show(tab) {
  S.tab = tab;
  $$('.view').forEach(v => v.classList.toggle('on', v.id === `v-${tab}`));
  $$('nav.tabs a').forEach(a => { if (a.dataset.tab === tab) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
  setLive(tab === 'live' && !document.hidden);
  if (tab === 'alarme') { S.unseen = 0; renderBadge(); loadAlerts(); }
  if (tab === 'einrichtung') { loadSetup(); renderChannels(); refreshPushUi(); }
  if (tab === 'funk') { S.funkUnseen = 0; renderFunkBadge(); loadFunk(); }
  if (tab === 'wissen') loadKnowledge();
  window.scrollTo(0, 0);
}
window.addEventListener('hashchange', route);
document.addEventListener('visibilitychange', () => {
  setLive(S.tab === 'live' && !document.hidden);
  if (!document.hidden) { refreshStatus(); if (S.wantWake) requestWake(); }
});

/* ---------- Live-Bild ---------- */
function setLive(on) {
  const img = $('#live-img');
  if (on) {
    if (!img.getAttribute('src')) img.src = `/api/live.mjpg?t=${Date.now()}`;
  } else img.removeAttribute('src');
}
$('#live-img').addEventListener('load', () => { $('#live-empty').hidden = true; });
$('#live-img').addEventListener('error', () => {
  $('#live-empty').hidden = false;
  $('#live-img').removeAttribute('src');
  setTimeout(() => { if (S.tab === 'live' && !document.hidden && S.authed) setLive(true); }, 3000);
});

/* ---------- Status ---------- */
async function refreshStatus() {
  if (!S.authed) return;
  try {
    S.status = await api('/api/status');
    renderStatus(S.status);
  } catch { setConn(false, 'keine Verbindung'); }
}
function setConn(ok, txt) {
  $('#conn-dot').className = `dot ${ok ? 'ok' : 'bad'}`;
  $('#conn-txt').textContent = txt;
}
function renderStatus(st) {
  const cam = st.camera, det = st.detector;
  const alertSet = new Set(st.settings.alert_classes);
  const protSet = new Set(st.settings.protected_classes);
  const now = st.detections_now || [];
  const inEvent = !!st.event;
  const hero = $('#hero');
  let cls = '', title = 'Am Stock ist alles ruhig', sub = '';
  const lastSeen = Object.entries(st.last_seen || {}).sort((a, b) => b[1] - a[1])[0];
  if (cam.type === 'phone' && !cam.online) {
    cls = 'offline'; title = 'Warte auf das Handy';
    sub = cam.state === 'offline' ? (cam.error || 'Verbindung unterbrochen – Handy prüft selbst automatisch erneut.')
         : 'Noch nicht verbunden. QR-Code unter „Einrichtung“ scannen und auf dem Handy „Kamera starten“ tippen.';
  }
  else if (!cam.online) { cls = 'offline'; title = 'Kamera nicht erreichbar'; sub = cam.error || `Status: ${cam.state}`; }
  else if (!det.loaded) { cls = 'offline'; title = 'Keine Erkennung aktiv'; sub = det.error || 'Modell nicht geladen'; }
  else if (inEvent) {
    cls = 'alarm'; title = 'Asiatische Hornisse am Stock!';
    sub = `Bis zu ${st.event.max_count} Tier${st.event.max_count === 1 ? '' : 'e'} · seit ${fmtClock(st.event.first)} Uhr · zuletzt ${ago(st.event.last_hit)}`;
  } else if (st.muted) { cls = 'muted'; title = `Alarme stumm bis ${fmtClock(st.mute_until)} Uhr`; sub = 'Erkennungen werden gespeichert, aber nicht gemeldet.'; }
  else if (lastSeen) sub = `Zuletzt im Bild: ${lastSeen[0]} ${ago(lastSeen[1])}`;
  hero.className = `hero ${cls}`;
  $('#h-live').textContent = title;
  let info = `${cam.name} · ${cam.source || '—'} · Erkennung ${det.infer_ms || '—'} ms/Bild · Alarme in 24 h: ${st.alarms_24h}`;
  if (cam.type === 'phone') {
    info = cam.device ? `${cam.name} · Handy: ${cam.device} · Erkennung ${det.infer_ms || '—'} ms/Bild · Alarme in 24 h: ${st.alarms_24h}`
                      : `${cam.name} · wartet auf Verbindung vom Handy (QR-Code unter „Einrichtung“) · Alarme in 24 h: ${st.alarms_24h}`;
  }
  $('#hero-sub').textContent = sub ? `${sub}\n${info}` : info;
  $('#hero-sub').style.whiteSpace = 'pre-line';

  const chips = $('#chips');
  chips.replaceChildren(...now.map(d => el('span', { class: `chip2 ${alertSet.has(d.cls) ? 'alert' : protSet.has(d.cls) ? 'prot' : ''}` },
    `${DISPLAY[d.cls] || d.cls} ${pct(d.conf)}`)));

  $('#btn-unmute').hidden = !st.muted;
  $('#mute-sel').hidden = st.muted;
  setConn(cam.online && !!S.es, !st.configured ? 'nicht eingerichtet' : cam.online ? (S.es ? 'verbunden' : 'Live-Meldungen getrennt') : 'Kamera offline');
  if (S.tab === 'einrichtung') renderSystem();
}

/* ---------- Alarme ---------- */
const KIND = { new: '', update: 'Verstärkung', reminder: 'Erinnerung', test: 'Test' };
function deliverySummary(d) {
  if (!d) return 'Zustellung: läuft …';
  const parts = Object.entries(d).map(([ch, r]) => {
    const a = r.alarm; const ok = a ? a.ok : null;
    return `${{ telegram: 'Telegram', whatsapp: 'WhatsApp', sms: 'SMS', push: 'App' }[ch] || ch} ${ok === null ? '–' : ok ? '✓' : '✗'}`;
  });
  return parts.length ? parts.join(' · ') : 'kein Meldeweg eingerichtet';
}
function alertItem(a) {
  const tag = KIND[a.kind] ? el('span', { class: `tag ${a.kind === 'test' ? 'test' : ''}` }, KIND[a.kind]) : null;
  const muted = a.muted ? el('span', { class: 'tag' }, 'stumm') : null;
  const thumb = a.snapshot_url ? el('img', { src: a.snapshot_url, alt: '', loading: 'lazy' }) : el('div', { class: 'ph' });
  const btn = el('button', { class: 'item', type: 'button', onclick: () => { location.hash = `#alarm-${a.id}`; if (location.hash === `#alarm-${a.id}`) openDetail(a.id); } },
    thumb,
    el('div', {},
      el('div', { class: 'ttl' }, a.kind === 'test' ? 'Test-Alarm' : a.label || 'Alarm', tag, muted),
      el('div', { class: 'sub' }, `${fmtTime(a.ts)} · ${a.count || 1} Tier${(a.count || 1) === 1 ? '' : 'e'}${a.kind === 'test' ? '' : ' · ' + pct(a.conf)}`),
      el('div', { class: 'sub' }, deliverySummary(a.delivery) + (a.clip_url ? ' · Video mit Ton' : a.kind === 'test' || a.kind === 'new' ? ' · Video folgt …' : ''))));
  return el('li', {}, btn);
}
async function loadAlerts() {
  if (!S.authed) return;
  try {
    const { items } = await api('/api/alerts?limit=50');
    $('#alerts').replaceChildren(...items.map(alertItem));
    $('#alerts-empty').hidden = items.length > 0;
    $('#recent').replaceChildren(...items.slice(0, 4).map(alertItem));
    $('#recent-empty').hidden = items.length > 0;
  } catch { /* Verbindung fehlt */ }
}
function renderBadge() {
  const b = $('#badge');
  b.hidden = S.unseen === 0;
  b.textContent = S.unseen;
  if (S.unseen === 0 && S.titleTimer) { clearInterval(S.titleTimer); S.titleTimer = null; document.title = 'Hornet3000 Wächter'; }
}

async function openDetail(id) {
  let a;
  try { a = await api(`/api/alerts/${id}`); } catch (e) { toast(e.message); return; }
  const dlg = $('#detail');
  $('#d-title').textContent = a.kind === 'test' ? 'Test-Alarm' : `${a.label || 'Alarm'}${KIND[a.kind] ? ' – ' + KIND[a.kind] : ''}`;
  $('#d-sub').textContent = `${a.camera || ''} · ${fmtTime(a.ts)}`;
  const img = $('#d-img');
  img.hidden = !a.snapshot_url;
  if (a.snapshot_url) img.src = a.snapshot_url;
  const vw = $('#d-video-wrap');
  vw.replaceChildren();
  const showClip = url => vw.replaceChildren(el('video', { controls: true, playsinline: true, preload: 'metadata', src: url, 'aria-label': 'Video mit Ton' }),
    el('p', { class: 'muted small' }, 'Video mit Ton – Lautstärke am Gerät prüfen.'));
  if (a.clip_url) showClip(a.clip_url);
  else if (a.kind === 'new' || a.kind === 'test') {
    vw.replaceChildren(el('p', { class: 'muted' }, 'Das Video mit Ton wird noch erstellt …'));
    let tries = 0;
    const iv = setInterval(async () => {
      if (!dlg.open || ++tries > 20) return clearInterval(iv);
      try { const n = await api(`/api/alerts/${id}`); if (n.clip_url) { clearInterval(iv); showClip(n.clip_url); } } catch { clearInterval(iv); }
    }, 3000);
  }
  const kv = $('#d-kv');
  const rows = [];
  if (a.kind !== 'test') rows.push(['Erkennung', `${a.count || 1} Tier${(a.count || 1) === 1 ? '' : 'e'}, Sicherheit ${pct(a.conf)}`]);
  const v = a.verify;
  if (v && v.provider !== 'none') {
    const art = { velutina: 'Asiatische Hornisse', crabro: 'Europäische Hornisse (geschützt)', andere_wespe: 'andere Wespe', biene: 'Biene', anderes_insekt: 'anderes Insekt', unklar: 'unklar', fehler: 'Prüfung nicht möglich' }[v.art] || v.art;
    rows.push(['KI-Prüfung', `${art}${v.sicherheit ? ' (' + pct(v.sicherheit) + ')' : ''}${v.merkmale ? ' – ' + v.merkmale : ''}${v.error ? ' – ' + v.error : ''}`]);
  }
  if (a.muted) rows.push(['Hinweis', 'Alarme waren stumm geschaltet – nichts wurde gesendet.']);
  const dl = a.delivery || {};
  for (const [ch, r] of Object.entries(dl)) {
    const name = { telegram: 'Telegram', whatsapp: 'WhatsApp', sms: 'SMS', push: 'App-Meldung' }[ch] || ch;
    const cell = el('span', {});
    for (const [ph, lab] of [['alarm', 'Foto/Text'], ['clip', 'Video']]) {
      if (!r[ph]) continue;
      cell.append(el('span', { class: r[ph].ok ? 'ok-t' : 'bad-t' }, `${lab}: ${r[ph].ok ? 'gesendet' : 'Fehler'}`),
        el('span', { class: 'muted small' }, ` (${r[ph].detail})`), el('br'));
    }
    rows.push([name, cell]);
  }
  kv.replaceChildren(...rows.flatMap(([k, val]) => [el('dt', {}, k), el('dd', {}, val)]));
  const copy = $('#d-copy');
  copy.hidden = !a.share_url;
  copy.onclick = async () => { try { await navigator.clipboard.writeText(a.share_url); toast('Link kopiert – gültig 48 Stunden.'); } catch { toast(a.share_url, 9000); } };
  if (!dlg.open) dlg.showModal();
}
$('#d-close').addEventListener('click', () => $('#detail').close());
$('#detail').addEventListener('close', () => {
  $('#d-video-wrap').replaceChildren();
  if (/^#alarm-/.test(location.hash)) history.replaceState(null, '', '#alarme');
});

/* ---------- Live-Ereignisse (SSE) ---------- */
function connectEvents() {
  if (S.es) S.es.close();
  const es = new EventSource('/api/events');
  S.es = es;
  es.addEventListener('open', () => setConn(!!S.status?.camera.online, S.status?.camera.online ? 'verbunden' : 'Kamera offline'));
  es.addEventListener('error', () => setConn(false, 'Live-Meldungen getrennt'));
  es.addEventListener('alert', e => onAlert(JSON.parse(e.data)));
  for (const ev of ['clip', 'delivery']) es.addEventListener(ev, () => { loadAlerts(); });
  es.addEventListener('status', () => refreshStatus());
  es.addEventListener('mesh', e => onMesh(JSON.parse(e.data)));
  es.addEventListener('mesh_notice', e => { const d = JSON.parse(e.data); toast(`Funknetz: Station „${d.station}“ wird begrenzt (${d.reason}).`, 7000); if (S.tab === 'funk') loadFunk(); });
}
function renderFunkBadge() {
  const b = $('#badge-funk');
  b.hidden = !S.funkUnseen;
  b.textContent = S.funkUnseen || 0;
}
function onMesh(m) {
  if (m.typ === 'A' || m.typ === 'U') {
    const where = m.km != null ? `, ca. ${Math.round(m.km)} km entfernt` : '';
    toast(`📡 ${m.station} meldet Asiatische Hornisse (${m.count} Tier${m.count === 1 ? '' : 'e'}${where}) – ungeprüfte Funkmeldung`, 12000);
    if (navigator.vibrate) navigator.vibrate([200, 100, 200]);
  }
  if (S.tab === 'funk') loadFunk(); else if (m.typ !== 'R') { S.funkUnseen = (S.funkUnseen || 0) + 1; renderFunkBadge(); }
}
function onAlert(a) {
  loadAlerts();
  refreshStatus();
  if (a.muted) { toast('Stummgeschaltete Erkennung gespeichert.'); return; }
  const isTest = a.kind === 'test';
  const title = isTest ? 'Test-Alarm' : a.kind === 'update' ? `Verstärkung: jetzt ${a.count} Tiere` : a.kind === 'reminder' ? 'Aktivität dauert an' : 'Asiatische Hornisse erkannt!';
  $('#ab-title').textContent = title;
  $('#ab-sub').textContent = `${a.camera} · ${fmtTime(a.ts)}${isTest ? '' : ' · Sicherheit ' + pct(a.conf)}`;
  $('#ab-img').src = a.snapshot + `?t=${Date.now()}`;
  $('#alarmbar').hidden = false;
  S.barAlert = a;
  if (!isTest || S.sound) siren(isTest ? 2 : 6);
  if (navigator.vibrate) navigator.vibrate([300, 120, 300, 120, 600]);
  if (S.tab !== 'alarme') { S.unseen++; renderBadge(); }
  if (!isTest && !S.titleTimer) {
    let on = false;
    S.titleTimer = setInterval(() => { on = !on; document.title = on ? '⚠ HORNISSE am Stock!' : 'Hornet3000 Wächter'; }, 900);
  }
}
$('#ab-open').addEventListener('click', () => { if (S.barAlert) { location.hash = `#alarm-${S.barAlert.id}`; if (location.hash === `#alarm-${S.barAlert.id}`) route(); } });
$('#ab-close').addEventListener('click', () => {
  $('#alarmbar').hidden = true;
  if (S.titleTimer) { clearInterval(S.titleTimer); S.titleTimer = null; document.title = 'Hornet3000 Wächter'; }
});

/* ---------- Alarmton, Bildschirm ---------- */
function armAudio() {
  if (!S.audio) S.audio = new (window.AudioContext || window.webkitAudioContext)();
  return S.audio.resume();
}
function siren(seconds = 5) {
  if (!S.sound || !S.audio || S.audio.state !== 'running') return;
  const ctx = S.audio, t0 = ctx.currentTime;
  const o = ctx.createOscillator(), g = ctx.createGain();
  o.type = 'square'; o.connect(g); g.connect(ctx.destination);
  g.gain.setValueAtTime(0.0001, t0);
  g.gain.exponentialRampToValueAtTime(0.18, t0 + 0.05);
  for (let i = 0; i < seconds * 2; i++) o.frequency.setValueAtTime(i % 2 ? 740 : 990, t0 + i * 0.5);
  g.gain.setValueAtTime(0.18, t0 + seconds - 0.15);
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + seconds);
  o.start(t0); o.stop(t0 + seconds + 0.05);
}
function renderSound() {
  const b = $('#btn-sound');
  b.setAttribute('aria-pressed', String(S.sound));
  b.textContent = `Alarmton: ${S.sound ? 'an' : 'aus'}`;
}
$('#btn-sound').addEventListener('click', async () => {
  S.sound = !S.sound;
  localStorage.setItem('sound', S.sound ? '1' : '0');
  if (S.sound) { await armAudio(); siren(1); toast('Alarmton an – die Seite muss dafür geöffnet bleiben.'); }
  renderSound();
});
document.addEventListener('click', () => { if (S.sound && !S.audio) armAudio(); }, { once: false });

async function requestWake() {
  try { S.wake = await navigator.wakeLock.request('screen'); S.wake.addEventListener('release', () => { S.wake = null; }); } catch { /* nicht erlaubt */ }
}
const wakeBtn = $('#btn-wake');
if (!('wakeLock' in navigator)) wakeBtn.hidden = true;
wakeBtn.addEventListener('click', async () => {
  S.wantWake = !S.wantWake;
  wakeBtn.setAttribute('aria-pressed', String(S.wantWake));
  if (S.wantWake) await requestWake(); else if (S.wake) { S.wake.release(); S.wake = null; }
});

/* ---------- Steuerung ---------- */
$('#mute-sel').addEventListener('change', async e => {
  const m = +e.target.value;
  e.target.value = '';
  if (!m) return;
  await api('/api/mute', { method: 'POST', body: JSON.stringify({ minutes: m }) });
  toast(`Alarme für ${m >= 60 ? m / 60 + ' Std.' : m + ' Min.'} stumm.`);
  refreshStatus();
});
$('#btn-unmute').addEventListener('click', async () => { await api('/api/unmute', { method: 'POST' }); refreshStatus(); });
$('#btn-test').addEventListener('click', async e => {
  e.target.disabled = true;
  try { const r = await api('/api/test-alert', { method: 'POST' }); toast(r.detail, 6000); } catch (x) { toast(x.message); }
  setTimeout(() => { e.target.disabled = false; }, 5000);
});

/* ---------- Meldewege ---------- */
function renderChannels() {
  const st = S.status;
  if (!st) return;
  $('#channels').replaceChildren(...st.channels.filter(c => c.name !== 'push').map(c => el('div', { class: 'chan' },
    el('span', { class: `dot ${c.configured ? 'ok' : ''}` }),
    el('b', {}, c.label),
    c.configured ? el('button', { onclick: async ev => {
      ev.target.disabled = true;
      try { const r = await api(`/api/channels/${c.name}/test`, { method: 'POST' }); toast(r.ok ? `${c.label}: Testnachricht gesendet.` : `${c.label}: ${r.detail}`, 7000); }
      catch (x) { toast(x.message); }
      ev.target.disabled = false;
    } }, 'Testnachricht') : el('span'),
    el('span', { class: 'muted small', style: 'grid-column: 2 / 4' }, c.configured ? c.detail + (c.text_only ? ' (nur Text)' : '') : 'nicht eingerichtet (oben unter Einrichtung)'))));
  const t = st.tuning;
  $('#t-conf').value = t.conf_alert; $('#v-conf').textContent = pct(t.conf_alert);
  $('#t-hits').value = t.confirm_hits; $('#v-hits').textContent = t.confirm_hits;
  $('#t-gap').value = String([120, 300, 900, 1800].reduce((p, c) => Math.abs(c - t.event_gap_s) < Math.abs(p - t.event_gap_s) ? c : p));
  renderSystem();
}
function renderSystem() {
  const st = S.status;
  if (!st) return;
  const rows = [
    ['Version', st.version], ['Kamera', `${st.camera.name} (${st.camera.online ? 'online' : 'offline'}, ${st.camera.source || '—'})`],
    ['Erkennung', st.detector.loaded ? `${st.detector.model} · ${st.detector.provider} · ${st.detector.infer_ms} ms/Bild` : `nicht aktiv: ${st.detector.error}`],
    ['Video mit Ton', st.clip_enabled ? `an (${st.settings.clip_pre_s} s vor bis ${st.settings.clip_post_s} s nach der Erkennung)` : 'aus'],
    ['KI-Prüfung', { none: 'aus', anthropic: 'Claude', ollama: 'Ollama (lokal)' }[st.verify] || st.verify],
    ['Sichtungen (GBIF)', st.apiary_configured ? 'Standort gesetzt' : 'Standort fehlt (Einrichtung)'],
    ['Laufzeit', `${Math.floor(st.uptime_s / 3600)} Std. ${Math.floor(st.uptime_s / 60) % 60} Min.`],
  ];
  $('#sys').replaceChildren(...rows.flatMap(([k, v]) => [el('dt', {}, k), el('dd', {}, v)]));
}
$('#t-conf').addEventListener('input', e => { $('#v-conf').textContent = pct(+e.target.value); });
$('#t-hits').addEventListener('input', e => { $('#v-hits').textContent = e.target.value; });
$('#btn-tune').addEventListener('click', async () => {
  await api('/api/tuning', { method: 'PUT', body: JSON.stringify({ conf_alert: +$('#t-conf').value, confirm_hits: +$('#t-hits').value, event_gap_s: +$('#t-gap').value }) });
  toast('Gespeichert.'); refreshStatus();
});

/* ---------- Web-Push ---------- */
const b64ToU8 = s => Uint8Array.from(atob(s.replace(/-/g, '+').replace(/_/g, '/').padEnd(Math.ceil(s.length / 4) * 4, '=')), c => c.charCodeAt(0));
async function refreshPushUi() {
  const info = $('#push-info'), btn = $('#btn-push');
  btn.hidden = true;
  if (!window.isSecureContext) { info.textContent = 'Geräte-Benachrichtigungen brauchen eine sichere Adresse (HTTPS oder localhost). Telegram, WhatsApp und SMS funktionieren trotzdem.'; return; }
  if (!('serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window)) {
    info.textContent = /iPhone|iPad/.test(navigator.userAgent) ? 'Auf dem iPhone: in Safari „Zum Home-Bildschirm“ wählen und die App von dort öffnen (ab iOS 16.4).' : 'Dieser Browser unterstützt keine Push-Benachrichtigungen.';
    return;
  }
  if (!S.status?.webpush) { info.textContent = 'Für Geräte-Benachrichtigungen fehlt eine Kontakt-E-Mail (oben unter „Adresse und Standort“).'; return; }
  if (Notification.permission === 'denied') { info.textContent = 'Benachrichtigungen sind im Browser blockiert. In den Website-Einstellungen wieder erlauben.'; return; }
  const reg = await navigator.serviceWorker.ready;
  const sub = await reg.pushManager.getSubscription();
  btn.hidden = false;
  if (sub) { info.textContent = 'Dieses Gerät erhält Alarme als Benachrichtigung – auch wenn die App geschlossen ist.'; btn.textContent = 'Auf diesem Gerät ausschalten'; btn.className = ''; btn.onclick = async () => { await api('/api/push/unsubscribe', { method: 'POST', body: JSON.stringify({ endpoint: sub.endpoint }) }); await sub.unsubscribe(); refreshPushUi(); }; }
  else { info.textContent = 'Erhalte Alarme mit Foto als Benachrichtigung auf diesem Gerät.'; btn.textContent = 'Auf diesem Gerät aktivieren'; btn.className = 'primary';
    btn.onclick = async () => {
      try {
        if (await Notification.requestPermission() !== 'granted') { toast('Ohne Erlaubnis keine Benachrichtigungen.'); return; }
        const { key } = await api('/api/push/key');
        const s = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToU8(key) });
        await api('/api/push/subscribe', { method: 'POST', body: JSON.stringify(s) });
        toast('Aktiviert. Teste es mit „Testnachricht“ unten.');
      } catch (x) { toast(`Aktivieren fehlgeschlagen: ${x.message}`, 7000); }
      refreshPushUi();
    }; }
}

/* ---------- Wissen ---------- */
let knowledgeLoaded = false;
async function loadKnowledge() {
  if (!knowledgeLoaded) {
    try { $('#knowledge').innerHTML = await (await fetch('/assets/knowledge.html')).text(); knowledgeLoaded = true; }
    catch { $('#knowledge').textContent = 'Wissensseite nicht verfügbar (offline?).'; }
  }
  try {
    const s = await api('/api/sightings');
    const box = $('#sightings');
    if (!s.configured) { box.replaceChildren(el('p', { class: 'muted' }, 'Standort fehlt: unter „Einrichtung“ den Standort des Bienenstands eintragen, dann erscheinen hier gemeldete Sichtungen im Umkreis.')); return; }
    if (s.error) { box.replaceChildren(el('p', { class: 'bad-t' }, s.error)); return; }
    box.replaceChildren(
      el('p', { class: 'muted small' }, `${s.total} Meldungen im Umkreis von ${s.radius_km} km (Vorjahr und aktuelles Jahr, Quelle GBIF)${s.offline ? ' – Offline-Stand' : ''}.`),
      s.items.length ? el('ul', {}, s.items.slice(0, 15).map(i => el('li', {}, `${i.date || 'ohne Datum'} · ${i.km} km · ${i.place || 'Ort unbekannt'} `,
        /^https:\/\/www\.gbif\.org\//.test(i.url) ? el('a', { href: i.url, target: '_blank', rel: 'noopener' }, 'Eintrag') : ''))) : el('p', {}, 'Keine Meldungen im Umkreis – das heißt nicht, dass keine Tiere da sind: nicht jede Sichtung wird gemeldet.'));
  } catch { /* Anmeldung/Verbindung */ }
}


/* ---------- Funknetz ---------- */
const MESH_TYP = { A: 'Sichtung', U: 'Verstärkung', T: 'Test', R: 'Quittung' };
const MESH_STATUS = { ok: 'angenommen', queued: 'wartet', sent: 'gesendet', failed: 'fehlgeschlagen', expired: 'abgelaufen', limited: 'begrenzt' };
const WAY_NAME = { lora: 'LoRa (MeshCore)', freenet: 'Freenet (River)' };
function meshRow(r) {
  const dir = r.direction === 'in' ? '⬇ empfangen' : '⬆ gesendet';
  const typ = MESH_TYP[r.typ] || (r.status === 'limited' ? 'Begrenzung' : '–');
  const bits = [];
  if (r.typ === 'A' || r.typ === 'U') bits.push(`${r.count} Tier${r.count === 1 ? '' : 'e'}`, `Sicherheit ${pct(r.conf)}`);
  if (r.lat != null) bits.push(`Position ${r.lat.toFixed(2)}, ${r.lon.toFixed(2)}`);
  if (r.note) bits.push(r.note);
  if (r.direction === 'out' && r.acks != null) bits.push(r.acks ? `${r.acks} Quittung${r.acks === 1 ? '' : 'en'}` : 'keine Quittung');
  const via = (r.via || '').split(',').filter(Boolean).map(v => WAY_NAME[v] || v).join(' + ');
  return el('li', { class: `mesh-item ${r.direction}${r.status === 'limited' || r.status === 'failed' ? ' bad' : ''}` },
    el('div', { class: 'ttl' }, `${typ} · ${r.station || '–'}`),
    el('div', { class: 'sub' }, `${dir} · ${fmtTime(r.ts)} · ${via} · ${MESH_STATUS[r.status] || r.status || ''}`),
    bits.length ? el('div', { class: 'sub' }, bits.join(' · ')) : '');
}
async function loadFunk() {
  let st;
  try { st = await api('/api/mesh'); } catch { return; }
  $('#funk-off').hidden = st.enabled;
  $('#btn-funk-test').disabled = !st.enabled;
  const ways = $('#funk-ways');
  const probs = (st.problems || []).map(p => el('p', { class: 'warn' }, `⚠ ${p}`));
  ways.replaceChildren(el('h3', {}, `Station „${st.station}“`),
    ...st.transports.map(t => el('div', { class: 'row-way' },
      el('span', { class: 'dot ' + (t.online ? 'ok' : 'bad') }), ' ', el('b', {}, t.label), ' – ',
      t.online ? 'verbunden' : 'nicht verbunden', t.detail ? el('span', { class: 'muted small' }, ` (${t.detail})`) : '',
      el('div', { class: 'muted small' }, `empfangen ${t.rx ?? 0} · gesendet ${t.tx ?? 0}` +
        (t.last_rx ? ` · zuletzt empfangen ${ago(t.last_rx)}` : '') +
        (t.duty_budget_s ? ` · Sendezeit ${t.duty_used_s} von ${t.duty_budget_s} s pro Stunde` : '')))),
    ...probs,
    el('p', { class: 'muted small' }, `Warteschlange: ${st.queue} · angenommen ${st.counters.accepted} · doppelt ${st.counters.dup} · begrenzt ${st.counters.limited} · verworfen ${st.counters.rejected}`));
  const log = $('#funk-log');
  log.replaceChildren(...st.messages.map(meshRow));
  $('#funk-log-empty').hidden = st.messages.length > 0;
  $('#funk-stations').replaceChildren(...st.stations.map(s => el('li', {}, `${s.station} – ${s.n} Meldung${s.n === 1 ? '' : 'en'}, zuletzt ${ago(s.last)}`)));
}
$('#btn-funk-test').addEventListener('click', async e => {
  e.target.disabled = true;
  try { await api('/api/mesh/test', { method: 'POST' }); $('#funk-test-note').textContent = 'Test in der Warteschlange – Quittungen anderer Stationen erscheinen im Protokoll.'; setTimeout(loadFunk, 1500); }
  catch (x) { toast(x.message, 6000); }
  e.target.disabled = false;
});

/* ---------- Einrichtung ---------- */
const CLOUD = ['WHATSAPP_PROVIDER', 'cloud'], CMB = ['WHATSAPP_PROVIDER', 'callmebot'];
const ANTH = ['VERIFY_PROVIDER', 'anthropic'], OLL = ['VERIFY_PROVIDER', 'ollama'];
const SETUP = [
  { title: 'Kamera', extra: 'camera',
    help: 'Netzwerkkamera (z. B. Reolink): rtsp://Benutzer:Passwort@192.168.x.x:554/h264Preview_01_main. Sonderzeichen im Passwort URL-kodieren (@ = %40). Webcam am PC: „Webcams suchen“. Auch der Pfad einer Videodatei geht.',
    fields: [
      { k: 'CAMERA_NAME', label: 'Name des Bienenstands' },
      { k: 'CAMERA_SOURCE', label: 'Kamera-Quelle' },
      { k: 'CAMERA_AUDIO_DEVICE', label: 'Mikrofon (nur bei Webcams; Netzwerkkameras liefern den Ton selbst)' },
    ] },
  { title: 'Telegram', extra: 'telegram',
    help: 'Kostenlos, mit Foto und Video samt Ton. So geht es: 1) In Telegram @BotFather öffnen, /newbot senden und den Token kopieren. 2) Token hier einfügen. 3) Deinem neuen Bot /start schreiben. 4) „Bot prüfen und Chats suchen“ drücken und deinen Chat übernehmen.',
    fields: [
      { k: 'TELEGRAM_BOT_TOKEN', label: 'Bot-Token', secret: true },
      { k: 'TELEGRAM_CHAT_IDS', label: 'Chat-IDs (mehrere durch Komma; Gruppen haben negative Nummern)' },
    ] },
  { title: 'WhatsApp',
    help: 'Foto und Video gehen nur über die offizielle Meta-Cloud-API (Entwicklerkonto mit WhatsApp-Produkt nötig). Sie kommen an, wenn du dem Absender in den letzten 24 Stunden geschrieben hast; sonst geht nur eine genehmigte Textvorlage. CallMeBot ist kostenlos, sendet aber nur Text.',
    fields: [
      { k: 'WHATSAPP_PROVIDER', label: 'Anbieter', type: 'select', def: 'none', options: [['none', 'nicht nutzen'], ['cloud', 'Meta Cloud-API (Foto und Video)'], ['callmebot', 'CallMeBot (nur Text)']] },
      { k: 'WHATSAPP_TOKEN', label: 'Zugriffstoken (Meta)', secret: true, show: CLOUD },
      { k: 'WHATSAPP_PHONE_ID', label: 'Telefonnummer-ID (Meta)', show: CLOUD },
      { k: 'WHATSAPP_TO', label: 'Empfänger mit Landesvorwahl, z. B. +49…', show: CLOUD },
      { k: 'WHATSAPP_TEMPLATE', label: 'Name der genehmigten Vorlage mit einer Variable (optional)', show: CLOUD },
      { k: 'CALLMEBOT_PHONE', label: 'Deine Nummer mit Landesvorwahl', show: CMB },
      { k: 'CALLMEBOT_APIKEY', label: 'CallMeBot-Schlüssel', secret: true, show: CMB },
    ] },
  { title: 'SMS über dein Android-Handy',
    help: 'Installiere auf einem Android-Handy die App „SMS Gateway for Android“ und schalte den lokalen Server ein. Adresse, Benutzer und Passwort zeigt die App. PC und Handy müssen im selben WLAN sein. Es fallen nur die Kosten deines Mobilfunktarifs an.',
    fields: [
      { k: 'SMS_URL', label: 'Adresse des Handys (http://…:8080)' },
      { k: 'SMS_USER', label: 'Benutzer' },
      { k: 'SMS_PASSWORD', label: 'Passwort', secret: true },
      { k: 'SMS_TO', label: 'Empfänger mit Landesvorwahl (mehrere durch Komma)' },
      { k: 'SMS_MMS', label: 'Foto als MMS mitschicken', type: 'bool', def: false },
    ] },
  { title: 'Adresse und Standort', extra: 'geo',
    help: 'Die Adresse, unter der du die App vom Handy erreichst, wird als Link in die Nachrichten eingefügt (Foto und Video ohne Anmeldung, 48 Stunden gültig). App-Installation und Geräte-Benachrichtigungen brauchen eine https-Adresse.',
    fields: [
      { k: 'PUBLIC_URL', label: 'Adresse der App (z. B. https://… oder http://192.168.x.x:8080)' },
      { k: 'WEBPUSH_CONTACT', label: 'Kontakt-E-Mail (für Geräte-Benachrichtigungen erforderlich)' },
      { k: 'APIARY_LAT', label: 'Breitengrad des Bienenstands (Dezimalgrad, z. B. 51.05)' },
      { k: 'APIARY_LON', label: 'Längengrad des Bienenstands (z. B. 7.10)' },
      { k: 'SIGHTINGS_RADIUS_KM', label: 'Umkreis für gemeldete Sichtungen (km)' },
    ] },
  { title: 'Funknetz – Allgemein', extra: 'mesh',
    help: 'Die Stationen warnen sich gegenseitig, sobald eine Asiatische Hornisse erkannt wird. Mindestens ein Weg (LoRa oder Freenet) muss unten eingeschaltet sein. Ohne Haken bei „Standort mitsenden“ wird keine Position verschickt.',
    fields: [
      { k: 'MESH_STATION', label: 'Name dieser Station im Funknetz (leer = Name des Bienenstands; höchstens 24 Zeichen, ohne | und @)' },
      { k: 'MESH_SHARE_POSITION', label: 'Standort auf etwa 1 km gerundet mitsenden (Breiten-/Längengrad unter „Adresse und Standort“ nötig)', type: 'bool', def: false },
      { k: 'MESH_FORWARD', label: 'Meldungen anderer Stationen an Telegram/WhatsApp/SMS weiterreichen', type: 'bool', def: true },
      { k: 'MESH_ACK', label: 'Empfang von Meldungen anderer Stationen quittieren', type: 'bool', def: true },
      { k: 'MESH_TRUSTED', label: 'Vertraute Stationen (Namen durch Komma) – sie sind von Anfang an „bekannt“ und werden großzügiger zugelassen' },
    ] },
  { title: 'Funknetz – LoRa (MeshCore-Funkgerät)', extra: 'lora',
    help: 'Funkgerät mit MeshCore-Firmware (Companion-Modus) per USB anschließen, z. B. Heltec V3, LilyGO T-Beam, RAK4631. Alle Stationen brauchen denselben Kanalnamen und Kanalschlüssel (32 Hexzeichen) – wer den Schlüssel kennt, kann in eurem Namen melden: nur an Beteiligte weitergeben. Kanal 0 ist der öffentliche MeshCore-Kanal und wird nie benutzt.',
    fields: [
      { k: 'MESH_LORA_ENABLED', label: 'LoRa einschalten', type: 'bool', def: false },
      { k: 'MESH_LORA_PORT', label: 'Anschluss des Funkgeräts (z. B. /dev/ttyUSB0 oder COM3; leer oder „auto“ = automatisch suchen)' },
      { k: 'MESH_LORA_CHANNEL_IDX', label: 'Kanalplatz am Gerät (1 bis 7; leer = 1)' },
      { k: 'MESH_LORA_CHANNEL_NAME', label: 'Kanalname (leer = hornet3000)' },
      { k: 'MESH_LORA_CHANNEL_KEY', label: 'Kanalschlüssel, 32 Hexzeichen (wird am Gerät eingerichtet)', secret: true },
      { k: 'MESH_LORA_DUTY', label: 'Erlaubter Sendeanteil (leer = 0,01 = 1 %; im Teilband 869,4–869,65 MHz sind bis 10 % erlaubt)' },
    ] },
  { title: 'Funknetz – Freenet (River-Raum)', extra: 'freenet',
    help: 'Braucht einen laufenden Freenet-Knoten auf diesem Rechner (freenet.org) und das Programm „riverctl“. Lege einen privaten Raum an (riverctl room create --private) oder nimm eine Einladung an; den Raum-Schlüssel zeigt „riverctl room list“. Freenet ist noch jung (Alpha) – nutze es als zweiten Weg neben LoRa.',
    fields: [
      { k: 'MESH_FREENET_ENABLED', label: 'Freenet einschalten', type: 'bool', def: false },
      { k: 'MESH_FREENET_ROOM', label: 'Raum-Schlüssel (Room Owner VK)' },
      { k: 'MESH_FREENET_RIVERCTL', label: 'Pfad zu riverctl (leer = im Suchpfad)' },
      { k: 'MESH_FREENET_NODE', label: 'Freenet-Knoten (leer = ws://127.0.0.1:7509)' },
    ] },
  { title: 'Zweite Prüfung durch Bild-KI (optional)',
    help: 'Ordnet jeden Alarm zusätzlich ein (bestätigt, widerspricht, unklar) und schickt die Einschätzung mit. Sie unterdrückt nie einen Alarm.',
    fields: [
      { k: 'VERIFY_PROVIDER', label: 'Anbieter', type: 'select', def: 'auto', options: [['auto', 'automatisch (Claude, sobald ein Schlüssel eingetragen ist)'], ['none', 'aus'], ['anthropic', 'Claude (Anthropic)'], ['ollama', 'Ollama (lokal)']] },
      { k: 'ANTHROPIC_API_KEY', label: 'Anthropic-API-Schlüssel', secret: true, show: ANTH },
      { k: 'VERIFY_MODEL', label: 'Modell (leer = claude-sonnet-5)', show: ANTH },
      { k: 'OLLAMA_URL', label: 'Ollama-Adresse (leer = http://127.0.0.1:11434)', show: OLL },
      { k: 'OLLAMA_MODEL', label: 'Ollama-Modell mit Bildverständnis (leer = qwen2.5vl:7b)', show: OLL },
    ] },
  { title: 'Video und Speicher',
    fields: [
      { k: 'CLIP_ENABLED', label: 'Video mit Ton bei Alarm aufnehmen', type: 'bool', def: true },
      { k: 'CLIP_PRE_S', label: 'Sekunden Vorlauf (leer = 6)' },
      { k: 'CLIP_POST_S', label: 'Sekunden Nachlauf (leer = 8)' },
      { k: 'DETECT_FPS', label: 'Bilder pro Sekunde für die Erkennung (leer = 3; bei langsamem Rechner 1 bis 2)' },
      { k: 'RETENTION_DAYS', label: 'Alarme und Videos löschen nach Tagen (leer = 90)' },
    ] },
];

function applyShow() {
  for (const sec of SETUP) for (const f of sec.fields) {
    if (!f.show) continue;
    const ctl = $('#s-' + f.show[0]);
    $(`[data-k="${f.k}"]`).hidden = !ctl || ctl.value !== f.show[1];
  }
}
function fieldEl(f) {
  const id = 's-' + f.k;
  const raw = S.setup.values[f.k] ?? '';
  let input, note = null;
  if (f.type === 'bool') {
    input = el('input', { type: 'checkbox', id });
    input.checked = raw === '' ? f.def === true : ['true', '1', 'ja'].includes(String(raw).toLowerCase());
    return el('label', { class: 'f chk', 'data-k': f.k }, input, ' ', f.label);
  }
  if (f.type === 'select') {
    input = el('select', { id, onchange: applyShow }, f.options.map(([v, l]) => el('option', { value: v }, l)));
    input.value = raw || f.def;
  } else {
    input = el('input', { type: f.secret ? 'password' : 'text', id, autocomplete: 'off', spellcheck: 'false' });
    if (!f.secret) input.value = raw;
  }
  if (f.secret) {
    const isSet = !!S.setup.secrets[f.k];
    note = isSet ? el('span', { class: 'muted small' }, 'Gespeichert. Feld leer lassen, um den Wert zu behalten. ',
      el('label', { class: 'inl' }, el('input', { type: 'checkbox', id: 'rm-' + f.k }), ' gespeicherten Wert entfernen')) : null;
  }
  return el('label', { class: 'f', 'data-k': f.k }, f.label, input, note);
}
function cameraExtra() {
  const devs = el('div', { class: 'devs' }), res = el('div', { class: 'probe', 'aria-live': 'polite' });
  const bDev = el('button', { type: 'button', onclick: async e => {
    e.target.disabled = true; devs.textContent = 'Suche …';
    try {
      const d = await api('/api/setup/devices');
      devs.replaceChildren();
      if (!d.video.length) devs.append(el('p', { class: 'muted' }, 'Keine Kamera am PC gefunden.'));
      d.video.forEach(v => devs.append(el('button', { type: 'button', onclick: () => { $('#s-CAMERA_SOURCE').value = v.source; } }, `Kamera: ${v.label}`)));
      d.audio.forEach(a => devs.append(el('button', { type: 'button', onclick: () => { $('#s-CAMERA_AUDIO_DEVICE').value = a.value; } }, `Mikrofon: ${a.label}`)));
    } catch (x) { devs.textContent = x.message; }
    e.target.disabled = false;
  } }, 'Webcams suchen');
  const bTest = el('button', { type: 'button', class: 'primary', onclick: async e => {
    e.target.disabled = true; res.textContent = 'Verbinde … (bis zu 35 Sekunden)';
    try {
      const r = await api('/api/setup/camera-test', { method: 'POST', body: JSON.stringify({ source: $('#s-CAMERA_SOURCE').value, audio_device: $('#s-CAMERA_AUDIO_DEVICE').value }) });
      if (!r.ok) res.replaceChildren(el('p', { class: 'bad-t' }, r.error));
      else res.replaceChildren(el('img', { src: 'data:image/jpeg;base64,' + r.image, alt: 'Testbild der Kamera' }),
        el('p', { class: 'ok-t' }, `Verbindung steht (${r.seconds} s). Video: ${r.video}. Ton: ${r.audio || 'keiner'}.`),
        r.audio_note ? el('p', { class: 'muted small' }, r.audio_note) : '');
    } catch (x) { res.replaceChildren(el('p', { class: 'bad-t' }, x.message)); }
    e.target.disabled = false;
  } }, 'Verbindung testen');
  const pres = el('div', { class: 'probe', 'aria-live': 'polite' });
  const bPhone = el('button', { type: 'button', onclick: async e => {
    e.target.disabled = true; pres.textContent = 'Erzeuge QR-Code …';
    try {
      const r = await api('/api/setup/phone-pair');
      if (!r.ready) { pres.replaceChildren(el('p', { class: 'bad-t' }, r.reason)); }
      else {
        pres.replaceChildren(
          el('img', { src: 'data:image/png;base64,' + r.qr_png_base64, alt: 'QR-Code zum Verbinden des Handys', style: 'width:220px;max-width:60vw;background:#fff;padding:8px;border-radius:8px' }),
          el('p', {}, 'Mit dem Handy scannen (Kamera-App) oder den Link direkt öffnen:'),
          el('p', { class: 'muted small' }, r.url),
          el('p', { class: 'muted small' }, 'Danach auf dem Handy „Kamera starten“ tippen. Der Verbindungsstatus erscheint im Reiter „Live“. ' +
            'Das Handy muss am Strom hängen und die Seite im Vordergrund bleiben (Bildschirm nicht sperren) – das ist eine Einschränkung der Mobil-Browser, keine Fehlfunktion.'));
      }
    } catch (x) { pres.replaceChildren(el('p', { class: 'bad-t' }, x.message)); }
    e.target.disabled = false;
  } }, 'QR-Code zum Verbinden anzeigen');
  const bUsePhone = el('button', { type: 'button', onclick: () => { $('#s-CAMERA_SOURCE').value = 'phone'; toast('Kamera-Quelle auf „Handy“ gesetzt – unten speichern, dann QR-Code anzeigen.'); } }, 'Handy als Kamera verwenden');
  return el('div', {}, el('div', { class: 'row' }, bDev, bTest), devs, res,
    el('p', { class: 'muted small', style: 'margin-top:1rem' }, 'Kein Netzwerkkamera und keine Webcam am PC? Ein Handy (iPhone oder Android) kann als Kamera dienen – ohne App, über den Browser. Dafür braucht „Adresse der App“ unten eine https-Adresse.'),
    el('div', { class: 'row' }, bUsePhone, bPhone), pres);
}
function telegramExtra() {
  const res = el('div', { 'aria-live': 'polite' });
  const b = el('button', { type: 'button', onclick: async e => {
    e.target.disabled = true; res.textContent = 'Prüfe …';
    try {
      const r = await api('/api/setup/telegram', { method: 'POST', body: JSON.stringify({ token: $('#s-TELEGRAM_BOT_TOKEN').value }) });
      if (!r.ok) { res.replaceChildren(el('p', { class: 'bad-t' }, r.error)); }
      else {
        res.replaceChildren(el('p', { class: 'ok-t' }, `Bot ${r.bot} gefunden.`), r.note ? el('p', { class: 'muted' }, r.note) : '',
          ...r.chats.map(c => el('button', { type: 'button', onclick: () => {
            const inp = $('#s-TELEGRAM_CHAT_IDS'); const ids = inp.value.split(/[,;\s]+/).filter(Boolean);
            if (!ids.includes(c.id)) ids.push(c.id);
            inp.value = ids.join(',');
          } }, `${c.name || 'Chat'} (${c.id}) übernehmen`)));
      }
    } catch (x) { res.replaceChildren(el('p', { class: 'bad-t' }, x.message)); }
    e.target.disabled = false;
  } }, 'Bot prüfen und Chats suchen');
  return el('div', {}, el('div', { class: 'row' }, b), res);
}
function loraExtra() {
  const out = el('div', { class: 'probe', 'aria-live': 'polite' });
  return el('div', {}, el('div', { class: 'row' }, el('button', { type: 'button', onclick: async e => {
    e.target.disabled = true; out.textContent = 'Suche …';
    try {
      const ports = await api('/api/mesh/lora/ports');
      out.replaceChildren(ports.length ? el('div', {}, ports.map(p => el('div', {}, el('button', { type: 'button', class: 'linkish', onclick: () => { $('#s-MESH_LORA_PORT').value = p.device; } }, p.device), ` ${p.name} ${p.usb}`)))
                                     : 'Kein serielles Gerät gefunden – USB-Kabel und Treiber prüfen.');
    } catch (x) { out.textContent = x.message; }
    e.target.disabled = false;
  } }, 'Angeschlossene Geräte suchen')), out);
}
function freenetExtra() {
  const code = el('input', { type: 'text', id: 'fn-invite', autocomplete: 'off', spellcheck: 'false', placeholder: 'Einladungscode einfügen' });
  const out = el('div', { class: 'probe', 'aria-live': 'polite' });
  return el('div', {}, el('label', { class: 'f' }, 'Einladung zu einem River-Raum annehmen', code),
    el('div', { class: 'row' }, el('button', { type: 'button', onclick: async e => {
      e.target.disabled = true; out.textContent = 'Trete bei … (kann bis zu drei Minuten dauern)';
      try { await api('/api/mesh/freenet/invite', { method: 'POST', body: JSON.stringify({ code: code.value.trim(), nickname: $('#s-MESH_STATION')?.value || '' }) }); out.textContent = 'Beigetreten. Den Raum-Schlüssel (riverctl room list) oben eintragen.'; code.value = ''; }
      catch (x) { out.textContent = x.message; }
      e.target.disabled = false;
    } }, 'Einladung annehmen')), out);
}
function geoExtra() {
  return el('div', { class: 'row' }, el('button', { type: 'button', onclick: () => {
    if (!navigator.geolocation) { toast('Standortbestimmung wird hier nicht unterstützt.'); return; }
    navigator.geolocation.getCurrentPosition(p => {
      $('#s-APIARY_LAT').value = p.coords.latitude.toFixed(5);
      $('#s-APIARY_LON').value = p.coords.longitude.toFixed(5);
      toast('Standort dieses Geräts übernommen – gilt nur, wenn du am Bienenstand bist.', 6000);
    }, err => toast(`Standort nicht verfügbar: ${err.message}`, 6000), { enableHighAccuracy: true, timeout: 20000 });
  } }, 'Standort dieses Geräts verwenden'));
}
async function loadSetup(force = false) {
  if (S.setup && !force) return;
  try { S.setup = await api('/api/setup'); } catch { return; }
  const root = $('#setup-forms');
  root.replaceChildren(...SETUP.map(sec => el('div', { class: 'panel' },
    el('h3', {}, sec.title), sec.help ? el('p', { class: 'muted small' }, sec.help) : '',
    sec.fields.map(fieldEl),
    sec.extra === 'camera' ? cameraExtra() : sec.extra === 'telegram' ? telegramExtra() : sec.extra === 'geo' ? geoExtra() : sec.extra === 'lora' ? loraExtra() : sec.extra === 'freenet' ? freenetExtra() : '')));
  applyShow();
  $('#setup-intro').textContent = S.setup.configured ? 'Änderungen werden erst nach „Speichern und neu starten“ wirksam.'
    : 'Erster Schritt: die Kamera eintragen und testen. Alle weiteren Meldewege sind optional und lassen sich später ergänzen.';
  $('#btn-save').textContent = S.setup.can_restart ? 'Speichern und neu starten' : 'Speichern';
  $('#save-note').textContent = S.setup.can_restart ? 'Das Programm startet dabei kurz neu (ca. 10 Sekunden).' : 'Nach dem Speichern das Programm bitte selbst neu starten.';
}
function collectSetup() {
  const out = {};
  for (const sec of SETUP) for (const f of sec.fields) {
    const inp = $('#s-' + f.k);
    if (f.secret) {
      if ($('#rm-' + f.k)?.checked) out[f.k] = '';
      else if (inp.value.trim()) out[f.k] = inp.value.trim();
    } else out[f.k] = f.type === 'bool' ? String(inp.checked) : inp.value.trim();
  }
  return out;
}
$('#btn-save').addEventListener('click', async e => {
  const btn = e.target;
  btn.disabled = true;
  try {
    const r = await api('/api/setup', { method: 'PUT', body: JSON.stringify({ values: collectSetup() }) });
    if (!r.changed.length) { toast('Keine Änderungen.'); btn.disabled = false; return; }
    if (!S.setup.can_restart) { toast('Gespeichert. Bitte das Programm neu starten.', 8000); btn.disabled = false; S.setup = null; loadSetup(true); return; }
    $('#save-note').textContent = 'Gespeichert. Programm startet neu …';
    await api('/api/setup/restart', { method: 'POST' });
    for (let i = 0; i < 90; i++) {
      await new Promise(r2 => setTimeout(r2, 1000));
      try { if ((await fetch('/api/health')).ok && i > 2) { location.reload(); return; } } catch { /* Neustart läuft */ }
    }
    $('#save-note').textContent = 'Der Neustart dauert ungewöhnlich lange. Seite neu laden oder das Programm prüfen (data/hornet.log).';
  } catch (x) { toast(x.message, 7000); }
  btn.disabled = false;
});

/* ---------- Start ---------- */
async function boot() {
  const p = new URLSearchParams(location.search);
  if (p.get('t')) {
    try { await fetch('/api/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token: p.get('t') }) }); } catch { /* zeigt Login */ }
    history.replaceState(null, '', location.pathname + location.hash);
  }
  let authed = false;
  try { authed = (await (await fetch('/api/session', { credentials: 'same-origin' })).json()).authed; } catch { /* offline */ }
  if (!authed) { showLogin(); return; }
  S.authed = true;
  $('#login').hidden = true;
  $('.tabs').hidden = false;
  renderSound();
  await refreshStatus();
  connectEvents();
  loadAlerts();
  route();
}
if ('serviceWorker' in navigator && window.isSecureContext) {
  navigator.serviceWorker.register('/sw.js').catch(() => { /* ohne SW weiter */ });
  navigator.serviceWorker.addEventListener('message', e => { if (e.data?.goto) { location.hash = e.data.goto.replace(/^.*#/, '#'); route(); } });
}
setInterval(() => { if (!document.hidden) refreshStatus(); }, 3000);
boot();
