# BeeKeeper3000 – Hardware-Referenzentwürfe und Anschlussdiagramme

**Status:** Konzeptionelle Entwürfe für Prototypen. Keine zertifizierten Konstruktionszeichnungen, keine Funkzulassung und kein Ersatz für Herstellerdatenblätter oder eine elektrotechnische Prüfung.

## Entwurf A – Teilnahme ausschließlich mit Smartphone
~~~mermaid
flowchart LR
  P[Android / iPhone] -->|PWA: manuelle Meldung / freigegebene Medien| Q[Lokale Offline-Warteschlange]
  Q -->|HTTPS bei Internetverbindung| API[BeeKeeper-Quell-API]
  P -->|BLE optional| R[MeshCore-Begleitfunkgerät]
  R -->|nur signierte Metadaten| M[Mesh-Netzwerk]
  API --> J[Lokales Ereignisprotokoll]
~~~
Zusätzliche Stationselektronik ist nicht erforderlich. Kamera und Standort werden nur nach aktiver Einwilligung des Nutzers verwendet. Optional ist eine zertifizierte USB-Powerbank möglich. Offline-Entwürfe benötigen einen erkennbaren Versandstatus, ein Ablaufdatum sowie Funktionen zur Prüfung und Löschung.

## Entwurf B – feste PoE-Kamera mit Edge-Rechner
~~~mermaid
flowchart TB
  CAM[RTSP-/ONVIF-IP-Kamera] -->|Ethernet / PoE| SW[PoE-Switch oder Injektor]
  SW -->|LAN| EDGE[Mini-PC / Einplatinenrechner]
  EDGE -->|lokale KI-Auswertung| DET[Freigegebene Modelllaufzeit]
  DET -->|nur Metadaten| DB[Lokales Protokoll und Versandwarteschlange]
  DB -->|HTTPS / MQTT TLS| GW[Lokales Gateway / Quell-API]
  GW -->|signierte Ereignispakete| NET[Optionaler MeshCore-/IP-Transport]
  UPS[Zertifizierte DC-USV] --> EDGE
  UPS --> SW
~~~
Ein eingeschränktes LAN/VLAN und ein eigenes Kamera-Benutzerkonto mit minimalen Berechtigungen verwenden. RTSP/ONVIF niemals direkt ins Internet stellen. PoE-Klasse und Leistungsbedarf mit den Datenblättern von Kamera und Switch abgleichen.

## Entwurf C – solare Niederspannungsstation (nur Konzept)
~~~mermaid
flowchart TD
  PV[Solarmodul] --> CTRL[Passender Solarladeregler]
  BAT[Geschützter Akku mit BMS] <--> CTRL
  CTRL --> F1[DC-Sicherung in Akkunähe]
  F1 --> DC[Geregelte DC-Verteilung / Abwärtswandler]
  DC --> EDGE[Edge-Rechner]
  DC --> CAM[Kamera / Sensor]
  DC --> RADIO[LoRa-Funkknoten]
  EDGE -->|USB / Ethernet / seriell| CAM
  EDGE -->|USB / BLE / UART| RADIO
  EDGE -->|nur Metadaten| NET[IP- oder LoRa-Gateway]
~~~
Solarmodul, Akkutechnologie, Laderegler, Batteriemanagementsystem (BMS), Sicherung, Leitungsquerschnitt und Wandler nach gemessener Höchstlast, Temperatur, gewünschter Betriebsdauer ohne Sonne und standortspezifischem Solarertrag auslegen. Ein Solarmodul niemals direkt mit Akku oder Einplatinenrechner verbinden. Schutz gegen Verpolung, Überstrom, Über- und Unterspannung sowie Überhitzung vorsehen.

## Entwurf D – optionaler Sensorbus
~~~mermaid
flowchart LR
  S1[Temperatur / Feuchte / Licht] -->|BLE oder Modbus RTU| HUB[Sensor-Gateway]
  S2[GNSS / NMEA] -->|USB / UART| HUB
  S3[IMU / Kompass] -->|BLE / I2C / SPI| HUB
  S4[Regen / Wind] -->|Impuls / RS-485| HUB
  HUB -->|geprüfte Messwerte| EDGE[Stationsrechner]
  EDGE --> DB[Lokales Protokoll]
~~~
I²C und SPI eignen sich für kurze Verbindungen auf Platinen, nicht für lange Außenkabel. Für längere Strecken sind geeignete, galvanisch getrennte RS-485-/Modbus-Verbindungen mit Abschluss und Überspannungsschutz vorzusehen. GNSS- und Kompasswerte benötigen Qualitätsmerkmale; magnetische Richtungsangaben erfordern Kalibrierung und Deklinationskorrektur.

## Hinweise zu Niederspannungsanschlüssen

