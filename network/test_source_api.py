"""Tests for the durable, authenticated Hornet3000 cursor source API."""
from __future__ import annotations

import http.client
import json
import os
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from network.source_api import make_server
from network.source_cursors import CursorError, CursorExpired, CursorSigner
from network.source_event_store import SQLiteSourceEventStore, SourceDeletedError
from network.source_events import SourceEventError, validate_source_event

API_KEY = "source-api-test-key-not-for-production"
CURSOR_SECRET = "cursor-secret-test-value-at-least-32-bytes"


def sample_event(index: int, *, timestamp=None):
    return {
        "id": f"source-event-{index:04d}",
        "observed_at": timestamp or "2026-11-20T10:00:00Z",
        "station_id": "station_north",
        "species": "Vespa velutina",
        "confidence": 0.91,
        "prey_detected": index % 2 == 0,
        "origin": "camera",
    }


class SourceContractTests(unittest.TestCase):
    def test_normalizes_valid_event(self):
        event = validate_source_event(sample_event(1))
        self.assertEqual(event["id"], "source-event-0001")
        self.assertEqual(event["species"], "Vespa velutina")
        self.assertIs(type(event["prey_detected"]), bool)
        self.assertEqual(event["origin"], "camera")

    def test_quarantines_missing_origin_instead_of_assuming_camera(self):
        event = sample_event(1)
        del event["origin"]
        normalized = validate_source_event(event)
        self.assertEqual(normalized["origin"], "legacy_unverified")

    def test_preserves_explicit_manual_observation_origin(self):
        event = validate_source_event(sample_event(1) | {"origin": "manual_observation"})
        self.assertEqual(event["origin"], "manual_observation")
        for invalid in ("expert_confirmed", [], None, True):
            with self.subTest(origin=invalid), self.assertRaises(SourceEventError):
                validate_source_event(sample_event(2) | {"origin": invalid})

    def test_rejects_media_gps_free_text_and_untrusted_fields(self):
        for extra in (
            {"image_path": "/private/capture.jpg"},
            {"latitude": 51.2, "longitude": 6.8},
            {"audio_base64": "AAAA"},
            {"status": "expert_confirmed"},
        ):
            event = sample_event(1)
            event.update(extra)
            with self.subTest(extra=extra), self.assertRaises(SourceEventError):
                validate_source_event(event)

    def test_rejects_naive_timestamp_nonfinite_confidence_and_boolean_confidence(self):
        for patch in (
            {"observed_at": "2026-11-20T10:00:00"},
            {"confidence": float("nan")},
            {"confidence": float("inf")},
            {"confidence": True},
        ):
            event = sample_event(1)
            event.update(patch)
            with self.subTest(patch=patch), self.assertRaises(SourceEventError):
                validate_source_event(event)


