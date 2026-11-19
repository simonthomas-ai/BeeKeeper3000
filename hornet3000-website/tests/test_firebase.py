# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende
"""Prüft firebase.json am Firebase-Hosting-Emulator (läuft lokal; es wird nichts zu Google hochgeladen).

WICHTIG zur Aussagekraft: Der Emulator ist ein lokaler Nachbau von Google. Er bestätigt, dass firebase.json gültig ist und die
Kopfzeilen sowie die 404-Seite so verwendet werden. Ob der echte Dienst zusätzlich eigene Kopfzeilen setzt (z. B.
Strict-Transport-Security), zeigt erst ein Aufruf der veröffentlichten Seite (siehe README, „Nach dem Hochladen prüfen“).

Voraussetzung: firebase-tools (npm install firebase-tools) und Node. Sonst werden die Tests übersprungen.
Pfad zum Programm: Umgebungsvariable FIREBASE_BIN oder „firebase“ im PATH.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request

import pytest

from test_site import ROOT, VERSION, attrappen, fertig  # noqa: F401

FIREBASE = os.environ.get("FIREBASE_BIN") or shutil.which("firebase")
pytestmark = pytest.mark.skipif(not FIREBASE or not shutil.which("node"), reason="firebase-tools/Node nicht installiert")
PORT = 15321


@pytest.fixture(scope="module")
def emulator(fertig, tmp_path_factory):
    tmp = tmp_path_factory.mktemp("firebase")
    shutil.copytree(fertig, tmp / "public")
    cfg = json.loads((ROOT / "firebase.json").read_text(encoding="utf-8"))
    cfg["emulators"] = {"hosting": {"port": PORT, "host": "127.0.0.1"}, "ui": {"enabled": False}, "singleProjectMode": True}
    (tmp / "firebase.json").write_text(json.dumps(cfg), encoding="utf-8")
    with socket.socket() as s:
        s.bind(("127.0.0.1", PORT))
    proc = subprocess.Popen([FIREBASE, "emulators:start", "--only", "hosting", "--project", "demo-hornet3000"], cwd=tmp,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
    ok = False
    for _ in range(90):
        try:
            if urllib.request.urlopen(f"http://127.0.0.1:{PORT}/", timeout=2).status == 200:
                ok = True
                break
        except (urllib.error.URLError, ConnectionError, socket.timeout):
            time.sleep(1)
    if not ok:
        os.killpg(proc.pid, signal.SIGKILL)
        pytest.fail("Emulator startet nicht")
    yield f"http://127.0.0.1:{PORT}"
    os.killpg(proc.pid, signal.SIGTERM)
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)


def holen(url):
    try:
        r = urllib.request.urlopen(url, timeout=10)
        return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def test_kopfzeilen_auf_allen_antworten(emulator):
    fb = json.loads((ROOT / "firebase.json").read_text(encoding="utf-8"))["hosting"]["headers"][0]["headers"]
    erwartet = {h["key"].lower(): h["value"] for h in fb}
    for pfad, status in (("/", 200), ("/impressum.html", 200), ("/assets/style.css", 200),
                         ("/assets/fonts/bitter-latin-700-normal.woff2", 200), ("/gibt-es-nicht.html", 404)):
        s, h, _ = holen(emulator + pfad)
        assert s == status, pfad
        for k, v in erwartet.items():
            assert h[k] == v, (pfad, k)
        assert h.get("Set-Cookie") is None, pfad


def test_eigene_404_seite_und_keine_versteckten_dateien(emulator):
    s, _, body = holen(emulator + "/gibt-es-nicht.html")
    assert s == 404 and b"<h1" in body
    for pfad in ("/firebase.json", "/.firebaserc", "/.git/config"):
        assert holen(emulator + pfad)[0] == 404, pfad


def test_seiten_unveraendert_und_download_ausgeliefert(emulator, fertig):
    for name in ("index.html", "impressum.html", "datenschutz.html", "haftung.html"):
        assert holen(f"{emulator}/{name}")[2] == (fertig / name).read_bytes(), name
    s, h, body = holen(f"{emulator}/downloads/Hornet3000-Station-{VERSION}.apk")
    assert s == 200 and body == (fertig / "downloads" / f"Hornet3000-Station-{VERSION}.apk").read_bytes()
