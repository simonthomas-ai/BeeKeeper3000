"""Hilfsklassen für Tests (Testattrappen – nicht Teil des Programms)."""
from __future__ import annotations

import threading
import time

from hornet.mesh import wire
from hornet.mesh.transport import Transport, TransportError


class FakeTransport(Transport):
    """TESTATTRAPPE eines Übertragungswegs."""

    def __init__(self, name="lora", max_bytes=118):
        super().__init__()
        self.name, self.label, self.max_bytes = name, name, max_bytes
        self.sent: list[str] = []
        self.connected = True
        self.fail = 0
        self.allow = True
        self.started = False

    def start(self, on_receive):
        super().start(on_receive)
        self.started = True

    def stop(self):
        self.started = False

    def can_send_now(self, text, now):
        return self.allow

    def send(self, text):
        if self.fail:
            self.fail -= 1
            raise TransportError("simulierter Fehler")
        self.sent.append(text)

    def status(self):
        return {"name": self.name, "label": self.label, "online": self.connected, "detail": ""}


class FakeBus:
    def __init__(self):
        self.events = []

    def publish(self, event, data):
        self.events.append((event, data))


class FakeHub:
    def __init__(self):
        self.texts = []
        self.fail = False

    def dispatch(self, kind, long_text, short_text=""):
        if self.fail:
            raise RuntimeError("kaputt")
        self.texts.append((kind, long_text, short_text))
        return ["telegram"]


def alert_line(ident="abcdef12", station="Nachbar", count=1, conf=80, typ="A", lat=None, lon=None, note="", ai="-"):
    return wire.encode(wire.MeshMessage(typ, ident, station, count, conf, ai, lat, lon, note), 400)


def wait_for(cond, timeout=5.0, step=0.02):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(step)
    return cond()
