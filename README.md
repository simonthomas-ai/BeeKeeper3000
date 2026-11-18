# Hornet3000 Wächter 1.3.1 – Quellcode

Überwachung von Bienenständen gegen die Asiatische Hornisse (*Vespa velutina*): Kamera → Erkennung (YOLOv8, ONNX) →
Alarm (Telegram, WhatsApp, SMS, Web-Push) → optional **Funknetz** (LoRa/MeshCore und Freenet/River) zwischen Stationen.
Nur freie Software, keine Cloud nötig. Nichts im Programm ist Attrappe; Testattrappen liegen ausschließlich in `tests/`.

* `hornet/` Programm (FastAPI, SQLite, ffmpeg) · `hornet/mesh/` Funknetz · `web/` Oberfläche · `models/` Erkennungsmodell
* `docs/FUNKNETZ.md` Einrichtung Funknetz · `docs/SICHERHEIT.md` Schutzmaßnahmen und Grenzen · `docs/PRUEFSTATUS.md` was wirklich getestet wurde
* ESP32-Kamera: eigenes Paket `Hornet3000-ESP32-Kamera-1.0.0.zip` (Firmware, Hardware- und Softwaredoku, Testbericht); Anbindung als Kamera-Quelle `http://IP:81/stream?t=SCHLÜSSEL`
* `packaging/` Bauskripte der Installer (Linux/Windows/macOS) und des Update-Pakets (setzen die entpackten 1.1.0-Laufzeiten voraus, Pfade im Skript anpassen)

## Entwicklung
```
python -m venv venv && . venv/bin/activate
pip install -r requirements.txt          # Laufzeit
pip install pytest                      # Tests
python -m pytest tests -q                 # ~30 s
python hornet_run.py selftest             # Selbsttest der Installation
python hornet_run.py run                  # starten, Oberfläche auf Port 8080
```
Echt-Tests gegen Freenet (brauchen `freenet` und `riverctl` im selben Ordner):
`HORNET_REAL_FREENET=1 HORNET_RIVERCTL=/pfad/riverctl python -m pytest tests/test_freenet_real.py`
Dauerlauf mit echtem Prozess: `python tests/stability/soak.py` · Browserprüfung: `python3 tests/browser/check_ui.py` (Playwright).

## Lizenz

Der eigene Programmcode (Wächter, Handy-Seite, Android-App, Skripte, Tests, Texte) steht unter der
**GNU General Public License, Version 3 oder neuer (GPL-3.0-or-later)**. Der Lizenztext liegt in der Datei `LICENSE`.
Jede und jeder darf die Software kostenlos nutzen, ändern und weitergeben, auch andere Imker-Initiativen, solange
Weitergaben unter denselben Bedingungen erfolgen. Die Quelltexte tragen die Kennung `SPDX-License-Identifier: GPL-3.0-or-later`,
der Urhebervermerk lautet „Hornet3000-Mitwirkende“.

Mitgelieferte Bausteine Dritter behalten ihre eigenen Lizenzen (Erkennungsmodell GPL-3.0, ffmpeg-Build GPL-3.0, Schriften SIL OFL 1.1,
Python-Bibliotheken je nach Paket); sie sind in `LICENSES.txt` im Programmordner aufgeführt.

Die Software wurde von einer künstlichen Intelligenz hergestellt (Claude, Anthropic PBC) und ohne Gewähr abgegeben,
soweit das Gesetz es zulässt. Siehe auch `docs/PRUEFSTATUS.md` für das, was wirklich getestet wurde.
