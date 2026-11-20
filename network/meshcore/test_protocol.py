import unittest
from datetime import datetime, timezone

from Crypto.PublicKey import ECC

from network.meshcore.protocol import (
    MAX_WIRE_BYTES, MeshCoreProtocolError, decode_event, encode_event,
    public_key_fingerprint,
)


class MeshCoreProtocolTests(unittest.TestCase):
    def setUp(self):
        self.private = ECC.generate(curve="Ed25519")
        self.public = self.private.public_key()
        self.fingerprint = public_key_fingerprint(self.public)
        self.now = int(datetime.now(timezone.utc).timestamp())
        observed = datetime.fromtimestamp(self.now - 30, timezone.utc)
        expires = datetime.fromtimestamp(self.now + 300, timezone.utc)
        self.event = {
            "event_id": "test-event-000000000001",
            "station_id": "station-west-001",
            "observed_at": observed.isoformat().replace("+00:00", "Z"),
            "expires_at": expires.isoformat().replace("+00:00", "Z"),
            "event_type": "bearing",
            "candidate_taxon": "Vespa_velutina",
            "verification_status": "unverified",
            "confidence": 0.84,
            "bearing_deg": 142.5,
            "bearing_sigma_deg": 3.0,
            "latitude": 51.2,
            "longitude": 6.8,
            "image_path": "private/image.jpg",
        }

    def test_bearing_event_round_trip_signed_and_privacy_minimized(self):
        payload = encode_event(self.event, self.private, now_epoch=self.now)
        self.assertLessEqual(len(payload), MAX_WIRE_BYTES)
        self.assertEqual(len(payload), 116)
        decoded = decode_event(payload, {self.fingerprint: self.public}, now_epoch=self.now)
        self.assertEqual(decoded["event_type"], "bearing")
        self.assertEqual(decoded["candidate_taxon"], "Vespa_velutina")
        self.assertEqual(decoded["bearing_deg"], 142.5)
        self.assertEqual(decoded["bearing_sigma_deg"], 3.0)
        self.assertNotIn("latitude", decoded)
        self.assertNotIn("longitude", decoded)
        self.assertNotIn("image_path", decoded)
        self.assertEqual(decoded["signature_key_id"], self.fingerprint)

    def test_untrusted_expert_claim_is_downgraded(self):
        event = dict(self.event, verification_status="expert_confirmed")
        payload = encode_event(event, self.private, now_epoch=self.now)
        decoded = decode_event(payload, {self.fingerprint: self.public}, now_epoch=self.now)
        self.assertEqual(decoded["verification_status"], "unverified")
        decoded = decode_event(
            payload, {self.fingerprint: self.public},
            trusted_expert_fingerprints={self.fingerprint}, now_epoch=self.now
        )
        self.assertEqual(decoded["verification_status"], "expert_confirmed")

    def test_tampered_data_rejected(self):
        payload = bytearray(encode_event(self.event, self.private, now_epoch=self.now))
        payload[10] ^= 0x01
        with self.assertRaises(MeshCoreProtocolError):
            decode_event(payload, {self.fingerprint: self.public}, now_epoch=self.now)

    def test_unknown_key_rejected(self):
        payload = encode_event(self.event, self.private, now_epoch=self.now)
        with self.assertRaises(MeshCoreProtocolError):
            decode_event(payload, {}, now_epoch=self.now)

    def test_expired_event_rejected(self):
        past = datetime.fromtimestamp(self.now - 900, timezone.utc)
        expired = datetime.fromtimestamp(self.now - 600, timezone.utc)
        event = dict(
            self.event,
            observed_at=past.isoformat().replace("+00:00", "Z"),
            expires_at=expired.isoformat().replace("+00:00", "Z"),
        )
        with self.assertRaises(MeshCoreProtocolError):
            encode_event(event, self.private, now_epoch=self.now)

    def test_bearing_required_and_bounded(self):
        event = dict(self.event)
        event.pop("bearing_deg")
        with self.assertRaises(MeshCoreProtocolError):
            encode_event(event, self.private, now_epoch=self.now)
        event = dict(self.event, bearing_deg=360.0)
        with self.assertRaises(MeshCoreProtocolError):
            encode_event(event, self.private, now_epoch=self.now)

    def test_nest_hypothesis_not_allowed_without_location_protocol(self):
        event = dict(self.event, event_type="nest_hypothesis")
        with self.assertRaises(MeshCoreProtocolError):
            encode_event(event, self.private, now_epoch=self.now)

    def test_signature_is_64_bytes_and_fingerprint_is_stable(self):
        payload = encode_event(self.event, self.private, now_epoch=self.now)
        self.assertEqual(len(payload[-64:]), 64)
        self.assertEqual(public_key_fingerprint(self.public), self.fingerprint)


if __name__ == "__main__":
    unittest.main()
