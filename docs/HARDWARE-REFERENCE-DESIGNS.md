# BeeKeeper3000 – hardware reference designs and wiring diagrams

Status: conceptual reference designs for prototyping. Not certified construction drawings, not radio certification, and not a substitute for device datasheets or electrical review.

## Design A – smartphone-only participant
~~~mermaid
flowchart LR
  P[Android / iPhone] -->|PWA: manual report / consented media| Q[Local offline draft queue]
  Q -->|HTTPS when online| API[BeeKeeper source API]
  P -->|optional BLE| R[MeshCore companion radio]
  R -->|signed metadata only| M[Mesh network]
  API --> J[Local event journal]
~~~
No extra station electronics required. Camera/location are accessed only while the user actively grants permission. Optional certified USB power bank. Offline drafts need visible pending/sent state, expiry, review and deletion.

## Design B – fixed PoE camera + edge computer
~~~mermaid
flowchart TB
  CAM[RTSP / ONVIF IP camera] -->|Ethernet / PoE| SW[PoE switch or injector]
  SW -->|LAN| EDGE[Mini-PC / SBC edge host]
  EDGE -->|local inference| DET[Approved detector runtime]
  DET -->|metadata only| DB[Local journal + outbox]
  DB -->|HTTPS / MQTT TLS| GW[Local gateway / source API]
  GW -->|signed event batches| NET[Optional MeshCore / IP transport]
  UPS[Certified DC UPS] --> EDGE
  UPS --> SW
~~~
Use a restricted LAN/VLAN and a dedicated least-privilege camera account. Do not expose RTSP/ONVIF to the Internet. Match PoE class and power budget to camera/switch datasheets.

## Design C – low-voltage solar station (concept only)
~~~mermaid
flowchart TD
  PV[PV module] --> CTRL[Matched solar charge controller]
  BAT[Protected battery with BMS] <--> CTRL
  CTRL --> F1[DC fuse near battery]
  F1 --> DC[Regulated DC distribution / buck converters]
  DC --> EDGE[Edge computer]
  DC --> CAM[Camera / sensor]
  DC --> RADIO[LoRa radio node]
  EDGE -->|USB / Ethernet / serial| CAM
  EDGE -->|USB / BLE / UART| RADIO
  EDGE -->|metadata only| NET[IP or LoRa gateway]
~~~
Size panel, battery chemistry, controller, BMS, fuse, wire gauge and converters from measured worst-case load, temperature, autonomy and site-specific solar yield. Never connect a panel directly to a battery or SBC. Provide reverse-polarity, over-current, over-voltage, undervoltage and thermal protection.

## Design D – optional sensor bus
~~~mermaid
flowchart LR
  S1[Temp / RH / light] -->|BLE or Modbus RTU| HUB[Sensor gateway]
  S2[GNSS / NMEA] -->|USB / UART| HUB
  S3[IMU / compass] -->|BLE / I2C / SPI| HUB
  S4[Rain / wind] -->|pulse / RS-485| HUB
  HUB -->|validated readings| EDGE[Station host]
  EDGE --> DB[Local journal]
~~~
I2C/SPI are short board-level buses, not long outdoor cabling. For longer runs use properly isolated RS-485/Modbus with termination and surge protection. GNSS/compass readings require quality flags; magnetic heading requires calibration and declination.

## Connector-level low-voltage notes
| Interface | Typical use | Wiring / safety |
|---|---|---|
| USB 2/3 | UVC camera, GNSS, radio, sensor | Respect host/device current limits; powered hub if specified |
| Ethernet | IP camera, host, gateway | Outdoor-rated cable, surge protection, proper PoE |
| PoE | Camera / remote node | Match IEEE class and datasheet; no passive PoE unless explicitly supported |
| UART TTL | GNSS / MCU | Confirm logic voltage (3.3 V vs 5 V), TX/RX/GND; never assume |
| RS-485 | Long sensor cable | Differential pair, topology/termination/bias per transceiver; isolation/surge protection |
| I2C / SPI | On-board sensors | Short traces; verify logic voltage and pinout |
| BLE | Phone / environmental sensor | Pairing and identity; not deterministic long-range |
| LoRa | Small signed event metadata | Approved regional band, compliant module/antenna and airtime |

## Power-budget worksheet
For each load record input voltage, peak/average current, duty cycle, startup current, daily Wh, converter efficiency, battery usable capacity at minimum temperature/age, worst-month solar yield, autonomy days, fuse, wire gauge and connector ratings.

Daily energy = sum(voltage × average current × operating hours) / 1000 Wh.
Battery nominal energy = daily energy × autonomy days / usable depth-of-discharge / conversion efficiency.
PV sizing must use site-specific worst-month irradiation and losses, not a generic panel size.

## Electrical and radio safety boundary
This reference intentionally covers low-voltage DC only. Do not use it as DIY mains wiring guidance. AC mains, building wiring, lightning protection, mast bonding and permanent outdoor electrical installations must be designed/installed/inspected by qualified professionals under applicable rules. Do not modify RF power amplifiers, bypass regulatory limits or use unapproved antenna combinations. Germany/EU operation must comply with current BNetzA frequency, power, duty-cycle/channel-access and RED/CE requirements for the exact equipment/band. Do not attach transmitters to wildlife without separate expert animal-welfare and legal review.

## Drawing release checklist
A build-to-print drawing needs exact part numbers/revisions, datasheets, pinout, wire gauge/length, fuse, voltage/current limits, connector ratings, enclosure/IP rating, thermal analysis, RF configuration, firmware, assembly steps and independent review. These generic diagrams are not build-to-print drawings.

## Design E – smartphone-only participant client

The first mobile implementation is a local-first PWA in `mobile-pwa/`. The phone uses its built-in camera/photo picker, one-shot location and optional orientation sensor only after a user action. Reports stay in IndexedDB; a manually initiated export contains only the Source-API-v1 metadata fields. It does not pair to MeshCore radios or continuously track location. See [MOBILE-PWA-ACCEPTANCE.md](MOBILE-PWA-ACCEPTANCE.md).

## Detailed low-voltage wiring templates

The connector-level examples, UART/I²C signal direction, RS-485 bus topology, DC fuse/power-tree checklist and procurement/BOM template are documented in [LOW-VOLTAGE-WIRING-TEMPLATES.md](LOW-VOLTAGE-WIRING-TEMPLATES.md). They deliberately avoid universal GPIO numbers or unverified part numbers; the exact board revision and datasheets must be selected before a build-to-print schematic can be released.
