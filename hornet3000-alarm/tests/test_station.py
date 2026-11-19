# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende
"""Station (Altgerät schickt JPEG-Bilder) und schlanke Handy-Schnittstelle. Echte App, echter Speicher, echte Bildprüfung."""
import io
import shutil
import threading
import time

import pytest
from PIL import Image

from conftest import TOKEN, login
from hornet.detector import Detection
from hornet.pushcam import MAX_SIDE, PushCamera, PushError, check_jpeg, clean_station

AUTH = {"Authorization": f"Bearer {TOKEN}"}


def jpeg(w=640, h=480, color=(120, 140, 90), mode="RGB", quality=70):
    im = Image.new(mode, (w, h), color if mode == "RGB" else 128)
    for i in range(0, w, 16):                      # etwas Inhalt, damit es nicht winzig wird
        im.paste((i % 255, 200, 40) if mode == "RGB" else 20, (i, 0, min(w, i + 8), h))
    b = io.BytesIO()
    im.save(b, "JPEG", quality=quality)
    return b.getvalue()


def post(c, data, headers=None, ctype="image/jpeg"):
    h = {**AUTH, "Content-Type": ctype}
    h.update(headers or {})
    return c.post("/api/station/frame", content=data, headers=h)


@pytest.fixture
def push_app(make_app, settings):
    settings.clip_enabled = False
    app, c = make_app(camera_source="push")
    return app, c


# ── Bildprüfung ────────────────────────────────────────────────────────────────────────────────────
def test_check_jpeg_accepts_normal_and_gray():
    assert check_jpeg(jpeg()) == (640, 480)
    assert check_jpeg(jpeg(320, 240, mode="L")) == (320, 240)


@pytest.mark.parametrize("data,status", [
    (b"", 400), (b"\xff\xd8\xff" + b"\x00" * 10, 400), (b"hello world" * 100, 415), (b"\x89PNG\r\n\x1a\n" + b"0" * 500, 415),
    (b"\xff\xd8\xff\xe0" + b"\x00" * 400, 400),     # JPEG-Anfang, aber Kopf kaputt
])
def test_check_jpeg_rejects_garbage(data, status):
    with pytest.raises(PushError) as e:
        check_jpeg(data)
    assert e.value.status == status


def test_check_jpeg_rejects_png_even_if_valid():
    b = io.BytesIO()
    Image.new("RGB", (100, 100), (1, 2, 3)).save(b, "PNG")
    with pytest.raises(PushError) as e:
        check_jpeg(b.getvalue() + b"\x00" * 300)
    assert e.value.status == 415


def test_check_jpeg_dimension_and_pixel_caps():
    with pytest.raises(PushError) as e:
        check_jpeg(jpeg(MAX_SIDE + 1, 16))
    assert e.value.status == 413
    with pytest.raises(PushError) as e:
        check_jpeg(jpeg(3200, 3000, color=(5, 5, 5)))        # 9,6 Megapixel
    assert e.value.status == 413
    with pytest.raises(PushError) as e:
        check_jpeg(jpeg(15, 400))
    assert e.value.status == 413


def test_check_jpeg_rejects_cmyk():
    b = io.BytesIO()
    Image.new("CMYK", (64, 64), (0, 0, 0, 0)).save(b, "JPEG")
    with pytest.raises(PushError) as e:
        check_jpeg(b.getvalue() + b"\x00" * 300)
    assert e.value.status == 415


def test_clean_station_names():
    assert clean_station("Bienenstand Nord") == "Bienenstand Nord"
    assert clean_station("Kamera_1-ä") == "Kamera_1-ä"
    for bad in (None, "", "   ", "a" * 41, "x\ny", "<script>", "a|b", "../etc", "ok\x00"):
        assert clean_station(bad) == "Station"


# ── Schnittstelle ───────────────────────────────────────────────────────────────────────────────────
def test_station_needs_login_and_push_source(make_app, settings):
    app, c = make_app(camera_source="")
    assert c.post("/api/station/frame", content=jpeg(), headers={"Content-Type": "image/jpeg"}).status_code == 401
    assert c.get("/api/station/config").status_code == 401
    r = post(c, jpeg())
    assert r.status_code == 409 and "push" in r.json()["detail"]
    assert c.get("/api/station/config", headers=AUTH).status_code == 409


