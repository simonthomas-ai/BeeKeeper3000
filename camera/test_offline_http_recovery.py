"""Real loopback HTTP transport + persistent SQLite outbox recovery regression."""
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from camera.outbox import SQLiteOutbox
from camera.runtime import LocalCameraRuntime
from camera.source_client import SourceApiClient, SourceClientError


def event(event_id):
    return {"id": event_id, "observed_at": "2026-11-21T00:00:00Z",
            "station_id": "station-1", "species": "vespa_velutina_candidate",
            "confidence": 0.91, "prey_detected": False}


class OfflineHttpRecoveryTests(unittest.TestCase):
    def test_offline_reboot_http_recovery_and_duplicate_ack(self):
        with tempfile.TemporaryDirectory() as temp:
            path = str(Path(temp) / "private" / "events.sqlite3")
            outbox = SQLiteOutbox(path)
            outbox.enqueue(event("recover-001"))
            outbox.enqueue(event("recover-002"))

            # No listener: real TCP connection refusal, with SQLite preserved.
            unavailable = SourceApiClient("http://127.0.0.1:1", "k" * 32, timeout=0.5)
            runtime = LocalCameraRuntime(detector=None, outbox=outbox,
                                         client=unavailable, station_id="station-1", source="0")
            with self.assertRaises(SourceClientError):
                runtime.drain_outbox()
            self.assertEqual(SQLiteOutbox(path).count(), 2)

            received = {}
            class Handler(BaseHTTPRequestHandler):
                def do_POST(self):
                    if self.path != "/api/events" or self.headers.get("X-API-Key") != "k" * 32:
                        self.send_error(403)
                        return
                    row = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                    if row["id"] in received and received[row["id"]] != row:
                        self.send_error(409)
                        return
                    received[row["id"]] = row
                    self.send_response(201 if len(received) == 1 else 200)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                def log_message(self, *args):
                    pass

            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                # Simulate an acknowledged event whose HTTP response was lost.
                client = SourceApiClient(f"http://127.0.0.1:{server.server_port}", "k" * 32)
                self.assertTrue(client.send_event(event("recover-001")))
                self.assertEqual(len(received), 1)
                # After restart, the same stable ID is resent and acknowledged.
                restarted = SQLiteOutbox(path)
                recovered = LocalCameraRuntime(detector=None, outbox=restarted,
                                               client=client, station_id="station-1", source="0")
                self.assertEqual(recovered.drain_outbox(), 2)
                self.assertEqual(len(received), 2)
                self.assertEqual(restarted.count(), 0)
                self.assertEqual(recovered.drain_outbox(), 0)
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
