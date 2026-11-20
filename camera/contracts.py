"""Strict metadata-only camera detection contracts.

Camera frames and raw model outputs must never enter the source event journal.
Every detection remains an unverified candidate until reviewed by a human.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
import re
import uuid

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$")


@dataclass(frozen=True)
class Detection:
    species: str
    confidence: float
    prey_detected: bool = False

    def validate(self) -> None:
        if not isinstance(self.species, str) or not self.species.strip() or len(self.species) > 160:
            raise ValueError("species must be a non-empty label of at most 160 characters")
        if any(ord(ch) < 32 or ord(ch) == 127 for ch in self.species):
            raise ValueError("species contains control characters")
        if isinstance(self.confidence, bool) or not isinstance(self.confidence, (int, float)):
            raise ValueError("confidence must be numeric")
        if not math.isfinite(float(self.confidence)) or not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("confidence must be finite and in 0..1")
        if type(self.prey_detected) is not bool:
            raise ValueError("prey_detected must be boolean")


def make_source_event(*, station_id: str, detection: Detection, observed_at: datetime | None = None) -> dict:
    """Create the strict BeeKeeper source API v1 event; never attach media/GPS."""
    if not isinstance(station_id, str) or not _ID.fullmatch(station_id):
        raise ValueError("station_id must be a short technical identifier")
    if not isinstance(detection, Detection):
        raise TypeError("detection must be a Detection")
    detection.validate()
    stamp = observed_at or datetime.now(timezone.utc)
    if not isinstance(stamp, datetime) or stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("observed_at must be timezone-aware")
    return {
        "id": "camera-" + uuid.uuid4().hex,
        "observed_at": stamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "station_id": station_id,
        "species": detection.species.strip(),
        "confidence": float(detection.confidence),
        "prey_detected": detection.prey_detected,
    }
