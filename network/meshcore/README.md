# BeeKeeper3000 MeshCore adapter

Optional serial adapter for MeshCore companion radios. The adapter sends compact signed metadata over MeshCore channel-data packets. It does not send photos, audio, GPS coordinates, personal names, free-form notes or camera credentials.

## Install

From the repository root, install the optional dependency file at network/meshcore/requirements.txt. The reviewed upstream binding is meshcore 2.3.19, MIT, Python 3.10 or newer. This library is optional and is not imported by the core triangulation runtime.

## Wire protocol v1

- Binary envelope with Ed25519 signature and 16-byte public-key fingerprint.
- Event and station identifiers are short SHA-256 identifiers.
- Transmits timestamps, expiry, event type, taxon, verification claim, confidence and optional bearing.
- Does not encode exact GPS, images, audio, filenames, credentials or free-form text.
- The payload is 128 bytes without a bearing and 132 bytes with a bearing, below the 163-byte MeshCore channel-data payload limit.
- Nest-hypothesis events are not accepted in v1 because the common schema requires a location for that event type and the radio envelope intentionally excludes coordinates.
- An expert-confirmed claim is downgraded to unverified unless the signing key is included in the explicit expert trust allowlist.

A valid signature proves possession of a configured private key, not biological correctness. All detections remain candidates until expert review.

## Configure

Create a dedicated Ed25519 key pair out of band and protect the private key using operating-system permissions or a hardware-backed key store. Do not commit either private or operational keys. Provision each receiving station with the public keys it trusts.

Instantiate MeshCoreSerialTransport with a serial port, channel index, application data type, the station ID and the station private key. Open a connection before sending events. Disconnect the transport during orderly shutdown. The implementation is in network/meshcore/transport.py.

For receiving, subscribe to the configured channel/data type and pass raw payload bytes to decode_event with a public-key allowlist. The allowlist is keyed by the 32-character public-key fingerprint. A separate trusted-expert fingerprint allowlist is needed to accept expert-confirmed claims.

## Operational limits

- No physical MeshCore radio, antenna, repeater or firmware was available for this build; RF transmission, duty-cycle, coverage and interoperability are not claimed as tested.
- Channel-data support requires compatible companion firmware. The upstream Python API provides send_channel_data and CHANNEL_DATA_RECV events.
- Receiving stations must provision public keys and map the short station identifier to a local station record and calibrated coordinates. Without that mapping, the bearing cannot be transformed into a geographic ray.
- This adapter is independent of Meshtastic, Freenet and Mosquitto. It does not activate those transports.
- Validate German/EU frequency, duty-cycle, channel-width and EIRP constraints for the selected hardware before deployment.

## Receive and convert bearings

A receiving station installs the MeshCore public-key allowlist and its own local
station registry. Station coordinates are not transmitted over the radio; the
receiver resolves the short station identifier to coordinates held locally.

The MeshCoreEventReceiver verifies Ed25519 signatures and expiry, rejects
unknown keys and unknown station hashes for bearing events, downgrades expert
claims unless the signer is in the explicit expert-key allowlist, filters
duplicates in a bounded in-memory cache and passes a normalized event plus an
optional local Bearing object to the application sink. The sink must persist
events idempotently across process restarts; the RAM cache is only an additional
short-term duplicate filter.

For triangulation, the local registry maps each signed station hash to a stable
station ID and calibrated latitude/longitude. Only a bearing event is converted
to a local network.triangulation.Bearing instance. No coordinate is added to
the radio packet.
