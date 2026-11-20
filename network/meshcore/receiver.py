"""Authenticated MeshCore receiver and local station-coordinate resolver."""
from __future__ import annotations

import inspect
import re
from collections import deque
from typing import Callable, Iterable, Mapping

from network.triangulation import Bearing
from .protocol import MeshCoreProtocolError, decode_event


class StationRegistryError(ValueError):
    """Invalid local station-coordinate registry."""


class StationRegistry:
    """Local-only mapping from privacy-preserving radio station hashes to site data.

    Coordinates are never transmitted over MeshCore. Each receiver provisions
    the station mapping locally after validating the station identity/location.
    """

    def __init__(self, entries: Mapping[str, Mapping]):
        self._entries = {}
        for station_hash, value in entries.items():
            if not isinstance(station_hash, str) or not re.fullmatch(r"[0-9a-f]{16}", station_hash):
                raise StationRegistryError("station registry keys must be 16-character lowercase hashes")
            if not isinstance(value, Mapping):
                raise StationRegistryError("station registry entry must be an object")
            station_id = value.get("station_id")
            latitude = value.get("latitude")
            longitude = value.get("longitude")
            if not isinstance(station_id, str) or not station_id or len(station_id) > 128:
                raise StationRegistryError("station_id is required")
            if isinstance(latitude, bool) or not isinstance(latitude, (int, float)) or not -90 <= latitude <= 90:
                raise StationRegistryError("invalid station latitude")
            if isinstance(longitude, bool) or not isinstance(longitude, (int, float)) or not -180 <= longitude <= 180:
                raise StationRegistryError("invalid station longitude")
            self._entries[station_hash] = {
                "station_id": station_id,
                "latitude": float(latitude),
                "longitude": float(longitude),
            }

    def resolve(self, station_hash: str) -> dict:
        try:
            return dict(self._entries[station_hash])
        except KeyError as exc:
            raise StationRegistryError("radio station is not present in the local coordinate registry") from exc

    def bearing(self, event: Mapping) -> Bearing:
        if event.get("event_type") != "bearing":
            raise StationRegistryError("event is not a bearing")
        site = self.resolve(event.get("station_id", ""))
        try:
            return Bearing(
                station_id=site["station_id"],
                latitude=site["latitude"],
                longitude=site["longitude"],
                azimuth_deg=float(event["bearing_deg"]),
                sigma_deg=float(event["bearing_sigma_deg"]),
                observed_at=event["observed_at"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise StationRegistryError("invalid signed bearing event") from exc


class MeshCoreEventReceiver:
    """Verify received MeshCore packets before forwarding normalized metadata.

    sink(event, bearing) is called only after signature, expiry and schema
    validation. bearing is None for non-bearing events. The sink should persist
    event IDs idempotently; this receiver additionally caches recent IDs in RAM.
    """

    def __init__(
        self,
        transport,
        trusted_public_keys: Mapping[str, object],
        station_registry: StationRegistry,
        sink: Callable,
        *,
        trusted_expert_fingerprints: Iterable[str] = (),
        max_seen: int = 10_000,
    ):
        if not callable(sink):
            raise ValueError("sink callback is required")
        if not 1 <= max_seen <= 100_000:
            raise ValueError("max_seen must be between 1 and 100000")
        self.transport = transport
        self.trusted_public_keys = dict(trusted_public_keys)
        self.station_registry = station_registry
        self.sink = sink
        self.trusted_expert_fingerprints = set(trusted_expert_fingerprints)
        self.max_seen = max_seen
        self._seen = set()
        self._seen_order = deque()
        self._subscription = None
        self.accepted_count = 0
        self.rejected_count = 0
        self.duplicate_count = 0

    async def start(self):
        await self.transport.connect()
        self._subscription = await self.transport.subscribe(self.handle_payload)
        return self

    async def handle_payload(self, payload: bytes):
        try:
            event = decode_event(
                payload,
                self.trusted_public_keys,
                trusted_expert_fingerprints=self.trusted_expert_fingerprints,
            )
            event_id = event["event_id"]
            if event_id in self._seen:
                self.duplicate_count += 1
                return False
            bearing = None
            if event["event_type"] == "bearing":
                bearing = self.station_registry.bearing(event)
            result = self.sink(event, bearing)
            if inspect.isawaitable(result):
                await result
            self._seen.add(event_id)
            self._seen_order.append(event_id)
            while len(self._seen_order) > self.max_seen:
                expired = self._seen_order.popleft()
                self._seen.discard(expired)
            self.accepted_count += 1
            return True
        except (MeshCoreProtocolError, StationRegistryError, KeyError, TypeError, ValueError):
            self.rejected_count += 1
            return False
        except Exception:
            # Do not hide application/storage failures as accepted events.
            self.rejected_count += 1
            return False

    async def stop(self):
        subscription, self._subscription = self._subscription, None
        if subscription is not None and hasattr(subscription, "unsubscribe"):
            subscription.unsubscribe()
        await self.transport.disconnect()
