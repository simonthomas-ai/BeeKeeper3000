import asyncio
import unittest
from datetime import datetime, timezone

from Crypto.PublicKey import ECC

from adapters.nmea import NmeaSerialAdapter
from network.meshcore.protocol import decode_event, encode_event, public_key_fingerprint


def sentence(body):
    checksum = 0
    for character in body:
        checksum ^= ord(character)
    return ("$" + body + "*" + format(checksum, "02X") + "\r\n").encode("ascii")


class FakeSerial:
    def __init__(self, port, *, baudrate, timeout, write_timeout, lines):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.write_timeout = write_timeout
        self.lines = list(lines)
        self.is_open = True

    def read_until(self, terminator, size):
        if not self.lines:
            return b""
        return self.lines.pop(0)[:size]

    def close(self):
        self.is_open = False


class NmeaMeshCoreIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_true_bearing_is_ed25519_signed_and_location_free_on_meshcore_wire(self):
        captured = datetime.now(timezone.utc)
        time_field = captured.strftime("%H%M%S.%f")
        date_field = captured.strftime("%d%m%y")
        rmc = (
            f"GPRMC,{time_field},A,4807.038,N,01131.000,E,"
            f"0.0,0.0,{date_field},,,A"
        )
        gga = (
            f"GPGGA,{time_field},4807.038,N,01131.000,E,"
            "1,08,0.9,545.4,M,46.9,M,,"
        )
        lines = [sentence(rmc), sentence(gga), sentence("GPHDT,87.5,T")]

        def serial_factory(port, *, baudrate, timeout, write_timeout):
            return FakeSerial(
                port,
                baudrate=baudrate,
                timeout=timeout,
                write_timeout=write_timeout,
                lines=lines,
            )

        adapter = NmeaSerialAdapter(
            port="COM-NMEA-TEST",
            station_id="station-01",
            permission_granted=True,
            calibrated_heading_accuracy_degrees=2.0,
            serial_factory=serial_factory,
        )
        await adapter.discover()
        await adapter.start()
        self.assertIsNone(await adapter.read_event(1.0))
        self.assertIsNone(await adapter.read_event(1.0))
        event = await adapter.read_event(1.0)
        await adapter.stop()

        self.assertIsNotNone(event)
        self.assertEqual(event["event_type"], "bearing")
        self.assertEqual(event["candidate_taxon"], "unknown")
        self.assertEqual(event["verification_status"], "unverified")
        self.assertNotIn("latitude", event)
        self.assertNotIn("longitude", event)
        self.assertNotIn("location", event)

        private_key = ECC.generate(curve="Ed25519")
        fingerprint = public_key_fingerprint(private_key)
        payload = encode_event(event, private_key, now_epoch=int(captured.timestamp()))
        decoded = decode_event(
            payload,
            {fingerprint: private_key.public_key()},
            now_epoch=int(captured.timestamp()),
        )

        self.assertEqual(decoded["event_type"], "bearing")
        self.assertEqual(decoded["candidate_taxon"], "unknown")
        self.assertEqual(decoded["verification_status"], "unverified")
        self.assertEqual(decoded["bearing_deg"], 87.5)
        self.assertEqual(decoded["bearing_sigma_deg"], 2.0)
        self.assertEqual(decoded["signature_key_id"], fingerprint)
        self.assertNotIn("latitude", decoded)
        self.assertNotIn("longitude", decoded)
        self.assertNotIn("location", decoded)
        self.assertEqual(len(payload), 132)


if __name__ == "__main__":
    unittest.main()
