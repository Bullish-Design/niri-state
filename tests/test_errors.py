from __future__ import annotations

from niri_state.errors import (
    BootstrapError,
    DesyncError,
    InvariantError,
    NiriStateError,
    ReductionError,
    ResyncError,
    StateConfigError,
    StateLifecycleError,
    SubscriptionOverflowError,
    WaitTimeoutError,
)


class TestErrorHierarchy:
    def test_all_inherit_from_base(self) -> None:
        for cls in [
            StateConfigError,
            StateLifecycleError,
            BootstrapError,
            ReductionError,
            InvariantError,
            DesyncError,
            ResyncError,
            SubscriptionOverflowError,
            WaitTimeoutError,
        ]:
            assert issubclass(cls, NiriStateError)

    def test_wait_timeout_inherits_timeout_error(self) -> None:
        assert issubclass(WaitTimeoutError, TimeoutError)
        err = WaitTimeoutError("timed out", timeout=5.0)
        assert isinstance(err, TimeoutError)
        assert err.timeout == 5.0

    def test_invariant_error_carries_violations(self) -> None:
        err = InvariantError(
            "bad state",
            violations=("focus points to missing window",),
            revision=42,
        )
        assert err.violations == ("focus points to missing window",)
        assert err.revision == 42

    def test_cause_chaining(self) -> None:
        original = ValueError("upstream broke")
        err = BootstrapError("query failed", query="outputs", cause=original)
        assert err.cause is original
        assert err.query == "outputs"
