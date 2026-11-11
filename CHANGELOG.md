# Änderungen

## 1.2.0 (11.11.2026)
**Neu**
* Funknetz zwischen Stationen bei bestätigter Sichtung: LoRa/MeshCore (868 MHz, USB-Funkgerät) und/oder Freenet/River (privater, verschlüsselter Chatraum). Ab Werk aus.
  Textformat `H3K1`, strenge Prüfung und Begrenzung aller Funkmeldungen, Quittungen, Duplikaterkennung, Sendezeitgrenze (EU868), Reiter „Funknetz“, Einrichtung, Selbsttest.
* Update-Paket für vorhandene 1.0/1.1-Installationen mit Sicherung und automatischem Rückfall.
**Sicherheit**
* Schutz vor Angriffen aus dem Browser (Herkunftsprüfung für schreibende Anfragen und WebSocket, Sec-Fetch-Site), strenge Inhaltsrichtlinie und Sicherheits-Kopfzeilen, begrenzte Anfragegrößen.
* Zeitkonstante Vergleiche, signierte und ablaufende Freigabelinks, Begrenzung falscher Anmeldungen je Adresse, Einstellungsdatei nur für den Besitzer lesbar (0600), Datenordner 0700.
* Strenge Prüfung aller Eingaben der Einrichtung (Typen, Bereiche, Muster), Schutz vor SQL-Spaltennamen-Einschleusung durch Erlaubnislisten.
**Sonstiges**
* Bibliotheken: Pillow 13.0.0, certifi 2026.10.23; neu pyserial 3.5.
* Behoben: siehe `PRUEFSTATUS.md`, Abschnitt 4.

## 1.1.0
* Handy als Kamera, Installer für Linux/Windows/macOS (Intel und Apple Silicon).
