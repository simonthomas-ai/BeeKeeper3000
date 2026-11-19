# Software

## Flashen (fertiges Abbild)

Voraussetzung: Python und `esptool` (`pip install esptool`), Verdrahtung und IO0-Brücke wie in `HARDWARE.md`.

```
esptool --chip esp32 --port /dev/ttyUSB0 --baud 460800 write-flash 0x0 firmware/firmware.factory.bin
```
(Ältere esptool-Fassungen schreiben `write_flash`; Windows: `--port COM5`.) Danach IO0-Brücke entfernen, RESET drücken.
Das Abbild ist für 4 MB Flash mit der Partitionstabelle `huge_app` gebaut (ein großer Programmbereich, **keine** Funkaktualisierung/OTA).
Der Bau ergab: RAM 18,4 %, Flash 34,2 % belegt.

## Selbst bauen (PlatformIO)

```
pip install platformio
cd esp32-kamera
pio run                     # erzeugt .pio/build/esp32cam/firmware.bin und firmware.factory.bin
pio run -t upload           # flasht direkt (IO0 gegen GND beim Anstecken)
pio device monitor          # serielle Konsole, 115200 Baud
```
Die Plattform (pioarduino 55.03.312, Arduino-ESP32 3.3.12) ist in `platformio.ini` fest eingetragen, damit der Bau wiederholbar bleibt.
Einstellungen zur Übersetzungszeit stehen in `include/config.h` (Bildgröße, Qualität, Bildrate, Drehen/Spiegeln, Zeitgrenzen, Schutz vor Fehlversuchen).
**Keine** Zugangsdaten in `config.h` eintragen; WLAN und Schlüssel werden im Einrichtungs-WLAN gesetzt.

## Einrichtung der Kamera (Einrichtungs-WLAN)

Beim ersten Start (oder nach Werkseinstellung, oder wenn das gespeicherte WLAN dreimal in Folge nicht erreichbar war) öffnet die Kamera ein WLAN
`Hornet3000-Cam-XXXX` (XXXX = Ende der MAC-Adresse) mit WPA2.

* Das **Passwort** wird beim ersten Mal zufällig erzeugt, im Flash gespeichert und in der seriellen Konsole angezeigt (Block `=== EINRICHTUNG ===`).
  Es bleibt gleich, bis eine Werkseinstellung gemacht wird. Gleich aufschreiben (z. B. auf das Gehäuse kleben).
  Wer ein festes eigenes Passwort will, trägt es vor dem Bau in `config.h` bei `AP_PASSWORD` ein (8–63 Zeichen).
* Mit dem Handy verbinden, `http://192.168.4.1/` öffnen. Eintragen:
  * WLAN-Name und -Passwort deines Heim-/Stall-WLANs (2,4 GHz),
  * **Zugangsschlüssel** (16–64 Zeichen aus `A–Z a–z 0–9 - _`); die Seite schlägt einen zufälligen vor,
  * Name im Netz (optional).
* „Speichern und neu starten“. Das Einrichtungs-WLAN schließt sich, die Kamera verbindet sich mit deinem WLAN.
* Ist die Kamera schon eingerichtet, schließt sich das Einrichtungs-WLAN 10 Minuten nach dem Start von selbst (Neustart, neuer Versuch mit den gespeicherten Daten). Eine noch nie eingerichtete Kamera bleibt im Einrichtungsmodus.

Der Wächter braucht die **IP-Adresse** der Kamera. Sie steht in der seriellen Konsole („WLAN verbunden, IP …“) und in der Geräteliste des Routers.
**Empfehlung:** im Router eine feste Zuteilung (DHCP-Reservierung) für die Kamera einrichten. Der Name `hornet-cam-xxxx.local` (mDNS) funktioniert nur,
wenn das Betriebssystem des Wächter-Rechners ihn auflösen kann; das ist nicht überall der Fall.

## Anschluss an Hornet3000

Im Wächter unter **Einrichtung → Kamera** als Kamera-Quelle eintragen:

