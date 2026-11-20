# BEEKEEPER3000 – Ausbau- und Einsatzfahrplan

Stand: 20.11.2026

Dieses Dokument definiert die technische Reihenfolge für einen belastbaren, gemeinnützig nutzbaren Stationsverbund zur Beobachtung und fachlichen Eingrenzung von Neststandorten der Asiatischen Hornisse (*Vespa velutina*). Es ist ein Arbeits- und Abnahmedokument, keine Behauptung bereits abgeschlossener Feldvalidierung.

## Leitplanken

- Local-first, offlinefähig, herstellerneutral; keine Pflicht-Cloud und keine Pflichtkonten.
- Datenminimierung: Funk- und Verbundereignisse enthalten nur pseudonyme Stationskennung, Ereigniskennung, Zeitfenster, Messart, Qualitäts-/Konfidenzmetadaten und Signatur. Keine Fotos, Audiodaten, Zugangsdaten, Namen oder exakten Koordinaten im LoRa-Payload.
- Artbestimmung bleibt bis zur fachlichen Bestätigung ein Kandidat. Keine automatische Bekämpfungs-, Fang- oder Nestzerstörungsentscheidung.
- Nestortung ist eine Suchhypothese mit Unsicherheitsfläche, niemals eine punktgenaue Behauptung. Mindestens drei unabhängige, zeitlich passende und kalibrierte Peilstationen; Geometrie, Zeitversatz, Winkelqualität und Fehlerfortpflanzung ausweisen.
- Keine Lizenzvermischung: jedes Modell, Bild, Datenset, SDK und jede Firmware erhält eine maschinenlesbare Provenienz- und Lizenzangabe.
- Funkbetrieb nur innerhalb der jeweils geltenden Frequenz-, Sendeleistungs-, Duty-Cycle- und Geräteanforderungen. Vor bundesweitem Betrieb regulatorisch prüfen.

## Arbeitspakete und Abnahmekriterien

### P0 – Reproduzierbarer Build und Stationspaket
- Versionierte, reproduzierbare Builds für Linux x86_64/ARM64 und Windows; ESP32-Firmware separat.
- Ein Installer/Uninstaller, Konfigurationsassistent, Dienstverwaltung, Diagnosebericht, Update-/Rollback-Pfad und Offline-Installationspaket.
- Keine Secrets in Images, Logs, Konfigurationsexporten oder CI-Artefakten.
- Abnahme: Installation auf sauberer VM/Hardware, Neustart, Upgrade, Downgrade/Rollback, Deinstallation und Neuinstallation dokumentiert bestanden.

### P1 – Kamera- und Ereignispipeline
- Adapter für USB/UVC, RTSP und lokale Videodatei; explizite Kameraauswahl, Reconnect, Zeitstempel, Health-Metriken, begrenzte Puffer und Backpressure.
- Pipeline: Capture → Bewegung/ROI → Inferenz → Tracking über Frames → Qualitätsfilter → Ereignis-Outbox → authentifizierte lokale Source-API.
- RTSP-Zugangsdaten ausschließlich im lokalen Secret Store bzw. geschützten Dateisystem; niemals in URLs, Logs oder Telemetrie ausgeben.
- Ereignisse lokal puffern und idempotent zustellen; bei vollem Speicher kontrolliert stoppen/warnen statt stillschweigend Daten zu verwerfen.
- Abnahme: 24-/72-Stunden-Dauerlauf, Kamera-Neustart, Netzwerkunterbrechung, voller Datenträger, Prozessabsturz und Stromausfall simulieren.

### P2 – Erkennungsqualität und Daten-Governance
- Kein Modell ohne Herkunft, Lizenz, Hash, Architektur, Klassenmapping, Trainings-/Validierungsdatenbeschreibung und dokumentierte Nutzungsrechte.
- Getrennte Klassen mindestens: Vespa velutina, Vespa crabro, andere Wespen/Hornissen, Bienen/Hummeln und unbekannt. Unbekannt/unsicher ist ein gültiges Ergebnis.
- Train/Validation/Test strikt nach Aufnahmeort, Individuum und Zeit getrennt; keine nahezu identischen Frames über Splits.
- Metriken je Klasse: Precision, Recall, F1, PR-Kurve, Konfusionsmatrix, Fehlalarme pro Kameratag, Latenz und Kalibrierung; zusätzlich Nacht-/Regen-/Gegenlicht-/Distanz-/Winkel-Stratifizierung.
- Schwellenwerte anhand unabhängiger Testdaten festlegen. Menschliche Prüfung vor bestätigter Meldung. Kein Modell als „nachgewiesen“ bezeichnen, bevor ein unabhängiger Testbericht vorliegt.
- Bevorzugt selbst erhobene und ausdrücklich freigegebene Bilder sowie einzeln nach Lizenz gefilterte CC0/CC-BY-Daten. CC-BY-NC-Material nicht in einer kommerziell weiterverwendbaren Modellpipeline nutzen; keine ungeklärten Bilder scrapen.

