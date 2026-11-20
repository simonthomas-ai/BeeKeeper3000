# BeeKeeper3000 – bundesweites, dezentrales Velutina-Messnetz

## Ziel und harte technische Grenze

Das Netz soll Beobachtungen von *Vespa velutina* bundesweit austauschen und aus räumlich unabhängigen Beobachtungen belastbare Suchgebiete für Primär- und Sekundärnester ableiten. Es ist ein Beobachtungs- und Lokalisierungssystem, kein automatisches Nestvernichtungs- oder Bekämpfungssystem.

**Wichtig:** Eine Hornisse sendet kein LoRa-Signal. LoRa kann daher nicht direkt das Tier orten. Funkdaten transportieren nur Messmeldungen der Stationen. Die eigentliche Ortung entsteht aus optischen/visuellen Peilungen, bestätigten Flugrichtungen und – in spezialisierten Suchteams – Radio-/Harmonic-Radar-Telemetrie. Die wissenschaftliche Literatur beschreibt Radio-Telemetrie als praxistaugliche Nest-Suchmethode; visuelle Flugrichtungs-Triangulation ist ebenfalls dokumentiert.

## 1. Für alle nutzbare Teilnehmerklassen

| Klasse | Hardware | Beitrag |
|---|---|---|
| Bürger-App | vorhandenes Smartphone | Foto/Beobachtung, Zeit, GPS mit ausdrücklicher Freigabe, manuelle Qualitätsangaben |
| Imkerei-/Gartenstation | vorhandene Kamera oder Smartphone, optional GNSS | wiederkehrende Sichtungen und Flugrichtungen |
| KI-Station | Raspberry Pi/ähnlicher Edge-Rechner, Kamera, optional Beschleuniger | lokale Bildklassifikation; nur Ereignismetadaten teilen |
| Richtungsstation | kalibrierte Kamera/Kompass oder geschulte Beobachter | Azimut, Unsicherheit, Zeit und Standort |
| Relais/Gateway | LoRa-fähiges Gerät oder IP-Knoten | speichert und leitet signierte, kleine Meldungen weiter |
| Suchteam | zugelassener Telemetrieempfänger und geeigneter Sender/Tag | gezielte Verfolgung eines markierten Tieres durch sachkundige Teams |

Ein Smartphone-only-Teilnehmer ist vollwertig: Es gibt keine Pflicht, Funkhardware oder KI-Kamera zu kaufen.

## 2. Funk- und Netzwerktopologie

### LoRa / MeshCore
- Lokaler, stromsparender Transport für kurze Ereignisdatensätze und Statusmeldungen.
- Zielanforderung für den späteren Netzbetrieb: Store-and-forward mit Ablaufzeit, persistenter Duplikaterkennung und begrenzter Hop-Anzahl. Der aktuelle MeshCore-Adapter sendet und empfängt kompakte Ereignisse; ein persistenter Funk-Relay-/Hop-Queue-Dienst ist noch nicht implementiert.
- Kein Bild-, Video- oder Audio-Transport über LoRa.
- MeshCore ist eine mögliche Implementierung, nicht die einzige zulässige Funktechnik.
- LoRa-Funkabdeckung ist regional und topografieabhängig. Eine bundesweite Abdeckung entsteht nur durch viele freiwillige Gateways/Relais und darf nicht versprochen werden.

### Freenet (freenet.org)
- Zusätzliche dezentrale IP-P2P-Verteilung zwischen Knoten, die ohnehin Internetzugang haben.
- Geeignet für Replikation, Synchronisierung und Abruf signierter Ereignis-Batches.
- Nicht als LoRa-Modem, Funk-Repeater oder Echtzeitgarantie behandeln.
- Freenet-Knoten sind optional; lokaler Betrieb und Export/Import müssen auch ohne Freenet funktionieren.

### IP-Alternativen
- Lokales WLAN/Ethernet, VPN und HTTPS für Installationen mit Internetzugang.
- MQTT/HTTPS kann als austauschbarer Adapter für Vereine, Kommunen und Forschung dienen.
- Keine zentrale Cloud und kein einzelner Betreiber als Single Point of Failure.

## 3. Messverfahren und Nestlokalisierung

### Stufe A – Beobachtung
Eine Meldung enthält Artkandidat, Zeit, Stationskennung, Position/Positionsgenauigkeit, Belegart und Qualitätswerte. Fotos bleiben standardmäßig lokal; eine freiwillig freigegebene Aufnahme kann separat über HTTPS übermittelt werden.

