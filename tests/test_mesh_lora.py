"""LoRa-Client gegen die TESTATTRAPPE eines MeshCore-Geräts (pty) – keine echte Hardware."""
import asyncio
import random
import struct
import time

import pytest

from fakes.mesh_device import BW_HZ, CR, FREQ_KHZ, SF, FakeMeshDevice
from helpers import wait_for
from hornet.mesh import lora, wire
from hornet.mesh.lora import (DutyCycle, FrameParser, LinkError, LoraTransport, MeshLink, airtime_s, build_frame,
                              check_port, onair_bytes, parse_channel_info, parse_channel_msg, parse_self_info)
from hornet.mesh.transport import TransportError

KEY = bytes(range(16)).hex()


@pytest.fixture
def dev():
    d = FakeMeshDevice()
    yield d
    d.close()


def make_transport(dev, **kw):
    kw.setdefault("poll_s", 0.3)
    t = LoraTransport(dev.path, 115200, 1, "hornet3000", KEY, **kw)
    got = []
    t.start(lambda text, via, ts: got.append((text, via)))
    return t, got


# ── reine Funktionen ───────────────────────────────────────────────────────────────────────────────────
def test_frame_parser_handles_split_garbage_and_resync():
    p = FrameParser()
    good = b">" + (3).to_bytes(2, "little") + b"abc"
    assert p.feed(b"\x00\xffjunk" + good[:2]) == []
    assert p.feed(good[2:] + good) == [b"abc", b"abc"]
    # unmögliche Längen: weiter suchen statt hängen bleiben
    assert p.feed(b">\x00\x00" + b">\xff\xff" + good) == [b"abc"]
    assert p.feed(b">" * 10000) == [] and len(p.buf) < FrameParser.MAX_BUF + 4


def test_frame_parser_fuzz_never_raises_and_recovers():
    rnd = random.Random(5)
    p = FrameParser()
    for _ in range(3000):
        p.feed(bytes(rnd.randrange(256) for _ in range(rnd.randint(0, 40))))
    assert p.feed(b">\x02\x00ok") [-1:] == [b"ok"] or p.feed(b">\x02\x00ok") == [b"ok"]


def test_build_frame_limits():
    assert build_frame(b"\x16\x03") == b"<\x02\x00\x16\x03"
    with pytest.raises(ValueError):
        build_frame(b"")
    with pytest.raises(ValueError):
        build_frame(b"x" * 301)


def test_self_info_and_channel_parsers_use_real_layout():
    dev = FakeMeshDevice(name="Imker-Funk")
    try:
        info = parse_self_info(dev._self_info())
        assert (info.name, info.freq_mhz, info.bw_khz, info.sf, info.cr) == ("Imker-Funk", 869.525, 62.5, SF, CR)
    finally:
        dev.close()
    with pytest.raises(ValueError):
        parse_self_info(b"\x05\x00")
    ts = struct.pack("<I", 1234)
    v3 = bytes([17]) + struct.pack("<b", -8) + b"\0\0" + bytes([1, 3, 0]) + ts + b"Max: hallo\0\0"
    m = parse_channel_msg(v3)
    assert (m.channel, m.text, m.snr, m.hops, m.sender_ts) == (1, "Max: hallo", -2.0, 3, 1234)
    v2 = bytes([8, 2, 255, 0]) + ts + "Äpfel".encode()
    m = parse_channel_msg(v2)
    assert (m.channel, m.text, m.hops) == (2, "Äpfel", None)
    for bad in (b"", b"\x11", b"\x11" + b"\0" * 5, b"\x08\x01", b"\x07abc"):
        with pytest.raises(ValueError):
            parse_channel_msg(bad)
    with pytest.raises(ValueError):
        parse_channel_info(b"\x12\x01")


