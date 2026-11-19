# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende
"""Echt-Tests gegen einen echten lokalen Freenet-Knoten und das echte riverctl (nichts davon ist simuliert).

Nur mit  HORNET_REAL_FREENET=1 HORNET_RIVERCTL=/pfad/zu/riverctl  (der Knoten `freenet` liegt daneben).
Der Knoten läuft allein auf diesem Rechner (nicht im öffentlichen Freenet-Netz) – getestet wird die Anbindung
unseres Programms an Knoten und River-Raum, nicht das Freenet-Netz selbst.
"""
import json
import os
import signal
import socket
import subprocess
import time
from pathlib import Path

import pytest

from helpers import FakeHub, wait_for
from hornet.mesh import wire
from hornet.mesh.freenet import FreenetTransport, accept_invite
from hornet.mesh.service import MeshService
from hornet.mesh.transport import TransportError

RIVERCTL = os.environ.get("HORNET_RIVERCTL", "")
pytestmark = pytest.mark.skipif(os.environ.get("HORNET_REAL_FREENET") != "1" or not Path(RIVERCTL).is_file(),
                                reason="Echt-Test: HORNET_REAL_FREENET=1 und HORNET_RIVERCTL setzen")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def rc(cfg, node, *args, timeout=120):
    cmd = [RIVERCTL, "--no-version-check", "--node-url", f"{node}/v1/contract/command?encodingProtocol=native",
           "--config-dir", str(cfg), *args]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