```
http://192.168.1.50:81/stream?t=DEIN_ZUGANGSSCHLÜSSEL
```
und „Testen“. Der Wächter liest den Strom mit ffmpeg wie bei jeder Netzwerkkamera. Hinweise:

* Der Schlüssel steht in der Adresse und damit in der Einstellungsdatei des Wächters (`.env`, nur für den Besitzer lesbar).
  Ab Hornet3000 1.2.0 (Stand 12.11.2026) wird er in Fehlermeldungen, im Status und in Telegram-Statusantworten **geschwärzt**
  (beim Test mit der ESP32-Attrappe entdeckt und behoben). Ältere Fassungen zeigen die Adresse in Fehlertexten – bitte aktualisieren.
* Die Kamera liefert **nur einen Zuschauer** gleichzeitig. Während der Wächter verbunden ist, bekommt ein zweiter Abruf von `/stream` die Antwort 503.
  Einzelbilder (`/jpg`) sind davon unabhängig, auf echter Hardware parallel zum Strom aber **nicht erprobt**.
* Ton: der ESP32-CAM hat kein Mikrofon; es gibt keinen Ton. Clips haben nur Bild.
* Bildgröße VGA (640×480), bis zu 8 Bilder je Sekunde. Der Wächter verkleinert/untertastet selbst nach seinen Einstellungen.

## Adressen der Kamera

| Adresse | Zweck | Schlüssel nötig |
|---|---|---|
| `http://IP/` | Namensschild und Version | nein |
| `http://IP/status?t=…` | JSON: Version, Laufzeit, WLAN-Stärke, freier Speicher, Bilder, Fehler, ungewollte Neustarts | ja |
| `http://IP/jpg?t=…` | ein aktuelles Bild | ja |
| `http://IP:81/stream?t=…` | MJPEG-Strom (Mehrteil, Grenze `h3kframe`) | ja |
| `POST http://IP/reboot` | Neustart | ja |
| `POST http://IP/factory-reset` | Werkseinstellung (löscht WLAN, Schlüssel, Einrichtungs-Passwort), startet das Einrichtungs-WLAN | ja |

Der Schlüssel kann statt als `?t=…` auch im Kopf `X-Token` übergeben werden (nützlich für Skripte; er steht dann nicht in Protokollen).

## Fehlersuche

| Beobachtung | Wahrscheinliche Ursache / Abhilfe |
|---|---|
| Neustarts, „Brownout detector“ in der Konsole | Stromversorgung zu schwach: besseres Netzteil, kürzeres/dickeres Kabel, Kondensator, 5 V am Modul messen |
| Beim Flashen „Failed to connect“ | IO0 nicht mit GND verbunden beim Reset; TX/RX vertauscht; Adapter auf 5 V statt 3,3 V Pegel |
| Nach dem Flashen Dauerschleife „waiting for download“ | IO0-Brücke noch drin → entfernen, RESET |
| „Kamera-Start fehlgeschlagen“ | Flachbandkabel der Kamera nicht richtig eingerastet (Verriegelung), Modul ohne PSRAM/anderes Pinout, Stromproblem |
| Bild nur 320×240 | Modul ohne (erkannten) PSRAM: Firmware wählt dann bewusst das kleine Bild |
| Einrichtungs-WLAN nicht sichtbar | Konsole prüfen; ggf. `factory-reset` oder Flash komplett löschen (`esptool erase-flash`) und neu schreiben |
| Wächter meldet „401 Unauthorized“ | Schlüssel in der Adresse falsch. **5 falsche Versuche in 60 s sperren die Kamera für 60 s (auch für den richtigen Schlüssel)** |
| Wächter meldet „503“ | schon ein Zuschauer verbunden (z. B. Browser-Tab mit `/stream`) |
| Strom bricht oft ab / Bild ruckelt | WLAN-Empfang schwach (`/status` → `rssi`, besser als −75 dBm), anderen Standort/Antenne, Bildrate/Qualität in `config.h` senken |
| `reboots_bad` steigt | ungewollte Neustarts (Absturz, Wächterhund, Unterspannung): Konsole mitlesen |
