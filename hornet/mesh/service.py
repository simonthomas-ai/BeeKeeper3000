# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende
"""Funknetz-Dienst: verbindet Alarme mit den Übertragungswegen.

Senden:   `announce()` stellt eine Sichtung in die Warteschlange; ein Sender-Thread verteilt sie an alle
          eingeschalteten Wege (LoRa und Freenet unabhängig voneinander), beachtet dabei Sendezeit-Budget und
          Verbindungsabbrüche und wiederholt, bis die Meldung zugestellt oder abgelaufen ist.
Empfangen: `on_receive()` ist der einzige Eingang für Fremdtext. Reihenfolge – billig vor teuer:
          Längenprüfung → strenge Formatprüfung → Duplikat (gratis) → Flutschutz → Datenbank-Duplikat →
          eigene Meldung → Stations-Limits → Protokoll → Weiterleitung/Quittung.
"""
from __future__ import annotations

import logging
import math
import random
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable

from ..config import Settings
from ..store import Store
from . import wire
from .guard import FlowGate
from .transport import Transport, TransportError

log = logging.getLogger("hornet.mesh")

QUEUE_MAX = 200
ACK_QUEUE_MAX = 50
TTL = {"A": 1800.0, "U": 900.0, "R": 300.0, "T": 300.0}
PRIO = {"A": 0, "U": 1, "R": 2, "T": 3}
MAX_ATTEMPTS = 5
SEND_GAP_S = 1.0
MEM_SEEN_MAX = 5000
MEM_SEEN_TTL = 86400.0
ESTABLISHED_MIN_N = 3
ESTABLISHED_MIN_AGE_S = 3600.0


