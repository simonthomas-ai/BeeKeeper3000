"""Alarm-Ablauf ↔ Funknetz. Echte Engine, echter Speicher; nur der Übertragungsweg ist eine TESTATTRAPPE."""
import io
import time

import pytest
from PIL import Image

from helpers import FakeTransport, wait_for
from hornet.detector import Detection
from hornet.engine import Engine, EventBus
from hornet.mesh import wire
from hornet.mesh.service import MeshService
from hornet.notifiers import Hub


def _jpeg():
    buf = io.BytesIO()
    Image.new("RGB", (320, 240), (120, 130, 90)).save(buf, "JPEG")
    return buf.getvalue()


def _best(conf=0.9):
    d = Detection(0, "velutina", conf, (50.0, 50.0, 150.0, 150.0))
    return {"conf": conf, "jpeg": _jpeg(), "dets": [d], "hits": [d], "ts": time.time()}


@pytest.fixture
def eng(settings, store):
    settings.camera_source = ""
    settings.clip_enabled = False
    settings.verify_provider = "none"
    hub = Hub(settings, store)
    e = Engine(settings, store, hub, EventBus(), None)
    tr = FakeTransport("lora")
    svc = MeshService(settings, store, {"lora": tr}, hub=hub, jitter=lambda: 0.0)
    e.mesh = svc
    yield e, svc, tr
    e.pool.shutdown(wait=False, cancel_futures=True)
    svc._pool.shutdown(wait=False)


def _announced(svc):
    return [r for r in svc.store.mesh_list(50) if r["direction"] == "out"]


def test_new_alert_is_announced_once(eng):
    e, svc, tr = eng
    aid = e._raise_alert("new", {"id": None}, _best(0.87), 3)
    assert aid
    rows = _announced(svc)
    assert len(rows) == 1
    r = rows[0]
    assert r["typ"] == "A" and r["count"] == 3 and abs(r["conf"] - 0.87) < 1e-9 and r["station"] == "Teststand 1"
    assert r["status"] == "queued"


def test_update_is_announced_as_update(eng):
    e, svc, tr = eng
    e._raise_alert("update", {"id": None}, _best(), 5)
    rows = _announced(svc)
    assert len(rows) == 1 and rows[0]["typ"] == "U" and rows[0]["count"] == 5


def test_test_alert_is_never_announced(eng):
    e, svc, tr = eng
    best = {"conf": 1.0, "jpeg": _jpeg(), "dets": [], "hits": [], "ts": time.time()}
    assert e._raise_alert("test", {"id": None}, best, 1)
    assert _announced(svc) == []


def test_muted_alert_is_not_announced(eng):
    e, svc, tr = eng
    e.store.kv_set("mute_until", time.time() + 600)
    assert e.is_muted()
    assert e._raise_alert("new", {"id": None}, _best(), 1)
    assert _announced(svc) == []


def test_mesh_failure_does_not_block_alarm_delivery(eng, monkeypatch):
    e, svc, tr = eng
    monkeypatch.setattr(svc, "announce", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("kaputt")))
    aid = e._raise_alert("new", {"id": None}, _best(), 1)
    assert aid                                             # Alarm wurde trotzdem gespeichert und verteilt
    assert e.store.get_alert(aid)["delivery"] is not None


def test_engine_without_mesh_works(eng):
    e, svc, tr = eng
    e.mesh = None
    assert e._raise_alert("new", {"id": None}, _best(), 1)


def test_engine_start_stop_runs_mesh_thread(eng):
    e, svc, tr = eng
    e.mesh.start()
    try:
        assert tr.started and svc.started
        e._raise_alert("new", {"id": None}, _best(), 2)
        assert wait_for(lambda: len(tr.sent) == 1, 5)
        assert wire.parse(tr.sent[0]).count == 2
    finally:
        e.mesh.stop()
    assert not tr.started and not svc.started
