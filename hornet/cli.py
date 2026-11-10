"""Programmsteuerung:  run | open | stop | selftest | token

  run       Server im Vordergrund starten (Neustart nach Änderungen in der Einrichtung inklusive)
  open      Falls nötig im Hintergrund starten, dann die Oberfläche im Browser öffnen (mit Zugangsschlüssel)
  stop      Laufendes Programm beenden
  selftest  Selbsttest
  token     Zugangsschlüssel anzeigen
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

import httpx

from .config import ROOT, Settings, ensure_access_token, ensure_env_file

PID_FILE = ROOT / "data" / "hornet.pid"


def _ensure_console() -> None:
    """Unter pythonw.exe (Autostart ohne Fenster) gibt es keine Konsole: Ausgaben in data/hornet.log umleiten."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    log_dir = ROOT / "data"
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / "hornet.log"
    if path.exists() and path.stat().st_size > 5_000_000:
        path.replace(log_dir / "hornet.log.1")
    log = open(path, "a", buffering=1, encoding="utf-8")
    sys.stdout = sys.stdout or log
    sys.stderr = sys.stderr or log


def _base_url(s: Settings) -> str:
    return f"{'https' if s.ssl_certfile else 'http'}://127.0.0.1:{s.port}"


def _alive(s: Settings) -> bool:
    try:
        return httpx.get(_base_url(s) + "/api/health", timeout=2, verify=False).status_code == 200  # nosec B501 - nur Selbstabfrage an 127.0.0.1, es wird nichts Geheimes gesendet
    except httpx.HTTPError:
        return False


def run_server() -> None:
    import uvicorn

    from .server import create_app

    _ensure_console()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%H:%M:%S")
    ensure_env_file()
    first = True
    while True:
        s = Settings.from_env(override=not first)
        fresh = ensure_access_token(s)
        if first and _alive(s):
            print(f"Hornet3000 läuft bereits ({_base_url(s)}). Öffne die Oberfläche …")
            webbrowser.open(f"{_base_url(s)}/?t={s.access_token}")
            return
        scheme = "https" if s.ssl_certfile else "http"
        shown = s.public_url or f"{scheme}://localhost:{s.port}"
        print("\n" + "=" * 66)
        print(" Hornet3000 Wächter")
        print(f" Oberfläche:       {shown}")
        print(f" Zugangsschlüssel: {s.access_token}" + ("   (neu erzeugt)" if fresh else ""))
        print(f" Kamera:           {'eingerichtet' if s.camera_source.strip() else 'noch nicht eingerichtet – bitte in der App unter „Einrichtung“ eintragen'}")
        print(" Beenden: dieses Fenster schließen oder Strg+C")
        print("=" * 66 + "\n", flush=True)
        app = create_app(s)
        kw = {"ssl_certfile": s.ssl_certfile, "ssl_keyfile": s.ssl_keyfile} if s.ssl_certfile and s.ssl_keyfile else {}
        server = uvicorn.Server(uvicorn.Config(app, host=s.host, port=s.port, log_level="warning", **kw))
        app.state.shutdown = lambda: setattr(server, "should_exit", True)
        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text(str(os.getpid()))
        try:
            server.run()
        finally:
            PID_FILE.unlink(missing_ok=True)
        if not app.state.restart_requested:
            return
        print("Neustart mit den neuen Einstellungen …", flush=True)
        first = False
        time.sleep(1.5)


def _spawn_background() -> None:
    exe = Path(sys.executable)
    if os.name == "nt":
        pyw = exe.with_name("pythonw.exe")
        exe = pyw if pyw.exists() else exe
    entry = ROOT / "hornet_run.py"
    cmd = [str(exe), str(entry), "run"] if entry.exists() else [str(exe), "-m", "hornet", "run"]
    kw: dict = {"cwd": str(ROOT), "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        kw["creationflags"] = 0x00000008 | 0x00000200 | 0x08000000  # DETACHED | NEW_PROCESS_GROUP | NO_WINDOW
    else:
        kw["start_new_session"] = True
    subprocess.Popen(cmd, **kw)


def cmd_open() -> int:
    ensure_env_file()
    s = Settings.from_env()
    ensure_access_token(s)
    if not _alive(s):
        _spawn_background()
        for _ in range(80):
            time.sleep(0.5)
            if _alive(s):
                break
        else:
            print("Das Programm startet nicht. Protokoll: data/hornet.log", file=sys.stderr)
            return 1
    webbrowser.open(f"{_base_url(s)}/?t={s.access_token}")
    return 0


def cmd_stop() -> int:
    if not PID_FILE.exists():
        print("Hornet3000 läuft nicht.")
        return 0
    pid = int(PID_FILE.read_text().strip() or 0)
    if not pid:
        return 0
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True,
                           creationflags=0x08000000)
        else:
            import signal

            os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        pass
    for _ in range(30):
        time.sleep(0.3)
        try:
            os.kill(pid, 0)
        except OSError:
            break
    PID_FILE.unlink(missing_ok=True)
    print("Hornet3000 beendet.")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else "run"
    if cmd in ("run", "open", "stop", "selftest", "token"):
        # .env und Zugangsschlüssel müssen für jeden Befehl existieren (auch vor dem allerersten Start),
        # damit z. B. "selftest" und "token" direkt nach der Installation einen Schlüssel anzeigen können.
        ensure_env_file()
        ensure_access_token(Settings.from_env())
    if cmd == "run":
        run_server()
        return 0
    if cmd == "open":
        return cmd_open()
    if cmd == "stop":
        return cmd_stop()
    if cmd == "selftest":
        from .tools.selftest import main as selftest

        return selftest()
    if cmd == "token":
        s = Settings.from_env()
        ensure_env_file()
        ensure_access_token(s)
        print(s.access_token)
        return 0
    print(__doc__)
    return 2