### Stufe B – Richtungspeilung
Eine kalibrierte Kamera oder ein geschulter Beobachter erfasst die beobachtete Abflug-/Flugrichtung als Azimut (Grad von geografisch Nord, im Uhrzeigersinn) plus Unsicherheit. Smartphone-Kompasswerte sind nur nach Kalibrierung und Qualitätsprüfung zulässig. Magnetische Störungen in Gebäuden und an Metallmasten müssen erkannt werden.

### Stufe C – räumliche Zusammenführung
Mindestens drei zeitlich passende, räumlich unabhängige Peilungen sollen ein Suchgebiet erzeugen. Die Referenzimplementierung in `network/triangulation.py` berechnet einen gewichteten Schnittpunkt der Peillinien in einem lokalen ebenen Koordinatensystem. Sie weist schlechte Geometrie, rückwärts gerichtete Strahlen und große Restfehler zurück. Der berechnete Punkt ist **nur ein Suchhinweis**, kein bestätigter Neststandort.

### Stufe D – fachliche Verifikation
Suchteams prüfen den Bereich vor Ort. Bei Bedarf kann ein sachkundiges Team eine Hornisse mit einem geeigneten Telemetriesender markieren und per Empfänger verfolgen. Die Auswahl, Masse und Befestigung eines Senders müssen tierwohlgerecht und fachlich geprüft sein; kein LoRa-Tag an frei fliegenden Tieren als Standard voraussetzen.

### Akustik
Mikrofone können lokal bei nahen Flugbewegungen Zusatzinformationen liefern. Ein einzelnes Mikrofon oder ein einfaches Mikrofonarray ist kein belastbarer bundesweiter Nest-Peiler. Akustische Klassifikation ist ergänzend und muss gegen Nichtzielarten validiert werden.

### Wärmebild
Kann bei geeigneter Sichtlinie und Tageszeit ein Suchteam unterstützen, ist aber kein alleiniger Art- oder Nestnachweis.

## 4. Ereignisformat und Funkbudget

Das transportneutrale Ereignismodell ist in JSON beschrieben (siehe `network/protocol-v1.schema.json`). Für MeshCore ist inzwischen ein konkretes binäres Profil v1 unter `network/meshcore/protocol.py` implementiert. Die JSON-Struktur wird nicht unverändert über Funk gesendet. Andere Transportadapter benötigen ein eigenes, versioniertes Wire-Format.

Pflichtfelder:
- schema_version, event_id, station_id
- observed_at (UTC mit Zeitzone), expires_at
- event_type, candidate_taxon, confidence und verification_status
- location (Koordinate plus Genauigkeit) nur nach Teilnahme-/Datenschutzeinstellung
- bearing_deg und bearing_sigma_deg nur bei Richtungsbeobachtung
- evidence_hash statt Bild/Ton-Datei
- signature_key_id und Signatur über kanonische Nutzdaten

Das MeshCore-Profil verwendet eine Ed25519-Signatur, 128-Bit-Fingerprints für öffentliche Schlüssel und pseudonyme 128-Bit-Hashes für Stations- und Ereigniskennungen. Das Funkpaket enthält Ereignistyp, Taxonkandidat, Konfidenz, Verifikationsstatus, Beobachtungs-/Ablaufzeit und bei Peilungen Azimut plus Unsicherheit. Die Größe liegt bei 128 Byte ohne bzw. 132 Byte mit Peilungsdaten und damit unter dem dokumentierten 163-Byte-Anwendungsdatenlimit des MeshCore-Channel-Data-Pakets.

**Keine exakten Koordinaten, Fotos, Audiodaten, Zugangsdaten oder Freitexte werden über dieses Funkprofil übertragen.** Empfangende Stationen müssen eine lokale Zuordnung des Stationshashs zu Station-ID und kalibrierten Koordinaten pflegen. Erst dort entsteht aus einer verifizierten Peilungsmeldung ein lokales `Bearing`-Objekt für die Triangulation. Unbekannte Stationen oder nicht vertrauenswürdige Schlüssel werden abgewiesen. Ein kryptografisch signierter Expert-Status wird ohne explizite Expert-Key-Allowlist zu `unverified` zurückgestuft.

