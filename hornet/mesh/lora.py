"""LoRa-Weg: Funkgerät mit MeshCore-Firmware (Companion-Modus) über USB-Seriell.

Der Client spricht das Companion-Protokoll von MeshCore selbst (nur pyserial nötig):

  App → Gerät: 0x3C, Länge (2 Byte, little endian), Nutzdaten      Gerät → App: 0x3E, Länge, Nutzdaten

Gesendet wird als Kanal-Textnachricht (CMD 3) auf einem eigenen, privaten Kanal. Empfang: das Gerät meldet
„Nachrichten warten“ (Push 0x83), der Client holt sie mit CMD_SYNC_NEXT_MESSAGE (CMD 10) ab.

Sendezeit: Das Funkgerät ist im EU-868-Band an Sendezeit-Anteile gebunden (je nach Teilband 1 % oder 10 %).
`DutyCycle` rechnet die Sendedauer jeder Meldung nach der LoRa-Formel aus den echten Funkparametern des Geräts
und hält einen gleitenden Stundenanteil ein.
"""
from __future__ import annotations

import logging
import math
import queue
import re
import struct
import threading
import time
from collections import deque
from dataclasses import dataclass, field

from .transport import ReceiveFn, Transport, TransportError

log = logging.getLogger("hornet.mesh.lora")

FRAME_TO_DEVICE = 0x3C
FRAME_FROM_DEVICE = 0x3E
MAX_FRAME = 300

# Befehle
CMD_APP_START, CMD_SEND_CHANNEL_TXT, CMD_GET_TIME, CMD_SET_TIME, CMD_SYNC_NEXT = 1, 3, 5, 6, 10
CMD_DEVICE_QUERY, CMD_GET_CHANNEL, CMD_SET_CHANNEL = 22, 31, 32
# Antworten
R_OK, R_ERROR, R_SELF_INFO, R_MSG_SENT, R_CONTACT_MSG, R_CHANNEL_MSG = 0, 1, 5, 6, 7, 8
R_NO_MORE, R_DEVICE_INFO, R_CONTACT_MSG_V3, R_CHANNEL_MSG_V3, R_CHANNEL_INFO = 10, 13, 16, 17, 18
PUSH_MESSAGES_WAITING = 0x83

APP_VERSION = 3
APP_NAME = b"hornet3000"
POLL_S = 5.0          # Abholen auch ohne Push (falls ein Push verloren ging)
DRAIN_MAX = 40        # Nachrichten pro Abholrunde; danach sofort weiter, ohne auf den Takt zu warten


# ── Sendezeit ──────────────────────────────────────────────────────────────────────────────────
def airtime_s(payload_bytes: int, sf: int, bw_hz: float, cr: int = 5, preamble: int = 16) -> float:
    """Sendedauer eines LoRa-Pakets (Semtech-Formel, expliziter Header, CRC an)."""
    if not (5 <= sf <= 12) or bw_hz <= 0:
        raise ValueError("ungültige Funkparameter")
    cr_i = min(8, max(5, cr)) - 4
    t_sym = (2 ** sf) / bw_hz
    de = 1 if t_sym > 0.016 else 0
    n_payload = 8 + max(math.ceil((8 * payload_bytes - 4 * sf + 28 + 16) / (4 * (sf - 2 * de))) * (cr_i + 4), 0)
    return (preamble + 4.25) * t_sym + n_payload * t_sym


def onair_bytes(text_bytes: int, name_bytes: int = 12, max_hops: int = 8) -> int:
    """Obergrenze der Paketlänge einer MeshCore-Kanalnachricht (Kopf, Pfad, Kanal-Hash, MAC, verschlüsselter Block)."""
    plain = 5 + name_bytes + 2 + text_bytes          # Zeitstempel(4)+Flags(1)+„Name: “+Text
    return 2 + max_hops + 3 + 16 * math.ceil(plain / 16)


