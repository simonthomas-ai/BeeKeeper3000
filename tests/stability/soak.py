#!/usr/bin/env python3
"""Stabilitätstest mit dem ECHTEN Programm als eigenem Prozess (nicht Teil des Programms, nicht in pytest).

Was hier echt ist:   Programmprozess (uvicorn, Engine, ffmpeg-Kamera „selftest“, echtes ONNX-Modell, SQLite,
                     Funknetz-Dienst, serieller Anschluss).
Was hier Attrappe ist: das Funkgerät (TESTATTRAPPE auf einem Pseudo-Terminal, tests/fakes/mesh_device.py).

Phasen:  A  Start/Stopp-Zyklen (abwechselnd sauber beenden und hart abschießen), Datenbank danach prüfen
         B  Funk-Überflutung (gültige + kaputte Zeilen von vielen Stationen) bei gleichzeitigem Bedienbetrieb
         C  Dauerlauf mit gleichmäßigem Verkehr: Speicher, Dateihandles, Threads dürfen nicht wachsen
Aufruf:  python tests/stability/soak.py [--cycles 8] [--flood 3000] [--minutes 3]
Ergebnis: JSON-Zeile je Phase und am Ende „SOAK: BESTANDEN“ bzw. Liste der Verstöße; Exitcode 0/1.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))
from fakes.mesh_device import FakeMeshDevice  # noqa: E402
from hornet.mesh import wire  # noqa: E402

TOKEN = "soak-" + "k" * 30
CHAN_KEY = bytes(range(16))
violations: list[str] = []


def fail(msg: str) -> None:
    violations.append(msg)
    print("VERSTOSS:", msg, flush=True)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def proc_stats(pid: int) -> dict:
    st = {"rss_mb": None, "fds": None, "threads": None}
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                st["rss_mb"] = round(int(line.split()[1]) / 1024, 1)
            elif line.startswith("Threads:"):
                st["threads"] = int(line.split()[1])
        st["fds"] = len(os.listdir(f"/proc/{pid}/fd"))
    except OSError:
        pass
    return st


def children_of(pid: int) -> list[int]:
    out = subprocess.run(["pgrep", "-P", str(pid)], capture_output=True, text=True).stdout.split()
    return [int(x) for x in out]


class Instance:
    def __init__(self, root: Path, dev_path: str, src: Path = REPO, python: str = sys.executable):
        self.root, self.port = root, free_port()
        self.src, self.python = src, python
        self.proc: subprocess.Popen | None = None
        self.dev_path = dev_path
        self.base = f"http://127.0.0.1:{self.port}"

    def prepare(self) -> None:
        for name in ("hornet", "web"):
            shutil.copytree(self.src / name, self.root / name, ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy(self.src / "hornet_run.py", self.root / "hornet_run.py")
        (self.root / "models").symlink_to(self.src / "models")
        if (self.src / "lib").is_dir():
            (self.root / "lib").symlink_to(self.src / "lib")
        self.write_env()

    def write_env(self, extra: dict | None = None) -> None:
        env = {"HOST": "127.0.0.1", "PORT": str(self.port), "ACCESS_TOKEN": TOKEN, "CAMERA_NAME": "Soak-Stand",
               "CAMERA_SOURCE": "selftest", "CLIP_ENABLED": "false", "MESH_LORA_ENABLED": "true",
               "MESH_LORA_PORT": self.dev_path, "MESH_LORA_CHANNEL_KEY": CHAN_KEY.hex(), "MESH_STATION": "Soak",
               "VERIFY_PROVIDER": "none", **(extra or {})}
        (self.root / ".env").write_text("".join(f"{k}={v}\n" for k, v in env.items()))

    def start(self, timeout=60) -> float:
        t0 = time.time()
        log = open(self.root / "run.log", "ab")
        self.proc = subprocess.Popen([self.python, "-I", str(self.root / "hornet_run.py"), "run"], cwd=self.root,
                                     stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True)
        while time.time() - t0 < timeout:
            if self.proc.poll() is not None:
                raise RuntimeError(f"Prozess endete sofort (Code {self.proc.returncode}); siehe {self.root/'run.log'}")
            try:
                if httpx.get(self.base + "/api/health", timeout=1).status_code == 200:
                    return time.time() - t0
            except httpx.HTTPError:
                pass
            time.sleep(0.2)
        raise RuntimeError("Start dauerte länger als %d s" % timeout)

    def client(self) -> httpx.Client:
        c = httpx.Client(base_url=self.base, timeout=10)
        r = c.post("/api/login", json={"token": TOKEN})
        r.raise_for_status()
        return c

    def stop(self, hard: bool, wait=20) -> tuple[float, int | None]:
        assert self.proc
        kids = children_of(self.proc.pid)
        t0 = time.time()
        self.proc.send_signal(signal.SIGKILL if hard else signal.SIGTERM)
        try:
            self.proc.wait(wait)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(5)
            fail("Prozess reagierte nicht auf SIGTERM innerhalb %d s" % wait)
        dt = time.time() - t0
        # Kindprozesse (ffmpeg) dürfen nicht übrig bleiben
        end = time.time() + 12
        while time.time() < end and any(Path(f"/proc/{k}").exists() for k in kids):
            time.sleep(0.3)
        left = [k for k in kids if Path(f"/proc/{k}").exists()]
        for k in left:
            fail(f"{'nach SIGKILL' if hard else 'nach SIGTERM'}: Kindprozess {k} läuft weiter")
            try:
                os.kill(k, signal.SIGKILL)
            except OSError:
                pass
        return dt, self.proc.returncode

    def db_check(self) -> str:
        p = self.root / "data" / "hornet.db"
        if not p.exists():
            return "keine Datenbank"
        con = sqlite3.connect(p)
        try:
            return con.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            con.close()


def valid_line(i: int, station: str) -> str:
    return wire.encode(wire.MeshMessage("A", f"{i:08x}", station, 1 + i % 5, 70 + i % 30, "-", None, None, ""), 400)


def _alerts(c) -> list[dict]:
    j = c.get("/api/alerts").json()
    return j if isinstance(j, list) else j.get("alerts") or j.get("items") or []


def wait_until(cond, timeout=20, step=0.1) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(step)
    return cond()


# ── Phase A ────────────────────────────────────────────────────────────────────────────────────────
def phase_a(inst: Instance, dev: FakeMeshDevice, cycles: int) -> None:
    res = []
    for n in range(cycles):
        hard = n % 2 == 1
        t_start = inst.start()
        c = inst.client()
        st = c.get("/api/status").json()
        if st["mesh"]["enabled"] is not True:
            fail(f"Zyklus {n}: Funknetz nicht aktiv nach Start")
        ident = f"{0xA000 + n:08x}"
        dev.inject_channel_text(wire.encode(wire.MeshMessage("A", ident, f"Nachbar{n}", 2, 88, "-", None, None, ""), 400))
        ok = wait_until(lambda: any(m["ident"] == ident for m in c.get("/api/mesh/messages").json()), 25)
        if not ok:
            fail(f"Zyklus {n}: eingespeiste Meldung kam nicht an")
        c.close()
        dt, code = inst.stop(hard)
        integ = inst.db_check()
        if integ != "ok":
            fail(f"Zyklus {n} ({'SIGKILL' if hard else 'SIGTERM'}): Datenbank-Prüfung = {integ}")
        if not hard and code not in (0, -signal.SIGTERM):
            fail(f"Zyklus {n}: Beenden mit unerwartetem Code {code}")
        res.append({"n": n, "art": "kill -9" if hard else "sauber", "start_s": round(t_start, 1),
                    "stop_s": round(dt, 1), "code": code, "db": integ})
    print(json.dumps({"phase": "A", "zyklen": res}, ensure_ascii=False), flush=True)


# ── Phase B ────────────────────────────────────────────────────────────────────────────────────────
def phase_b(inst: Instance, dev: FakeMeshDevice, flood: int) -> None:
    inst.start()
    c = inst.client()
    pid = inst.proc.pid
    before = proc_stats(pid)
    lat: list[float] = []
    stop = threading.Event()
    errors: list[str] = []

    def poller():
        pc = inst.client()
        while not stop.is_set():
            t0 = time.time()
            try:
                r = pc.get("/api/status")
                if r.status_code != 200:
                    errors.append(f"status {r.status_code}")
                lat.append(time.time() - t0)
            except Exception as e:  # noqa: BLE001
                errors.append(repr(e))
            time.sleep(0.25)
        pc.close()

    th = threading.Thread(target=poller, daemon=True)
    th.start()
    t0 = time.time()
    garbage = [b"\x00\xff" * 40, b"\x3e\xff\xff", b"\x3e\x02\x00\x11\x00", os.urandom(300), b"\x83" * 50]
    for i in range(flood):
        st = f"Stat{i % 60}"
        dev.inject_channel_text(valid_line(i, st), sender=st, push=(i % 10 == 0))
        if i % 7 == 0:   # ungültige, aber für ein echtes Gerät mögliche (≤ 160 Byte) Texte
            dev.inject_channel_text("H3K1|A|zz|" + "x" * 120, sender="Böse")
        if i % 11 == 0:
            dev.inject_channel_text("H3K1|A|%08x|Fake|999|101|J|91.0|7.0|<script>alert(1)</script> http://evil" % i,
                                    sender="Fake")
        if i % 150 == 0:  # Leitungsstörung (Kabel/Stecker): selten, das Programm muss sich selbst wieder fangen
            dev.write_garbage(garbage[(i // 150) % len(garbage)])
        if i % 100 == 0:
            time.sleep(0.05)
    dev.inject_channel_text(valid_line(0xFFFFFF, "Ende"), sender="Ende")
    # Verarbeitung abwarten: Warteschlange des Geräts leer
    wait_until(lambda: not dev.pending, 120)
    time.sleep(3)
    stop.set()
    th.join(5)
    dur = time.time() - t0
    mesh = c.get("/api/mesh").json()
    after = proc_stats(pid)
    p95 = sorted(lat)[int(len(lat) * 0.95)] if lat else None
    print(json.dumps({"phase": "B", "eingespeist": flood, "dauer_s": round(dur, 1), "vorher": before,
                      "nachher": after, "status_antworten": len(lat), "latenz_max_s": round(max(lat), 2) if lat else None,
                      "latenz_p95_s": round(p95, 2) if p95 else None, "zaehler": mesh["counters"],
                      "log_zeilen": mesh["log_rows"], "verworfen_nach_grund": mesh["gate_dropped"],
                      "warteschlange": mesh["queue"]}, ensure_ascii=False), flush=True)
    if errors:
        fail(f"Phase B: {len(errors)} Fehler bei Bedienanfragen, z. B. {errors[0]}")
    if lat and max(lat) > 5:
        fail(f"Phase B: Bedienung stockte {max(lat):.1f} s während der Überflutung")
    if inst.proc.poll() is not None:
        fail("Phase B: Programm ist abgestürzt")
    if mesh["log_rows"] > 20000:
        fail(f"Phase B: Funkprotokoll nicht begrenzt ({mesh['log_rows']} Zeilen)")
    if mesh["queue"] > 250:
        fail(f"Phase B: Sendewarteschlange wuchs auf {mesh['queue']}")
    if after["rss_mb"] and before["rss_mb"] and after["rss_mb"] - before["rss_mb"] > 150:
        fail(f"Phase B: Speicher wuchs um {after['rss_mb'] - before['rss_mb']:.0f} MB")
    if after["fds"] and before["fds"] and after["fds"] - before["fds"] > 10:
        fail(f"Phase B: Dateihandles stiegen von {before['fds']} auf {after['fds']}")
    # Bedienung nach der Überflutung noch voll funktionsfähig, Alarmkette (Testalarm) läuft
    r = c.post("/api/test-alert")
    if r.status_code != 200:
        fail(f"Phase B: Testalarm nach Überflutung: {r.status_code} {r.text[:100]}")
    else:
        ok = wait_until(lambda: any(a["kind"] == "test" for a in _alerts(c)), 30)
        if not ok:
            fail("Phase B: Testalarm wurde nicht gespeichert")
    c.close()
    # läuft weiter für Phase C


# ── Phase C ────────────────────────────────────────────────────────────────────────────────────────
def phase_c(inst: Instance, dev: FakeMeshDevice, minutes: float) -> None:
    c = inst.client()
    pid = inst.proc.pid
    samples = []
    end = time.time() + minutes * 60
    i = 100000
    next_sample = 0.0
    while time.time() < end:
        i += 1
        dev.inject_channel_text(valid_line(i, f"Dauer{i % 8}"), sender=f"Dauer{i % 8}")
        if i % 5 == 0:
            c.get("/api/mesh")
            c.get("/api/status")
        if time.time() >= next_sample:
            samples.append({"t": round(end - time.time()), **proc_stats(pid)})
            next_sample = time.time() + 20
        time.sleep(0.4)
    samples.append(proc_stats(pid))
    print(json.dumps({"phase": "C", "proben": samples[:: max(1, len(samples) // 8)] + [samples[-1]]},
                     ensure_ascii=False), flush=True)
    first, last = samples[1] if len(samples) > 1 else samples[0], samples[-1]
    if last["rss_mb"] and first["rss_mb"] and last["rss_mb"] - first["rss_mb"] > 60:
        fail(f"Phase C: Speicher wuchs von {first['rss_mb']} auf {last['rss_mb']} MB")
    if last["fds"] and first["fds"] and last["fds"] - first["fds"] > 5:
        fail(f"Phase C: Dateihandles wuchsen von {first['fds']} auf {last['fds']}")
    if last["threads"] and first["threads"] and last["threads"] - first["threads"] > 5:
        fail(f"Phase C: Threads wuchsen von {first['threads']} auf {last['threads']}")
    if inst.proc.poll() is not None:
        fail("Phase C: Programm ist abgestürzt")
    c.close()
    dt, code = inst.stop(False)
    if inst.db_check() != "ok":
        fail("Phase C: Datenbank nach sauberem Beenden nicht in Ordnung")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cycles", type=int, default=8)
    ap.add_argument("--flood", type=int, default=3000)
    ap.add_argument("--minutes", type=float, default=3)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--app-dir", default="", help="installierten app/-Ordner prüfen (zusammen mit --python)")
    ap.add_argument("--python", default=sys.executable)
    a = ap.parse_args()
    root = Path(tempfile.mkdtemp(prefix="hornet-soak-"))
    dev = FakeMeshDevice(channels={1: ("hornet3000", CHAN_KEY)})
    inst = Instance(root, dev.path, Path(a.app_dir) if a.app_dir else REPO, a.python)
    inst.prepare()
    t0 = time.time()
    try:
        phase_a(inst, dev, a.cycles)
        phase_b(inst, dev, a.flood)
        phase_c(inst, dev, a.minutes)
    except Exception as e:  # noqa: BLE001
        fail(f"Testlauf abgebrochen: {e!r}")
    finally:
        if inst.proc and inst.proc.poll() is None:
            inst.proc.kill()
        dev.close()
        if not a.keep:
            shutil.rmtree(root, ignore_errors=True)
    print(f"Gesamtdauer {time.time() - t0:.0f} s")
    if violations:
        print("SOAK: DURCHGEFALLEN –", len(violations), "Verstöße")
        return 1
    print("SOAK: BESTANDEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
