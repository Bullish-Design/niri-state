from __future__ import annotations

from niri_pypc import BackpressureMode

from niri_state.api.config import (
    InvariantFailurePolicy,
    SubscriberOverflowPolicy,
    UnknownEventPolicy,
    strict_config,
)


def test_strict_config_applies_fail_fast_policies() -> None:
    config = strict_config()

    assert config.pypc.backpressure_mode is BackpressureMode.FAIL_FAST
    assert config.unknown_event_policy is UnknownEventPolicy.FAIL
    assert config.invariant_failure_policy is InvariantFailurePolicy.FAIL
    assert config.subscriber_overflow_policy is SubscriberOverflowPolicy.FAIL_FAST
