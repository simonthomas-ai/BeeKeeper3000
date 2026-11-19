#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende
"""Übertragungstest: ECHTER Hornet3000-Server (eigener Prozess, ffmpeg, Modell, Datenbank) gegen die TESTATTRAPPE der ESP32-Kamera.

Echt:        Hornet3000-Programm, ffmpeg-Lesen des Mehrteil-Stroms, JPEG-Zerlegung, Erkennung, Statusanzeige,
             die Rahmen des Stroms (gebaut vom ECHTEN Firmware-Code core.cpp über das Hilfsprogramm framer).
Attrappe:    die Kamera selbst (tools/emulator.py) – WLAN, Sensor, Speicher und Neustart-Logik der Firmware sind NICHT getestet.

Prüft: 1 Bilder fließen und werden ausgewertet   2 Wiederverbindung nach Abriss der Übertragung
       3 falscher/fehlender Zugangsschlüssel → Kamera-Fehler ohne Absturz, Dienst bleibt bedienbar
       4 der Zugangsschlüssel der Kamera taucht nirgends auf (Status, Meldungsverlauf, Programm-Protokoll, Support-Daten)
Aufruf: python tools/integration_test.py --hornet-dir /pfad/zu/hornet3000 --framer /pfad/zu/framer [--python /pfad/python]
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import emulator  # noqa: E402

violations: list[str] = []


def fail(msg: str) -> None:
    violations.append(msg)
    print("VERSTOSS:", msg, flush=True)


def wait_until(cond, timeout=30, step=0.25) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(step)
    return cond()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hornet-dir", required=True)
    ap.add_argument("--framer", required=True)
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    hd = Path(a.hornet_dir).resolve()
    sys.path.insert(0, str(hd))
    sys.path.insert(0, str(hd / "tests" / "stability"))
    import soak  # noqa: E402  (nutzt dieselbe Prozess-Steuerung wie der Dauerlauf des Servers)

    CAM_TOKEN = "esp32-GEHEIM-" + "q7Z" * 8
    cam_port = soak.free_port()
    root = Path(tempfile.mkdtemp(prefix="h3k-esp-"))
    inst = soak.Instance(root, "/dev/null", src=hd, python=a.python)
    inst.prepare()

    def env(src: str) -> None:
        inst.write_env({"CAMERA_SOURCE": src, "MESH_LORA_ENABLED": "false", "MESH_LORA_PORT": "",
                        "MESH_LORA_CHANNEL_KEY": ""})

    good = f"http://127.0.0.1:{cam_port}/stream?t={CAM_TOKEN}"
    srv = emulator.serve(cam_port, CAM_TOKEN, a.framer, fps=8)

    # ── 1 Bilder fließen ───────────────────────────────────────────────────────────────────────────
    env(good)
    inst.start()
    c = inst.client()
    ok = wait_until(lambda: c.get("/api/status").json()["camera"]["online"], 45)
    st = c.get("/api/status").json()
    if not ok:
        fail(f"Kamera wurde nicht online: {st['camera']}")
    else:
        f0 = st["detector"]["frames"]
        time.sleep(6)
        f1 = c.get("/api/status").json()["detector"]["frames"]
        print(f"1  Bilder ausgewertet in 6 s: {f1 - f0} (Detektor geladen: {st['detector']['loaded']})", flush=True)
        if f1 - f0 < 3:
            fail(f"zu wenige Bilder ausgewertet ({f1 - f0})")
        snap = c.get("/api/snapshot.jpg")
        if snap.status_code != 200 or not snap.content.startswith(b"\xff\xd8"):
            fail(f"Standbild nicht abrufbar: {snap.status_code}")
        else:
            print(f"   Standbild vom Server: {len(snap.content)} Byte JPEG", flush=True)

    # ── 2 Wiederverbindung: Übertragung reißt nach 10 Bildern ab, Server muss sich neu verbinden ──
    emulator.STATE["drop_after"] = 10
    base = emulator.STATE["frames"]
    time.sleep(1)
    reconnects = 0
    seen_offline = False
    end = time.time() + 40
    while time.time() < end and reconnects < 2:
        cam = c.get("/api/status").json()["camera"]
        if cam["restarts"] > reconnects:
            reconnects = cam["restarts"]
        seen_offline |= not cam["online"]
        time.sleep(0.3)
    print(f"2  Abrisse: Server hat sich {reconnects}-mal neu verbunden (Kamera zwischendurch offline: {seen_offline})",
          flush=True)
    if reconnects < 2:
        fail(f"keine Wiederverbindung nach Abriss (restarts={reconnects})")
    emulator.STATE["drop_after"] = 0
    if not wait_until(lambda: c.get("/api/status").json()["camera"]["online"], 60):
        fail("Kamera nach Abriss-Serie nicht wieder online")
    else:
        print("   danach wieder online", flush=True)

    # ── 3 Attrappe wird beendet und kommt zurück ──────────────────────────────────────────────────
    emulator.stop(srv)
    if not wait_until(lambda: not c.get("/api/status").json()["camera"]["online"], 40):
        fail("Kamera gilt nach Ausfall der Attrappe weiter als online")
    srv = emulator.serve(cam_port, CAM_TOKEN, a.framer, fps=8)
    if not wait_until(lambda: c.get("/api/status").json()["camera"]["online"], 90):
        fail("Kamera kam nach Neustart der Attrappe nicht zurück")
    else:
        print("3  Attrappe weg → Kamera offline; Attrappe zurück → wieder online", flush=True)
    c.close()
    inst.stop(hard=False)

    # ── 4 Falscher Schlüssel: Fehler sichtbar, aber ohne den Schlüssel; Dienst bleibt bedienbar ──
    wrong = f"http://127.0.0.1:{cam_port}/stream?t=FALSCH-{CAM_TOKEN[:6]}"
    env(wrong)
    inst.start()
    c = inst.client()
    errors_seen: set[str] = set()
    end = time.time() + 30                       # Fehlertext wechselt je Versuch → laufend einsammeln
    while time.time() < end:
        errors_seen.add(c.get("/api/status").json()["camera"]["error"])
        time.sleep(0.25)
    st = c.get("/api/status")
    if st.status_code != 200:
        fail(f"Status nicht abrufbar bei falschem Kamera-Schlüssel: {st.status_code}")
    cam = st.json()["camera"]
    print(f"4  falscher Schlüssel: state={cam['state']} online={cam['online']}; gesehene Fehlertexte: "
          f"{[e[:200] for e in sorted(errors_seen) if e]}", flush=True)
    if cam["online"]:
        fail("Kamera mit falschem Schlüssel als online gemeldet")
    if emulator.STATE["fail_auth"] == 0:
        fail("Attrappe hat keinen abgewiesenen Zugriff gesehen")
    for path in ("/api/alerts", "/api/mesh", "/"):
        r = c.get(path)
        if r.status_code != 200:
            fail(f"{path} nicht bedienbar bei Kamera-Fehler: {r.status_code}")

    # ── 5 Schlüssel-Leck-Suche ────────────────────────────────────────────────────────────────────
    needles = [CAM_TOKEN, CAM_TOKEN[:12] + CAM_TOKEN[-8:], f"FALSCH-{CAM_TOKEN[:6]}"]
    hay: dict[str, str] = {"gesammelte Kamera-Fehlertexte": "\n".join(errors_seen)}
    for p in ("/api/status", "/api/alerts", "/api/mesh", "/api/mesh/messages", "/api/health"):
        r = c.get(p)
        hay[p] = r.text
    c.close()
    inst.stop(hard=False)
    hay["Programm-Protokoll (run.log)"] = (inst.root / "run.log").read_text(errors="replace")
    for logf in (inst.root / "data").rglob("*.log"):
        hay[str(logf.relative_to(inst.root))] = logf.read_text(errors="replace")
    leaks = 0
    for where, text in hay.items():
        for n in needles:
            if n in text:
                leaks += 1
                fail(f"Kamera-Schlüssel {n[:10]}… taucht auf in: {where}")
    print(f"5  Leck-Suche in {len(hay)} Quellen: {leaks} Funde", flush=True)

    emulator.stop(srv)
    print(json.dumps({"frames_gesendet": emulator.STATE["frames"], "abgewiesen": emulator.STATE["fail_auth"]}), flush=True)
    print("ESP32-ÜBERTRAGUNG: BESTANDEN" if not violations else f"ESP32-ÜBERTRAGUNG: {len(violations)} VERSTÖSSE", flush=True)
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
