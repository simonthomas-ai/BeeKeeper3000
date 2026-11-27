import argparse
import asyncio
import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
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
    manifest = SimpleNamespace(inference_status="independently_validated")


class ExperimentalDetector:
    manifest = SimpleNamespace(inference_status="experimental")


class UnmanifestedDetector:
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
            shadow=False,
        )

    def test_requires_explicit_local_file_access_confirmation(self):
        args = self.make_args(confirmed=False)
        with patch.object(importer.OnnxDetector, "from_manifest") as detector:
            with self.assertRaisesRegex(AdapterConfigurationError, "confirmation"):
                asyncio.run(importer.import_media(args))
        detector.assert_not_called()

    def test_rejects_experimental_model_without_shadow_before_outbox_creation(self):
        args = self.make_args()
        with (
            patch.object(importer.OnnxDetector, "from_manifest", return_value=ExperimentalDetector()),
            patch.object(importer, "SQLiteOutbox") as outbox,
            patch.object(importer, "LocalMediaAdapter") as adapter,
        ):
            with self.assertRaisesRegex(AdapterConfigurationError, "experimental_model_requires_explicit_shadow_mode"):
                asyncio.run(importer.import_media(args))
        outbox.assert_not_called()
        adapter.assert_not_called()

    def test_rejects_detector_without_reviewed_manifest(self):
        args = self.make_args()
        with (
            patch.object(importer.OnnxDetector, "from_manifest", return_value=UnmanifestedDetector()),
            patch.object(importer, "SQLiteOutbox") as outbox,
        ):
            with self.assertRaisesRegex(AdapterConfigurationError, "reviewed_model_manifest"):
                asyncio.run(importer.import_media(args))
        outbox.assert_not_called()

    def test_shadow_import_discards_experimental_detections_without_outbox(self):
        args = self.make_args()
        args.shadow = True
        stdout = io.StringIO()
        with (
            patch.object(importer.OnnxDetector, "from_manifest", return_value=ExperimentalDetector()),
            patch.object(importer, "SQLiteOutbox") as outbox,
            patch.object(importer, "LocalMediaAdapter", FakeAdapter),
            patch.object(importer, "AdapterSupervisor", FakeSupervisor),
            redirect_stdout(stdout),
        ):
            self.assertEqual(asyncio.run(importer.import_media(args)), 0)
        outbox.assert_not_called()
        report = stdout.getvalue()
        self.assertIn("1 unverified detection event(s) discarded", report)
        self.assertIn("no outbox was created or modified", report)

    def test_self_asserted_independent_status_is_rejected_with_or_without_shadow(self):
        for shadow in (False, True):
            args = self.make_args()
            args.shadow = shadow
            with (
                patch.object(importer.OnnxDetector, "from_manifest", return_value=FakeDetector()),
                patch.object(importer, "SQLiteOutbox") as outbox,
                patch.object(importer, "LocalMediaAdapter") as adapter,
            ):
                with self.assertRaisesRegex(
                    AdapterConfigurationError,
                    "trusted_evaluator_attestation",
                ):
                    asyncio.run(importer.import_media(args))
            outbox.assert_not_called()
            adapter.assert_not_called()


if __name__ == "__main__":
    unittest.main()
