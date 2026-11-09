"""Freenet-Weg: River-Raum über das Kommandozeilenprogramm `riverctl` und einen Freenet-Knoten auf dem eigenen Rechner.

  Empfangen  riverctl message stream <Raum> --format json   (läuft dauerhaft, JSON je Zeile)
  Senden     riverctl message send <Raum> "<Zeile>"

Alle Aufrufe verwenden Argumentlisten (nie eine Shell). Raum, Programmpfad und Knotenadresse werden vor der
Verwendung streng geprüft. Ein privater River-Raum (`riverctl room create --private`) verschlüsselt alle
Nachrichten mit AES-256-GCM; Beitritt nur per Einladung.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

from .transport import ReceiveFn, Transport, TransportError

log = logging.getLogger("hornet.mesh.freenet")

_ROOM_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,64}$")           # base58 (Verifying Key des Raum-Besitzers)
_NODE_RE = re.compile(r"^wss?://(?:[A-Za-z0-9.\-]{1,253}|\[[0-9A-Fa-f:]{2,45}\]):\d{2,5}$")
_INVITE_RE = re.compile(r"^[A-Za-z0-9+/=_\-:.]{16,8000}$")
_NOWIN = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)} if os.name == "nt" else {}
LINE_MAX = 64 * 1024
SEND_TIMEOUT_S = 90
MIN_SEND_GAP_S = 2.0


def check_room(room: str) -> str:
    room = (room or "").strip()
    if room and not _ROOM_RE.match(room):
        raise ValueError("River-Raum: bitte den Raum-Schlüssel (Room Owner VK) aus „riverctl room list“ einfügen")
    return room


def check_node(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    if not _NODE_RE.match(url):
        raise ValueError("Freenet-Knoten: Adresse wie ws://127.0.0.1:7509 erwartet")
    return url


def check_invite(code: str) -> str:
    code = (code or "").strip()
    if not _INVITE_RE.match(code):
        raise ValueError("Das sieht nicht wie eine River-Einladung aus")
    return code


def resolve_riverctl(configured: str) -> str:
    """Findet das Programm; erlaubt sind nur Dateien, die riverctl heißen (keine beliebigen Programme)."""
    cand = (configured or "riverctl").strip()
    path = shutil.which(cand) if os.sep not in cand and "/" not in cand else cand
    if not path or not Path(path).is_file() or not os.access(path, os.X_OK):
        raise TransportError("riverctl nicht gefunden – Programm installieren oder den Pfad eintragen")
    if not re.match(r"^riverctl(\.exe)?$", Path(path).name, re.I):
        raise TransportError("Als Programm ist nur „riverctl“ erlaubt")
    return path


class FreenetTransport(Transport):
    name = "freenet"
    label = "Freenet (River)"
    max_bytes = 200

    def __init__(self, riverctl: str, room: str, node: str = "ws://127.0.0.1:7509", config_dir: Path | None = None):
        super().__init__()
        self.room = check_room(room)
        if not self.room:
            raise ValueError("Freenet: Raum-Schlüssel fehlt")
        self.node = check_node(node)
        self.riverctl_cfg = riverctl
        self.config_dir = config_dir
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._proc: subprocess.Popen | None = None
        self._send_lock = threading.Lock()
        self._last_send = 0.0
        self.me_key = ""
        self.connected = False
        self.error = ""
        self.rx = self.tx = self.restarts = 0
        self.last_rx = self.last_tx = 0.0

    # -- Kommandozeile ---------------------------------------------------------------------
    def _base(self) -> list[str]:
        exe = resolve_riverctl(self.riverctl_cfg)
        cmd = [exe, "--no-version-check", "--node-url", f"{self.node}/v1/contract/command?encodingProtocol=native"]
        if self.config_dir:
            cmd += ["--config-dir", str(self.config_dir)]
        return cmd

    def _env(self) -> dict:
        env = dict(os.environ)
        env["RIVERCTL_NO_VERSION_CHECK"] = "1"
        return env

    def whoami(self) -> str:
        """Eigener Schlüssel im Raum – damit eigene Nachrichten nicht als fremde zurückkommen."""
        r = subprocess.run([*self._base(), "--format", "json", "identity", "whoami", self.room],
                           capture_output=True, text=True, timeout=30, env=self._env(), **_NOWIN)
        if r.returncode != 0:
            raise TransportError(_first_line(r.stderr) or "riverctl whoami fehlgeschlagen")
        try:
            return str(json.loads(r.stdout).get("verifying_key") or "")
        except (ValueError, AttributeError):
            return ""

    # -- Lebenszyklus -----------------------------------------------------------------------
    def start(self, on_receive: ReceiveFn) -> None:
        super().start(on_receive)
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="mesh-freenet")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        p = self._proc
        if p is not None and p.poll() is None:
            try:
                p.terminate()
                p.wait(timeout=5)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass
        if self._thread is not None:
            self._thread.join(timeout=8)

    def _run(self) -> None:
        backoff = 2.0
        while not self._stop.is_set():
            try:
                try:
                    self.me_key = self.whoami()
                except (TransportError, subprocess.SubprocessError, OSError) as e:
                    self.me_key = ""
                    if isinstance(e, TransportError) and "nicht gefunden" in str(e):
                        raise
                cmd = [*self._base(), "--format", "json", "message", "stream", self.room, "--subscribe"]
                self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                              encoding="utf-8", errors="replace", env=self._env(), **_NOWIN)
                err_tail: list[str] = []
                threading.Thread(target=_drain_err, args=(self._proc.stderr, err_tail), daemon=True).start()
                started = time.time()
                self.connected, self.error = True, ""
                self._read_stream(self._proc.stdout)
                code = self._proc.wait(timeout=10)
                self.connected = False
                if self._stop.is_set():
                    return
                self.error = _first_line(" ".join(err_tail)) or f"riverctl beendet (Code {code})"
                if code == 75:              # Raum-Vertrag wurde neu aufgesetzt: sofort neu starten
                    backoff = 0.5
                elif time.time() - started > 60:
                    backoff = 2.0
            except Exception as e:
                self.connected, self.error = False, str(e)
            self.restarts += 1
            self._stop.wait(backoff)
            backoff = min(60.0, backoff * 2)

    def _read_stream(self, f) -> None:
        while not self._stop.is_set():
            line = f.readline(LINE_MAX)
            if not line:
                return
            if len(line) >= LINE_MAX and not line.endswith("\n"):   # überlange Zeile: Rest wegwerfen
                while True:
                    rest = f.readline(LINE_MAX)
                    if not rest or rest.endswith("\n"):
                        break
                continue
            self._handle_line(line)

    def _handle_line(self, line: str) -> None:
        line = line.strip()
        if not line.startswith("{"):
            return
        try:
            ev = json.loads(line)
        except (ValueError, RecursionError):
            return
        if not isinstance(ev, dict) or ev.get("type") != "message":
            return
        content = ev.get("content")
        if not isinstance(content, str) or not content:
            return
        author = ev.get("author_verifying_key")
        if self.me_key and isinstance(author, str) and author == self.me_key:
            return                           # eigene Nachricht
        self.rx += 1
        self.last_rx = time.time()
        if self.on_receive:
            try:
                self.on_receive(content, "freenet", self.last_rx)
            except Exception:
                log.exception("Fehler bei der Verarbeitung einer Freenet-Meldung")

    # -- Senden ------------------------------------------------------------------------------
    def can_send_now(self, text: str, now: float) -> bool:
        return now - self._last_send >= MIN_SEND_GAP_S

    def send(self, text: str) -> None:
        if "\n" in text or "\r" in text or not text:
            raise TransportError("Ungültige Meldung")
        with self._send_lock:
            try:
                r = subprocess.run([*self._base(), "message", "send", self.room, text], capture_output=True,
                                   text=True, timeout=SEND_TIMEOUT_S, env=self._env(), **_NOWIN)
            except subprocess.TimeoutExpired:
                raise TransportError("Freenet: Zeitüberschreitung beim Senden") from None
            except OSError as e:
                raise TransportError(f"riverctl nicht startbar: {e}") from e
        if r.returncode != 0:
            raise TransportError("Freenet: " + (_first_line(r.stderr) or f"Fehler {r.returncode}"))
        self._last_send = time.time()
        self.tx += 1
        self.last_tx = self._last_send

    def status(self) -> dict:
        return {"name": self.name, "label": self.label, "online": self.connected, "detail": self.error,
                "room": self.room[:8] + "…", "rx": self.rx, "tx": self.tx, "last_rx": self.last_rx or None,
                "last_tx": self.last_tx or None, "restarts": self.restarts}


def accept_invite(riverctl: str, code: str, node: str, config_dir: Path | None, nickname: str = "") -> str:
    """Tritt einem River-Raum bei (Einladungscode aus der Einrichtung)."""
    code = check_invite(code)
    exe = resolve_riverctl(riverctl)
    cmd = [exe, "--no-version-check", "--node-url", f"{check_node(node)}/v1/contract/command?encodingProtocol=native"]
    if config_dir:
        cmd += ["--config-dir", str(config_dir)]
    cmd += ["invite", "accept"]
    if nickname:
        cmd += ["--nickname", re.sub(r"[^\w .\-]", "", nickname)[:32] or "Station"]
    cmd.append(code)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180, **_NOWIN)
    if r.returncode != 0:
        raise TransportError(_first_line(r.stderr) or "Einladung konnte nicht angenommen werden")
    return (r.stdout or "").strip()[:500]


def _first_line(text: str) -> str:
    for ln in (text or "").splitlines():
        if ln.strip():
            return ln.strip()[:240]
    return ""


def _drain_err(f, tail: list[str]) -> None:
    try:
        for ln in f:
            tail.append(ln.strip())
            del tail[:-5]
    except Exception:
        pass
