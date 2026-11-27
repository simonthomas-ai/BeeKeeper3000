#!/usr/bin/env python3
"""Import a strictly validated, metadata-only BeeKeeper mobile export into loopback Source API."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from network.source_events import SourceEventError, validate_source_event  # noqa: E402

API_URL = "http://127.0.0.1:8787/api/events"
EXPORT_FORMAT = "beekeeper-source-api-v2-metadata-export"
MAX_EXPORT_BYTES = 2 * 1024 * 1024
MAX_EVENTS = 100
MAX_RESPONSE_BYTES = 16 * 1024
POST_INTERVAL_SECONDS = 0.55
_EVENT_FIELDS = {"id", "observed_at", "station_id", "species", "confidence", "prey_detected", "origin"}


class MobileExportError(ValueError):
    """An export or station API response failed the strict import contract."""


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise MobileExportError("Export enthält doppelte JSON-Schlüssel.")
        result[key] = value
    return result


def _reject_constant(_value):
    raise MobileExportError("Export enthält ungültige numerische Werte.")


def _valid_timestamp(value: object) -> bool:
    if not isinstance(value, str) or not 1 <= len(value) <= 40:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def load_mobile_export(path: Path) -> list[dict]:
    """Read a bounded export and enforce its exact envelope and event schema."""
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise MobileExportError("Exportdatei kann nicht gelesen werden.") from exc
    if size < 1 or size > MAX_EXPORT_BYTES:
        raise MobileExportError("Exportdatei ist leer oder überschreitet 2 MiB.")
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MobileExportError("Exportdatei ist kein gültiges UTF-8-JSON.") from exc

    if not isinstance(payload, dict) or set(payload) != {"format", "generated_at", "events"}:
        raise MobileExportError("Export-Umschlag hat nicht das erwartete Schema.")
    if payload["format"] != EXPORT_FORMAT or not _valid_timestamp(payload["generated_at"]):
        raise MobileExportError("Exportformat oder Erstellungszeitpunkt ist ungültig.")
    events = payload["events"]
    if not isinstance(events, list) or not 1 <= len(events) <= MAX_EVENTS:
        raise MobileExportError(f"Export muss 1 bis {MAX_EVENTS} Ereignisse enthalten.")

    normalized = []
    seen = set()
    for index, event in enumerate(events, start=1):
        try:
            if not isinstance(event, dict) or set(event) != _EVENT_FIELDS:
                raise SourceEventError("event keys do not match")
            clean = validate_source_event(event)
            if clean["origin"] != "manual_observation":
                raise SourceEventError("mobile exports must be marked as manual_observation")
        except (SourceEventError, TypeError, ValueError) as exc:
            raise MobileExportError(f"Ereignis {index} verletzt den Source-API-v1-Vertrag.") from exc
        if clean["id"] in seen:
            raise MobileExportError(f"Export enthält eine doppelte Ereignis-ID (Eintrag {index}).")
        seen.add(clean["id"])
        normalized.append(clean)
    return normalized


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # A local API response must never redirect the API key to another host.
        return None


def import_events(events: list[dict], api_key: str, *, opener=None, sleep=time.sleep) -> tuple[int, int]:
    """POST each event to the fixed loopback endpoint; the API key is never logged."""
    if not isinstance(api_key, str) or len(api_key) < 16 or not api_key.isascii():
        raise MobileExportError("HORNET3000_API_KEY fehlt oder ist ungültig.")
    if opener is None:
        opener = urllib.request.build_opener(_NoRedirect())

    imported = duplicates = 0
    for index, event in enumerate(events):
        if index:
            # Source API is rate-limited to 120 requests/minute per local client.
            sleep(POST_INTERVAL_SECONDS)
        body = json.dumps(event, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            API_URL,
            data=body,
            headers={"Content-Type": "application/json", "X-API-Key": api_key},
            method="POST",
        )
        try:
            with opener.open(request, timeout=5) as response:
                status = int(response.status)
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            raw = b""
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise MobileExportError(
                f"Quell-API-Verbindung nach {imported + duplicates} von {len(events)} Einträgen fehlgeschlagen ({type(exc).__name__})."
            ) from None

        if status not in (200, 201) or len(raw) > MAX_RESPONSE_BYTES:
            detail = "API-Schlüssel abgelehnt" if status == 401 else f"HTTP {status}"
            raise MobileExportError(
                f"Import nach {imported + duplicates} von {len(events)} Einträgen gestoppt ({detail}). "
                "Denselben Export nach Behebung erneut starten; Ereignis-IDs verhindern Duplikate."
            )
        try:
            ack = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            raise MobileExportError("Quell-API lieferte keine gültige Bestätigung.") from None
        if not isinstance(ack, dict) or ack.get("accepted") is not True or ack.get("event_id") != event["id"]:
            raise MobileExportError("Quell-API-Bestätigung passt nicht zum gesendeten Ereignis.")
        if ack.get("duplicate") is True:
            duplicates += 1
        else:
            imported += 1
    return imported, duplicates


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Importiert einen BeeKeeper-Mobileexport ausschließlich in die lokale Loopback-Quell-API."
    )
    parser.add_argument("export_file", type=Path)
    args = parser.parse_args(argv)
    key = os.environ.get("HORNET3000_API_KEY", "")
    try:
        events = load_mobile_export(args.export_file)
        imported, duplicates = import_events(events, key)
    except MobileExportError as exc:
        print(f"BeeKeeper-Mobileimport abgebrochen: {exc}", file=sys.stderr)
        return 2
    print(f"Import abgeschlossen: {imported} neu, {duplicates} bereits vorhanden; {len(events)} Ereignisse geprüft.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
