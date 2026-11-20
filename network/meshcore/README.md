# BeeKeeper3000 MeshCore adapter

Optional serial adapter for MeshCore companion radios. The adapter sends compact signed metadata over MeshCore channel-data packets. It does not send photos, audio, GPS coordinates, personal names, free-form notes or camera credentials.

## Install

From the repository root, install the optional dependency lock at `network/meshcore/requirements.lock`. The reviewed upstream binding is `meshcore==2.3.19`, MIT, Python 3.10 or newer. The current lock was captured for Linux CI only; resolve and test separately for Windows and target SBCs. This library is optional and is not imported by the core triangulation runtime.

## Wire protocol v1

- Binary envelope with Ed25519 signature and 16-byte public-key fingerprint.
- Event and station identifiers are short SHA-256 identifiers.
- Transmits timestamps, expiry, event type, taxon, verification claim, confidence and optional bearing.
- Does not encode exact GPS, images, audio, filenames, credentials or free-form text.
- Payload is 128 bytes without a bearing and 132 bytes with a bearing, below the 163-byte MeshCore channel-data payload limit.
- Nest-hypothesis events are not accepted in v1 because the common schema requires a location for that event type and the radio envelope intentionally excludes coordinates.
- An expert-confirmed claim is downgraded to unverified unless the signing key is included in the explicit expert trust allowlist.

A valid signature proves possession of a configured private key, not biological correctness. All detections remain candidates until expert review.

## Configure

Create a dedicated Ed25519 key pair out of band and protect the private key using operating-system permissions or a hardware-backed key store. Do not commit either private or operational keys. Provision each receiving station with the public keys it trusts.

Instantiate `MeshCoreSerialTransport` with a serial port, channel index, application data type, station ID and station private key. Open a connection before sending events. Disconnect the transport during orderly shutdown. The implementation is in `network/meshcore/transport.py`.

For receiving, use `MeshCoreEventReceiver` with a public-key allowlist and a receiver-local `StationRegistry`. The allowlist is keyed by the 32-character public-key fingerprint. A separate trusted-expert fingerprint allowlist is required to accept expert-confirmed claims. In addition, every station hash must be explicitly bound to one or more authorized public-key fingerprints using `trusted_station_keys`. A key that is globally trusted but not authorized for a given station cannot submit events under that station's identity. Each signing fingerprint may be assigned to exactly one station; one station may temporarily have multiple fingerprints during rotation. Configure both old and new fingerprints for that station, verify the new station key, then remove the old fingerprint. Keep the public-key allowlist and station-key mapping local to the receiving station; never transmit private keys.

## Durable local event store

`SQLiteMeshCoreEventStore` in `network/meshcore/event_store.py` is an idempotent receiver sink:

```python
from network.meshcore.event_store import SQLiteMeshCoreEventStore
from network.meshcore.receiver import MeshCoreEventReceiver, StationRegistry

store = SQLiteMeshCoreEventStore(
    r"C:\BeeKeeper3000\data\meshcore-events.sqlite3",
    retention_days=30,
    max_rows=100_000,
)
registry = StationRegistry({
    # 32-hex station hash from the signed MeshCore protocol:
    "PUT_STATION_HASH_HERE": {
        "station_id": "yard-north",
        "latitude": 51.2345,
        "longitude": 6.7890,
    }
})
# Bind every station hash to its authorized signing-key fingerprint(s).
# Multiple fingerprints allow an explicit overlap period during key rotation.
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

The sink stores only events after signature, expiry and registry validation. Its unique event ID survives process restarts; exact packet replays return `False` from the sink and are counted as duplicates. A reused event ID with different signed content or a changed local station resolution is rejected rather than silently overwritten. Retention and maximum row count are bounded. On POSIX the store requires a service-owned private directory (mode 0700) and restricts SQLite files/sidecars to mode 0600. On Windows configure NTFS ACLs for the service identity. SQLite is not encrypted by this application; use full-disk encryption.

Station coordinates are receiver-local data: they are not transmitted over MeshCore. The stored station coordinates are only attached to bearing events after resolving the signed station hash through the local registry. They are not part of the signed radio event JSON.

## Receive and triangulate

`store.recent_bearings(window_seconds=1800)` returns the most recent bearing for each independent locally resolved station. `store.triangulate_recent()` calls the reference weighted least-squares estimator. It requires at least three stations, compatible timestamps and stable crossing geometry; an output is only a `search_hypothesis`, never a confirmed nest. Survey calibration, outlier rejection, uncertainty geometry and independent field validation remain necessary before operational search use.

## Operational limits

- No physical MeshCore radio, antenna, repeater or firmware was available for this build; RF transmission, duty-cycle, coverage and interoperability are not claimed as tested.
- Channel-data support requires compatible companion firmware. The upstream Python API provides `send_channel_data` and `CHANNEL_DATA_RECV` events.
- Receiving stations must provision public keys and map the short station identifier to a local station record and calibrated coordinates. Without that mapping, the bearing cannot be transformed into a geographic ray.
- The adapter is independent of Meshtastic, Freenet and Mosquitto. It does not activate those transports.
- Validate German/EU frequency, duty-cycle, channel-width and EIRP constraints for the selected hardware before deployment.
