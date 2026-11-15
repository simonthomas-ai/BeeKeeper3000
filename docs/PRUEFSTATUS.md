# Prüfstatus Hornet3000 1.3.0 (Stand 14.11.2026)

Diese Seite sagt ehrlich, **was wirklich ausgeführt wurde** und was nicht. „Attrappe“ bedeutet: ein Testwerkzeug ersetzt
das fehlende Gerät; die Attrappen liegen nur in `tests/` (Quellcode-Paket) und sind nie Teil des Programms.

## 1. Was getestet wurde

| Prüfung | Wie | Ergebnis |
|---|---|---|
| Automatische Tests, Entwicklungsumgebung (Python 3.13) | 275 Tests: Funkformat, Flusskontrolle, Dienst, LoRa-Anbindung gegen Geräte-Attrappe, Sicherheit, Server-Schnittstellen, Alarm→Funknetz, Schwärzung von Kamera-Zugangsdaten, **Station und Handy-Schnittstelle (31)** | 270 bestanden, 5 übersprungen (siehe Zeile Freenet) |
| Dieselben Tests mit dem **mitgelieferten** Python 3.12 und genau den Bibliotheken des Pakets | wie oben | 269 bestanden, 6 übersprungen (die 5 Freenet-Echttests und der Abgleich mit der offiziellen MeshCore-Bibliothek, die nicht im Paket steckt) |
| Freenet/River **echt** | echter Freenet-Knoten 0.2.154 und echtes `riverctl` 0.2.24, lokal auf dem Testrechner (kein Anschluss an das offene Freenet-Netz): Nachricht zwischen zwei Stationen, Alarm → Weiterleitung → Quittung, Fremdtext/Müll im Raum, Neustart nach abgeschossenem `riverctl`, Knoten nicht erreichbar | 5 von 5 bestanden |
| LoRa/MeshCore | eigene Anbindung gegen eine **Geräte-Attrappe** (Pseudo-Terminal), Rahmenformat zusätzlich gegen die Leseroutine und Befehle der offiziellen Python-Bibliothek `meshcore` 2.3.17 abgeglichen (dabei wurde ein Antwortcode der Attrappe korrigiert) | bestanden – **an echter Funkhardware nicht getestet** |
| Echter Browser (Chromium, Playwright) | alle Reiter inkl. Funknetz, Handy-Seite (alt), keine Verstöße gegen die Inhaltsrichtlinie, Angriff von fremder Webseite (Cross-Site-Anfrage mit Cookie) wird abgewiesen, Eingabeprüfung der Einrichtung; auch gegen die **installierte** Linux-Fassung | 25 Prüfungen bestanden |
| **Handy-Seite `/m` im echten Browser** (Chromium mit iPhone-9-Kennung, 320 px Breite, Testkamera TESTATTRAPPE) | Anmeldung, Station sendet Bilder an den echten Wächter, Erkennung wertet sie aus, Foto-Auswertung, Alarm mit Ton, Stumm, App-Download, keine Inhaltsrichtlinien-Verstöße; zweiter Durchgang mit **entfernten** modernen Browserfunktionen (fetch, Promise, classList …) als Nachbildung alter Browser | 37 Prüfungen bestanden. Echte alte iPhones/Android-Browser: nicht geprüft |
| **Android-App, Netzwerk- und Ablaufteil** (`android/test`, `tests/android/run_protocol.py`) | dieselben Java-Quelldateien wie in der APK, in der JVM **gegen den echten Wächter** (HTTP und HTTPS mit Fingerabdruck, eigener Prozess): Eingabeprüfung, JSON, falscher Schlüssel, 409/429/413/415, Ausfall und Wiederkehr (TCP-Zwischenstück als Attrappe), Stationswechsel, Testalarm, Stumm, Bild der Meldung; absichtlich schlechter Mini-Server (Weiterleitung, übergroße/kaputte Antwort) | 104 Prüfungen bestanden |
| **Android-App, Bau und Aufbau** | Übersetzung gegen die Systembibliotheken von Android 2.2/2.3/4.0/4.1 (jede zu neue Funktion wäre ein Fehler), Dex-Umsetzung, `aapt dump badging` (Mindestversion 8, Ziel 28, Berechtigungen Internet/Kamera/Vibration), `apksigner verify` (v1, v2, v3), `zipalign` | bestanden |
| Dauerlauf mit dem **echten Programm als eigenem Prozess** (echte Erkennung, ffmpeg-Testquelle, SQLite) | 8 Start/Stopp-Zyklen (abwechselnd sauber beenden und `kill -9`), danach Datenbankprüfung; Flut von 3000 gültigen und ungültigen Funkmeldungen von 60 „Stationen“ plus Leitungsstörungen bei laufender Bedienung; 3 Minuten Dauerverkehr | bestanden: Datenbank nach jedem Abschuss in Ordnung, kein Kindprozess (ffmpeg) bleibt übrig, Bedienung antwortet in höchstens 0,01 s, Speicher/Dateihandles/Threads konstant (337 MB / 18 / 13), Testalarm nach der Flut funktioniert |
| Dauerlauf **Phase D: Station unter Beschuss** (neu) | eine ehrliche Station sendet 90 s lang Bilder, während sechs Störer gleichzeitig Müll, übergroße Bilder, gültige Bilder einer Fremdstation, Abfragen und Foto-Auswertungen fluten; danach 25 falsche Schlüssel | bestanden (gegen die Linux-Fassung mit mitgelieferten Bibliotheken): alle 226 Bilder der ehrlichen Station kamen an (Takt 2,5 Bilder/s), Programm blieb oben, Oberfläche antwortete in höchstens 0,03 s, Speicher/Dateihandles/Threads blieben nach dem Anlauf konstant (411 MB / 18 / 5), Störer wurden abgewiesen (u. a. 22 459× 409, 11 107× 400, 5 174× 413); nach 10 falschen Schlüsseln Sperre mit 429, Datenbank in Ordnung |
| Dasselbe gegen den **installierten** Linux-Installer | 6 Zyklen, 3000er Flut, 2 Minuten | bestanden, gleiche Werte |
| Linux-Installer | in leerem Benutzerverzeichnis installiert: Selbsttest, Start, Anmeldung, Dateirechte (`.env` 0600, Datenordner 0700), Sicherheits-Kopfzeilen, Aktualisierung | bestanden |
| Update-Paket | an **echten Installationen von 1.1.0 und 1.2.0** (laufend, mit Alarm und eigener `.env`): Erfolgsweg, Einstellungen und Alarm erhalten, zweiter Aufruf „schon aktuell“, Paket mit Programmfehler → automatischer Rückfall auf 1.1.0, beschädigtes Paket → Abbruch ohne Änderung, falsches Python → abgelehnt, nur prüfen | bestanden |
| Statische Analyse `bandit` | gesamter Programmcode | 0 hoch, 0 mittel; 46 niedrig, alle geprüft: Aufrufe von ffmpeg/riverctl mit fester Argumentliste ohne Shell, bewusst stille `except`-Zweige, Schlüsselnamen der Einrichtung (Fehlalarme) |
| Bibliotheken auf bekannte Schwachstellen (`pip-audit`) | alle mitgelieferten Pakete je Plattform | Stand 15.11.2026: Linux, Windows, macOS arm64: keine bekannten Schwachstellen (beim letzten Durchlauf fiel `opentelemetry-api` 1.45.1 mit einer neuen Meldung auf – Zeitaufwand bei manipulierten `traceparent`-Kopfzeilen, von Hornet3000 nicht erreichbar –; Pakete mit 1.45.2 neu gebaut). **macOS Intel:** `cryptography` 48.0.1 hat drei gemeldete Schwachstellen; für diese Plattform gibt es keine neuere Fassung (geprüft). Sie liegen in Funktionen, die Hornet3000 nicht verwendet (nur Web-Push-Verschlüsselung) |
| ESP32-Kamera (separates Paket) | Übertragung der Kamera-Attrappe gegen **diesen** Server als eigenen Prozess: Bilder, Wiederverbindung, falscher Schlüssel, Schlüssel-Leck-Suche (Details im Testbericht des ESP32-Pakets) | bestanden; dabei wurde der Fehler aus Abschnitt 4 (Kamera-Zugangsdaten in Fehlertexten) gefunden |
| Paket-Hygiene | keine `.env`, Datenbanken, Schlüssel, Zugangsdaten oder Entwicklerpfade in den Paketen; keine weltweit schreibbaren Dateien | bestanden |

