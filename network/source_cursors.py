"""Authenticated opaque cursor tokens for the source event journal."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re


class CursorError(ValueError):
    """Invalid, forged or wrong-stream pagination token."""


class CursorExpired(CursorError):
    """Cursor points behind the earliest retained event."""

    def __init__(self, earliest_sequence: int):
        self.earliest_sequence = earliest_sequence
        super().__init__("cursor is older than the retained event journal")


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise CursorError("malformed cursor encoding")
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, base64.binascii.Error) as exc:
        raise CursorError("malformed cursor encoding") from exc


class CursorSigner:
    """HMAC-SHA256 signed, versioned and stream-bound opaque cursors."""

    STREAM = "hornet3000-events"
    VERSION = 1
    MAX_TOKEN_CHARS = 512

    def __init__(self, secret: str | bytes):
        if isinstance(secret, str):
            secret = secret.encode("utf-8")
        if not isinstance(secret, bytes) or len(secret) < 32:
            raise ValueError("cursor secret must contain at least 32 bytes")
        self._secret = secret

    def issue(self, sequence: int) -> str:
        if type(sequence) is not int or sequence < 0:
            raise ValueError("sequence must be a non-negative integer")
        payload = json.dumps(
            {"v": self.VERSION, "stream": self.STREAM, "seq": sequence},
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        encoded = _b64encode(payload)
        signature = _b64encode(hmac.new(self._secret, encoded.encode("ascii"), hashlib.sha256).digest())
        token = encoded + "." + signature
        if len(token) > self.MAX_TOKEN_CHARS:
            raise ValueError("generated cursor exceeds maximum size")
        return token

    def read(self, token: str) -> int:
        if not isinstance(token, str) or not 1 <= len(token) <= self.MAX_TOKEN_CHARS:
            raise CursorError("cursor is missing or too large")
        parts = token.split(".")
        if len(parts) != 2:
            raise CursorError("malformed cursor")
        encoded, supplied_signature = parts
        expected_signature = _b64encode(
            hmac.new(self._secret, encoded.encode("ascii", errors="strict"), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(supplied_signature, expected_signature):
            raise CursorError("cursor signature is invalid")
        payload = _b64decode(encoded)
        try:
            data = json.loads(payload.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise CursorError("cursor payload is invalid") from exc
        if (
            not isinstance(data, dict)
            or set(data) != {"v", "stream", "seq"}
            or type(data["v"]) is not int
            or data["v"] != self.VERSION
            or data["stream"] != self.STREAM
            or type(data["seq"]) is not int
            or data["seq"] < 0
        ):
            raise CursorError("cursor payload has an unsupported shape or stream")
        return data["seq"]
