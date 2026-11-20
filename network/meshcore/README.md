# BeeKeeper3000 – MeshCore-Funkadapter

Optionaler serieller Adapter für MeshCore-Begleitfunkgeräte. Er sendet kompakte, signierte Metadaten in MeshCore-Kanaldatenpaketen. **Nicht übertragen** werden Fotos, Ton, GPS-Koordinaten, persönliche Namen, Freitextnotizen oder Kamerazugangsdaten.

## Installation
Im Repository-Hauptverzeichnis die optionalen Abhängigkeiten aus `network/meshcore/requirements.lock` installieren. Die geprüfte Originalbibliothek ist `meshcore==2.3.19` (MIT-Lizenz, Python 3.10 oder neuer). Die derzeitige Versionssperre wurde ausschließlich für Linux-CI erstellt; für Windows und die vorgesehenen Einplatinenrechner müssen Abhängigkeiten gesondert aufgelöst und getestet werden. Die Bibliothek ist optional und wird nicht von der Kern-Triangulation importiert.

## Funkprotokoll v1
- Binäre Nachrichtenhülle mit Ed25519-Signatur und 16 Byte langem Fingerabdruck des öffentlichen Schlüssels.
- Ereignis- und Stationskennungen sind verkürzte SHA-256-Kennungen.
- Übertragen werden Zeitstempel, Ablaufzeit, Ereignistyp, Taxon, Verifizierungsangabe, Konfidenz und optional eine Peilrichtung.
- Keine genauen GPS-Koordinaten, Bilder, Tondateien, Dateinamen, Zugangsdaten oder Freitexte im Paket.
- Nutzdatenlänge: 128 Byte ohne Peilung beziehungsweise 132 Byte mit Peilung; unter der Grenze von 163 Byte für MeshCore-Kanaldaten.
- Ereignisse des Typs Nesthypothese werden in v1 nicht akzeptiert: Das gemeinsame Schema verlangt hierfür einen Standort, den die Funknachricht bewusst nicht enthält.
- Eine Angabe „fachkundig bestätigt“ wird auf „unbestätigt“ zurückgestuft, wenn der Signaturschlüssel nicht ausdrücklich in der Vertrauensliste für Fachkundige steht.

Eine gültige Signatur belegt nur den Besitz des zugehörigen privaten Schlüssels, **nicht die biologische Richtigkeit** einer Artbestimmung. Alle Erkennungen bleiben bis zur fachkundigen Prüfung Kandidaten.

## Konfiguration
Ein eigenes Ed25519-Schlüsselpaar außerhalb des Programms erzeugen. Den privaten Schlüssel mit Betriebssystemrechten oder einem hardwaregestützten Schlüsselspeicher schützen. Weder private noch operative Schlüssel in Git einchecken. Empfangsstationen müssen die öffentlichen Schlüssel der vertrauenswürdigen Sender vorab erhalten.

`MeshCoreSerialTransport` mit serieller Schnittstelle, Kanalnummer, Anwendungsdatentyp, Stationskennung und privatem Stationsschlüssel einrichten. Vor dem Senden eine Verbindung öffnen und beim geordneten Beenden schließen. Implementierung: `network/meshcore/transport.py`.

Zum Empfang `MeshCoreEventReceiver` mit einer Liste zugelassener öffentlicher Schlüssel und einer empfängerinternen `StationRegistry` verwenden. Die Liste wird über den 32 Zeichen langen Fingerabdruck des öffentlichen Schlüssels indiziert. Für fachkundig bestätigte Aussagen ist eine **separate** Vertrauensliste nötig.

Zusätzlich muss jeder Stations-Hash mit `trusted_station_keys` ausdrücklich einem oder mehreren autorisierten Fingerabdrücken zugeordnet sein. Ein allgemein vertrauenswürdiger Schlüssel darf keine Ereignisse unter einer fremden Stationskennung senden. Jeder Signaturfingerabdruck darf genau einer Station zugeordnet sein; während eines Schlüsselwechsels darf eine Station vorübergehend mehrere Fingerabdrücke besitzen. Alten und neuen Fingerabdruck für diese Station eintragen, den neuen Schlüssel überprüfen und erst dann den alten entfernen. Vertrauenslisten und Stationszuordnung ausschließlich lokal am Empfänger aufbewahren. Private Schlüssel niemals übertragen.

## Dauerhafter lokaler Ereignisspeicher
`SQLiteMeshCoreEventStore` in `network/meshcore/event_store.py` ist ein empfangsseitiger Speicher, der wiederholte Ereignisse sicher behandelt:

