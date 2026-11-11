#!/bin/sh
# Hornet3000 Update auf 1.2.0 (Linux/macOS): sucht die Installation und startet update.py mit deren Python.
# Eigener Ordner:  sh Update-Linux-macOS.sh /pfad/zur/installation   (Ordner mit „python“ und „app“)
cd "$(dirname "$0")" || exit 2
for d in "$1" "$HOME/.local/share/hornet3000" "$HOME/Library/Application Support/Hornet3000"; do
  if [ -n "$d" ] && [ -x "$d/python/bin/python3" ] && [ -f "$d/app/hornet_run.py" ]; then
    exec "$d/python/bin/python3" update.py --target "$d"
  fi
done
echo "Keine Hornet3000-Installation gefunden. Ordner angeben:  sh Update-Linux-macOS.sh /pfad/zur/installation"
exit 2
