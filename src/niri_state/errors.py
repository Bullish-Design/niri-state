from __future__ import annotations

from typing import Any


class NiriStateError(Exception):
    """Base exception for all niri-state errors."""

    def __init__(
        self,
        message: str,
        *,
        cause: Exception | None = None,
    ) -> None:
        self.cause = cause
        super().__init__(message)


class StateConfigError(NiriStateError):
    """Invalid or conflicting configuration."""


class StateLifecycleError(NiriStateError):
    """Invalid lifecycle state transition."""

    def __init__(
        self,
        message: str,
        *,
        current_state: str | None = None,
        target_state: str | None = None,
        **kwargs: Any,
    ) -> None:
        self.current_state = current_state
        self.target_state = target_state
        super().__init__(message, **kwargs)


class BootstrapError(NiriStateError):
    """Bootstrap query or normalization failure."""

    def __init__(
        self,
        message: str,
        *,
        query: str | None = None,
        **kwargs: Any,
    ) -> None:
        self.query = query
        super().__init__(message, **kwargs)


class ReductionError(NiriStateError):
    """Reducer failed to process an event."""

    def __init__(
        self,
        message: str,
        *,
        event_type: str | None = None,
        revision: int | None = None,
        **kwargs: Any,
    ) -> None:
        self.event_type = event_type
        self.revision = revision
        super().__init__(message, **kwargs)


class InvariantError(NiriStateError):
    """Snapshot invariant violation detected."""

    def __init__(
        self,
        message: str,
        *,
        violations: tuple[str, ...] = (),
        revision: int | None = None,
        **kwargs: Any,
    ) -> None:
        self.violations = violations
        self.revision = revision
        super().__init__(message, **kwargs)


class DesyncError(NiriStateError):
    """State desynchronization detected."""

    def __init__(
        self,
        message: str,
        *,
        event_type: str | None = None,
        revision: int | None = None,
        **kwargs: Any,
    ) -> None:
        self.event_type = event_type
        self.revision = revision
        super().__init__(message, **kwargs)


class ResyncError(NiriStateError):
    """Recovery/resync operation failed."""


class SubscriptionOverflowError(NiriStateError):
    """Subscriber queue overflow in FAIL_FAST mode."""


class WaitTimeoutError(NiriStateError, TimeoutError):
    """Wait predicate was not satisfied within timeout.

    Inherits TimeoutError for asyncio.wait_for compatibility.
    """

    def __init__(
        self,
        message: str,
        *,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> None:
        self.timeout = timeout
        super().__init__(message, **kwargs)
