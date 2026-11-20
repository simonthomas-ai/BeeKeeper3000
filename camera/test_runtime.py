import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from camera.contracts import Detection
from camera.outbox import SQLiteOutbox
from camera.runtime import LocalCameraRuntime, _capture_source
from camera.source_client import SourceClientError


class FakeCapture:
    def __init__(self, source, backend):
        self.source = source
        self.backend = backend
        self.buffer_size = None

    def set(self, prop, value):
        self.buffer_size = (prop, value)

    def isOpened(self):
        return True

    def release(self):
        pass


class FakeCV2:
    CAP_DSHOW = 700
    CAP_FFMPEG = 1900
    CAP_V4L2 = 200
    CAP_AVFOUNDATION = 1200
    CAP_ANY = 0
    CAP_PROP_BUFFERSIZE = 38
    CAP_PROP_OPEN_TIMEOUT_MSEC = 53
    CAP_PROP_READ_TIMEOUT_MSEC = 54

    def __init__(self):
        self.calls = []

    def VideoCapture(self, source, backend, params=None):
        capture = FakeCapture(source, backend)
        capture.params = params

        self.calls.append(capture)
        return capture


class FakeDetector:
    def detect(self, frame):
        return [Detection("vespa_velutina_candidate", 0.91)]


class OfflineClient:
    def send_event(self, event):
        raise SourceClientError("offline")


class RuntimeTests(unittest.TestCase):
    def test_linux_local_camera_uses_v4l2(self):
        fake = FakeCV2()
        with patch.dict(sys.modules, {"cv2": fake}), patch("camera.runtime.sys.platform", "linux"):
            _capture_source("0")
        self.assertEqual(fake.calls[0].source, 0)
        self.assertEqual(fake.calls[0].backend, fake.CAP_V4L2)
        self.assertEqual(fake.calls[0].buffer_size, (fake.CAP_PROP_BUFFERSIZE, 1))

    def test_linux_video_device_path_uses_v4l2(self):
        fake = FakeCV2()
        with patch.dict(sys.modules, {"cv2": fake}), patch("camera.runtime.sys.platform", "linux"):
            _capture_source("/dev/video0")
        self.assertEqual(fake.calls[0].source, "/dev/video0")
        self.assertEqual(fake.calls[0].backend, fake.CAP_V4L2)

    def test_network_camera_uses_ffmpeg(self):
        fake = FakeCV2()
        with patch.dict(sys.modules, {"cv2": fake}), patch("camera.runtime.sys.platform", "linux"):
            _capture_source("rtsp://127.0.0.1:554/stream")
        self.assertEqual(fake.calls[0].backend, fake.CAP_FFMPEG)

    def test_network_camera_uses_bounded_open_and_read_timeouts(self):
        fake = FakeCV2()
        with patch.dict(sys.modules, {"cv2": fake}), patch("camera.runtime.sys.platform", "linux"):
            _capture_source("rtsp://127.0.0.1:554/stream")
        self.assertEqual(fake.calls[0].backend, fake.CAP_FFMPEG)
        self.assertEqual(fake.calls[0].params, [
            fake.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000,
            fake.CAP_PROP_READ_TIMEOUT_MSEC, 5000,
        ])

    def test_windows_local_camera_uses_directshow(self):
        fake = FakeCV2()
        with patch.dict(sys.modules, {"cv2": fake}), patch("camera.runtime.sys.platform", "win32"):
            _capture_source("0")
        self.assertEqual(fake.calls[0].source, 0)
        self.assertEqual(fake.calls[0].backend, fake.CAP_DSHOW)

    def test_cooldown_and_offline_queue_preservation(self):
        with tempfile.TemporaryDirectory() as tmp:
            box = SQLiteOutbox(str(Path(tmp) / "outbox.sqlite3"))
            runtime = LocalCameraRuntime(
                detector=FakeDetector(), outbox=box, client=OfflineClient(),
                station_id="station-01", source="0", max_fps=2, cooldown_seconds=30,
            )
            self.assertEqual(runtime.process_frame(object(), now_epoch=1000), 1)
            self.assertEqual(runtime.process_frame(object(), now_epoch=1010), 0)
            self.assertEqual(box.count(), 1)
            with self.assertRaises(SourceClientError):
                runtime.drain_outbox()
            self.assertEqual(box.count(), 1)

    def test_cooldown_survives_runtime_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "outbox.sqlite3")
            first = LocalCameraRuntime(
                detector=FakeDetector(), outbox=SQLiteOutbox(path), client=OfflineClient(),
                station_id="station-01", source="0", cooldown_seconds=30,
            )
            self.assertEqual(first.process_frame(object(), now_epoch=2000), 1)
            restarted = LocalCameraRuntime(
                detector=FakeDetector(), outbox=SQLiteOutbox(path), client=OfflineClient(),
                station_id="station-01", source="0", cooldown_seconds=30,
            )
            self.assertEqual(restarted.process_frame(object(), now_epoch=2029), 0)
            self.assertEqual(restarted.process_frame(object(), now_epoch=2030), 1)
            self.assertEqual(restarted.outbox.count(), 2)


if __name__ == "__main__":
    unittest.main()
