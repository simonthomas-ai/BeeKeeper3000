"""Station als Kamera: Ein Altgerät (Android-App, Handy-Webseite, Tablet, kleiner Rechner …) schickt einzelne
JPEG-Bilder per HTTP (POST /api/station/frame) an den Wächter – als wäre es eine normale Kamera.

Warum Einzelbilder statt Videostrom? Alte Geräte (Android 2.3/4.x, iPhone mit iOS 9/10) können weder
MediaRecorder noch WebRTC; ein JPEG aus der Kamera-Vorschau kann dagegen jedes Gerät erzeugen, und HTTP-POST
beherrscht jede Version. Die Erkennung läuft ohnehin auf dem Server, das Gerät muss nur Bilder liefern.

Absicherung (Station ist Netzwerk-Eingang, also Angriffsfläche):
  * nur nach Anmeldung (Cookie oder „Authorization: Bearer“), das prüft server.py;
  * Bildgröße (höchstens 1 MiB, vom WebGuard erzwungen), Bildformat, Kantenlänge und Pixelzahl werden geprüft, BEVOR
    jemand das Bild dekodiert (Schutz vor „Dekompressionsbomben“);
  * höchstens 5 Bilder je Sekunde; Überschuss wird mit 429 abgewiesen;
  * nur eine Station gleichzeitig aktiv (sonst springt die Erkennung zwischen zwei Blickwinkeln); eine zweite
    Station bekommt 409, bis die erste 20 s lang schweigt;
  * Speicher des Clip-Puffers ist nach Alter UND Bytes begrenzt.
"""
from __future__ import annotations

import collections
import io
import logging
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

from PIL import Image

from .camera import _NOWIN, find_ffmpeg
from .config import Settings

log = logging.getLogger("hornet.pushcam")

MIN_JPEG_BYTES = 300
MAX_SIDE = 4096
MAX_PIXELS = 8_000_000
MIN_INTERVAL_S = 0.2          # höchstens 5 Bilder je Sekunde
ACTIVE_S = 20.0               # so lange gilt eine Station als „da“, auch ohne neues Bild
RING_MAX_BYTES = 24 * 1024 * 1024
_STATION_RE = re.compile(r"^[A-Za-z0-9ÄÖÜäöüß._ \-]{1,40}$")


class PushError(Exception):
    """Abgewiesenes Bild: HTTP-Status, Meldung, empfohlene Wartezeit in ms."""

    def __init__(self, status: int, detail: str, retry_ms: int = 0):
        super().__init__(detail)
        self.status, self.detail, self.retry_ms = status, detail, retry_ms


def clean_station(name: str | None) -> str:
    name = (name or "").strip()
    return name if _STATION_RE.match(name) else "Station"


def check_jpeg(data: bytes) -> tuple[int, int]:
    """Prüft nur den Kopf (billig, ohne das Bild zu entpacken). Rückgabe: (Breite, Höhe)."""
    if len(data) < MIN_JPEG_BYTES:
        raise PushError(400, "Kein gültiges JPEG-Bild (zu klein)")
    if data[:3] != b"\xff\xd8\xff":
        raise PushError(415, "Kein JPEG-Bild")
    try:
        with Image.open(io.BytesIO(data)) as im:
            if im.format != "JPEG":
                raise PushError(415, "Kein JPEG-Bild")
            w, h = im.size
            mode = im.mode
    except PushError:
        raise
    except Exception:
        raise PushError(400, "JPEG-Kopf unlesbar") from None
    if w < 16 or h < 16 or w > MAX_SIDE or h > MAX_SIDE or w * h > MAX_PIXELS:
        raise PushError(413, f"Bildmaße nicht erlaubt ({w}×{h}; höchstens {MAX_SIDE} je Seite, {MAX_PIXELS // 1_000_000} Megapixel)")
    if mode not in ("RGB", "L"):
        raise PushError(415, f"Farbmodus {mode} nicht unterstützt (RGB/Graustufen erwartet)")
    return w, h


