from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Any, cast

from niri_pypc import BackpressureMode, NiriConfig
from pydantic import BaseModel, ConfigDict, Field, PositiveFloat, PositiveInt


class UnknownEventPolicy(StrEnum):
    STALE = "stale"
    FAIL = "fail"
    IGNORE = "ignore"


class InvariantFailurePolicy(StrEnum):
    STALE = "stale"
    FAIL = "fail"


class ResyncPolicy(StrEnum):
    MANUAL = "manual"
    AUTO = "auto"


class WaitHealthPolicy(StrEnum):
    LIVE_ONLY = "live_only"
    ALLOW_STALE = "allow_stale"


class SubscriberOverflowPolicy(StrEnum):
    DROP_OLDEST = "drop_oldest"
    FAIL_FAST = "fail_fast"


class NiriStateConfig(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    pypc: NiriConfig = Field(default_factory=NiriConfig)

    unknown_event_policy: UnknownEventPolicy = UnknownEventPolicy.STALE
    invariant_failure_policy: InvariantFailurePolicy = InvariantFailurePolicy.STALE
    resync_policy: ResyncPolicy = ResyncPolicy.MANUAL
    wait_health_policy: WaitHealthPolicy = WaitHealthPolicy.LIVE_ONLY
    subscriber_overflow_policy: SubscriberOverflowPolicy = SubscriberOverflowPolicy.DROP_OLDEST

    subscriber_queue_size: PositiveInt = 64
    resync_max_attempts: PositiveInt = 3
    resync_backoff_base: PositiveFloat = 1.0


def strict_config(**overrides: object) -> NiriStateConfig:
    base = NiriStateConfig(**overrides)
    pypc_update = cast(Mapping[str, Any], {"backpressure_mode": BackpressureMode.FAIL_FAST})
    state_update = cast(
        Mapping[str, Any],
        {
            "pypc": base.pypc.model_copy(update=pypc_update),
            "unknown_event_policy": UnknownEventPolicy.FAIL,
            "invariant_failure_policy": InvariantFailurePolicy.FAIL,
            "subscriber_overflow_policy": SubscriberOverflowPolicy.FAIL_FAST,
        },
    )
    return base.model_copy(update=state_update)
