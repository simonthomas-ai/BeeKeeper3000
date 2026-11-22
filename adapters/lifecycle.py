"""Shared, privacy-first lifecycle contract for replaceable hardware adapters.

Adapters are software interfaces until a named device/firmware acceptance record
exists. The supervisor never logs event payloads, credentials, media or precise
coordinates and fails closed when permissions/capabilities are missing.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import random
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Awaitable, Callable, Mapping, Protocol


_ADAPTER_ID = re.compile(r"^[a-z][a-z0-9._-]{1,63}$")
_PERMISSION_ID = re.compile(r"^[a-z][a-z0-9._-]{0,63}$")
_FORBIDDEN_EVENT_KEYS = {
    "image", "images", "image_bytes", "image_data", "image_url", "thumbnail",
    "frame", "frames", "frame_data", "video", "video_bytes", "video_url",
    "audio", "audio_bytes", "audio_url", "raw_media", "media", "media_bytes",
    "media_url", "latitude", "longitude", "lat", "lon", "gps", "coordinates",
    "location", "api_key", "token", "password", "secret", "authorization",
    "cookie", "private_key", "credential",
}
_MAX_EVENT_BYTES = 64 * 1024


class AdapterState(str, Enum):
    CREATED = "created"
    DISCOVERING = "discovering"
    DISCOVERED = "discovered"
    CHECKING_PERMISSIONS = "checking_permissions"
    READY = "ready"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


class AdapterLifecycleError(RuntimeError):
    """Base exception with a safe machine-readable code; never stores payloads."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class AdapterTransientError(AdapterLifecycleError):
    """A timeout, disconnect or temporary adapter failure that may be retried."""


class AdapterConfigurationError(AdapterLifecycleError):
    """A permanently invalid adapter descriptor or capability contract."""


class AdapterPermissionDenied(AdapterConfigurationError):
    """The operator has not granted every permission required by the adapter."""


@dataclass(frozen=True)
class AdapterSpec:
    adapter_id: str
    version: str
    source_type: str
    required_capabilities: tuple[str, ...] = ()
    required_permissions: tuple[str, ...] = ()
    raw_media_local_only: bool = True
    exact_coordinates_local_only: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.adapter_id, str) or not _ADAPTER_ID.fullmatch(self.adapter_id):
            raise ValueError("adapter_id must be a stable lowercase identifier")
        if not isinstance(self.version, str) or not self.version.strip() or len(self.version) > 40:
            raise ValueError("adapter version is required and limited to 40 characters")
        if not isinstance(self.source_type, str) or not self.source_type.strip() or len(self.source_type) > 64:
            raise ValueError("source_type is required and limited to 64 characters")
        for field_name, values, pattern in (
            ("required_capabilities", self.required_capabilities, _PERMISSION_ID),
            ("required_permissions", self.required_permissions, _PERMISSION_ID),
        ):
            if not isinstance(values, tuple) or len(values) > 32:
                raise ValueError(f"{field_name} must be a tuple containing at most 32 entries")
            if any(not isinstance(value, str) or not pattern.fullmatch(value) for value in values):
                raise ValueError(f"{field_name} contains an invalid identifier")
            if len(set(values)) != len(values):
                raise ValueError(f"{field_name} entries must be unique")
        if self.raw_media_local_only is not True or self.exact_coordinates_local_only is not True:
            raise ValueError("adapter raw media and exact coordinates must remain local by default")


class InputAdapter(Protocol):
    """Async adapter contract. Implementations must bound their own native I/O."""

    async def discover(self) -> bool: ...
    async def capabilities(self) -> Mapping[str, bool]: ...
    async def permissions(self) -> Mapping[str, bool]: ...
    async def start(self) -> None: ...
    async def read_event(self, timeout_seconds: float) -> Mapping[str, Any] | None: ...
    async def health(self) -> Mapping[str, Any]: ...
    async def stop(self) -> None: ...


EventSink = Callable[[Mapping[str, Any]], Awaitable[None] | None]
DiagnosticSink = Callable[[Mapping[str, Any]], Awaitable[None] | None]


def _contains_forbidden_key(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, child in value.items():
            # Compare a separator-free form as well: API payloads commonly use
            # camelCase, kebab-case or dotted names for the same sensitive field.
            normalized = str(key).strip().casefold().replace("-", "_")
            compact = re.sub(r"[^a-z0-9]", "", normalized)
            forbidden_compact = {
                re.sub(r"[^a-z0-9]", "", name) for name in _FORBIDDEN_EVENT_KEYS
            }
            if normalized in _FORBIDDEN_EVENT_KEYS or compact in forbidden_compact:
                return True
            if _contains_forbidden_key(child):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_contains_forbidden_key(item) for item in value)
    return False