### P3 – Monitor und Verbund
- Monitor-Bridge mit authentifizierter, TLS-geschützter Verbindung außerhalb Loopback; lokale Installationen dürfen weiterhin loopback-only bleiben.
- Ereignis-Schema versionieren; Signaturen, Replay-Schutz, Zeitfenster, Rate Limits, Cursor-Integrität, Idempotenz und Dead-Letter-Handling testen.
- Stationsverwaltung: Registrierung, Schlüsselrotation/-sperre, Kalibrierungsstatus, Software-/Modellversion, letzte Verbindung und Betriebszustand.
- Rollen/Rechte: Stationsbetreiber, Prüfer, Netzwerkadministrator. Export- und Löschprotokoll ohne unnötige personenbezogene Inhalte.
- Abnahme: Mehrstationen-E2E, Offline-/Reconnect, doppelte und verspätete Ereignisse, Schlüsselwiderruf, falsche Signatur und kompromittierte Station.

### P4 – MeshCore-Feldbetrieb
- MeshCore bleibt optionaler Transportadapter, nicht die Quelle der Wahrheit und nicht Voraussetzung für den lokalen Betrieb.
- Zunächst zwei bis fünf reale Knoten auf unterstützter Hardware: Reichweite, Paketverlust, Latenz, Hop-Verhalten, Stromverbrauch, Antennenposition und Wiederanlauf protokollieren.
- Kompakte signierte Ereignisse, TTL, Sequenz-/Replay-Schutz, Deduplizierung und Store-and-forward. Keine großen Payloads und keine Medienübertragung.
- Bundesweite Abdeckung erst behaupten, wenn reale Messfahrten und Betreiber-/Repeater-Zustimmungen vorliegen.
- Frequenz- und Betriebsparameter für Deutschland vor jeder Hardwarefreigabe gegen aktuelle regulatorische Vorgaben prüfen.

### P5 – Freenet-Integration getrennt evaluieren
- Das Projekt freenet.org / freenet-core ist ein eigenständiges P2P-Overlay und kein LoRa-Funknetz und kein Ersatz für MeshCore.
- Zunächst nur ein isolierter Prototyp für signierte, pseudonyme Ereignis-Metadaten bzw. Replikation; keine Standort- oder Medienfreigabe per Default.
- Vor Integration: aktuelle Lizenz, Reifegrad, API/Contract-Modell, Ressourcenbedarf, Bedrohungsmodell, Update-/Key-Management und Datenschutz-Folgen bewerten.
- Adapter nur hinter Feature-Flag; Ausfall von Freenet darf Stationsbetrieb und lokale Datenhaltung nicht beeinträchtigen.

### P6 – Triangulation und Kalibrierung
- Winkelmessung nur aus kalibrierten, dokumentierten Stationen mit Zeitbasis und Richtungsunsicherheit.
- Robuste Schätzung mit Ausreißerdiagnostik, Geometrie-/Konditionsprüfung und 95-%-Unsicherheitsgebiet.
- Testfälle: ideale Geometrie, nahezu parallele Peilungen, Ausreißer, Zeitversatz, Stationsausfall, fehlerhafte Kalibrierung und Mehrdeutigkeit.
- Feldabnahme zunächst mit bekannten Referenzpunkten; Distanzfehler und Abdeckungswahrscheinlichkeit berichten. Ohne validierte Referenzmessungen keine Genauigkeitsversprechen.

### P7 – Datenschutz, Sicherheit und Lizenzfreigabe
- Zweck, Verantwortlichkeit, Rechtsgrundlage, Speicherfristen und Betroffenenprozesse je Pilotstandort dokumentieren; Datenschutzbeauftragte/Behörde bei Bedarf einbeziehen.
- Kameraausrichtung auf erforderliche Beobachtungszone begrenzen; Maskierung, minimale Auflösung, kurze lokale Pufferung und keine Audioaufzeichnung standardmäßig.
- TLS, sichere Schlüsselablage, Least Privilege, signierte Updates, SBOM, Dependency-/Container-Scanning, Backup-Verschlüsselung und Wiederherstellungstests.
- Lizenzinventar pro Datei/Komponente/Modell/Dataset einschließlich SPDX-Identifier, Copyright-Hinweis, Upstream-URL, Version/Commit, Änderungen und Weitergabepflichten.
- Vor jeder Veröffentlichung: Lizenzprüfung, Security-Review, Datenschutz-Checkliste und reproduzierbarer Release-Nachweis.

### P8 – Pilot und Wiederherstellung
- Pilot mit 3–5 Standorten, dokumentierter Einwilligung/Betreiberfreigabe, Referenzbeobachtungen und menschlicher Verifikation.
- Vorab festgelegte Kennzahlen: Verfügbarkeit, Ereignisse/Kameratag, Fehlalarme/Kameratag, Erkennungsmetriken, Übertragungsverlust, Wiederanlaufzeit und Ortungsfehler.
- Backup/Restore aller Datenbanken, Konfigurationen, Schlüssel-Wiederherstellungsprozesse und Kalibrierungen testen; Schlüssel selbst nicht ungeschützt sichern.
- Go/No-Go nach unabhängiger Auswertung; bei Qualitäts- oder Datenschutzmängeln Pilot stoppen und Fehler beheben.

