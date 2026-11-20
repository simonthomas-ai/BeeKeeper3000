# Netzwerk-Referenzimplementierung

Dieses Verzeichnis enthält zwei getrennte Teile:

## 1. Kern ohne Funkabhängigkeiten

- `triangulation.py`: gewichteter Least-Squares-Schnittpunkt geografischer Peilungen.
- `test_triangulation.py`: synthetische Tests für bekannten Zielpunkt, ungültige Geometrie und Rückwärtsstrahlen.
- `protocol-v1.schema.json`: JSON-Ereignisvertrag als transportneutrale Datenstruktur.

Test:

```sh
python -m unittest network.test_triangulation -v
```

## 2. Optionaler MeshCore-Adapter

`meshcore/` enthält:

- Ed25519-signiertes Binärprofil v1 mit 128-Bit-Station-/Event-Hashes und 128-Bit-Public-Key-Fingerprint.
- Serial-Transport über den optionalen Upstream-Python-Binding `meshcore==2.3.19`.
- Empfangsprüfung gegen explizite Public-Key-Allowlist.
- lokale Auflösung von Station-Hashes in kalibrierte Koordinaten; Koordinaten werden nicht über Funk übertragen.
- begrenzte In-Memory-Duplikaterkennung und Tests mit simuliertem Funkclient.

Installieren und testen:

```sh
python -m pip install -r network/meshcore/requirements.lock
python -m unittest network.meshcore.test_protocol network.meshcore.test_receiver network.meshcore.test_transport -v
```

Die MeshCore-Abhängigkeit ist optional und wird nicht durch die Kern-Triangulation importiert. Lizenz- und Herkunftsinformationen sind im Adapter-README und im Komponentenregister dokumentiert.

## Sicherheits- und Betriebsgrenzen

Die Triangulation benötigt mindestens drei unabhängige, zeitlich passende Peilungen und liefert einen **Suchhinweis**, keine bestätigte Nestposition. Eine gültige Ed25519-Signatur bestätigt nur den Besitz eines Schlüssels, nicht die biologische Richtigkeit einer Artbestimmung.

MeshCore-Pakete übertragen keine exakten GPS-Koordinaten, Bilder, Audiodaten, Zugangsdaten oder Freitext. Empfangende Stationen müssen vertrauenswürdige Schlüssel und die lokale Zuordnung ihrer Stationskennungen vorab provisionieren.

Es wurden keine physischen Radios, Antennen, Repeater oder realen Stationen für diesen Softwaretest verwendet. Funkreichweite, Airtime, EU-Funkkonformität und echte Stations-Triangulation bleiben Feldabnahmen.

Freenet ist ein optionales IP-P2P-Konzept und kein LoRa-Modem. Freenet, Meshtastic, Mosquitto und MapLibre sind in diesem Repository noch keine aktiv integrierten Laufzeitadapter.