class CursorSignerTests(unittest.TestCase):
    def setUp(self):
        self.signer = CursorSigner(CURSOR_SECRET)

    def test_cursor_round_trip_and_stream_binding(self):
        token = self.signer.issue(123456)
        self.assertLessEqual(len(token), 512)
        self.assertEqual(self.signer.read(token), 123456)

    def test_rejects_tampered_truncated_unicode_and_wrong_stream(self):
        token = self.signer.issue(42)
        forged = token[:-1] + ("A" if token[-1] != "A" else "B")
        for candidate in (forged, token + "x", "☃", "", "not-a-cursor"):
            with self.subTest(candidate=candidate), self.assertRaises(CursorError):
                self.signer.read(candidate)

        payload = json.dumps(
            {"v": 1, "stream": "other-stream", "seq": 1},
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        import base64
        import hmac
        import hashlib
        encoded = base64.urlsafe_b64encode(payload).decode().rstrip("=")
        signature = base64.urlsafe_b64encode(
            hmac.new(CURSOR_SECRET.encode(), encoded.encode(), hashlib.sha256).digest()
        ).decode().rstrip("=")
        with self.assertRaises(CursorError):
            self.signer.read(encoded + "." + signature)


class SQLiteSourceStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "source.sqlite3")
        self.store = SQLiteSourceEventStore(self.db_path, retention_days=30, max_rows=500)

    def tearDown(self):
        self.tmp.cleanup()

    def test_individual_delete_keeps_cursor_sequence_and_blocks_replay(self):
        for index in range(1, 4):
            self.store.append(sample_event(index))
        self.assertTrue(self.store.delete("source-event-0001"))
        self.assertFalse(self.store.delete("source-event-0001"))
        self.assertEqual(self.store.count(), 2)
        page = self.store.page(0, 100)
        self.assertEqual([event["id"] for event in page["events"]],
                         ["source-event-0002", "source-event-0003"])
        self.assertEqual(page["next_sequence"], 3)
        with self.assertRaises(SourceDeletedError):
            self.store.append(sample_event(1))

    def test_invalid_source_event_id_cannot_be_deleted(self):
        for invalid in ("", "has space", "snowman-☃", "x" * 129):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.store.delete(invalid)

    def test_deleted_event_tombstone_expires_with_retention_without_sequence_reuse(self):
        for index in range(1, 4):
            self.store.append(sample_event(index))
        self.assertTrue(self.store.delete("source-event-0001"))
        expired = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
        with self.store._db() as db:
            db.execute(
                "UPDATE source_tombstones SET deleted_at=? WHERE event_id=?",
                (expired, "source-event-0001"),
            )
        self.store.purge_expired()
        record, inserted = self.store.append(sample_event(1))
        self.assertTrue(inserted)
        self.assertGreater(record["sequence"], 3)

    def test_duplicate_delivery_is_idempotent_but_conflicting_reuse_is_rejected(self):
        record, inserted = self.store.append(sample_event(1))
        self.assertTrue(inserted)
        duplicate, inserted = self.store.append(sample_event(1))
        self.assertFalse(inserted)
        self.assertEqual(record["sequence"], duplicate["sequence"])
        conflict = sample_event(1)
        conflict["confidence"] = 0.22
        with self.assertRaises(RuntimeError):
            self.store.append(conflict)
        self.assertEqual(self.store.count(), 1)

    def test_capacity_does_not_evict_unforwarded_events(self):
        store = SQLiteSourceEventStore(self.db_path, retention_days=30, max_rows=100)
        for index in range(100):
            store.append(sample_event(index))
        with self.assertRaises(RuntimeError):
            store.append(sample_event(101))
        self.assertEqual(store.count(), 100)

    def test_cursor_expiration_after_retention_returns_earliest_sequence(self):
        store = SQLiteSourceEventStore(self.db_path, retention_days=1, max_rows=100)
        for index in range(3):
            store.append(sample_event(index + 1))
        old = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        with store._db() as db:
            db.execute("UPDATE source_events SET created_at=? WHERE sequence=1", (old,))
        self.assertEqual(store.purge_expired(), 1)
        with self.assertRaises(Exception) as raised:
            store.page(0, 100)
        self.assertEqual(getattr(raised.exception, "earliest_sequence", None), 2)
        self.assertEqual(store.page(1, 100)["events"][0]["id"], "source-event-0002")


    def test_page_enforces_retention_and_preserves_cursor_boundary(self):
        store = SQLiteSourceEventStore(self.db_path, retention_days=1, max_rows=100)
        for index in range(1, 4):
            store.append(sample_event(index))
        old = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        with store._db() as db:
            db.execute("UPDATE source_events SET created_at=? WHERE sequence=1", (old,))
        with self.assertRaises(CursorExpired) as raised:
            store.page(0, 100)
        self.assertEqual(raised.exception.earliest_sequence, 2)
        self.assertEqual(store.count(), 2)

    def test_sequence_survives_empty_retained_journal_and_restart(self):
        store = SQLiteSourceEventStore(self.db_path, retention_days=1, max_rows=100)
        store.append(sample_event(1))
        old = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        with store._db() as db:
            db.execute("UPDATE source_events SET created_at=?", (old,))
        store.purge_expired()
        restarted = SQLiteSourceEventStore(self.db_path, retention_days=1, max_rows=100)
        record, inserted = restarted.append(sample_event(2))
        self.assertTrue(inserted)
        self.assertEqual(record["sequence"], 2)
        with self.assertRaises(Exception):
            restarted.page(0, 100)


class SourceApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "source.sqlite3")
        self.store = SQLiteSourceEventStore(self.db_path, retention_days=30, max_rows=1000)
        self.server = make_server(API_KEY, CURSOR_SECRET, self.store, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.tmp.cleanup()

    def request(self, method, path, *, key=API_KEY, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        headers = {"X-API-Key": key}
        if body is not None:
            headers["Content-Type"] = "application/json"
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        raw = response.read()
        status = response.status
        headers = dict(response.getheaders())
        conn.close()
        payload = json.loads(raw.decode("utf-8")) if raw else None
        return status, payload, headers

    def test_authenticated_delete_erases_source_event_without_breaking_cursors(self):
        for index in (1, 2):
            status, _, _ = self.request("POST", "/api/events", body=json.dumps(sample_event(index)))
            self.assertEqual(status, 201)
        status, payload, _ = self.request(
            "DELETE", "/api/events?id=source-event-0001", key="wrong"
        )
        self.assertEqual(status, 401)
        self.assertEqual(self.store.count(), 2)

        status, payload, _ = self.request(
            "DELETE", "/api/events?id=source-event-0001"
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload, {"deleted": True})
        self.assertEqual(self.store.count(), 1)

        # An explicit deletion is a sequence hole, not a retention purge:
        # consumers can still continue from the prior cursor.
        status, page, _ = self.request("GET", "/api/events?limit=100&cursor=start")
        self.assertEqual(status, 200)
        self.assertEqual([event["id"] for event in page["events"]], ["source-event-0002"])
        self.assertFalse(page["has_more"])

        # Delayed replay of the deleted ID must fail closed.
        status, replay, _ = self.request(
            "POST", "/api/events", body=json.dumps(sample_event(1))
        )
        self.assertEqual(status, 410)
        self.assertEqual(replay, {"error": "source_event_id_deleted"})
        status, payload, _ = self.request(
            "DELETE", "/api/events?id=source-event-0001"
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload, {"deleted": False})

    def test_delete_rejects_missing_duplicate_and_malformed_parameters(self):
        for path in (
            "/api/events",
            "/api/events?id=",
            "/api/events?id=source-event-0001&id=source-event-0002",
            "/api/events?id=source-event-0001&extra=1",
        ):
            with self.subTest(path=path):
                status, _, _ = self.request("DELETE", path)
                self.assertEqual(status, 400)

    def test_unauthorized_source_access_is_denied(self):
        status, payload, _ = self.request("GET", "/api/events", key="wrong")
        self.assertEqual(status, 401)
        self.assertEqual(payload["error"], "unauthorized")

    def test_post_accepts_strict_event_and_duplicate_without_duplicate_row(self):
        body = json.dumps(sample_event(1))
        status, payload, _ = self.request("POST", "/api/events", body=body)
        self.assertEqual(status, 201)
        self.assertTrue(payload["accepted"])
        status, duplicate, _ = self.request("POST", "/api/events", body=body)
        self.assertEqual(status, 200)
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(self.store.count(), 1)
        conflict = sample_event(1)
        conflict["confidence"] = 0.12
        status, payload, _ = self.request("POST", "/api/events", body=json.dumps(conflict))
        self.assertEqual(status, 409)
        self.assertEqual(payload["error"], "source_event_id_conflict")
        self.assertEqual(self.store.count(), 1)

    def test_post_when_journal_is_full_returns_503_without_evicting_events(self):
        self.store.max_rows = 100
        for index in range(100):
            self.store.append(sample_event(index))
        status, payload, _ = self.request(
            "POST", "/api/events", body=json.dumps(sample_event(1000))
        )
        self.assertEqual(status, 503)
        self.assertEqual(payload["error"], "source_journal_capacity")
        self.assertEqual(self.store.count(), 100)

    def test_post_quarantines_missing_origin_without_camera_classification(self):
        event = sample_event(1)
        del event["origin"]
        status, payload, _ = self.request("POST", "/api/events", body=json.dumps(event))
        self.assertEqual(status, 201)
        self.assertTrue(payload["accepted"])
        stored = self.store.page(0, 10)["events"]
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["origin"], "legacy_unverified")

    def test_post_rejects_location_and_media_fields(self):
        event = sample_event(1)
        event["latitude"] = 51.2
        status, payload, _ = self.request("POST", "/api/events", body=json.dumps(event))
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"], "invalid_event")
        self.assertEqual(self.store.count(), 0)

    def test_signed_cursor_paginates_250_events_in_order(self):
        for index in range(1, 251):
            self.store.append(sample_event(index))
        cursor = 'start'
        received = []
        page_sizes = []
        for _ in range(4):
            query = "?limit=100" + ("&cursor=" + quote(cursor, safe="") if cursor else "")
            status, payload, headers = self.request("GET", "/api/events" + query)
            self.assertEqual(status, 200)
            self.assertEqual(headers.get("Cache-Control"), "no-store")
            page_sizes.append(len(payload["events"]))
            received.extend(payload["events"])
            cursor = payload["next_cursor"]
            self.assertTrue(cursor)
            if not payload["has_more"]:
                break
        self.assertEqual(page_sizes, [100, 100, 50])
        self.assertEqual([event["id"] for event in received],
                         [f"source-event-{index:04d}" for index in range(1, 251)])

    def test_pagination_resumes_after_service_restart(self):
        for index in range(1, 151):
            self.store.append(sample_event(index))
        status, first, _ = self.request("GET", "/api/events?limit=100")
        self.assertEqual(status, 200)
        cursor = first["next_cursor"]
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

        self.store = SQLiteSourceEventStore(self.db_path, retention_days=30, max_rows=1000)
        self.server = make_server(API_KEY, CURSOR_SECRET, self.store, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        status, second, _ = self.request("GET", "/api/events?limit=100&cursor=" + quote(cursor, safe=""))
        self.assertEqual(status, 200)
        self.assertEqual(len(second["events"]), 50)
        self.assertFalse(second["has_more"])
        self.assertEqual(second["events"][0]["id"], "source-event-0101")

    def test_stale_cursor_returns_410_and_earliest_retained_sequence(self):
        store = SQLiteSourceEventStore(self.db_path, retention_days=1, max_rows=1000)
        for index in range(1, 4):
            store.append(sample_event(index))
        old = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        with store._db() as db:
            db.execute("UPDATE source_events SET created_at=? WHERE sequence=1", (old,))
        self.assertEqual(store.purge_expired(), 1)
        # Restart the handler with the retained journal before requesting the cursor.
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.store = SQLiteSourceEventStore(self.db_path, retention_days=1, max_rows=1000)
        self.server = make_server(API_KEY, CURSOR_SECRET, self.store, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        # A token from before the retained boundary cannot be silently reset.
        stale = CursorSigner(CURSOR_SECRET).issue(0)
        status, payload, _ = self.request("GET", "/api/events?limit=100&cursor=" + quote(stale, safe=""))
        self.assertEqual(status, 410)
        self.assertEqual(payload["earliest_sequence"], 2)
        self.assertEqual(CursorSigner(CURSOR_SECRET).read(payload["earliest_cursor"]), 1)


    def test_new_start_cursor_uses_current_retention_boundary(self):
        store = SQLiteSourceEventStore(self.db_path, retention_days=1, max_rows=1000)
        for index in range(1, 4):
            store.append(sample_event(index))
        old = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        with store._db() as db:
            db.execute("UPDATE source_events SET created_at=? WHERE sequence=1", (old,))
        self.assertEqual(store.purge_expired(), 1)
        self.store = store
        status, payload, _ = self.request("GET", "/api/events?limit=100&cursor=start")
        self.assertEqual(status, 200)
        self.assertEqual([event["id"] for event in payload["events"]],
                         ["source-event-0002", "source-event-0003"])
        self.assertFalse(payload["has_more"])

    def test_tampered_cursor_and_duplicate_query_keys_are_rejected(self):
        signer = CursorSigner(CURSOR_SECRET)
        tampered = signer.issue(1)[:-1] + "A"
        for path in (
            "/api/events?limit=10&cursor=" + quote(tampered, safe=""),
            "/api/events?limit=10&limit=20",
        ):
            status, _, _ = self.request("GET", path)
            self.assertEqual(status, 400)

    def test_rejects_limit_over_100_and_unknown_parameters(self):
        for path in ("/api/events?limit=101", "/api/events?limit=1&offset=1"):
            status, _, _ = self.request("GET", path)
            self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
