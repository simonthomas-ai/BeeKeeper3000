#!/usr/bin/env python3
"""Baut Hornet3000-1.2.0-Update.zip aus dem Projektstand und den gestagten Paketen (assemble.py)."""
import hashlib
import shutil
import zipfile
from pathlib import Path

VERSION = "1.2.0"
PROJ = Path(__file__).resolve().parents[1]
B = Path("/home/claude/build")
OUT = Path("/home/claude/dist")
ROOT = B / "update_pkg" / f"Hornet3000-{VERSION}-Update"
KINDS = ["lin", "win", "mac_arm64", "mac_x86_64"]


def app_of(kind: str) -> Path:
    s = B / f"stage_{kind}"
    return s / "Hornet3000/Hornet3000.app/Contents/Resources/runtime/app" if kind.startswith("mac") else s / "app"


if ROOT.parent.exists():
    shutil.rmtree(ROOT.parent)
ROOT.mkdir(parents=True)
ign = shutil.ignore_patterns("__pycache__", "*.pyc")
for n in ("hornet", "web", "docs"):
    shutil.copytree(app_of("lin") / n, ROOT / "app" / n, ignore=ign)
shutil.copy(PROJ / "hornet_run.py", ROOT / "app/hornet_run.py")
for k in KINDS:
    (ROOT / "platform" / k).mkdir(parents=True)
    for f in ("README.txt", "LICENSES.txt"):
        shutil.copy(app_of(k) / f, ROOT / "platform" / k / f)
    (ROOT / "wheels" / k).mkdir(parents=True)
    shutil.copy(next((B / "wheels" / k).glob("pillow-*.whl")), ROOT / "wheels" / k)
(ROOT / "wheels/pure").mkdir(parents=True)
for w in (B / "wheels/pure").glob("*.whl"):
    shutil.copy(w, ROOT / "wheels/pure")
for f in ("update.py", "Update-Linux-macOS.sh", "Update-Windows.bat", "LIES-MICH-UPDATE.txt"):
    shutil.copy(PROJ / "packaging/update" / f, ROOT / f)
(ROOT / "Update-Linux-macOS.sh").chmod(0o755)
lines = []
for p in sorted(ROOT.rglob("*")):
    if p.is_file() and p.name != "MANIFEST.sha256":
        lines.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(ROOT).as_posix()}")
(ROOT / "MANIFEST.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
z = OUT / f"Hornet3000-{VERSION}-Update.zip"
z.unlink(missing_ok=True)
with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
    for p in sorted(ROOT.rglob("*")):
        if p.is_file():
            zi = zipfile.ZipInfo.from_file(p, p.relative_to(ROOT.parent).as_posix())
            zi.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(zi, p.read_bytes())
print(z, z.stat().st_size // 1024, "KB,", len(lines), "Dateien im Manifest")