class DutyCycle:
    """Gleitendes Stundenbudget der Sendezeit."""

    def __init__(self, share: float = 0.01, window_s: float = 3600.0):
        self.share = min(0.10, max(0.001, share))
        self.window_s = window_s
        self._log: deque[tuple[float, float]] = deque()

    def _trim(self, now: float) -> None:
        while self._log and now - self._log[0][0] > self.window_s:
            self._log.popleft()

    def used(self, now: float) -> float:
        self._trim(now)
        return sum(a for _, a in self._log)

    def budget(self) -> float:
        return self.share * self.window_s

    def allows(self, air: float, now: float) -> bool:
        return self.used(now) + air <= self.budget()

    def charge(self, air: float, now: float) -> None:
        self._trim(now)
        self._log.append((now, air))

    def wait_s(self, air: float, now: float) -> float:
        """Wie lange, bis `air` Sekunden wieder ins Budget passen (0 = jetzt)."""
        self._trim(now)
        used, need = self.used(now), self.used(now) + air - self.budget()
        if need <= 0:
            return 0.0
        freed = 0.0
        for t, a in self._log:
            freed += a
            if freed >= need:
                return max(0.0, t + self.window_s - now)
        return self.window_s


# ── Rahmen und Pakete ───────────────────────────────────────────────────────────────────────────
class FrameParser:
    """Setzt den Bytestrom vom Gerät zu Rahmen zusammen. Findet nach Müll/Fehlern von selbst wieder den Anfang."""

    MAX_BUF = 4096

    def __init__(self) -> None:
        self.buf = bytearray()
        self.resyncs = 0

    def feed(self, data: bytes) -> list[bytes]:
        self.buf += data
        out: list[bytes] = []
        while True:
            i = self.buf.find(bytes([FRAME_FROM_DEVICE]))
            if i < 0:
                self.buf.clear()
                break
            if i:
                del self.buf[:i]
                self.resyncs += 1
            if len(self.buf) < 3:
                break
            n = self.buf[1] | (self.buf[2] << 8)
            if n == 0 or n > MAX_FRAME:
                del self.buf[0]        # kein gültiger Anfang – ab dem nächsten Byte neu suchen
                self.resyncs += 1
                continue
            if len(self.buf) < 3 + n:
                break
            out.append(bytes(self.buf[3:3 + n]))
            del self.buf[:3 + n]
        if len(self.buf) > self.MAX_BUF:
            self.buf.clear()
        return out


def build_frame(payload: bytes) -> bytes:
    if not payload or len(payload) > MAX_FRAME:
        raise ValueError("ungültige Rahmenlänge")
    return bytes([FRAME_TO_DEVICE]) + len(payload).to_bytes(2, "little") + payload


@dataclass
class SelfInfo:
    name: str = ""
    freq_mhz: float = 0.0
    bw_khz: float = 0.0
    sf: int = 0
    cr: int = 5
    tx_power: int = 0
    public_key: str = ""


def parse_self_info(p: bytes) -> SelfInfo:
    """Antwort auf CMD_APP_START (Code 5)."""
    if len(p) < 58 or p[0] != R_SELF_INFO:
        raise ValueError("SELF_INFO zu kurz")
    freq, bw = struct.unpack_from("<II", p, 48)
    return SelfInfo(tx_power=p[2], public_key=p[4:36].hex(), freq_mhz=freq / 1000, bw_khz=bw / 1000, sf=p[56],
                    cr=p[57], name=p[58:].decode("utf-8", "ignore").strip("\0"))


@dataclass
class ChannelMsg:
    channel: int
    text: str
    snr: float | None = None
    hops: int | None = None
    sender_ts: int = 0


