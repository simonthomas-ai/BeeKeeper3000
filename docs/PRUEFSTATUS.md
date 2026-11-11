# Prüfstatus Hornet3000 1.2.0 (Stand 11.11.2026)

Diese Seite sagt ehrlich, **was wirklich ausgeführt wurde** und was nicht. „Attrappe“ bedeutet: ein Testwerkzeug ersetzt
das fehlende Gerät; die Attrappen liegen nur in `tests/` (Quellcode-Paket) und sind nie Teil des Programms.

## 1. Was getestet wurde

| Prüfung | Wie | Ergebnis |
|---|---|---|
| Automatische Tests, Entwicklungsumgebung (Python 3.13) | 229 Tests: Funkformat, Flusskontrolle, Dienst, LoRa-Anbindung gegen Geräte-Attrappe, Sicherheit, Server-Schnittstellen, Alarm→Funknetz | 224 bestanden, 5 übersprungen (siehe Zeile Freenet) |
| Dieselben Tests mit dem **mitgelieferten** Python 3.12 und genau den Bibliotheken des Pakets | wie oben | 223 bestanden, 6 übersprungen (die 5 Freenet-Echttests und der Abgleich mit der offiziellen MeshCore-Bibliothek, die nicht im Paket steckt) |
| Freenet/River **echt** | echter Freenet-Knoten 0.2.154 und echtes `riverctl` 0.2.24, lokal auf dem Testrechner (kein Anschluss an das offene Freenet-Netz): Nachricht zwischen zwei Stationen, Alarm → Weiterleitung → Quittung, Fremdtext/Müll im Raum, Neustart nach abgeschossenem `riverctl`, Knoten nicht erreichbar | 5 von 5 bestanden |
| LoRa/MeshCore | eigene Anbindung gegen eine **Geräte-Attrappe** (Pseudo-Terminal), Rahmenformat zusätzlich gegen die Leseroutine und Befehle der offiziellen Python-Bibliothek `meshcore` 2.3.17 abgeglichen (dabei wurde ein Antwortcode der Attrappe korrigiert) | bestanden – **an echter Funkhardware nicht getestet** |
| Echter Browser (Chromium, Playwright) | alle Reiter inkl. Funknetz, Handy-Seite, keine Verstöße gegen die Inhaltsrichtlinie, Angriff von fremder Webseite (Cross-Site-Anfrage mit Cookie) wird abgewiesen, Eingabeprüfung der Einrichtung; auch gegen die **installierte** Linux-Fassung | 25 Prüfungen bestanden |
| Dauerlauf mit dem **echten Programm als eigenem Prozess** (echte Erkennung, ffmpeg-Testquelle, SQLite) | 8 Start/Stopp-Zyklen (abwechselnd sauber beenden und `kill -9`), danach Datenbankprüfung; Flut von 3000 gültigen und ungültigen Funkmeldungen von 60 „Stationen“ plus Leitungsstörungen bei laufender Bedienung; 3 Minuten Dauerverkehr | bestanden: Datenbank nach jedem Abschuss in Ordnung, kein Kindprozess (ffmpeg) bleibt übrig, Bedienung antwortet in höchstens 0,01 s, Speicher/Dateihandles/Threads konstant (337 MB / 18 / 13), Testalarm nach der Flut funktioniert |
| Dasselbe gegen den **installierten** Linux-Installer | 6 Zyklen, 3000er Flut, 2 Minuten | bestanden, gleiche Werte |
| Linux-Installer | in leerem Benutzerverzeichnis installiert: Selbsttest, Start, Anmeldung, Dateirechte (`.env` 0600, Datenordner 0700), Sicherheits-Kopfzeilen, Aktualisierung | bestanden |
| Update-Paket | an einer **echten 1.1.0-Installation** (laufend, mit Alarm und eigener `.env`): Erfolgsweg, Einstellungen und Alarm erhalten, zweiter Aufruf „schon aktuell“, Paket mit Programmfehler → automatischer Rückfall auf 1.1.0, beschädigtes Paket → Abbruch ohne Änderung, falsches Python → abgelehnt, nur prüfen | bestanden |
| Statische Analyse `bandit` | gesamter Programmcode | 0 hoch, 0 mittel; 44 niedrig, alle geprüft: Aufrufe von ffmpeg/riverctl mit fester Argumentliste ohne Shell, bewusst stille `except`-Zweige, Schlüsselnamen der Einrichtung (Fehlalarme) |
| Bibliotheken auf bekannte Schwachstellen (`pip-audit`) | alle mitgelieferten Pakete je Plattform | Linux, Windows, macOS arm64: keine bekannten Schwachstellen. **macOS Intel:** `cryptography` 48.0.1 hat drei gemeldete Schwachstellen; für diese Plattform gibt es keine neuere Fassung (geprüft). Sie liegen in Funktionen, die Hornet3000 nicht verwendet (nur Web-Push-Verschlüsselung) |
| Paket-Hygiene | keine `.env`, Datenbanken, Schlüssel, Zugangsdaten oder Entwicklerpfade in den Paketen; keine weltweit schreibbaren Dateien | bestanden |

