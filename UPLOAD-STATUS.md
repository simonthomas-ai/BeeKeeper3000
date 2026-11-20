# Veröffentlichungs- und Integrationsstatus

Stand: 20.11.2026

## In GitHub veröffentlichte Komponenten

Repository: https://github.com/simonthomas-ai/BeeKeeper3000

- Architektur-, Security-, Lizenz-, Provenienz- und Lieferketten-Dokumentation.
- Cursor-fähige lokale Quell-API mit HMAC-signierten Cursor-Tokens, strengem Ereignisvertrag, begrenztem SQLite-Quelljournal, Aufbewahrungsgrenze und explizitem Fehler bei abgelaufenen/wiederaufzuholenden Cursorn.
- Node.js-Monitor-Bridge mit Cursor-Paginierung, begrenzten Wiederholungen, Retry-After, schema- und größenbegrenzten Antworten, atomarem Checkpoint und Metadaten-Minimierung.
- Optionaler MeshCore-Serialadapter mit kompaktem signiertem Ereignisformat, Ed25519-Prüfung, Station-Key-Bindung, TTL, Replay-Schutz und lokalem SQLite-Empfänger-/Peilungsspeicher.
- Robuste Winkelpeilungs-Triangulation mit Zeitfenster, Geometrieprüfung, Huber-Gewichtung, begrenzter Ausreißerbehandlung und 95-%-Unsicherheitsellipse. Das Resultat ist immer eine Suchhypothese.
- Windows-Start-/Stopp- und Backup-Skripte mit lokalem DPAPI-Schutz für Stationsgeheimnisse, ACL-geschütztem Arbeitsverzeichnis, SQLite-Online-Backups und SHA-256-Manifest.
- CI für Python-/Netzwerk-/MeshCore-Regressionen, Bridge-Tests auf Ubuntu und Windows, CodeQL, optionalen Dependency-Audit und CycloneDX-SBOM für die vorhandene optionale MeshCore-Python-Abhängigkeitsliste.

Monitor-Repository: https://github.com/simonthomas-ai/Beekeeper-Monitor

- Authentifizierter Loopback-Eingang für streng validierte Metadatenereignisse.
- Dauerhafte SQLite-Speicherung, Replay-Deduplizierung, Retention, Export-/Löschpfade, begrenzte Requests und lokale Stationsereignisansicht.
- Software-Ende-zu-Ende-Test Quelle → Bridge → Monitor mit realen lokalen HTTP-Handlern und temporären SQLite-Datenbanken.

## Ende-zu-Ende-Nachweis

Der Test übertrug 205 Ereignisse durch echte lokale Softwareprozesse und HTTP-Schnittstellen:
- 205 Quellereignisse wurden über Cursor-Seiten 100/100/5 an den Monitor übertragen.
- Nach Neustart der Bridge wurde am gespeicherten Cursor weitergearbeitet; es kamen keine weiteren Datensätze hinzu.
- Ein absichtlicher vollständiger Replay sendete die 205 Ereignisse erneut; der Monitor behielt trotzdem genau 205 eindeutige Datensätze.
- Die Tests prüfen, dass keine Bilder, Audiodaten oder GPS-Koordinaten über die Bridge gehen und Kandidaten nicht als fachlich bestätigt hochgestuft werden.

Nachweise:
- Monitor-Integrations-Workflow: https://github.com/simonthomas-ai/Beekeeper-Monitor/actions/runs/44733301612
- BeeKeeper3000 Bridge-Tests Linux/Windows: https://github.com/simonthomas-ai/BeeKeeper3000/actions/runs/44734124679
- BeeKeeper3000 Netzwerk-/MeshCore-/Python-Regressionen: https://github.com/simonthomas-ai/BeeKeeper3000/actions/runs/44734124954
- CodeQL auf dem PR-Stand: https://github.com/simonthomas-ai/BeeKeeper3000/actions/runs/44734124850

Diese Ergebnisse belegen die automatisierte Softwarestrecke mit Testdaten. Sie belegen weder den Betrieb einer realen Kamera/KI noch eine Funkverbindung, ein bundesweites LoRa-Netz oder die Genauigkeit einer Feldtriangulation.