class PushCamera:
    """Gleiche äußere Schnittstelle wie camera.Camera / phonecam.PhoneCamera (start/stop/online/state/make_clip …)."""

    def __init__(self, s: Settings, on_frame: Callable[[bytes, float], None]):
        self.s = s
        self.on_frame = on_frame
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.source_label = "Station (Bilder per HTTP)"
        self.last_frame_ts = 0.0
        self.frames = 0
        self.restarts = 0                 # wie oft eine Station nach Ausfall wieder da war
        self.rejected = 0
        self._station = ""
        self._size = (0, 0)
        self._last_accept = 0.0
        self._was_down = False
        self._times: collections.deque[float] = collections.deque(maxlen=12)
        self._ring: collections.deque[tuple[float, bytes]] = collections.deque()
        self._ring_bytes = 0

    # -- Schnittstelle der anderen Kameraarten ------------------------------------------------
    def start(self) -> None:
        self._stop.clear()

    def stop(self) -> None:
        self._stop.set()

    @property
    def online(self) -> bool:
        return bool(self.last_frame_ts) and (time.time() - self.last_frame_ts) < ACTIVE_S

    @property
    def state(self) -> str:
        if not self.last_frame_ts:
            return "waiting"
        return "online" if self.online else "offline"

    @property
    def error(self) -> str:
        if self.state == "offline":
            return f"Station „{self._station}“ sendet seit {int(time.time() - self.last_frame_ts)} s nichts mehr"
        return ""

    def status_extra(self) -> dict:
        fps = 0.0
        t = list(self._times)
        if len(t) >= 2 and t[-1] > t[0]:
            fps = round((len(t) - 1) / (t[-1] - t[0]), 2)
        return {"station": self._station or None, "fps": fps, "size": list(self._size) if self._size[0] else None,
                "rejected": self.rejected,
                "last_seen_s": round(time.time() - self.last_frame_ts, 1) if self.last_frame_ts else None}

    def config(self) -> dict:
        """Empfehlung für die Station (sie darf sich daran halten oder langsamer/kleiner senden)."""
        interval = int(min(5000, max(250, 1000.0 / max(0.2, self.s.detect_fps))))
        return {"interval_ms": interval, "width": min(int(self.s.pipe_width), 960), "quality": 70,
                "max_bytes": 1 << 20, "min_interval_ms": int(MIN_INTERVAL_S * 1000)}

    # -- Bild annehmen --------------------------------------------------------------------------
    def push(self, data: bytes, station: str, now: float | None = None) -> dict:
        now = time.time() if now is None else now
        if self._stop.is_set():
            raise PushError(503, "Wächter wird beendet", 5000)
        w, h = check_jpeg(data)               # zuerst die billige Kopfprüfung: ungültige Bilder zählen nicht als Bild
        with self._lock:
            if self._station and station != self._station and (now - self.last_frame_ts) < ACTIVE_S:
                self.rejected += 1
                raise PushError(409, f"Eine andere Station („{self._station}“) ist aktiv", 5000)
            if (now - self._last_accept) < MIN_INTERVAL_S:
                self.rejected += 1
                raise PushError(429, "Zu viele Bilder – höchstens 5 je Sekunde",
                                int((MIN_INTERVAL_S - (now - self._last_accept)) * 1000) + 50)
            if self._station != station or (self.last_frame_ts and not self.online):
                if self.last_frame_ts:
                    self.restarts += 1
                log.info("Station „%s“ verbunden (%d×%d)", station, w, h)
            self._station, self._size = station, (w, h)
            self._last_accept = now
            self.last_frame_ts = now
            self.frames += 1
            self._times.append(now)
            self._ring.append((now, data))
            self._ring_bytes += len(data)
            horizon = now - (self.s.clip_pre_s + self.s.clip_post_s + 10)
            while self._ring and (self._ring[0][0] < horizon or self._ring_bytes > RING_MAX_BYTES):
                self._ring_bytes -= len(self._ring.popleft()[1])
        self.on_frame(data, now)
        return {"ok": True, "interval_ms": self.config()["interval_ms"]}

    # -- Clip aus den letzten Bildern (ohne Ton) ---------------------------------------------------
    def make_clip(self, t_alert: float, out_path: Path, pre: int | None = None, post: int | None = None) -> Path | None:
        if not self.s.clip_enabled:
            return None
        pre = self.s.clip_pre_s if pre is None else pre
        post = self.s.clip_post_s if post is None else post
        deadline = t_alert + post + 1
        while time.time() < deadline and not self._stop.is_set():
            time.sleep(0.25)
        with self._lock:
            frames = [(t, d) for t, d in self._ring if t_alert - pre <= t <= t_alert + post]
        if len(frames) < 2:
            return None
        span = frames[-1][0] - frames[0][0]
        fps = min(15.0, max(1.0, (len(frames) - 1) / span)) if span > 0 else 2.0
        out_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [find_ffmpeg(self.s.ffmpeg_bin), "-y", "-hide_banner", "-loglevel", "error", "-f", "image2pipe",
               "-framerate", f"{fps:.3f}", "-vcodec", "mjpeg", "-i", "pipe:0",
               "-vf", f"scale='min({self.s.clip_width},iw)':-2", "-c:v", "libx264", "-preset", "ultrafast",
               "-crf", "28", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out_path)]
        try:
            r = subprocess.run(cmd, input=b"".join(d for _, d in frames), capture_output=True, timeout=90, **_NOWIN)
        except (subprocess.TimeoutExpired, OSError) as e:
            log.warning("Clip aus Stationsbildern fehlgeschlagen: %s", e)
            return None
        if r.returncode != 0 or not out_path.is_file() or out_path.stat().st_size == 0:
            log.warning("Clip aus Stationsbildern fehlgeschlagen: %s", r.stderr.decode("utf-8", "replace")[-200:])
            return None
        return out_path