def parse_channel_msg(p: bytes) -> ChannelMsg:
    """Code 8 (alt) oder 17 (V3, mit SNR) – Kanalnachricht aus dem Speicher des Geräts."""
    if not p:
        raise ValueError("leer")
    if p[0] == R_CHANNEL_MSG_V3:
        if len(p) < 12:
            raise ValueError("zu kurz")
        snr = struct.unpack_from("<b", p, 1)[0] / 4
        idx, plen, _txt_type = p[4], p[5], p[6]
        ts = struct.unpack_from("<I", p, 7)[0]
        text = p[11:]
    elif p[0] == R_CHANNEL_MSG:
        if len(p) < 8:
            raise ValueError("zu kurz")
        snr = None
        idx, plen, _txt_type = p[1], p[2], p[3]
        ts = struct.unpack_from("<I", p, 4)[0]
        text = p[8:]
    else:
        raise ValueError("keine Kanalnachricht")
    hops = None if plen == 255 else plen & 0x3F
    return ChannelMsg(channel=idx, text=text.rstrip(b"\0").decode("utf-8", "ignore"), snr=snr, hops=hops,
                      sender_ts=ts)


def parse_channel_info(p: bytes) -> tuple[int, str, bytes]:
    if len(p) < 50 or p[0] != R_CHANNEL_INFO:
        raise ValueError("CHANNEL_INFO zu kurz")
    name = p[2:34].split(b"\0", 1)[0].decode("utf-8", "ignore")
    return p[1], name, bytes(p[34:50])


# ── Verbindung ────────────────────────────────────────────────────────────────────────────────────
class LinkError(TransportError):
    pass


def open_serial(port: str, baud: int):
    import serial  # pyserial

    ser = serial.serial_for_url(port, do_not_open=True)
    ser.baudrate, ser.timeout, ser.write_timeout = baud, 0.2, 2.0
    ser.dtr, ser.rts = True, False   # RTS an würde manche ESP32-Platinen zurücksetzen
    ser.open()
    return ser


