# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende
"""Selbsttest:  python -m hornet.tools.selftest   (nach der Installation und nach jeder Änderung der .env)

Prüft Python, Pakete, ffmpeg, Modell, Demo-Kamera und – falls in der .env eingetragen – die echte Kamera.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from ..config import ROOT, Settings

OK, BAD, WARN = "  OK   ", " FEHLER", " HINWEIS"


def _grab(s: Settings, seconds: float) -> tuple[int, str, str]:
    from ..camera import Camera

    n = {"c": 0}

    def on(_j, _t):
        n["c"] += 1

    cam = Camera(s, on)
    cam.start()
    t0 = time.time()
    while time.time() - t0 < seconds and n["c"] < 4:
        time.sleep(0.3)
    state, err, label = cam.state, cam.error, cam.source_label
    cam.stop()
    return n["c"], (err or state), label


def main() -> int:
    bad = 0
    print(f"\nHornet3000 Selbsttest ({ROOT})\n")

    v = sys.version_info
    if (3, 10) <= (v.major, v.minor) <= (3, 13):
        print(f"{OK} Python {v.major}.{v.minor}.{v.micro}")
    else:
        print(f"{WARN} Python {v.major}.{v.minor}: empfohlen ist 3.10 bis 3.13 (onnxruntime-Pakete)")

    for mod in ("fastapi", "uvicorn", "httpx", "PIL", "numpy", "onnxruntime", "pywebpush", "serial"):
        try:
            m = __import__(mod)
            print(f"{OK} Paket {mod} {getattr(m, '__version__', '')}")
        except Exception as e:
            print(f"{BAD} Paket {mod}: {e}  -> pip install -r requirements.txt")
            bad += 1

    s = Settings.from_env()
    try:
        from ..camera import find_ffmpeg

        ff = find_ffmpeg(s.ffmpeg_bin)
        ver = subprocess.run([ff, "-version"], capture_output=True, text=True, timeout=15).stdout.splitlines()[0]
        print(f"{OK} ffmpeg: {ver[:60]}")
    except Exception as e:
        print(f"{BAD} ffmpeg: {e}")
        bad += 1

    try:
        from PIL import Image

        from ..detector import YoloOnnx

        t0 = time.time()
        m = YoloOnnx(s.resolve_model(), providers=s.ort_providers or None)
        t1 = time.time()
        m.detect(Image.new("RGB", (960, 540), (90, 110, 80)))
        ms = (time.time() - t1) * 1000
        print(f"{OK} Modell {Path(s.model_path).name}: Klassen {list(m.names.values())}, Rechner {m.provider}, "
              f"{ms:.0f} ms pro Bild (Laden {t1 - t0:.1f} s)")
        missing = [c for c in s.alert_classes + s.protected_classes if c not in m.names.values()]
        if missing:
            print(f"{BAD} ALERT_CLASSES/PROTECTED_CLASSES nicht im Modell: {missing}")
            bad += 1
        if ms > 900:
            print(f"{WARN} {ms:.0f} ms pro Bild ist langsam – DETECT_FPS in der .env senken (z. B. 1)")
    except Exception as e:
        print(f"{BAD} Modell: {e}")
        bad += 1

    demo = Settings.from_env()
    demo.camera_source, demo.data_dir = "selftest", ROOT / "data" / "selftest"
    n, info, label = _grab(demo, 15)
    if n >= 2:
        print(f"{OK} Kamera-Kette (ffmpeg-Testgenerator): {n} Bilder in wenigen Sekunden")
    else:
        print(f"{BAD} Kamera-Kette: keine Bilder – {info}")
        bad += 1

    if s.camera_source.strip():
        real = Settings.from_env()
        real.data_dir = ROOT / "data" / "selftest_real"
        print(f"      Verbinde mit deiner Kamera (bis zu 25 s) …")
        n, info, label = _grab(real, 25)
        if n >= 2:
            print(f"{OK} Kamera erreichbar ({label}): {n} Bilder")
        else:
            print(f"{BAD} Kamera nicht erreichbar ({label}): {info}")
            print("        Prüfen: Adresse/Benutzer/Passwort, RTSP in der Kamera aktiviert, PC und Kamera im selben Netz,")
            print("        Sonderzeichen im Passwort URL-kodieren (@ = %40, : = %3A).")
            bad += 1
    else:
        print(f"{WARN} Noch keine Kamera eingerichtet – in der App unter „Einrichtung“ eintragen.")

    chans = []
    if s.telegram_bot_token and s.telegram_chat_ids:
        chans.append("Telegram")
    if s.whatsapp_provider == "cloud" and s.whatsapp_token and s.whatsapp_phone_id and s.whatsapp_to:
        chans.append("WhatsApp (Cloud)")
    if s.whatsapp_provider == "callmebot" and s.callmebot_phone and s.callmebot_apikey:
        chans.append("WhatsApp (CallMeBot, nur Text)")
    if s.sms_url and s.sms_user and s.sms_password and s.sms_to:
        chans.append("SMS")
    print(f"{OK if chans else WARN} Meldewege in der .env: {', '.join(chans) if chans else 'keine – nur die App zeigt Alarme (Einrichtung in der App)'}")
    print(f"{OK if s.public_url else WARN} Adresse für Links: {s.public_url or 'nicht gesetzt – Nachrichten enthalten keinen Link zu Foto/Video'}")

    # Funknetz (nur prüfen, was eingeschaltet ist – ohne etwas zu senden)
    if s.mesh_lora_enabled:
        try:
            from ..mesh.lora import check_port, find_port

            port = check_port(s.mesh_lora_port or "auto")
            port = find_port() if port == "auto" else port
            if not Path(port).exists() and not port.upper().startswith("COM"):
                raise OSError(f"{port} existiert nicht – Funkgerät angesteckt?")
            print(f"{OK} Funknetz LoRa: Anschluss {port}")
        except Exception as e:
            print(f"{BAD} Funknetz LoRa: {e}")
            bad += 1
    if s.mesh_freenet_enabled:
        try:
            import socket
            from urllib.parse import urlsplit

            from ..mesh.freenet import check_node, resolve_riverctl

            rc = resolve_riverctl(s.mesh_freenet_riverctl)
            u = urlsplit(check_node(s.mesh_freenet_node))
            with socket.create_connection((u.hostname, u.port or 7509), timeout=3):
                pass
            print(f"{OK} Funknetz Freenet: riverctl {rc}, Knoten {u.hostname}:{u.port} erreichbar")
        except Exception as e:
            print(f"{BAD} Funknetz Freenet: {e}")
            bad += 1
    if not (s.mesh_lora_enabled or s.mesh_freenet_enabled):
        print(f"{WARN} Funknetz ausgeschaltet (optional) – Einrichtung in der App, Reiter „Einrichtung“.")

    print("\n" + ("Alles bereit." if not bad else f"{bad} Problem(e) gefunden – oben nachlesen."))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())