## Kostenfreie / gemeinnützige Quellen – Nutzungsregeln

| Quelle | Geeigneter Zweck | Lizenz-/Nutzungsregel |
|---|---|---|
| GBIF (Vespa velutina, Taxon-Key 1311477) | Verbreitungs-/Vorkommensdaten, Forschungsabgleich | Lizenz pro Datensatz prüfen; CC0/CC-BY bevorzugen; Datensatzquellen nennen und Downloads mit DOI zitieren |
| iNaturalist | Beobachtungsdaten und ggf. Medien | Lizenz je Beobachtung und Medium prüfen; Standard ist häufig CC-BY-NC, daher nicht ungeprüft für kommerziell nutzbare Modelle übernehmen |
| Observation.org | ergänzende Sichtungsdaten | Lizenz und API-Bedingungen je Datensatz prüfen; nicht pauschal als frei kommerziell nutzbar behandeln |
| Umweltbundesamt / BfN / Landesbehörden | Fachinformationen, Verbreitung, Meldewege | Nutzungsbedingungen der konkreten Seite/des Dokuments prüfen; amtliche Information ist nicht automatisch gemeinfrei |
| Universität Hohenheim, Landesanstalt für Bienenkunde | Bestimmungshilfen, Schulungsmaterial | Nur die ausdrücklich zur Weitergabe freigegebenen Materialien unverändert und mit Quellenhinweis nutzen; Bildrechte separat prüfen |
| OpenStreetMap | Karten-/Geodaten | ODbL; sichtbare Attribution und Share-Alike-Pflichten für abgeleitete Datenbanken beachten |
| MapLibre | Karten-Rendering | Open-Source-Renderer; Kartenkacheln/Tile-Provider haben separate Nutzungsbedingungen |
| MeshCore | optionaler LoRa-Transport | Upstream-Firmware überwiegend MIT; einzelne Clients/Firmware-Ausnahmen getrennt prüfen |
| Freenet Core | optionales P2P-Overlay | Eigenständige Software und Architektur; aktuelle Repository-Lizenz/Abhängigkeiten vor Integration prüfen |
| OpenCV / ONNX Runtime | Kamera- und Inferenzruntime | Upstream-Lizenzen, gebündelte Binärdateien und Drittanbieter-Abhängigkeiten in SBOM erfassen |
| OpenVINO | CPU-/Intel-Beschleunigung | Lizenz und unterstützte Hardwareversion vor Paketierung prüfen |

## Verbindliche Release-Gates

Ein Release darf nur dann als einsatzbereit bezeichnet werden, wenn:
1. Build und Installation auf sauberem Zielsystem reproduzierbar sind.
2. Kamera-Dauerlauf und Fehlerwiederherstellung bestanden sind.
3. Modellprovenienz und unabhängige Erkennungsmetriken vorliegen.
4. Monitor-E2E und Mehrstationen-Datenschutztests bestanden sind.
5. MeshCore-Funkmessungen mit realen Geräten vorliegen, falls Funkbetrieb beworben wird.
6. Triangulationsfehler anhand bekannter Referenzpunkte gemessen wurden.
7. Lizenz-, Sicherheits- und Datenschutzprüfung dokumentiert freigegeben ist.
8. Backup/Restore und Pilot-Go/No-Go dokumentiert sind.

## Referenzquellen

- GBIF Occurrence API: https://techdocs.gbif.org/en/openapi/v1/occurrence
- GBIF Citation Guidelines: https://www.gbif.org/citation-guidelines
- iNaturalist Terms: https://www.inaturalist.org/pages/terms
- iNaturalist Media Licensing: https://help.inaturalist.org/en/support/solutions/articles/151000169918
- Umweltbundesamt – Asiatische Hornisse: https://www.umweltbundesamt.de/asiatische-hornisse
- Universität Hohenheim – Vespa velutina: https://bienenkunde.uni-hohenheim.de/vespavelutina
- OpenStreetMap Copyright/ODbL: https://www.openstreetmap.org/copyright
- MeshCore upstream: https://github.com/meshcore-dev/MeshCore
- Freenet Core upstream: https://github.com/freenet/freenet-core
- Freenet architecture: https://freenet.org/build/manual/introduction/
- Frigate detector documentation (reference for detector backend trade-offs): https://docs.frigate.video/configuration/object_detectors/

Alle externen Quellen und Lizenzen sind vor jedem Release erneut zu prüfen. Die Nennung einer Quelle ist keine pauschale Erlaubnis, deren Inhalte oder Modelle zu übernehmen.
