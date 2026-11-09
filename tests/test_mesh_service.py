import itertools
import time

import pytest

from helpers import FakeBus, FakeHub, FakeTransport, alert_line, wait_for
from hornet.mesh import guard, service, wire
from hornet.mesh.service import MeshService


class Clock:
    def __init__(self, t=1_800_000_000.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t += s


@pytest.fixture
def env(settings, store):
    settings.mesh_lora_enabled = True
    settings.apiary_lat, settings.apiary_lon = 51.00, 7.00
    clock = Clock()
    lora, fn = FakeTransport("lora"), FakeTransport("freenet", 200)
    bus, hub = FakeBus(), FakeHub()
    svc = MeshService(settings, store, {"lora": lora, "freenet": fn}, bus=bus, hub=hub, clock=clock,
                      jitter=lambda: 5.0)
    svc._pool.shutdown(wait=False)
    # Weiterleitung synchron ausführen, damit Tests deterministisch sind
    class Inline:
        def submit(self, fn_, *a):
            fn_(*a)
    svc._pool = Inline()
    return svc, clock, lora, fn, bus, hub


def pump(svc, clock, until=None):
    """Sender-Durchgänge von Hand ausführen (statt Thread)."""
    for _ in range(50):
        now = clock()
        ready = sorted([q for q in svc._queue if q.not_before <= now], key=lambda q: (q.prio, q.created))
        if not ready:
            break
        svc._attempt(ready[0])


# ── Senden ──────────────────────────────────────────────────────────────────────────────────────────
def test_announce_goes_to_both_transports_independently(env):
    svc, clock, lora, fn, bus, hub = env
    fn.fail = 99                                           # Freenet kaputt
    ident = svc.announce("new", 2, 0.87, "J")
    pump(svc, clock)
    assert len(lora.sent) == 1 and wire.parse(lora.sent[0]).ident == ident
    assert svc.queue_len() == 1                            # Freenet wird weiter versucht
    clock.advance(20)
    fn.fail = 0
    pump(svc, clock)
    assert len(fn.sent) == 1 and svc.queue_len() == 0
    row = svc.store.mesh_list(5)[0]
    assert row["status"] == "sent" and set(row["via"].split(",")) == {"lora", "freenet"}


def test_failed_transport_gives_up_after_max_attempts_but_other_one_delivers(env):
    svc, clock, lora, fn, *_ = env
    fn.fail = 999
    svc.announce("new", 1, 0.9)
    for _ in range(service.MAX_ATTEMPTS + 2):
        pump(svc, clock)
        clock.advance(400)
    assert svc.queue_len() == 0 and len(lora.sent) == 1 and not fn.sent
    assert svc.store.mesh_list(1)[0]["status"] == "sent" and svc.store.mesh_list(1)[0]["via"] == "lora"


def test_duty_cycle_blocks_and_releases(env):
    svc, clock, lora, *_ = env
    lora.allow = False
    svc.announce("new", 1, 0.9)
    pump(svc, clock)
    assert not lora.sent and svc.queue_len() == 1
    lora.allow = True
    pump(svc, clock)
    assert len(lora.sent) == 1


def test_disconnected_transport_keeps_message_until_it_expires(env):
    svc, clock, lora, fn, *_ = env
    lora.connected = fn.connected = False
    svc.announce("new", 1, 0.9)
    pump(svc, clock)
    assert svc.queue_len() == 1
    clock.advance(service.TTL["A"] + 1)
    pump(svc, clock)
    assert svc.queue_len() == 0 and svc.store.mesh_list(1)[0]["status"] == "expired" or \
        svc.store.mesh_list(1)[0]["status"] == "failed"
    assert svc.counters["expired"] == 1


def test_alerts_are_sent_before_tests_and_receipts(env):
    svc, clock, lora, fn, *_ = env
    svc.send_test()
    svc.on_receive(alert_line("11111111", "Nachbar"), "lora")
    clock.advance(10)
    svc.announce("new", 1, 0.9)
    order = []
    for _ in range(10):
        now = clock()
        ready = sorted([q for q in svc._queue if q.not_before <= now], key=lambda q: (q.prio, q.created))
        if not ready:
            break
        order.append(ready[0].typ)
        svc._attempt(ready[0])
    assert order[0] == "A" and order.index("R") < order.index("T")


def test_queue_is_capped_and_alerts_survive_a_test_flood(env):
    svc, clock, lora, fn, *_ = env
    lora.connected = fn.connected = False
    for _ in range(service.QUEUE_MAX + 50):
        svc.send_test()
    assert svc.queue_len() <= service.QUEUE_MAX
    svc.announce("new", 1, 0.9)
    assert svc.queue_len() <= service.QUEUE_MAX
    assert any(q.typ == "A" for q in svc._queue)


def test_non_alert_kinds_are_never_announced(env):
    svc, *_ = env
    assert svc.announce("reminder", 1, 0.9) is None and svc.announce("test", 1, 0.9) is None and svc.queue_len() == 0


def test_position_only_when_enabled_and_rounded(env):
    svc, clock, lora, *_ = env
    svc.s.apiary_lat, svc.s.apiary_lon = 51.04567, 7.12345
    svc.announce("new", 1, 0.9)
    pump(svc, clock)
    assert wire.parse(lora.sent[-1]).lat is None
    svc.s.mesh_share_position = True
    svc.announce("new", 1, 0.9)
    pump(svc, clock)
    m = wire.parse(lora.sent[-1])
    assert (m.lat, m.lon) == (51.05, 7.12)


def test_sender_thread_delivers_in_real_time(settings, store):
    t = FakeTransport("lora")
    svc = MeshService(settings, store, {"lora": t})
    svc.start()
    try:
        svc.announce("new", 1, 0.9)
        assert wait_for(lambda: len(t.sent) == 1)
        assert t.started
    finally:
        svc.stop()
    assert not t.started


# ── Empfangen ───────────────────────────────────────────────────────────────────────────────────────
def test_accepted_alert_is_logged_published_forwarded_and_acked(env):
    svc, clock, lora, fn, bus, hub = env
    assert svc.on_receive(alert_line("aaaaaaa1", "Nachbar", 3, 91, lat=51.05, lon=7.05, note="Flugloch"), "lora")
    row = svc.store.mesh_list(1)[0]
    assert (row["direction"], row["station"], row["count"], row["status"], row["via"]) == ("in", "Nachbar", 3, "ok", "lora")
    ev = [d for e, d in bus.events if e == "mesh"][0]
    assert ev["station"] == "Nachbar" and 5 < ev["km"] < 9
    assert len(hub.texts) == 1 and "Nachbar" in hub.texts[0][1] and "ca. " in hub.texts[0][1]
    assert any(q.typ == "R" and q.targets == {"lora": "pending"} for q in svc._queue)      # Quittung nur auf dem Empfangsweg


def test_ack_is_delayed_and_suppressed_when_others_already_acked(env):
    svc, clock, lora, *_ = env
    svc.on_receive(alert_line("aaaaaaa1", "Nachbar"), "lora")
    ack = next(q for q in svc._queue if q.typ == "R")
    assert ack.not_before - clock() == 5.0
    # zwei andere Stationen quittieren in der Wartezeit – eigene Quittung entfällt
    svc.store.mesh_seen_add("out:aaaaaaa1")  # (nur damit Quittungen als „für uns“ zählen würden – hier irrelevant)
    for n in ("S1", "S2"):
        svc.store.mesh_add(direction="in", via="lora", typ="R", ident="aaaaaaa1", station=n, status="ok")
    clock.advance(6)
    pump(svc, clock)
    assert not lora.sent and svc.queue_len() == 0


def test_test_messages_are_logged_but_never_forwarded(env):
    svc, clock, lora, fn, bus, hub = env
    assert svc.on_receive(alert_line("bbbbbbb1", "Nachbar", typ="T"), "lora")
    assert not hub.texts


def test_forwarding_respects_mute_setting_and_switch(env):
    svc, clock, lora, fn, bus, hub = env
    svc.forward_ok = lambda: False
    svc.on_receive(alert_line("ccccccc1", "Nachbar"), "lora")
    assert not hub.texts
    svc.forward_ok = lambda: True
    svc.s.mesh_forward = False
    svc.on_receive(alert_line("ccccccc2", "Nachbar"), "lora")
    assert not hub.texts


def test_forward_failure_does_not_break_receiving(env):
    svc, clock, lora, fn, bus, hub = env
    hub.fail = True
    assert svc.on_receive(alert_line("ddddddd1", "Nachbar"), "lora")
    assert svc.store.mesh_count() >= 1


def test_forwarded_text_contains_no_link_or_markup_from_the_sender(env):
    svc, clock, lora, fn, bus, hub = env
    svc.on_receive(alert_line("eeeeeee1", "http://evil.example", note="klick https://evil.example/x @alle"), "lora")
    text = hub.texts[0][1] + hub.texts[0][2]
    assert "evil" not in text and "http" not in text and "@" not in text


def test_duplicate_over_both_transports_counts_once(env):
    svc, clock, *_ = env
    line = alert_line("fffffff1", "Nachbar")
    assert svc.on_receive(line, "lora") is True
    assert svc.on_receive(line, "freenet") is False
    assert svc.counters["accepted"] == 1 and svc.counters["dup"] == 1


def test_duplicates_cost_no_rate_budget(env):
    svc, clock, *_ = env
    line = alert_line("fffffff2", "Nachbar")
    svc.on_receive(line, "lora")
    for _ in range(5000):
        svc.on_receive(line, "lora")
    assert svc.counters["limited"] == 0
    assert svc.on_receive(alert_line("fffffff3", "Nachbar"), "lora")


def test_duplicate_detection_survives_restart(settings, store):
    a = MeshService(settings, store, {"lora": FakeTransport()}, clock=Clock())
    line = alert_line("12121212", "Nachbar")
    assert a.on_receive(line, "lora")
    b = MeshService(settings, store, {"lora": FakeTransport()}, clock=Clock())
    assert b.on_receive(line, "lora") is False


def test_own_alert_coming_back_is_ignored(env):
    svc, clock, lora, fn, bus, hub = env
    svc.announce("new", 1, 0.9)
    pump(svc, clock)
    echo = lora.sent[0]
    assert svc.on_receive(echo, "freenet") is False
    assert svc.counters["own"] == 1 and not hub.texts


def test_receipts_for_own_message_are_counted_foreign_ones_ignored(env):
    svc, clock, lora, *_ = env
    ident = svc.announce("new", 1, 0.9)
    pump(svc, clock)
    assert svc.on_receive(wire.encode(wire.receipt(ident, "S1")), "lora")
    assert svc.on_receive(wire.encode(wire.receipt(ident, "S2")), "lora")
    assert svc.on_receive(wire.encode(wire.receipt(ident, "S2")), "lora") is False          # doppelt
    assert svc.on_receive(wire.encode(wire.receipt("99999999", "S3")), "lora") is False     # fremde Meldung
    assert svc.store.mesh_ack_counts([ident]) == {ident: 2}


def test_garbage_is_dropped_without_writing_to_the_database(env):
    svc, *_ = env
    before = svc.store.mesh_count()
    for junk in ["", "hallo welt", "H3K1|", "H3K1|A|x", "x" * 5000, None, 123, b"H3K1|A|abcdef12|s|1|1|-|-|-|"]:
        assert svc.on_receive(junk, "lora") is False
    assert svc.store.mesh_count() == before and svc.counters["rejected"] == 8


def test_station_window_limits_messages_and_alerts(env):
    svc, clock, *_ = env
    ok = 0
    for i in range(30):
        clock.advance(2)
        ok += svc.on_receive(alert_line(f"{i:08x}", "Vielschreiber", typ="T"), "lora")
    assert ok == 30
    for i in range(30, 60):
        clock.advance(2)
        ok += svc.on_receive(alert_line(f"{i:08x}", "Vielschreiber", typ="T"), "lora")
    assert ok == guard.WINDOW_MSGS                       # danach dicht
    clock.advance(guard.WINDOW_S + 1)
    assert svc.on_receive(alert_line("0000ffff", "Vielschreiber", typ="T"), "lora")


def test_newcomer_alert_limit_per_hour_and_one_notice(env):
    svc, clock, lora, fn, bus, hub = env
    accepted = 0
    for i in range(20):
        clock.advance(20)
        accepted += svc.on_receive(alert_line(f"{i + 100:08x}", "Neuling"), "lora")
    assert accepted == guard.NEWCOMER_ALERTS
    notices = [d for e, d in bus.events if e == "mesh_notice"]
    assert len(notices) == 1 and notices[0]["station"] == "Neuling"          # nur eine Meldung an den Betreiber
    limited_rows = [r for r in svc.store.mesh_list(200) if r["status"] == "limited"]
    assert len(limited_rows) == 1


def test_trusted_station_skips_newcomer_limit(env):
    svc, clock, *_ = env
    svc._trusted = {"freund"}
    ok = 0
    for i in range(8):
        clock.advance(70)
        ok += svc.on_receive(alert_line(f"{i + 200:08x}", "Freund"), "lora")
    assert ok == 8


def test_station_becomes_established_after_history(env):
    svc, clock, *_ = env
    for i in range(3):
        clock.advance(2)
        svc.on_receive(alert_line(f"{i + 300:08x}", "Alter Hase", typ="T"), "lora")
    clock.advance(3700)
    svc._est_cache.clear()
    assert svc._is_established("Alter Hase", clock())
    assert not svc._is_established("Unbekannt", clock())


def test_unknown_flood_does_not_lock_out_known_stations(env):
    svc, clock, *_ = env
    svc._trusted = {"nachbar"}
    # Flut unbekannter Absender mit vielen verschiedenen Namen, ohne dass Zeit vergeht
    flood_ok = sum(svc.on_receive(alert_line(f"{i:08x}", f"Fremd{i}", typ="T"), "lora") for i in range(2000))
    assert flood_ok <= int(guard.NEW_RATE * guard.BURST_S) + 1       # nur der Eimer-Inhalt kommt durch
    assert svc.on_receive(alert_line("77777777", "Nachbar"), "lora")  # bekannte Station wird nicht ausgesperrt


def test_flood_keeps_database_and_memory_bounded(env):
    svc, clock, *_ = env
    for i in range(8000):
        clock.advance(0.5)
        svc.on_receive(alert_line(f"{i:08x}", f"F{i % 5000}", typ="T"), "lora")
    assert svc.store.mesh_count() <= 21000
    assert len(svc._mem_seen) <= service.MEM_SEEN_MAX and len(svc.gate._msgs) <= guard.MAX_TRACKED


def test_mesh_log_is_trimmed(store):
    from hornet import store as st
    for i in range(st.MESH_LOG_MAX + 3 * st.MESH_LOG_TRIM_EVERY):
        store.mesh_add(direction="in", via="lora", typ="T", ident=f"{i:08x}", station="x", status="ok")
    assert store.mesh_count() <= st.MESH_LOG_MAX + st.MESH_LOG_TRIM_EVERY


def test_store_refuses_unknown_columns(store):
    with pytest.raises(ValueError):
        store.mesh_add(direction="in", **{"station) VALUES (1); DROP TABLE mesh_log; --": "x"})
    with pytest.raises(ValueError):
        store.add_alert(**{"x": 1})
    assert store.mesh_count() == 0


def test_exception_in_processing_is_contained(env, monkeypatch):
    svc, *_ = env
    monkeypatch.setattr(svc.store, "mesh_add", lambda **k: (_ for _ in ()).throw(RuntimeError("db kaputt")))
    assert svc.on_receive(alert_line("abababab", "Nachbar"), "lora") is False
