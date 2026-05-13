from __future__ import annotations

from typing import TYPE_CHECKING

from niri_state.diagnostics import InvariantViolation

if TYPE_CHECKING:
    from niri_state.health import HealthState


class NiriStateError(Exception):
    def __init__(
        self,
        message: str,
        *,
        operation: str | None = None,
        retryable: bool = False,
        cause: Exception | None = None,
    ) -> None:
        self.operation = operation
        self.retryable = retryable
        self.cause = cause
        super().__init__(message)


class StateConfigError(NiriStateError):
    pass


class StateLifecycleError(NiriStateError):
    def __init__(
        self,
        message: str,
        *,
        current_state: HealthState | None = None,
        target_state: HealthState | None = None,
        operation: str | None = None,
        retryable: bool = False,
        cause: Exception | None = None,
    ) -> None:
        self.current_state = current_state
        self.target_state = target_state
        super().__init__(
            message,
            operation=operation,
            retryable=retryable,
            cause=cause,
        )


class BootstrapError(NiriStateError):
    def __init__(
        self,
        message: str,
        *,
        query: str | None = None,
        operation: str | None = None,
        retryable: bool = False,
        cause: Exception | None = None,
    ) -> None:
        self.query = query
        super().__init__(
            message,
            operation=operation,
            retryable=retryable,
            cause=cause,
        )


class ReductionError(NiriStateError):
    def __init__(
        self,
        message: str,
        *,
        event_type: str | None = None,
        revision: int | None = None,
        operation: str | None = None,
        retryable: bool = False,
        cause: Exception | None = None,
    ) -> None:
        self.event_type = event_type
        self.revision = revision
        super().__init__(
            message,
            operation=operation,
            retryable=retryable,
            cause=cause,
        )


class InvariantError(NiriStateError):
    def __init__(
        self,
        message: str,
        *,
        violations: tuple[InvariantViolation, ...],
        revision: int,
        operation: str | None = None,
    ) -> None:
        self.violations = violations
        self.revision = revision
        super().__init__(message, operation=operation, retryable=False)


class DesyncError(NiriStateError):
    def __init__(
        self,
        message: str,
        *,
        event_type: str | None = None,
        revision: int | None = None,
        operation: str | None = None,
        retryable: bool = True,
        cause: Exception | None = None,
    ) -> None:
        self.event_type = event_type
        self.revision = revision
        super().__init__(
            message,
            operation=operation,
            retryable=retryable,
            cause=cause,
        )


class ResyncError(NiriStateError):
    pass


class SubscriptionOverflowError(NiriStateError):
    pass


class WaitTimeoutError(TimeoutError, NiriStateError):
    def __init__(
        self,
        message: str,
        *,
        timeout: float,
        operation: str | None = None,
        retryable: bool = False,
        cause: Exception | None = None,
    ) -> None:
        self.timeout = timeout
        super().__init__(
            message,
            operation=operation,
            retryable=retryable,
            cause=cause,
        )