def test_airtime_matches_known_semtech_values():
    # SF7 / 125 kHz / CR4/5 / 8 Preamble / 20 Byte: 56,6 ms (Semtech-Rechner) – hier mit 8 statt 16 Preamble prüfen
    assert airtime_s(20, 7, 125000, 5, preamble=8) == pytest.approx(0.0566, abs=0.0005)
    # SF12 / 125 kHz / 20 Byte: 1,319 s
    assert airtime_s(20, 12, 125000, 5, preamble=8) == pytest.approx(1.3189, abs=0.002)
    with pytest.raises(ValueError):
        airtime_s(10, 4, 125000)
    assert airtime_s(100, SF, BW_HZ, CR) > airtime_s(10, SF, BW_HZ, CR) > 0


def test_duty_cycle_window():
    d = DutyCycle(0.01)                       # 36 s pro Stunde
    assert d.budget() == 36 and d.allows(30, 0)
    d.charge(30, 0)
    assert not d.allows(10, 100) and d.allows(5, 100)
    assert d.wait_s(10, 100) == pytest.approx(3500, abs=1)
    assert d.allows(10, 3601) and d.used(3601) == 0
    assert DutyCycle(5).share == 0.10 and DutyCycle(0).share == 0.001


def test_check_port_only_allows_serial_devices():
    for ok in ("/dev/ttyUSB0", "/dev/ttyACM1", "COM3", "/dev/cu.usbserial-0001", "auto", "/dev/serial/by-id/usb-Heltec_V3-if00"):
        assert check_port(ok)
    for bad in ("", "/etc/passwd", "../../dev/ttyUSB0", "socket://evil:1", "rfc2217://h:1", "/dev/tty\nUSB0", "loop://", "COM", "-h",
                "/dev/ttyUSB0/../../etc/passwd", "/dev/null", "http://x"):
        with pytest.raises(ValueError):
            check_port(bad)


def test_onair_estimate_is_conservative():
    assert onair_bytes(60) >= 60 + 16
    assert onair_bytes(0) >= 20


# ── MeshLink gegen das simulierte Gerät ───────────────────────────────────────────────────────────────────────
def test_link_handshake_and_commands(dev):
    link = MeshLink(dev.path)
    link.open()
    try:
        info = link.app_start()
        assert info.name == dev.name and info.sf == SF
        link.device_query()
        assert link.get_channel(1)[1] == "hornet3000"
        link.set_time(1_800_000_000)
        assert dev.clock_set == 1_800_000_000
        link.send_channel_text(1, "H3K1|T|abcdef12|S|0|0|-|-|-|")
        assert dev.sent == [(1, "H3K1|T|abcdef12|S|0|0|-|-|-|")]
        with pytest.raises(LinkError):
            link.get_channel(5)                  # Gerät meldet Fehler
        with pytest.raises(ValueError):
            link.send_channel_text(1, "x" * 200)
    finally:
        link.close()


def test_link_times_out_when_device_is_silent(dev):
    link = MeshLink(dev.path, timeout=0.5)
    link.open()
    try:
        dev.silent = True
        t = time.time()
        with pytest.raises(LinkError):
            link.app_start()
        assert time.time() - t < 2
    finally:
        link.close()


def test_link_ignores_garbage_and_unknown_pushes(dev):
    link = MeshLink(dev.path)
    link.open()
    try:
        dev.write_garbage(b"\xff\x00junk>\xff\xff<<")
        dev._write(bytes([0x8A, 1, 2, 3]))     # Push, den wir nicht brauchen
        assert link.app_start().name == dev.name
    finally:
        link.close()


def test_garbage_that_looks_like_a_header_swallows_one_answer_but_the_command_is_retried(dev):
    link = MeshLink(dev.path, timeout=0.6)
    link.open()
    try:
        dev.write_garbage(b">\x3c\x00\x00")       # sieht wie Kopf eines 60-Byte-Rahmens aus
        time.sleep(0.1)
        assert link.app_start().name == dev.name   # erste Antwort geht verloren, Wiederholung klappt
    finally:
        link.close()


def test_link_open_failure_is_a_readable_error():
    with pytest.raises(LinkError) as e:
        MeshLink("/dev/ttyUSB99").open()
    assert "ttyUSB99" in str(e.value)


