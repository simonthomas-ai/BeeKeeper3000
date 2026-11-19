# Testbericht ESP32-Kamera 1.0.0 (Stand 12.11.2026)

**Kurzfassung: Die Firmware wurde mit dem offiziellen Werkzeugsatz gebaut, ihre Logik am Rechner scharf geprüft und die Übertragung gegen den
echten Hornet3000-Wächter getestet – aber sie wurde noch nie auf einem ESP32 ausgeführt.** Alles, was Funk, Kamera-Sensor, Speicher und
das Zusammenspiel der Espressif-Bibliotheken betrifft, ist ungeprüft.

## Was wirklich ausgeführt wurde

| Prüfung | Wie | Ergebnis |
|---|---|---|
| **Bau der Firmware** | PlatformIO, Plattform pioarduino 55.03.312 (Arduino-ESP32 3.3.12, ESP-IDF 5.5.5), Ziel `esp32cam`, Optionen `-Wall -Wextra` | gebaut, **0 Warnungen**; RAM 18,4 % (60 144 von 327 680 Byte), Flash 34,2 % (1 074 869 von 3 145 728 Byte); `firmware.bin` 1 084 160 Byte, `firmware.factory.bin` 1 149 696 Byte |
| **Aufbau des Flash-Abbilds** | Espressifs `esptool image-info` und Adresskontrolle | Kopf ESP32, Prüfsumme und Hash **gültig**; im Gesamtabbild: Bootloader bei 0x1000, Partitionstabelle bei 0x8000, Programm bei 0x10000 (byte-gleich mit `firmware.bin`) |
| **Neubau aus dem fertigen Zip** | Zip in leeren Ordner entpackt, `pio run`, Rechner-Tests | gleiche Belegung (RAM 18,4 %, Flash 34,2 %), gleiche Größe (1 084 160 Byte); 70 Byte unterscheiden sich vom mitgelieferten Abbild (eingebettete Pfade/Zeitstempel, Prüfsumme), Prüfsumme und Hash des Neubaus gültig – der Bau ist wiederholbar, aber nicht bitgenau gleich |
| **Logik der Firmware am Rechner** (`test/native/`) | der echte Firmware-Code `core.cpp` (Schlüsselvergleich, Abfrage-Auswertung, Eingabeprüfung, Zufallspasswort, Wiederholabstände, Sperre bei Fehlversuchen, Bildrate, Status-JSON, Rahmenkopf des Stroms) mit g++, AddressSanitizer + UndefinedBehaviorSanitizer; dazu 300 000 Zufallsabfragen und 100 000 Zufallsvergleiche (Fuzz) | **660 476 Prüfungen, 0 Fehler**; Status-JSON ist gültiges JSON |
| **Übertragung gegen den echten Wächter** (`tools/integration_test.py`) | Hornet3000 1.2.0 als eigener Prozess (echtes ffmpeg, echtes Erkennungsmodell, SQLite) liest den Strom einer **Kamera-Attrappe**. Die Mehrteil-Rahmen baut der echte Firmware-Code (`part_header`), die Attrappe sendet sie wie `esp_http_server` in zwei Chunks je Bild (`Transfer-Encoding: chunked`) | Bilder fließen und werden ausgewertet (6 in 6 s bei der eingestellten Erkennungsrate), Standbild des Servers ist ein gültiges JPEG; Abriss der Übertragung nach 10 Bildern: Wächter verbindet sich **jedes Mal neu**; Attrappe aus → Kamera „offline“, Attrappe wieder an → „online“; falscher Schlüssel → 401, Kamera-Fehler sichtbar, Dienst bleibt bedienbar; **Schlüssel in keiner von 7 Quellen** (Status, Alarmliste, Funk-Ansicht, Protokoll …) gefunden |

## Bei den Prüfungen gefundene und behobene Fehler

