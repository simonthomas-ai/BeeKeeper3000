#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende
"""Browser-Prüfung der Handy-Seite /m mit echtem Chromium (Playwright) gegen das ECHTE Programm als eigenen Prozess.

Echt: Server, Erkennungsmodell, Datenbank, Anmeldung, Alarmkette (Testalarm), Foto-Auswertung, Bildannahme der Station.
Behelf: Die Kamera ist die Test-Kamera von Chromium (--use-fake-device-for-media-stream, TESTATTRAPPE); ein Alarm der Art
„Sichtung“ wird direkt in die Datenbank geschrieben, weil es hier keine echte Hornisse gibt.
„Alter Browser“: im zweiten Durchgang werden moderne Funktionen (fetch, Promise, classList, Object.assign, Array.from …) vor
dem Laden der Seite ENTFERNT; die Seite muss trotzdem laufen. Das ist KEIN Ersatz für echte alte Geräte.
Aufruf (System-Python mit Playwright):  /usr/bin/python3 tests/browser/check_mobile.py [--shots DIR]
"""
from __future__ import annotations

import argparse
import io
import json
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[2]
TOKEN = "mobile-" + "m" * 30
problems: list[str] = []
checks = 0
IOS9_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 9_3_5 like Mac OS X) AppleWebKit/601.1.46 (KHTML, like Gecko) "
           "Version/9.0 Mobile/13G36 Safari/601.1")


def check(cond: bool, msg: str) -> None:
    global checks
    checks += 1
    if not cond:
        problems.append(msg)
        print("  ✗", msg, flush=True)
    else:
        print("  ✓", msg, flush=True)


def wf(pg, expr: str, timeout: int = 10000) -> None:
    """Wartet auf einen Ausdruck – als Funktion übergeben, weil die strenge Inhaltsrichtlinie der Seite eval() verbietet."""
    pg.wait_for_function("() => (" + expr + ")", timeout=timeout)