# ── Übertragungsweg ──────────────────────────────────────────────────────────────────────────────────────────────
def test_transport_receives_pushed_messages_and_only_from_its_channel(dev):
    t, got = make_transport(dev)
    try:
        assert wait_for(lambda: t.connected)
        dev.inject_channel_text("H3K1|A|abcdef12|Nachbar|2|80|-|-|-|", channel=1)
        dev.inject_channel_text("H3K1|A|11111111|Fremd|2|80|-|-|-|", channel=0)      # öffentlicher Kanal: ignorieren
        assert wait_for(lambda: len(got) == 1)
        time.sleep(0.3)
        assert len(got) == 1 and "Nachbar: H3K1|A|abcdef12" in got[0][0] and got[0][1] == "lora"
        assert wire.parse(got[0][0]).station == "Nachbar"
        assert t.status()["rx"] == 1 and t.status()["online"]
    finally:
        t.stop()


def test_transport_works_with_old_style_message_frames(dev):
    t, got = make_transport(dev)
    try:
        dev.inject_channel_text("H3K1|T|abcdef12|N|0|0|-|-|-|", v3=False)
        assert wait_for(lambda: len(got) == 1)
    finally:
        t.stop()


def test_transport_polls_even_when_the_push_is_lost(dev):
    t, got = make_transport(dev)
    try:
        assert wait_for(lambda: t.connected)
        dev.inject_channel_text("H3K1|T|abcdef12|N|0|0|-|-|-|", push=False)
        assert wait_for(lambda: len(got) == 1, timeout=3)
    finally:
        t.stop()


def test_backlog_in_the_device_is_drained_without_waiting_for_the_poll_interval(dev):
    for i in range(130):
        dev.inject_channel_text(f"H3K1|T|{i:08x}|N|0|0|-|-|-|", push=False)
    t, got = make_transport(dev, poll_s=60.0)         # Taktintervall absichtlich riesig
    try:
        assert wait_for(lambda: len(got) == 130, timeout=15), len(got)
    finally:
        t.stop()


def test_transport_provisions_the_channel_when_key_given(settings):
    d = FakeMeshDevice(channels={})
    try:
        t, got = make_transport(d)
        assert wait_for(lambda: t.connected)
        assert d.set_channel_calls and d.set_channel_calls[0][:2] == (1, "hornet3000")
        assert d.set_channel_calls[0][2] == bytes(range(16))
        n = len(d.set_channel_calls)
        t.stop()
        t2, _ = make_transport(d)                                 # zweiter Start: Kanal stimmt schon – nichts ändern
        assert wait_for(lambda: t2.connected)
        t2.stop()
        assert len(d.set_channel_calls) == n
    finally:
        d.close()


def test_transport_sends_text_and_charges_the_duty_budget(dev):
    t, _ = make_transport(dev, duty=0.01)
    try:
        assert wait_for(lambda: t.connected)
        text = wire.encode(wire.MeshMessage("A", "abcdef12", "Stand", 1, 90), 118)
        assert t.can_send_now(text, time.time())
        t.send(text)
        assert dev.sent[-1] == (1, text)
        assert 0 < t.status()["duty_used_s"] < 3
        # Budget (36 s) mit „teuren“ Sendungen aufbrauchen
        t.duty.charge(35.9, time.time())
        assert not t.can_send_now(text, time.time())
        with pytest.raises(TransportError):
            t.send(text)
    finally:
        t.stop()


def test_send_failure_is_reported_and_does_not_charge(dev):
    t, _ = make_transport(dev)
    try:
        assert wait_for(lambda: t.connected)
        dev.fail_next_send = True
        with pytest.raises(TransportError):
            t.send("H3K1|T|abcdef12|S|0|0|-|-|-|")
        assert t.status()["duty_used_s"] == 0
    finally:
        t.stop()


def test_send_while_disconnected_raises(dev):
    t = LoraTransport(dev.path, 115200, 1, "hornet3000", KEY)
    with pytest.raises(TransportError):
        t.send("x")


