"""Zeigt die an diesem Rechner erkannten Kameras/Mikrofone:  python -m hornet.tools.list_devices"""
from __future__ import annotations

import glob
import platform
import subprocess
import sys

from ..camera import _NOWIN, find_ffmpeg


def main() -> None:
    system = platform.system()
    ff = find_ffmpeg()
    if system == "Windows":
        r = subprocess.run([ff, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
                           capture_output=True, text=True, **_NOWIN)
        print(r.stderr)
        print('In der .env eintragen, z. B.:\n  CAMERA_SOURCE=dshow:Integrated Camera\n  CAMERA_AUDIO_DEVICE=Mikrofon (Realtek Audio)')
    elif system == "Darwin":
        r = subprocess.run([ff, "-hide_banner", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
                           capture_output=True, text=True)
        print(r.stderr)
        print("In der .env eintragen, z. B.:  CAMERA_SOURCE=avfoundation:0:0   (Video-Nr.:Audio-Nr.)")
    else:
        devs = sorted(glob.glob("/dev/video*"))
        print("Kameras:", ", ".join(devs) or "keine gefunden")
        print("In der .env eintragen, z. B.:  CAMERA_SOURCE=v4l2:/dev/video0   und für Ton  CAMERA_AUDIO_DEVICE=hw:1")
        print("Tonquellen: 'arecord -l'")


if __name__ == "__main__":
    sys.exit(main())