"""Loopback-only client for the BeeKeeper3000 source event API."""
from __future__ import annotations

import ipaddress
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class SourceClientError(RuntimeError):
    pass


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, new_url):
        return None


def _loopback_endpoint(base_url: str) -> str:
    parsed = urlsplit(base_url)
    if parsed.scheme != "http" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("source API must be plain HTTP on a loopback host only")
    host = parsed.hostname.lower()
    try:
        local = ipaddress.ip_address(host).is_loopback
    except ValueError:
        local = host == "localhost"
    if not local or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise ValueError("source API URL must be a loopback origin (no path, query or fragment)")
    return urlunsplit(("http", parsed.netloc, "/api/events", "", ""))


class SourceApiClient:
    def __init__(self, base_url: str, api_key: str, *, timeout: float = 4.0):
        if not isinstance(api_key, str) or len(api_key) < 24 or not api_key.isascii():
            raise ValueError("source API key must be at least 24 ASCII characters")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0.2 <= float(timeout) <= 30:
            raise ValueError("timeout must be between 0.2 and 30 seconds")
        self.endpoint = _loopback_endpoint(base_url)
        self.api_key = api_key
        self.timeout = float(timeout)

    def send_event(self, event: dict) -> bool:
        raw = json.dumps(event, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
        request = Request(self.endpoint, data=raw, method="POST", headers={
            "Content-Type": "application/json", "Accept": "application/json",
            "X-API-Key": self.api_key,
        })
        try:
            opener = build_opener(_NoRedirectHandler())
            with opener.open(request, timeout=self.timeout) as response:
                if response.status not in (200, 201):
                    raise SourceClientError(f"source API returned HTTP {response.status}")
                return True
        except HTTPError as exc:
            raise SourceClientError(f"source API rejected event with HTTP {exc.code}") from None
        except (URLError, TimeoutError, OSError) as exc:
            raise SourceClientError("source API is temporarily unavailable; event remains queued") from None
