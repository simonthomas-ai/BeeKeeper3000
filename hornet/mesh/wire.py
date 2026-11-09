"""Nachrichtenformat H3K1 für das Funknetz zwischen den Stationen (LoRa/MeshCore und Freenet/River).

Eine Meldung ist eine einzige Textzeile:

    H3K1|<Typ>|<Kennung>|<Station>|<Anzahl>|<Sicherheit>|<KI>|<Breite>|<Länge>|<Notiz>

  Typ        A = neue Sichtung, U = Verstärkung, T = Test, R = Quittung (Empfangsbestätigung)
  Kennung    8 Hexzeichen; bei R die Kennung der bestätigten Meldung
  Station    Name der meldenden Station (Klartext, ohne | und @)
  Anzahl     Tiere im Bild (0–999)
  Sicherheit Erkennungssicherheit in Prozent (0–100)
  KI         Zweitprüfung: - keine, J bestätigt, N widerspricht, ? unklar
  Breite/Länge  Dezimalgrad auf ca. 1 km gerundet, oder - (wenn nicht freigegeben)
  Notiz      Freitext (gekürzt)

Alles, was von außen hereinkommt, ist nicht vertrauenswürdig: `parse()` prüft jedes Feld streng, entfernt
Steuer-/Unsichtbar-Zeichen und Links und gibt bei jedem Zweifel None zurück. Kein Funknetz-Teilnehmer kann
darüber Befehle, Links oder Formatierung in die Meldewege der anderen einschleusen.
"""
from __future__ import annotations

import re
import secrets
from dataclasses import dataclass

MAGIC = "H3K1"
TYPES = ("A", "U", "T", "R")
AI_CODES = ("-", "J", "N", "?")
RX_MAX_CHARS = 600        # längere Eingänge werden verworfen, bevor sie geprüft werden
LORA_MAX_BYTES = 118      # MeshCore erlaubt rund 160 Byte inkl. „Gerätename: “ – so bleibt Reserve
STATION_MAX_BYTES = 24
NOTE_MAX_BYTES = 60

# Zeichen, die nie in eine Meldung gehören: C0/C1-Steuerzeichen, unsichtbare und Richtungs-Umschalter
# (Text umdrehen/verstecken), Tag-Zeichen, Ersatzzeichen, Zeilen-/Absatztrenner.
_CTRL_RE = re.compile(
    "[\u0000-\u001f\u007f-\u009f­؜᠎​-‏ -‮⁠-⁯﻿"
    "￹-￻\ud800-\udfff\U000e0000-\U000e007f]")
_LINK_RE = re.compile(
    r"(?i)(?:\b[a-z][a-z0-9+.\-]{1,12}://\S*|\bwww\.\S*|(?:[a-z0-9-]{1,63}\.){1,8}[a-z]{2,24}\b"
    r"|\b\d{1,3}(?:\.\d{1,3}){3}\b|\bmailto:\S*|\btel:\S*)")
_ID_RE = re.compile(r"[0-9a-f]{8}")
_COORD_RE = re.compile(r"-?[0-9]{1,3}(?:\.[0-9]{1,6})?")


@dataclass(frozen=True)
class MeshMessage:
    typ: str
    ident: str
    station: str
    count: int = 1
    conf: int = 0
    ai: str = "-"
    lat: float | None = None
    lon: float | None = None
    note: str = ""

    @property
    def is_alert(self) -> bool:
        return self.typ in ("A", "U")


def new_ident() -> str:
    return secrets.token_hex(4)


def _clip(value: str, max_bytes: int) -> str:
    """Kürzt auf höchstens max_bytes UTF-8-Bytes, ohne ein Zeichen zu zerschneiden."""
    raw = value.encode("utf-8", "ignore")
    if len(raw) <= max_bytes:
        return value
    return raw[:max_bytes].decode("utf-8", "ignore")


