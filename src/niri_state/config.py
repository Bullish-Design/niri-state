from __future__ import annotations

import enum
from dataclasses import dataclass, replace

from niri_pypc import BackpressureMode, NiriConfig

from niri_state.errors import StateConfigError


class CorrectnessMode(enum.Enum):
    STRICT = "strict"
    BEST_EFFORT = "best_effort"


class ResyncPolicy(enum.Enum):
    MANUAL = "manual"
    AUTO = "auto"


class UnknownEventPolicy(enum.Enum):
    STALE = "stale"
    FAIL = "fail"
    IGNORE = "ignore"


class InvariantFailurePolicy(enum.Enum):
    STALE = "stale"
    FAIL = "fail"


class WaitHealthPolicy(enum.Enum):
    LIVE_ONLY = "live_only"
    ALLOW_STALE = "allow_stale"


class SubscriberOverflowPolicy(enum.Enum):
    DROP_OLDEST = "drop_oldest"
    FAIL_FAST = "fail_fast"


@dataclass(frozen=True, slots=True)
class NiriStateConfig:
    pypc: NiriConfig = NiriConfig()
    correctness_mode: CorrectnessMode = CorrectnessMode.BEST_EFFORT
    resync_policy: ResyncPolicy = ResyncPolicy.MANUAL
    unknown_event_policy: UnknownEventPolicy = UnknownEventPolicy.STALE
    invariant_failure_policy: InvariantFailurePolicy = InvariantFailurePolicy.STALE
    wait_health_policy: WaitHealthPolicy = WaitHealthPolicy.LIVE_ONLY
    subscriber_overflow_policy: SubscriberOverflowPolicy = SubscriberOverflowPolicy.DROP_OLDEST
    subscriber_queue_size: int = 64
    resync_max_attempts: int = 3
    resync_backoff_base: float = 1.0


def normalize_config(config: NiriStateConfig) -> NiriStateConfig:
    """Apply policy normalization rules.

    If correctness mode is STRICT, upstream backpressure must be FAIL_FAST.
    Returns a new config with normalized pypc settings.
    """
    if config.correctness_mode is not CorrectnessMode.STRICT:
        return config

    if config.pypc.backpressure_mode is BackpressureMode.FAIL_FAST:
        return config

    try:
        normalized_pypc = replace(config.pypc, backpressure_mode=BackpressureMode.FAIL_FAST)  # type: ignore[arg-type]
    except Exception as exc:
        raise StateConfigError(
            "Failed to normalize upstream backpressure for strict mode",
            cause=exc,
        ) from exc

    return replace(config, pypc=normalized_pypc)  # type: ignore[arg-type]
