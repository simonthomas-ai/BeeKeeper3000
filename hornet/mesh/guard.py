"""Flutschutz für eingehende Funkmeldungen.

Auf einem gemeinsamen Funkkanal kann jeder Teilnehmer beliebig viele Zeilen senden. Der Schutz hat vier Stufen,
die in dieser Reihenfolge greifen (billig vor teuer):

  1. Eingangs-Eimer je Übertragungsweg (`ingress`): begrenzt, wie viele Meldungen pro Sekunde überhaupt geprüft
     werden. Es gibt zwei getrennte Eimer – für bekannte und für neue/unbekannte Stationen –, damit eine Flut
     von Unbekannten die bekannten Nachbarn nicht aussperrt.
  2. Je Station ein Zeitfenster (`station`): höchstens 40 Meldungen und 8 Alarme je 10 Minuten.
  3. Neulinge: höchstens 5 Alarme pro Stunde, bis die Station als „bekannt“ gilt.
  4. Hinweis an den Betreiber höchstens einmal pro Stunde und Station (`notice`), nicht bei jeder Meldung.
"""
from __future__ import annotations

from collections import OrderedDict, deque

KNOWN_RATE = 10.0   # Meldungen/Sekunde, Eimer „bekannte Stationen“
NEW_RATE = 3.0      # Meldungen/Sekunde, Eimer „neue Stationen“
BURST_S = 3.0       # Eimergröße in Sekunden Zufluss
WINDOW_S = 600.0
WINDOW_MSGS = 40
WINDOW_ALERTS = 8
NEWCOMER_ALERTS = 5
NEWCOMER_WINDOW_S = 3600.0
NOTICE_EVERY_S = 3600.0
MAX_TRACKED = 2000  # Stationen, die gleichzeitig verfolgt werden (ältere werden vergessen)


class Bucket:
    def __init__(self, rate: float, burst_s: float = BURST_S):
        self.rate, self.cap = rate, rate * burst_s
        self.tokens, self.last = self.cap, None

    def take(self, now: float) -> bool:
        if self.last is not None:
            self.tokens = min(self.cap, self.tokens + max(0.0, now - self.last) * self.rate)
        self.last = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False


class FlowGate:
    def __init__(self):
        self._buckets: dict[tuple[str, bool], Bucket] = {}
        self._msgs: OrderedDict[str, deque[float]] = OrderedDict()
        self._alerts: OrderedDict[str, deque[float]] = OrderedDict()
        self._notice: OrderedDict[str, float] = OrderedDict()
        self.dropped = {"ingress": 0, "station": 0, "newcomer": 0}

    # -- Stufe 1 -----------------------------------------------------------------------
    def ingress(self, via: str, now: float, known: bool = False) -> bool:
        key = (via, bool(known))
        b = self._buckets.get(key)
        if b is None:
            b = self._buckets[key] = Bucket(KNOWN_RATE if known else NEW_RATE)
        ok = b.take(now)
        if not ok:
            self.dropped["ingress"] += 1
        return ok

    # -- Stufe 2 und 3 -----------------------------------------------------------------
    @staticmethod
    def _win(store: OrderedDict, key: str, now: float, span: float) -> deque:
        dq = store.get(key)
        if dq is None:
            dq = store[key] = deque()
            while len(store) > MAX_TRACKED:
                store.popitem(last=False)
        else:
            store.move_to_end(key)
        while dq and now - dq[0] > span:
            dq.popleft()
        return dq

    def busy(self, station: str, now: float) -> bool:
        """Hat die Station ihr Zeitfenster schon ausgeschöpft? (ohne zu zählen)"""
        return len(self._win(self._msgs, station, now, WINDOW_S)) >= WINDOW_MSGS

    def station(self, station: str, now: float, *, is_alert: bool, established: bool) -> tuple[bool, str]:
        """Zählt eine Meldung der Station. Rückgabe: (angenommen, Grund bei Ablehnung)."""
        msgs = self._win(self._msgs, station, now, WINDOW_S)
        if len(msgs) >= WINDOW_MSGS:
            self.dropped["station"] += 1
            return False, "Zu viele Meldungen dieser Station"
        if is_alert:
            alerts = self._win(self._alerts, station, now, NEWCOMER_WINDOW_S if not established else WINDOW_S)
            if established:
                recent = sum(1 for t in alerts if now - t <= WINDOW_S)
                if recent >= WINDOW_ALERTS:
                    self.dropped["station"] += 1
                    return False, "Zu viele Alarme dieser Station"
            elif len(alerts) >= NEWCOMER_ALERTS:
                self.dropped["newcomer"] += 1
                return False, "Neue Station: Alarmgrenze pro Stunde erreicht"
            alerts.append(now)
        msgs.append(now)
        return True, ""

    # -- Stufe 4 -----------------------------------------------------------------------
    def notice(self, station: str, now: float) -> bool:
        """True höchstens einmal pro Stunde und Station: dann darf der Betreiber informiert werden."""
        last = self._notice.get(station)
        if last is not None and now - last < NOTICE_EVERY_S:
            return False
        self._notice[station] = now
        self._notice.move_to_end(station)
        while len(self._notice) > MAX_TRACKED:
            self._notice.popitem(last=False)
        return True
