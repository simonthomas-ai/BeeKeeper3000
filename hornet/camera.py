# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende
"""Kameraeingang über ffmpeg (kein OpenCV).

Ein einziger ffmpeg-Prozess liefert zwei Ausgänge – so bleibt auch eine USB-Kamera nutzbar,
die nur einmal geöffnet werden kann:

  1. MJPEG-Bilder über stdout  -> Erkennung + Live-Bild
  2. Rollierende .ts-Segmente (Bild + Ton) -> daraus werden bei Alarm Clips mit Vorlauf geschnitten
"""
from __future__ import annotations

import collections
import os
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qsl, urlsplit

from .config import Settings

_NOWIN = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)} if os.name == "nt" else {}
SEG_RE = re.compile(r"seg_(\d{8})_(\d{6})\.ts$")
_URL_RE = re.compile(r"(?P<scheme>[A-Za-z][A-Za-z0-9+.\-]*://)(?P<auth>[^/\s@?#]*@)?(?P<rest>[^\s?#]*)(?P<q>[?#]\S*)?")


def _source_secrets(source: str) -> list[str]:
    """Geheime Teile der eingerichteten Quelle: Passwort/Benutzer in der Adresse und alle Werte hinter dem „?“."""
    out: list[str] = []
    try:
        u = urlsplit(source.strip())
        out += [u.password or "", u.username or ""]
        out += [v for _, v in parse_qsl(u.query, keep_blank_values=False)]
        out.append(u.query)
    except ValueError:
        pass
    return sorted({x for x in out if len(x) >= 4}, key=len, reverse=True)


def redact(text: str, source: str = "") -> str:
    """Entfernt Zugangsdaten aus Fehlertexten, die angezeigt, protokolliert oder verschickt werden:
    Benutzer:Passwort in Adressen, alles hinter „?“ (Zugangsschlüssel), und wörtlich die geheimen Teile der Quelle."""
    def sub(m: re.Match) -> str:
        return m.group("scheme") + ("***@" if m.group("auth") else "") + m.group("rest") + ("?***" if m.group("q") else "")

    text = _URL_RE.sub(sub, text or "")
    for secret in _source_secrets(source):
        text = text.replace(secret, "***")
    return text


def find_ffmpeg(configured: str = "") -> str:
    if configured:
        return configured
    p = shutil.which("ffmpeg")
    if p:
        return p
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    raise RuntimeError(
        "ffmpeg nicht gefunden. Installieren (Windows: 'winget install Gyan.FFmpeg', Debian: 'apt install ffmpeg') "
        "oder 'pip install imageio-ffmpeg' und/oder FFMPEG_BIN in der .env setzen.")


@dataclass
class SourceSpec:
    inputs: list[str]
    vmap: str
    amap: str | None
    label: str


def resolve_source(src: str, audio_device: str = "") -> SourceSpec:
    low = src.lower()
    if low == "selftest":  # interner Generator des Selbsttests (ffmpeg-Testbild + Ton), nicht für den Betrieb gedacht
        return SourceSpec(
            ["-re", "-f", "lavfi", "-i", "testsrc2=size=960x540:rate=15",
             "-re", "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=44100,volume=0.15"],
            "0:v:0", "1:a:0", "Selbsttest-Generator")
    if low.startswith(("rtsp://", "rtsps://")):
        return SourceSpec(["-rtsp_transport", "tcp", "-i", src], "0:v:0", "0:a:0?", "RTSP-Kamera")
    if low.startswith(("http://", "https://", "rtmp://")):
        return SourceSpec(["-i", src], "0:v:0", "0:a:0?", "Netzwerk-Stream")
    if low.startswith("dshow:"):
        name = src[6:]
        spec = f"video={name}" + (f":audio={audio_device}" if audio_device else "")
        return SourceSpec(["-f", "dshow", "-rtbufsize", "100M", "-i", spec], "0:v:0",
                          "0:a:0?" if audio_device else None, "Windows-Kamera")
    if low.startswith("avfoundation:"):
        return SourceSpec(["-f", "avfoundation", "-framerate", "15", "-i", src[13:]], "0:v:0", "0:a:0?", "macOS-Kamera")
    if low.startswith("v4l2:") or low.startswith("/dev/video"):
        dev = src[5:] if low.startswith("v4l2:") else src
        inputs = ["-f", "v4l2", "-i", dev]
        amap = None
        if audio_device:
            inputs += ["-f", "alsa", "-i", audio_device]
            amap = "1:a:0"
        return SourceSpec(inputs, "0:v:0", amap, "USB-Kamera")
    path = src[5:] if low.startswith("file:") else src
    if Path(path).is_file():
        return SourceSpec(["-re", "-stream_loop", "-1", "-i", path], "0:v:0", "0:a:0?", "Videodatei")
    raise ValueError(
        f"CAMERA_SOURCE '{src}' nicht erkannt. Erlaubt: phone | push | rtsp://… | dshow:Kameraname | v4l2:/dev/video0 | Dateipfad")


