"""Loopback-first authenticated HTTP API for the durable source event journal."""
from __future__ import annotations

import hmac
import json
import os
import threading
import time
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import parse_qs, urlsplit

from .source_cursors import CursorError, CursorExpired, CursorSigner
from .source_event_store import (
    SQLiteSourceEventStore, SourceStoreError, SourceConflictError, SourceCapacityError,
    SourceDeletedError,
)
from .source_events import SourceEventError

MAX_BODY_BYTES = 32 * 1024
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_WORKERS = 16
READ_TIMEOUT_SECONDS = 5
BODY_DEADLINE_SECONDS = 10
RATE_LIMIT_REQUESTS = 120
RATE_LIMIT_WINDOW_SECONDS = 60


class BoundedSourceHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    block_on_close = False
    request_queue_size = 32

    def __init__(self, *args, max_workers=MAX_WORKERS, **kwargs):
        if type(max_workers) is not int or not 1 <= max_workers <= 128:
            raise ValueError("max_workers must be between 1 and 128")
        self._worker_slots = threading.BoundedSemaphore(max_workers)
        super().__init__(*args, **kwargs)

    def process_request(self, request, client_address):
        if not self._worker_slots.acquire(timeout=0.25):
            try:
                request.sendall(
                    b"HTTP/1.1 503 Service Unavailable\r\n"
                    b"Connection: close\r\nContent-Length: 0\r\n\r\n"
                )
            except OSError:
                pass
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._worker_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._worker_slots.release()

    def get_request(self):
        request, address = super().get_request()
        request.settimeout(READ_TIMEOUT_SECONDS)
        return request, address


