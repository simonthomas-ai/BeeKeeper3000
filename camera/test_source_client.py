import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from camera.source_client import SourceApiClient


class SourceClientTests(unittest.TestCase):
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
            event = {"id":"camera-1","observed_at":"2026-11-20T00:00:00Z","station_id":"station-1","species":"vespa_velutina_candidate","confidence":0.9,"prey_detected":False}
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
            event = {"id":"camera-redirect","observed_at":"2026-11-20T00:00:00Z","station_id":"station-1","species":"candidate","confidence":0.8,"prey_detected":False}
            with self.assertRaises(Exception):
                client.send_event(event)
            self.assertFalse(followed["value"])
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