class MeshLink:
    """Eine Verbindung zum Funkgerät. Ein Leser-Thread sortiert Rahmen in Antworten und Push-Meldungen."""

    def __init__(self, port: str, baud: int = 115200, opener=open_serial, timeout: float = 4.0):
        self.port, self.baud, self.timeout = port, baud, timeout
        self._opener = opener
        self._ser = None
        self._parser = FrameParser()
        self._resp: queue.Queue[bytes] = queue.Queue(maxsize=64)
        self._cmd_lock = threading.Lock()
        self._reader: threading.Thread | None = None
        self._closing = threading.Event()
        self.waiting = threading.Event()   # Gerät hat Nachrichten bereit
        self.dead = threading.Event()      # Verbindung ist abgerissen
        self.info = SelfInfo()
        self.bad_frames = 0

    # -- Aufbau/Abbau --------------------------------------------------------------------
    def open(self) -> None:
        try:
            self._ser = self._opener(self.port, self.baud)
        except Exception as e:
            raise LinkError(f"Funkgerät nicht erreichbar ({self.port}): {e}") from e
        self._closing.clear()
        self.dead.clear()
        self._reader = threading.Thread(target=self._read_loop, daemon=True, name="mesh-link-rx")
        self._reader.start()

    def close(self) -> None:
        self._closing.set()
        ser, self._ser = self._ser, None
        try:
            if ser is not None:
                ser.close()
        except Exception:
            pass
        if self._reader is not None and self._reader is not threading.current_thread():
            self._reader.join(timeout=2)
        self.dead.set()

    def _read_loop(self) -> None:
        ser = self._ser
        while not self._closing.is_set() and ser is not None:
            try:
                data = ser.read(max(1, getattr(ser, "in_waiting", 0) or 1))
            except Exception as e:
                if not self._closing.is_set():
                    log.warning("Funkgerät: Lesefehler (%s) – Verbindung wird neu aufgebaut", e)
                break
            if not data:
                continue
            for frame in self._parser.feed(data):
                self._on_frame(frame)
        self.dead.set()

    def _on_frame(self, f: bytes) -> None:
        if not f:
            return
        if f[0] >= 0x80:
            if f[0] == PUSH_MESSAGES_WAITING:
                self.waiting.set()
            return                          # andere Push-Meldungen (Werbung, Pfade …) braucht dieser Dienst nicht
        try:
            self._resp.put_nowait(f)
        except queue.Full:
            try:
                self._resp.get_nowait()     # älteste verwerfen
            except queue.Empty:
                pass
            self._resp.put_nowait(f)

    # -- Befehle ---------------------------------------------------------------------------
    def request(self, payload: bytes, expect: tuple[int, ...], timeout: float | None = None) -> bytes:
        """Sendet einen Befehl und wartet auf die erste passende Antwort (oder ERROR)."""
        if self._ser is None or self.dead.is_set():
            raise LinkError("Funkgerät nicht verbunden")
        deadline = time.monotonic() + (timeout or self.timeout)
        with self._cmd_lock:
            while True:                      # veraltete Antworten früherer Befehle wegräumen
                try:
                    self._resp.get_nowait()
                except queue.Empty:
                    break
            try:
                self._ser.write(build_frame(payload))
                self._ser.flush()
            except Exception as e:
                self.dead.set()
                raise LinkError(f"Schreiben zum Funkgerät fehlgeschlagen: {e}") from e
            while True:
                left = deadline - time.monotonic()
                if left <= 0:
                    raise LinkError("Funkgerät antwortet nicht")
                try:
                    r = self._resp.get(timeout=left)
                except queue.Empty:
                    raise LinkError("Funkgerät antwortet nicht") from None
                if r[0] == R_ERROR:
                    raise LinkError(f"Funkgerät meldet Fehler{' ' + str(r[1]) if len(r) > 1 else ''}")
                if r[0] in expect:
                    return r

    def app_start(self) -> SelfInfo:
        r = self.request(bytes([CMD_APP_START, APP_VERSION]) + b" " * 6 + APP_NAME, (R_SELF_INFO,))
        self.info = parse_self_info(r)
        return self.info

    def device_query(self) -> bytes:
        return self.request(bytes([CMD_DEVICE_QUERY, APP_VERSION]), (R_DEVICE_INFO,))

    def get_channel(self, idx: int) -> tuple[int, str, bytes]:
        return parse_channel_info(self.request(bytes([CMD_GET_CHANNEL, idx]), (R_CHANNEL_INFO,)))

    def set_channel(self, idx: int, name: str, secret: bytes) -> None:
        if len(secret) != 16:
            raise ValueError("Kanalschlüssel muss 16 Byte lang sein")
        nb = name.encode("utf-8")[:32].ljust(32, b"\0")
        self.request(bytes([CMD_SET_CHANNEL, idx]) + nb + secret, (R_OK,))

    def set_time(self, ts: int) -> None:
        self.request(bytes([CMD_SET_TIME]) + int(ts).to_bytes(4, "little"), (R_OK,))

    def send_channel_text(self, idx: int, text: str, ts: int | None = None) -> None:
        raw = text.encode("utf-8")
        if not raw or len(raw) > 150:
            raise ValueError("Text zu lang für eine Funknachricht")
        t = int(ts if ts is not None else time.time()).to_bytes(4, "little")
        self.request(bytes([CMD_SEND_CHANNEL_TXT, 0, idx]) + t + raw, (R_MSG_SENT, R_OK))

    def next_message(self) -> ChannelMsg | None:
        """Holt die nächste wartende Nachricht; None = keine mehr. Kontaktnachrichten (privat) werden verworfen."""
        r = self.request(bytes([CMD_SYNC_NEXT]), (R_NO_MORE, R_CHANNEL_MSG, R_CHANNEL_MSG_V3, R_CONTACT_MSG,
                                                    R_CONTACT_MSG_V3))
        if r[0] == R_NO_MORE:
            self.waiting.clear()
            return None
        if r[0] in (R_CONTACT_MSG, R_CONTACT_MSG_V3):
            return ChannelMsg(channel=-1, text="")
        try:
            return parse_channel_msg(r)
        except ValueError:
            self.bad_frames += 1
            return ChannelMsg(channel=-1, text="")