def make_handler(api_key: str, cursor_secret: str | bytes, store: SQLiteSourceEventStore,
                 *, rate_limit=RATE_LIMIT_REQUESTS, rate_window=RATE_LIMIT_WINDOW_SECONDS):
    if not isinstance(api_key, str) or len(api_key) < 16 or not api_key.isascii():
        raise ValueError("source API key must be at least 16 ASCII characters")
    signer = CursorSigner(cursor_secret)
    requests = defaultdict(deque)
    request_lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "HornetSourceAPI"
        sys_version = ""

        def log_message(self, fmt, *args):
            # No request paths, API keys, payloads or station IDs in logs.
            return

        def _send_json(self, status: int, payload: dict):
            raw = json.dumps(payload, ensure_ascii=False, allow_nan=False,
                             sort_keys=True, separators=(",", ":")).encode("utf-8")
            if len(raw) > MAX_RESPONSE_BYTES:
                status = 413
                raw = b'{"error":"response_too_large"}'
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Connection", "close")
            self.end_headers()
            try:
                self.wfile.write(raw)
            except OSError:
                pass
            self.close_connection = True

        def _authorized(self):
            values = self.headers.get_all("X-API-Key", [])
            if len(values) != 1:
                return False
            try:
                supplied = values[0].encode("ascii", errors="strict")
            except UnicodeError:
                return False
            return hmac.compare_digest(supplied, api_key.encode("ascii"))

        def _rate_allowed(self):
            now = time.monotonic()
            address = self.client_address[0]
            with request_lock:
                queue = requests.get(address)
                if queue is None:
                    if len(requests) >= 1024:
                        for old_address, old_queue in list(requests.items()):
                            while old_queue and now - old_queue[0] > rate_window:
                                old_queue.popleft()
                            if not old_queue:
                                requests.pop(old_address, None)
                            if len(requests) < 1024:
                                break
                    if len(requests) >= 1024:
                        return False
                    queue = deque()
                    requests[address] = queue
                while queue and now - queue[0] > rate_window:
                    queue.popleft()
                if len(queue) >= rate_limit:
                    return False
                queue.append(now)
                return True

        def do_GET(self):
            parsed = urlsplit(self.path)
            if parsed.path != "/api/events":
                self._send_json(404, {"error": "not_found"})
                return
            if not self._authorized():
                self._send_json(401, {"error": "unauthorized"})
                return
            if not self._rate_allowed():
                self._send_json(429, {"error": "rate_limited"})
                return
            try:
                query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
                if set(query) - {"limit", "cursor"} or any(len(values) != 1 for values in query.values()):
                    raise ValueError("unexpected or duplicated query parameter")
                raw_limit = query.get("limit", ["100"])[0]
                if not raw_limit.isascii() or not raw_limit.isdigit() or len(raw_limit) > 3:
                    raise ValueError("invalid limit")
                limit = int(raw_limit)
                if not 1 <= limit <= 100:
                    raise ValueError("limit out of range")
                raw_cursor = query.get("cursor", [None])[0]
                after = store.start_sequence() if raw_cursor in (None, 'start') else signer.read(raw_cursor)
                result = store.page(after, limit)
                response = {
                    "events": result["events"],
                    "next_cursor": signer.issue(result["next_sequence"]),
                    "has_more": result["has_more"],
                }
                self._send_json(200, response)
            except CursorExpired as exc:
                self._send_json(410, {
                    "error": "cursor_expired",
                    "earliest_sequence": exc.earliest_sequence,
                    "earliest_cursor": signer.issue(exc.earliest_sequence - 1),
                    "recovery": "operator_intervention_required",
                })
            except (CursorError, ValueError):
                self._send_json(400, {"error": "invalid_cursor_or_query"})
            except Exception:
                self._send_json(503, {"error": "source_journal_unavailable"})

        def do_POST(self):
            if self.path != "/api/events":
                self._send_json(404, {"error": "not_found"})
                return
            if not self._authorized():
                self._send_json(401, {"error": "unauthorized"})
                return
            if not self._rate_allowed():
                self._send_json(429, {"error": "rate_limited"})
                return
            if self.headers.get("Transfer-Encoding") is not None or self.headers.get("Content-Encoding") is not None:
                self._send_json(400, {"error": "unsupported_encoding"})
                return
            lengths = self.headers.get_all("Content-Length", [])
            if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit():
                self._send_json(400, {"error": "invalid_content_length"})
                return
            if len(lengths[0]) > 5:
                self._send_json(413, {"error": "body_too_large"})
                return
            length = int(lengths[0])
            if not 1 <= length <= MAX_BODY_BYTES:
                self._send_json(413, {"error": "body_too_large_or_empty"})
                return
            if self.headers.get_content_type() != "application/json":
                self._send_json(415, {"error": "application_json_required"})
                return
            try:
                body = bytearray()
                remaining = length
                deadline = time.monotonic() + BODY_DEADLINE_SECONDS
                while remaining:
                    budget = deadline - time.monotonic()
                    if budget <= 0:
                        raise TimeoutError
                    self.connection.settimeout(min(READ_TIMEOUT_SECONDS, budget))
                    chunk = self.rfile.read1(min(remaining, 8192))
                    if not chunk:
                        raise ValueError("incomplete body")
                    body.extend(chunk)
                    remaining -= len(chunk)
                def reject_duplicates(pairs):
                    result = {}
                    for key, value in pairs:
                        if key in result:
                            raise ValueError("duplicate JSON key")
                        result[key] = value
                    return result
                event = json.loads(body.decode("utf-8"), object_pairs_hook=reject_duplicates,
                                   parse_constant=lambda _: (_ for _ in ()).throw(ValueError("invalid number")))
                record, inserted = store.append(event)
                self._send_json(201 if inserted else 200, {
                    "accepted": True, "duplicate": not inserted,
                    "event_id": event["id"], "sequence": record["sequence"],
                })
            except SourceDeletedError:
                self._send_json(410, {"error": "source_event_id_deleted"})
            except SourceConflictError:
                self._send_json(409, {"error": "source_event_id_conflict"})
            except SourceCapacityError:
                self._send_json(503, {"error": "source_journal_capacity"})
            except SourceEventError:
                self._send_json(400, {"error": "invalid_event"})
            except (UnicodeError, ValueError, TypeError, KeyError, json.JSONDecodeError):
                self._send_json(400, {"error": "invalid_json_or_event"})
            except SourceStoreError:
                self._send_json(503, {"error": "source_journal_unavailable"})
            except TimeoutError:
                self._send_json(408, {"error": "request_body_timeout"})
            except OSError:
                self.close_connection = True
            except Exception:
                self._send_json(503, {"error": "source_journal_unavailable"})

        def do_PUT(self):
            self._send_json(405, {"error": "method_not_allowed"})

        def do_DELETE(self):
            parsed = urlsplit(self.path)
            if parsed.path != "/api/events":
                self._send_json(404, {"error": "not_found"})
                return
            if not self._authorized():
                self._send_json(401, {"error": "unauthorized"})
                return
            if not self._rate_allowed():
                self._send_json(429, {"error": "rate_limited"})
                return
            if self.headers.get("Transfer-Encoding") is not None or self.headers.get("Content-Encoding") is not None:
                self._send_json(400, {"error": "unsupported_encoding"})
                return
            lengths = self.headers.get_all("Content-Length", [])
            if len(lengths) > 1 or (lengths and lengths[0] != "0"):
                self._send_json(400, {"error": "delete_body_not_allowed"})
                return
            try:
                query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
                if set(query) != {"id"} or len(query["id"]) != 1:
                    raise ValueError("one event id is required")
                event_id = query["id"][0]
                if (
                    not isinstance(event_id, str)
                    or not 1 <= len(event_id) <= 128
                    or any(ord(char) < 33 or ord(char) > 126 for char in event_id)
                ):
                    raise ValueError("invalid event id")
                deleted = store.delete(event_id)
                self._send_json(200, {"deleted": deleted})
            except (ValueError, UnicodeError):
                self._send_json(400, {"error": "invalid_delete_query"})
            except SourceCapacityError:
                self._send_json(503, {"error": "source_deletion_ledger_capacity"})
            except SourceStoreError:
                self._send_json(503, {"error": "source_journal_unavailable"})
            except Exception:
                self._send_json(503, {"error": "source_journal_unavailable"})

    return Handler


def make_server(api_key, cursor_secret, store, *, host="127.0.0.1", port=8787, max_workers=MAX_WORKERS):
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("source API is loopback-only; remote access requires a separately reviewed TLS gateway")
    return BoundedSourceHTTPServer(
        (host, port), make_handler(api_key, cursor_secret, store), max_workers=max_workers
    )


def run():
    api_key = os.environ.get("HORNET3000_API_KEY", "")
    cursor_secret = os.environ.get("HORNET3000_CURSOR_SECRET", "")
    database = os.environ.get(
        "HORNET3000_EVENT_DB",
        os.path.join(os.path.dirname(__file__), "data", "source-events.sqlite3"),
    )
    retention_days = int(os.environ.get("HORNET3000_EVENT_RETENTION_DAYS", "30"))
    max_rows = int(os.environ.get("HORNET3000_EVENT_MAX_ROWS", "250000"))
    store = SQLiteSourceEventStore(database, retention_days=retention_days, max_rows=max_rows)
    removed = store.purge_expired()
    if removed:
        print(f"Source journal startup retention removed {removed} event(s).", flush=True)
    server = make_server(api_key, cursor_secret, store)
    print("Hornet3000 source API listening on 127.0.0.1:8787 (localhost only)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    run()