## 2. Was NICHT getestet wurde

* **LoRa an echter Funkhardware.** Weder Reichweite noch Sendezeit-Verhalten noch das Zusammenspiel mit echter
  MeshCore-Firmware sind erprobt. Die Sendezeit-Begrenzung (Standard 1 %) ist nach der Semtech-Formel berechnet, aber nicht gemessen.
* **Freenet im offenen Netz.** Getestet wurde ein lokaler Knoten. Freenet ist noch Alpha-Software; Verbindungszeiten im offenen Netz sind unbekannt.
* **Die Android-App wurde nie auf einem Gerät oder Emulator ausgeführt.** Kamera-Vorschau, Bildschirme, Ton, Vibration und das
  Verhalten auf einzelnen Geräten sind nur gebaut und gelesen. Dass sie „ab Android 2.2“ läuft, folgt aus dem Bau gegen die
  Systembibliothek von Android 2.2 und dem Manifest – es ist **berechnet, nicht erprobt**. Besonders unsicher: Kamera-Treiber
  sehr alter Geräte (Vorschaugrößen, NV21), TLS 1.2 auf Android 4.1 – 4.4, das Verhalten beim Sperren des Bildschirms.
* **Alte iPhones und alte Android-Browser** wurden nur im modernen Chromium nachgebildet (moderne Funktionen entfernt, iPhone-Kennung).
  Echtes iOS 9/10, Safari-Eigenheiten (Ton erst nach Berührung, Kamera erst ab iOS 11) beruhen auf Herstellerangaben.
