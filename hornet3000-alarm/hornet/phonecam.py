# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende
"""Handy als Kamera: Empfängt den fortlaufenden MediaRecorder-Bytestrom eines Telefon-Browsers
(WebSocket, siehe server.py) und reicht ihn an ffmpeg weiter – als wäre es eine normale Videoquelle.

Warum keine App? Eine echte, store-signierte iOS-App lässt sich ohne Mac/Xcode/Entwicklerkonto nicht bauen,
und für Android fehlt in dieser Umgebung der Zugriff auf die Google-Maven-Infrastruktur. Browser-Aufnahme
(getUserMedia + MediaRecorder) ist dagegen auf jedem halbwegs aktuellen iPhone (Safari ≥ 14.3) und Android-Handy
(Chrome) bereits vorhanden, erfordert keine Installation und läuft über denselben, bereits getesteten Server.

Funktionsweise: MediaRecorder mit "timeslice" liefert KEINE unabhängigen Dateihäppchen, sondern Bruchstücke
eines fortlaufenden Containers (erstes Stück = Kopf + erstes Fragment, alle weiteren nur Fragmente). Diese
Häppchen werden deshalb nicht einzeln dekodiert, sondern byteweise an ein einziges, langlebiges ffmpeg
weitergereicht (stdin), das wie bei einer RTSP-Kamera MJPEG-Bilder (stdout) und .ts-Segmente mit Ton erzeugt.
Technisch dasselbe Prinzip, mit dem Streaming-Dienste Browser-Aufnahmen entgegennehmen.
"""
from __future__ import annotations

import collections
import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

from .camera import SEG_RE, _NOWIN, find_ffmpeg
from .config import Settings

log = logging.getLogger("hornet.phonecam")

# Von MediaRecorder tatsächlich erzeugte Containerformate (siehe web/assets/phone.js: MIME_CANDIDATES).
# "webm" liefert Android Chrome (VP8/VP9 + Opus), "mp4" liefert iOS Safari (H.264 + AAC, fragmentiert).
FORMAT_BY_MIME = {"video/webm": "webm", "video/mp4": "mp4"}


