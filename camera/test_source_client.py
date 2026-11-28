import json
import threading
import tempfile
import unittest
from pathlib import Path
from camera.contracts import Detection, make_source_event
from network.source_api import make_server
from network.source_event_store import SQLiteSourceEventStore
from http.server import BaseHTTPRequestHandler, HTTPServer
from camera.source_client import SourceApiClient, SourceClientError


class SourceClientTests(unittest.TestCase):
    def test_camera_contract_round_trips_through_real_source_api(self):
        with tempfile.TemporaryDirectory() as tmp:
            api_key = "source-api-test-key-not-for-production"
            store = SQLiteSourceEventStore(
                str(Path(tmp) / "source.sqlite3"), retention_days=30, max_rows=100
            )
            server = make_server(
                api_key, "cursor-secret-test-value-at-least-32-bytes", store, port=0
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                client = SourceApiClient(
                    f"http://127.0.0.1:{server.server_port}", api_key
                )
                event = make_source_event(
                    station_id="station-01",
                    detection=Detection("vespa_velutina_candidate", 0.9),
                )
                self.assertEqual(event["origin"], "camera")
                self.assertTrue(client.send_event(event))
                stored = store.page(0, 10)["events"]
                self.assertEqual(len(stored), 1)
                self.assertEqual(stored[0]["origin"], "camera")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)

    def test_posts_to_loopback_and_uses_source_auth_header(self):
        received = {}
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                received["path"] = self.path
                received["key"] = self.headers.get("X-API-Key")
                received["event"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                self.send_response(201)
                self.send_header("Content-Length", "0")
                self.end_headers()
            def log_message(self, *args):
                pass
        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = SourceApiClient("http://127.0.0.1:%d" % server.server_port, "a" * 32)
            event = {"id":"camera-1","observed_at":"2026-11-20T00:00:00Z","station_id":"station-1","species":"vespa_velutina_candidate","confidence":0.9,"prey_detected":False,"origin":"camera"}
            self.assertTrue(client.send_event(event))
            self.assertEqual(received["path"], "/api/events")
            self.assertEqual(received["key"], "a" * 32)
            self.assertEqual(received["event"], event)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


    def test_does_not_follow_redirects(self):
        followed = {"value": False}
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.send_response(302)
                self.send_header("Location", "http://127.0.0.1:%d/forwarded" % server.server_port)
                self.send_header("Content-Length", "0")
                self.end_headers()
            def do_GET(self):
                followed["value"] = True
                self.send_response(200)
                self.send_header("Content-Length", "0")
                self.end_headers()
            def log_message(self, *args):
                pass
        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = SourceApiClient("http://127.0.0.1:%d" % server.server_port, "a" * 32)
            event = {"id":"camera-redirect","observed_at":"2026-11-20T00:00:00Z","station_id":"station-1","species":"candidate","confidence":0.8,"prey_detected":False,"origin":"camera"}
            with self.assertRaises(SourceClientError):
                client.send_event(event)
            self.assertFalse(followed["value"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_acknowledges_only_explicit_source_erasure_response(self):
        class Handler(BaseHTTPRequestHandler):
            response_body = b'{"error":"source_event_id_deleted"}'
            response_code = 410
            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                self.send_response(self.response_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(self.response_body)))
                self.end_headers()
                self.wfile.write(self.response_body)
            def log_message(self, *args):
                pass
        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = SourceApiClient("http://127.0.0.1:%d" % server.server_port, "a" * 32)
            event = {"id":"camera-deleted","observed_at":"2026-11-20T00:00:00Z","station_id":"station-1","species":"candidate","confidence":0.8,"prey_detected":False,"origin":"camera"}
            self.assertTrue(client.send_event(event))
            Handler.response_body = b'{"error":"some_other_410"}'
            with self.assertRaises(SourceClientError):
                client.send_event(event)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_rejects_non_loopback_and_remote_scheme(self):
        with self.assertRaises(ValueError):
            SourceApiClient("http://example.org", "a" * 32)
        with self.assertRaises(ValueError):
            SourceApiClient("https://127.0.0.1", "a" * 32)


if __name__ == "__main__":
    unittest.main()