* **Eine iPhone-App gibt es nicht** (Mac, Xcode und Apple-Entwicklerkonto nötig); iPhones nutzen die Handy-Seite.
* **Windows und macOS wurden nie ausgeführt** (kein Windows-/Mac-Rechner verfügbar). Windows-Installer (NSIS) und macOS-Zips sind gebaut und
  strukturell geprüft (Inhalt, Versionen, Signaturen). Das Update-Skript ist plattformunabhängig geschrieben, lief aber nur unter Linux.
* **Eine ernsthafte Penetrationsprüfung durch Dritte hat es nicht gegeben.** „Bulletproof“ im Sinne von „nicht angreifbar“
  kann niemand ehrlich versprechen; geprüft wurden die bekannten Angriffswege (siehe `SICHERHEIT.md`).

## 3. Bewusste Grenzen (keine Fehler)

* Die Station (Altgerät) arbeitet nur im **Vordergrund** und mit eingeschaltetem Bildschirm; es gibt keinen Hintergrunddienst und keine
  Benachrichtigung bei geschlossener App. Das Bild wird nicht gedreht. Es ist immer nur eine Station aktiv.
* Nach 10 falschen Bearer-Schlüsseln in 10 Minuten antwortet der Wächter dieser Adresse mit 429 – auch auf richtige Schlüssel von derselben Adresse.

* Wer den Kanalschlüssel bzw. den River-Raum kennt, kann Meldungen im Namen jeder Station senden oder Alarme unterdrücken.
  Schlüssel nur an vertraute Imker geben, bei Missbrauch wechseln.
* Bei einer Flut von Funkmeldungen nimmt das Programm nur wenige an (im Dauertest 13–16 von 3000 neuen Absendern) – das ist der Schutz,
  nicht ein Fehler. Ein echtes LoRa-Netz liefert ohnehin nur wenige Nachrichten pro Minute.
