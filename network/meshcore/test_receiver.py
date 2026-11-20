import asyncio
import unittest
from datetime import datetime, timezone

from Crypto.PublicKey import ECC

from network.meshcore.protocol import encode_event, public_key_fingerprint
from network.meshcore.receiver import (
    MeshCoreEventReceiver,
    StationRegistry,
    StationRegistryError,
)


class MeshCoreReceiverTests(unittest.TestCase):
    def setUp(self):
        self.private = ECC.generate(curve="Ed25519")
        self.public = self.private.public_key()
        self.fingerprint = public_key_fingerprint(self.public)
        self.now = int(datetime.now(timezone.utc).timestamp())
        self.observed = datetime.fromtimestamp(self.now - 10, timezone.utc).isoformat().replace("+00:00", "Z")
        self.expires = datetime.fromtimestamp(self.now + 300, timezone.utc).isoformat().replace("+00:00", "Z")
        self.event = {
            "event_id": "receiver-event-001",
            "station_id": "station-north",
            "observed_at": self.observed,
            "expires_at": self.expires,
            "event_type": "bearing",
            "candidate_taxon": "Vespa_velutina",
            "verification_status": "unverified",
            "confidence": 0.9,
            "bearing_deg": 81.25,
            "bearing_sigma_deg": 2.5,
        }
        # The station identifier hash is derived exactly as in protocol v1.
        import hashlib
        station_hash = hashlib.sha256(b"station-north").digest()[:16].hex()
        self.station_hash = station_hash
        self.registry = StationRegistry({
            station_hash: {
                "station_id": "north-roof",
                "latitude": 51.234,
                "longitude": 6.789,
            }
        })

    def test_station_registry_resolves_private_local_coordinates(self):
        event = {
            "event_type": "bearing",
            "station_id": next(iter(self.registry._entries)),
            "observed_at": self.observed,
            "bearing_deg": 81.25,
            "bearing_sigma_deg": 2.5,
        }
        result = self.registry.bearing(event)
        self.assertEqual(result.station_id, "north-roof")
        self.assertAlmostEqual(result.latitude, 51.234)
        self.assertAlmostEqual(result.longitude, 6.789)
        self.assertAlmostEqual(result.azimuth_deg, 81.25)

    def test_invalid_registry_rejected(self):
        with self.assertRaises(StationRegistryError):
            StationRegistry({"invalid": {"station_id": "a", "latitude": 91, "longitude": 0}})

    def test_signed_event_delivered_once_with_local_bearing(self):
        received = []
        receiver = MeshCoreEventReceiver(
            transport=object(),
            trusted_public_keys={self.fingerprint: self.public},
            trusted_station_keys={self.station_hash: {self.fingerprint}},
            station_registry=self.registry,
            sink=lambda event, bearing: received.append((event, bearing)),
        )
        payload = encode_event(self.event, self.private, now_epoch=self.now)
        self.assertTrue(asyncio.run(receiver.handle_payload(payload)))
        self.assertFalse(asyncio.run(receiver.handle_payload(payload)))
        self.assertEqual(receiver.accepted_count, 1)
        self.assertEqual(receiver.duplicate_count, 1)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0][0]["station_id"], next(iter(self.registry._entries)))
        self.assertEqual(received[0][1].station_id, "north-roof")

    def test_unknown_station_hash_rejected_without_forwarding(self):
        received = []
        receiver = MeshCoreEventReceiver(
            transport=object(),
            trusted_public_keys={self.fingerprint: self.public},
            trusted_station_keys={self.station_hash: {self.fingerprint}},
            station_registry=StationRegistry({}),
            sink=lambda event, bearing: received.append(event),
        )
        payload = encode_event(self.event, self.private, now_epoch=self.now)
        self.assertFalse(asyncio.run(receiver.handle_payload(payload)))
        self.assertEqual(receiver.rejected_count, 1)
        self.assertEqual(received, [])

    def test_signer_cannot_impersonate_another_station(self):
        second_private = ECC.generate(curve="Ed25519")
        second_public = second_private.public_key()
        second_fingerprint = public_key_fingerprint(second_public)
        received = []
        receiver = MeshCoreEventReceiver(
            transport=object(),
            trusted_public_keys={
                self.fingerprint: self.public,
                second_fingerprint: second_public,
            },
            trusted_station_keys={self.station_hash: {second_fingerprint}},
            station_registry=self.registry,
            sink=lambda event, bearing: received.append(event),
        )
        payload = encode_event(self.event, self.private, now_epoch=self.now)
        self.assertFalse(asyncio.run(receiver.handle_payload(payload)))
        self.assertEqual(receiver.rejected_count, 1)
        self.assertEqual(received, [])

    def test_receiver_requires_explicit_station_key_binding(self):
        with self.assertRaises(TypeError):
            MeshCoreEventReceiver(
                transport=object(),
                trusted_public_keys={self.fingerprint: self.public},
                station_registry=self.registry,
                sink=lambda event, bearing: None,
            )

    def test_async_sink_is_awaited(self):
        received = []
        async def sink(event, bearing):
            await asyncio.sleep(0)
            received.append(event["event_id"])
        receiver = MeshCoreEventReceiver(
            transport=object(),
            trusted_public_keys={self.fingerprint: self.public},
            trusted_station_keys={self.station_hash: {self.fingerprint}},
            station_registry=self.registry,
            sink=sink,
        )
        payload = encode_event(self.event, self.private, now_epoch=self.now)
        self.assertTrue(asyncio.run(receiver.handle_payload(payload)))
        self.assertEqual(len(received), 1)


if __name__ == "__main__":
    unittest.main()
