# Beekeeper3000 – Früherkennung der Asiatischen Hornisse

Freie Software für Imkerinnen und Imker: Eine Kamera am Bienenstand erkennt die Asiatische Hornisse (*Vespa velutina*) und alarmiert früh,
damit Völker geschützt werden können. Ohne Gewinnabsicht, kostenlos, quelloffen.

**Beekeeper3000** ist der Name dieses Gesamtprojekts. Die Erkennungssoftware darin heißt im Programm, in den Installern und auf der Website
weiterhin **Hornet3000** (Ordner `hornet3000-…`); sie wurde bisher nicht umbenannt.

| Ordner | Inhalt | Einstieg |
|---|---|---|
| `hornet3000-alarm/` | Hornet3000 Wächter (Version 1.3.1): Erkennung, Alarmierung, Handy-Kamera, Android-Station, Funk-Mesh, Installer-Bau | `hornet3000-alarm/README.md` |
| `hornet3000-website/` | Baukasten für die Verteilerseite (Impressum, Datenschutz, Haftungsausschluss, Downloads), Hosting z. B. bei Firebase | `hornet3000-website/README.md` |
| `hornet3000-esp32-kamera/` | Firmware und Dokumentation für die ESP32-CAM als Kamera | `hornet3000-esp32-kamera/README.md` |

**Lizenz:** der eigene Code aller Ordner steht unter `GPL-3.0-or-later` (`LICENSE`). Mitgelieferte Drittbestandteile behalten ihre eigenen
Lizenzen (siehe `LICENSES.txt` bzw. die jeweilige README).

**Herkunft:** Programmcode und Texte wurden von einer KI (Claude, Anthropic) erstellt; die Verantwortung für die Verbreitung trägt die
Betreiberin dieser Seite, siehe Impressum der Verteilerseite. Es gilt der Haftungsausschluss der Website. Die Software ist ein Hilfsmittel und
ersetzt keine Sorgfalt am Bienenstand.

**Nicht im Repository:** fertige Installer (`.run`, `.exe`, macOS-`.zip`, `.apk`) und Signaturschlüssel. Installer werden aus dem Quellcode
gebaut (`hornet3000-alarm/packaging/`).

**Prüfstand:** was getestet ist und was nur strukturell geprüft wurde, steht ehrlich in `hornet3000-alarm/docs/PRUEFSTATUS.md`.