ALLOWED_PREFIXES = ("rtsp://", "rtsps://", "http://", "https://", "rtmp://", "dshow:", "avfoundation:", "v4l2:",
                    "/dev/video", "file:")


def validate_source(src: str) -> str:
    """Prüft die Kamera-Quelle aus der Einrichtung (keine Optionen einschleusen, nur bekannte Arten)."""
    src = (src or "").strip()
    if not src:
        raise ValueError("Keine Kamera-Quelle angegeben")
    if src.startswith("-") or "\n" in src or "\r" in src:
        raise ValueError("Ungültige Kamera-Quelle")
    low = src.lower()
    if low in ("selftest", "phone", "push") or low.startswith(ALLOWED_PREFIXES) or Path(src).is_file():
        return src
    raise ValueError("Unbekannte Kamera-Quelle. Erlaubt: phone, push, rtsp://…, dshow:Kameraname, v4l2:/dev/video0, "
                     "avfoundation:0:0 oder der Pfad einer Videodatei")


def build_cmd(s: Settings, seg_dir: Path | None) -> tuple[list[str], SourceSpec]:
    spec = resolve_source(s.camera_source, s.camera_audio_device)
    cmd = [find_ffmpeg(s.ffmpeg_bin), "-hide_banner", "-loglevel", "warning", "-nostdin", *spec.inputs]
    # Ausgang 1: Bilder für Erkennung/Live
    cmd += ["-map", spec.vmap, "-an", "-vf", f"fps={s.detect_fps:g},scale={s.pipe_width}:-2",
            "-q:v", "5", "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1"]
    # Ausgang 2: Segmente mit Ton für Clips
    if s.clip_enabled and seg_dir is not None:
        seg_dir.mkdir(parents=True, exist_ok=True)
        cmd += ["-map", spec.vmap]
        if spec.amap:
            cmd += ["-map", spec.amap]
        if s.clip_video == "copy":
            cmd += ["-c:v", "copy"]
        else:
            cmd += ["-vf", f"scale={s.clip_width}:-2,fps=15", "-c:v", "libx264", "-preset", "ultrafast",
                    "-tune", "zerolatency", "-crf", "28", "-pix_fmt", "yuv420p", "-g", str(15 * s.segment_s),
                    "-force_key_frames", f"expr:gte(t,n_forced*{s.segment_s})"]
        if spec.amap:
            cmd += ["-c:a", "aac", "-b:a", "64k", "-ac", "1", "-ar", "44100"]
        cmd += ["-f", "segment", "-segment_time", str(s.segment_s), "-segment_format", "mpegts",
                "-reset_timestamps", "1", "-strftime", "1", str(seg_dir / "seg_%Y%m%d_%H%M%S.ts")]
    return cmd, spec


