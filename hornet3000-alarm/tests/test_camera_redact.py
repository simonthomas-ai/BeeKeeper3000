# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende
"""Zugangsdaten der Kamera-Adresse dürfen nie in Fehlertexten auftauchen (Status, Telegram, Einrichtungs-Test)."""
import time

import pytest

from hornet.camera import Camera, redact
from hornet.setup_wizard import _friendly, probe_camera

SECRET = "esp32-GEHEIM-q7Zq7Zq7Z"


@pytest.mark.parametrize("src,err", [
    (f"http://10.0.0.5:81/stream?t={SECRET}", f"Error opening input file http://10.0.0.5:81/stream?t={SECRET}."),
    (f"http://10.0.0.5:81/stream?t={SECRET}&x=1", f"[http @ 0x1] HTTP error 401 for http://10.0.0.5:81/stream?t={SECRET}&x=1"),
    ("rtsp://admin:hunter2pw@192.168.1.20:554/h264", "Error opening input file rtsp://admin:hunter2pw@192.168.1.20:554/h264."),
    ("rtsp://admin:hunter2pw@192.168.1.20:554/h264", "Connection to tcp://admin:hunter2pw@192.168.1.20:554 failed"),
    ("rtsp://admin:hunter2pw@192.168.1.20:554/h264", "auth failed for user admin password hunter2pw"),
    (f"https://cam.example/live?token={SECRET}#frag", f"cannot open https://cam.example/live?token={SECRET}#frag now"),
    (f"http://u:pw-geheim99@host/s?t={SECRET}", f"x http://u:pw-geheim99@host/s?t={SECRET} y rtmp://a:b@h/p?k=v z"),
])
def test_redact_removes_secrets(src, err):
    out = redact(err, src)
    for bad in (SECRET, "hunter2pw", "pw-geheim99"):
        assert bad not in out, out
    assert out                                            # Fehlertext bleibt lesbar


def test_redact_keeps_useful_parts():
    out = redact("Error opening input: Server returned 401 Unauthorized | Error opening input file http://10.0.0.5:81/stream?t=abcdefgh.",
                 "http://10.0.0.5:81/stream?t=abcdefgh")
    assert "401 Unauthorized" in out and "10.0.0.5:81/stream" in out and "abcdefgh" not in out


def test_redact_is_safe_on_odd_input():
    for t in ("", "kein url", "http://", "://x", "http://[::1", "a" * 100000):
        assert isinstance(redact(t, "http://[::1"), str)
    assert redact("", "") == ""
    assert redact(None, "") == ""                         # type: ignore[arg-type]


def test_friendly_probe_error_is_redacted():
    err = "Error opening input file rtsp://admin:hunter2pw@1.2.3.4/x?t=tokentoken\nFehler beim Öffnen"
    out = _friendly(err, "rtsp://admin:hunter2pw@1.2.3.4/x?t=tokentoken")
    assert "hunter2pw" not in out and "tokentoken" not in out


def test_probe_camera_error_has_no_secret(settings):
    import shutil
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg fehlt")
    r = probe_camera(f"http://127.0.0.1:9/stream?t={SECRET}")           # Port 9: nichts hört zu
    assert r["ok"] is False and SECRET not in r["error"]


def test_camera_status_error_has_no_secret(settings):
    import shutil
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg fehlt")
    settings.camera_source = f"http://127.0.0.1:9/stream?t={SECRET}"
    settings.clip_enabled = False
    cam = Camera(settings, lambda b, t: None)
    cam.start()
    try:
        end = time.time() + 20
        while time.time() < end and not cam.error:
            time.sleep(0.2)
        assert cam.error, "kein Fehlertext entstanden"
        assert SECRET not in cam.error and "?t=" not in cam.error, cam.error
    finally:
        cam.stop()
