#!/usr/bin/env python3
"""macOS: setzt Version in die App-Bundles, ergänzt „laufendes Programm vor dem Ersetzen beenden“ in den Startskripten,
signiert jede Mach-O-Datei neu ad-hoc (rcodesign; für Apple Silicon zwingend, sonst verweigert der Kernel den Start)
und packt je Architektur ein Zip. Ausgangspunkt: build/stage_mac_*/Hornet3000 (von assemble.py gebaut).
Nicht möglich ohne Mac: Starten/Notarisieren – das Ergebnis ist strukturell geprüft, nicht ausgeführt."""
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

VERSION = "1.2.0"
B = Path("/home/claude/build")
OUT = Path("/home/claude/dist")
RCODESIGN = next((B / "tools").glob("apple-codesign-*/rcodesign"))
ARCH = {"mac_arm64": "arm64", "mac_x86_64": "x86_64"}
STOP_SNIPPET = '''  if [ -x "$TARGET/python/bin/python3" ] && [ -f "$TARGET/app/hornet_run.py" ]; then
    "$TARGET/python/bin/python3" -I "$TARGET/app/hornet_run.py" stop >/dev/null 2>&1 || true
    sleep 1
  fi
'''


def is_macho(p: Path) -> bool:
    try:
        with open(p, "rb") as f:
            return f.read(4) in (b"\xfe\xed\xfa\xce", b"\xce\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe",
                                 b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca")
    except OSError:
        return False


def patch_launcher(path: Path) -> None:
    t = path.read_text(encoding="utf-8")
    key = '  rm -rf "$TARGET/python" "$TARGET/app/lib"'
    assert key in t, path
    if "stop >/dev/null" not in t:
        t = t.replace(key, STOP_SNIPPET + key, 1)
    t = t.replace('rm -rf "$TARGET/python" "$TARGET/app/lib" "$TARGET/app/hornet" "$TARGET/app/web" "$TARGET/app/models"',
                  'rm -rf "$TARGET/python" "$TARGET/app/lib" "$TARGET/app/hornet" "$TARGET/app/web" "$TARGET/app/models" "$TARGET/app/docs"')
    path.write_text(t, encoding="utf-8")


def build_one(kind: str) -> Path:
    root = B / f"stage_{kind}" / "Hornet3000"
    assert root.is_dir(), root
    for app in ("Hornet3000.app", "Hornet3000 beenden.app"):
        pl = root / app / "Contents/Info.plist"
        d = plistlib.loads(pl.read_bytes())
        d["CFBundleVersion"] = d["CFBundleShortVersionString"] = VERSION
        pl.write_bytes(plistlib.dumps(d))
    patch_launcher(root / "Hornet3000.app/Contents/MacOS/Hornet3000")
    patch_launcher(root / "Selbsttest.command")
    n = 0
    for p in sorted(root.rglob("*")):
        if p.is_file() and not p.is_symlink() and is_macho(p):
            r = subprocess.run([str(RCODESIGN), "sign", str(p)], capture_output=True)
            if r.returncode != 0:
                raise SystemExit(f"Signieren fehlgeschlagen: {p}\n{r.stderr.decode()[-400:]}")
            n += 1
    print(f"{kind}: {n} Mach-O-Dateien ad-hoc signiert")
    OUT.mkdir(exist_ok=True)
    z = OUT / f"Hornet3000-{VERSION}-macos-{ARCH[kind]}.zip"
    z.unlink(missing_ok=True)
    subprocess.run(["zip", "-r", "-X", "-y", "-q", str(z), "Hornet3000"], cwd=root.parent, check=True)
    print(f"{kind}: {z} ({z.stat().st_size // 1048576} MB)")
    return z


if __name__ == "__main__":
    for k in sys.argv[1:] or list(ARCH):
        build_one(k)
