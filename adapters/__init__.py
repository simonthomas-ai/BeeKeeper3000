"""Shared adapter lifecycle contracts and supervisors."""

from .local_media import LocalMediaAdapter
from .lifecycle import (
    AdapterConfigurationError,
    AdapterLifecycleError,
    AdapterPermissionDenied,
    AdapterSpec,
    AdapterState,
    AdapterSupervisor,
    AdapterTransientError,
    retry_delay_seconds,
    safe_diagnostic,
    validate_metadata_event,
)

__all__ = [
    "AdapterConfigurationError", "AdapterLifecycleError",
    "AdapterPermissionDenied", "AdapterSpec", "AdapterState",
    "AdapterSupervisor", "AdapterTransientError",
    "LocalMediaAdapter", "retry_delay_seconds", "safe_diagnostic", "validate_metadata_event",
]