| Schnittstelle | Typischer Einsatz | Anschluss und Sicherheit |
|---|---|---|
| USB 2/3 | UVC-Kamera, GNSS, Funk, Sensoren | Stromgrenzen des Hosts und Geräts beachten; gegebenenfalls aktiven Hub einsetzen |
| Ethernet | IP-Kamera, Rechner, Gateway | Außenkabel und Überspannungsschutz, korrekte PoE-Auslegung |
| PoE | Kamera oder entfernter Knoten | IEEE-Klasse und Datenblatt beachten; passives PoE nur bei ausdrücklicher Unterstützung |
| UART TTL | GNSS / Mikrocontroller | Logikspannung (3,3 V oder 5 V), TX/RX/GND prüfen; niemals annehmen |
| RS-485 | Lange Sensorleitungen | Differenzielles Adernpaar, Topologie, Abschluss und Vorspannung laut Transceiver; Isolation und Überspannungsschutz |
| I²C / SPI | Sensoren auf Platinen | Kurze Leitungen; Logikspannung und Pinbelegung prüfen |
| BLE | Smartphone / Umweltsensor | Kopplung und Identitätsprüfung; keine garantierte Langstreckenverbindung |
| LoRa | Kleine signierte Ereignismetadaten | Zulässiges Frequenzband, geeignetes Funkmodul und Antenne, erlaubte Sendezeit |

## Vorlage zur Energieberechnung
Für jeden Verbraucher Eingangsspannung, Spitzen- und Durchschnittsstrom, Einschaltdauer, Anlaufstrom, täglichen Energiebedarf (Wh), Wandlerwirkungsgrad, nutzbare Akkukapazität bei Kälte und Alterung, Solarertrag im ungünstigsten Monat, gewünschte Autonomietage, Sicherung, Leitungsquerschnitt und Steckverbinderbelastbarkeit erfassen.

Tagesenergie in Wh = Summe aus Spannung (V) × mittlerem Strom (A) × Betriebsstunden (h).

Benötigte nominelle Akkuenergie = Tagesenergie × Autonomietage / nutzbarer Entladetiefe / Umwandlungswirkungsgrad.

Die Solarmodulgröße muss auf den standortspezifischen Ertrag im ungünstigsten Monat und auf Verluste abgestimmt werden, nicht auf eine pauschale Wattangabe.

## Grenzen der Elektro- und Funksicherheit
Diese Vorlage behandelt ausschließlich Gleichstrom-Niederspannung. Sie ist **keine Anleitung für Eigenarbeiten an Netzspannung**. Netzanschlüsse, Gebäudeinstallation, Blitzschutz, Mastausgleich und dauerhafte elektrische Außenanlagen müssen von qualifizierten Fachkräften entsprechend den geltenden Regeln geplant, errichtet und geprüft werden. Keine Funkverstärker verändern, gesetzliche Grenzen umgehen oder nicht zugelassene Antennenkombinationen verwenden. In Deutschland und der EU gelten für das konkrete Gerät und Frequenzband die aktuellen Vorgaben der Bundesnetzagentur sowie RED-/CE-Anforderungen. Sender dürfen nicht ohne gesonderte fachliche, tierschutzrechtliche und rechtliche Prüfung an Wildtieren angebracht werden.

## Checkliste zur Freigabe eines nachbaubaren Schaltplans
Ein fertiger Fertigungs-/Nachbauplan benötigt genaue Bauteilnummern und Revisionen, Herstellerdatenblätter, Pinbelegung, Leitungsquerschnitte und -längen, Sicherungen, Spannungs- und Stromgrenzen, Steckverbinderbelastbarkeit, Gehäuse-Schutzart, thermische Prüfung, Funkkonfiguration, Firmware, Montageschritte und unabhängige Kontrolle. Diese allgemeinen Diagramme sind **noch keine nachbaureifen Fertigungsunterlagen**.

## Entwurf E – Smartphone-PWA
Die erste mobile Implementierung liegt in `mobile-pwa/` und arbeitet zunächst lokal. Kamera/Fotowahl, einmalige Standortfreigabe und optionale Orientierungssensoren werden nur nach Nutzeraktion verwendet. Meldungen bleiben in IndexedDB. Ein manuell gestarteter Export enthält ausschließlich die Metadatenfelder der Source-API v1. Eine Kopplung an MeshCore-Funkgeräte oder dauerhafte Standortverfolgung ist noch nicht implementiert. Siehe [MOBILE-PWA-ACCEPTANCE.md](MOBILE-PWA-ACCEPTANCE.md).

## Detaillierte Niederspannungs-Verdrahtung
Beispiele für Steckverbinder, UART-/I²C-Signalrichtungen, RS-485-Bustopologie, DC-Sicherungen, Energieverteilung und Stücklisten stehen in [LOW-VOLTAGE-WIRING-TEMPLATES.md](LOW-VOLTAGE-WIRING-TEMPLATES.md). Allgemeingültige GPIO-Pinnummern und ungeprüfte Bauteilnummern werden bewusst vermieden. Vor einem nachbaureifen Schaltplan müssen die exakte Platinenrevision und die Herstellerdatenblätter feststehen.