class PhoneCamera:
    """Hat dieselbe äußere Schnittstelle wie camera.Camera (start/stop/online/segments/make_clip),
    damit Engine und der Rest des Programms nicht unterscheiden müssen, woher das Bild kommt."""

    def __init__(self, s: Settings, on_frame: Callable[[bytes, float], None]):
        self.s = s
        self.on_frame = on_frame
        self._stop = threading.Event()
        self._proc: subprocess.Popen | None = None
        self._proc_lock = threading.Lock()
        self._session = 0  # wächst bei jeder neuen Handy-Verbindung; verwirft Schreibversuche alter Sitzungen
        self.last_frame_ts = 0.0
        self.frames = 0
        self.restarts = 0
        self.state = "waiting"  # waiting | connecting | online | offline | error
        self.error = ""
        self.source_label = "Handy-Kamera"
        self.device_label = ""
        self.last_seen_phone = 0.0
        self._stderr: collections.deque[str] = collections.deque(maxlen=12)
        self._cleanup_thread: threading.Thread | None = None

    # -- Steuerung --------------------------------------------------------------------------
    def start(self) -> None:
        if not self.s.camera_source.strip():
            self.state, self.error = "unconfigured", "Keine Kamera eingerichtet"
            return
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True, name="phonecam-cleanup")
        self._cleanup_thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._end_session()

    @property
    def online(self) -> bool:
        return self.state == "online" and (time.time() - self.last_frame_ts) < 20

    def status_extra(self) -> dict:
        """Zusatzinfo fürs Status-API: wie lange das Handy schon/zuletzt verbunden war."""
        return {"device": self.device_label or None,
                "last_seen_s": round(time.time() - self.last_seen_phone, 1) if self.last_seen_phone else None}

    # -- Eine Handy-Sitzung ------------------------------------------------------------------
    def attach(self, mime: str, device_label: str) -> int:
        """Neue Handy-Verbindung: beendet eine evtl. alte Sitzung sauber und startet ffmpeg neu.
        Rückgabe: Sitzungsnummer, die der Aufrufer bei jedem write()/detach() mitgeben muss."""
        if self._stop.is_set():
            raise RuntimeError("wird beendet")
        self._end_session()
        fmt = FORMAT_BY_MIME.get(mime.split(";")[0].strip().lower())
        if not fmt:
            raise ValueError(f"Nicht unterstütztes Format vom Handy: {mime!r}")
        cmd = self._build_cmd(fmt)
        self.state, self.error = "connecting", ""
        self._stderr.clear()
        self.device_label = device_label[:120]
        with self._proc_lock:
            self._session += 1
            session = self._session
            try:
                self._proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                              stderr=subprocess.PIPE, bufsize=0, **_NOWIN)
            except Exception as e:
                self.state, self.error = "error", f"ffmpeg konnte nicht gestartet werden: {e}"
                raise
            proc = self._proc
        threading.Thread(target=self._drain_stderr, args=(proc, session), daemon=True).start()
        threading.Thread(target=self._read_frames, args=(proc, session), daemon=True).start()
        threading.Thread(target=self._watchdog, args=(proc, session, time.time()), daemon=True).start()
        self.last_seen_phone = time.time()
        return session

    def write(self, session: int, data: bytes) -> bool:
        """Reicht ein vom Handy empfangenes Stück an ffmpeg weiter. False = Sitzung nicht mehr aktuell (verwerfen)."""
        with self._proc_lock:
            if session != self._session or self._proc is None or self._proc.poll() is not None:
                return False
            proc = self._proc
        try:
            proc.stdin.write(data)
            proc.stdin.flush()
        except (BrokenPipeError, OSError):
            return False
        self.last_seen_phone = time.time()
        return True

    def detach(self, session: int) -> None:
        """Handy hat die Verbindung regulär beendet (Browser-Tab geschlossen, Stopp-Taste)."""
        with self._proc_lock:
            if session != self._session:
                return
        self._end_session()
        if not self._stop.is_set():
            self.state, self.error = "offline", "Handy hat die Verbindung beendet"

    def _end_session(self) -> None:
        with self._proc_lock:
            proc, self._proc = self._proc, None
            self._session += 1  # macht alle noch laufenden write()-Aufrufe der alten Sitzung wirkungslos
        if proc is None:
            return
        try:
            if proc.stdin:
                proc.stdin.close()
        except OSError:
            pass
        if proc.poll() is None:
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()

    # -- ffmpeg: Eingang von stdin (Handy), Ausgang wie bei der normalen Kamera -----------------
    def _build_cmd(self, fmt: str) -> list[str]:
        s = self.s
        cmd = [find_ffmpeg(s.ffmpeg_bin), "-hide_banner", "-loglevel", "warning", "-nostdin",
               "-fflags", "+genpts", "-f", fmt, "-i", "pipe:0"]
        cmd += ["-map", "0:v:0", "-an", "-vf", f"fps={s.detect_fps:g},scale={s.pipe_width}:-2",
                "-q:v", "5", "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1"]
        if s.clip_enabled:
            s.segments_dir.mkdir(parents=True, exist_ok=True)
            cmd += ["-map", "0:v:0", "-map", "0:a:0?"]
            cmd += ["-vf", f"scale={s.clip_width}:-2,fps=15", "-c:v", "libx264", "-preset", "ultrafast",
                    "-tune", "zerolatency", "-crf", "28", "-pix_fmt", "yuv420p", "-g", str(15 * s.segment_s),
                    "-force_key_frames", f"expr:gte(t,n_forced*{s.segment_s})",
                    "-c:a", "aac", "-b:a", "64k", "-ac", "1", "-ar", "44100"]
            cmd += ["-f", "segment", "-segment_time", str(s.segment_s), "-segment_format", "mpegts",
                    "-reset_timestamps", "1", "-strftime", "1", str(s.segments_dir / "seg_%Y%m%d_%H%M%S.ts")]
        return cmd

    def _read_frames(self, proc: subprocess.Popen, session: int) -> None:
        buf = bytearray()
        rd = proc.stdout
        while not self._stop.is_set():
            chunk = rd.read(65536)
            if not chunk:
                return
            with self._proc_lock:
                if session != self._session:
                    return
            buf += chunk
            while True:
                i = buf.find(b"\xff\xd8")
                if i < 0:
                    buf.clear()
                    break
                j = buf.find(b"\xff\xd9", i + 2)
                if j < 0:
                    if i > 0:
                        del buf[:i]
                    break
                frame = bytes(buf[i:j + 2])
                del buf[:j + 2]
                self.last_frame_ts = time.time()
                self.frames += 1
                self.state = "online"
                try:
                    self.on_frame(frame, self.last_frame_ts)
                except Exception:
                    pass

    def _drain_stderr(self, proc: subprocess.Popen, session: int) -> None:
        try:
            for line in iter(proc.stderr.readline, b""):
                with self._proc_lock:
                    if session != self._session:
                        return
                txt = line.decode("utf-8", "replace").strip()
                if txt:
                    self._stderr.append(txt[:240])
        except Exception:
            pass

    def _watchdog(self, proc: subprocess.Popen, session: int, started: float) -> None:
        while proc.poll() is None and not self._stop.is_set():
            time.sleep(3)
            with self._proc_lock:
                if session != self._session:
                    return
            ref = max(self.last_frame_ts, started)
            if time.time() - ref > 20:
                self._stderr.append("Watchdog: seit 20 s kein Bild vom Handy – Sitzung wird beendet")
                with self._proc_lock:
                    if session == self._session:
                        self.state, self.error = "offline", "Keine Daten mehr vom Handy erhalten"
                proc.kill()
                return

    # -- Segmente / Clips: identisch zu camera.Camera (gleiche Verzeichnisstruktur) --------------
    def segments(self) -> list[tuple[float, Path]]:
        out: list[tuple[float, Path]] = []
        d = self.s.segments_dir
        if not d.is_dir():
            return out
        for p in d.iterdir():
            m = SEG_RE.search(p.name)
            if m:
                try:
                    from datetime import datetime

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
            self._stderr.append("Clip-Erzeugung fehlgeschlagen: " + r.stderr.decode("utf-8", "replace")[-200:])
            return None
        return out_path