def _no_links(value: str, max_bytes: int) -> str:
    """Entfernt Link-artige Muster und kürzt – wiederholt, bis sich nichts mehr ändert. Entfernen und Kürzen
    können beide neue Muster erzeugen (Reste fügen sich zusammen, ein Schnitt lässt „abc.de“ übrig)."""
    out = value
    for _ in range(8):
        nxt = _clip(" ".join(_LINK_RE.sub(" ", out).split()), max_bytes).strip()
        if nxt == out:
            return out
        out = nxt
    # Nach 8 Runden noch Bewegung: Punkte, Doppelpunkte und Schrägstriche entfernen – dann kann kein Link mehr entstehen.
    return _clip(" ".join(re.sub(r"[.:/]", " ", out).split()), max_bytes).strip()


def clean_text(value: str, max_bytes: int) -> str:
    """Macht Fremdtext für Anzeige und Weiterleitung unschädlich (idempotent)."""
    value = _CTRL_RE.sub(" ", value).replace("|", " ").replace("@", " ")
    return _no_links(" ".join(value.split()), max_bytes)


def _int_field(v: str, lo: int, hi: int) -> int | None:
    if not (1 <= len(v) <= 3 and v.isascii() and v.isdigit()):
        return None
    n = int(v)
    return n if lo <= n <= hi else None


def _coord(v: str, lim: float) -> float | None | bool:
    """None = „-“ (keine Angabe), False = ungültig."""
    if v == "-":
        return None
    if not _COORD_RE.fullmatch(v):
        return False
    f = float(v)
    return f if -lim <= f <= lim else False


def parse(text: str) -> MeshMessage | None:
    """Prüft eine empfangene Zeile. Gibt eine bereinigte Meldung zurück oder None."""
    if not isinstance(text, str) or len(text) > RX_MAX_CHARS:
        return None
    i = text.find(MAGIC + "|")
    if i < 0:
        return None
    body = re.split(r"[\r\n]", text[i:], maxsplit=1)[0]
    parts = body.split("|", 9)
    if len(parts) != 10:
        return None
    _, typ, ident, station, cnt, conf, ai, lat, lon, note = parts
    if typ not in TYPES or not _ID_RE.fullmatch(ident) or ai not in AI_CODES:
        return None
    count, pct = _int_field(cnt, 0, 999), _int_field(conf, 0, 100)
    if count is None or pct is None:
        return None
    la, lo = _coord(lat, 90.0), _coord(lon, 180.0)
    if la is False or lo is False or ((la is None) != (lo is None)):
        return None
    station = clean_text(station, STATION_MAX_BYTES * 2) or "?"
    return MeshMessage(typ=typ, ident=ident, station=_clip(station, STATION_MAX_BYTES).strip() or "?",
                       count=count, conf=pct, ai=ai, lat=la, lon=lo,  # type: ignore[arg-type]
                       note=clean_text(note, NOTE_MAX_BYTES * 2))


def encode(m: MeshMessage, max_bytes: int = LORA_MAX_BYTES) -> str:
    """Baut die Zeile. Die Notiz wird gekürzt, bis alles in max_bytes passt."""
    if m.typ not in TYPES or not _ID_RE.fullmatch(m.ident) or m.ai not in AI_CODES:
        raise ValueError("ungültige Meldung")
    station = clean_text(m.station, STATION_MAX_BYTES) or "?"
    lat = "-" if m.lat is None or m.lon is None else f"{m.lat:.2f}"
    lon = "-" if m.lat is None or m.lon is None else f"{m.lon:.2f}"
    head = (f"{MAGIC}|{m.typ}|{m.ident}|{station}|{max(0, min(999, int(m.count)))}|"
            f"{max(0, min(100, int(m.conf)))}|{m.ai}|{lat}|{lon}|")
    room = max_bytes - len(head.encode("utf-8"))
    if room < 0:
        raise ValueError("Meldung passt nicht in die erlaubte Länge")
    return head + clean_text(m.note, room)


def receipt(ident: str, station: str) -> MeshMessage:
    return MeshMessage(typ="R", ident=ident, station=station, count=0, conf=0)