1. **Abfrage-Auswertung (Firmware):** ungültige Prozent-Kodierung ließ einen halb dekodierten Schlüssel im Ausgabepuffer (`t=GEHEIM%zz` → abgelehnt, Puffer „GEHEIM“). Vom Fuzz-Test gefunden; jetzt wird der Puffer bei jedem Fehler geleert, der Aufrufer setzt zusätzlich zurück, Regressionstests.
2. **Einrichtungs-Passwort (Firmware):** war aus der MAC-Adresse abgeleitet, also für jeden in Reichweite berechenbar → zufälliges, gespeichertes Passwort aus dem Hardware-Zufallsgenerator (Verteilung am Rechner geprüft: alle 31 Zeichen, grob gleichverteilt).
3. **Hornet3000-Server:** die komplette Kamera-Adresse (`?t=Schlüssel`, bei RTSP-Kameras Benutzer:Passwort) stand in ffmpeg-Fehlertexten und damit in Status, Telegram-Statusantwort und Einrichtungstest → Schwärzung im Server, 12 Tests; Teil des neu gebauten Hornet3000 1.2.0.
4. Eigene Fehler der Attrappe (Prüfwerkzeug): ein „Ausfall“ trennte laufende Übertragungen nicht; Testpfad falsch. Nur im Prüfwerkzeug, nicht im Produkt.

## Was NICHT getestet wurde

* **Kein Lauf auf echter Hardware.** Weder Start, Einrichtungs-WLAN, WLAN-Anmeldung, Kamera-Initialisierung, PSRAM, Flash-Speicherung (NVS), noch mDNS wurden ausgeführt. Ein Emulator für den ESP32 stand nicht zur Verfügung.
* **`main.cpp` wurde nur übersetzt, nicht ausgeführt** (Handler, Portal, Wächterhund, Selbstheilung). Die Logik darunter ist getestet, das Zusammenspiel mit den Espressif-Bibliotheken nicht.
* **Der echte `esp_http_server`** wurde durch die Attrappe nachgebildet (gleiche Adressen, gleiche Rahmen, Chunk-Aufteilung); sein Verhalten bei langsamen Clients, Verbindungsabbruch, mehreren Zugriffen gleichzeitig, Speicherknappheit ist **ungeprüft**. Das gilt auch für `/jpg` parallel zum Strom.
* **Bildqualität und Erkennung.** Die Attrappe liefert eigene Testbilder (kein OV2640). Ob das Erkennungsmodell bei echten OV2640-Bildern in VGA Hornissen findet, ist unbekannt.
* **Dauerbetrieb, Wärme, Stromaufnahme, WLAN-Reichweite, Selbstheilung (Brownout, WLAN-Verlust)** – nichts davon gemessen.
* **Sicherheitsprüfung durch Dritte:** keine. Der Schlüssel läuft im Klartext über HTTP (siehe `SICHERHEIT.md`).
* **Ton:** nicht vorhanden (kein Mikrofon auf dem Modul).

## Prüfungen selbst wiederholen

```
# Logik am Rechner (g++ nötig)
sh test/native/run.sh

# Übertragung gegen den Wächter (Quellcode von Hornet3000 1.2.0 + Python mit dessen Bibliotheken + ffmpeg)
g++ -std=c++17 -O1 -o framer tools/framer.cpp src/core.cpp
python tools/integration_test.py --hornet-dir /pfad/zu/hornet3000-1.2.0 --framer ./framer --python /pfad/zu/python

# Firmware bauen
pio run
```
Die Attrappe `tools/emulator.py` ist ein Prüfwerkzeug (TESTATTRAPPE) und nicht für den Betrieb gedacht.

## Erste Messung auf der Hardware – was bitte zurückgemeldet werden sollte

Ausgabe der seriellen Konsole vom Start bis zum ersten Bild, `/status` nach 1 Stunde und nach 24 Stunden (`reboots_bad`, `cam_errors`, `free_heap`, `rssi`),
ein Standbild aus dem Einsatz, und ob der Wächter Hornissen darauf erkennt.
