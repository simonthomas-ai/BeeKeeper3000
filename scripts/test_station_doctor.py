import json
import sys
import threading
import types
import unittest
from unittest import mock
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from station_doctor import Report, _is_loopback_url, _request, _version, check_bridge_config, check_model, parse_args


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

    def test_no_model_flag_ignores_manifest_argument_and_environment(self):
        report = Report()
        with mock.patch.dict("os.environ", {"BEEKEEPER_MODEL_MANIFEST": "private-model.json"}):
            check_model(report, Path("."), "explicit-model.json", no_model=True)

        self.assertEqual(len(report.checks), 1)
        self.assertEqual(report.checks[0].name, "Camera model manifest")
        self.assertEqual(report.checks[0].status, "WARN")
        self.assertIn("--no-model", report.checks[0].detail)
        self.assertIn("no model file is read or executed", report.checks[0].detail)

    def test_parse_args_accepts_no_model(self):
        args = parse_args(["--no-model"])
        self.assertTrue(args.no_model)

    def test_model_check_runs_and_discards_local_synthetic_inference(self):
        manifest = types.SimpleNamespace(width=320, height=240)
        fake_numpy = types.SimpleNamespace(uint8="uint8", zeros=mock.Mock(return_value="synthetic-frame"))
        fake_runtime = types.SimpleNamespace(get_available_providers=lambda: ["CPUExecutionProvider"])
        report = Report()
        with mock.patch.dict(sys.modules, {"numpy": fake_numpy, "onnxruntime": fake_runtime}):
            with mock.patch("camera.model_manifest.load_manifest", return_value=manifest), \
                 mock.patch("camera.onnx_detector.OnnxDetector") as detector_type:
                check_model(report, Path("."), "local-manifest.json")

        detector_type.assert_called_once_with(manifest, intra_op_threads=2)
        detector_type.return_value.detect.assert_called_once_with("synthetic-frame")
        fake_numpy.zeros.assert_called_once_with((240, 320, 3), dtype="uint8")
        self.assertEqual(
            [(item.name, item.status) for item in report.checks],
            [
                ("Camera model manifest", "PASS"),
                ("ONNX Runtime CPU", "PASS"),
                ("ONNX CPU inference smoke test", "PASS"),
            ],
        )

    def test_model_check_fails_when_synthetic_inference_fails(self):
        manifest = types.SimpleNamespace(width=320, height=240)
        fake_numpy = types.SimpleNamespace(uint8="uint8", zeros=mock.Mock(return_value="synthetic-frame"))
        fake_runtime = types.SimpleNamespace(get_available_providers=lambda: ["CPUExecutionProvider"])
        report = Report()
        with mock.patch.dict(sys.modules, {"numpy": fake_numpy, "onnxruntime": fake_runtime}):
            with mock.patch("camera.model_manifest.load_manifest", return_value=manifest), \
                 mock.patch("camera.onnx_detector.OnnxDetector") as detector_type:
                detector_type.return_value.detect.side_effect = ValueError("private local detail")
                check_model(report, Path("."), "local-manifest.json")

        self.assertTrue(report.failed)
        self.assertEqual(report.checks[-1].name, "ONNX CPU inference smoke test")
        self.assertEqual(report.checks[-1].status, "FAIL")
        self.assertNotIn("private local detail", report.checks[-1].detail)


if __name__ == "__main__":
    unittest.main()
