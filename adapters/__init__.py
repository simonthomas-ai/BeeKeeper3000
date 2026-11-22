"""Shared adapter lifecycle contracts and supervisors."""

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
    "retry_delay_seconds", "safe_diagnostic", "validate_metadata_event",
]
