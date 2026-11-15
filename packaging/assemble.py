#!/usr/bin/env python3
"""Baut die Installationsverzeichnisse für 1.3.0 (Linux, Windows, macOS arm64/x86_64) aus den geprüften
1.1.0-Laufzeiten (Python + Bibliotheken) und dem aktuellen Projektstand.

Eingaben (außerhalb dieses Repos):  x110/<kind>/…  = entpackte 1.1.0-Pakete (Python-Laufzeit, Bibliotheken, ffmpeg)
                                    build/wheels/…  = frisch geladene Wheels: Pillow 13.0.0 je Plattform, certifi, pyserial, opentelemetry-api 1.45.2
Ausgabe:  build/stage_<kind>/ (python/ + app/ bzw. Hornet3000/-Ordner für macOS)
Nichts wird erfunden: ersetzt werden nur hornet/, web/, hornet_run.py, README, LICENSES und vier Bibliotheken."""
import re
import shutil
import sys
import zipfile
from pathlib import Path

VERSION = "1.3.0"
PROJ = Path(__file__).resolve().parents[1]
APK_SRC = Path("/home/claude/dist/Hornet3000-Station-1.3.0.apk")
B = Path("/home/claude/build")
X = Path("/home/claude/x110")
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache")
KINDS = ["lin", "win", "mac_arm64", "mac_x86_64"]
PILLOW_WHEEL = {k: next((B / "wheels" / k).glob("pillow-*.whl")) for k in KINDS}
PURE = {p.name.split("-")[0].lower(): p for p in (B / "wheels/pure").glob("*.whl")}


def app_dir(root: Path, kind: str) -> Path:
    if kind.startswith("mac"):
        return root / "Hornet3000/Hornet3000.app/Contents/Resources/runtime/app"
    return root / "app"


def unwheel(whl: Path, lib: Path) -> list[str]:
    with zipfile.ZipFile(whl) as z:
        names = z.namelist()
        for n in names:                       # keine Pfade nach außen
            assert not n.startswith("/") and ".." not in Path(n).parts, n
        z.extractall(lib)
        # Ausführbare Bits (Mach-O/ELF-Dateien liegen im Wheel mit gesetzten Rechten)
        for info in z.infolist():
            mode = info.external_attr >> 16
            if mode:
                (lib / info.filename).chmod((mode & 0o755) | 0o644 if not (mode & 0o111) else (mode & 0o755) | 0o700)
    return names


def replace_lib(lib: Path, kind: str) -> None:
    # Pillow
    for pat in ("PIL", "pillow-*.dist-info", "pillow.libs", "Pillow-*.dist-info"):
        for p in lib.glob(pat):
            shutil.rmtree(p)
    unwheel(PILLOW_WHEEL[kind], lib)
    # certifi
    for p in list(lib.glob("certifi")) + list(lib.glob("certifi-*.dist-info")):
        shutil.rmtree(p)
    unwheel(PURE["certifi"], lib)
    # opentelemetry-api (Abhängigkeit von FastAPI; 1.45.1 hat die Meldung CVE-2026-126360, behoben in 1.45.2)
    for p in list(lib.glob("opentelemetry")) + list(lib.glob("opentelemetry_api-*.dist-info")):
        shutil.rmtree(p)
    unwheel(PURE["opentelemetry_api"], lib)
    # pyserial (neu in 1.2.0, Funkgerät)
    for p in list(lib.glob("serial")) + list(lib.glob("pyserial-*.dist-info")):
        shutil.rmtree(p)
    unwheel(PURE["pyserial"], lib)
    for d in lib.rglob("__pycache__"):
        shutil.rmtree(d, ignore_errors=True)
    # pyserial: Teile anderer Betriebssysteme werden nie geladen, bleiben aber (klein) im Paket


def licenses_text(old: str, lib: Path) -> str:
    """LICENSES.txt: Versionszeile, Paketliste (aus den dist-info) und Zusatzhinweise neu."""
    rows = []
    for di in sorted(lib.glob("*.dist-info")):
        meta = (di / "METADATA").read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
        name = re.search(r"^Name: (.+)$", meta, re.M)
        ver = re.search(r"^Version: (.+)$", meta, re.M)
        lic = re.search(r"^License-Expression: (.+)$", meta, re.M) or re.search(r"^License: (.+)$", meta, re.M)
        cls = re.findall(r"^Classifier: License :: (?:OSI Approved :: )?(.+)$", meta, re.M)
        text = (lic.group(1).strip() if lic else "; ".join(cls) or "siehe Paket")
        if len(text) > 60 or "\n" in text:
            text = "; ".join(cls) or text.splitlines()[0][:60]
        rows.append(f"  {name.group(1) if name else di.name:<28} {ver.group(1) if ver else '':<12} {text}")
    head, _, tail = old.partition("Python-Pakete (Lizenzangaben aus den Paketen)\n")
    _, _, tail2 = tail.partition("\n\nNicht enthalten")
    head = head.replace("1.1.0", VERSION)
    return head + "Python-Pakete (Lizenzangaben aus den Paketen)\n" + "\n".join(rows) + "\n\nNicht enthalten" + tail2


