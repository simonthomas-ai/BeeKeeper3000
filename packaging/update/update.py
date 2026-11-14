#!/usr/bin/env python3
"""Hornet3000 – Update einer vorhandenen Installation (1.0/1.1.x/1.2.x) auf 1.3.0, ohne Einstellungen und Daten anzufassen.

Aufruf mit dem Python DER INSTALLATION (nicht mit dem System-Python):
    <Installationsordner>/python/bin/python3 update.py            (Linux, macOS)
    <Installationsordner>\\python\\python.exe update.py            (Windows)
Optionen:  --target ORDNER   Installationsordner (Standard je Betriebssystem, siehe LIES-MICH-UPDATE.txt)
           --nur-pruefen     prüft nur Paket und Installation, ändert nichts

Ablauf: Paket gegen MANIFEST.sha256 prüfen → laufendes Programm beenden → Sicherung der zu ersetzenden Teile in
app/sicherung-<alte Version>-<Zeit>/ → neue Dateien einspielen → Selbsttest → bei Fehler automatischer Rückfall.
Nur die Standardbibliothek wird benutzt."""
from __future__ import annotations

import argparse
import hashlib
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
NEW = "1.3.0"


def say(msg: str) -> None:
    print(msg, flush=True)


def default_target() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Programs" / "Hornet3000"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Hornet3000"
    return Path.home() / ".local" / "share" / "hornet3000"


def pillow_wheel_kind() -> str:
    m = platform.machine().lower()
    if os.name == "nt":
        return "win"
    if sys.platform == "darwin":
        return "mac_arm64" if m in ("arm64", "aarch64") else "mac_x86_64"
    return "lin"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_payload() -> None:
    man = HERE / "MANIFEST.sha256"
    if not man.exists():
        raise SystemExit("MANIFEST.sha256 fehlt – das Paket ist unvollständig.")
    bad = []
    for line in man.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, name = line.split("  ", 1)
        p = HERE / name
        if not p.is_file() or sha256(p) != digest:
            bad.append(name)
    if bad:
        raise SystemExit("Das Paket ist beschädigt (Prüfsumme stimmt nicht): " + ", ".join(bad[:5]))


def installed_version(app: Path) -> str:
    try:
        m = re.search(r'__version__\s*=\s*"([^"]+)"', (app / "hornet" / "__init__.py").read_text(encoding="utf-8"))
        return m.group(1) if m else "unbekannt"
    except OSError:
        return "unbekannt"


def py_of(target: Path) -> Path:
    return target / "python" / ("python.exe" if os.name == "nt" else "bin/python3")


def run_app(target: Path, *args: str, timeout: int = 180) -> subprocess.CompletedProcess:
    return subprocess.run([str(py_of(target)), "-I", str(target / "app" / "hornet_run.py"), *args],
                          capture_output=True, text=True, timeout=timeout, cwd=str(target / "app"))


def unwheel(whl: Path, lib: Path) -> None:
    with zipfile.ZipFile(whl) as z:
        for n in z.namelist():
            if n.startswith("/") or ".." in Path(n).parts:
                raise SystemExit(f"Unsicherer Pfad im Paket: {n}")
        z.extractall(lib)
        for info in z.infolist():
            mode = info.external_attr >> 16
            if mode:
                (lib / info.filename).chmod(((mode & 0o755) | 0o700) if (mode & 0o111) else ((mode & 0o644) | 0o600))


def rm(p: Path) -> None:
    if p.is_dir() and not p.is_symlink():
        shutil.rmtree(p)
    elif p.exists() or p.is_symlink():
        p.unlink()


LIB_PARTS = ("PIL", "pillow.libs", "pillow-*.dist-info", "Pillow-*.dist-info", "certifi", "certifi-*.dist-info",
             "serial", "pyserial-*.dist-info")
APP_PARTS = ("hornet", "web", "docs", "mobil", "hornet_run.py", "README.txt", "LICENSES.txt")


def cp(src: Path, dst: Path) -> None:
    if src.is_dir():
        shutil.copytree(src, dst, symlinks=True)
    else:
        shutil.copy2(src, dst)


def backup(app: Path, dest: Path) -> None:
    dest.mkdir(parents=True)
    for name in APP_PARTS:
        if (app / name).exists():
            cp(app / name, dest / name)
    (dest / "lib").mkdir()
    for pat in LIB_PARTS:
        for src in (app / "lib").glob(pat):
            cp(src, dest / "lib" / src.name)


