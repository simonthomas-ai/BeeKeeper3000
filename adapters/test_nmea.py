import asyncio
import unittest

from adapters.lifecycle import AdapterConfigurationError, validate_metadata_event
from adapters.nmea import Nmea0183Parser, NmeaSerialAdapter, _checksum_body


def sentence(body):
    checksum = 0
    for character in body:
        checksum ^= ord(character)
    return ("$" + body + "*" + format(checksum, "02X") + "\r\n").encode("ascii")


RMC = "GPRMC,120000.00,A,4807.038,N,01131.000,E,0.0,0.0,230394,,,A"
GGA = "GPGGA,120000.00,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,"
HDT = "GPHDT,87.5,T"


class FakeSerial:
    def __init__(self, port, *, baudrate, timeout, write_timeout):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.write_timeout = write_timeout
        self.lines = []
        self.is_open = True
        self.closed = False

    def read_until(self, terminator, size):
        if not self.lines:
            return b""
        line = self.lines.pop(0)
        return line[:size]

    def close(self):
        self.is_open = False
        self.closed = True


class NmeaParserTests(unittest.TestCase):
    def test_checksum_parser_combines_gga_rmc_and_true_heading(self):
        parser = Nmea0183Parser()
        self.assertTrue(parser.feed(sentence(RMC), received_monotonic=100.0))
        self.assertIsNone(parser.fix)
        self.assertTrue(parser.feed(sentence(GGA), received_monotonic=100.1))
        self.assertIsNotNone(parser.fix)
        self.assertAlmostEqual(parser.fix.latitude_degrees, 48.1173, places=5)
        self.assertAlmostEqual(parser.fix.longitude_degrees, 11.5166667, places=5)
        self.assertEqual(parser.fix.fix_quality, 1)
        self.assertEqual(parser.fix.satellites, 8)
        self.assertAlmostEqual(parser.fix.hdop, 0.9)
        self.assertEqual(parser.fix.captured_at.isoformat(), "1994-03-23T12:00:00+00:00")

        self.assertTrue(parser.feed(sentence(HDT), received_monotonic=100.2))
        self.assertAlmostEqual(parser.heading.true_degrees, 87.5)
        self.assertEqual(parser.heading.source, "HDT_TRUE")

    def test_rejects_invalid_checksum_and_non_ascii(self):
        parser = Nmea0183Parser()
        with self.assertRaisesRegex(ValueError, "checksum_mismatch"):
            parser.feed(b"$GPHDT,87.5,T*00\r\n")
        with self.assertRaisesRegex(ValueError, "non_ascii"):
            parser.feed(b"$GPHDT,\xff,T*00\r\n")

    def test_invalid_rmc_status_clears_previous_fix(self):
        parser = Nmea0183Parser()
        parser.feed(sentence(RMC), received_monotonic=100.0)
        parser.feed(sentence(GGA), received_monotonic=100.1)
        self.assertIsNotNone(parser.fix)
        void = "GPRMC,120001.00,V,4807.038,N,01131.000,E,0.0,0.0,230394,,,N"
        parser.feed(sentence(void), received_monotonic=101.0)
        self.assertIsNone(parser.fix)

    def test_rejects_coordinate_and_quality_ranges(self):
        parser = Nmea0183Parser()
        with self.assertRaisesRegex(ValueError, "coordinate_out_of_range"):
            parser.feed(sentence(
                "GPRMC,120000.00,A,9060.000,N,01131.000,E,0.0,0.0,230394,,,A"
            ))
        with self.assertRaisesRegex(ValueError, "hdop_out_of_range"):
            parser.feed(sentence(
                "GPGGA,120000.00,4807.038,N,01131.000,E,1,08,101,545.4,M,46.9,M,,"
            ))

    def test_stale_gga_and_rmc_pair_is_rejected(self):
        parser = Nmea0183Parser()
        parser.feed(sentence(RMC), received_monotonic=100.0)
        parser.feed(sentence(GGA), received_monotonic=103.0)
        self.assertIsNone(parser.fix)

    def test_midnight_rollover_uses_nearest_rmc_date(self):
        parser = Nmea0183Parser()
        rmc = "GPRMC,235959.80,A,4807.038,N,01131.000,E,0.0,0.0,230394,,,A"
        gga = "GPGGA,000000.20,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,"
        parser.feed(sentence(rmc), received_monotonic=100.0)
        parser.feed(sentence(gga), received_monotonic=100.1)
        self.assertEqual(parser.fix.captured_at.isoformat(), "1994-03-24T00:00:00.200000+00:00")

    def test_dead_reckoning_and_simulated_gga_fixes_are_rejected(self):
        parser = Nmea0183Parser()
        parser.feed(sentence(RMC), received_monotonic=100.0)
        for quality in (6, 7, 8):
            gga = f"GPGGA,120000.00,4807.038,N,01131.000,E,{quality},08,0.9,545.4,M,46.9,M,,"
            parser.feed(sentence(gga), received_monotonic=100.1)
            self.assertIsNone(parser.fix)

    def test_only_matching_rmc_and_gga_positions_produce_fix(self):
        parser = Nmea0183Parser()
        parser.feed(sentence(RMC), received_monotonic=100.0)
        mismatched = "GPGGA,120000.00,4907.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,"
        parser.feed(sentence(mismatched), received_monotonic=100.1)
        self.assertIsNone(parser.fix)

    def test_hdm_requires_explicit_declination_and_hdg_requires_corrections(self):
        parser = Nmea0183Parser()
        self.assertFalse(parser.feed(sentence("HCHDM,82.0,M"), received_monotonic=10.0))
        calibrated = Nmea0183Parser(magnetic_declination_degrees=5.0)
        self.assertTrue(calibrated.feed(sentence("HCHDM,82.0,M"), received_monotonic=10.0))
        self.assertAlmostEqual(calibrated.heading.true_degrees, 87.0)
        self.assertEqual(calibrated.heading.source, "HDM_WITH_CONFIGURED_DECLINATION")
        with self.assertRaisesRegex(ValueError, "corrections_missing"):
            calibrated.feed(sentence("HCHDG,100.0,,,,"), received_monotonic=10.0)

    def test_hdg_applies_east_positive_west_negative_corrections(self):
        parser = Nmea0183Parser()
        parser.feed(sentence("HCHDG,100.0,2.0,E,3.0,W"), received_monotonic=10.0)
        self.assertAlmostEqual(parser.heading.true_degrees, 99.0)
        self.assertEqual(parser.heading.source, "HDG_WITH_SENTENCE_CORRECTIONS")

    def test_rejects_overlong_and_unframed_sentences(self):
        with self.assertRaisesRegex(ValueError, "too_long"):
            _checksum_body(b"$" + b"A" * 130 + b"*00\r\n")
        with self.assertRaisesRegex(ValueError, "framing"):
            _checksum_body(b"GPGGA,invalid*00\r\n")


class NmeaSerialAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_serial_adapter_emits_bearing_without_exact_coordinates(self):
        created = []

        def factory(port, *, baudrate, timeout, write_timeout):
            serial = FakeSerial(port, baudrate=baudrate, timeout=timeout, write_timeout=write_timeout)
            serial.lines = [sentence(RMC), sentence(GGA), sentence(HDT)]
            created.append(serial)
            return serial

        adapter = NmeaSerialAdapter(
            port="/dev/ttyUSB0",
            station_id="station-01",
            permission_granted=True,
            calibrated_heading_accuracy_degrees=2.0,
            serial_factory=factory,
        )
        await adapter.discover()
        self.assertTrue((await adapter.capabilities())["nmea_serial"])
        self.assertTrue((await adapter.permissions())["serial_device_access"])
        await adapter.start()
        self.assertEqual(created[0].baudrate, 4800)

        self.assertIsNone(await adapter.read_event(1.0))
        self.assertIsNone(await adapter.read_event(1.0))
        event = await adapter.read_event(1.0)
        self.assertIsNotNone(event)
        self.assertEqual(event["event_type"], "bearing")
        self.assertEqual(event["candidate_taxon"], "unknown")
        self.assertEqual(event["verification_status"], "unverified")
        self.assertEqual(event["station_id"], "station-01")
        self.assertEqual(event["bearing_deg"], 87.5)
        self.assertEqual(event["bearing_sigma_deg"], 2.0)
        self.assertIn("expires_at", event)
        self.assertNotIn("latitude", event)
        self.assertNotIn("longitude", event)
        self.assertNotIn("coordinates", event)
        self.assertNotIn("nmea_sentence", event)
        validate_metadata_event(event)

        await adapter.stop()
        self.assertTrue(created[0].closed)

    async def test_requires_explicit_permission_before_serial_creation(self):
        called = []

        def factory(*args, **kwargs):
            called.append(True)
            return FakeSerial(*args, **kwargs)

        with self.assertRaisesRegex(AdapterConfigurationError, "permission"):
            NmeaSerialAdapter(
                port="COM3", station_id="station-01",
                permission_granted=False,
                calibrated_heading_accuracy_degrees=2.0,
                serial_factory=factory,
            )
        self.assertEqual(called, [])

    async def test_bad_lines_are_discarded_without_leaking_raw_sentence(self):
        def factory(port, *, baudrate, timeout, write_timeout):
            serial = FakeSerial(port, baudrate=baudrate, timeout=timeout, write_timeout=write_timeout)
            serial.lines = [b"$GPRMC,private-invalid*00\r\n", sentence(RMC), sentence(GGA), sentence(HDT)]
            return serial

        adapter = NmeaSerialAdapter(
            port="COM3", station_id="station-01",
            permission_granted=True,
            calibrated_heading_accuracy_degrees=2.0,
            serial_factory=factory,
        )
        await adapter.discover()
        await adapter.start()
        self.assertIsNone(await adapter.read_event(1.0))
        self.assertIsNone(await adapter.read_event(1.0))
        self.assertIsNone(await adapter.read_event(1.0))
        event = await adapter.read_event(1.0)
        self.assertEqual(event["event_type"], "bearing_observation")
        self.assertNotIn("private-invalid", str(event))
        await adapter.stop()


if __name__ == "__main__":
    unittest.main()
