# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende
"""Funknetz-Schnittstellen des Servers (/api/mesh*, Einrichtung, Status). Echte App, echter Speicher."""
import pytest

from conftest import TOKEN, login


def test_mesh_endpoints_require_login(make_app):
    app, c = make_app()
    for method, path in [("get", "/api/mesh"), ("get", "/api/mesh/messages"), ("post", "/api/mesh/test"),
                         ("get", "/api/mesh/lora/ports"), ("post", "/api/mesh/freenet/invite")]:
        r = getattr(c, method)(path)
        assert r.status_code in (401, 403), (path, r.status_code)


def test_mesh_state_when_disabled(make_app):
    app, c = make_app()
    login(c)
    r = c.get("/api/mesh")
    assert r.status_code == 200
    j = r.json()
    assert j["messages"] == [] and j["problems"] == []
    assert j.get("transports") in ([], {}, None) or len(j["transports"]) == 0
    st = c.get("/api/status").json()
    assert st["mesh"]["enabled"] is False


def test_mesh_test_is_409_when_disabled(make_app):
    app, c = make_app()
    login(c)
    r = c.post("/api/mesh/test")
    assert r.status_code == 409
    assert "Funk" in r.json()["detail"]


def test_messages_listing_is_bounded_and_validated(make_app):
    app, c = make_app()
    login(c)
    st = app.state.store
    for i in range(30):
        st.mesh_add(ts=1000 + i, direction="in" if i % 2 else "out", via="lora", typ="A", ident=f"{i:08x}",
                    station="X", count=1, conf=0.5, ai="-", note="", status="ok")
    assert len(c.get("/api/mesh/messages?limit=10").json()) == 10
    assert len(c.get("/api/mesh/messages?limit=99999").json()) == 30          # intern auf 500 begrenzt
    assert {r["direction"] for r in c.get("/api/mesh/messages?direction=in").json()} == {"in"}
    assert c.get("/api/mesh/messages?limit=abc").status_code == 422
    assert c.get("/api/mesh/messages?limit=-5").status_code == 200            # wird auf 1 geklemmt
    assert c.get("/api/mesh/messages?offset=-5").status_code == 200
    assert c.get("/api/mesh/messages?direction=%27%3B%20DROP%20TABLE%20mesh_log%3B--").status_code == 200
    assert len(c.get("/api/mesh/messages").json()) == 30                      # Tabelle noch da


def test_mesh_state_lists_messages_with_ack_counts(make_app):
    app, c = make_app()
    login(c)
    st = app.state.store
    st.mesh_add(ts=1000, direction="out", via="lora", typ="A", ident="aaaaaaaa", station="Ich", count=2, conf=0.9,
                ai="-", note="", status="sent")
    st.mesh_add(ts=1001, direction="in", via="lora", typ="R", ident="aaaaaaaa", station="Nachbar", count=0,
                conf=0, ai="-", note="", status="ok")
    j = c.get("/api/mesh").json()
    out = [m for m in j["messages"] if m["direction"] == "out"][0]
    assert out["acks"] == 1
    assert all(m["acks"] is None for m in j["messages"] if m["direction"] == "in")


def test_invite_rejects_bad_input_without_running_anything(make_app):
    app, c = make_app()
    login(c)
    for body in [{}, {"code": ""}, {"code": "x" * 100000}, {"code": "a b; rm -rf /"}, {"code": 123}]:
        r = c.post("/api/mesh/freenet/invite", json=body)
        assert r.status_code in (400, 502), (body.keys(), r.status_code, r.text)
    assert c.post("/api/mesh/freenet/invite", content=b"not json",
                  headers={"Content-Type": "application/json"}).status_code == 400
    assert c.post("/api/mesh/freenet/invite", json=[1, 2]).status_code == 400