def validate_metadata_event(event: object) -> Mapping[str, Any]:
    """Return a JSON-safe metadata event; reject media, secrets and precise location."""
    if not isinstance(event, Mapping) or _contains_forbidden_key(event):
        raise AdapterConfigurationError("event_contract_violation")
    try:
        encoded = json.dumps(event, allow_nan=False, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError, RecursionError) as exc:
        raise AdapterConfigurationError("event_not_json_serializable") from None
    if len(encoded.encode("utf-8")) > _MAX_EVENT_BYTES:
        raise AdapterConfigurationError("event_exceeds_size_limit")
    # Round-trip into plain JSON types so custom Mapping objects cannot execute
    # delayed behaviour in downstream sinks.
    return json.loads(encoded)


def safe_diagnostic(spec: AdapterSpec, state: AdapterState, code: str,
                    *, attempt: int = 0, elapsed_ms: int | None = None) -> dict[str, Any]:
    """Build a deliberately narrow diagnostic record without exception text."""
    record: dict[str, Any] = {
        "adapter_id": spec.adapter_id,
        "state": state.value,
        "code": code if re.fullmatch(r"[a-z][a-z0-9_]{0,63}", code) else "adapter_error",
        "attempt": max(0, min(int(attempt), 1_000_000)),
    }
    if elapsed_ms is not None:
        record["elapsed_ms"] = max(0, min(int(elapsed_ms), 86_400_000))
    return record


def retry_delay_seconds(attempt: int, *, base_seconds: float = 1.0,
                        max_seconds: float = 30.0, jitter_fraction: float = 0.2,
                        random_value: float | None = None) -> float:
    """Capped exponential backoff with injectable jitter for deterministic tests."""
    if type(attempt) is not int or attempt < 1:
        raise ValueError("attempt must be a positive integer")
    if not 0 < base_seconds <= 60 or not base_seconds <= max_seconds <= 300:
        raise ValueError("backoff limits are invalid")
    if not 0 <= jitter_fraction <= 0.5:
        raise ValueError("jitter_fraction must be between 0 and 0.5")
    if random_value is None:
        random_value = random.uniform(-1.0, 1.0)
    if not -1.0 <= random_value <= 1.0:
        raise ValueError("random_value must be in [-1, 1]")
    nominal = min(max_seconds, base_seconds * (2 ** min(attempt - 1, 16)))
    return max(0.05, min(max_seconds, nominal * (1.0 + jitter_fraction * random_value)))


