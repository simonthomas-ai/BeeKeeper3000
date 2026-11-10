#!/usr/bin/python3
"""Browser-Prüfung der Oberfläche mit echtem Chromium (Playwright) gegen das ECHTE Programm als eigenen Prozess.

Prüft: Anmeldung über den Zugangslink, alle Reiter ohne Konsolenfehler, keine Verstöße gegen die Inhaltsrichtlinie
(CSP), Funknetz-Reiter (Live-Eingang einer Meldung, Test senden, fremder Text wird nur als Text angezeigt, nie als HTML),
Einrichtung weist ungültige Funknetz-Werte ab, Handy-Seite ist formatiert, fremde Webseite kann nichts auslösen (CSRF).
Das Funkgerät ist eine TESTATTRAPPE (Pseudo-Terminal). Aufruf (System-Python mit Playwright):
    /usr/bin/python3 tests/browser/check_ui.py [--venv-python /home/claude/venv/bin/python] [--shots DIR]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[2]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


mesh_device = _load("mesh_device", REPO / "tests/fakes/mesh_device.py")
wire = _load("wire", REPO / "hornet/mesh/wire.py")
TOKEN = "browser-" + "t" * 30
KEY = bytes(range(16))
problems: list[str] = []
checks = 0


def check(cond: bool, msg: str) -> None:
    global checks
    checks += 1
    if not cond:
        problems.append(msg)
        print("  ✗", msg, flush=True)
    else:
        print("  ✓", msg, flush=True)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--venv-python", default="/home/claude/venv/bin/python")
    ap.add_argument("--shots", default="")
    a = ap.parse_args()
    shots = Path(a.shots) if a.shots else None
    if shots:
        shots.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="hornet-ui-"))
    for n in ("hornet", "web"):
        shutil.copytree(REPO / n, root / n, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy(REPO / "hornet_run.py", root / "hornet_run.py")
    (root / "models").symlink_to(REPO / "models")
    dev = mesh_device.FakeMeshDevice(channels={1: ("hornet3000", KEY)})
    port = free_port()
    env = {"HOST": "127.0.0.1", "PORT": str(port), "ACCESS_TOKEN": TOKEN, "CAMERA_NAME": "UI-Stand",
           "CAMERA_SOURCE": "selftest", "CLIP_ENABLED": "false", "MESH_LORA_ENABLED": "true",
           "MESH_LORA_PORT": dev.path, "MESH_LORA_CHANNEL_KEY": KEY.hex(), "MESH_STATION": "UI-Stand",
           "VERIFY_PROVIDER": "none"}
    (root / ".env").write_text("".join(f"{k}={v}\n" for k, v in env.items()))
    log = open(root / "run.log", "wb")
    srv = subprocess.Popen([a.venv_python, "-I", str(root / "hornet_run.py"), "run"], cwd=root, stdout=log, stderr=log,
                           stdin=subprocess.DEVNULL, start_new_session=True)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(150):
            try:
                if urllib.request.urlopen(base + "/api/health", timeout=1).status == 200:
                    break
            except Exception:  # noqa: BLE001
                time.sleep(0.2)
        else:
            print("Programm startet nicht", (root / "run.log").read_text()[-800:])
            return 2
        run_checks(base, dev, shots, port)
    finally:
        srv.terminate()
        try:
            srv.wait(15)
        except subprocess.TimeoutExpired:
            srv.kill()
        dev.close()
        shutil.rmtree(root, ignore_errors=True)
    print(f"\n{checks} Prüfungen, {len(problems)} Verstöße")
    if problems:
        print("BROWSER: DURCHGEFALLEN")
        for p in problems:
            print(" -", p)
        return 1
    print("BROWSER: BESTANDEN")
    return 0


def run_checks(base: str, dev, shots: Path | None, port: int) -> None:
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        ctx = br.new_context(viewport={"width": 1100, "height": 900}, device_scale_factor=1)
        errors: list[str] = []
        csp: list[str] = []
        bad_resp: list[str] = []
        ctx.add_init_script("window.__csp=[];document.addEventListener('securitypolicyviolation',e=>window.__csp.push("
                            "e.violatedDirective+' '+e.blockedURI+' '+e.sourceFile+':'+e.lineNumber+' '+(e.sample||'')));")
        page = ctx.new_page()
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append("pageerror: " + str(e)))
        page.on("response", lambda r: bad_resp.append(f"{r.status} {r.url}") if r.status >= 400 and "/api/login" not in r.url
                else None)
        dialogs: list[str] = []
        page.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))

        print("Anmeldung")
        page.goto(f"{base}/")
        page.wait_for_timeout(800)
        check(page.locator("#login").is_visible(), "ohne Schlüssel erscheint die Anmeldung")
        page.fill("#login input", "falsch") if page.locator("#login input").count() else None
        page.goto(f"{base}/?t={TOKEN}")
        page.wait_for_selector("nav.tabs a[data-tab=live]", timeout=8000)
        check(page.locator("#login").is_hidden(), "Zugangslink meldet an")
        check(page.title() != "", "Seite hat einen Titel")

        print("Reiter")
        for tab in ("live", "alarme", "funk", "einrichtung", "wissen"):
            page.click(f"nav.tabs a[data-tab={tab}]")
            page.wait_for_timeout(700)
            check(page.locator(f"#v-{tab}").is_visible(), f"Reiter {tab} sichtbar")
            if shots:
                page.screenshot(path=str(shots / f"tab-{tab}.png"))

        print("Funknetz")
        page.click("nav.tabs a[data-tab=funk]")
        page.wait_for_timeout(600)
        check(page.locator("#funk-off").is_hidden(), "Funknetz als aktiv angezeigt")
        check("UI-Stand" in page.locator("#funk-ways").inner_text(), "Stationsname angezeigt")
        page.wait_for_function("() => document.querySelector('#funk-ways').innerText.includes('verbunden')", timeout=15000)
        check("nicht verbunden" not in page.locator("#funk-ways").inner_text(), "Funkgerät verbunden angezeigt")
        # Eingang einer Meldung: erscheint live im Protokoll; Texte mit HTML werden nur als Text gezeigt
        evil = "<img src=x onerror=alert(1)> <b>fett</b>"
        dev.inject_channel_text(wire.encode(wire.MeshMessage("A", "0badcafe", "Nachbar <i>Süd</i>", 3, 91, "J", None, None,
                                                           evil), 400), sender="Nachbar")
        try:
            page.wait_for_function("() => document.querySelector('#funk-log').innerText.includes('Sichtung')", timeout=15000)
            got = True
        except Exception:  # noqa: BLE001
            page.click("nav.tabs a[data-tab=alarme]")
            page.click("nav.tabs a[data-tab=funk]")
            page.wait_for_timeout(1500)
            got = "Sichtung" in page.locator("#funk-log").inner_text()
        check(got, "empfangene Meldung erscheint im Funk-Protokoll")
        check(page.locator("#funk-log img, #funk-log b, #funk-log i").count() == 0, "fremder Text wird nicht als HTML gedeutet")
        check(not dialogs, "kein Skript aus Funktext ausgeführt")
        page.click("#btn-funk-test")
        page.wait_for_timeout(2500)
        txt = page.locator("#funk-log").inner_text()
        check("Test" in txt or "gesendet" in txt, "Funknetz-Test erscheint im Protokoll")
        if shots:
            page.screenshot(path=str(shots / "funknetz.png"), full_page=True)

        print("Einrichtung")
        page.click("nav.tabs a[data-tab=einrichtung]")
        page.wait_for_timeout(1200)
        body = page.locator("#v-einrichtung").inner_text()
        check("Funknetz" in body, "Einrichtung enthält den Funknetz-Abschnitt")
        field = page.locator("#s-MESH_LORA_PORT")
        if field.count():
            field.fill("/etc/passwd")
            btn = page.locator("#v-einrichtung button.primary, #v-einrichtung button:has-text('Speichern')").first
            btn.click()
            page.wait_for_timeout(1200)
            check("erlaubt" in page.inner_text("body") or "ungültig" in page.inner_text("body").lower()
                  or "Fehler" in page.inner_text("body"), "ungültiger Funkanschluss wird mit Meldung abgelehnt")
        else:
            check(False, "Feld MESH_LORA_PORT gefunden")

        print("Handy-Seite")
        p2 = ctx.new_page()
        p2.set_viewport_size({"width": 390, "height": 800})
        p2.goto(f"{base}/phone")
        p2.wait_for_timeout(800)
        bg = p2.evaluate("() => getComputedStyle(document.body).backgroundColor")
        check(bg not in ("rgba(0, 0, 0, 0)", "rgb(255, 255, 255)"), f"Handy-Seite ist formatiert (Hintergrund {bg})")
        check(p2.evaluate("() => window.__csp.length") == 0, "Handy-Seite ohne CSP-Verstoß")
        if shots:
            p2.screenshot(path=str(shots / "phone.png"))
        p2.close()

        print("Fremde Webseite (CSRF)")
        p3 = ctx.new_page()
        p3.route("http://evil.example/**", lambda r: r.fulfill(status=200, content_type="text/html", body=f"""<!doctype html>