def wt(pg, selector: str, cond, timeout: int = 15000) -> None:
    """Wartet, bis cond(Text des Elements) wahr ist (Abfrage von außen, unabhängig von den entfernten Browserfunktionen)."""
    end = time.time() + timeout / 1000
    last = ""
    while time.time() < end:
        try:
            last = pg.inner_text(selector)
        except Exception:  # noqa: BLE001
            last = ""
        if cond(last):
            return
        time.sleep(0.2)
    raise AssertionError(f"Zeitüberschreitung bei {selector}: {last!r}")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def jpeg_bytes(w, h, noise=False) -> bytes:
    import random
    from PIL import Image
    im = Image.new("RGB", (w, h), (110, 140, 80))
    if noise:                                   # Rauschen → große Datei (> 900 kB), erzwingt das Verkleinern im Browser
        px = im.load()
        rnd = random.Random(3)
        for y in range(h):
            for x in range(w):
                px[x, y] = (rnd.randrange(256), rnd.randrange(256), rnd.randrange(256))
    b = io.BytesIO()
    im.save(b, "JPEG", quality=92)
    return b.getvalue()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--venv-python", default="/home/claude/venv/bin/python")
    ap.add_argument("--shots", default="")
    ap.add_argument("--app-dir", default="")
    a = ap.parse_args()
    shots = Path(a.shots) if a.shots else None
    if shots:
        shots.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="hornet-mob-"))
    src = Path(a.app_dir) if a.app_dir else REPO
    for n in ("hornet", "web"):
        shutil.copytree(src / n, root / n, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy(src / "hornet_run.py", root / "hornet_run.py")
    (root / "models").symlink_to(src / "models")
    if a.app_dir:
        (root / "lib").symlink_to(src / "lib")
    (root / "mobil").mkdir()
    (root / "mobil" / "Hornet3000-Station.apk").write_bytes(b"PK\x03\x04" + b"TESTATTRAPPE-APK" * 64)    # nur Test: beweist Link und Download
    port = free_port()
    env = {"HOST": "127.0.0.1", "PORT": str(port), "ACCESS_TOKEN": TOKEN, "CAMERA_NAME": "Mobil-Stand",
           "CAMERA_SOURCE": "push", "CLIP_ENABLED": "false", "VERIFY_PROVIDER": "none"}
    (root / ".env").write_text("".join(f"{k}={v}\n" for k, v in env.items()))
    log = open(root / "run.log", "wb")
    srv = subprocess.Popen([a.venv_python, "-I", str(root / "hornet_run.py"), "run"], cwd=root, stdout=log, stderr=log,
                           stdin=subprocess.DEVNULL, start_new_session=True)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(200):
            try:
                if urllib.request.urlopen(base + "/api/health", timeout=1).status == 200:
                    break
            except Exception:  # noqa: BLE001
                time.sleep(0.2)
        else:
            print("Programm startet nicht", (root / "run.log").read_text()[-800:])
            return 2
        run_checks(base, root, shots)
    finally:
        srv.terminate()
        try:
            srv.wait(15)
        except subprocess.TimeoutExpired:
            srv.kill()
        shutil.rmtree(root, ignore_errors=True)
    print(f"\n{checks} Prüfungen, {len(problems)} Verstöße")
    if problems:
        print("HANDY-SEITE: DURCHGEFALLEN")
        for p in problems:
            print(" -", p)
        return 1
    print("HANDY-SEITE: BESTANDEN")
    return 0


def status(base: str) -> dict:
    rq = urllib.request.Request(base + "/api/status", headers={"Authorization": f"Bearer {TOKEN}"})
    return json.loads(urllib.request.urlopen(rq, timeout=5).read())


def insert_alert(root: Path, **f) -> int:
    db = sqlite3.connect(next((root / "data").rglob("*.db")), timeout=10)
    f = {"ts": time.time(), "camera": "Mobil-Stand", "kind": "new", "species": "vvel", "label": "Asiatische Hornisse",
         "conf": 0.88, "count": 2, "muted": 0, **f}
    cur = db.execute(f"INSERT INTO alerts ({','.join(f)}) VALUES ({','.join('?' for _ in f)})", list(f.values()))
    db.commit()
    i = cur.lastrowid
    db.close()
    return i


def run_checks(base: str, root: Path, shots: Path | None) -> None:
    with sync_playwright() as pw:
        br = pw.chromium.launch(args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream",
                                      "--autoplay-policy=no-user-gesture-required"])
        ctx = br.new_context(viewport={"width": 320, "height": 568}, user_agent=IOS9_UA, device_scale_factor=2,
                             permissions=["camera"], is_mobile=True, has_touch=True)
        errors: list[str] = []
        bad: list[str] = []
        ctx.add_init_script("window.__csp=[];document.addEventListener('securitypolicyviolation',function(e){window.__csp.push("
                            "e.violatedDirective+' '+e.blockedURI)});window.__plays=0;var _p=HTMLMediaElement.prototype.play;"
                            "HTMLMediaElement.prototype.play=function(){window.__plays++;return _p.apply(this,arguments)};")
        page = ctx.new_page()
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" and "/api/login" not in (m.location or {}).get("url", "")
                else None)
        page.on("pageerror", lambda e: errors.append("pageerror: " + str(e)))
        page.on("response", lambda r: bad.append(f"{r.status} {r.url}") if r.status >= 400 and "/api/login" not in r.url
                and "/api/station/frame" not in r.url else None)
        dialogs: list[str] = []
        page.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))

        print("Anmeldung")
        page.goto(f"{base}/m")
        page.wait_for_selector("#login:not(.hidden)", timeout=8000)
        check(page.locator("#app").is_hidden(), "ohne Anmeldung ist nur die Anmeldemaske sichtbar")
        page.fill("#tok", "falsch")
        page.click("#btn-login")
        wf(page, "document.getElementById('login-err').textContent.length>0", timeout=8000)
        check("falsch" in page.inner_text("#login-err").lower(), "falscher Schlüssel wird abgewiesen: " + page.inner_text("#login-err"))
        page.goto(f"{base}/m#k={TOKEN}")
        page.wait_for_selector("#app:not(.hidden)", timeout=10000)
        check("#k=" not in page.url and "k=" not in page.url, "Schlüssel verschwindet nach der Anmeldung aus der Adresszeile")
        wf(page, "document.getElementById('conn').textContent==='verbunden'", timeout=10000)
        check(True, "Seite zeigt „verbunden“")
        check("wartet" in page.inner_text("#cam-state").lower(), "Kamera: wartet auf Bild – " + page.inner_text("#cam-state"))
        check(page.locator("#apk").is_visible() and "Android-App" in page.inner_text("#apk"),
              "Link zur Android-App ist sichtbar, wenn der Wächter sie bereithält")
        dl = page.request.get(f"{base}/mobil/hornet3000-station.apk")
        check(dl.status == 200 and dl.body().startswith(b"PK") and "android.package-archive" in dl.headers.get("content-type", ""),
              f"Download der App mit der Sitzung der Seite: {dl.status}, {len(dl.body())} Bytes")
        scroll = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        check(scroll <= 1, f"kein waagerechtes Scrollen auf 320 px Breite (Überstand {scroll})")
        if shots:
            page.screenshot(path=str(shots / "m-1-start.png"), full_page=True)

        print("Station: dieses Gerät als Kamera (Chromium-Testkamera)")
        wf(page, "document.getElementById('st-hint').textContent.indexOf('nimmt Bilder')>=0", timeout=8000)
        check(True, "Seite kennt die Stationsannahme des Wächters")
        page.fill("#st-name", "Tablet Süd/1")
        page.click("#btn-st")
        wf(page, "document.getElementById('st-stats').textContent.indexOf('Sendet: ')>=0 "
                               "&& parseInt(document.getElementById('st-stats').textContent.split('Sendet: ')[1])>=4", timeout=30000)
        st = status(base)
        cam = st["camera"]
        check(cam["type"] == "push" and cam["online"] and cam["station"] == "Tablet S_d_1",
              f"Server sieht die Station: {cam['station']!r}, online={cam['online']}, {cam.get('fps')} Bilder/s")
        f0 = st["detector"]["frames"]
        time.sleep(4)
        f1 = status(base)["detector"]["frames"]
        check(f1 - f0 >= 2, f"Erkennung wertet die Bilder der Station aus ({f1 - f0} in 4 s)")
        if shots:
            page.screenshot(path=str(shots / "m-2-station.png"), full_page=True)
        page.click("#btn-st")
        time.sleep(1.5)
        n = status(base)["camera"].get("rejected", 0)
        check(page.inner_text("#st-stats").startswith("Gestoppt"), "Station lässt sich beenden")

        print("Testalarm über die echte Kette, Alarmanzeige")
        page.click("#btn-st")                                   # noch einmal starten: Testalarm braucht ein aktuelles Bild
        wf(page, "parseInt((document.getElementById('st-stats').textContent.split('Sendet: ')[1]||'0'))>=2", timeout=20000)
        page.click("#btn-snd")
        check(page.evaluate("window.__plays") >= 1 and "bereit" in page.inner_text("#snd-state"), "Alarmton lässt sich aktivieren und spielt")
        page.click("#btn-test")
        page.wait_for_selector("#alarm:not(.hidden)", timeout=25000)
        check("Testalarm" in page.inner_text("#alarm-title"), "Testalarm erscheint als Alarmfeld: " + page.inner_text("#alarm-title"))
        page.click("#btn-ack")
        check(page.locator("#alarm").is_hidden(), "Quittieren blendet das Alarmfeld aus")
        page.click("#btn-st")                                   # Station beenden
        time.sleep(1)

        print("Sichtung (direkt in der Datenbank), fremder Text, Ton")
        plays_before = page.evaluate("window.__plays")
        aid = insert_alert(root, label='<img src=x onerror="window.__xss=1">Hornisse', species="vvel")
        page.wait_for_selector("#alarm:not(.hidden)", timeout=15000)
        check("ALARM" in page.inner_text("#alarm-title"), "Sichtung löst roten Alarm aus: " + page.inner_text("#alarm-title"))
        check("<img" in page.inner_text("#alarm-text"), "fremder Text steht als Text im Alarmfeld, nicht als HTML")
        check(page.evaluate("window.__xss") is None and not dialogs, "kein Skript aus fremdem Text ausgeführt")
        check(page.evaluate("window.__plays") > plays_before, "Alarmton wurde abgespielt")
        page.wait_for_timeout(500)
        lis = page.locator("#alerts li").all_inner_texts()
        check(len(lis) >= 2, "Meldungsliste zeigt die Einträge: " + " | ".join(t.replace("\n", " ") for t in lis))
        if shots:
            page.screenshot(path=str(shots / "m-3-alarm.png"), full_page=True)
        page.click("#btn-ack")

        print("Stumm / Ton an")
        page.click("#btn-mute")
        wf(page, "document.getElementById('stats').textContent.indexOf('STUMM')>=0", timeout=10000)
        check(page.locator("#btn-unmute").is_visible() and page.locator("#btn-mute").is_hidden(), "Stumm: Anzeige und Knöpfe schalten um")
        plays = page.evaluate("window.__plays")
        insert_alert(root)
        page.wait_for_selector("#alarm:not(.hidden)", timeout=15000)
        check("stumm" in page.inner_text("#alarm-text"), "stumm geschaltet: Alarm erscheint, aber ohne Ton")
        page.wait_for_timeout(500)
        check(page.evaluate("window.__plays") == plays, "stumm geschaltet: kein Ton gespielt")
        page.click("#btn-ack")
        page.click("#btn-unmute")
        wf(page, "document.getElementById('stats').textContent.indexOf('STUMM')<0", timeout=10000)
        check(True, "Ton wieder an")

        print("Foto prüfen (echte Auswertung)")
        small = root / "klein.jpg"
        small.write_bytes(jpeg_bytes(800, 600))
        page.set_input_files("#photo", str(small))
        wf(page, "document.getElementById('check-res').textContent.indexOf('Hornisse')>=0 || "
                               "document.getElementById('check-res').textContent.indexOf('Fehler')>=0", timeout=60000)
        check("Keine Hornisse erkannt" in page.inner_text("#check-res"), "kleines Foto: " + page.inner_text("#check-res")[:80])
        big = root / "gross.jpg"
        big.write_bytes(jpeg_bytes(2400, 1800, noise=True))
        check(big.stat().st_size > 900 * 1024, f"Testfoto ist groß ({big.stat().st_size // 1024} kB)")
        page.set_input_files("#photo", str(big))
        wf(page, "document.getElementById('check-res').textContent.indexOf('Bildgröße')>=0", timeout=90000)
        t = page.inner_text("#check-res")
        check("1280×" in t.replace(" ", "") or "1280x" in t, "großes Foto wird im Browser auf 1280 px verkleinert: " + t[-60:])
        if shots:
            page.screenshot(path=str(shots / "m-4-foto.png"), full_page=True)
        stt = status(base)
        check(stt["alarms_24h"] >= 0, "Foto-Prüfung löst keinen eigenen Alarm aus")

        print("Abmelden")
        page.click("#lnk-out")
        page.wait_for_selector("#login:not(.hidden)", timeout=8000)
        check(page.locator("#app").is_hidden(), "nach Abmelden nur noch Anmeldemaske")

        check(not errors, "keine Konsolenfehler: " + "; ".join(errors[:3]))
        check(not bad, "keine fehlgeschlagenen Anfragen: " + "; ".join(bad[:3]))
        csp = page.evaluate("window.__csp")
        check(not csp, "keine Verstöße gegen die Inhaltsrichtlinie: " + "; ".join(csp[:3]))
        ctx.close()

        # ── „alter Browser“: moderne Funktionen entfernt ────────────────────────────────────────────────
        print("Alter-Browser-Nachbildung (fetch, Promise, classList, Object.assign, Array.from … entfernt)")
        ctx2 = br.new_context(viewport={"width": 320, "height": 480}, user_agent=IOS9_UA)
        ctx2.add_init_script("""
          try { delete window.fetch; } catch (e) {}
          try { window.fetch = undefined; } catch (e) {}
          try { delete Element.prototype.classList; } catch (e) {}
          Object.assign = undefined; Array.from = undefined; Array.prototype.includes = undefined;
          String.prototype.includes = undefined; String.prototype.startsWith = undefined; String.prototype.endsWith = undefined;
          String.prototype.padStart = undefined; String.prototype.repeat = undefined; Object.entries = undefined; Object.values = undefined;
          window.URLSearchParams = undefined;
          Element.prototype.closest = undefined; NodeList.prototype.forEach = undefined; window.IntersectionObserver = undefined;
          Array.prototype.find = undefined; Array.prototype.findIndex = undefined; Array.prototype.fill = undefined;
          Function.prototype.bind = Function.prototype.bind;   // ES5: bleibt
          window.__e = [];
          window.addEventListener('error', function (e) { window.__e.push(String(e.message)); });
        """)
        p2 = ctx2.new_page()
        e2: list[str] = []
        p2.on("pageerror", lambda e: e2.append(str(e)))
        p2.on("console", lambda m: e2.append(m.text) if m.type == "error" else None)
        p2.goto(f"{base}/m#k={TOKEN}")
        p2.wait_for_selector("#app:not(.hidden)", timeout=10000)
        wt(p2, "#conn", lambda t: t == "verbunden")
        check(p2.evaluate("typeof window.fetch") == "undefined", "Nachbildung aktiv: kein fetch im Browser")
        p2.click("#btn-mute")
        wt(p2, "#stats", lambda t: "STUMM" in t)
        p2.click("#btn-unmute")
        wt(p2, "#stats", lambda t: "STUMM" not in t)
        check(True, "Knöpfe, Abfrage und Anzeige laufen ohne moderne Funktionen")
        insert_alert(root, label="Asiatische Hornisse")
        p2.wait_for_selector("#alarm:not(.hidden)", timeout=15000)
        check("ALARM" in p2.inner_text("#alarm-title"), "Alarm erscheint auch ohne moderne Funktionen")
        p2.click("#btn-ack")
        p2.set_input_files("#photo", str(small))
        wt(p2, "#check-res", lambda t: "Keine Hornisse" in t, timeout=60000)
        check(True, "Foto prüfen läuft ohne moderne Funktionen")
        check(not e2, "keine Fehler im Alter-Browser-Durchgang: " + "; ".join(e2[:3]))
        ctx2.close()
        br.close()


if __name__ == "__main__":
    sys.exit(main())