Die Softwaretests verwenden synthetische Schlüssel, Koordinaten und einen simulierten Funkclient. Sie belegen weder reale Funkübertragung noch Reichweite, Funkrecht, Koordinatenkalibrierung oder Feldgenauigkeit. Persistente Funk-Relay-Queues, Schlüsselwiderruf/-rotation und ein echtes Hardware-Lab bleiben separate Abnahmen. Vertrauenswürdigkeit entsteht nicht allein aus einem Modellscore.

## 5. Datenhoheit und Datenschutz

- Edge-first: Bilder und Ton bleiben standardmäßig auf dem Gerät.
- GPS wird nur geteilt, wenn der Nutzer es bewusst aktiviert; die Oberfläche bietet grobe Standortfreigabe.
- Keine Gesichts-, Kennzeichen- oder Personenanalyse.
- Keine dauerhafte öffentliche Anzeige privater Grundstücke oder genauer Nestkoordinaten.
- Nestverdacht wird zunächst rollenbasiert und mit Genauigkeitsradius geteilt; genaue Position nur an berechtigte Suchteams/Behörden mit Einwilligung bzw. geeigneter Rechtsgrundlage.
- Löschfristen, Widerruf, Export und Offline-Löschung sind Produktanforderungen.
- Öffentliche Karte zeigt aggregierte Raster/Regionen, nicht automatisch exakte Privatstandorte.

## 6. Sicherheit und Missbrauchsschutz

- Eindeutige Stationsidentität und widerrufbare Schlüssel.
- Signierte Meldungen, TLS bei IP-Transport, getrennte Schlüssel je Dienst.
- Replay-Schutz über event_id, Zeitstempel und Ablaufzeit.
- Quoten je Station, Größenlimits, maximale Hop-Zahl und Warteschlangenlimits.
- Kein ausführbarer Code, keine Skripte und keine beliebigen Anhänge über das Funknetz.
- Unbestätigte Artbestimmung bleibt als Kandidat markiert.
- Admin- und Updatepfade müssen signiert sein; keine offenen Standardpasswörter.

## 7. Recht und Betrieb in Deutschland

LoRa-Funkbetrieb muss die zum jeweiligen Zeitpunkt geltenden Allgemeinzuteilungen der Bundesnetzagentur einhalten (insbesondere SRD-Verfügung 91/2025 einschließlich Teilband-, Leistungs-, Kanalzugangs- und Airtime-Bedingungen). Nicht pauschal eine Sendeleistung oder Duty-Cycle-Zahl für alle Kanäle fest verdrahten. Geräte, die als Produkt bereitgestellt werden, benötigen eine passende RED-/CE-Konformitätsbewertung. Funkmodule und Antennen müssen gemäß Hersteller-/Zulassungsbedingungen betrieben werden.

Meldungen ersetzen keine Meldung an die zuständige Landes-/Kommunalbehörde. Das Umweltbundesamt empfiehlt die Meldung bestätigungsbedürftiger Funde an die zuständigen Stellen. Nestentfernung und Bekämpfung bleiben sachkundigen Personen vorbehalten; Europäische Hornissen dürfen nicht verwechselt oder beeinträchtigt werden.

## 8. Umsetzungsphasen und Abnahmekriterien

1. **Software-Protokoll:** JSON-Schema und das MeshCore-Binärprofil v1 sind vorhanden; Signaturprüfung, Ablaufzeit, lokaler Stationsresolver und simulierte Transporttests laufen in CI. Persistente Offline-Funkqueue, Schlüsselwiderruf und Simulator für Funkverlust müssen noch ergänzt werden.
2. **Zwei-Knoten-Labor:** zwei reale LoRa-Knoten und ein Gateway; Paketverlust, Duplikate, Zeitdrift, Reichweite und Stromverbrauch messen. Diese Hardwareabnahme ist offen.
3. **Drei- bis Fünf-Stationen-Feldtest:** bekannte Testpeilungen, vermessene Referenzpunkte, Vergleich mit GPS/Kompass und manuellem Tracking.
4. **P2P-Adapter:** Freenet-Synchronisierung nur für signierte Ereignis-Batches; Offline- und Konflikttests.
5. **Pilotregion:** Imkerverein/Uni/Naturschutzbehörde, Datenschutzkonzept und fachliche Validierung.
6. **Skalierung:** erst nach dokumentierter Funkabdeckung, Fehlalarmrate, Ortungsfehler und Betriebskosten.

**Abnahme:** kein bundesweiter Funktionsanspruch, bevor reale Feldtests, Funkmessungen, Sicherheitsprüfung und unabhängige Artbestimmungsvalidierung bestanden sind.
