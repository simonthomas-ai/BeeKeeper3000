# BeeKeeper3000 – low-voltage wiring templates

Status: conceptual reference wiring only. Exact board revisions, part numbers, conductor sizes and fuses must be selected from datasheets and measured load before construction. These are not certified drawings.

## 1. Smartphone-only participant

```text
Android / iPhone
  ├─ integrated camera → user-selected photo → local PWA storage
  ├─ GPS/compass → one-shot permission → local-only metadata
  └─ Wi-Fi / mobile data → manual metadata export only
No extra electronics, radio or power wiring required.
```

## 2. USB GNSS receiver (UART TTL alternative)

```text
USB GNSS receiver ──USB──> Edge PC / Raspberry Pi

UART breakout (only after voltage check):
GNSS TX ───────────────> Host RX
GNSS RX <─────────────── Host TX (optional configuration)
GNSS GND ────────────── Host GND
GNSS VCC <───────────── documented regulated supply
```

Check 3.3 V/5 V logic levels and supply voltage on the exact receiver. Never connect a 5 V UART output to a 3.3 V-only input. Record NMEA fix quality, HDOP/accuracy and timestamp; do not infer accuracy from coordinates alone.

## 3. Environmental sensors over isolated RS-485 / Modbus RTU

```text
Sensor A A(+) ───────────────┐
Sensor B A(+) ───────────────┼── twisted pair A(+) ── Isolated RS-485 A
Sensor A B(-) ───────────────┤
Sensor B B(-) ───────────────┴── twisted pair B(-) ── Isolated RS-485 B
Sensor bus reference/shield ───── per transceiver/site design only
Gateway USB/UART ──────────────── Edge host
120-ohm termination only at the two physical bus ends, when required.
```

Use one linear bus, not a star, unless the selected transceiver/network explicitly permits it. Set bias and termination per vendor data. Outdoor lines need galvanic isolation and surge protection appropriate to the installation.

## 4. Solar DC power tree (concept)

```text
PV panel → matched MPPT/PWM controller ↔ protected battery/BMS
                                      |
Battery positive → DC fuse near battery → DC distribution
                                      ├─ regulated supply → edge host
                                      ├─ rated DC supply → camera
                                      └─ rated DC supply → radio / sensors
All returns → engineered common/isolated return scheme per device datasheets
```

Do not connect a panel directly to a battery or SBC. Calculate Wh/day from measured peak and average loads, startup currents, duty cycle, temperature, autonomy days and worst-month irradiation. Select fuse, wire gauge, connector, BMS, converter and enclosure by datasheet and derating. AC mains wiring, building wiring, lightning protection, mast bonding and permanent outdoor installation require qualified professionals.

## 5. Bill-of-materials template

| Item | Required evidence before ordering |
|---|---|
| Edge host / phone | Exact model/revision, OS and supported interfaces |
| Camera / GNSS / sensor | Datasheet, pinout, voltage, current, environmental rating |
| Radio module | Exact firmware, permitted band/power/airtime, antenna approval |
| Power supply / converter | Input range, regulated output, continuous/peak current, thermal rating |
| Fuse / holder / conductor | DC interrupt rating, current curve, cable length, temperature and voltage drop |
| Enclosure / glands | IP rating, UV/temperature, condensation and service access |
| Surge / isolation | Installation-specific rated device and grounding design |

No universal GPIO pin numbers or unverified part numbers are supplied. The final build-to-print drawing must be reviewed against exact manufacturer datasheets and by a qualified electrical/radio professional. Do not DIY mains wiring or modify transmitter power/antenna limits.