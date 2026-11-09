"""Schutzschicht vor der gesamten Webanwendung (reines ASGI, keine Abhängigkeit).

  * Größenlimit für Anfragen (Standard 1 MiB) – auch bei Chunked-Übertragung ohne Content-Length.
  * Schutz vor fremden Webseiten (CSRF): Änderungen (POST/PUT/PATCH/DELETE) nur von der eigenen Adresse;
    WebSocket-Verbindungen nur mit passendem Origin.
  * Sicherheits-Header und eine strenge Content-Security-Policy (keine Skripte außer den eigenen).
"""
from __future__ import annotations

import json
import re
from urllib.parse import urlsplit

MAX_BODY = 1 << 20
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
_HOST_RE = re.compile(r"^[A-Za-z0-9._\-]{1,253}(:\d{1,5})?$|^\[[0-9A-Fa-f:.]{2,45}\](:\d{1,5})?$")


def _hdr(scope: dict, name: bytes) -> str | None:
    for k, v in scope.get("headers") or ():
        if k == name:
            return v.decode("latin-1")
    return None


def _norm_host(netloc: str) -> str:
    return netloc.strip().lower()


def origin_allowed(origin: str | None, host: str | None, extra_hosts: set[str]) -> bool:
    """True, wenn der Origin-Header zur Adresse passt, unter der die Anwendung gerade aufgerufen wird."""
    if origin is None:
        return True  # kein Browser-Kontext (Skripte, Kameras): die Anmeldung schützt hier
    if origin.strip().lower() == "null":
        return False
    try:
        parts = urlsplit(origin)
    except ValueError:
        return False
    if parts.scheme not in ("http", "https") or not parts.netloc or parts.path not in ("", "/") or parts.query:
        return False
    o = _norm_host(parts.netloc)
    if host and o == _norm_host(host):
        return True
    return o in extra_hosts


class WebGuard:
    def __init__(self, app, *, max_body: int = MAX_BODY, public_url: str = "", extra_hosts: list[str] | None = None):
        self.app = app
        self.max_body = max_body
        self.extra_hosts: set[str] = set()
        for u in ([public_url] if public_url else []) + list(extra_hosts or []):
            try:
                p = urlsplit(u if "//" in u else "//" + u)
            except ValueError:
                continue
            if p.netloc:
                self.extra_hosts.add(_norm_host(p.netloc))

    # -- Hilfen ------------------------------------------------------------------------
    def _csp(self, scope: dict) -> str:
        host = _hdr(scope, b"host") or ""
        ws = f" ws://{host} wss://{host}" if _HOST_RE.match(host) else ""
        return ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; "
                f"media-src 'self' blob:; font-src 'self'; connect-src 'self'{ws}; manifest-src 'self'; "
                "worker-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")

    def _security_headers(self, scope: dict) -> list[tuple[bytes, bytes]]:
        h = {
            "x-content-type-options": "nosniff",
            "x-frame-options": "DENY",
            "referrer-policy": "no-referrer",
            "permissions-policy": "camera=(self), microphone=(self), geolocation=(self), interest-cohort=()",
            "cross-origin-opener-policy": "same-origin",
            "cross-origin-resource-policy": "same-origin",
            "content-security-policy": self._csp(scope),
        }
        proto = _hdr(scope, b"x-forwarded-proto")
        if scope.get("scheme") == "https" or proto == "https":
            h["strict-transport-security"] = "max-age=31536000"
        return [(k.encode(), v.encode()) for k, v in h.items()]

    @staticmethod
    async def _reject(send, status: int, message: str, scope: dict | None = None, extra=()):
        body = json.dumps({"detail": message}, ensure_ascii=False).encode()
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json; charset=utf-8"),
                                (b"content-length", str(len(body)).encode()), (b"cache-control", b"no-store"),
                                (b"x-content-type-options", b"nosniff"), *extra]})
        await send({"type": "http.response.body", "body": body})

    # -- ASGI --------------------------------------------------------------------------
    async def __call__(self, scope, receive, send):
        kind = scope["type"]
        if kind == "websocket":
            if not origin_allowed(_hdr(scope, b"origin"), _hdr(scope, b"host"), self.extra_hosts):
                # Vor dem accept() beantwortet der Server das mit HTTP 403.
                await receive()
                await send({"type": "websocket.close", "code": 1008})
                return
            await self.app(scope, receive, send)
            return
        if kind != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET").upper()
        if method in UNSAFE:
            site = (_hdr(scope, b"sec-fetch-site") or "").lower()
            if site and site not in ("same-origin", "none"):
                await self._reject(send, 403, "Anfrage von einer fremden Seite abgelehnt")
                return
            if not origin_allowed(_hdr(scope, b"origin"), _hdr(scope, b"host"), self.extra_hosts):
                await self._reject(send, 403, "Anfrage von einer fremden Seite abgelehnt")
                return
        cl = _hdr(scope, b"content-length")
        if cl is not None:
            try:
                n = int(cl)
            except ValueError:
                await self._reject(send, 400, "Ungültige Anfrage")
                return
            if n < 0:
                await self._reject(send, 400, "Ungültige Anfrage")
                return
            if n > self.max_body:
                await self._reject(send, 413, "Anfrage zu groß")
                return

        state = {"seen": 0, "done": False}
        sec = self._security_headers(scope)
        path = scope.get("path", "")

        async def guarded_receive():
            msg = await receive()
            if msg["type"] == "http.request":
                state["seen"] += len(msg.get("body", b""))
                if state["seen"] > self.max_body and not state["done"]:
                    state["done"] = True
                    await self._reject(send, 413, "Anfrage zu groß", extra=sec)
                    return {"type": "http.disconnect"}
            return msg

        async def guarded_send(msg):
            if state["done"]:
                return  # die Antwort (413) ist bereits gesendet
            if msg["type"] == "http.response.start":
                names = {k.lower() for k, _ in msg.get("headers", [])}
                hs = list(msg.get("headers", []))
                hs += [(k, v) for k, v in sec if k not in names]
                if path.startswith("/api/") and b"cache-control" not in names:
                    hs.append((b"cache-control", b"no-store"))
                msg = {**msg, "headers": hs}
            await send(msg)

        await self.app(scope, guarded_receive, guarded_send)
