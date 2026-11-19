# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende
"""Zugangsschutz: Sitzungs-Cookie und signierte, zeitlich begrenzte Links für einzelne Alarme.

Alle Vergleiche laufen über Bytes (hmac.compare_digest wirft bei str mit Nicht-ASCII-Zeichen einen TypeError –
ein Angreifer könnte sonst mit einem Umlaut im Schlüssel einen Serverfehler provozieren)."""
from __future__ import annotations

import hashlib
import hmac
import time


def _b(value: str) -> bytes:
    return value.encode("utf-8", "surrogatepass")


def same(a: str | None, b: str | None) -> bool:
    """Zeitkonstanter Vergleich zweier Texte, ohne Ausnahme bei beliebigen Zeichen."""
    if a is None or b is None:
        return False
    return hmac.compare_digest(_b(a), _b(b))


def _mac(secret: str, msg: str) -> str:
    return hmac.new(_b(secret), _b(msg), hashlib.sha256).hexdigest()[:32]


def session_value(secret: str) -> str:
    """Wert des Sitzungs-Cookies (vom Zugangsschlüssel abgeleitet, nicht der Schlüssel selbst)."""
    return _mac(secret, "session-v1")


def check_token(secret: str, given: str | None) -> bool:
    return bool(secret) and bool(given) and same(given, secret)


def check_session(secret: str, cookie: str | None) -> bool:
    return bool(secret) and bool(cookie) and same(cookie, session_value(secret))


def sign_alert(secret: str, alert_id: int, ttl_s: int = 48 * 3600) -> tuple[int, str]:
    exp = int(time.time()) + ttl_s
    return exp, _mac(secret, f"alert:{alert_id}:{exp}")


def verify_alert(secret: str, alert_id: int, exp: str | int | None, sig: str | None) -> bool:
    try:
        exp_i = int(exp)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    if not secret or not sig or exp_i < time.time():
        return False
    return same(sig, _mac(secret, f"alert:{alert_id}:{exp_i}"))