def readme_text(old: str, kind: str) -> str:
    t = old.replace("HORNET3000 WÄCHTER 1.1.0", f"HORNET3000 WÄCHTER {VERSION}")
    t = t.replace("Hornet3000-1.1.0-", f"Hornet3000-{VERSION}-").replace("Hornet3000-Setup-1.1.0", f"Hornet3000-Setup-{VERSION}")
    sep = "────────────────────────────────────────────────────────────────────────\n"
    new = (PROJ / "packaging/README-neu-1.3.0.txt").read_text(encoding="utf-8")
    i = t.index(sep + "INSTALLATION (")
    t = t[:i] + new + t[i:]
    extra = ("· Altgeräte (1.3.0): Alte Handys/Tablets liefern Bilder (Kamera-Quelle „push“) und zeigen Alarme an. Die Android-App\n"
             "  (ab Android 2.2) lädt man auf der Seite /m des Wächters herunter. Mehr: docs/MOBIL.md.\n"
             "· Funknetz (1.2.0): Funknachrichten sind Fremdtext und werden streng geprüft und begrenzt. Bei Missbrauch\n"
             "  den Funkschlüssel bzw. den River-Raum wechseln. Die Oberfläche ist standardmäßig im Heimnetz erreichbar\n"
             "  (HOST=0.0.0.0) und nur durch den Zugangsschlüssel geschützt – ohne HTTPS nicht ins Internet stellen;\n"
             "  nur für den eigenen Rechner: HOST=127.0.0.1 in der .env. Mehr: docs/SICHERHEIT.md.\n")
    anchor = "· Aufzeichnungen liegen im Ordner data und werden nach 90 Tagen gelöscht (einstellbar).\n"
    assert anchor in t
    t = t.replace(anchor, anchor + extra)
    return t


def stage(kind: str) -> Path:
    dst = B / f"stage_{kind}"
    if dst.exists():
        shutil.rmtree(dst)
    if kind.startswith("mac"):
        shutil.copytree(X / kind / "Hornet3000", dst / "Hornet3000", symlinks=True)
    else:
        dst.mkdir(parents=True)
        shutil.copytree(X / kind / "python", dst / "python", symlinks=True)
        shutil.copytree(X / kind / "app", dst / "app", symlinks=True)
    app = app_dir(dst, kind)
    for name in ("hornet", "web"):
        shutil.rmtree(app / name)
        shutil.copytree(PROJ / name, app / name, ignore=IGNORE)
    shutil.copy(PROJ / "hornet_run.py", app / "hornet_run.py")
    (app / "docs").mkdir(exist_ok=True)
    for f in sorted((PROJ / "docs").glob("*.md")):
        shutil.copy(f, app / "docs" / f.name)
    shutil.copy(PROJ / "CHANGELOG.md", app / "docs" / "CHANGELOG.md")
    # Android-App zum Herunterladen für Altgeräte (der Wächter liefert sie nach Anmeldung aus; Quelle: android/, Signatur: eigener Schlüssel)
    apk = APK_SRC
    assert apk.is_file() and apk.stat().st_size > 50_000, f"Android-App fehlt: {apk}"
    (app / "mobil").mkdir(exist_ok=True)
    shutil.copy(apk, app / "mobil" / "Hornet3000-Station.apk")
    # Das Modell bleibt unverändert; Prüfsumme gegen das Projekt
    assert (app / "models/hornet_yolov8s.onnx").stat().st_size == (PROJ / "models/hornet_yolov8s.onnx").stat().st_size
    replace_lib(app / "lib", kind)
    (app / "LICENSES.txt").write_text(licenses_text((app / "LICENSES.txt").read_text(encoding="utf-8-sig"),
                                                    app / "lib"), encoding="utf-8-sig")
    old = (app / "README.txt").read_text(encoding="utf-8-sig")
    (app / "README.txt").write_text(readme_text(old, kind), encoding="utf-8-sig")
    if kind.startswith("mac"):
        top = dst / "Hornet3000"
        shutil.copy(app / "README.txt", top / "README.txt")
        shutil.copy(app / "LICENSES.txt", top / "LICENSES.txt")
        (top / "Hornet3000.app/Contents/Resources/VERSION").write_text(VERSION, encoding="utf-8")
    for d in dst.rglob("__pycache__"):
        shutil.rmtree(d, ignore_errors=True)
    return dst


if __name__ == "__main__":
    for k in sys.argv[1:] or KINDS:
        d = stage(k)
        mb = sum(f.stat().st_size for f in d.rglob("*") if f.is_file()) // 1048576
        print(k, "->", d, mb, "MB")