## 2. Was NICHT getestet wurde

* **LoRa an echter Funkhardware.** Weder Reichweite noch Sendezeit-Verhalten noch das Zusammenspiel mit echter
  MeshCore-Firmware sind erprobt. Die Sendezeit-Begrenzung (Standard 1 %) ist nach der Semtech-Formel berechnet, aber nicht gemessen.
* **Freenet im offenen Netz.** Getestet wurde ein lokaler Knoten. Freenet ist noch Alpha-Software; Verbindungszeiten im offenen Netz sind unbekannt.
* **Windows und macOS wurden nie ausgeführt** (kein Windows-/Mac-Rechner verfügbar). Windows-Installer (NSIS) und macOS-Zips sind gebaut und
  strukturell geprüft (Inhalt, Versionen, Signaturen). Das Update-Skript ist plattformunabhängig geschrieben, lief aber nur unter Linux.
* **Eine ernsthafte Penetrationsprüfung durch Dritte hat es nicht gegeben.** „Bulletproof“ im Sinne von „nicht angreifbar“
  kann niemand ehrlich versprechen; geprüft wurden die bekannten Angriffswege (siehe `SICHERHEIT.md`).

## 3. Bewusste Grenzen (keine Fehler)

* Wer den Kanalschlüssel bzw. den River-Raum kennt, kann Meldungen im Namen jeder Station senden oder Alarme unterdrücken.
  Schlüssel nur an vertraute Imker geben, bei Missbrauch wechseln.
* Bei einer Flut von Funkmeldungen nimmt das Programm nur wenige an (im Dauertest 13–16 von 3000 neuen Absendern) – das ist der Schutz,
  nicht ein Fehler. Ein echtes LoRa-Netz liefert ohnehin nur wenige Nachrichten pro Minute.
* Standardmäßig lauscht die Oberfläche im Heimnetz (HOST=0.0.0.0), geschützt nur durch den Zugangsschlüssel. Nicht ohne HTTPS ins Internet stellen.
* Nach einer Leitungsstörung zwischen Rechner und Funkgerät baut das Programm die Verbindung selbst neu auf; das kann bis zu etwa 6 Sekunden dauern.

## 4. Beim Testen gefundene und behobene Fehler (Auswahl)

* Ungültiger Port (z. B. 99999) für den Freenet-Knoten wurde in der Einrichtung akzeptiert → Bereichsprüfung.
* Textbereinigung war nach dem Kürzen nicht stabil (zweite Bereinigung änderte das Ergebnis) → Bereinigung idempotent gemacht, getestet.
* Eine Störung auf der Funkleitung konnte die Antwort auf einen Befehl verschlucken → Parser setzt zurück, wiederholt, leert den Eingang.
* Die Handy-Seite verletzte die neue Inhaltsrichtlinie (Inline-Stil) → in eine Datei ausgelagert (vom Browsertest gefunden).
* `PUT /api/setup` mit `values: []` wurde angenommen → streng geprüft (400).
* River lehnte Nachrichten über 3000 Zeichen ab → Länge vorab begrenzt.
* Eigene Funkgeräte-Attrappe antwortete mit falschem Code → am offiziellen Quellcode der MeshCore-Bibliothek korrigiert.

## 5. Inbetriebnahme-Test für LoRa (bitte einmal durchführen)

1. Zwei Stationen mit je einem MeshCore-Funkgerät (868 MHz, Companion-Firmware, USB). Auf beiden denselben Kanalnamen und Kanalschlüssel eintragen (Einrichtung → Funknetz), Kanal 1–7 (nicht 0).
2. Reiter „Funknetz“: Zustand „verbunden“ bei beiden? Bei Problemen steht der Grund dort.
3. „Testsendung“ auf Station A → erscheint im Protokoll von Station B als „Test“, und A zeigt eine Quittung.
4. Entfernung/Hindernisse schrittweise erhöhen, Quittungsquote notieren.
5. Erst danach „Weiterleiten bei Sichtung“ scharf lassen. Ergebnis gern zurückmelden – damit wird dieser Prüfstatus ehrlich ergänzt.
