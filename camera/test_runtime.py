import tempfile
import unittest
from pathlib import Path
from camera.contracts import Detection
from camera.outbox import SQLiteOutbox
from camera.runtime import LocalCameraRuntime
from camera.source_client import SourceClientError


class FakeDetector:
    def detect(self, frame):
        return [Detection("vespa_velutina_candidate", 0.91)]


class OfflineClient:
    def send_event(self, event):
        raise SourceClientError("offline")


class RuntimeTests(unittest.TestCase):
    def test_cooldown_and_offline_queue_preservation(self):
        with tempfile.TemporaryDirectory() as tmp:
            box = SQLiteOutbox(str(Path(tmp) / "outbox.sqlite3"))
            runtime = LocalCameraRuntime(
                detector=FakeDetector(), outbox=box, client=OfflineClient(),
                station_id="station-01", source="0", max_fps=2, cooldown_seconds=30,
            )
            self.assertEqual(runtime.process_frame(object(), now_monotonic=100.0), 1)
            self.assertEqual(runtime.process_frame(object(), now_monotonic=110.0), 0)
            self.assertEqual(box.count(), 1)
            with self.assertRaises(SourceClientError):
                runtime.drain_outbox()
            self.assertEqual(box.count(), 1)


if __name__ == "__main__":
    unittest.main()