# ── Port finden/prüfen ─────────────────────────────────────────────────────────────────────────────
_PORT_OK = re.compile(r"^(/dev/(tty(USB|ACM|AMA|S)\d+|cu\.[\w.\-]+|tty\.[\w.\-]+|serial/by-(id|path)/[\w.:\-]+|pts/\d+)|COM\d{1,3})$")


def check_port(port: str) -> str:
    """Prüft die Angabe aus der Einrichtung: nur echte serielle Geräte, nichts anderes (kein Dateipfad, keine URL)."""
    port = (port or "").strip()
    if port.lower() == "auto":
        return "auto"
    if not _PORT_OK.match(port):
        raise ValueError("Funkgerät: erlaubt sind /dev/ttyUSB0, /dev/ttyACM0, COM3, /dev/cu.usbserial-… oder „auto“")
    return port


_KNOWN_USB = {0x303A, 0x10C4, 0x1A86, 0x239A, 0x2886, 0x0403, 0x2E8A}  # Espressif, CP210x, CH340, Adafruit/RAK, Seeed, FTDI, Pico


def find_port() -> str:
    from serial.tools import list_ports

    cands = [p.device for p in list_ports.comports() if p.vid in _KNOWN_USB]
    if len(cands) == 1:
        return cands[0]
    if not cands:
        raise LinkError("Kein Funkgerät gefunden – USB-Kabel prüfen oder den Anschluss (z. B. /dev/ttyUSB0) eintragen")
    raise LinkError("Mehrere mögliche Funkgeräte: " + ", ".join(sorted(cands)) + " – bitte den Anschluss eintragen")