def test_transport_reconnects_after_the_device_goes_away_and_comes_back(dev):
    t, got = make_transport(dev)
    try:
        assert wait_for(lambda: t.connected)
        dev.silent = True
        t._link.close()                       # Verbindung reißt ab (wie USB-Abzug)
        assert wait_for(lambda: not t.connected, timeout=3)
        dev.silent = False
        assert wait_for(lambda: t.connected, timeout=15)
        dev.inject_channel_text("H3K1|T|abcdef12|N|0|0|-|-|-|")
        assert wait_for(lambda: len(got) == 1)
        assert t.status()["reconnects"] >= 1
    finally:
        t.stop()


def test_transport_survives_missing_device_with_readable_error():
    t = LoraTransport("/dev/ttyUSB98", 115200, 1, "hornet3000", KEY)
    t.start(lambda *a: None)
    try:
        assert wait_for(lambda: bool(t.error), timeout=3)
        assert "ttyUSB98" in t.error and not t.connected
    finally:
        t.stop()


def test_transport_refuses_public_channel_and_bad_key():
    with pytest.raises(ValueError):
        LoraTransport("auto", 115200, 0, "x", KEY)
    with pytest.raises(ValueError):
        LoraTransport("auto", 115200, 8, "x", KEY)
    with pytest.raises(ValueError):
        LoraTransport("auto", 115200, 1, "x", "abcd")
    with pytest.raises(ValueError):
        LoraTransport("/etc/passwd", 115200, 1, "x", KEY)


def test_stop_is_prompt_even_while_connected(dev):
    t, _ = make_transport(dev)
    assert wait_for(lambda: t.connected)
    s = time.time()
    t.stop()
    assert time.time() - s < 4


def test_stop_and_link_loss_do_not_wait_for_the_poll_interval(dev):
    t, _ = make_transport(dev, poll_s=30.0)          # Takt absichtlich lang: früher wartete das Beenden darauf
    assert wait_for(lambda: t.connected)
    t._link.close()                                  # Verbindung weg → Abholer muss sofort aufwachen
    assert wait_for(lambda: not t.connected, timeout=1.5)
    assert wait_for(lambda: t.connected, timeout=8)
    s = time.time()
    t.stop()
    assert time.time() - s < 1.5


# ── Gegenprobe mit der offiziellen Bibliothek „meshcore“ ───────────────────────────────────────────────────────
def test_official_meshcore_library_talks_to_the_same_simulated_device(dev, monkeypatch):
    """Die Attrappe und der eigene Client sind nur dann glaubwürdig, wenn auch die offizielle Bibliothek mit der
    Attrappe zurechtkommt (sie liest dieselben Rahmen). Das ersetzt keinen Test an echter Hardware."""
    meshcore = pytest.importorskip("meshcore")
    import serial.serialposix as sp   # Die Bibliothek setzt DTR nachträglich; ein Pseudo-Terminal kennt das nicht
    monkeypatch.setattr(sp.Serial, "_update_dtr_state", lambda self: None)
    monkeypatch.setattr(sp.Serial, "_update_rts_state", lambda self: None)

    async def run():
        mc = await meshcore.MeshCore.create_serial(dev.path, 115200, debug=False)
        assert mc is not None and mc.self_info["name"] == dev.name
        assert mc.self_info["radio_freq"] == FREQ_KHZ / 1000 and mc.self_info["radio_sf"] == SF
        res = await mc.commands.send_chan_msg(1, "H3K1|T|abcdef12|S|0|0|-|-|-|")
        assert res.type != meshcore.EventType.ERROR
        dev.inject_channel_text("H3K1|T|99999999|Nachbar|0|0|-|-|-|", push=False)
        msg = await mc.commands.get_msg()
        assert msg.type == meshcore.EventType.CHANNEL_MSG_RECV
        assert "H3K1|T|99999999" in msg.payload["text"] and msg.payload["channel_idx"] == 1
        await mc.disconnect()

    asyncio.run(run())
    assert dev.sent and dev.sent[0][1].startswith("H3K1|T|abcdef12")
