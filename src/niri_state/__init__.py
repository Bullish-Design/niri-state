from __future__ import annotations

from niri_state._runtime.store import NiriState
from niri_state._version import __version__
from niri_state.config import (
    CorrectnessMode,
    InvariantFailurePolicy,
    NiriStateConfig,
    ResyncPolicy,
    SubscriberOverflowPolicy,
    UnknownEventPolicy,
    WaitHealthPolicy,
    normalize_config,
)
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
from niri_state.selectors import aggregates, focus, keyboard, outputs, overview, windows, workspaces

__all__ = [
    "__version__",
    "NiriState",
    "CorrectnessMode",
    "InvariantFailurePolicy",
    "NiriStateConfig",
    "normalize_config",
    "ResyncPolicy",
    "SubscriberOverflowPolicy",
    "UnknownEventPolicy",
    "WaitHealthPolicy",
    "BootstrapError",
    "DesyncError",
    "InvariantError",
    "NiriStateError",
    "ReductionError",
    "ResyncError",
    "StateConfigError",
    "StateLifecycleError",
    "SubscriptionOverflowError",
    "WaitTimeoutError",
    "aggregates",
    "focus",
    "keyboard",
    "outputs",
    "overview",
    "windows",
    "workspaces",
]