# ── Übertragungsweg ──────────────────────────────────────────────────────────────────────────────────
class LoraTransport(Transport):
    name = "lora"
    label = "LoRa (MeshCore)"
    max_bytes = 118

    def __init__(self, port: str, baud: int, channel_idx: int, channel_name: str = "hornet3000",
                 channel_key: str = "", duty: float = 0.01, opener=open_serial, poll_s: float = POLL_S):
        super().__init__()
        if channel_idx < 1 or channel_idx > 7:
            raise ValueError("Funkkanal: erlaubt sind 1 bis 7 (Kanal 0 ist der öffentliche MeshCore-Kanal)")
        self.port_cfg = check_port(port)
        self.baud, self.idx, self.chan_name = baud, channel_idx, channel_name or "hornet3000"
        self.secret = bytes.fromhex(channel_key) if channel_key else b""
        if channel_key and len(self.secret) != 16:
            raise ValueError("Funkkanal-Schlüssel: 32 Hexzeichen (16 Byte) erwartet")
        self.duty = DutyCycle(duty)
        self.poll_s = poll_s
        self._opener = opener
        self._link: MeshLink | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self.connected = False
        self.error = ""
        self.rx = self.tx = self.reconnects = 0
        self.last_rx = self.last_tx = 0.0
        self.snr: float | None = None

    # -- Lebenszyklus --------------------------------------------------------------------
    def start(self, on_receive: ReceiveFn) -> None:
        super().start(on_receive)
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="mesh-lora")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        link = self._link
        if link is not None:
            link.close()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _connect(self) -> MeshLink:
        port = find_port() if self.port_cfg == "auto" else self.port_cfg
        link = MeshLink(port, self.baud, self._opener)
        link.open()
        try:
            info = link.app_start()
            try:
                link.device_query()
            except LinkError:
                pass                               # ältere Firmware: nicht nötig
            if self.secret:
                self._ensure_channel(link)
            else:
                link.get_channel(self.idx)         # Kanal muss am Gerät vorhanden sein
            try:
                link.set_time(int(time.time()))   # Zeitstempel der Meldungen stimmen nur mit richtiger Uhr
            except LinkError:
                pass
        except Exception:
            link.close()
            raise
        log.info("Funkgerät verbunden: %s (%s, %.3f MHz, SF%d, BW %.1f kHz)", info.name, port, info.freq_mhz,
                 info.sf, info.bw_khz)
        return link

    def _ensure_channel(self, link: MeshLink) -> None:
        try:
            _, name, secret = link.get_channel(self.idx)
        except LinkError:
            name, secret = "", b""
        if name != self.chan_name or secret != self.secret:
            link.set_channel(self.idx, self.chan_name, self.secret)
            log.info("Funkkanal %d am Gerät eingerichtet (%s)", self.idx, self.chan_name)

    def _run(self) -> None:
        backoff = 2.0
        while not self._stop.is_set():
            try:
                link = self._connect()
            except Exception as e:
                self.connected, self.error = False, str(e)
                self._stop.wait(backoff)
                backoff = min(60.0, backoff * 2)
                continue
            backoff = 2.0
            with self._lock:
                self._link = link
            self.connected, self.error = True, ""
            try:
                self._poll(link)
            except Exception as e:
                self.error = str(e)
                log.warning("Funkgerät: %s", e)
            finally:
                self.connected = False
                with self._lock:
                    self._link = None
                link.close()
            if not self._stop.is_set():
                self.reconnects += 1
                self._stop.wait(2.0)

    def _poll(self, link: MeshLink) -> None:
        link.waiting.set()                         # beim Start einmal alles abholen, was schon wartet
        while not self._stop.is_set() and not link.dead.is_set():
            if not link.waiting.wait(self.poll_s):
                link.waiting.set()                 # Takt: sicherheitshalber auch ohne Push nachsehen
            if self._stop.is_set() or link.dead.is_set():
                break
            n = 0
            while n < DRAIN_MAX:
                msg = link.next_message()
                if msg is None:
                    break
                n += 1
                if msg.channel == self.idx and msg.text and self.on_receive:
                    self.rx += 1
                    self.last_rx = time.time()
                    self.snr = msg.snr
                    try:
                        self.on_receive(msg.text, "lora", self.last_rx)
                    except Exception:
                        log.exception("Fehler bei der Verarbeitung einer Funkmeldung")
            else:
                link.waiting.set()                 # mehr als DRAIN_MAX warteten: ohne Wartezeit weitermachen

    # -- Senden ----------------------------------------------------------------------------
    def _air(self, text: str) -> float:
        info = self._link.info if self._link else SelfInfo()
        if not info.sf or not info.bw_khz:
            return 2.0                              # Funkparameter unbekannt: vorsichtig hoch ansetzen
        return airtime_s(onair_bytes(len(text.encode("utf-8")), len(info.name.encode("utf-8"))), info.sf,
                         info.bw_khz * 1000, info.cr)

    def can_send_now(self, text: str, now: float) -> bool:
        return self.duty.allows(self._air(text), now)

    def wait_s(self, text: str, now: float) -> float:
        return self.duty.wait_s(self._air(text), now)

    def send(self, text: str) -> None:
        with self._lock:
            link = self._link
        if link is None or not self.connected:
            raise TransportError("Funkgerät nicht verbunden")
        now = time.time()
        air = self._air(text)
        if not self.duty.allows(air, now):
            raise TransportError("Sendezeit-Budget aufgebraucht")
        try:
            link.send_channel_text(self.idx, text)
        except ValueError as e:
            raise TransportError(str(e)) from e
        self.duty.charge(air, now)
        self.tx += 1
        self.last_tx = now

    def status(self) -> dict:
        info = self._link.info if self._link else SelfInfo()
        now = time.time()
        return {"name": self.name, "label": self.label, "online": self.connected,
                "detail": self.error or (f"{info.name} · {info.freq_mhz:.3f} MHz · SF{info.sf}" if self.connected else ""),
                "port": self.port_cfg, "channel": self.idx, "rx": self.rx, "tx": self.tx,
                "last_rx": self.last_rx or None, "last_tx": self.last_tx or None, "snr": self.snr,
                "reconnects": self.reconnects, "duty_share": self.duty.share,
                "duty_used_s": round(self.duty.used(now), 2), "duty_budget_s": round(self.duty.budget(), 1)}
