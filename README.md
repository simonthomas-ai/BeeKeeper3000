# BEEKEEPER3000

**Lokale, modulare und herstellerneutrale Plattform für Beobachtung und Ereignisverarbeitung rund um Bienenstände und Insekten.**

Dieses Repository enthält eine veröffentlichte Teilmenge der BeeKeeper3000-/Hornet3000-Entwicklung: Architektur- und Lizenzdokumentation, Python-Referenz-Triangulation, Node.js-Monitor-Bridge, optionalen MeshCore-Transport und nun eine optionale lokale Kamera-/ONNX-Produzentenpipeline. Der vollständige ursprüngliche Hornet3000-Wächter-Quellbaum und ein nach unabhängigen Felddaten validiertes KI-Modell sind nicht vollständig in diesem Repository enthalten.

## Grundsätze

- Local-first und ohne verpflichtende Cloud betreibbar.
- Austauschbare Funk- und IP-Adapter.
- Keine ungefragte Übermittlung von Bildern, Audio oder GPS.
- Jede Ereignisquelle bleibt zunächst ein Kandidat; Signaturen ersetzen keine fachliche Artbestimmung.
- Betreiberkontrolle über Daten, Schlüssel und externe Integrationen.
- Herkunfts- und Lizenzhinweise bleiben erhalten.

## Aktueller Softwarestand

### Netzwerk und Triangulation

- `network/triangulation.py`: winkelgewichtete iterative Peilschnittberechnung mit Huber-Robustifizierung, begrenzter Ausreißererkennung und lokaler linearer 95-%-Unsicherheitsellipse. Mindestens drei unabhängige, zeitlich passende Stationen bleiben erforderlich; Ergebnis bleibt eine Suchhypothese.
- `network/protocol-v1.schema.json`: JSON-Vertrag für künftige und lokale IP-/Netzwerkereignisse.
- `network/meshcore/`: optionaler MeshCore-Serialadapter mit binärem Ereignisformat v1, Ed25519-Signaturen, 128-Bit-Fingerprints, Ablaufzeit, Duplikatfilter und lokalem Stationskoordinatenregister.
- `network/meshcore/event_store.py`: lokaler SQLite-Speicher mit dauerhafter Ereignis-ID-Deduplizierung, Aufbewahrungs-/Datensatzlimit und lokaler Speicherung der zur Peilung aufgelösten Stationskoordinaten. Doppelte signierte Ereignisse werden auch nach einem Empfänger-Neustart nicht erneut gespeichert.
- MeshCore-Funkpakete enthalten keine exakten Koordinaten, Fotos, Audio, Zugangsdaten oder Freitext. Die Empfängerstation ordnet die pseudonyme Stationskennung lokal einem kalibrierten Standort zu. Die Triangulation liefert ausschließlich eine Suchhypothese.

### Monitor-Anbindung

