import argparse
import asyncio
import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from adapters.lifecycle import AdapterConfigurationError
import scripts.import_local_media as importer


class FakeOutbox:
    def __init__(self, path):
        self.path = path
        self.inserted = []

    def enqueue_if_due(self, event, *, cooldown_seconds):
        self.inserted.append((dict(event), cooldown_seconds))
        return True

    def count(self):
        return len(self.inserted)


class FakeDetector:
    pass


class FakeAdapter:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeSupervisor:
    def __init__(self, spec, adapter):
        self.spec = spec
        self.adapter = adapter

    async def run_once(self, sink, stop_event):
        sink({
            "id": "camera-00000000000000000000000000000001",
            "observed_at": "2026-11-22T12:00:00Z",
            "station_id": "station-01",
            "species": "vespa_velutina_candidate",
            "confidence": 0.91,
            "prey_detected": False,
        })


class LocalMediaCliTests(unittest.TestCase):
    def make_args(self, confirmed=True):
        return argparse.Namespace(
            manifest=Path("model-manifest.json"),
            source=Path("images/sample.png"),
            allowed_root=Path("review"),
            station_id="station-01",
            outbox=Path("outbox.sqlite3"),
            threads=2,
            cooldown=30.0,
            max_video_frames=10_000,
            max_video_duration=3_600,
            confirm_local_file_access=confirmed,
        )

    def test_requires_explicit_local_file_access_confirmation(self):
        args = self.make_args(confirmed=False)
        with patch.object(importer.OnnxDetector, "from_manifest") as detector:
            with self.assertRaisesRegex(AdapterConfigurationError, "confirmation"):
                asyncio.run(importer.import_media(args))
        detector.assert_not_called()

    def test_queues_only_metadata_and_never_constructs_network_client(self):
        args = self.make_args()
        stdout = io.StringIO()
        with (
            patch.object(importer.OnnxDetector, "from_manifest", return_value=FakeDetector()),
            patch.object(importer, "SQLiteOutbox", FakeOutbox),
            patch.object(importer, "LocalMediaAdapter", FakeAdapter),
            patch.object(importer, "AdapterSupervisor", FakeSupervisor),
            redirect_stdout(stdout),
        ):
            self.assertEqual(asyncio.run(importer.import_media(args)), 0)
        report = stdout.getvalue()
        self.assertIn("1 unverified metadata event", report)
        self.assertIn("Raw media remained local", report)
        self.assertNotIn(str(args.source), report)
        self.assertNotIn("http://", report)
        self.assertNotIn("https://", report)
        self.assertFalse(hasattr(importer, "SourceApiClient"))


if __name__ == "__main__":
    unittest.main()