<form id=f method=POST action="{base}/api/mute"><input name=x value=1></form>
<script>
fetch("{base}/api/mute",{{method:"POST",credentials:"include",mode:"no-cors",headers:{{"Content-Type":"text/plain"}},body:"{{}}"}});
fetch("{base}/api/mesh/test",{{method:"POST",credentials:"include",mode:"no-cors"}});
document.getElementById("f").submit();
</script>"""))
        p3.goto("http://evil.example/")
        p3.wait_for_timeout(1500)
        p3.close()
        st = json.loads(page.evaluate("(u) => fetch(u).then(r => r.text())", f"{base}/api/status"))
        check(st.get("muted") in (False, None, 0) or not st.get("muted"), "Anfragen einer fremden Seite lösen nichts aus (nicht stummgeschaltet)")
        mesh = json.loads(page.evaluate("(u) => fetch(u).then(r => r.text())", f"{base}/api/mesh"))
        check(sum(1 for m in mesh["messages"] if m["typ"] == "T" and m["direction"] == "out") <= 1,
              "fremde Seite konnte keinen zweiten Funk-Test auslösen")

        print("Sammelprüfung")
        csp_all = page.evaluate("() => window.__csp")
        check(not csp_all, f"keine CSP-Verstöße auf der Hauptseite {csp_all[:3]}")
        real_err = [e for e in errors if "evil.example" not in e and "ERR_FAILED" not in e and "ERR_ABORTED" not in e
                    and "403" not in e and "mjpg" not in e]
        check(not real_err, f"keine Konsolenfehler {real_err[:3]}")
        real_bad = [r for r in bad_resp if "evil.example" not in r and "/api/mute" not in r and "/api/mesh/test" not in r
                    and "/api/setup" not in r]
        check(not real_bad, f"keine fehlgeschlagenen Anfragen {real_bad[:3]}")
        hdr = page.evaluate("(u) => fetch(u).then(r => [r.headers.get('content-security-policy'), r.headers.get('x-content-type-options'), r.headers.get('x-frame-options')])", f"{base}/")
        check(all(hdr), f"Sicherheits-Kopfzeilen gesetzt {hdr[1:]}")
        br.close()


if __name__ == "__main__":
    sys.exit(main())
