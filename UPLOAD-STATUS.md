# Veröffentlichungs- und Integrationsstatus

Stand: 22.11.2026

## Aktualisierung – 22.11.2026

Der aktuelle Hauptzweig enthält inzwischen eine experimentelle lokale Kamera-/ONNX-Strecke sowie eine persistente Offline-Warteschlange. Diese Komponenten sind softwareseitig geprüft, aber noch keine freigegebene automatische Hornissenerkennung.

- [x] Lokales Kamera-Runtime-Modul in `camera/runtime.py`: USB-Gerät, lokale Videodatei oder RTSP-/HTTP-Stream; native lokale Kamera-Backends je Betriebssystem; begrenzte Open-/Read-Timeouts für Netzwerk-/Dateiquellen; Wiederverbindungsversuche mit begrenztem Backoff.
- [x] ONNX-Detektor in `camera/onnx_detector.py` mit fail-closed Modellmanifest in `camera/model_manifest.py`: Prüfsumme, Modellquelle, Lizenzprüfung, Inferenz-/Weitergaberechte und expliziter Tensor-/Ausgabevertrag werden verlangt. Das Beispielmanifest ist absichtlich ungültig.
- [x] Persistente Metadaten-Outbox in `camera/outbox.py`: SQLite, begrenzte Kapazität, eindeutige Ereignis-IDs, Kollisionsschutz, persistente Cooldowns und kontrollierter Fehler statt stiller Löschung bei voller Warteschlange.
- [x] Offline-Recovery und Wiederanlauf einschließlich SQLite-Neustart, Retry und HTTP-Übertragung sind durch Kameratests und die repo-übergreifende Monitor-Integration geprüft.
- [x] Letzter dokumentierter BeeKeeper3000-Hauptzweigstand: `8eba14db628a5b5d8672bcbab9b078f0e7977799`. Die zugehörigen Hauptzweigläufe waren erfolgreich: [Quality gates #44933015228](https://github.com/simonthomas-ai/BeeKeeper3000/actions/runs/44933015228), [CodeQL #44933015262](https://github.com/simonthomas-ai/BeeKeeper3000/actions/runs/44933015262), [Network reference tests #44933015273](https://github.com/simonthomas-ai/BeeKeeper3000/actions/runs/44933015273) und [Supply-chain audit/SBOM #44933015286](https://github.com/simonthomas-ai/BeeKeeper3000/actions/runs/44933015286).
- [x] Der aktuelle Monitor-Gesamttest prüfte den festgelegten BeeKeeper3000-Commit inklusive Kamera-Outbox, Offline-HTTP-Recovery, Bridge und repo-übergreifendem Ereignisvertrag erfolgreich: [Monitor-Gesamttest #44994991995](https://github.com/simonthomas-ai/Beekeeper-Monitor/actions/runs/44994991995).

**Weiterhin nicht freigegeben bzw. nicht nachgewiesen:**
- [ ] Kein verifiziertes Modellgewicht und kein vollständiger rechtlich/fachlich freigegebener Trainings- und unabhängiger Testdatensatz im Repository.
- [ ] Keine gemessene Precision, Recall, Konfusionsmatrix, Fehlalarmrate oder Feldgenauigkeit des Detektors.
- [ ] Keine Abnahme mit einer realen Kamera, einem realen RTSP-Stream oder einem dauerhaft betriebenen Stationsrechner.
- [ ] Keine physische MeshCore-/LoRa-Reichweitenmessung und keine Triangulationsvalidierung an vermessenen Zielpositionen.
- [ ] Keine vollständige Produkt-SBOM und keine pauschale Repository-Lizenz. Die vorhandenen Supply-Chain-Prüfungen decken nur die dokumentierten Abhängigkeitsbereiche ab; die ursprüngliche C++-Quelle, Firmware, Modellgewichte und Datensätze bleiben separat zu klären.

Ein erfolgreicher Softwarelauf belegt nur die darin ausgeführten Tests. Er ist weder KI-Modellfreigabe noch Hardware-/Feldabnahme, rechtliche Freigabe oder Erlaubnis zum produktiven Nestmanagement.


## Bisheriger Integrationsstand (Dokumentation vom 20.11.2026)

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

Der vollständige ursprüngliche Hornet3000-Wächter-Quellbaum 1.6.0 wurde aus dem bereitgestellten Bibliotheksarchiv wiederhergestellt. Der SHA-256 des Ausgangsarchivs `Hornet3000-1.6.0-source.zip` stimmt mit `SHA256SUMS.txt` überein: `ffb4040bf1facf2d08f880b73c06c3933f801e5de2a97a497bfabaa9ca9c007a`. Daraus wurde lokal eine gehärtete 1.6.1-Version gebaut und getestet (GCC 14.2, CMake Release, CTest 1/1, HTTP/JPEG/Privacy-Smoke, MeshCore/Freenet-Protokolltests 10/10). Das 1.6.1-Paket liegt als lokales Arbeitsartefakt vor; es ist in diesem Stand noch nicht als entpackter Quellbaum oder Release-Asset in GitHub veröffentlicht.

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

1. Wiederhergestellten 1.6.0-Quellbaum und gehärtete 1.6.1-Module in GitHub veröffentlichen; für alle Drittanbieter-Artefakte die Provenienz weiter prüfen. Es gibt weiterhin keine pauschale Repository-Lizenz. GitHub erkennt für das Repository weiterhin keine Root-Lizenz; keine pauschale Weiterverteilungslizenz ableiten.
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