def test_frame_is_accepted_and_reaches_the_engine(push_app):
    app, c = push_app
    r = post(c, jpeg(), {"X-Station": "Bienenstand Nord"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["ok"] is True and 250 <= j["interval_ms"] <= 5000
    eng = app.state.engine
    assert eng.has_frame()
    assert eng._latest[0][:3] == b"\xff\xd8\xff"
    cam = c.get("/api/status", headers=AUTH).json()["camera"]
    assert cam["type"] == "push" and cam["online"] is True and cam["state"] == "online"
    assert cam["station"] == "Bienenstand Nord" and cam["size"] == [640, 480]


def test_wrong_content_type_and_garbage(push_app):
    app, c = push_app
    assert post(c, jpeg(), ctype="text/plain").status_code == 415
    assert post(c, jpeg(), ctype="application/octet-stream").status_code == 415
    assert post(c, b"nicht jpeg" * 100).status_code == 415
    assert post(c, b"").status_code in (400, 415)
    assert post(c, jpeg(MAX_SIDE + 8, 16)).status_code == 413
    assert not app.state.engine.has_frame()


def test_body_over_one_mib_is_refused_by_the_guard(push_app):
    app, c = push_app
    r = post(c, b"\xff\xd8\xff" + b"0" * (1 << 21))
    assert r.status_code == 413
    assert not app.state.engine.has_frame()


def test_rate_limit_and_second_station(push_app):
    app, c = push_app
    assert post(c, jpeg(), {"X-Station": "A"}).status_code == 200
    r = post(c, jpeg(), {"X-Station": "A"})                       # sofort danach: zu schnell
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1
    r = post(c, jpeg(), {"X-Station": "B"})
    assert r.status_code == 409 and "A" in r.json()["detail"]
    cam = app.state.engine.camera
    cam.last_frame_ts -= 30                                       # A schweigt seit 30 s → B darf übernehmen
    cam._last_accept -= 30
    assert post(c, jpeg(), {"X-Station": "B"}).status_code == 200
    assert c.get("/api/status", headers=AUTH).json()["camera"]["station"] == "B"
    assert app.state.engine.camera.restarts == 1


def test_offline_after_silence_and_back(push_app):
    app, c = push_app
    assert post(c, jpeg(), {"X-Station": "A"}).status_code == 200
    cam = app.state.engine.camera
    cam.last_frame_ts -= 25
    cam._last_accept -= 25
    st = c.get("/api/status", headers=AUTH).json()["camera"]
    assert st["online"] is False and st["state"] == "offline" and "A" in st["error"]
    assert post(c, jpeg(), {"X-Station": "A"}).status_code == 200
    assert c.get("/api/status", headers=AUTH).json()["camera"]["online"] is True
    assert cam.restarts == 1


def test_bad_station_name_becomes_default(push_app):
    app, c = push_app
    assert post(c, jpeg(), {"X-Station": "<script>alert(1)</script>"}).status_code == 200
    assert c.get("/api/status", headers=AUTH).json()["camera"]["station"] == "Station"


def test_cookie_session_works_and_csrf_is_blocked(push_app):
    app, c = push_app
    login(c)
    ok = c.post("/api/station/frame", content=jpeg(), headers={"Content-Type": "image/jpeg", "X-Station": "A"})
    assert ok.status_code == 200
    bad = c.post("/api/station/frame", content=jpeg(), headers={"Content-Type": "image/jpeg", "Origin": "http://evil.example"})
    assert bad.status_code == 403
    bad = c.post("/api/station/frame", content=jpeg(), headers={"Content-Type": "image/jpeg", "Sec-Fetch-Site": "cross-site"})
    assert bad.status_code == 403


def test_bearer_guessing_is_throttled(push_app):
    app, c = push_app
    for i in range(10):
        r = c.get("/api/mobile/poll", headers={"Authorization": f"Bearer falsch-{i}"})
        assert r.status_code == 401
    r = c.get("/api/mobile/poll", headers={"Authorization": f"Bearer falsch-x"})
    assert r.status_code == 429
    assert c.get("/api/mobile/poll", headers=AUTH).status_code == 429     # gesperrt gilt auch für den richtigen Schlüssel (wie die Anmeldemaske)


def test_valid_token_attempts_do_not_count_as_failures(push_app):
    app, c = push_app
    for _ in range(30):
        assert c.get("/api/mobile/poll", headers=AUTH).status_code == 200


def test_station_config(push_app):
    app, c = push_app
    j = c.get("/api/station/config", headers=AUTH).json()
    assert j["max_bytes"] == 1 << 20 and j["width"] <= 960 and j["interval_ms"] >= 250


# ── Abfrage für kleine Anzeigen ──────────────────────────────────────────────────────────────────────
def test_poll_shape_and_since_filter(push_app):
    app, c = push_app
    st = app.state.store
    for i in range(3):
        st.add_alert(ts=1000.0 + i, camera="K", kind="new", species="velutina", label="Asiatische Hornisse", conf=0.8,
                     count=i + 1, muted=False)
    j = c.get("/api/mobile/poll", headers=AUTH).json()
    assert j["v"] == 1 and "camera" in j and isinstance(j["alerts"], list) and "newest_id" in j
    assert j["camera"]["state"] == "waiting" and j["camera"]["online"] is False
    assert j["muted"] is False and j["detections_now"] == 0
    newest = j["newest_id"]
    assert newest >= 3 and len(j["alerts"]) == 3 and j["alerts"][0]["id"] == newest and j["alerts"][0]["kind"] == "new"
    assert [a["id"] for a in c.get(f"/api/mobile/poll?since={newest - 1}", headers=AUTH).json()["alerts"]] == [newest]
    assert c.get(f"/api/mobile/poll?since={newest}", headers=AUTH).json()["alerts"] == []
    assert c.get("/api/mobile/poll?since=abc", headers=AUTH).status_code == 422
    assert c.get("/api/mobile/poll?since=-5", headers=AUTH).status_code == 200
    assert c.get("/api/mobile/poll").status_code == 401


# ── Foto prüfen ──────────────────────────────────────────────────────────────────────────────────────
class FakeDet:
    names = {0: "vvel", 1: "vcra"}

    def __init__(self, delay=0.0):
        self.delay, self.calls = delay, 0

    def detect(self, img, conf_min=0.25):
        self.calls += 1
        time.sleep(self.delay)
        return [Detection(0, "vvel", 0.91, (10, 10, 60, 60)), Detection(1, "vcra", 0.40, (100, 100, 140, 140))]


def test_check_needs_model(push_app):
    app, c = push_app
    assert c.post("/api/mobile/check", content=jpeg(), headers={**AUTH, "Content-Type": "image/jpeg"}).status_code == 503


def test_check_reports_without_raising_an_alarm(push_app):
    app, c = push_app
    app.state.engine.detector = FakeDet()
    before = app.state.store.count_alerts()
    r = c.post("/api/mobile/check", content=jpeg(), headers={**AUTH, "Content-Type": "image/jpeg"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["alarm_like"] is True and j["detections"][0]["conf"] == 0.91 and j["detections"][0]["kind"] == "alarm"
    assert "wahrscheinlich" in j["verdict"]
    assert app.state.store.count_alerts() == before and app.state.store.list_alerts(10) == []


def test_check_rejects_bad_input(push_app):
    app, c = push_app
    app.state.engine.detector = FakeDet()
    for data, ct, code in [(b"x" * 500, "image/jpeg", 415), (jpeg(), "text/plain", 415), (jpeg(MAX_SIDE + 1, 16), "image/jpeg", 413)]:
        assert c.post("/api/mobile/check", content=data, headers={**AUTH, "Content-Type": ct}).status_code == code
    assert c.post("/api/mobile/check", content=jpeg(), headers={"Content-Type": "image/jpeg"}).status_code == 401
    assert app.state.engine.detector.calls == 0


def test_check_runs_one_at_a_time(push_app):
    app, c = push_app
    app.state.engine.detector = FakeDet(delay=1.0)
    res = {}

    def first():
        res["a"] = c.post("/api/mobile/check", content=jpeg(), headers={**AUTH, "Content-Type": "image/jpeg"}).status_code
    t = threading.Thread(target=first)
    t.start()
    time.sleep(0.4)
    r = c.post("/api/mobile/check", content=jpeg(), headers={**AUTH, "Content-Type": "image/jpeg"})
    t.join()
    assert res["a"] == 200 and r.status_code == 429


# ── Clip aus Stationsbildern ─────────────────────────────────────────────────────────────────────────
@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg fehlt")
def test_clip_is_built_from_station_frames(settings, tmp_path):
    settings.clip_enabled, settings.clip_pre_s, settings.clip_post_s, settings.clip_width = True, 2, 1, 320
    got = []
    cam = PushCamera(settings, lambda b, t: got.append(t))
    cam.start()
    t0 = time.time()
    n = 0
    while time.time() < t0 + 3.2:
        cam.push(jpeg(color=(n * 5 % 255, 100, 100)), "S")
        n += 1
        time.sleep(0.25)
    out = cam.make_clip(t0 + 1.5, tmp_path / "clip.mp4", pre=1, post=1)
    assert out is not None and out.stat().st_size > 1000
    assert out.read_bytes()[4:8] == b"ftyp"
    assert len(got) == n


def test_clip_without_enough_frames_is_none(settings, tmp_path):
    settings.clip_enabled = True
    cam = PushCamera(settings, lambda b, t: None)
    assert cam.make_clip(time.time() - 100, tmp_path / "c.mp4", pre=1, post=0) is None


def test_ring_buffer_is_bounded(settings):
    settings.clip_pre_s, settings.clip_post_s = 1, 1
    cam = PushCamera(settings, lambda b, t: None)
    data = jpeg()
    for i in range(200):
        cam.push(data, "S", now=1000.0 + i)                 # 200 s Bilder → nur noch die letzten ~12 s
    assert len(cam._ring) <= 14 and cam._ring_bytes == sum(len(d) for _, d in cam._ring)


# ── Android-App zum Herunterladen ──────────────────────────────────────────────────────────────────────
def test_apk_download_needs_login_and_reports_absence(push_app, monkeypatch, tmp_path):
    import hornet.server as srv
    app, c = push_app
    monkeypatch.setattr(srv, "APK_PATH", tmp_path / "gibt-es-nicht.apk")
    assert c.get("/api/mobile/poll", headers=AUTH).json()["apk"] is False
    assert c.get("/mobil/hornet3000-station.apk", headers=AUTH).status_code == 404
    assert c.get("/mobil/hornet3000-station.apk").status_code == 401


def test_apk_download_serves_file_with_safe_headers(push_app, monkeypatch, tmp_path):
    import hornet.server as srv
    app, c = push_app
    apk = tmp_path / "x.apk"
    apk.write_bytes(b"PK\x03\x04" + b"0" * 1000)
    monkeypatch.setattr(srv, "APK_PATH", apk)
    assert c.get("/api/mobile/poll", headers=AUTH).json()["apk"] is True
    r = c.get("/mobil/hornet3000-station.apk", headers=AUTH)
    assert r.status_code == 200 and r.content == apk.read_bytes()
    assert r.headers["content-type"] == "application/vnd.android.package-archive"
    assert "Hornet3000-Station.apk" in r.headers["content-disposition"] and r.headers["cache-control"] == "no-store"
    assert c.get("/mobil/hornet3000-station.apk").status_code == 401          # ohne Anmeldung nichts
    # fremde Pfade unter /mobil/ gibt es nicht (kein Verzeichnis-Zugriff)
    assert c.get("/mobil/", headers=AUTH).status_code in (404, 405)
    assert c.get("/mobil/../hornet/config.py", headers=AUTH).status_code in (404, 400)