Die Node.js-Komponente in [monitor-bridge/](monitor-bridge/) fragt den Hornet3000-Ereignisendpunkt ab und überträgt ausgewählte Metadaten an den authentifizierten Eingang von [Beekeeper-Monitor](https://github.com/simonthomas-ai/Beekeeper-Monitor). Die Bridge kennzeichnet Artbestimmungen als unbestätigt und lässt Bilder, Audio und GPS weg. Sie markiert Ereignisse erst nach einer positiven dauerhaften Empfangsbestätigung; bei fehlgeschriebenem lokalen Bridge-Checkpoint wird die In-Memory-Markierung zurückgerollt.

Der Monitor-Hauptzweig verfügt über einen loopback-gebundenen Empfangsdienst mit SQLite-Ereignisspeicher und einer lokalen Stationsereignis-Ansicht. Die lokale Ansicht wird unter `http://127.0.0.1:8765/` geöffnet. Die öffentliche GitHub-Pages-Seite greift absichtlich nicht auf einen privaten localhost-Dienst zu.

**Synchronisationsstand (20.11.2026):** Die veröffentlichte Quell-API implementiert jetzt HMAC-signierte, opaque Cursor-Paginierung über ein dauerhaftes SQLite-Quelljournal. Die Bridge verarbeitet Seiten bis 100 Ereignisse, validiert Cursor-Fortschritt, wiederholt temporäre Fehler begrenzt und schreibt atomare Checkpoints erst nach bestätigter dauerhafter Annahme durch den Monitor. Der Checkpoint ist auf 2 MiB begrenzt und akzeptiert nur Ereignis-IDs aus dem Quellvertrag.

Der softwareseitige Ende-zu-Ende-Test verwendete die echte Quell-API, den Node-Bridge-Prozess und den authentifizierten Monitor-HTTP-Eingang: 205 Testereignisse wurden als 100/100/5 zugestellt; ein Neustart setzte am gespeicherten Cursor ohne weitere Zustellung fort; vollständiger Replay erzeugte keine zusätzlichen Datensätze. Bilder, Audio und GPS fehlten im übertragenen Payload, alle Kandidaten blieben unbestätigt. [E2E-Workflow](https://github.com/simonthomas-ai/Beekeeper-Monitor/actions/runs/44733301612). Die Software-Polling-/Idempotenzlücke aus [Issue #7](https://github.com/simonthomas-ai/BeeKeeper3000/issues/7) ist damit geschlossen.

Diese Tests belegen die lokale HTTP-/SQLite-Softwarestrecke, nicht die reale Kamera-/KI-Produktion, physischen MeshCore-Funkbetrieb, ein bundesweites Netz oder die Freenet-Anbindung. Der Legacy-Modus kann weiterhin nur bewusst als verlustbehafteter Fallback aktiviert werden; im Standardbetrieb ist Cursor-Pagination erforderlich.

### Lokale Kamera-/ONNX-Pipeline (experimentell)

Das optionale Paket [camera/](camera/) stellt USB-/RTSP-/Videodatei-Aufnahme, CPU-Inferenz über ONNX Runtime, ein strenges lokales Model-Manifest mit SHA-256-/Lizenzprüfung, eine persistente SQLite-Outbox und einen Loopback-Source-API-Client bereit. Es sendet nur die sechs Felder des Source-API-Vertrags; Bild-/Audio-/GPS-Daten werden nicht weitergegeben. Offline-Ereignisse bleiben in der lokalen Warteschlange, bis der Quellserver sie bestätigt. Bei voller Warteschlange stoppt der Prozess statt Ereignisse still zu verwerfen.

Das Beispielmanifest ist absichtlich ungültig und es sind keine Modellgewichte enthalten. Ein reales Modell wird erst nach unabhängiger Lizenz-/Provenienzprüfung und Anpassung an den expliziten ONNX-Ausgabevertrag akzeptiert. Das verbindliche Hardware- und Qualitätsabnahmeverfahren steht in [docs/CAMERA-ACCEPTANCE.md](docs/CAMERA-ACCEPTANCE.md). Alle Vorhersagen bleiben unbestätigte Kandidaten. Das Modul wird separat gestartet und ist nicht Bestandteil des Basis-Stationslaunchers. Einrichtung und Grenzen: [camera/README.md](camera/README.md).

## Tests

Aus dem Repository-Hauptverzeichnis:

```sh
python -m unittest network.test_triangulation -v
```

Für den optionalen MeshCore-Adapter:

```sh
python -m pip install -r network/meshcore/requirements.lock
python -m unittest network.meshcore.test_protocol network.meshcore.test_receiver network.meshcore.test_event_store network.meshcore.test_transport -v
```

Für die Node.js-Bridge:

```sh
cd monitor-bridge
npm test
```

GitHub Actions prüft Triangulation, signiertes MeshCore-Protokoll, Empfänger, persistenten Speicher und Transport sowie die Bridge separat. Erfolgreiche CI belegt Softwaretests und synthetische Datenpfade, aber keinen realen Funkbetrieb oder Feldgenauigkeit.

## Was noch nicht als einsatzbereit gilt

- Kein bestätigter Funk-/Repeater-Feldtest mit realen MeshCore-Geräten.
- Kein bundesweiter LoRa-Netzabdeckungsnachweis.
- Kein Freenet-, Meshtastic-, Mosquitto- oder MapLibre-Laufzeitadapter in diesem Repository.
- Keine vollständige lokale Stationsruntime mit Installer und Geräteverwaltung.
- Eine lokale ONNX-Kamerapipeline ist implementiert, aber ohne freigegebenes Modell nicht einsatzbereit; kein nach unabhängigen Testdaten validiertes Vespa-velutina-Erkennungsmodell und keine nachgewiesene Erkennungsqualität.
- Kein vollständiger Backup-/Restore-Abnahmetest aller lokalen Datenspeicher; die neue Kamera-Outbox besitzt einen eigenen Backup-/Restore-Prüfer.
- Keine vollständige Datenschutz- oder DSGVO-Konformitätsprüfung.

## Sicherheit und Datenschutz

Keine echten Zugangsdaten, privaten Schlüssel, Kamerapasswörter, privaten Aufnahmen, Audiodateien oder GPS-Spuren einchecken. Private Schlüssel müssen lokal geschützt und öffentliche Schlüssel außerhalb des Funknetzes vertrauenswürdig provisioniert werden. Dienste nur lokal oder hinter VPN und korrekt konfiguriertem HTTPS betreiben. SQLite ist nicht anwendungsseitig verschlüsselt; Datenträgerverschlüsselung und passende Dateisystemrechte sind erforderlich. Siehe [SECURITY.md](SECURITY.md).

## Lieferkette und SBOM

Die CI prüft die optionale MeshCore-Python-Abhängigkeitsliste mit `pip-audit`, erzeugt daraus einen CycloneDX-SBOM als CI-Artefakt und führt `npm audit` für die Bridge aus. Das ist ausdrücklich **kein vollständiger SBOM des ursprünglichen Hornet3000-Gesamtprodukts**, weil der komplette C++-Quellbaum und weitere Runtime-/Modell-/Firmware-Artefakte hier nicht vollständig vorliegen. Details und Grenzen stehen in [SUPPLY_CHAIN.md](SUPPLY_CHAIN.md).

## Herkunft und Lizenz

Die eingebrachte Ausgangsbasis stammt aus Hornet3000 Wächter 1.6.0. Dieses Repository behauptet keine Clean-Room-Neuentwicklung und keine pauschale Neulizenzierung. Die veröffentlichte Repository-Lizenzmetadaten- und Quellbaumprüfung ist noch nicht vollständig abgeschlossen; die Root-Datei `LICENSE` und die vollständige ursprüngliche Quellbasis sind vor einer Release-/Weiterverteilungsfreigabe zu prüfen. Siehe [PROVENANCE.md](PROVENANCE.md), [LICENSES.md](LICENSES.md) und [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Recht, Gemeinnützigkeit und Freigabestatus

**Das Projekt ist nicht als gemeinnützige Körperschaft anerkannt und wird hier nicht als solche bezeichnet.** Kostenloser Open-Source-Zugang ist nicht gleichbedeutend mit steuerlicher Gemeinnützigkeit. Es werden über dieses Repository keine Spendenquittungen, steuerlichen Vorteile, Zertifizierungen oder Haftungsfreiheit zugesagt.

Die Root-Lizenz und die vollständige Rechtekette des veröffentlichten Teilbaums sind noch nicht abschließend freigegeben. Die Ausgangsbasis ist laut Provenienzunterlagen Hornet3000 Wächter 1.6.0 mit GPL-3.0-or-later-Herkunft; daraus folgt keine pauschale Neulizenzierung aller neu hinzugefügten oder externen Bestandteile. Bis zur Prüfung keine Gesamtprojektlizenz unterstellen und keine unklar lizenzierten Artefakte weiterverteilen.

Der öffentliche Pilot- und Release-Status bleibt **BLOCKIERT**, bis die anwendbare Checkliste für Träger-/Betreiberrollen, Lizenzkette, Datenschutz, Produktsicherheit, Funkrecht und fachliche Erkennungsqualität dokumentiert freigegeben wurde. Siehe:
- [Recht und Gemeinnützigkeit](docs/LEGAL-COMPLIANCE.md)
- [Verbindliches Release-/Pilot-Gate](docs/RELEASE-LEGAL-GATE.md)
- [Mitwirkungsregeln](CONTRIBUTING.md)
- [Sicherheitsrichtlinie](SECURITY.md)

Diese Dokumente sind Risikomanagement und keine Rechtsberatung, keine behördliche Anerkennung und keine Garantie, dass Maintainer oder Betreiber niemals in Anspruch genommen werden können.