def restore(app: Path, src: Path) -> None:
    for name in APP_PARTS:
        rm(app / name)
        if (src / name).exists():
            cp(src / name, app / name)
    for pat in LIB_PARTS:
        for p in (app / "lib").glob(pat):
            rm(p)
    for p in (src / "lib").iterdir():
        cp(p, app / "lib" / p.name)


def install_new(app: Path) -> None:
    for name in ("hornet", "web", "docs", "mobil"):
        rm(app / name)
        shutil.copytree(HERE / "app" / name, app / name)
    shutil.copy2(HERE / "app" / "hornet_run.py", app / "hornet_run.py")
    for name in ("README.txt", "LICENSES.txt"):          # je Betriebssystem/Architektur eigene Fassung
        shutil.copy2(HERE / "platform" / pillow_wheel_kind() / name, app / name)
    lib = app / "lib"
    for pat in LIB_PARTS:
        for p in lib.glob(pat):
            rm(p)
    unwheel(next((HERE / "wheels" / pillow_wheel_kind()).glob("pillow-*.whl")), lib)
    unwheel(next((HERE / "wheels" / "pure").glob("certifi-*.whl")), lib)
    unwheel(next((HERE / "wheels" / "pure").glob("pyserial-*.whl")), lib)
    for d in app.glob("hornet/**/__pycache__"):
        shutil.rmtree(d, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", default="")
    ap.add_argument("--nur-pruefen", action="store_true")
    a = ap.parse_args()
    target = Path(a.target).expanduser() if a.target else default_target()
    app = target / "app"
    say(f"Hornet3000 Update auf {NEW}\nInstallationsordner: {target}")
    if not (app / "hornet_run.py").exists() or not py_of(target).exists():
        say("Hier ist keine Hornet3000-Installation. Mit --target ORDNER den Installationsordner angeben "
            "(der Ordner, in dem „python“ und „app“ liegen).")
        return 2
    if Path(sys.executable).resolve() != py_of(target).resolve():
        say(f"Bitte mit dem Python der Installation starten:\n  {py_of(target)} {Path(__file__).name}")
        return 2
    old = installed_version(app)
    say(f"Installierte Version: {old}")
    if old == NEW:
        say("Diese Installation ist schon auf dem Stand 1.3.0. Nichts zu tun.")
        return 0
    if not re.match(r"^1\.[012]\.", old):
        say("Dieses Update ist nur für 1.0.x bis 1.2.x gedacht. Bitte stattdessen den Installer 1.3.0 verwenden.")
        return 2
    say("Prüfe das Paket …")
    verify_payload()
    say("  Paket ist vollständig und unverändert.")
    if a.nur_pruefen:
        say("Alles in Ordnung (nur geprüft, nichts geändert).")
        return 0
    say("Beende laufendes Programm …")
    try:
        run_app(target, "stop", timeout=60)
    except Exception as e:  # noqa: BLE001
        say(f"  (Hinweis: {e})")
    time.sleep(1.5)
    sich = app / f"sicherung-{old}-{time.strftime('%Y%m%d-%H%M%S')}"
    say(f"Sichere die alten Programmteile nach {sich.name} …")
    backup(app, sich)
    try:
        say("Spiele die neuen Dateien ein …")
        install_new(app)
        say("Selbsttest …")
        r = run_app(target, "selftest")
        out = (r.stdout or "") + (r.stderr or "")
        if r.returncode != 0 or "Alles bereit" not in out:
            raise RuntimeError("Selbsttest fehlgeschlagen:\n" + out[-1500:])
        if installed_version(app) != NEW:
            raise RuntimeError("Version nach dem Einspielen nicht 1.3.0")
    except Exception as e:  # noqa: BLE001
        say(f"\nFEHLER: {e}\nStelle den alten Stand wieder her …")
        restore(app, sich)
        r = run_app(target, "selftest")
        ok = r.returncode == 0
        say("Der alte Stand ist wiederhergestellt" + (" und läuft." if ok else ", der Selbsttest meldet aber Probleme.")
            + f" Die Sicherung liegt in {sich}.")
        return 1
    if sys.platform == "darwin" and (target / ".installed-version").exists():
        (target / ".installed-version").write_text(NEW, encoding="utf-8")
    say(f"\nFertig: Hornet3000 ist jetzt auf {NEW}. Einstellungen (.env) und Daten wurden nicht angefasst.\n"
        f"Die Sicherung der alten Programmteile liegt in {sich} (kann später gelöscht werden).\n"
        "Starten wie bisher (Linux: hornet3000 open · Windows: Startmenü · macOS: Hornet3000.app).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
