import asyncio, os, tempfile, unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch
from Crypto.PublicKey import ECC
from network.meshcore.hardware_probe import load_private_key, make_test_event, run_probe

class FakeTransport:
    instances = []
    def __init__(self, **kwargs):
        self.kwargs, self.connected, self.sent, self.disconnected = kwargs, False, [], False
        self.instances.append(self)
    async def connect(self): self.connected = True
    async def send_event(self, event):
        self.sent.append(event)
        return {"bytes": 132, "channel": self.kwargs["channel"], "data_type": self.kwargs["data_type"]}
    async def disconnect(self): self.disconnected = True

class Args:
    port="COM5"; station_id="station-test"; signing_key=""
    channel=2; data_type=0xB301; baudrate=115200
    probe=False; transmit_test_packet=False

class HardwareProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/"probe-key.pem"
        self.path.write_text(ECC.generate(curve="Ed25519").export_key(format="PEM"), encoding="ascii")
        if os.name=="posix": self.path.chmod(0o600)
        self.args=Args(); self.args.signing_key=str(self.path)
        FakeTransport.instances.clear()
    def tearDown(self): self.tmp.cleanup()

    def test_event_is_short_lived_unverified_heartbeat(self):
        now=datetime(2026,11,20,12,0,tzinfo=timezone.utc)
        event=make_test_event("station-test",now=now)
        self.assertEqual(event["event_type"],"station_heartbeat")
        self.assertEqual(event["verification_status"],"unverified")
        self.assertEqual(event["candidate_taxon"],"unknown")
        self.assertEqual(event["confidence"],0.0)
        start=datetime.fromisoformat(event["observed_at"].replace("Z","+00:00"))
        end=datetime.fromisoformat(event["expires_at"].replace("Z","+00:00"))
        self.assertEqual(end-start,timedelta(minutes=5))

    def test_default_run_never_opens_serial_or_transmits(self):
        with patch("network.meshcore.hardware_probe.MeshCoreSerialTransport",FakeTransport):
            report=asyncio.run(run_probe(self.args))
        self.assertEqual(report["mode"],"dry_run")
        self.assertFalse(report["transmitted"])
        self.assertEqual(FakeTransport.instances,[])

    def test_probe_connects_and_disconnects_without_transmission(self):
        self.args.probe=True
        with patch("network.meshcore.hardware_probe.MeshCoreSerialTransport",FakeTransport):
            report=asyncio.run(run_probe(self.args))
        item=FakeTransport.instances[0]
        self.assertTrue(report["serial_connected"])
        self.assertFalse(report["transmitted"])
        self.assertEqual(item.sent,[])
        self.assertTrue(item.disconnected)

    def test_explicit_transmit_sends_exactly_one_heartbeat(self):
        self.args.probe=True; self.args.transmit_test_packet=True
        with patch("network.meshcore.hardware_probe.MeshCoreSerialTransport",FakeTransport):
            report=asyncio.run(run_probe(self.args))
        item=FakeTransport.instances[0]
        self.assertTrue(report["transmitted"])
        self.assertEqual(len(item.sent),1)
        self.assertEqual(item.sent[0]["event_type"],"station_heartbeat")
        self.assertEqual(item.sent[0]["verification_status"],"unverified")
        self.assertTrue(item.disconnected)

    def test_posix_rejects_group_or_world_readable_private_key(self):
        if os.name!="posix": self.skipTest("POSIX mode bits are not available")
        self.path.chmod(0o644)
        with self.assertRaises(PermissionError): load_private_key(str(self.path))

if __name__=="__main__": unittest.main()
