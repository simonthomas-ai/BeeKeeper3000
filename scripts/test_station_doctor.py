import json
import socket
import unittest
from unittest.mock import patch

from station_doctor import Report, _is_loopback_url, _version, check_bridge_config


class StationDoctorTests(unittest.TestCase):
    def test_report_fails_only_on_fail_status(self):
        report = Report()
        report.add("python", "PASS", "ok")
        report.add("camera", "WARN", "not configured")
        self.assertFalse(report.failed)
        report.add("source", "FAIL", "offline")
        self.assertTrue(report.failed)

    def test_json_report_has_machine_readable_status(self):
        report = Report()
        report.add("node", "PASS", "ok")
        self.assertEqual(report.checks[0].status, "PASS")
        self.assertEqual(json.loads(json.dumps({
            "checks": [item.__dict__ for item in report.checks]
        }))["checks"][0]["name"], "node")

    def test_loopback_urls_allowed(self):
        with patch("station_doctor.socket.getaddrinfo", return_value=[
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 8787))
        ]):
            self.assertTrue(_is_loopback_url("http://localhost:8787/api/events"))
            self.assertTrue(_is_loopback_url("http://127.0.0.1:8787/api/events"))

    def test_non_loopback_and_bad_urls_rejected(self):
        with patch("station_doctor.socket.getaddrinfo", return_value=[
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.10", 8787))
        ]):
            self.assertFalse(_is_loopback_url("http://station.local:8787/api/events"))
        self.assertFalse(_is_loopback_url("file:///etc/passwd"))
        self.assertFalse(_is_loopback_url("http://"))

    def test_cursor_fallback_is_blocked(self):
        report = Report()
        with patch.dict("os.environ", {"BRIDGE_REQUIRE_CURSOR": "false"}):
            check_bridge_config(report)
        self.assertEqual(report.checks[0].status, "FAIL")

    def test_cursor_requirement_missing_is_warning(self):
        report = Report()
        with patch.dict("os.environ", {}, clear=True):
            check_bridge_config(report)
        self.assertEqual(report.checks[0].status, "WARN")

    def test_python_version_parser_handles_missing(self):
        with patch("station_doctor.shutil.which", return_value=None):
            self.assertIsNone(_version("node"))


if __name__ == "__main__":
    unittest.main()
