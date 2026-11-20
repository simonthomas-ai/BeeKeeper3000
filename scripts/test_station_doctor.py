import json
import threading
import unittest
from unittest import mock
from http.server import BaseHTTPRequestHandler, HTTPServer

from station_doctor import Report, _is_loopback_url, _request, _version, check_bridge_config


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

    def test_only_literal_loopback_addresses_are_allowed(self):
        self.assertTrue(_is_loopback_url("http://127.0.0.1:8787/api/events"))
        self.assertTrue(_is_loopback_url("http://127.0.0.2:8787/api/events"))
        self.assertTrue(_is_loopback_url("http://[::1]:8787/api/events"))
        self.assertFalse(_is_loopback_url("http://localhost:8787/api/events"))
        self.assertFalse(_is_loopback_url("http://station.local:8787/api/events"))
        self.assertFalse(_is_loopback_url("http://192.168.1.10:8787/api/events"))
        self.assertFalse(_is_loopback_url("http://user:secret@127.0.0.1:8787/api/events"))
        self.assertFalse(_is_loopback_url("file:///etc/passwd"))
        self.assertFalse(_is_loopback_url("http://"))

    def test_http_request_does_not_follow_redirects(self):
        requested_paths = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                requested_paths.append(self.path)
                self.send_response(302)
                self.send_header("Location", f"http://127.0.0.1:{server.server_port}/redirected")
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            status, _ = _request(f"http://127.0.0.1:{server.server_port}/start")
            self.assertEqual(status, 302)
            self.assertEqual(requested_paths, ["/start"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_cursor_fallback_is_blocked(self):
        report = Report()
        with mock.patch.dict("os.environ", {"BRIDGE_REQUIRE_CURSOR": "false"}):
            check_bridge_config(report)
        self.assertEqual(report.checks[0].status, "FAIL")

    def test_cursor_requirement_missing_is_warning(self):
        report = Report()
        with unittest.mock.patch.dict("os.environ", {}, clear=True):
            check_bridge_config(report)
        self.assertEqual(report.checks[0].status, "WARN")

    def test_python_version_parser_handles_missing(self):
        with mock.patch("station_doctor.shutil.which", return_value=None):
            self.assertIsNone(_version("node"))


if __name__ == "__main__":
    unittest.main()
