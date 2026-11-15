# Änderungen

## 1.3.0 (14.11.2026)
**Neu: alte Handys und Tablets nutzen** (Anleitung und ehrliche Prüfübersicht: `docs/MOBIL.md`)
* **Android-App „Hornet3000 Station“** (laut Manifest ab Android 2.2): Kamera-Betrieb (Einzelbilder per HTTP), Alarm-Anzeige
  (Ton, Vibration, Bild), Stumm/Testalarm, mehrere Kameras wählbar, https mit Zertifikat-Fingerabdruck. Gebaut ohne Gradle
  (`android/`, Skript `build.sh`), signiert (v1+v2+v3), rund 95 KB. Der Wächter liefert die App nach Anmeldung zum Herunterladen aus
  (Seite `/m`, Link „Android-App laden“).
* **Handy-Seite `/m`** für alte iPhones (ab iOS 9) und Android-Browser: Alarm-Anzeige, Foto auswerten lassen, Kamera-Betrieb
  (iPhone ab iOS 11 mit https). Reines ES5.
* **Kamera-Quelle „push“**: Ein Altgerät schickt JPEG-Bilder an `POST /api/station/frame`; Clips entstehen aus den Einzelbildern.
  Neue Schnittstellen: `/api/station/config`, `/api/station/frame`, `/api/mobile/poll`, `/api/mobile/check`.
* Einrichtung: Knopf „Altgerät als Station verwenden („push“)“.
**Sicherheit**
* Bildeingang mit Kopfprüfung vor dem Dekodieren (Größe, Maße, Format), 5 Bilder/s, eine aktive Station, Begrenzung der Puffer,
  Sperre nach falschen Bearer-Schlüsseln. Einzelheiten: `docs/SICHERHEIT.md`.
**Prüfung**
* Neu: Pytest-Tests der Station (31), Browsertest der Handy-Seite (37 Prüfungen), JVM-Test der App-Logik gegen den echten Wächter
  (104 Prüfungen, `tests/android/run_protocol.py`), Phase D im Dauerlauf (Station unter Beschuss).
* Nicht geprüft: die App auf einem echten Gerät oder Emulator; alte Browser nur nachgebildet.
**Sonstiges**
* Update-Paket (`Hornet3000-1.3.0-Update.zip`) aktualisiert Installationen 1.0.x bis 1.2.x.
* Bibliothek `opentelemetry-api` 1.45.1 → 1.45.2 (Meldung CVE-2026-126360: Zeitaufwand bei manipulierten `traceparent`-Kopfzeilen; Hornet3000 liest solche Kopfzeilen nicht, trotzdem aktualisiert).

## 1.2.0 (11.11.2026)
**Neu**
* Funknetz zwischen Stationen bei bestätigter Sichtung: LoRa/MeshCore (868 MHz, USB-Funkgerät) und/oder Freenet/River (privater, verschlüsselter Chatraum). Ab Werk aus.
  Textformat `H3K1`, strenge Prüfung und Begrenzung aller Funkmeldungen, Quittungen, Duplikaterkennung, Sendezeitgrenze (EU868), Reiter „Funknetz“, Einrichtung, Selbsttest.
* Update-Paket für vorhandene 1.0/1.1-Installationen mit Sicherung und automatischem Rückfall.
**Sicherheit**
* Schutz vor Angriffen aus dem Browser (Herkunftsprüfung für schreibende Anfragen und WebSocket, Sec-Fetch-Site), strenge Inhaltsrichtlinie und Sicherheits-Kopfzeilen, begrenzte Anfragegrößen.
* Zeitkonstante Vergleiche, signierte und ablaufende Freigabelinks, Begrenzung falscher Anmeldungen je Adresse, Einstellungsdatei nur für den Besitzer lesbar (0600), Datenordner 0700.
* Strenge Prüfung aller Eingaben der Einrichtung (Typen, Bereiche, Muster), Schutz vor SQL-Spaltennamen-Einschleusung durch Erlaubnislisten.
* Zugangsdaten der Kamera-Adresse (`?t=Schlüssel`, `Benutzer:Passwort@`) erscheinen nicht mehr in Fehlertexten (Kamera-Status, Telegram-Statusantwort, Einrichtungstest). Die Pakete wurden dafür am 12.11.2026 neu gebaut (gleiche Versionsnummer, neue Prüfsummen). Wer die erste Fassung vom 11.11.2026 schon installiert hat, führt den Installer noch einmal aus (Einstellungen und Daten bleiben erhalten); das Update-Paket meldet bei gleicher Versionsnummer „schon aktuell“.
**Sonstiges**
* Bibliotheken: Pillow 13.0.0, certifi 2026.10.23; neu pyserial 3.5.
* Behoben: siehe `PRUEFSTATUS.md`, Abschnitt 4.

## 1.1.0
* Handy als Kamera, Installer für Linux/Windows/macOS (Intel und Apple Silicon).
