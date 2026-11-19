# Hornet3000 ESP32-Kamera 1.0.0

Eine günstige Kamera (AI-Thinker ESP32-CAM, ca. 8–12 €) für den Hornet3000-Wächter: Sie hängt am WLAN, liefert ein Bild
(`/jpg`) und einen Videostrom (`/stream`, MJPEG) und ist nur mit einem Zugangsschlüssel erreichbar. Der Wächter holt den
Strom ab, erkennt Hornissen und alarmiert wie mit jeder anderen Kamera.

**Stand: 12.11.2026 – die Firmware wurde gebaut und ihre Logik am Rechner geprüft, aber noch nie auf echter Hardware gestartet.**
Genaues Bild: `docs/TESTBERICHT.md`. Bitte lies vor dem Einsatz den Abschnitt „Erste Inbetriebnahme“ unten.

## Inhalt dieses Pakets

| Pfad | Inhalt |
|---|---|
| `firmware/firmware.factory.bin` | fertiges Flash-Abbild (Bootloader + Partitionen + Programm), ab Adresse 0x0 zu schreiben |
| `firmware/firmware.bin` | nur das Programm (Adresse 0x10000, z. B. für späteres Aktualisieren) |
| `src/`, `include/config.h`, `platformio.ini` | Quellcode der Firmware (zum selbst Bauen und Anpassen) |
| `test/native/` | Rechner-Tests der Firmware-Logik (mit Speicher-Prüfern) |
| `tools/` | Prüfwerkzeuge: Kamera-Attrappe (`emulator.py`), Rahmen-Hilfsprogramm, Übertragungstest |
| `docs/HARDWARE.md` | Einkaufsliste, Verdrahtung, Stromversorgung, Linse, Gehäuse, Montage |
| `docs/SOFTWARE.md` | Flashen, Einrichtung im Einrichtungs-WLAN, Anbindung an Hornet3000, Fehlersuche |
| `docs/SICHERHEIT.md` | was geschützt ist, was nicht, bewusste Grenzen |
| `docs/TESTBERICHT.md` | was wirklich getestet wurde und was nicht |

## In fünf Schritten

1. Hardware nach `docs/HARDWARE.md` verdrahten (Netzteil mit mindestens 2 A! Die meisten Fehler kommen von schwacher Stromversorgung).
2. `firmware.factory.bin` flashen: `esptool --chip esp32 --baud 460800 write-flash 0x0 firmware.factory.bin` (Einzelheiten in `docs/SOFTWARE.md`).
3. Kamera startet ein Einrichtungs-WLAN `Hornet3000-Cam-XXXX`; Das Passwort steht in der seriellen Konsole (115200 Baud) im Block „=== EINRICHTUNG ===“ (nach RESET) – aufschreiben und auf das Gehäuse kleben.
4. Mit dem Handy verbinden, `http://192.168.4.1/` öffnen, WLAN-Name, WLAN-Passwort und einen Zugangsschlüssel eintragen. Speichern. Die Kamera startet neu.
5. Im Hornet3000-Wächter unter Einrichtung als Kamera-Quelle `http://<IP-der-Kamera>:81/stream?t=<Zugangsschlüssel>` eintragen und „Testen“.

## Erste Inbetriebnahme (bitte so vorgehen, weil nie auf Hardware erprobt)

Die Firmware ist mit dem offiziellen Espressif-Werkzeugsatz gebaut und prüft sich zur Laufzeit selbst (Wächterhund, Neustart bei WLAN-Verlust,
Kamerafehlern und Speichermangel). Ob sie auf **deiner** Platine alles richtig macht, zeigt nur ein Probelauf:

* Erst am Schreibtisch mit USB-Seriell-Adapter und offener serieller Konsole starten, nicht gleich im Garten.
* Prüfen: Einrichtungs-WLAN erscheint, Seite lässt sich speichern, nach Neustart „WLAN verbunden“ und „Kamera bereit: 640x480“ auf der Konsole.
* `http://<IP>/status?t=<Schlüssel>` zeigt JSON; `http://<IP>/jpg?t=<Schlüssel>` liefert ein Bild; Fokus an der Linse einstellen (siehe `HARDWARE.md`).
* Danach 24 Stunden Dauerlauf mit dem Wächter beobachten (`/status`: `reboots_bad`, `cam_errors`, `free_heap`), erst dann aufhängen.

Rückmeldungen (Fehler, Messwerte) bitte mit der Ausgabe der seriellen Konsole.

## Lizenzen

Der eigene Quellcode dieses Pakets gehört zum Hornet3000-Projekt und steht wie dieses unter der **GNU General Public License, Version 3 oder
(nach Ihrer Wahl) jeder späteren Fassung** (`GPL-3.0-or-later`, Text in `LICENSE`). Sie dürfen ihn kostenlos nutzen, ändern und weitergeben.

Beim Bauen lädt PlatformIO: Arduino-ESP32 (LGPL 2.1), ESP-IDF (Apache 2.0), esp32-camera (Apache 2.0). Diese Bestandteile behalten ihre
eigenen Lizenzen. Das mitgelieferte Flash-Abbild enthält sie; der Quellcode der Firmware liegt bei und lässt sich mit `pio run` neu bauen.
Ob die Lizenzen im fertigen Flash-Abbild juristisch lückenlos zusammenpassen, ist nicht von einer Juristin oder einem Juristen geprüft.