def test_invite_with_missing_riverctl_gives_readable_error(make_app, settings):
    settings.mesh_freenet_riverctl = "/nonexistent/riverctl"
    app, c = make_app()
    login(c)
    r = c.post("/api/mesh/freenet/invite", json={"code": "abcdef0123456789", "nickname": "Imker"})
    assert r.status_code in (400, 502)
    assert r.json()["detail"]


def test_app_starts_with_freenet_enabled_but_riverctl_missing(make_app, settings):
    settings.mesh_freenet_enabled = True
    settings.mesh_freenet_riverctl = "/nonexistent/riverctl"
    settings.mesh_freenet_room = "A" * 44
    app, c = make_app()
    login(c)
    st = c.get("/api/status")
    assert st.status_code == 200
    j = c.get("/api/mesh").json()
    assert j["problems"] or any(not t.get("online", True) for t in j.get("transports", []))


def test_app_starts_with_lora_enabled_but_no_device(make_app, settings):
    settings.mesh_lora_enabled = True
    settings.mesh_lora_port = "/dev/does-not-exist"
    app, c = make_app()
    login(c)
    assert c.get("/api/status").status_code == 200
    assert c.get("/api/mesh").status_code == 200


def test_lora_ports_listing_works(make_app):
    app, c = make_app()
    login(c)
    r = c.get("/api/mesh/lora/ports")
    assert r.status_code == 200 and isinstance(r.json(), list)


def test_csrf_is_blocked_on_mesh_post(make_app):
    app, c = make_app()
    login(c)
    r = c.post("/api/mesh/test", headers={"Origin": "http://evil.example"})
    assert r.status_code == 403
    r = c.post("/api/mesh/freenet/invite", json={"code": "x"}, headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403


# ── Einrichtung: Funknetz-Werte ─────────────────────────────────────────────────────────────────────
def _put(c, values):
    return c.put("/api/setup", json={"values": values})


def test_setup_accepts_valid_mesh_values_and_persists(make_app, tmp_path):
    app, c = make_app()
    login(c)
    r = _put(c, {"MESH_LORA_ENABLED": "true", "MESH_LORA_PORT": "/dev/ttyUSB0", "MESH_LORA_CHANNEL_KEY": "ab" * 16,
                 "MESH_LORA_DUTY": "0.01", "MESH_STATION": "Bienenstand Nord"})
    assert r.status_code == 200, r.text
    text = (tmp_path / ".env").read_text()
    assert "MESH_LORA_PORT=/dev/ttyUSB0" in text and "MESH_STATION=Bienenstand Nord" in text
    cfg = c.get("/api/setup").json()
    assert "MESH_LORA_CHANNEL_KEY" in str(cfg)


@pytest.mark.parametrize("key,val", [
    ("MESH_LORA_CHANNEL_KEY", "zz" * 16),         # kein Hex
    ("MESH_LORA_CHANNEL_KEY", "abcd"),            # zu kurz
    ("MESH_LORA_DUTY", "0.5"),                    # über Obergrenze (max. 10 %)
    ("MESH_LORA_DUTY", "-1"),
    ("MESH_LORA_DUTY", "abc"),
    ("MESH_LORA_BAUD", "12"),
    ("MESH_LORA_CHANNEL_IDX", "0"),               # Kanal 0 = öffentlich, verboten
    ("MESH_LORA_CHANNEL_IDX", "99"),
    ("MESH_FREENET_NODE", "http://evil.example"),
    ("MESH_FREENET_NODE", "ws://127.0.0.1:99999"),
    ("MESH_STATION", "A|B"),
    ("MESH_STATION", "x" * 500),
    ("MESH_LORA_PORT", "/dev/ttyUSB0\nEVIL=1"),
    ("MESH_FREENET_ROOM", "not a room key"),
])
def test_setup_rejects_bad_mesh_values(make_app, tmp_path, key, val):
    app, c = make_app()
    login(c)
    r = _put(c, {key: val})
    assert r.status_code in (400, 422), (key, val, r.status_code, r.text)
    env = tmp_path / ".env"
    assert not env.exists() or "EVIL" not in env.read_text()
