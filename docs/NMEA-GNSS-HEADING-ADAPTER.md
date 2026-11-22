# NMEA 0183 GNSS/True-heading adapter

Status (22 November 2026): **Software adapter merged into `main` via PR #105; Linux/Windows parser and fake-serial regression tests added via PR #107. Post-merge Quality Gates and CodeQL were reported successful for commit `3b4f8953c7e82ce96010f5095577830ce90e8361` ([Quality Gates](https://github.com/simonthomas-ai/BeeKeeper3000/actions/runs/45016389940), [CodeQL](https://github.com/simonthomas-ai/BeeKeeper3000/actions/runs/45016389962)). No physical GNSS receiver, compass, calibration, or field bearing has been accepted.**

## Supported NMEA sentences

| Sentence | Role | Acceptance |
|---|---|---|
| GGA | UTC time, fix quality, satellites, HDOP and position | Checksum-valid; position/UTC paired with RMC |
| RMC | Active/void navigation state, UTC date/time and position | Must be active; void status clears the current fix |
| HDT | True heading | Accepted directly as true-north heading |
| HDM | Magnetic heading | Rejected unless explicit magnetic declination is configured |
| HDG | Magnetic heading, deviation and variation | Both east/west correction fields are mandatory |

The parser requires the NMEA XOR checksum and ASCII framing. Coordinates are range-checked, GGA and RMC timestamps must be within one second and their received sentences within two seconds, and their coordinates must agree within 50 metres. GGA fix qualities 1–5 are accepted; dead-reckoning, manual and simulated qualities 6–8 are rejected. The adapter also enforces satellite count, HDOP, fix-age and heading/fix pairing limits.

## Privacy and transport

Exact latitude/longitude are held only in the parser's in-memory NmeaFix. They are not emitted in the adapter event, not added to the station outbox, and not placed in the MeshCore payload. The adapter produces the existing signed MeshCore bearing event shape:

- random event ID, station ID and UTC observation/expiry timestamps
- event_type=bearing, candidate_taxon=unknown, verification_status=unverified
- bearing_deg and calibrated bearing_sigma_deg

The separate MeshCore transport signs the event with Ed25519. The receiver resolves the station's coordinates from its **receiver-local station registry**; the radio packet contains only a station hash and bearing data. Do not provision the station registry in a public repository.

A heading is not a GNSS course-over-ground value. HDT means true heading; a magnetic heading needs an explicit and correctly signed declination or the sentence's own corrections. The configured calibrated_heading_accuracy_degrees is a required uncertainty input and must come from a device-specific calibration record, not an arbitrary optimistic default.

## Optional dependency

pySerial is installed only on a station that actually uses a local serial receiver:

~~~powershell
python -m pip install --requirement adapters/nmea-requirements.lock
~~~

The lock currently pins pySerial 3.5. The parser and fake-serial tests do not require pySerial; the real serial driver is loaded lazily only when the adapter is discovered. Serial paths must be explicitly selected and local; URL-style network serial paths are rejected.

## Operator example

~~~python
import asyncio

from adapters.lifecycle import AdapterSpec, AdapterSupervisor
from adapters.nmea import NmeaSerialAdapter

adapter = NmeaSerialAdapter(
    port="COM3",  # Linux example: /dev/serial/by-id/...
    station_id="station-01",
    permission_granted=True,  # explicit operator consent to open this port
    calibrated_heading_accuracy_degrees=2.0,  # replace with calibration evidence
    baudrate=4800,
    # Set only from a trusted, documented declination source when the receiver
    # supplies HDM rather than HDT. East is positive; west is negative.
    magnetic_declination_degrees=None,
)

spec = AdapterSpec(
    adapter_id="gnss.nmea0183",
    version="1.0.0",
    source_type="positioning",
    required_capabilities=("nmea_serial", "nmea0183_parser"),
    required_permissions=("serial_device_access",),
)

async def send_to_meshcore(event):
    # A separately configured MeshCoreSerialTransport signs this event.
    await meshcore_transport.send_event(dict(event))

async def main():
    stop = asyncio.Event()
    supervisor = AdapterSupervisor(spec, adapter)
    try:
        await supervisor.run_forever(send_to_meshcore, stop)
    finally:
        stop.set()

asyncio.run(main())
~~~

The example intentionally uses a separate meshcore_transport configured with its own serial device, channel, data type and protected Ed25519 private key. Never store that private key in this file, a source-control repository or a command-line argument. Run the transport under the station service account with restrictive filesystem ACLs.

## Tests

~~~sh
python -m unittest adapters.test_nmea -v
python -m unittest network.meshcore.test_nmea_integration -v
~~~

Tests cover checksum failures, malformed ASCII/framing, coordinate and fix-quality ranges, stale/mismatched GGA/RMC fixes, midnight rollover, magnetic-to-true conversion rules, east/west corrections, serial permission, cleanup and a signed MeshCore encode/decode round-trip without coordinates.

## Acceptance still required

Before assigning hardware-tested status, record the exact GNSS/compass manufacturer, model, firmware, NMEA output sentences, datum, baud rate, antenna and mounting orientation, true-vs-magnetic heading source, declination source/date, calibration procedure, measured heading error (including hard-/soft-iron effects), time synchronization, loss-of-fix response, reconnect behaviour and a test against a surveyed reference bearing. Repeat over different headings, distances, temperature and supply conditions.

No station is field-validated by these software tests. The event remains an **unverified bearing**, not a species confirmation or nest location.