* Standardmäßig lauscht die Oberfläche im Heimnetz (HOST=0.0.0.0), geschützt nur durch den Zugangsschlüssel. Nicht ohne HTTPS ins Internet stellen.
* Nach einer Leitungsstörung zwischen Rechner und Funkgerät baut das Programm die Verbindung selbst neu auf; das kann bis zu etwa 6 Sekunden dauern.

## 4. Beim Testen gefundene und behobene Fehler (Auswahl)

* Handy-Seite: Ein Anmelde-Link `/m#k=…` reagierte nicht, wenn die Seite schon geladen war (nur die Adresse nach dem `#` änderte sich) → auf `hashchange` reagiert (Browsertest).
* Handy-Seite: Nach der ersten Abfrage zeigte die Meldungsliste nur noch die neuesten Meldungen, weil der Server nur Neueres liefert → Liste wird zusammengeführt (Browsertest).
* Android-App: Ein Bild über 1 MiB hätte der Wächter mitten im Senden abgebrochen; es wäre als Netzwerkfehler erschienen → wird lokal als „zu groß“ erkannt, die nächste Aufnahme stärker komprimiert.
* Android-App: Der Schlüsselspeicher-Aufruf des Bauskripts las das Passwort zweimal aus derselben Datei → Passwort über die Umgebung übergeben (beim ersten Bauversuch aufgefallen).

* Ungültiger Port (z. B. 99999) für den Freenet-Knoten wurde in der Einrichtung akzeptiert → Bereichsprüfung.
* Textbereinigung war nach dem Kürzen nicht stabil (zweite Bereinigung änderte das Ergebnis) → Bereinigung idempotent gemacht, getestet.
* Eine Störung auf der Funkleitung konnte die Antwort auf einen Befehl verschlucken → Parser setzt zurück, wiederholt, leert den Eingang.
* Die Handy-Seite verletzte die neue Inhaltsrichtlinie (Inline-Stil) → in eine Datei ausgelagert (vom Browsertest gefunden).
* `PUT /api/setup` mit `values: []` wurde angenommen → streng geprüft (400).
* River lehnte Nachrichten über 3000 Zeichen ab → Länge vorab begrenzt.
* Eigene Funkgeräte-Attrappe antwortete mit falschem Code → am offiziellen Quellcode der MeshCore-Bibliothek korrigiert.
* **Kamera-Zugangsdaten in Fehlertexten:** ffmpeg gibt bei Verbindungsfehlern die ganze Adresse aus. Dadurch standen `?t=Schlüssel` (ESP32-Kamera) bzw. `Benutzer:Passwort@` (RTSP-Kameras) im Kamera-Status der Oberfläche, in der Telegram-Statusantwort und im Einrichtungstest. Jetzt werden Zugangsdaten in Adressen, alles hinter „?“ und die geheimen Teile der eingerichteten Quelle geschwärzt (12 Tests, Leck-Suche im Übertragungstest). Gefunden beim Test mit der ESP32-Kamera-Attrappe.

## 5. Inbetriebnahme-Test für LoRa (bitte einmal durchführen)

1. Zwei Stationen mit je einem MeshCore-Funkgerät (868 MHz, Companion-Firmware, USB). Auf beiden denselben Kanalnamen und Kanalschlüssel eintragen (Einrichtung → Funknetz), Kanal 1–7 (nicht 0).
2. Reiter „Funknetz“: Zustand „verbunden“ bei beiden? Bei Problemen steht der Grund dort.
3. „Testsendung“ auf Station A → erscheint im Protokoll von Station B als „Test“, und A zeigt eine Quittung.
4. Entfernung/Hindernisse schrittweise erhöhen, Quittungsquote notieren.
5. Erst danach „Weiterleiten bei Sichtung“ scharf lassen. Ergebnis gern zurückmelden – damit wird dieser Prüfstatus ehrlich ergänzt.
