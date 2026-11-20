from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from scripts.import_mobile_export import (
    EXPORT_FORMAT, MobileExportError, import_events, load_mobile_export, API_URL,
)


def sample_event(event_id="mobile-test-001"):
    return {
        "id": event_id,
        "observed_at": "2026-11-20T12:00:00Z",
        "station_id": "mobile-0123456789abcdef",
        "species": "Vespa velutina (Verdacht; unbestätigt)",
        "confidence": 0.55,
        "prey_detected": False,
    }


def write_export(path: Path, events=None):
    path.write_text(json.dumps({
        "format": EXPORT_FORMAT,
        "generated_at": "2026-11-20T12:01:00+01:00",
        "events": events if events is not None else [sample_event()],
    }), encoding="utf-8")


class FakeResponse:
    def __init__(self, payload):
        self.status = 201
        self._body = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit=-1):
        return self._body


class FakeOpener:
    def __init__(self):
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        event = json.loads(request.data)
        return FakeResponse({"accepted": True, "duplicate": False, "event_id": event["id"]})


class MobileExportImportTests(unittest.TestCase):
    def test_reads_exact_metadata_export(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "export.json"
            write_export(path)
            events = load_mobile_export(path)
        self.assertEqual(events, [sample_event()])

    def test_rejects_private_fields_and_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "export.json"
            private = sample_event() | {"latitude": 51.2}
            write_export(path, [private])
            with self.assertRaises(MobileExportError):
                load_mobile_export(path)
            write_export(path, [sample_event(), sample_event()])
            with self.assertRaises(MobileExportError):
                load_mobile_export(path)

    def test_rejects_non_timezone_timestamp_and_nonfinite_confidence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "export.json"
            bad = sample_event() | {"observed_at": "2026-11-20T12:00:00"}
            write_export(path, [bad])
            with self.assertRaises(MobileExportError):
                load_mobile_export(path)
            path.write_text(
                '{"format":"' + EXPORT_FORMAT + '","generated_at":"2026-11-20T12:01:00Z",'
                '"events":[{"id":"x","observed_at":"2026-11-20T12:00:00Z","station_id":"station1",'
                '"species":"unknown","confidence":NaN,"prey_detected":false}]}',
                encoding="utf-8",
            )
            with self.assertRaises(MobileExportError):
                load_mobile_export(path)

    def test_posts_only_to_fixed_loopback_and_checks_acknowledgement(self):
        opener = FakeOpener()
        events = [sample_event()]
        imported, duplicates = import_events(events, "a" * 32, opener=opener, sleep=lambda _delay: None)
        self.assertEqual((imported, duplicates), (1, 0))
        request, timeout = opener.requests[0]
        self.assertEqual(request.full_url, API_URL)
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("X-api-key"), "a" * 32)
        self.assertEqual(timeout, 5)
        self.assertEqual(json.loads(request.data), sample_event())
        self.assertEqual(set(json.loads(request.data)), set(sample_event()))

    def test_rejects_short_api_key_without_network(self):
        opener = Mock()
        with self.assertRaises(MobileExportError):
            import_events([sample_event()], "short", opener=opener)
        opener.open.assert_not_called()


if __name__ == "__main__":
    unittest.main()
