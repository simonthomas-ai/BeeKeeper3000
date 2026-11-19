#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende
# Hornet3000 Waechter - wird von makeself nach dem Entpacken im Payload-Ordner ausgefuehrt.
set -e

DEFAULT_TARGET="$HOME/.local/share/hornet3000"
TARGET="$DEFAULT_TARGET"
DO_SERVICE=0

for arg in "$@"; do
  case "$arg" in
    --target=*) TARGET="${arg#--target=}" ;;
    --target) : ;;
    --service) DO_SERVICE=1 ;;
    --help|-h)
      echo "Verwendung: sh Hornet3000-1.3.1-linux-x86_64.run [-- --target ORDNER] [--service]"
      echo "  --target ORDNER   Zielordner (Standard: $DEFAULT_TARGET)"
      echo "  --service         richtet einen systemd-Benutzerdienst ein (dauerhafter Betrieb)"
      exit 0
      ;;
  esac
done
prev=""
for arg in "$@"; do
  if [ "$prev" = "--target" ]; then TARGET="$arg"; fi
  prev="$arg"
done

HERE="$(cd "$(dirname "$0")" && pwd)"
echo "==> Installiere nach: $TARGET"
mkdir -p "$TARGET"

if [ -x "$TARGET/python/bin/python3" ] && [ -f "$TARGET/app/hornet_run.py" ]; then
  "$TARGET/python/bin/python3" -I "$TARGET/app/hornet_run.py" stop >/dev/null 2>&1 || true
fi

rm -rf "$TARGET/python" "$TARGET/app/lib" "$TARGET/app/hornet" "$TARGET/app/web" "$TARGET/app/models"
mkdir -p "$TARGET/app"
cp -a "$HERE/python" "$TARGET/python"
cp -a "$HERE/app/." "$TARGET/app/"
chmod +x "$TARGET/python/bin/python3" "$TARGET/python/bin/python3.12" 2>/dev/null || true

BIN_DIR="$HOME/.local/bin"
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/hornet3000" <<LAUNCH
#!/bin/sh
exec "$TARGET/python/bin/python3" -I "$TARGET/app/hornet_run.py" "\$@"
LAUNCH
chmod +x "$BIN_DIR/hornet3000"

DESK_DIR="$HOME/.local/share/applications"
mkdir -p "$DESK_DIR"
ICON_DIR="$HOME/.local/share/icons/hicolor/512x512/apps"
mkdir -p "$ICON_DIR"
cp "$TARGET/app/web/assets/icons/icon-512.png" "$ICON_DIR/hornet3000.png" 2>/dev/null || true
cat > "$DESK_DIR/hornet3000.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Hornet3000 Wächter
Comment=Meldet die Asiatische Hornisse am Bienenstock mit Foto und Ton
Exec=$BIN_DIR/hornet3000 open
Icon=hornet3000
Terminal=false
Categories=Utility;
DESKTOP
chmod +x "$DESK_DIR/hornet3000.desktop"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$DESK_DIR" >/dev/null 2>&1 || true

if [ "$DO_SERVICE" = "1" ]; then
  UNIT_DIR="$HOME/.config/systemd/user"
  mkdir -p "$UNIT_DIR"
  cat > "$UNIT_DIR/hornet3000.service" <<UNIT
[Unit]
Description=Hornet3000 Waechter
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$TARGET/app
ExecStart=$TARGET/python/bin/python3 -I $TARGET/app/hornet_run.py run
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
UNIT
  if command -v systemctl >/dev/null 2>&1 && systemctl --user daemon-reload >/dev/null 2>&1; then
    systemctl --user enable --now hornet3000.service
    echo "==> systemd-Benutzerdienst eingerichtet und gestartet."
    echo "    Damit er auch ohne Anmeldung laeuft: sudo loginctl enable-linger $USER"
    echo "    Protokoll: journalctl --user -u hornet3000 -f"
  else
    echo "!!  systemd (--user) nicht verfuegbar; Dienstdatei liegt unter $UNIT_DIR/hornet3000.service bereit."
  fi
fi

echo "==> Selbsttest"
"$TARGET/python/bin/python3" -I "$TARGET/app/hornet_run.py" selftest || true

TOKEN=$(grep '^ACCESS_TOKEN=' "$TARGET/app/.env" 2>/dev/null | cut -d= -f2-)
PORT=$(grep '^PORT=' "$TARGET/app/.env" 2>/dev/null | cut -d= -f2-); PORT=${PORT:-8080}
case ":$PATH:" in *":$BIN_DIR:"*) PATH_OK=1 ;; *) PATH_OK=0 ;; esac
echo
echo "============================================================"
echo " Fertig."
echo " Starten:            hornet3000 open"
echo " Oberflaeche:        http://localhost:$PORT"
echo " Zugangsschluessel:  $TOKEN"
if [ "$PATH_OK" = "0" ]; then
  echo " Hinweis: $BIN_DIR ist nicht in PATH. Entweder neu anmelden oder direkt aufrufen:"
  echo "   $BIN_DIR/hornet3000 open"
fi
echo " Naechster Schritt:  in der App den Reiter „Einrichtung“ oeffnen (Kamera, Telegram, ...)"
echo " Neu in 1.3.1: Lizenz GPL-3.0-or-later (Datei LICENSE im Programmordner). Neu in 1.3.0: Alte Handys/Tablets als Kamera oder Alarm-Anzeige, Android-App (siehe docs/MOBIL.md)"
echo "============================================================"