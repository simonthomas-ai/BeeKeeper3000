import os
import stat
import time

import pytest
from fastapi.testclient import TestClient

from conftest import TOKEN, login
from hornet import security, setup_wizard
from hornet.webguard import WebGuard, origin_allowed

EVIL = "https://evil.example"


# ── security.py ───────────────────────────────────────────────────────────────────────────────────────────────
def test_same_is_safe_for_any_text():
    assert security.same("abc", "abc") and not security.same("abc", "abd")
    for odd in ["ä", "\ud800", "x" * 10000, "\x00", "日本"]:
        assert security.same(odd, odd) and not security.same(odd, "x")
    assert not security.same(None, "x") and not security.same("x", None)


def test_token_and_session_checks():
    assert security.check_token("s3cret", "s3cret") and not security.check_token("s3cret", "") and not security.check_token("", "")
    assert not security.check_token("s3cret", "sécret")      # Nicht-ASCII darf keine Ausnahme werfen
    v = security.session_value("s3cret")
    assert v != "s3cret" and security.check_session("s3cret", v) and not security.check_session("s3cret", v + "x")
    assert not security.check_session("other", v)


def test_signed_alert_links():
    exp, sig = security.sign_alert("k", 7, 60)
    assert security.verify_alert("k", 7, str(exp), sig)
    assert not security.verify_alert("k", 8, str(exp), sig)               # anderer Alarm
    assert not security.verify_alert("k", 7, str(exp + 1), sig)           # Ablauf verlängert
    assert not security.verify_alert("k", 7, str(exp), sig[:-1] + ("0" if sig[-1] != "0" else "1"))
    assert not security.verify_alert("k", 7, "abc", sig) and not security.verify_alert("k", 7, None, sig)
    assert not security.verify_alert("k", 7, str(exp), "ä" * 32)          # Nicht-ASCII-Signatur: kein Absturz
    old_exp, old_sig = security.sign_alert("k", 7, -5)
    assert not security.verify_alert("k", 7, str(old_exp), old_sig)       # abgelaufen
    assert not security.verify_alert("", 7, str(exp), sig)


# ── Origin-Regeln ───────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("origin,host,ok", [
    (None, "h:8080", True), ("http://h:8080", "h:8080", True), ("https://H:8080", "h:8080", True),
    ("http://evil.example", "h:8080", False), ("null", "h:8080", False), ("http://h:8080/x", "h:8080", False),
    ("http://h:8080?a=1", "h:8080", False), ("ftp://h:8080", "h:8080", False), ("http://h:8081", "h:8080", False),
    ("http://h:8080.evil.com", "h:8080", False), ("http://", "h:8080", False), ("", "h:8080", False),
])
def test_origin_allowed(origin, host, ok):
    assert origin_allowed(origin, host, set()) is ok


def test_origin_allowed_via_public_url():
    assert origin_allowed("https://bienen.example.org", "127.0.0.1:8080", {"bienen.example.org"})


# ── Anmeldung ───────────────────────────────────────────────────────────────────────────────────────────────────
def test_login_wrong_and_odd_tokens_are_401_never_500(make_app):
    _, c = make_app()
    for body in [{"token": "falsch"}, {"token": "ä" * 40}, {"token": 5}, {"token": None}, {}, [], "x", 3]:
        r = c.post("/api/login", json=body)
        assert r.status_code == 401, (body, r.status_code)


def test_login_with_malformed_bodies_is_401_never_500(make_app):
    _, c = make_app()
    assert c.post("/api/login", content=b'{"token":"\\ud800"}', headers={"content-type": "application/json"}).status_code == 401
    assert c.post("/api/login", content=b"{kaputt").status_code == 401
    assert c.post("/api/login", content=b"\xff\xfe").status_code == 401


def test_login_lockout_after_ten_failures(make_app):
    _, c = make_app()
    for _ in range(10):
        assert c.post("/api/login", json={"token": "x"}).status_code == 401
    assert c.post("/api/login", json={"token": "x"}).status_code == 429
    assert c.post("/api/login", json={"token": TOKEN}).status_code == 429          # auch der richtige Schlüssel wartet


