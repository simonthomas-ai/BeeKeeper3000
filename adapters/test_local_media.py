import asyncio
import os
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from adapters.lifecycle import AdapterConfigurationError, AdapterSpec, AdapterSupervisor
from adapters.local_media import LocalMediaAdapter, image_dimensions
from camera.contracts import Detection


PNG_HEADER = (
    b"\x89PNG\r\n\x1a\n"
    + (13).to_bytes(4, "big")
    + b"IHDR"
    + struct.pack(">II", 640, 480)
)


class FakeFrame:
    def __init__(self, width=640, height=480):
        self.shape = (height, width, 3)


class FakeNumpy:
    uint8 = "uint8"

    @staticmethod
    def frombuffer(payload, dtype):
        return payload


class FakeVideoCapture:
    def __init__(self, source, backend, params, frames=None):
        self.source = source
        self.backend = backend
        self.params = params
        self.frames = list(frames or [])
        self.opened = True
        self.released = False
        self.position_ms = 0.0

    def isOpened(self):
        return self.opened

    def get(self, prop):
        if prop == FakeCV2.CAP_PROP_FRAME_WIDTH:
            return 640
        if prop == FakeCV2.CAP_PROP_FRAME_HEIGHT:
            return 480
        if prop == FakeCV2.CAP_PROP_FRAME_COUNT:
            return len(self.frames)
        if prop == FakeCV2.CAP_PROP_FPS:
            return 30.0
        if prop == FakeCV2.CAP_PROP_POS_MSEC:
            return self.position_ms
        return 0.0

    def read(self):
        if not self.frames:
            return False, None
        frame = self.frames.pop(0)
        self.position_ms += 1000.0 / 30.0
        return True, frame

    def release(self):
        self.released = True
        self.opened = False


class FakeCV2:
    IMREAD_COLOR = 1
    CAP_FFMPEG = 1900
    CAP_PROP_OPEN_TIMEOUT_MSEC = 53
    CAP_PROP_READ_TIMEOUT_MSEC = 54
    CAP_PROP_FRAME_WIDTH = 3
    CAP_PROP_FRAME_HEIGHT = 4
    CAP_PROP_FPS = 5
    CAP_PROP_FRAME_COUNT = 7
    CAP_PROP_POS_MSEC = 0

    def __init__(self, *, frames=None, image_frame=None):
        self.frames = list(frames or [])
        self.image_frame = image_frame or FakeFrame()
        self.captures = []
        self.decode_calls = 0

    def imdecode(self, encoded, flags):
        self.decode_calls += 1
        return self.image_frame

    def VideoCapture(self, source, backend, params):
        capture = FakeVideoCapture(source, backend, params, self.frames)
        self.captures.append(capture)
        return capture


class FakeDetector:
    def __init__(self, detections=None):
        self.detections = detections if detections is not None else [
            Detection("vespa_velutina_candidate", 0.91)
        ]
        self.frames_seen = 0

    def detect(self, frame):
        self.frames_seen += 1
        return list(self.detections)


class LocalMediaAdapterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def make_adapter(self, name="sample.png", **kwargs):
        path = self.root / name
        if not path.exists():
            path.write_bytes(PNG_HEADER)
        return LocalMediaAdapter(
            source_path=path,
            allowed_root=self.root,
            detector=kwargs.pop("detector", FakeDetector()),
            station_id="station-01",
            permission_granted=kwargs.pop("permission_granted", True),
            **kwargs,
        )

    async def test_image_is_decoded_locally_and_only_metadata_is_emitted(self):
        adapter = self.make_adapter()
        cv2 = FakeCV2(image_frame=FakeFrame(640, 480))
        with patch.dict("sys.modules", {"cv2": cv2, "numpy": FakeNumpy}):
            self.assertTrue(await adapter.discover())
            capabilities = await adapter.capabilities()
            self.assertTrue(capabilities["local_image"])
            await adapter.start()
            event = await adapter.read_event(1.0)
            self.assertEqual(event["species"], "vespa_velutina_candidate")
            self.assertEqual(event["station_id"], "station-01")
            self.assertNotIn("image", event)
            self.assertNotIn("image_bytes", event)
            self.assertNotIn("path", event)
            self.assertTrue(adapter.completed)
            self.assertIsNone(await adapter.read_event(1.0))
            await adapter.stop()
        self.assertEqual(cv2.decode_calls, 1)

    async def test_image_with_no_detections_completes_without_event(self):
        adapter = self.make_adapter(detector=FakeDetector(detections=[]))
        cv2 = FakeCV2()
        with patch.dict("sys.modules", {"cv2": cv2, "numpy": FakeNumpy}):
            await adapter.discover()
            await adapter.start()
            self.assertIsNone(await adapter.read_event(1.0))
            self.assertTrue(adapter.completed)
            await adapter.stop()

    async def test_supervisor_exits_cleanly_after_single_image(self):
        adapter = self.make_adapter()
        cv2 = FakeCV2()
        spec = AdapterSpec(
            adapter_id="media.local",
            version="1.0.0",
            source_type="local_media",
            required_capabilities=("local_image", "local_file_read"),
            required_permissions=("local_file_read",),
        )
        supervisor = AdapterSupervisor(spec, adapter, jitter_fraction=0)
        stop = asyncio.Event()
        events = []
        with patch.dict("sys.modules", {"cv2": cv2, "numpy": FakeNumpy}):
            await adapter.discover()
            await supervisor.run_once(lambda event: events.append(event), stop)
        self.assertEqual(len(events), 1)
        self.assertEqual(supervisor.state.value, "stopped")
        self.assertFalse(adapter._started)

    async def test_video_uses_ffmpeg_bounded_timeouts_and_completes_at_eof(self):
        path = self.root / "test.mp4"
        path.write_bytes(b"small fake video")
        adapter = self.make_adapter("test.mp4")
        cv2 = FakeCV2(frames=[FakeFrame(), FakeFrame()])
        with patch.dict("sys.modules", {"cv2": cv2, "numpy": FakeNumpy}):
            await adapter.discover()
            capabilities = await adapter.capabilities()
            self.assertTrue(capabilities["local_video"])
            await adapter.start()
            self.assertEqual(
                cv2.captures[0].params,
                [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000,
                 cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000],
            )
            event = await adapter.read_event(1.0)
            self.assertIsNotNone(event)
            self.assertEqual(event["species"], "vespa_velutina_candidate")
            self.assertIsNone(await adapter.read_event(1.0))
            self.assertTrue(adapter.completed)
            self.assertTrue(cv2.captures[0].released)
            await adapter.stop()

    async def test_rejects_permission_denial(self):
        with self.assertRaisesRegex(AdapterConfigurationError, "permission"):
            self.make_adapter(permission_granted=False)

    async def test_rejects_path_outside_allowed_root(self):
        outside = self.root.parent / (self.root.name + "-outside.png")
        outside.write_bytes(PNG_HEADER)
        self.addCleanup(lambda: outside.unlink(missing_ok=True))
        adapter = LocalMediaAdapter(
            source_path=outside,
            allowed_root=self.root,
            detector=FakeDetector(),
            station_id="station-01",
            permission_granted=True,
        )
        with self.assertRaisesRegex(AdapterConfigurationError, "outside"):
            await adapter.discover()

    async def test_rejects_symlinked_media(self):
        target = self.root / "real.png"
        target.write_bytes(PNG_HEADER)
        link = self.root / "linked.png"
        try:
            link.symlink_to(target.name)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation is unavailable on this runner")
        adapter = LocalMediaAdapter(
            source_path=link,
            allowed_root=self.root,
            detector=FakeDetector(),
            station_id="station-01",
            permission_granted=True,
        )
        with self.assertRaisesRegex(AdapterConfigurationError, "symlink"):
            await adapter.discover()

    async def test_rejects_oversized_image_before_decode(self):
        path = self.root / "oversized.png"
        path.write_bytes(PNG_HEADER + (b"x" * 2000))
        adapter = self.make_adapter("oversized.png", max_image_bytes=1024)
        cv2 = FakeCV2()
        with patch.dict("sys.modules", {"cv2": cv2, "numpy": FakeNumpy}):
            with self.assertRaisesRegex(AdapterConfigurationError, "size"):
                await adapter.discover()
        self.assertEqual(cv2.decode_calls, 0)

    async def test_rejects_excessive_detection_count_and_clears_image_snapshot(self):
        many = [Detection(f"candidate-{index}", 0.5) for index in range(65)]
        adapter = self.make_adapter(detector=FakeDetector(detections=many))
        cv2 = FakeCV2()
        with patch.dict("sys.modules", {"cv2": cv2, "numpy": FakeNumpy}):
            await adapter.discover()
            with self.assertRaisesRegex(AdapterConfigurationError, "detector_result_limit"):
                await adapter.start()
        self.assertIsNone(adapter._image_snapshot)

    async def test_rejects_excessive_image_dimensions_before_decode(self):
        payload = (
            b"\x89PNG\r\n\x1a\n" + (13).to_bytes(4, "big") + b"IHDR"
            + struct.pack(">II", 50000, 50000)
        )
        path = self.root / "huge.png"
        with patch.dict("sys.modules", {"cv2": cv2, "numpy": FakeNumpy}):
            await adapter.discover()
            with self.assertRaisesRegex(AdapterConfigurationError, "dimension"):
                await adapter.start()
        self.assertEqual(cv2.decode_calls, 0)

    async def test_rejects_unknown_file_extensions(self):
        path = self.root / "payload.exe"
        path.write_bytes(b"not media")
        adapter = self.make_adapter("payload.exe")
        with self.assertRaisesRegex(AdapterConfigurationError, "extension"):
            await adapter.discover()

    def test_image_header_reader_supports_png(self):
        self.assertEqual(image_dimensions(PNG_HEADER), (640, 480))

    def test_image_header_reader_supports_jpeg_and_webp_dimensions(self):
        jpeg = b"\xff\xd8\xff\xc0" + bytes([0, 8, 8, 1, 224, 2, 128, 3])
        self.assertEqual(image_dimensions(jpeg), (640, 480))

        webp = (
            b"RIFF" + (22).to_bytes(4, "little") + b"WEBP"
            + b"VP8X" + (10).to_bytes(4, "little")
            + b"\x00\x00\x00\x00"
            + (639).to_bytes(3, "little") + (479).to_bytes(3, "little")
        )
        self.assertEqual(image_dimensions(webp), (640, 480))

    async def test_rejects_video_file_replaced_after_discovery(self):
        path = self.root / "replace.mp4"
        path.write_bytes(b"old video source")
        adapter = self.make_adapter("replace.mp4")
        cv2 = FakeCV2()
        replacement = self.root / "replacement.tmp"
        replacement.write_bytes(b"new video source with a different identity")
        with patch.dict("sys.modules", {"cv2": cv2, "numpy": FakeNumpy}):
            await adapter.discover()
            os.replace(replacement, path)
            with self.assertRaisesRegex(AdapterConfigurationError, "source_changed"):
                await adapter.start()
        self.assertEqual(cv2.captures, [])

    async def test_releases_video_capture_when_declared_frame_count_exceeds_limit(self):
        path = self.root / "too-many-frames.mp4"
        path.write_bytes(b"fake video")
        adapter = self.make_adapter("too-many-frames.mp4", max_video_frames=1)
        cv2 = FakeCV2(frames=[FakeFrame(), FakeFrame()])
        with patch.dict("sys.modules", {"cv2": cv2, "numpy": FakeNumpy}):
            await adapter.discover()
            with self.assertRaisesRegex(AdapterConfigurationError, "frame_limit"):
                await adapter.start()
        self.assertTrue(cv2.captures[0].released)

    def test_image_header_reader_rejects_malformed_or_unknown_data(self):
        for payload in (b"", b"\x89PNG\r\n\x1a\n", b"not an image payload"):
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    image_dimensions(payload)


if __name__ == "__main__":
    unittest.main()
