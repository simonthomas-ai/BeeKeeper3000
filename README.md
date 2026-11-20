# BEEKEEPER3000

**Lokale, modulare und herstellerneutrale Plattform für Beobachtung und Ereignisverarbeitung rund um Bienenstände und Insekten.**

Dieses Repository enthält aktuell eine veröffentlichte Teilmenge der BeeKeeper3000-/Hornet3000-Entwicklung: Architektur- und Lizenzdokumentation, Python-Referenz-Triangulation, einen Node.js-Monitor-Bridge-Adapter sowie einen optionalen MeshCore-Transport. Der vollständige ursprüngliche Hornet3000-Wächter-Quellbaum, die vollständige Stationsruntime und validierte KI-Modelle sind nicht vollständig in diesem Repository enthalten.

## Grundsätze

- Local-first und ohne verpflichtende Cloud betreibbar.
- Austauschbare Funk- und IP-Adapter.
- Keine ungefragte Übermittlung von Bildern, Audio oder GPS.
- Jede Ereignisquelle bleibt zunächst ein Kandidat; Signaturen ersetzen keine fachliche Artbestimmung.
- Betreiberkontrolle über Daten, Schlüssel und externe Integrationen.
- Herkunfts- und Lizenzhinweise bleiben erhalten.

## Aktueller Softwarestand

### Netzwerk und Triangulation
- `network/triangulation.py`: gewichtete Least-Squares-Schnittpunktberechnung aus mindestens drei unabhängigen, zeitlich passenden Peilungen.
- `network/protocol-v1.schema.json`: JSON-Vertrag für künftige und lokale IP-/Netzwerkereignisse.
- `network/meshcore/`: optionaler MeshCore-Serialadapter mit binärem Ereignisformat v1, Ed25519-Signaturen, 128-Bit-Fingerprints, Ablaufzeit, Duplikatfilter und lokalem Stationskoordinatenregister.
- MeshCore-Funkpakete enthalten keine exakten Koordinaten, Fotos, Audio, Zugangsdaten oder Freitext. Die Empfängerstation ordnet die pseudonyme Stationskennung lokal einem kalibrierten Standort zu.

### Monitor-Anbindung
Die Node.js-Komponente in [monitor-bridge/](monitor-bridge/) fragt den Hornet3000-Ereignisendpunkt ab und überträgt ausgewählte Metadaten an den authentifizierten Eingang von [Beekeeper-Monitor](https://github.com/simonthomas-ai/Beekeeper-Monitor). Die Bridge kennzeichnet Artbestimmungen als unbestätigt und lässt Bilder, Audio und GPS weg.

Der aktuelle Monitor-Hauptzweig verfügt über einen loopback-gebundenen Empfangsdienst mit SQLite-Ereignisspeicher und einer lokalen Stationsereignis-Ansicht. Die lokale Ansicht wird unter `http://127.0.0.1:8765/` geöffnet. Die öffentliche GitHub-Pages-Seite greift absichtlich nicht auf einen privaten localhost-Dienst zu.

**Synchronisationsgrenze:** Die Bridge liest derzeit nur die jüngsten 100 Ereignisse pro Abfrage. Ohne Cursor-/Sequenzunterstützung der Quell-API ist verlustfreie Nachholung bei größeren Rückständen noch nicht garantiert. Siehe [Issue #7](https://github.com/simonthomas-ai/BeeKeeper3000/issues/7).

## Tests

Aus dem Repository-Hauptverzeichnis:

```sh
python -m unittest network.test_triangulation -v
```

Für den optionalen MeshCore-Adapter:

```sh
python -m pip install -r network/meshcore/requirements.lock
python -m unittest network.meshcore.test_protocol network.meshcore.test_receiver network.meshcore.test_transport -v
```

Für die Node.js-Bridge:

```sh
cd monitor-bridge
npm test
```

GitHub Actions prüft Triangulation, signiertes MeshCore-Protokoll, Empfangs-/Transporttests und die Bridge separat. Die erfolgreiche CI belegt Softwaretests und synthetische Datenpfade, keinen realen Funkbetrieb oder Feldgenauigkeit.

## Was noch nicht als einsatzbereit gilt

- Kein bestätigter Funk-/Repeater-Feldtest mit realen MeshCore-Geräten.
- Kein bundesweiter LoRa-Netzabdeckungsnachweis.
- Kein Freenet-, Meshtastic-, Mosquitto- oder MapLibre-Laufzeitadapter in diesem Repository.
- Keine vollständige lokale Stationsruntime mit Installer und Geräteverwaltung.
- Kein nach unabhängigen Testdaten validiertes Vespa-velutina-Erkennungsmodell; ONNX-Inferenz ist nicht als aktiv bestätigt.
- Kein vollständiger Backup-/Restore-Abnahmetest für den Monitor-Datenspeicher.
- Keine vollständige Datenschutz- oder DSGVO-Konformitätsprüfung.

## Sicherheit und Datenschutz

Keine echten Zugangsdaten, privaten Schlüssel, Kamerapasswörter, privaten Aufnahmen, Audiodateien oder GPS-Spuren einchecken. Private Schlüssel müssen lokal geschützt und öffentliche Schlüssel außerhalb des Funknetzes vertrauenswürdig provisioniert werden. Dienste nur lokal oder hinter VPN und korrekt konfiguriertem HTTPS betreiben. SQLite ist nicht anwendungsseitig verschlüsselt; Datenträgerverschlüsselung und passende Dateisystemrechte sind erforderlich. Siehe [SECURITY.md](SECURITY.md).

## Herkunft und Lizenz

Die eingebrachte Ausgangsbasis stammt aus Hornet3000 Wächter 1.6.0. Dieses Repository behauptet keine Clean-Room-Neuentwicklung und keine pauschale Neulizenzierung. Die veröffentlichte Repository-Lizenzmetadaten- und Quellbaumprüfung ist noch nicht vollständig abgeschlossen; die Root-Datei `LICENSE` und die vollständige ursprüngliche Quellbasis sind vor einer Release-/Weiterverteilungsfreigabe zu prüfen. Siehe [PROVENANCE.md](PROVENANCE.md), [LICENSES.md](LICENSES.md) und [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