class Node:
    def __init__(self, base: Path, port: int):
        self.base, self.port = base, port
        self.url = f"ws://127.0.0.1:{port}"
        self.proc = None

    def start(self):
        exe = str(Path(RIVERCTL).with_name("freenet"))
        for d in ("cfg", "data", "log"):
            (self.base / d).mkdir(parents=True, exist_ok=True)
        self.proc = subprocess.Popen(
            [exe, "local", "--config-dir", str(self.base / "cfg"), "--data-dir", str(self.base / "data"),
             "--log-dir", str(self.base / "log"), "--disable-auto-update", "--ws-api-address", "127.0.0.1",
             "--ws-api-port", str(self.port), "--network-address", "127.0.0.1"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        end = time.time() + 60
        while time.time() < end:
            try:
                socket.create_connection(("127.0.0.1", self.port), timeout=1).close()
                time.sleep(1.5)
                return
            except OSError:
                time.sleep(0.5)
        raise RuntimeError("Freenet-Knoten startet nicht")

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.send_signal(signal.SIGTERM)
            try:
                self.proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.proc.kill()


@pytest.fixture(scope="module")
def room(tmp_path_factory):
    base = tmp_path_factory.mktemp("freenet")
    node = Node(base, free_port())
    node.start()
    a, b = base / "stationA", base / "stationB"
    a.mkdir(), b.mkdir()
    r = rc(a, node.url, "--format", "json", "room", "create", "--name", "h3k-test", "--nickname", "StationA", "--private")
    assert r.returncode == 0, r.stderr
    owner = json.loads(r.stdout[r.stdout.index("{"):])["owner_key"]
    inv = rc(a, node.url, "--format", "json", "invite", "create", owner)
    code = json.loads(inv.stdout[inv.stdout.index("{"):])["invitation_code"]
    out = accept_invite(RIVERCTL, code, node.url, b, "StationB")      # unser eigener Beitritts-Code
    assert "can now" in out.lower() or "joined" in out.lower() or out
    yield {"node": node, "owner": owner, "a": a, "b": b}
    node.stop()


def transport(room, who):
    return FreenetTransport(RIVERCTL, room["owner"], room["node"].url, room[who])


def test_message_travels_between_two_stations_through_the_real_node(room):
    ta, tb = transport(room, "a"), transport(room, "b")
    got_a, got_b = [], []
    ta.start(lambda t, v, ts: got_a.append(t))
    tb.start(lambda t, v, ts: got_b.append(t))
    try:
        assert wait_for(lambda: ta.connected and tb.connected, 30)
        time.sleep(2)
        line = wire.encode(wire.MeshMessage("A", "abcdef12", "StationA", 2, 88, "J", None, None, "echt"), 200)
        ta.send(line)
        assert wait_for(lambda: line in got_b, 30), got_b
        time.sleep(2)
        assert got_a == []                       # eigene Nachricht kommt nicht als fremde zurück
        assert ta.me_key == room["owner"] and tb.me_key != ta.me_key and tb.me_key
        assert ta.status()["tx"] == 1 and tb.status()["rx"] == 1
    finally:
        ta.stop()
        tb.stop()


def test_two_services_alarm_forward_and_acknowledge_over_freenet(room, tmp_path):
    from hornet.config import Settings
    from hornet.store import Store
    sa = Settings(data_dir=tmp_path / "a", access_token="x" * 32, camera_name="StationA", mesh_freenet_enabled=True)
    sb = Settings(data_dir=tmp_path / "b", access_token="x" * 32, camera_name="StationB", mesh_freenet_enabled=True)
    sta, stb = Store(tmp_path / "a.db"), Store(tmp_path / "b.db")
    hub_b = FakeHub()
    svc_a = MeshService(sa, sta, {"freenet": transport(room, "a")}, jitter=lambda: 0.1)
    svc_b = MeshService(sb, stb, {"freenet": transport(room, "b")}, hub=hub_b, jitter=lambda: 0.1)
    svc_a.start()
    svc_b.start()
    try:
        assert wait_for(lambda: all(t.connected for s in (svc_a, svc_b) for t in s.transports.values()), 30)
        time.sleep(2)
        ident = svc_a.announce("new", 3, 0.91, "J", "Flugloch")
        assert wait_for(lambda: len(hub_b.texts) == 1, 40), svc_b.status()
        assert "StationA" in hub_b.texts[0][1] and "3 Tiere" in hub_b.texts[0][1]
        row = stb.mesh_list(5)[-1]
        assert (row["station"], row["count"], row["typ"], row["ai"]) == ("StationA", 3, "A", "J")
        assert wait_for(lambda: sta.mesh_ack_counts([ident]).get(ident) == 1, 40)       # Quittung von B ist bei A angekommen
        assert svc_a.counters["own"] <= 1                                                    # Eigen-Echo erkannt oder gar nicht erst geliefert
    finally:
        svc_a.stop()
        svc_b.stop()
        sta.close()
        stb.close()


def test_foreign_chat_in_the_room_is_ignored_and_garbage_is_harmless(room, tmp_path):
    from hornet.config import Settings
    from hornet.store import Store
    sb = Settings(data_dir=tmp_path / "b", access_token="x" * 32, camera_name="StationB", mesh_freenet_enabled=True)
    stb = Store(tmp_path / "b.db")
    svc_b = MeshService(sb, stb, {"freenet": transport(room, "b")}, hub=FakeHub())
    svc_b.start()
    try:
        assert wait_for(lambda: svc_b.transports["freenet"].connected, 30)
        time.sleep(2)
        for text in ["Hallo zusammen!", "H3K1|A|zzzz|x", "H3K1|A|abcdef13|<script>|9999|1|-|-|-|", "x" * 650 + " https://evil.example"]:
            assert rc(room["a"], room["node"].url, "message", "send", room["owner"], text).returncode == 0
        assert wait_for(lambda: svc_b.counters["rx"] >= 4, 40), svc_b.counters
        assert svc_b.counters["accepted"] == 0 and stb.mesh_count() == 0
    finally:
        svc_b.stop()
        stb.close()


def test_stream_restarts_after_riverctl_is_killed(room):
    ta, tb = transport(room, "a"), transport(room, "b")
    got = []
    tb.start(lambda t, v, ts: got.append(t))
    ta.start(lambda *a: None)
    try:
        assert wait_for(lambda: tb.connected and ta.connected, 30)
        old = tb._proc.pid
        os.kill(old, signal.SIGKILL)
        assert wait_for(lambda: tb._proc is not None and tb._proc.pid != old and tb.connected, 30)
        time.sleep(2)
        line = wire.encode(wire.MeshMessage("T", "abcdef99", "StationA", 0, 0, "-", None, None, "nach Neustart"), 200)
        ta.send(line)
        assert wait_for(lambda: line in got, 30)
        assert tb.restarts >= 1
    finally:
        ta.stop()
        tb.stop()


def test_send_fails_readably_when_node_is_down(room, tmp_path):
    t = FreenetTransport(RIVERCTL, room["owner"], f"ws://127.0.0.1:{free_port()}", room["a"])
    with pytest.raises(TransportError) as e:
        t.send("H3K1|T|abcdef12|S|0|0|-|-|-|")
    assert str(e.value)
    t.stop()