## Noch nicht veröffentlichte bzw. nicht vollständig belegte Bestandteile

Der vollständige ursprüngliche Hornet3000-Wächter-Quellbaum 1.6.0 ist im aktuellen GitHub-Tree nicht enthalten. Insbesondere fehlen weiterhin der vollständige ursprüngliche C++-Dienst, zugehörige CMake-/Build-Manifeste, vollständige Packaging-/Installer-Bestandteile und eine durchgehende Artefakt-Provenienzkette. Der Repository-Baum darf nicht mit einem vollständigen Upload des ursprünglichen Produkts verwechselt werden.

Nicht als integriert oder betriebsbereit behauptet werden:
- validierte lokale KI-Inferenz bzw. ein nach unabhängigen Daten geprüftes Vespa-velutina-Modell,
- physischer MeshCore-/LoRa-Betrieb mit zwei oder mehr echten Funkgeräten,
- bundesweite Relais-/Gateway-Abdeckung,
- Meshtastic als eigener Adapter,
- Freenet-P2P-Adapter,
- MQTT/Mosquitto-Adapter,
- MapLibre-Live-Karte,
- Anbindung von Kamera-/Audio-Hardware an einen validierten Detektor.

## Noch offene Freigabe- und Betriebsarbeiten

1. Vollständige ursprüngliche C++-Quellbasis, Lizenztexte, Urheberhinweise und Provenienz aus vertrauenswürdiger Quelle wiederherstellen und abgleichen. GitHub erkennt für das Repository weiterhin keine Root-Lizenz; keine pauschale Weiterverteilungslizenz ableiten.
2. Vollständige SBOM-/Lizenzabdeckung für alle tatsächlich veröffentlichten Runtime-, OS-, Firmware-, Modell-, Datensatz- und Kartenartefakte herstellen. Die vorhandenen SBOM-/Audit-Jobs decken die vorhandene Bridge-Abhängigkeitsstruktur und die optionale MeshCore-Python-Lockdatei ab, nicht das fehlende Gesamtprodukt.
3. Physische MeshCore-Hardwaretests einschließlich unterstützter Boards/Firmware, Paketverlust, Reichweite, Antennen-/Standortkonfiguration und gesetzlicher Funkparameter durchführen.
4. Peilung mit kalibrierten Sensoren, dokumentiertem Fehlerbudget und unabhängig vermessenen Zielpositionen im Feld validieren.
5. Modellgewichte, Trainingsdaten und Fotos separat auf Lizenz/Einwilligung prüfen und ein unabhängiges Testset mit Precision/Recall und Verwechslungsmatrix bereitstellen.
6. PWA auf echten iOS-/Android-Geräten installieren, Offline-Neustart und Backup-/Restore auf einer Teststation abnehmen.
7. Datenschutz- und Sicherheitsreview für den konkreten Betreiber, Datenfluss, Speicherort, Rollen, Aufbewahrung, Export und Löschung durchführen. Diese Dokumentation ist keine DSGVO-Zertifizierung.

## Betrieb und Datensicherheit

- Keine API-Schlüssel, Stations-Private-Keys, Kamerapasswörter, privaten Bilder, Audioaufnahmen oder präzisen Standortdaten committen.
- Standarddienste bleiben auf Loopback; Remotezugriff nur über ein separat abgesichertes VPN/TLS-Gateway.
- SQLite-Dateien sind nicht anwendungsseitig verschlüsselt. Dateisystemrechte und Datenträgerverschlüsselung (z. B. BitLocker) bleiben erforderlich.
- Windows-DPAPI-Geheimnisse sind Benutzer-/Rechner-gebunden und nicht als portable Backup-Datei gedacht.
- Keine öffentliche Kartenfreigabe präziser Standorte ohne ausdrücklich geregelte Freigabe und Rollenmodell.
- Kein automatischer Artbestätigungs- oder Bekämpfungsentscheid aus einem Modellscore oder einer Peilhypothese.