class AdapterSupervisor:
    """Permission-aware supervisor with bounded lifecycle calls and reconnects."""

    def __init__(self, spec: AdapterSpec, adapter: InputAdapter, *,
                 operation_timeout_seconds: float = 5.0,
                 read_timeout_seconds: float = 1.0,
                 diagnostic_sink: DiagnosticSink | None = None,
                 jitter_fraction: float = 0.2):
        if not 0.1 <= operation_timeout_seconds <= 60:
            raise ValueError("operation timeout must be between 0.1 and 60 seconds")
        if not 0.1 <= read_timeout_seconds <= 30:
            raise ValueError("read timeout must be between 0.1 and 30 seconds")
        if not 0 <= jitter_fraction <= 0.5:
            raise ValueError("jitter fraction must be between 0 and 0.5")
        self.spec = spec
        self.adapter = adapter
        self.operation_timeout_seconds = float(operation_timeout_seconds)
        self.read_timeout_seconds = float(read_timeout_seconds)
        self.diagnostic_sink = diagnostic_sink
        self.jitter_fraction = float(jitter_fraction)
        self.state = AdapterState.CREATED
        self._started = False

    async def _emit_diagnostic(self, code: str, *, attempt: int = 0,
                               started_at: float | None = None) -> None:
        if self.diagnostic_sink is None:
            return
        import time
        elapsed = None if started_at is None else int((time.monotonic() - started_at) * 1000)
        record = safe_diagnostic(self.spec, self.state, code, attempt=attempt, elapsed_ms=elapsed)
        result = self.diagnostic_sink(record)
        if inspect.isawaitable(result):
            await result

    async def _call(self, method: str, *args: Any) -> Any:
        operation = getattr(self.adapter, method, None)
        if not callable(operation):
            raise AdapterConfigurationError("adapter_method_missing")
        try:
            return await asyncio.wait_for(operation(*args), timeout=self.operation_timeout_seconds)
        except asyncio.CancelledError:
            raise
        except asyncio.TimeoutError:
            raise AdapterTransientError("adapter_operation_timeout") from None
        except AdapterLifecycleError:
            raise
        except Exception:
            # Never surface arbitrary exception text: device drivers often put
            # RTSP credentials, paths, tokens or payload details in messages.
            raise AdapterTransientError("adapter_operation_failed") from None

    async def run_once(self, event_sink: EventSink, stop_event: asyncio.Event) -> None:
        if not callable(event_sink):
            raise TypeError("event_sink must be callable")
        if not isinstance(stop_event, asyncio.Event):
            raise TypeError("stop_event must be an asyncio.Event")
        if self.state not in {AdapterState.CREATED, AdapterState.STOPPED, AdapterState.FAILED}:
            raise AdapterConfigurationError("adapter_supervisor_already_running")

        self._started = False
        failed = False
        try:
            self.state = AdapterState.DISCOVERING
            if await self._call("discover") is not True:
                raise AdapterTransientError("adapter_not_discovered")
            self.state = AdapterState.DISCOVERED

            self.state = AdapterState.CHECKING_PERMISSIONS
            capabilities = await self._call("capabilities")
            if not isinstance(capabilities, Mapping) or any(
                capabilities.get(name) is not True for name in self.spec.required_capabilities
            ):
                raise AdapterConfigurationError("required_capability_unavailable")
            permissions = await self._call("permissions")
            if not isinstance(permissions, Mapping) or any(
                permissions.get(name) is not True for name in self.spec.required_permissions
            ):
                raise AdapterPermissionDenied("required_permission_not_granted")
            self.state = AdapterState.READY

            self.state = AdapterState.STARTING
            await self._call("start")
            self._started = True
            self.state = AdapterState.RUNNING

            while not stop_event.is_set():
                health = await self._call("health")
                if not isinstance(health, Mapping) or health.get("healthy") is not True:
                    raise AdapterTransientError("adapter_unhealthy")
                event = await self._call("read_event", self.read_timeout_seconds)
                if event is None:
                    continue
                safe_event = validate_metadata_event(event)
                result = event_sink(safe_event)
                if inspect.isawaitable(result):
                    await asyncio.wait_for(result, timeout=self.operation_timeout_seconds)
        except AdapterLifecycleError:
            failed = True
            self.state = AdapterState.FAILED
            raise
        except asyncio.CancelledError:
            self.state = AdapterState.STOPPING
            raise
        except Exception:
            failed = True
            self.state = AdapterState.FAILED
            raise AdapterTransientError("adapter_supervisor_failed") from None
        finally:
            if self._started:
                if not failed:
                    self.state = AdapterState.STOPPING
                try:
                    await self._call("stop")
                except AdapterLifecycleError:
                    failed = True
                    self.state = AdapterState.FAILED
                    raise
                finally:
                    self._started = False
            self.state = AdapterState.FAILED if failed else AdapterState.STOPPED

    async def run_forever(self, event_sink: EventSink, stop_event: asyncio.Event,
                          *, base_backoff_seconds: float = 1.0,
                          max_backoff_seconds: float = 30.0,
                          max_attempts: int | None = None) -> None:
        if max_attempts is not None and (type(max_attempts) is not int or max_attempts < 1):
            raise ValueError("max_attempts must be a positive integer or None")
        attempt = 0
        while not stop_event.is_set():
            try:
                await self.run_once(event_sink, stop_event)
                return
            except AdapterPermissionDenied:
                await self._emit_diagnostic("permission_denied", attempt=attempt)
                raise
            except AdapterConfigurationError:
                await self._emit_diagnostic("configuration_error", attempt=attempt)
                raise
            except AdapterTransientError as exc:
                attempt += 1
                await self._emit_diagnostic(exc.code, attempt=attempt)
                if max_attempts is not None and attempt >= max_attempts:
                    raise
                delay = retry_delay_seconds(
                    attempt,
                    base_seconds=base_backoff_seconds,
                    max_seconds=max_backoff_seconds,
                    jitter_fraction=self.jitter_fraction,
                )
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=delay)
                except asyncio.TimeoutError:
                    pass
        self.state = AdapterState.STOPPED
