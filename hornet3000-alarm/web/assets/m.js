/* SPDX-License-Identifier: GPL-3.0-or-later · SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende */
/* Hornet3000 Mobil – bewusst reines ES5 ohne Bibliotheken (läuft ab iOS 9 / Android 4.0-Browser).
   Kein fetch, kein Promise (außer wo der Browser es für die Kamera selbst verlangt), keine Pfeilfunktionen,
   kein let/const, kein classList. Alle Texte vom Server werden mit textContent eingesetzt (kein innerHTML). */
(function () {
  'use strict';

  var POLL_MS = 5000;
  var $ = function (id) { return document.getElementById(id); };

  // ---- kleine Helfer ---------------------------------------------------------------------------
  function hasClass(e, c) { return (' ' + e.className + ' ').indexOf(' ' + c + ' ') >= 0; }
  function addClass(e, c) { if (!hasClass(e, c)) { e.className = (e.className ? e.className + ' ' : '') + c; } }
  function delClass(e, c) { e.className = (' ' + e.className + ' ').replace(' ' + c + ' ', ' ').replace(/^\s+|\s+$/g, ''); }
  function show(e, on) { if (on) { delClass(e, 'hidden'); } else { addClass(e, 'hidden'); } }
  function text(e, t) { e.textContent = t; }
  function el(tag, cls, txt) {
    var e = document.createElement(tag);
    if (cls) { e.className = cls; }
    if (txt !== undefined && txt !== null) { e.textContent = txt; }
    return e;
  }
  function clear(e) { while (e.firstChild) { e.removeChild(e.firstChild); } }
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function fmtTime(ts) {
    var d = new Date(ts * 1000), now = new Date();
    var t = pad(d.getHours()) + ':' + pad(d.getMinutes());
    if (d.toDateString() === now.toDateString()) { return t; }
    return pad(d.getDate()) + '.' + pad(d.getMonth() + 1) + '. ' + t;
  }
  function store(key, val) {
    try { if (val === undefined) { return window.localStorage.getItem(key); } window.localStorage.setItem(key, val); } catch (e) { /* privater Modus */ }
    return null;
  }

  // ---- HTTP ----------------------------------------------------------------------------------------
  // body: null | Objekt (wird JSON) | {raw: ArrayBuffer/Blob/File, type: 'image/jpeg'}
  function api(method, url, body, cb, headers) {
    var x = new XMLHttpRequest(), done = false, payload = null;
    x.open(method, url, true);
    x.setRequestHeader('Accept', 'application/json');
    if (body && body.raw) {
      x.setRequestHeader('Content-Type', body.type);
      payload = body.raw;
    } else if (body) {
      x.setRequestHeader('Content-Type', 'application/json');
      payload = JSON.stringify(body);
    }
    if (headers) { for (var k in headers) { if (headers.hasOwnProperty(k)) { x.setRequestHeader(k, headers[k]); } } }
    var timer = setTimeout(function () {
      if (!done) { done = true; try { x.abort(); } catch (e) { /* egal */ } cb(0, null, x); }
    }, 20000);
    x.onreadystatechange = function () {
      if (x.readyState !== 4 || done) { return; }
      done = true;
      clearTimeout(timer);
      var j = null;
      try { j = JSON.parse(x.responseText); } catch (e) { j = null; }
      cb(x.status, j, x);
    };
    try { x.send(payload); } catch (e2) { if (!done) { done = true; clearTimeout(timer); cb(0, null, x); } }
  }
  function detail(j, st) {
    if (j && j.detail) { return typeof j.detail === 'string' ? j.detail : 'Fehler ' + st; }
    return st ? 'Fehler ' + st : 'keine Verbindung';
  }

  // ---- Zustand ---------------------------------------------------------------------------------------
  var sinceId = null;           // null = noch keine Grundlage (erste Abfrage setzt nur den Stand)
  var pollTimer = null, lastOk = 0, failing = 0;
  var audioReady = false, alarmTimer = null, alarmEnds = 0, flashTimer = null;
  var muted = false;
  var audio = null;
  var cfg = null;

  function showMsg(t, info) {
    var m = $('msg');
    if (!t) { show(m, false); return; }
    m.className = 'banner' + (info ? ' info' : '');
    text(m, t);
  }

  // ---- Anmeldung -------------------------------------------------------------------------------------
  function showLogin(err) {
    show($('login'), true); show($('app'), false);
    text($('login-err'), err || '');
    text($('conn'), 'abgemeldet');
    $('conn').className = 'pill bad';
    stopPolling();
  }
  function login(token, cb) {
    api('POST', '/api/login', { token: token }, function (st, j) {
      if (st === 200) { cb(true, ''); } else { cb(false, st === 429 ? 'Zu viele Versuche – 10 Minuten warten' : detail(j, st)); }
    });
  }
  function enterApp() {
    show($('login'), false); show($('app'), true);
    startPolling();
    loadStationConfig();
  }
  function boot() {
    var h = window.location.hash || '';
    var m = /[#&]k=([A-Za-z0-9_\-]{8,128})/.exec(h);
    if (m) {                                  // Link aus QR-Code: …/m#k=SCHLÜSSEL – der Teil nach # geht nie an den Server
      try { window.history.replaceState(null, '', window.location.pathname); } catch (e) { window.location.hash = ''; }
      login(m[1], function (ok, err) { if (ok) { enterApp(); } else { showLogin(err); } });
      return;
    }
    api('GET', '/api/session', null, function (st, j) {
      if (st === 200 && j && j.authed) { enterApp(); } else { showLogin(st === 0 ? 'Der Wächter ist nicht erreichbar' : ''); }
    });
  }

  // ---- Abfrage -----------------------------------------------------------------------------------------
  function stopPolling() { if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; } }
  function startPolling() { stopPolling(); poll(); }
  function poll() {
    api('GET', '/api/mobile/poll?since=' + (sinceId === null ? 0 : sinceId), null, function (st, j) {
      if (st === 401) { showLogin('Bitte neu anmelden'); return; }
      if (st === 200 && j) {
        failing = 0; lastOk = new Date().getTime();
        render(j);
      } else {
        failing += 1;
        var secs = lastOk ? Math.round((new Date().getTime() - lastOk) / 1000) : 0;
        text($('conn'), 'getrennt'); $('conn').className = 'pill bad';
        showMsg(st === 429 ? 'Zu viele Versuche – bitte warten.' :
          'Keine Verbindung zum Wächter' + (secs ? ' (seit ' + secs + ' s)' : '') + '. Es wird weiter versucht.');
      }
      pollTimer = setTimeout(poll, failing > 3 ? 15000 : POLL_MS);
    });
  }

  function kindClass(k) { return k === 'new' ? 'new' : k === 'test' ? 'tst' : 'upd'; }
  function kindName(k) { return k === 'new' ? 'Neue Sichtung' : k === 'update' ? 'Weitere Sichtung' : k === 'test' ? 'Testalarm' : k === 'reminder' ? 'Erinnerung' : k; }
  function alertText(a) {
    var t = a.label || a.species || 'Hornisse';
    if (a.count) { t += ' · ' + a.count + ' Tier' + (a.count === 1 ? '' : 'e'); }
    if (typeof a.conf === 'number' && a.conf > 0) { t += ' · ' + Math.round(a.conf * 100) + ' %'; }
    return t;
  }

  var shownAlerts = [];
  function render(j) {
    showMsg('');
    text($('conn'), 'verbunden'); $('conn').className = 'pill ok';
    text($('ver'), 'Wächter ' + j.version);
    show($('apk'), !!j.apk);
    muted = !!j.muted;
    show($('btn-mute'), !muted); show($('btn-unmute'), muted);

    var c = j.camera || {};
    var s = (c.state === 'online' ? 'online' : c.state === 'waiting' ? 'wartet auf Bild' : c.state === 'offline' ? 'OFFLINE' : (c.state || '?'));
    text($('cam-state'), (c.name || '') + ' – ' + s + (c.station ? ' (Station ' + c.station + (c.fps ? ', ' + c.fps + ' Bilder/s' : '') + ')' : ''));
    $('cam-state').className = c.online ? 'good' : 'bad';
    var st = '24 h: ' + j.alarms_24h + ' Alarm' + (j.alarms_24h === 1 ? '' : 'e') + ' · jetzt erkannt: ' + j.detections_now;
    if (muted) { st += ' · STUMM bis ' + fmtTime(j.mute_until); }
    text($('stats'), st);

    // neue Meldungen?
    var list = j.alerts || [];
    if (sinceId === null) {
      sinceId = j.newest_id || 0;            // erste Abfrage: Stand merken, keinen alten Alarm abspielen
      shownAlerts = list;
      renderList();
      return;
    }
    var fresh = [], i;
    for (i = list.length - 1; i >= 0; i--) { if (list[i].id > sinceId) { fresh.push(list[i]); } }
    if (j.newest_id > sinceId) { sinceId = j.newest_id; }
    if (fresh.length) {
      shownAlerts = list.concat(shownAlerts).slice(0, 30);     // der Server liefert nur neuere Meldungen: vor die alte Liste setzen
      renderList();
      var top = fresh[fresh.length - 1], i2;
      for (i2 = 0; i2 < fresh.length; i2++) { if (fresh[i2].kind === 'new') { top = fresh[i2]; } }
      raiseAlarm(top, muted || top.muted);
    }
  }

  function renderList() {
    var ul = $('alerts'), i, a, li;
    clear(ul);
    if (!shownAlerts.length) { ul.appendChild(el('li', 'small', 'Noch keine Meldungen.')); return; }
    for (i = 0; i < shownAlerts.length && i < 12; i++) {
      a = shownAlerts[i];
      li = el('li', kindClass(a.kind));
      if (a.snapshot_url) {
        var im = el('img'); im.alt = ''; im.src = a.snapshot_url;
        var link = el('a'); link.href = a.snapshot_url; link.appendChild(im);
        li.appendChild(link);
      }
      li.appendChild(el('div', '', kindName(a.kind) + (a.muted ? ' (stumm)' : '')));
      li.appendChild(el('div', 'small', fmtTime(a.ts) + ' · ' + alertText(a)));
      if (a.clip_url) { var cl = el('a', 'small', 'Video'); cl.href = a.clip_url; li.appendChild(cl); }
      ul.appendChild(li);
    }
  }

  // ---- Alarm ------------------------------------------------------------------------------------------------
  function ensureAudio() {
    if (!audio) { try { audio = new Audio('/assets/alarm.wav'); audio.preload = 'auto'; } catch (e) { audio = null; } }
    return audio;
  }
  function beep() {
    var a = ensureAudio();
    if (!a || !audioReady) { return false; }
    try { a.currentTime = 0; var p = a.play(); if (p && p.catch) { p.catch(function () { audioReady = false; setSndState(); }); } } catch (e) { return false; }
    return true;
  }
  function setSndState() {
    text($('snd-state'), audioReady ? 'Alarmton ist bereit.' :
      'Alte iPhones und Android-Geräte spielen Töne erst nach einer Berührung. Einmal tippen:');
  }
  function vibrate() { try { if (navigator.vibrate) { navigator.vibrate([400, 200, 400, 200, 800]); } } catch (e) { /* kein Vibrieren */ } }

  function raiseAlarm(a, silent) {
    var box = $('alarm');
    box.className = 'alarm' + (a.kind === 'test' ? ' tst' : a.kind === 'new' ? '' : ' upd');
    text($('alarm-title'), (a.kind === 'new' ? 'ALARM – ' : '') + kindName(a.kind));
    text($('alarm-text'), fmtTime(a.ts) + ' · ' + alertText(a) + (silent ? ' · stumm geschaltet' : ''));
    var im = $('alarm-img');
    if (a.snapshot_url) { im.src = a.snapshot_url; show(im, true); } else { show(im, false); }
    show(box, true);
    try { document.title = 'ALARM ' + kindName(a.kind) + ' – Hornet3000'; } catch (e) { /* egal */ }
    if (alarmTimer) { clearInterval(alarmTimer); alarmTimer = null; }
    if (flashTimer) { clearInterval(flashTimer); flashTimer = null; }
    if (silent) { return; }
    beep(); vibrate();
    if (a.kind === 'test') { return; }
    alarmEnds = new Date().getTime() + 5 * 60 * 1000;      // bis zur Quittierung, höchstens 5 Minuten
    alarmTimer = setInterval(function () {
      if (new Date().getTime() > alarmEnds) { clearInterval(alarmTimer); alarmTimer = null; return; }
      beep(); vibrate();
    }, 6000);
    var on = false;
    flashTimer = setInterval(function () { on = !on; if (on) { addClass(box, 'flash'); } else { delClass(box, 'flash'); } }, 600);
  }
  function ack() {
    show($('alarm'), false);
    if (alarmTimer) { clearInterval(alarmTimer); alarmTimer = null; }
    if (flashTimer) { clearInterval(flashTimer); flashTimer = null; }
    try { document.title = 'Hornet3000 Mobil'; } catch (e) { /* egal */ }
  }

  // ---- Knöpfe ----------------------------------------------------------------------------------------------------
  function bindButtons() {
    $('btn-login').onclick = function () {
      var t = $('tok').value.replace(/^\s+|\s+$/g, '');
      if (!t) { text($('login-err'), 'Bitte Schlüssel eingeben'); return; }
      login(t, function (ok, err) { if (ok) { $('tok').value = ''; enterApp(); } else { text($('login-err'), err); } });
    };
    $('tok').onkeydown = function (e) { if ((e || window.event).keyCode === 13) { $('btn-login').onclick(); } };
    $('btn-ack').onclick = ack;
    $('btn-mute').onclick = function () {
      api('POST', '/api/mute', { minutes: 60 }, function (st, j) { if (st === 200) { poll_now(); } else { showMsg(detail(j, st)); } });
    };
    $('btn-unmute').onclick = function () {
      api('POST', '/api/unmute', {}, function (st, j) { if (st === 200) { poll_now(); } else { showMsg(detail(j, st)); } });
    };
    $('btn-test').onclick = function () {
      showMsg('Testalarm wird ausgelöst …', true);
      api('POST', '/api/test-alert', {}, function (st, j) {
        if (st === 200) { showMsg((j && j.detail) || 'Testalarm läuft', true); } else { showMsg(detail(j, st)); }
      });
    };
    $('btn-snd').onclick = function () {
      audioReady = true;
      ensureAudio();
      if (!beep()) { audioReady = false; }
      setSndState();
    };
    $('lnk-out').onclick = function () {
      api('POST', '/api/logout', {}, function () { sinceId = null; showLogin(''); });
      return false;
    };
    $('photo').onchange = onPhoto;
    $('btn-st').onclick = function () { if (stationOn) { stopStation(); } else { startStation(); } };
    $('btn-st-flip').onclick = function () { facing = facing === 'environment' ? 'user' : 'environment'; if (stationOn) { stopStation(); startStation(); } };
    var nm = store('h3k_station'); if (nm) { $('st-name').value = nm; }
  }
  function poll_now() { stopPolling(); poll(); }

  // ---- Foto prüfen ---------------------------------------------------------------------------------------------------
  function showCheck(node) { var r = $('check-res'); clear(r); r.appendChild(node); }
  function onPhoto() {
    var f = this.files && this.files[0];
    if (!f) { return; }
    showCheck(el('p', '', 'Bild wird vorbereitet …'));
    var self = this;
    if (f.size <= 900 * 1024) { sendCheck(f, f.type || 'image/jpeg'); self.value = ''; return; }     // klein genug: unverändert senden (Ausrichtung bleibt erhalten)
    if (!window.FileReader || !document.createElement('canvas').getContext) {
      showCheck(el('p', 'bad', 'Das Foto ist zu groß (' + Math.round(f.size / 1024) + ' kB, erlaubt 900 kB) und dieses Gerät kann es nicht verkleinern. Bitte kleinere Auflösung einstellen.'));
      return;
    }
    var rd = new FileReader();
    rd.onload = function () {
      var img = new Image();
      img.onload = function () {
        var max = 1280, w = img.width, h = img.height, k = Math.min(1, max / Math.max(w, h));
        var cv = $('cv'); cv.width = Math.round(w * k); cv.height = Math.round(h * k);
        cv.getContext('2d').drawImage(img, 0, 0, cv.width, cv.height);
        var bin = dataUrlToBytes(cv.toDataURL('image/jpeg', 0.85));
        if (!bin) { showCheck(el('p', 'bad', 'Dieses Gerät kann das Foto nicht verkleinern.')); return; }
        sendCheck(bin, 'image/jpeg');
      };
      img.onerror = function () { showCheck(el('p', 'bad', 'Das Foto konnte nicht gelesen werden.')); };
      img.src = rd.result;
    };
    rd.onerror = function () { showCheck(el('p', 'bad', 'Das Foto konnte nicht gelesen werden.')); };
    rd.readAsDataURL(f);
    self.value = '';
  }
  function dataUrlToBytes(u) {
    var i = u.indexOf(',');
    if (i < 0 || u.indexOf('image/jpeg') < 0 || !window.Uint8Array || !window.atob) { return null; }
    var b = window.atob(u.substring(i + 1)), n = b.length, arr = new Uint8Array(n), k;
    for (k = 0; k < n; k++) { arr[k] = b.charCodeAt(k); }
    return arr;
  }
  function sendCheck(data, type) {
    showCheck(el('p', '', 'Wird ausgewertet …'));
    api('POST', '/api/mobile/check', { raw: data, type: type }, function (st, j) {
      var box = el('div');
      if (st !== 200 || !j) {
        box.appendChild(el('p', 'bad', detail(j, st)));
      } else {
        box.appendChild(el('p', j.alarm_like ? 'bad' : 'ok-t', j.verdict));
        var i, d;
        for (i = 0; i < j.detections.length; i++) {
          d = j.detections[i];
          box.appendChild(el('div', 'det', d.name + ' – ' + Math.round(d.conf * 100) + ' %' +
            (d.kind === 'alarm' ? ' (Alarmart)' : d.kind === 'geschuetzt' ? ' (geschützte Art)' : '')));
        }
        box.appendChild(el('p', 'small', 'Bildgröße ' + j.size[0] + '×' + j.size[1] + '. Die Auswertung ist eine Hilfe, keine Bestimmung.'));
      }
      showCheck(box);
    });
  }

  // ---- Station: dieses Gerät als Kamera -------------------------------------------------------------------------------------
  var stName = 'Handy', stationOn = false, stream = null, facing = 'environment', frameTimer = null, sent = 0, startedAt = 0, backoff = 0;
  var stStat = { err: '', lastMs: 0, width: 640 };

  function loadStationConfig() {
    api('GET', '/api/station/config', null, function (st, j) {
      if (st === 200 && j) {
        cfg = j; stStat.width = j.width || 640;
        text($('st-hint'), 'Der Wächter nimmt Bilder von Stationen an (etwa alle ' + String(Math.round(j.interval_ms / 100) / 10).replace('.', ',') + ' s).');
      } else if (st === 409) {
        cfg = null; text($('st-hint'), 'Der Wächter ist nicht auf „push“ eingestellt: Einrichtung → Kamera → Quelle „push“, speichern, neu starten.');
      }
    });
  }
  function getCam(constraints, ok, err) {
    var md = navigator.mediaDevices;
    if (md && md.getUserMedia) { md.getUserMedia(constraints).then(ok, err); return true; }
    var legacy = navigator.getUserMedia || navigator.webkitGetUserMedia || navigator.mozGetUserMedia;
    if (legacy) { legacy.call(navigator, constraints, ok, err); return true; }
    return false;
  }
  function stErr(t) { stStat.err = t; renderStat(); }
  function renderStat() {
    var s = stationOn ? 'Sendet: ' + sent + ' Bilder' : 'Gestoppt';
    if (stationOn && sent && startedAt) { s += ' (' + (sent / Math.max(1, (new Date().getTime() - startedAt) / 1000)).toFixed(1) + '/s)'; }
    var node = el('div', '', s);
    if (stStat.err) { node.appendChild(el('div', 'bad', stStat.err)); }
    var r = $('st-stats'); clear(r); r.appendChild(node);
  }
  function startStation() {
    if (!cfg) { stErr('Der Wächter ist nicht auf „push“ eingestellt (siehe Hinweis oben).'); return; }
    var nm = $('st-name').value.replace(/[^A-Za-z0-9._ \-]/g, '_').replace(/^\s+|\s+$/g, '').substring(0, 40) || 'Handy';
    $('st-name').value = nm; stName = nm; store('h3k_station', nm);
    var c = { video: { facingMode: facing }, audio: false };
    var ok = getCam(c, function (s) {
      stream = s;
      var v = $('st-video');
      try { v.setAttribute('playsinline', ''); v.setAttribute('webkit-playsinline', ''); v.muted = true; } catch (e) { /* egal */ }
      if ('srcObject' in v) { v.srcObject = s; } else { var U = window.URL || window.webkitURL; v.src = U.createObjectURL(s); }
      try { var p = v.play(); if (p && p.catch) { p.catch(function () {}); } } catch (e2) { /* egal */ }
      show($('st-stage'), true); show($('btn-st-flip'), true);
      text($('btn-st'), 'Kamera beenden'); $('btn-st').className = 'btn danger';
      stationOn = true; sent = 0; startedAt = new Date().getTime(); backoff = 0; stStat.err = '';
      renderStat();
      frameTimer = setTimeout(nextFrame, 800);
    }, function (e) {
      var n = e && e.name ? e.name : '';
      stErr(n === 'NotAllowedError' || n === 'PermissionDeniedError' ? 'Kamera-Zugriff wurde nicht erlaubt.' :
        n === 'NotFoundError' || n === 'DevicesNotFoundError' ? 'Keine Kamera gefunden.' :
        'Kamera nicht verfügbar (' + (n || 'Fehler') + '). Auf neueren Geräten wird dafür eine https-Adresse benötigt.');
    });
    if (!ok) { stErr('Dieser Browser kann die Kamera nicht für Webseiten freigeben. Bitte die Android-App „Hornet3000 Station“ verwenden.'); }
  }
  function stopStation() {
    stationOn = false;
    if (frameTimer) { clearTimeout(frameTimer); frameTimer = null; }
    if (stream) {
      var tr = stream.getTracks ? stream.getTracks() : [], i;
      for (i = 0; i < tr.length; i++) { try { tr[i].stop(); } catch (e) { /* egal */ } }
      if (stream.stop) { try { stream.stop(); } catch (e2) { /* alte Browser */ } }
      stream = null;
    }
    show($('st-stage'), false); show($('btn-st-flip'), false);
    text($('btn-st'), 'Kamera starten'); $('btn-st').className = 'btn';
    renderStat();
  }
  function nextFrame() {
    if (!stationOn) { return; }
    var v = $('st-video'), t0 = new Date().getTime();
    if (!v.videoWidth) { frameTimer = setTimeout(nextFrame, 400); return; }
    var w = Math.min(stStat.width, v.videoWidth), h = Math.round(v.videoHeight * w / v.videoWidth);
    var cv = $('cv'); cv.width = w; cv.height = h;
    var bin = null;
    try { cv.getContext('2d').drawImage(v, 0, 0, w, h); bin = dataUrlToBytes(cv.toDataURL('image/jpeg', 0.7)); } catch (e) { bin = null; }
    if (!bin) { stErr('Dieses Gerät kann keine Bilder aus der Kamera erzeugen.'); stopStation(); return; }
    var every = Math.max((cfg && cfg.interval_ms) || 1000, ((cfg && cfg.min_interval_ms) || 200) + 50);
    api('POST', '/api/station/frame', { raw: bin, type: 'image/jpeg' }, function (st, j, x) {
      var wait = Math.max(0, every - (new Date().getTime() - t0));
      if (st === 200) { sent += 1; stStat.err = ''; backoff = 0; }
      else if (st === 429) { var ra = parseInt(x.getResponseHeader('Retry-After') || '1', 10); wait = Math.max(wait, (isNaN(ra) ? 1 : ra) * 1000); }
      else if (st === 401) { stopStation(); showLogin('Bitte neu anmelden'); return; }
      else if (st === 413) { stStat.width = Math.max(160, Math.round(stStat.width * 0.7)); stStat.err = detail(j, st) + ' – verkleinere das Bild'; }
      else if (st === 409) { stStat.err = detail(j, st); wait = Math.max(wait, 5000); }
      else { backoff = backoff ? Math.min(30000, backoff * 2) : 2000; stStat.err = detail(j, st) + ' – neuer Versuch'; wait = Math.max(wait, backoff); }
      renderStat();
      if (stationOn) { frameTimer = setTimeout(nextFrame, wait); }
    }, { 'X-Station': stName });
  }

  // ---- Start -------------------------------------------------------------------------------------------------------------------
  function init() {
    bindButtons();
    setSndState();
    renderStat();
    boot();
    window.onhashchange = function () { if (/[#&]k=/.test(window.location.hash || '')) { boot(); } };
  }
  if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', init, false); } else { init(); }
}());
