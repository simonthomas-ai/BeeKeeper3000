#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende
"""TESTATTRAPPE der ESP32-Kamera (nur zum Prüfen des Hornet3000-Wächters, nicht für den Betrieb).

Spricht dieselben Adressen wie die Firmware (/status, /jpg, /stream, /reboot) und prüft den Zugangsschlüssel nach derselben Regel.
Die Rahmen der Übertragung baut der ECHTE Firmware-Code (framer, aus src/core.cpp). Bilder: eigene Testbilder (PIL).
Nicht nachgebildet: WLAN, Kamera-Sensor, Speicher, Neustart-Logik der Firmware (dafür: Firmware-Bau + Host-Tests der Logik)."""
from __future__ import annotations

import argparse
import io
import struct
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from PIL import Image, ImageDraw

STATE = {"token": "", "streaming": False, "frames": 0, "framer": "", "fps": 8, "drop_after": 0, "fail_auth": 0}
ABORT = threading.Event()          # beendet laufende Übertragungen sofort (Kamera „fällt aus“)
LOCK = threading.Lock()


def make_frame(i: int, size=(640, 480)) -> bytes:
    im = Image.new("RGB", size, (92 + i % 40, 110, 70))
    d = ImageDraw.Draw(im)
    x = (i * 9) % size[0]
    d.ellipse((x, 200, x + 60, 260), fill=(230, 180, 20))          # bewegtes Objekt
    d.text((10, 10), f"ESP32-CAM TESTATTRAPPE  Bild {i}", fill=(255, 255, 255))
    b = io.BytesIO()
    im.save(b, "JPEG", quality=70)
    return b.getvalue()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):  # still
        pass

    def _auth(self) -> bool:
        q = parse_qs(urlparse(self.path).query)
        given = (q.get("t") or [self.headers.get("X-Token", "")])[0]
        ok = bool(STATE["token"]) and given == STATE["token"]
        if not ok:
            STATE["fail_auth"] += 1
            body = b"Zugangsschluessel fehlt oder falsch\n"
            self.send_response(401)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        return ok

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            body = b"Hornet3000 ESP32-Kamera (TESTATTRAPPE)\n"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/status" and self._auth():
            body = (b'{"version":"1.0.0","hostname":"emulator","width":640,"height":480,"streaming":%s,"frames":%d}'
                    % (b"true" if STATE["streaming"] else b"false", STATE["frames"]))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/jpg" and self._auth():
            body = make_frame(int(time.time() * 8))
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/stream" and self._auth():
            self._stream()
        elif path not in ("/status", "/jpg", "/stream"):
            self.send_error(404)

    def _stream(self):
        with LOCK:
            if STATE["streaming"]:                      # wie die Firmware: nur ein Zuschauer
                body = b"es laeuft schon eine Uebertragung\n"
                self.send_response(503)
                self.send_header("Retry-After", "5")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            STATE["streaming"] = True
        fr = subprocess.Popen([STATE["framer"]], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        try:
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace;boundary=h3kframe")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Transfer-Encoding", "chunked")      # wie esp_http_server bei httpd_resp_send_chunk()
            self.end_headers()
            i, sent = 0, 0
            while not ABORT.is_set():
                jpg = make_frame(i)
                fr.stdin.write(struct.pack("<I", len(jpg)) + jpg)
                fr.stdin.flush()
                head = b""
                # Teil lesen: Kopf endet mit \r\n\r\n, dann Content-Length Byte JPEG
                while not head.endswith(b"\r\n\r\n"):
                    ch = fr.stdout.read(1)
                    if not ch:
                        return
                    head += ch
                body = fr.stdout.read(len(jpg))
                # Die Firmware sendet Kopf und Bild als zwei getrennte Stücke (httpd_resp_send_chunk) → zwei Chunks
                self.wfile.write(b"%x\r\n" % len(head) + head + b"\r\n")
                self.wfile.write(b"%x\r\n" % len(body) + body + b"\r\n")
                self.wfile.flush()
                STATE["frames"] += 1
                i += 1
                sent += 1
                if STATE["drop_after"] and sent >= STATE["drop_after"]:
                    return                                # Verbindung abreißen lassen (Test der Wiederverbindung)
                time.sleep(1.0 / STATE["fps"])
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            STATE["streaming"] = False
            fr.kill()
            self.close_connection = True


def stop(srv: ThreadingHTTPServer) -> None:
    """Kamera fällt aus: Anschluss schließen UND laufende Übertragungen abbrechen."""
    ABORT.set()
    srv.shutdown()
    srv.server_close()
    t0 = time.time()
    while STATE["streaming"] and time.time() - t0 < 5:
        time.sleep(0.05)


def serve(port: int, token: str, framer: str, fps: int = 8, drop_after: int = 0) -> ThreadingHTTPServer:
    ABORT.clear()
    STATE.update(token=token, framer=framer, fps=fps, drop_after=drop_after)
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8081)
    ap.add_argument("--token", required=True)
    ap.add_argument("--framer", required=True)
    a = ap.parse_args()
    serve(a.port, a.token, a.framer)
    print("Attrappe läuft auf Port", a.port, flush=True)
    while True:
        time.sleep(3600)
