import hashlib
import math
import os
import stat
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from Crypto.PublicKey import ECC

from network.meshcore.event_store import MeshCoreStoreError, SQLiteMeshCoreEventStore
from network.meshcore.protocol import decode_event, encode_event, public_key_fingerprint
from network.meshcore.receiver import MeshCoreEventReceiver, StationRegistry


def bearing_to(lat1, lon1, lat2, lon2):
    east = (lon2 - lon1) * 111_000 * math.cos(math.radians((lat1 + lat2) / 2))
    north = (lat2 - lat1) * 111_000
    return math.degrees(math.atan2(east, north)) % 360


class MeshCorePersistentStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "private", "meshcore.sqlite3")
        self.store = SQLiteMeshCoreEventStore(self.db_path, retention_days=30, max_rows=1000)
        self.private = ECC.generate(curve="Ed25519")
        self.public = self.private.public_key()
        self.fingerprint = public_key_fingerprint(self.public)
        self.now = int(datetime.now(timezone.utc).timestamp())
        self.observed = datetime.fromtimestamp(self.now - 10, timezone.utc)
        self.expires = datetime.fromtimestamp(self.now + 600, timezone.utc)

    def tearDown(self):
        self.tmp.cleanup()

    def make_decoded(self, *, station_id, event_id, event_type="sighting",
                     candidate_taxon="Vespa_velutina", confidence=0.9,
                     bearing_deg=None, sigma_deg=None):
        event = {
            "event_id": event_id,
            "station_id": station_id,
            "observed_at": self.observed.isoformat().replace("+00:00", "Z"),
            "expires_at": self.expires.isoformat().replace("+00:00", "Z"),
            "event_type": event_type,
            "candidate_taxon": candidate_taxon,
            "verification_status": "unverified",
            "confidence": confidence,
        }
        if bearing_deg is not None:
            event["bearing_deg"] = bearing_deg
            event["bearing_sigma_deg"] = sigma_deg
        packet = encode_event(event, self.private, now_epoch=self.now)
        decoded = decode_event(packet, {self.fingerprint: self.public}, now_epoch=self.now)
        return event, packet, decoded

    def test_duplicate_is_prevented_across_store_restart(self):
        _, packet, decoded = self.make_decoded(
            station_id="station-west", event_id="persistent-event-001"
        )
        first_receiver = MeshCoreEventReceiver(
            transport=object(),
            trusted_public_keys={self.fingerprint: self.public},
            trusted_station_keys={
                hashlib.sha256(b"station-west").digest()[:16].hex(): {self.fingerprint}
            },
            station_registry=StationRegistry({}),
            sink=self.store,
        )
        self.assertTrue(__import__("asyncio").run(first_receiver.handle_payload(packet)))
        self.assertEqual(self.store.count(), 1)

        reopened_store = SQLiteMeshCoreEventStore(self.db_path, retention_days=30, max_rows=1000)
        second_receiver = MeshCoreEventReceiver(
            transport=object(),
            trusted_public_keys={self.fingerprint: self.public},
            trusted_station_keys={
                hashlib.sha256(b"station-west").digest()[:16].hex(): {self.fingerprint}
            },
            station_registry=StationRegistry({}),
            sink=reopened_store,
        )
        self.assertFalse(__import__("asyncio").run(second_receiver.handle_payload(packet)))
        self.assertEqual(second_receiver.duplicate_count, 1)
        self.assertEqual(second_receiver.accepted_count, 0)
        self.assertEqual(reopened_store.count(), 1)

    def test_conflicting_same_event_id_is_rejected(self):
        _, _, decoded = self.make_decoded(
            station_id="station-west", event_id="persistent-event-002"
        )
        self.assertTrue(self.store(decoded, None))
        changed = dict(decoded, confidence=0.2)
        with self.assertRaises(MeshCoreStoreError):
            self.store(changed, None)
        self.assertEqual(self.store.count(), 1)

    def test_rejects_unapproved_extra_fields(self):
        _, _, decoded = self.make_decoded(
            station_id="station-west", event_id="persistent-event-003"
        )
        with self.assertRaises(MeshCoreStoreError):
            self.store(dict(decoded, image_path="private.jpg"), None)
        with self.assertRaises(MeshCoreStoreError):
            self.store(dict(decoded, latitude=51.2, longitude=6.8), None)
        self.assertEqual(self.store.count(), 0)

    def test_private_posix_storage_permissions(self):
        self.store(self.make_decoded(
            station_id="station-west", event_id="persistent-event-004"
        )[2], None)
        if os.name == "posix":
            self.assertEqual(stat.S_IMODE(os.stat(os.path.dirname(self.db_path)).st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(os.stat(self.db_path).st_mode), 0o600)

    def test_receiver_resolves_station_and_store_persists_local_bearing(self):
        station_hash = hashlib.sha256(b"station-east").digest()[:16].hex()
        registry = StationRegistry({
            station_hash: {
                "station_id": "site-east",
                "latitude": 51.234,
                "longitude": 6.789,
            }
        })
        _, packet, decoded = self.make_decoded(
            station_id="station-east",
            event_id="persistent-bearing-001",
            event_type="bearing",
            bearing_deg=81.25,
            sigma_deg=2.5,
        )
        bearing = registry.bearing(decoded)
        self.assertTrue(self.store(decoded, bearing))
        rows = self.store.list_events()
        self.assertEqual(rows[0]["station_id"], "site-east")
        self.assertEqual(rows[0]["station_latitude"], 51.234)
        self.assertEqual(rows[0]["bearing_deg"], 81.25)
        self.assertNotIn("latitude", decoded)
        self.assertNotIn("longitude", decoded)

    def test_recent_bearings_triangulate_three_local_stations(self):
        target = (51.0000, 7.0000)
        stations = [
            ("station-a", "site-a", 51.0000, 6.9950),
            ("station-b", "site-b", 50.9960, 7.0040),
            ("station-c", "site-c", 51.0050, 7.0060),
        ]
        registry_entries = {}
        prepared = []
        for index, (raw_id, stable_id, latitude, longitude) in enumerate(stations):
            station_hash = hashlib.sha256(raw_id.encode("utf-8")).digest()[:16].hex()
            registry_entries[station_hash] = {
                "station_id": stable_id,
                "latitude": latitude,
                "longitude": longitude,
            }
            azimuth = bearing_to(latitude, longitude, *target)
            _, _, decoded = self.make_decoded(
                station_id=raw_id,
                event_id=f"triangulation-event-{index:02d}",
                event_type="bearing",
                bearing_deg=azimuth,
                sigma_deg=2.0,
            )
            prepared.append((decoded, registry_entries[station_hash]))

        registry = StationRegistry(registry_entries)
        for event, _ in prepared:
            self.assertTrue(self.store(event, registry.bearing(event)))

        estimate = self.store.triangulate_recent(window_seconds=1800)
        self.assertAlmostEqual(estimate.latitude, target[0], places=4)
        self.assertAlmostEqual(estimate.longitude, target[1], places=4)
        self.assertEqual(estimate.bearing_count, 3)
        self.assertEqual(estimate.status, "search_hypothesis")

    def test_bearing_requires_local_registry_resolution(self):
        _, _, decoded = self.make_decoded(
            station_id="station-missing",
            event_id="persistent-bearing-missing",
            event_type="bearing",
            bearing_deg=90,
            sigma_deg=3,
        )
        with self.assertRaises(MeshCoreStoreError):
            self.store(decoded, None)

    def test_list_limit_is_bounded(self):
        with self.assertRaises(ValueError):
            self.store.list_events(501)


if __name__ == "__main__":
    unittest.main()