```python
from network.meshcore.event_store import SQLiteMeshCoreEventStore
from network.meshcore.receiver import MeshCoreEventReceiver, StationRegistry

store = SQLiteMeshCoreEventStore(
    r"C:\BeeKeeper3000\data\meshcore-events.sqlite3",
    retention_days=30,
    max_rows=100_000,
)
registry = StationRegistry({
    # 32-stelliger Stations-Hash aus dem signierten MeshCore-Protokoll:
    "PUT_STATION_HASH_HERE": {
        "station_id": "yard-north",
        "latitude": 51.2345,
        "longitude": 6.7890,
    }
})
# Jeder Stations-Hash wird an seine autorisierten Signatur-Fingerabdrücke gebunden.
# Mehrere Fingerabdrücke erlauben eine ausdrücklich begrenzte Übergangszeit beim Schlüsselwechsel.
trusted_station_keys = {
    "32_CHARACTER_STATION_HASH": {
        "32_CHARACTER_PUBLIC_KEY_FINGERPRINT",
    },
}
receiver = MeshCoreEventReceiver(
    transport=radio,
    trusted_public_keys=trusted_keys,
    trusted_station_keys=trusted_station_keys,
    station_registry=registry,
    sink=store,
)
```

**Hinweis:** Die Stationskoordinaten und Kennungen im Codeblock sind ausschließlich illustrative Beispieldaten, keine tatsächlichen Messungen oder betriebsbereite Konfiguration. Die Platzhalter `radio` und `trusted_keys` müssen in einer echten Anwendung definiert werden.

Der Speicher übernimmt Ereignisse erst nach Prüfung von Signatur, Ablaufzeit und Stationsregister. Eindeutige Ereignis-IDs bleiben über Prozessneustarts erhalten. Die genaue Wiederholung eines Pakets liefert im Speicher `False` und wird als Duplikat gezählt. Eine bereits verwendete Ereignis-ID mit verändertem signiertem Inhalt oder geänderter lokaler Stationsauflösung wird abgewiesen, nicht stillschweigend überschrieben. Aufbewahrungsfrist und maximale Zeilenzahl sind begrenzt.

Unter POSIX muss das Speicherverzeichnis dem Dienst gehören und privat sein (0700); SQLite-Dateien und Nebendateien erhalten 0600. Unter Windows passende NTFS-Zugriffsrechte für das Dienstkonto einrichten. SQLite wird durch diese Anwendung nicht verschlüsselt; Datenträgerverschlüsselung verwenden.

Stationskoordinaten bleiben ausschließlich beim Empfänger und werden nicht über MeshCore übertragen. Gespeicherte Koordinaten werden nur bei Peilereignissen nach Auflösung des signierten Stations-Hashs durch das lokale Register ergänzt. Sie gehören nicht zum signierten Funkereignis-JSON.

## Empfangen und triangulieren
`store.recent_bearings(window_seconds=1800)` liefert die jeweils neueste Peilung jeder unabhängigen, lokal aufgelösten Station. `store.triangulate_recent()` ruft das Referenzverfahren mit Winkelrestfehlern auf. Es gewichtet Beobachtungen anhand kalibrierter Winkelunsicherheit, begrenzt die robuste Ausreißerunterdrückung, verlangt mindestens drei übereinstimmende Stationen und berechnet eine lokale, linearisierte 95-%-Unsicherheitsellipse.

Die Zeitstempel müssen zusammenpassen und die Peillinien eine ausreichend stabile Schnittgeometrie haben. Das Ergebnis ist stets nur eine `search_hypothesis`, **niemals ein bestätigtes Nest**. Annahmen zur Kalibrierung und Abnahme stehen in `network/TRIANGULATION-VALIDATION.md`. Vermessung, Ausreißerbehandlung, Unsicherheitsgeometrie und unabhängige Feldtests sind vor dem Einsatz erforderlich.

## Betriebliche Grenzen
- Für diese Implementierung standen keine physischen MeshCore-Funkgeräte, Antennen, Repeater oder deren Firmware zur Verfügung. Funkübertragung, Sendezeitgrenzen, Reichweite und Interoperabilität sind **nicht als getestet nachgewiesen**.
- Kanaldaten erfordern kompatible Begleitgeräte-Firmware. Die ursprüngliche Python-API stellt `send_channel_data` und `CHANNEL_DATA_RECV` bereit.
- Empfangsstationen müssen öffentliche Schlüssel vorab einrichten und kurze Stationskennungen lokalen Datensätzen mit kalibrierten Koordinaten zuordnen. Ohne diese Zuordnung lässt sich eine Peilung nicht in einen geografischen Strahl umrechnen.
- Der Adapter ist unabhängig von Meshtastic, Freenet und Mosquitto; er aktiviert diese Übertragungswege nicht.
- Vor dem Betrieb mit der ausgewählten Hardware die deutschen und europäischen Grenzwerte für Frequenz, Sendezeit, Kanalbreite und EIRP prüfen.
