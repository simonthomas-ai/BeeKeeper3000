"""Strict source-side observation contract for the Hornet3000 bridge.

This module accepts only bounded observation metadata. Camera media, GPS,
credentials, file paths and untrusted verification claims are not part of v1.
"""
from __future__ import annotations

from datetime import datetime
import math
import re
from typing import Mapping

_EVENT_ID = re.compile(r"^[\x21-\x7e]{1,128}$")
_STATION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$")


class SourceEventError(ValueError):
    """An event does not satisfy the strict source API contract."""


def validate_source_event(value: Mapping) -> dict:
    """Return a normalized JSON-safe event or raise SourceEventError."""
    if not isinstance(value, Mapping):
        raise SourceEventError("event must be an object")

    required = {"id", "observed_at", "station_id", "species", "confidence", "prey_detected"}
    allowed = required | {"origin"}
    if set(value) not in (required, allowed):
        raise SourceEventError("event fields do not match the strict source contract")

    # Keep old local producers compatible without ever classifying their events
    # as camera detections. The bridge deliberately drops this quarantine value.
    if "origin" not in value:
        origin = "legacy_unverified"
    else:
        origin = value["origin"]
        if not isinstance(origin, str) or origin not in {"camera", "manual_observation"}:
            raise SourceEventError("origin must be camera or manual_observation")

    event_id = value["id"]
    station_id = value["station_id"]
    observed_at = value["observed_at"]
    species = value["species"]
    confidence = value["confidence"]
    prey_detected = value["prey_detected"]

    if not isinstance(event_id, str) or not _EVENT_ID.fullmatch(event_id):
        raise SourceEventError("id must be a stable printable ASCII identifier (1..128)")
    if not isinstance(station_id, str) or not _STATION_ID.fullmatch(station_id):
        raise SourceEventError("station_id must be a short technical identifier")
    if not isinstance(observed_at, str) or not 1 <= len(observed_at) <= 40:
        raise SourceEventError("observed_at must be an ISO-8601 timestamp")
    try:
        timestamp = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SourceEventError("observed_at is not a valid ISO-8601 timestamp") from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise SourceEventError("observed_at must include an explicit timezone")
    if not isinstance(species, str) or not 1 <= len(species.strip()) <= 160:
        raise SourceEventError("species must contain 1..160 characters")
    if any(ord(char) < 32 or ord(char) == 127 for char in species):
        raise SourceEventError("species contains control characters")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise SourceEventError("confidence must be numeric")
    try:
        confidence_number = float(confidence)
    except (OverflowError, TypeError, ValueError):
        raise SourceEventError("confidence must be finite") from None
    if not math.isfinite(confidence_number) or not 0 <= confidence_number <= 1:
        raise SourceEventError("confidence must be finite and within 0..1")
    if type(prey_detected) is not bool:
        raise SourceEventError("prey_detected must be boolean")

    # Canonicalize only stable representation; preserve the source timestamp.
    return {
        "id": event_id,
        "observed_at": observed_at,
        "station_id": station_id,
        "species": species.strip(),
        "confidence": confidence_number,
        "prey_detected": prey_detected,
        "origin": origin,
    }
