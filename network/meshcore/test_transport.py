import asyncio
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from Crypto.PublicKey import ECC
from meshcore.events import EventType

from network.meshcore.transport import MeshCoreSerialTransport, MeshCoreTransportError


class FakeCommands:
    def __init__(self, result_type):
        self.result_type = result_type
        self.calls = []

    async def send_channel_data(self, channel, data_type, payload):
        self.calls.append((channel, data_type, bytes(payload)))
        return SimpleNamespace(type=self.result_type, payload={"reason": "test"})


class FakeClient:
    def __init__(self, result_type=EventType.OK):
        self.commands = FakeCommands(result_type)
        self.disconnected = False

    async def disconnect(self):
        self.disconnected = True

    def subscribe(self, event_type, callback):
        self.subscription_event_type = event_type
        self.subscription_callback = callback
        return "subscription-1"


class MeshCoreTransportTests(unittest.TestCase):
    def setUp(self):
        self.key = ECC.generate(curve="Ed25519")
        self.now = int(datetime.now(timezone.utc).timestamp())
        observed = datetime.fromtimestamp(self.now - 10, timezone.utc)
        expires = datetime.fromtimestamp(self.now + 300, timezone.utc)
        self.event = {
            "event_id": "transport-event-001",
            "station_id": "station-01",
            "observed_at": observed.isoformat().replace("+00:00", "Z"),
            "expires_at": expires.isoformat().replace("+00:00", "Z"),
            "event_type": "sighting",
            "candidate_taxon": "Vespa_velutina",
            "verification_status": "unverified",
            "confidence": 0.8,
        }
        self.transport = MeshCoreSerialTransport(
            port="COM5", channel=2, data_type=0xB301,
            station_id="station-01", signing_key=self.key,
        )

    def test_send_event_uses_configured_channel_and_binary_payload(self):
        client = FakeClient()
        self.transport._meshcore = client
        self.transport._event_type_error = EventType.ERROR
        result = asyncio.run(self.transport.send_event(self.event))
        self.assertEqual(result["channel"], 2)
        self.assertEqual(result["data_type"], 0xB301)
        self.assertEqual(result["bytes"], len(client.commands.calls[0][2]))
        self.assertEqual(client.commands.calls[0][:2], (2, 0xB301))

    def test_station_mismatch_rejected(self):
        self.transport._meshcore = FakeClient()
        self.transport._event_type_error = EventType.ERROR
        with self.assertRaises(MeshCoreTransportError):
            asyncio.run(self.transport.send_event(dict(self.event, station_id="another-station")))

    def test_radio_error_is_reported(self):
        client = FakeClient(EventType.ERROR)
        self.transport._meshcore = client
        self.transport._event_type_error = EventType.ERROR
        with self.assertRaises(MeshCoreTransportError):
            asyncio.run(self.transport.send_event(self.event))

    def test_requires_connect_before_send(self):
        with self.assertRaises(MeshCoreTransportError):
            asyncio.run(self.transport.send_event(self.event))

    def test_disconnect_is_idempotent(self):
        client = FakeClient()
        self.transport._meshcore = client
        asyncio.run(self.transport.disconnect())
        self.assertTrue(client.disconnected)
        self.assertIsNone(self.transport._meshcore)
        asyncio.run(self.transport.disconnect())

    def test_subscribe_rejects_oversized_and_malformed_payloads_before_callback(self):
        client = FakeClient()
        self.transport._meshcore = client
        received = []

        async def callback(payload):
            received.append(payload)

        subscription = asyncio.run(self.transport.subscribe(callback))
        self.assertEqual(subscription, "subscription-1")
        self.assertEqual(client.subscription_event_type, EventType.CHANNEL_DATA_RECV)

        def radio_event(payload_hex):
            return SimpleNamespace(payload={
                "channel_idx": 2,
                "data_type": 0xB301,
                "payload": payload_hex,
            })

        asyncio.run(client.subscription_callback(radio_event("00" * 164)))
        asyncio.run(client.subscription_callback(radio_event("not-hex")))
        asyncio.run(client.subscription_callback(radio_event("00" * 163)))
        self.assertEqual(received, [b"\x00" * 163])

    def test_configuration_bounds(self):
        with self.assertRaises(ValueError):
            MeshCoreSerialTransport(
                port="", channel=0, data_type=1, station_id="x", signing_key=self.key
            )
        with self.assertRaises(ValueError):
            MeshCoreSerialTransport(
                port="COM5", channel=256, data_type=1, station_id="x", signing_key=self.key
            )
        with self.assertRaises(ValueError):
            MeshCoreSerialTransport(
                port="COM5", channel=1, data_type=0, station_id="x", signing_key=self.key
            )


if __name__ == "__main__":
    unittest.main()