class Camera:
    def __init__(self, s: Settings, on_frame: Callable[[bytes, float], None]):
        self.s = s
        self.on_frame = on_frame
        self._stop = threading.Event()
        self._proc: subprocess.Popen | None = None
        self._threads: list[threading.Thread] = []
        self.last_frame_ts = 0.0
        self.frames = 0
        self.restarts = 0
        self.state = "starting"
        self.error = ""
        self.source_label = ""
        self._stderr: collections.deque[str] = collections.deque(maxlen=12)

    # -- Steuerung --------------------------------------------------------------------
    def start(self) -> None:
        for target in (self._run, self._cleanup_loop):
            t = threading.Thread(target=target, daemon=True, name=f"camera-{target.__name__}")
            t.start()
            self._threads.append(t)

    def stop(self) -> None:
        self._stop.set()
        p = self._proc
        if p and p.poll() is None:
            try:
                p.terminate()
                p.wait(timeout=3)
            except Exception:
                p.kill()

    @property
    def online(self) -> bool:
        return self.state == "online" and (time.time() - self.last_frame_ts) < 20

    # -- Hauptschleife ----------------------------------------------------------------
    def _run(self) -> None:
        if not self.s.camera_source.strip():
            self.state, self.error = "unconfigured", "Keine Kamera eingerichtet"
            return
        backoff = 2.0
        while not self._stop.is_set():
            try:
                cmd, spec = build_cmd(self.s, self.s.segments_dir)
                self.source_label = spec.label
            except Exception as e:  # ungültige Quelle / ffmpeg fehlt
                self.state, self.error = "error", redact(str(e), self.s.camera_source)
                self._stop.wait(15)
                continue
            got_frames_before = self.frames
            self.state, self.error = "connecting", ""
            self._stderr.clear()
            try:
                self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0, **_NOWIN)
            except Exception as e:
                self.state, self.error = "error", redact(f"ffmpeg konnte nicht gestartet werden: {e}", self.s.camera_source)
                self._stop.wait(15)
                continue
            proc = self._proc
            started = time.time()
            threading.Thread(target=self._drain_stderr, args=(proc,), daemon=True).start()
            threading.Thread(target=self._watchdog, args=(proc, started), daemon=True).start()
            self._read_frames(proc)
            if proc.poll() is None:
                proc.kill()
            if self._stop.is_set():
                break
            self.state = "offline"
            self.error = " | ".join(list(self._stderr)[-3:]) or "Videoquelle beendet"
            self.restarts += 1
            backoff = 2.0 if self.frames > got_frames_before else min(30.0, backoff * 2)
            self._stop.wait(backoff)

    def _read_frames(self, proc: subprocess.Popen) -> None:
        buf = bytearray()
        rd = proc.stdout
        while not self._stop.is_set():
            chunk = rd.read(65536)
            if not chunk:
                return
            buf += chunk
            while True:
                s = buf.find(b"\xff\xd8")
                if s < 0:
                    buf.clear()
                    break
                e = buf.find(b"\xff\xd9", s + 2)
                if e < 0:
                    if s > 0:
                        del buf[:s]
                    break
                frame = bytes(buf[s:e + 2])
                del buf[:e + 2]
                self.last_frame_ts = time.time()
                self.frames += 1
                self.state = "online"
                try:
                    self.on_frame(frame, self.last_frame_ts)
                except Exception:
                    pass

    def _drain_stderr(self, proc: subprocess.Popen) -> None:
        try:
            for line in iter(proc.stderr.readline, b""):
                txt = line.decode("utf-8", "replace").strip()
                if txt:
                    self._stderr.append(redact(txt, self.s.camera_source)[:240])
        except Exception:
            pass

    def _watchdog(self, proc: subprocess.Popen, started: float) -> None:
        while proc.poll() is None and not self._stop.is_set():
            time.sleep(3)
            ref = max(self.last_frame_ts, started)
            if time.time() - ref > 30:
                self._stderr.append("Watchdog: seit 30 s kein Bild – Verbindung wird neu aufgebaut")
                proc.kill()
                return

    # -- Segmente / Clips -------------------------------------------------------------
    def segments(self) -> list[tuple[float, Path]]:
        out: list[tuple[float, Path]] = []
        d = self.s.segments_dir
        if not d.is_dir():
            return out
        for p in d.iterdir():
            m = SEG_RE.search(p.name)
            if m:
                try:
                    st = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").timestamp()
                except ValueError:
                    continue
                out.append((st, p))
        return sorted(out)

    def _cleanup_loop(self) -> None:
        keep = self.s.clip_pre_s + self.s.clip_post_s + 4 * self.s.segment_s + 90
        while not self._stop.wait(20):
            cutoff = time.time() - keep
            for st, p in self.segments():
                if st < cutoff:
                    try:
                        p.unlink()
                    except OSError:
                        pass

    def make_clip(self, t_alert: float, out_path: Path, pre: int | None = None, post: int | None = None) -> Path | None:
        """Schneidet einen Clip [t_alert-pre, t_alert+post] aus den Segmenten (Bild + Ton)."""
        if not self.s.clip_enabled:
            return None
        pre = self.s.clip_pre_s if pre is None else pre
        post = self.s.clip_post_s if post is None else post
        seg_s = self.s.segment_s
        deadline = t_alert + post + seg_s + 2
        while time.time() < deadline and not self._stop.is_set():
            time.sleep(0.25)
        t0, t1 = t_alert - pre, t_alert + post
        chosen = [p for st, p in self.segments() if st + seg_s + 0.3 > t0 and st < t1]
        chosen = [p for p in chosen if p.stat().st_size > 0]
        if not chosen:
            return None
        out_path.parent.mkdir(parents=True, exist_ok=True)
        lst = out_path.with_suffix(".txt")
        lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in chosen), encoding="utf-8")
        cmd = [find_ffmpeg(self.s.ffmpeg_bin), "-y", "-hide_banner", "-loglevel", "error",
               "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", "-movflags", "+faststart", str(out_path)]
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=90, **_NOWIN)
        finally:
            lst.unlink(missing_ok=True)
        if r.returncode != 0 or not out_path.is_file() or out_path.stat().st_size == 0:
            self._stderr.append("Clip-Erzeugung fehlgeschlagen: "
                                + redact(r.stderr.decode("utf-8", "replace"), self.s.camera_source)[-200:])
            return None
        return out_path