def km_between(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0 * 2 * math.asin(min(1.0, math.sqrt(a)))


@dataclass
class _Out:
    ident: str
    typ: str
    text: str
    created: float
    not_before: float
    targets: dict[str, str]                   # Weg -> pending | sent | failed
    row_id: int | None = None
    attempts: dict[str, int] = field(default_factory=dict)
    retry_at: dict[str, float] = field(default_factory=dict)
    skip_if_acked: int = 0                    # Quittungen: nicht senden, wenn schon so viele andere quittiert haben

    @property
    def prio(self) -> int:
        return PRIO.get(self.typ, 9)


class MeshService:
    def __init__(self, s: Settings, store: Store, transports: dict[str, Transport], *, bus=None, hub=None,
                 forward_ok: Callable[[], bool] | None = None, clock: Callable[[], float] = time.time,
                 jitter: Callable[[], float] | None = None):
        self.s, self.store, self.bus, self.hub = s, store, bus, hub
        self.transports = transports
        self.clock = clock
        self.forward_ok = forward_ok or (lambda: True)
        self._jitter = jitter or (lambda: random.uniform(2.0, 12.0))
        self.gate = FlowGate()
        self.counters = {"rx": 0, "rejected": 0, "dup": 0, "own": 0, "limited": 0, "accepted": 0, "forwarded": 0,
                         "sent": 0, "send_failed": 0, "expired": 0, "dropped_queue": 0}
        self._lock = threading.RLock()
        self._mem_seen: OrderedDict[str, float] = OrderedDict()
        self._est_cache: dict[str, tuple[float, bool]] = {}
        self._queue: list[_Out] = []
        self._cond = threading.Condition()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="mesh-fwd")
        self._trusted = {t.lower() for t in s.mesh_trusted}
        self.started = False

    # -- Lebenszyklus --------------------------------------------------------------------
    def start(self) -> None:
        self._stop.clear()
        for t in self.transports.values():
            try:
                t.start(self.on_receive)
            except Exception:
                log.exception("Übertragungsweg %s konnte nicht gestartet werden", t.name)
        self._thread = threading.Thread(target=self._sender, daemon=True, name="mesh-sender")
        self._thread.start()
        self.started = True

    def stop(self) -> None:
        self._stop.set()
        with self._cond:
            self._cond.notify_all()
        for t in self.transports.values():
            try:
                t.stop()
            except Exception:
                log.exception("Übertragungsweg %s lässt sich nicht sauber beenden", t.name)
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._pool.shutdown(wait=False, cancel_futures=True)
        self.started = False

    # ── Senden ───────────────────────────────────────────────────────────────────────────────
    def _position(self) -> tuple[float | None, float | None]:
        if not self.s.mesh_share_position or not (self.s.apiary_lat or self.s.apiary_lon):
            return None, None
        return round(self.s.apiary_lat, 2), round(self.s.apiary_lon, 2)

    def announce(self, kind: str, count: int, conf: float, ai: str = "-", note: str = "") -> str | None:
        """Meldet eine Sichtung (kind: new → A, update → U) an alle eingeschalteten Wege. Gibt die Kennung zurück."""
        typ = {"new": "A", "update": "U"}.get(kind)
        if typ is None or not self.transports:
            return None
        lat, lon = self._position()
        msg = wire.MeshMessage(typ, wire.new_ident(), self.s.mesh_station_name, count, int(round(conf * 100)),
                               ai if ai in wire.AI_CODES else "-", lat, lon, note)
        return self._enqueue_message(msg)

    def send_test(self, note: str = "Test") -> str | None:
        if not self.transports:
            return None
        msg = wire.MeshMessage("T", wire.new_ident(), self.s.mesh_station_name, 0, 0, "-", None, None, note)
        return self._enqueue_message(msg)

    def _enqueue_message(self, msg: wire.MeshMessage, only: set[str] | None = None) -> str | None:
        targets = {n: "pending" for n, t in self.transports.items() if not only or n in only}
        if not targets:
            return None
        text = wire.encode(msg, min(t.max_bytes for t in self.transports.values() if t.name in targets))
        now = self.clock()
        self.store.mesh_seen_add("out:" + msg.ident, now)
        row = self.store.mesh_add(ts=now, direction="out", via=",".join(sorted(targets)), typ=msg.typ,
                                  ident=msg.ident, station=msg.station, count=msg.count, conf=msg.conf / 100,
                                  ai=msg.ai, lat=msg.lat, lon=msg.lon, note=msg.note, status="queued")
        self._push(_Out(msg.ident, msg.typ, text, now, now, targets, row))
        return msg.ident

    def _push(self, item: _Out) -> None:
        with self._cond:
            if item.typ == "R":
                acks = [q for q in self._queue if q.typ == "R"]
                if len(acks) >= ACK_QUEUE_MAX:
                    self.counters["dropped_queue"] += 1
                    return
            if len(self._queue) >= QUEUE_MAX:
                victim = max(self._queue, key=lambda q: (q.prio, -q.created))   # unwichtigste, älteste zuerst
                if victim.prio <= item.prio:
                    self.counters["dropped_queue"] += 1
                    if item.row_id:
                        self.store.mesh_update(item.row_id, status="failed")
                    return
                self._queue.remove(victim)
                self.counters["dropped_queue"] += 1
                if victim.row_id:
                    self.store.mesh_update(victim.row_id, status="failed")
            self._queue.append(item)
            self._cond.notify_all()

    def queue_len(self) -> int:
        with self._cond:
            return len(self._queue)

    def _sender(self) -> None:
        while not self._stop.is_set():
            wait = 5.0
            item: _Out | None = None
            with self._cond:
                now = self.clock()
                ready = [q for q in self._queue if q.not_before <= now]
                if ready:
                    ready.sort(key=lambda q: (q.prio, q.created))
                    item = ready[0]
                else:
                    later = [q.not_before - now for q in self._queue]
                    wait = max(0.1, min([wait, *later]))
                    self._cond.wait(timeout=wait)
                    continue
            did = self._attempt(item)
            if not did:
                with self._cond:     # nichts ging – kurz warten, damit keine Dauerschleife entsteht
                    self._cond.wait(timeout=1.0)
            else:
                self._stop.wait(SEND_GAP_S)

    def _attempt(self, item: _Out) -> bool:
        """Ein Durchgang für eine Meldung. Rückgabe: True, wenn irgendwo tatsächlich gesendet wurde."""
        now = self.clock()
        sent_any = False
        if item.typ == "R" and item.skip_if_acked and self._ack_count(item.ident) >= item.skip_if_acked:
            self._finish(item, "expired")
            return False
        if now - item.created > TTL.get(item.typ, 300.0):
            self._finish(item, "expired")
            return False
        for name, st in list(item.targets.items()):
            if st != "pending" or item.retry_at.get(name, 0) > now:
                continue
            t = self.transports.get(name)
            if t is None:
                item.targets[name] = "failed"
                continue
            try:
                if not getattr(t, "connected", True) or not t.can_send_now(item.text, now):
                    continue
                t.send(item.text)
            except TransportError as e:
                n = item.attempts[name] = item.attempts.get(name, 0) + 1
                self.counters["send_failed"] += 1
                log.warning("Senden über %s fehlgeschlagen (%d): %s", name, n, e)
                if n >= MAX_ATTEMPTS:
                    item.targets[name] = "failed"
                else:
                    item.retry_at[name] = now + min(300.0, 15.0 * n)
                continue
            except Exception:
                log.exception("Unerwarteter Fehler beim Senden über %s", name)
                item.targets[name] = "failed"
                continue
            item.targets[name] = "sent"
            self.counters["sent"] += 1
            sent_any = True
        if all(v != "pending" for v in item.targets.values()):
            ok = any(v == "sent" for v in item.targets.values())
            self._finish(item, "sent" if ok else "failed")
        return sent_any

    def _finish(self, item: _Out, status: str) -> None:
        with self._cond:
            if item in self._queue:
                self._queue.remove(item)
        if status == "expired":
            if any(v == "sent" for v in item.targets.values()):
                status = "sent"
            else:
                self.counters["expired"] += 1
        if item.row_id:
            via = ",".join(n for n, v in item.targets.items() if v == "sent") or ",".join(item.targets)
            try:
                self.store.mesh_update(item.row_id, status=status, via=via)
            except Exception:
                log.exception("Funkprotokoll nicht aktualisierbar")

    def _ack_count(self, ident: str) -> int:
        with self.store._lock:  # noqa: SLF001 – gleiche Datenbankverbindung
            r = self.store._db.execute(  # noqa: SLF001
                "SELECT COUNT(*) c FROM mesh_log WHERE direction='in' AND typ='R' AND ident=?", (ident,)).fetchone()
        return int(r["c"])

    # ── Empfangen ────────────────────────────────────────────────────────────────────────────
    def _remember(self, key: str, now: float) -> None:
        self._mem_seen[key] = now
        self._mem_seen.move_to_end(key)
        while len(self._mem_seen) > MEM_SEEN_MAX:
            self._mem_seen.popitem(last=False)

    def _seen_mem(self, key: str, now: float) -> bool:
        t = self._mem_seen.get(key)
        if t is None:
            return False
        if now - t > MEM_SEEN_TTL:
            del self._mem_seen[key]
            return False
        return True

    def _is_established(self, station: str, now: float) -> bool:
        if station.lower() in self._trusted:
            return True
        hit = self._est_cache.get(station)
        if hit and now - hit[0] < 60.0:
            return hit[1]
        st = self.store.mesh_station_stats(station)
        ok = st["n"] >= ESTABLISHED_MIN_N and st["first"] is not None and now - st["first"] >= ESTABLISHED_MIN_AGE_S
        if len(self._est_cache) > 4000:
            self._est_cache.clear()
        self._est_cache[station] = (now, ok)
        return ok

    @staticmethod
    def _key(m: wire.MeshMessage) -> str:
        return f"R:{m.ident}:{m.station.lower()}" if m.typ == "R" else f"M:{m.ident}"

    def on_receive(self, text: str, via: str, now: float | None = None) -> bool:
        """Verarbeitet eine empfangene Zeile. Rückgabe: True, wenn sie angenommen wurde."""
        now = self.clock() if now is None else now
        try:
            return self._receive(text, via, now)
        except Exception:
            log.exception("Fehler bei der Verarbeitung einer Funkmeldung")
            return False

    def _receive(self, text: str, via: str, now: float) -> bool:
        with self._lock:
            self.counters["rx"] += 1
            if not isinstance(text, str) or len(text) > wire.RX_MAX_CHARS:
                self.counters["rejected"] += 1
                return False
            msg = wire.parse(text)
            if msg is None:
                self.counters["rejected"] += 1
                return False
            key = self._key(msg)
            if self._seen_mem(key, now):
                self.counters["dup"] += 1                      # Duplikate kosten nichts (Wiederholer senden alles mehrfach)
                return False
            known = self._is_established(msg.station, now)
            if self.gate.busy(msg.station, now) or not self.gate.ingress(via, now, known):
                self.counters["limited"] += 1
                self._limit_notice(msg.station, via, now, "Zu viele Meldungen")
                return False
            if self.store.mesh_seen_has(key):
                self._remember(key, now)
                self.counters["dup"] += 1
                return False
            if msg.typ != "R" and self.store.mesh_seen_has("out:" + msg.ident):
                self._remember(key, now)
                self.counters["own"] += 1
                return False
            if msg.typ == "R" and not self.store.mesh_seen_has("out:" + msg.ident):
                # Quittung für die Meldung einer anderen Station: weder speichern noch zählen (hält das Protokoll klein)
                self._remember(key, now)
                return False
            ok, why = self.gate.station(msg.station, now, is_alert=msg.is_alert, established=known)
            if not ok:
                self.counters["limited"] += 1
                self._limit_notice(msg.station, via, now, why)
                return False
            self.store.mesh_seen_add(key, now)
            self._remember(key, now)
            row = self.store.mesh_add(
                ts=now, direction="in", via=via, typ=msg.typ, ident=msg.ident, station=msg.station, count=msg.count,
                conf=msg.conf / 100, ai=msg.ai, lat=msg.lat, lon=msg.lon, note=msg.note, status="ok")
            self.counters["accepted"] += 1
        self._after_accept(msg, via, now, row)
        return True

    def _limit_notice(self, station: str, via: str, now: float, why: str) -> None:
        if self.gate.notice(station, now):
            self.store.mesh_add(ts=now, direction="in", via=via, typ=None, ident=None, station=station,
                                note=why[:80], status="limited")
            self._publish("mesh_notice", {"station": station, "via": via, "reason": why})
            log.warning("Funknetz: Station „%s“ wird begrenzt (%s)", station, why)

    def _publish(self, event: str, data: dict) -> None:
        if self.bus is not None:
            try:
                self.bus.publish(event, data)
            except Exception:
                pass

    def _after_accept(self, msg: wire.MeshMessage, via: str, now: float, row: int) -> None:
        if msg.typ == "R":
            self._publish("mesh", {"typ": "R", "station": msg.station, "ident": msg.ident, "via": via, "ts": now})
            return
        dist = None
        if msg.lat is not None and msg.lon is not None and (self.s.apiary_lat or self.s.apiary_lon):
            dist = km_between(self.s.apiary_lat, self.s.apiary_lon, msg.lat, msg.lon)
        self._publish("mesh", {"typ": msg.typ, "station": msg.station, "ident": msg.ident, "via": via, "ts": now,
                               "count": msg.count, "conf": msg.conf / 100, "ai": msg.ai, "lat": msg.lat,
                               "lon": msg.lon, "note": msg.note, "km": None if dist is None else round(dist, 1)})
        if msg.is_alert and self.s.mesh_forward and self.hub is not None and self.forward_ok():
            self._pool.submit(self._forward, msg, via, dist)
        if self.s.mesh_ack and self.transports.get(via) is not None:
            ack = _Out(msg.ident, "R", "", now, now + self._jitter(), {via: "pending"}, None, skip_if_acked=2)
            ack_msg = wire.receipt(msg.ident, self.s.mesh_station_name)
            ack.text = wire.encode(ack_msg, self.transports[via].max_bytes)
            self._push(ack)

    def _forward(self, msg: wire.MeshMessage, via: str, dist: float | None) -> None:
        animals = "1 Tier" if msg.count == 1 else f"{msg.count} Tiere"
        where = f", ca. {dist:.0f} km entfernt" if dist is not None else (
            f" (Position {msg.lat:.2f}, {msg.lon:.2f})" if msg.lat is not None else "")
        head = "📡 Funknetz: Nachbarstation meldet Asiatische Hornisse" if msg.typ == "A" else \
               "📡 Funknetz: Nachbarstation meldet Verstärkung"
        ai = {"J": " · KI-Prüfung bestätigt", "N": " · KI-Prüfung widerspricht", "?": " · KI-Prüfung unklar"}.get(msg.ai, "")
        long_text = (f"{head}\nStation „{msg.station}“{where}\n{animals} · Sicherheit {msg.conf} %{ai}"
                     + (f"\nNotiz: {msg.note}" if msg.note else "")
                     + "\nUngeprüfte Meldung aus dem Funknetz – Bienenstand im Blick behalten.")
        short = f"FUNKNETZ {msg.station}: Hornisse, {animals}, {msg.conf}%{where}"
        try:
            res = self.hub.dispatch("text", long_text, short)
            self.counters["forwarded"] += 1
            if res:
                log.info("Funkmeldung von %s weitergeleitet: %s", msg.station, ", ".join(res))
        except Exception:
            log.exception("Weiterleitung der Funkmeldung fehlgeschlagen")

    # ── Status ───────────────────────────────────────────────────────────────────────────────
    def status(self) -> dict:
        return {
            "enabled": bool(self.transports), "station": self.s.mesh_station_name,
            "share_position": self.s.mesh_share_position, "forward": self.s.mesh_forward, "ack": self.s.mesh_ack,
            "transports": [t.status() for t in self.transports.values()],
            "queue": self.queue_len(), "counters": dict(self.counters), "gate_dropped": dict(self.gate.dropped),
            "log_rows": self.store.mesh_count(), "stations": self.store.mesh_stations(20),
        }
