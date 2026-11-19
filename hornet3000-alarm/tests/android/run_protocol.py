#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende
"""Prüft den Netzwerk- und Ablaufteil der Android-App (reines Java) gegen das ECHTE Programm.

Ablauf: Das Programm (Wächter) wird als eigener Prozess gestartet – einmal per HTTP, einmal per HTTPS mit selbst erzeugtem
Zertifikat; dann läuft android/test/…/ProtocolTest.java in der JVM gegen beide. Die Java-Quellen sind DIESELBEN Dateien, die
auch in die APK kommen (alle ohne android.*-Importe; das prüft dieses Skript ebenfalls).
Behelf (nur in diesem Test): Bilddateien statt Kamera, ein TCP-Proxy für Ausfälle, ein absichtlich schlechter Mini-Server.
Nicht geprüft: Kamera, Oberfläche, Ton – dafür gibt es hier kein Gerät.
Aufruf:  python3 tests/android/run_protocol.py [--venv-python /home/claude/venv/bin/python] [--app-dir DIR]
"""
from __future__ import annotations

import argparse
import io
import random
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TOKEN = "android-" + "a" * 30
ANDROID = REPO / "android"
SRC = ANDROID / "src" / "org" / "hornet3000" / "station"
TESTSRC = ANDROID / "test" / "org" / "hornet3000" / "station" / "ProtocolTest.java"
# Diese Klassen müssen reines Java sein (laufen in der JVM-Prüfung); alle anderen dürfen android.* benutzen.
PURE = {"AlertTracker", "ApiException", "Client", "Json", "Logic", "Model", "PollLoop", "StationLoop", "TlsFactory"}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def make_images(d: Path) -> None:
    from PIL import Image, ImageDraw

    rnd = random.Random(5)
    im = Image.new("RGB", (640, 480), (110, 140, 80))
    dr = ImageDraw.Draw(im)
    for _ in range(60):
        x, y = rnd.randrange(640), rnd.randrange(480)
        dr.ellipse([x, y, x + rnd.randrange(8, 60), y + rnd.randrange(8, 60)], fill=tuple(rnd.randrange(256) for _ in range(3)))
    b = io.BytesIO()
    im.save(b, "JPEG", quality=80)
    (d / "ok.jpg").write_bytes(b.getvalue())
    (d / "truncated.jpg").write_bytes(b.getvalue()[: len(b.getvalue()) * 6 // 10])
    wide = io.BytesIO()
    Image.new("RGB", (4100, 32), (1, 2, 3)).save(wide, "JPEG")
    (d / "wide.jpg").write_bytes(wide.getvalue())
    noise = Image.frombytes("RGB", (1600, 1200), bytes(rnd.randrange(256) for _ in range(1600 * 1200 * 3)))
    big = io.BytesIO()
    noise.save(big, "JPEG", quality=95)
    assert len(big.getvalue()) > (1 << 20), len(big.getvalue())
    (d / "big.jpg").write_bytes(big.getvalue())
    png = io.BytesIO()
    im.save(png, "PNG")
    (d / "fake.jpg").write_bytes(png.getvalue())


def start_server(src: Path, root: Path, port: int, venv_python: str, extra: dict[str, str]):
    for n in ("hornet", "web"):
        shutil.copytree(src / n, root / n, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy(src / "hornet_run.py", root / "hornet_run.py")
    (root / "models").symlink_to(src / "models")
    if (src / "lib").exists():
        (root / "lib").symlink_to(src / "lib")
    env = {"HOST": "127.0.0.1", "PORT": str(port), "ACCESS_TOKEN": TOKEN, "CAMERA_NAME": "Android-Stand",
           "CAMERA_SOURCE": "push", "CLIP_ENABLED": "false", "VERIFY_PROVIDER": "none", **extra}
    (root / ".env").write_text("".join(f"{k}={v}\n" for k, v in env.items()))
    log = open(root / "run.log", "wb")
    return subprocess.Popen([venv_python, "-I", str(root / "hornet_run.py"), "run"], cwd=root, stdout=log, stderr=log,
                            stdin=subprocess.DEVNULL, start_new_session=True)


def wait_up(url: str, root: Path, cafile: str | None = None) -> bool:
    import ssl

    ctx = ssl.create_default_context(cafile=cafile) if cafile else None
    for _ in range(250):
        try:
            if urllib.request.urlopen(url + "/api/health", timeout=1, context=ctx).status == 200:
                return True
        except Exception:  # noqa: BLE001
            time.sleep(0.2)
    print("Programm startet nicht:", (root / "run.log").read_text()[-1500:])
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--venv-python", default="/home/claude/venv/bin/python")
    ap.add_argument("--app-dir", default="")
    ap.add_argument("--no-https", action="store_true")
    a = ap.parse_args()
    src = Path(a.app_dir) if a.app_dir else REPO

    # 1) nur reines Java in den als „rein“ gekennzeichneten Klassen
    problems = []
    for f in sorted(SRC.glob("*.java")):
        uses_android = bool(re.search(r"^\s*import\s+android\.", f.read_text(encoding="utf-8"), re.M))
        if f.stem in PURE and uses_android:
            problems.append(f"{f.name} soll reines Java sein, importiert aber android.*")
        if f.stem not in PURE and not uses_android:
            problems.append(f"{f.name} ist nicht als rein gelistet, benutzt aber kein android.* – in PURE eintragen und in der JVM prüfen")
    missing = [n for n in PURE if not (SRC / f"{n}.java").is_file()]
    if missing or problems:
        print("Quellen-Aufteilung:", missing, problems)
        return 1
    print(f"Quellen: {len(PURE)} reine Klassen werden in der JVM geprüft")

    tmp = Path(tempfile.mkdtemp(prefix="hornet-android-"))
    procs = []
    try:
        out = tmp / "classes"
        out.mkdir()
        cmd = ["javac", "-Xlint:all,-deprecation", "-Werror", "-encoding", "UTF-8", "-d", str(out), *[str(SRC / f"{n}.java") for n in sorted(PURE)], str(TESTSRC)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        err = "\n".join(l for l in r.stderr.splitlines() if "JAVA_TOOL_OPTIONS" not in l)
        if r.returncode != 0:
            print("Übersetzung fehlgeschlagen:\n" + err)
            return 1
        imgs = tmp / "img"
        imgs.mkdir()
        make_images(imgs)

        root = tmp / "app-http"
        root.mkdir()
        port = free_port()
        procs.append(start_server(src, root, port, a.venv_python, {}))
        base = f"http://127.0.0.1:{port}"
        if not wait_up(base, root):
            return 2
        args = [base, TOKEN, str(imgs)]

        if not a.no_https:
            cert, key = tmp / "cert.pem", tmp / "key.pem"
            subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key), "-out", str(cert), "-days", "30",
                            "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1"], check=True, capture_output=True)
            fp = subprocess.run(["openssl", "x509", "-in", str(cert), "-noout", "-fingerprint", "-sha256"], check=True, capture_output=True,
                                text=True).stdout.strip().split("=", 1)[1]
            root2 = tmp / "app-https"
            root2.mkdir()
            port2 = free_port()
            procs.append(start_server(src, root2, port2, a.venv_python, {"SSL_CERTFILE": str(cert), "SSL_KEYFILE": str(key)}))
            base2 = f"https://127.0.0.1:{port2}"
            if not wait_up(base2, root2, cafile=str(cert)):
                return 2
            args += [base2, fp]

        print("Starte Java-Prüfung …", flush=True)
        j = subprocess.run(["java", "-cp", str(out), "org.hornet3000.station.ProtocolTest", *args], text=True, stdout=sys.stdout, stderr=subprocess.PIPE)
        for l in j.stderr.splitlines():
            if "JAVA_TOOL_OPTIONS" not in l:
                print(l)
        # Zustand des Programms nach der Prüfung: lief es sauber (keine Abstürze im Protokoll)?
        log = (tmp / "app-http" / "run.log").read_text(errors="replace")
        bad = [l for l in log.splitlines() if "Traceback" in l or "Exception" in l]
        print(f"Programm-Protokoll: {len(log.splitlines())} Zeilen, {len(bad)} Auffälligkeiten")
        for l in bad[:10]:
            print("  !", l[:200])
        return j.returncode or (1 if bad else 0)
    finally:
        for p in procs:
            p.terminate()
            try:
                p.wait(15)
            except subprocess.TimeoutExpired:
                p.kill()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