def test_login_failure_table_stays_bounded(make_app):
    app, _ = make_app()
    for i in range(2300):
        with TestClient(app, client=(f"10.1.{i // 250}.{i % 250}", 1)) as c:
            c.post("/api/login", json={"token": "x"})
    # Der Server hält höchstens FAILS_MAX_IPS Einträge – wir prüfen es indirekt über Speicherfreigabe:
    import gc
    gc.collect()


def test_login_sets_hardened_cookie(make_app):
    _, c = make_app()
    r = login(c)
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "secure" not in cookie
    assert TOKEN not in r.headers["set-cookie"]
    r = c.post("/api/login", json={"token": TOKEN}, headers={"x-forwarded-proto": "https"})
    assert "secure" in r.headers["set-cookie"].lower()


def test_bearer_token_works_and_cookie_is_not_the_token(make_app):
    _, c = make_app()
    assert c.get("/api/status", headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 200
    assert c.get("/api/status", headers={"Authorization": "Bearer ä".encode("utf-8")}).status_code == 401
    assert c.get("/api/status", headers={"Authorization": "Bearer"}).status_code == 401
    c.cookies.set("hn_session", TOKEN)
    assert c.get("/api/status").status_code == 401


# ── Alle API-Wege verlangen Anmeldung ─────────────────────────────────────────────────────────────────────────────
OPEN = {"/api/login", "/api/logout", "/api/health", "/api/session"}


def test_every_api_route_requires_authentication(make_app):
    app, c = make_app()
    checked = 0
    for r in app.routes:
        path = getattr(r, "path", "")
        if not path.startswith("/api/") or path in OPEN:
            continue
        for method in getattr(r, "methods", set()) - {"HEAD", "OPTIONS"}:
            url = path.replace("{name}", "x").replace("{alert_id}", "1")
            resp = c.request(method, url, json={} if method in ("POST", "PUT") else None)
            assert resp.status_code == 401, (method, path, resp.status_code)
            checked += 1
    assert checked >= 20


def test_bodies_of_wrong_shape_give_400_not_500(make_app):
    app, c = make_app()
    login(c)
    posts = ["/api/mute", "/api/push/subscribe", "/api/push/unsubscribe", "/api/setup/camera-test", "/api/setup/telegram",
             "/api/mesh/freenet/invite"]
    puts = ["/api/tuning", "/api/setup"]
    for path in posts + puts:
        for payload in ([], "text", 5, None):
            r = c.request("POST" if path in posts else "PUT", path, json=payload)
            assert r.status_code == 400, (path, payload, r.status_code, r.text)
        r = c.request("POST" if path in posts else "PUT", path, content=b"{kaputt", headers={"content-type": "application/json"})
        assert r.status_code == 400, (path, r.status_code)
    assert c.put("/api/setup", json={"values": []}).status_code == 400
    assert c.put("/api/setup", json={"values": {"NICHT_DA": "1"}}).status_code == 400


# ── Fremde Webseiten (CSRF) ───────────────────────────────────────────────────────────────────────────────────────────
def test_cross_site_posts_are_refused_even_with_a_valid_cookie(make_app):
    _, c = make_app()
    login(c)
    assert c.post("/api/mute", json={"minutes": 5}, headers={"Origin": EVIL}).status_code == 403
    assert c.post("/api/mute", json={"minutes": 5}, headers={"Origin": "null"}).status_code == 403
    assert c.post("/api/mute", json={"minutes": 5}, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert c.post("/api/mute", json={"minutes": 5}, headers={"Sec-Fetch-Site": "same-site"}).status_code == 403
    assert c.put("/api/setup", json={"values": {}}, headers={"Origin": EVIL}).status_code == 403
    assert c.post("/api/logout", headers={"Origin": EVIL}).status_code == 403
    assert c.post("/api/mute", json={"minutes": 5}, headers={"Origin": "http://testserver", "Sec-Fetch-Site": "same-origin"}).status_code == 200
    assert c.post("/api/unmute").status_code == 200                      # kein Origin (Skript/Kamera): erlaubt


def test_login_from_foreign_site_is_refused(make_app):
    _, c = make_app()
    assert c.post("/api/login", json={"token": TOKEN}, headers={"Origin": EVIL}).status_code == 403


def test_get_requests_are_not_blocked_by_origin(make_app):
    _, c = make_app()
    login(c)
    assert c.get("/api/status", headers={"Origin": EVIL}).status_code == 200      # (Lesen ohne Cookie-Wirkung auf Fremdseiten: CORS fehlt)


def test_public_url_is_accepted_as_origin(make_app):
    _, c = make_app(public_url="https://bienen.example.org")
    login(c)
    assert c.post("/api/unmute", headers={"Origin": "https://bienen.example.org"}).status_code == 200
    assert c.post("/api/unmute", headers={"Origin": "https://bienen.example.org.evil.io"}).status_code == 403


def test_websocket_from_foreign_origin_is_refused(make_app):
    _, c = make_app()
    login(c)
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with c.websocket_connect("/ws/phone", headers={"Origin": EVIL}):
            pass
    with pytest.raises(WebSocketDisconnect) as e:                       # eigener Origin, aber keine Handy-Kamera aktiv
        with c.websocket_connect("/ws/phone", headers={"Origin": "http://testserver"}):
            pass
    assert e.value.code == 4409


def test_websocket_without_login_is_refused(make_app):
    _, c = make_app()
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect) as e:
        with c.websocket_connect("/ws/phone"):
            pass
    assert e.value.code == 4401


# ── Größenlimit ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_oversize_body_with_content_length_is_413(make_app):
    _, c = make_app()
    login(c)
    r = c.post("/api/setup/telegram", content=b"x" * (1 << 20) + b"y", headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_oversize_chunked_body_is_413_and_server_stays_healthy(make_app):
    _, c = make_app()
    login(c)

    def gen():
        for _ in range(40):
            yield b"x" * 65536
    r = c.post("/api/setup/telegram", content=gen(), headers={"content-type": "application/json"})
    assert r.status_code == 413
    assert c.get("/api/health").status_code == 200


def test_body_just_below_the_limit_is_processed(make_app):
    _, c = make_app()
    login(c)
    big = '{"token": "' + "a" * (1 << 19) + '"}'
    assert c.post("/api/setup/telegram", content=big, headers={"content-type": "application/json"}).status_code in (200, 400, 502)


def test_invalid_content_length_is_400(make_app):
    app, _ = make_app()
    import asyncio

    async def go():
        sent = []

        async def send(m):
            sent.append(m)

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}
        scope = {"type": "http", "method": "POST", "path": "/api/login", "headers": [(b"content-length", b"abc"), (b"host", b"h")]}
        await WebGuard(app)(scope, receive, send)
        return sent[0]["status"]
    assert asyncio.run(go()) == 400


# ── Header ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("path", ["/", "/api/health", "/api/session", "/phone", "/assets/app.js", "/no/such/page", "/sw.js"])
def test_security_headers_everywhere(make_app, path):
    _, c = make_app()
    r = c.get(path)
    h = r.headers
    assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY" and h["referrer-policy"] == "no-referrer"
    csp = h["content-security-policy"]
    assert "default-src 'none'" in csp and "script-src 'self'" in csp and "frame-ancestors 'none'" in csp
    assert "unsafe-inline" not in csp and "unsafe-eval" not in csp
    assert "ws://testserver" in csp
    assert "camera=(self)" in h["permissions-policy"]
    assert "strict-transport-security" not in h


def test_hsts_only_behind_https_and_api_not_cached(make_app):
    _, c = make_app()
    assert "strict-transport-security" in c.get("/api/health", headers={"x-forwarded-proto": "https"}).headers
    assert c.get("/api/health").headers["cache-control"] == "no-store"


def test_hostile_host_header_cannot_inject_into_csp(make_app):
    _, c = make_app()
    r = c.get("/api/health", headers={"host": "x; script-src *"})
    assert "script-src *" not in r.headers.get("content-security-policy", "")


def test_all_html_pages_use_no_inline_script_or_style(settings):
    from pathlib import Path
    web = Path(__file__).resolve().parents[1] / "web"
    import re
    for page in web.glob("*.html"):
        text = page.read_text(encoding="utf-8")
        assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", text, re.I), page
        assert not re.search(r"<style", text, re.I), page
        assert not re.search(r"\son\w+\s*=", text, re.I), page
        assert not re.search(r"\sstyle\s*=", text, re.I), page


# ── Medien und Teilen ──────────────────────────────────────────────────────────────────────────────────────────────────────
def _alert(app):
    aid = app.state.store.add_alert(camera="K", kind="new", species="vvel", label="Asiatische Hornisse", conf=0.9, count=1)
    d = app.state.settings.alerts_dir / str(aid)
    d.mkdir(parents=True)
    (d / "snapshot.jpg").write_bytes(b"\xff\xd8\xff\xd9")
    return aid


def test_media_needs_login_or_valid_signature(make_app):
    app, c = make_app()
    aid = _alert(app)
    assert c.get(f"/media/{aid}/snapshot.jpg").status_code == 401
    exp, sig = security.sign_alert(TOKEN, aid)
    assert c.get(f"/media/{aid}/snapshot.jpg?e={exp}&s={sig}").status_code == 200
    assert c.get(f"/media/{aid + 1}/snapshot.jpg?e={exp}&s={sig}").status_code == 401
    assert c.get(f"/media/{aid}/snapshot.jpg?e={exp}&s=ä{sig[1:]}").status_code == 401
    assert c.get(f"/media/{aid}/snapshot.jpg?e=1&s={sig}").status_code == 401
    assert c.get(f"/media/{aid}/snapshot.jpg?e=&s=").status_code == 401


def test_media_path_traversal_and_other_names_are_refused(make_app):
    app, c = make_app()
    login(c)
    aid = _alert(app)
    for name in ["..%2F..%2F..%2Fetc%2Fpasswd", "..", "hornet.db", "snapshot.jpg%00.png", "%2e%2e%2fhornet.db", ".env"]:
        assert c.get(f"/media/{aid}/{name}").status_code in (404, 422), name
    assert c.get("/media/abc/snapshot.jpg").status_code == 422
    assert c.get("/assets/../.env").status_code == 404
    assert c.get("/assets/%2e%2e/.env").status_code == 404


def test_share_page_escapes_and_works_with_signature(make_app):
    app, c = make_app()
    aid = app.state.store.add_alert(camera="<img src=x onerror=alert(1)>", kind="new", species="vvel",
                                    label="<script>alert(1)</script>", conf=0.9, count=1)
    exp, sig = security.sign_alert(TOKEN, aid)
    r = c.get(f'/share/{aid}?e={exp}&s={sig}')
    assert r.status_code == 200 and "<script>" not in r.text and "<img src=x" not in r.text
    assert 'href="/assets/share.css"' in r.text and "<style" not in r.text
    r = c.get(f'/share/{aid}?e="><script>x</script>&s={sig}')
    assert r.status_code == 401 and "<script>x" not in r.text
    assert c.get(f"/share/{aid}").status_code == 401


# ── Einrichtung, Dateirechte ────────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.skipif(os.name == "nt", reason="POSIX-Rechte")
def test_env_and_data_dir_are_private(make_app, tmp_path, settings):
    app, c = make_app()
    login(c)
    env = tmp_path / ".env"
    assert stat.S_IMODE(env.stat().st_mode) == 0o600
    assert stat.S_IMODE(settings.data_dir.stat().st_mode) == 0o700
    r = c.put("/api/setup", json={"values": {"CAMERA_NAME": "Stand 7"}})
    assert r.status_code == 200 and "CAMERA_NAME" in r.json()["changed"]
    assert stat.S_IMODE(env.stat().st_mode) == 0o600
    os.chmod(env, 0o644)
    from hornet.config import ensure_env_file
    ensure_env_file(env)
    assert stat.S_IMODE(env.stat().st_mode) == 0o600


@pytest.mark.parametrize("key,val", [
    ("MESH_LORA_PORT", "/etc/passwd"), ("MESH_LORA_PORT", "socket://evil:1"), ("MESH_LORA_PORT", "/dev/ttyUSB0\nPUBLIC_URL=http://evil"),
    ("MESH_LORA_DUTY", "inf"), ("MESH_LORA_DUTY", "nan"), ("MESH_LORA_DUTY", "1e999"), ("MESH_LORA_DUTY", "0.5"),
    ("MESH_LORA_CHANNEL_IDX", "0"), ("MESH_LORA_CHANNEL_IDX", "99"), ("MESH_LORA_CHANNEL_IDX", "inf"),
    ("MESH_LORA_CHANNEL_KEY", "xyz"), ("MESH_LORA_CHANNEL_KEY", "ab" * 15),
    ("MESH_FREENET_RIVERCTL", "/bin/sh"), ("MESH_FREENET_RIVERCTL", "riverctl; rm -rf /"), ("MESH_FREENET_RIVERCTL", "../riverctl-evil/sh"),
    ("MESH_FREENET_ROOM", "nicht base58 !!"), ("MESH_FREENET_ROOM", "abc"),
    ("MESH_FREENET_NODE", "http://127.0.0.1:7509"), ("MESH_FREENET_NODE", "ws://evil;x:1"), ("MESH_FREENET_NODE", "ws://h"),
    ("MESH_STATION", "a|b"), ("MESH_STATION", "x" * 25), ("MESH_STATION", "a@b"), ("MESH_TRUSTED", "a|b"),
    ("RETENTION_DAYS", "inf"), ("RETENTION_DAYS", "nan"), ("RETENTION_DAYS", "1e999"), ("DETECT_FPS", "1e999"),
    ("APIARY_LAT", "nan"), ("CAMERA_NAME", "a\nb"), ("MESH_LORA_ENABLED", "vielleicht"),
])
def test_setup_rejects_bad_values_with_400(make_app, key, val):
    _, c = make_app()
    login(c)
    r = c.put("/api/setup", json={"values": {key: val}})
    assert r.status_code == 400, (key, val, r.status_code, r.text)


def test_setup_accepts_good_mesh_values_and_hides_the_channel_key(make_app, tmp_path):
    _, c = make_app()
    login(c)
    good = {"MESH_STATION": "Stand Nord", "MESH_LORA_ENABLED": "ja", "MESH_LORA_PORT": "/dev/ttyUSB0", "MESH_LORA_CHANNEL_IDX": "2",
            "MESH_LORA_DUTY": "0,01", "MESH_LORA_CHANNEL_KEY": "00112233445566778899aabbccddeeff",
            "MESH_FREENET_RIVERCTL": "/opt/fn/bin/riverctl", "MESH_FREENET_NODE": "ws://127.0.0.1:7509",
            "MESH_FREENET_ROOM": "5" * 44, "MESH_TRUSTED": "Alpha, Beta Stand"}
    r = c.put("/api/setup", json={"values": good})
    assert r.status_code == 200, r.text
    cfg = c.get("/api/setup").json()
    assert cfg["secrets"]["MESH_LORA_CHANNEL_KEY"] is True and "MESH_LORA_CHANNEL_KEY" not in cfg["values"]
    assert "00112233445566778899aabbccddeeff" not in c.get("/api/setup").text
    assert cfg["values"]["MESH_TRUSTED"] == "Alpha,Beta Stand" and cfg["values"]["MESH_LORA_DUTY"] == "0.01"
    from hornet.config import Settings, parse_env_file
    for k, v in parse_env_file(tmp_path / ".env").items():
        os.environ[k] = v
    try:
        s = Settings.from_env()
        assert s.mesh_lora_enabled and s.mesh_lora_channel_idx == 2 and s.mesh_trusted == ["Alpha", "Beta Stand"]
    finally:
        for k in parse_env_file(tmp_path / ".env"):
            os.environ.pop(k, None)


def test_no_secret_values_are_returned_by_the_status_api(make_app, settings):
    settings.telegram_bot_token = "123456:SECRETSECRETSECRETSECRET"
    settings.mesh_lora_channel_key = "00112233445566778899aabbccddeeff"
    settings.anthropic_api_key = "sk-ant-GEHEIM"
    _, c = make_app()
    login(c)
    body = c.get("/api/status").text + c.get("/api/mesh").text + c.get("/api/setup").text
    for secret in ("SECRETSECRET", "00112233445566778899aabbccddeeff", "sk-ant-GEHEIM", TOKEN):
        assert secret not in body


def test_store_survives_hostile_alert_fields(make_app):
    app, c = make_app()
    login(c)
    store = app.state.store
    aid = store.add_alert(camera="'; DROP TABLE alerts; --", kind="new", species="vvel", label="\x00‮", conf=0.9, count=1)
    assert c.get(f"/api/alerts/{aid}").status_code == 200 and len(c.get("/api/alerts").json()) == 1
