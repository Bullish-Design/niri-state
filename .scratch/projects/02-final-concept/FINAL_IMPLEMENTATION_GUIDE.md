# FINAL_IMPLEMENTATION_GUIDE

Implementation runbook for building `niri-state` from zero to done, aligned to:
- `.scratch/projects/02-final-concept/FINAL_CONCEPT.md`
- `.scratch/projects/02-final-concept/FINAL_SPEC.md`
- `.context/niri-pypc` dependency behavior

This guide incorporates all architectural revisions from the final review, including: explicit `DraftState` representation, `BootstrapPayload` placement in `_core`, `NiriStateConfig` as a frozen dataclass, `MappingProxyType` enforcement on published snapshots, corrected error naming, defined diagnostics shape, floating-window indexing policy, `match`/`case` dispatch, `NiriState` composition model, and `refresh()` semantics in AUTO mode.

## Table of Contents

1. [How to Use This Guide](#1-how-to-use-this-guide)
2. [Dependency Reality You Must Honor](#2-dependency-reality-you-must-honor-niri-pypc)
3. [Step 0: Workspace and Tooling Bootstrap](#3-step-0-workspace-and-tooling-bootstrap)
4. [Step 1: Configuration and Error Contracts](#4-step-1-configuration-and-error-contracts)
5. [Step 2: Core Immutable Models and DraftState](#5-step-2-core-immutable-models-and-draftstate)
6. [Step 3: Lifecycle FSM](#6-step-3-lifecycle-fsm)
7. [Step 4: Snapshot Builder and Index Construction](#7-step-4-snapshot-builder-and-index-construction)
8. [Step 5: Invariant Engine](#8-step-5-invariant-engine)
9. [Step 6: Domain Reducers](#9-step-6-domain-reducers)
10. [Step 7: Root Reducer and Unknown Event Policy](#10-step-7-root-reducer-and-unknown-event-policy)
11. [Step 8: Bootstrap Pipeline](#11-step-8-bootstrap-pipeline)
12. [Step 9: Store and Subscription Runtime](#12-step-9-store-and-subscription-runtime)
13. [Step 10: Wait/Watch APIs](#13-step-10-waitwatch-apis)
14. [Step 11: Resync/Recovery Coordinator](#14-step-11-resyncrecovery-coordinator)
15. [Step 12: Selector Modules and Public Exports](#15-step-12-selector-modules-and-public-exports)
16. [Step 13: Integration and Replay Harness](#16-step-13-integration-and-replay-harness)
17. [Step 14: API Polish and Packaging](#17-step-14-api-polish-and-packaging)
18. [Mandatory Validation Matrix](#18-mandatory-validation-matrix)
19. [Completion Checklist](#19-completion-checklist)

---

## 1. How to Use This Guide

1. Follow steps in order. Do not skip ahead.
2. At each step, implement only that scope, then run the listed validation before moving on.
3. If validation fails, fix immediately; do not accumulate unresolved failures.
4. Keep implementation aligned to `FINAL_CONCEPT.md` and `FINAL_SPEC.md`; if code and spec conflict, fix code unless spec is proven wrong by `niri-pypc` reality.
5. Keep `_core` pure (no IO, no async, no clocks) and `_runtime` async/orchestration-only at all times.
6. Every code file must begin with `from __future__ import annotations`.
7. All environment-dependent commands run via `devenv shell -- ...`.

---

## 2. Dependency Reality You Must Honor (`niri-pypc`)

These are non-negotiable upstream facts verified from `.context/niri-pypc`. If any spec text contradicts these, the spec is wrong.

### 2.1 Connection Model

`NiriClient` uses **one-connection-per-request**: each `request()` call opens a Unix socket, sends the request, reads the reply, and closes the socket. It returns the unwrapped `Response` payload directly. Compositor `Err` replies raise `RemoteError`.

```python
from niri_pypc import NiriClient, NiriConfig
from niri_pypc.types.generated.request import OutputsRequest

client = NiriClient.connect(config)
# Returns OutputsResponse.payload directly (dict[str, Output])
outputs = await client.request(OutputsRequest())
```

`NiriClient.connect()` is synchronous — it validates config and resolves the socket path but does not open a socket.

### 2.2 Event Stream

`NiriEventStream` is long-lived with a background reader task and a bounded `asyncio.Queue`. Backpressure modes:
- `BackpressureMode.DROP_OLDEST`: silently drops oldest event when queue is full.
- `BackpressureMode.FAIL_FAST`: terminally errors the stream with `ProtocolError` when queue is full.

The `next()` method returns the **variant instance directly** (e.g., `WindowFocusChangedEvent`), not the `Event` wrapper. It can raise:
- `LifecycleError` — stream closed
- `NiriTimeoutError` — read timeout
- `ProtocolError` — terminal queue overflow (FAIL_FAST mode)
- `TransportError` — socket failure
- `DecodeError` — frame decode failure

### 2.3 Connection Bundle

`NiriConnectionBundle.open(config)` creates both client and event stream. If event stream creation fails, it cleans up the client before re-raising.

```python
from niri_pypc import NiriConnectionBundle

async with await NiriConnectionBundle.open(config) as bundle:
    result = await bundle.client.request(SomeRequest())
    event = await bundle.events.next()
```

### 2.4 Unknown Events

Unknown events decode into `UnknownEvent(variant_name=str, raw_payload=Any)` — they never cause a decode crash. This is the sentinel that triggers unknown-event policy handling.

### 2.5 Configuration

`NiriConfig` is a **frozen dataclass** (`@dataclass(frozen=True, slots=True)`):

```python
@dataclass(frozen=True, slots=True)
class NiriConfig:
    socket_path: Path | None = None
    connect_timeout: float = 5.0
    request_timeout: float = 10.0
    event_read_timeout: float | None = None
    max_frame_size: int = 4 * 1024 * 1024
    event_queue_capacity: int = 256
    backpressure_mode: BackpressureMode = BackpressureMode.DROP_OLDEST
```

Config normalization in `niri-state` uses `dataclasses.replace()` on this frozen dataclass.

### 2.6 Complete Event Variant Catalog

These are the **exact class names** from `niri_pypc.types.generated.event`:

| Event Class | Key Fields | Domain |
|---|---|---|
| `WindowsChangedEvent` | `windows: list[Window]` | windows (replace-all) |
| `WindowOpenedOrChangedEvent` | `window: Window` | windows (upsert) |
| `WindowClosedEvent` | `id: int` | windows |
| `WindowFocusChangedEvent` | `id: int \| None` | windows/focus |
| `WindowUrgencyChangedEvent` | `id: int, urgent: bool` | windows |
| `WindowFocusTimestampChangedEvent` | `focus_timestamp: Timestamp \| None, id: int` | windows |
| `WindowLayoutsChangedEvent` | `changes: list[tuple[int, WindowLayout]]` | windows |
| `WorkspacesChangedEvent` | `workspaces: list[Workspace]` | workspaces (replace-all) |
| `WorkspaceActivatedEvent` | `focused: bool, id: int` | workspaces |
| `WorkspaceActiveWindowChangedEvent` | `active_window_id: int \| None, workspace_id: int` | workspaces |
| `WorkspaceUrgencyChangedEvent` | `id: int, urgent: bool` | workspaces |
| `KeyboardLayoutsChangedEvent` | `keyboard_layouts: KeyboardLayouts` | keyboard |
| `KeyboardLayoutSwitchedEvent` | `idx: int` | keyboard |
| `OverviewOpenedOrClosedEvent` | `is_open: bool` | overview |
| `ConfigLoadedEvent` | `failed: bool` | metadata (no-op) |
| `ScreenshotCapturedEvent` | `path: str \| None` | metadata (no-op) |
| `UnknownEvent` | `variant_name: str, raw_payload: Any` | policy-handled |

### 2.7 Complete Request/Response Catalog

Mandatory bootstrap queries and their exact response shapes:

| Request | Response Type | Payload Shape |
|---|---|---|
| `OutputsRequest()` | `OutputsResponse` | `payload: dict[str, Output]` |
| `WorkspacesRequest()` | `WorkspacesResponse` | `payload: list[Workspace]` |
| `WindowsRequest()` | `WindowsResponse` | `payload: list[Window]` |
| `FocusedOutputRequest()` | `FocusedOutputResponse` | `payload: Output \| None` |
| `FocusedWindowRequest()` | `FocusedWindowResponse` | `payload: Window \| None` |
| `KeyboardLayoutsRequest()` | `KeyboardLayoutsResponse` | `payload: KeyboardLayouts` |
| `OverviewStateRequest()` | `OverviewStateResponse` | `payload: Overview` |

Optional:

| Request | Response Type | Payload Shape |
|---|---|---|
| `VersionRequest()` | `VersionResponse` | `payload: str` |

### 2.8 Key Protocol Model Fields

```python
class Window(BaseModel):
    id: int
    app_id: str | None = None
    title: str | None = None
    workspace_id: int | None = None  # None for floating/unassigned
    is_focused: bool
    is_floating: bool
    is_urgent: bool
    pid: int | None = None
    focus_timestamp: Timestamp | None = None
    layout: WindowLayout

class Workspace(BaseModel):
    id: int
    idx: int
    name: str | None = None
    output: str | None = None  # None if not bound to output
    is_active: bool
    is_focused: bool
    is_urgent: bool
    active_window_id: int | None = None

class Output(BaseModel):
    name: str
    make: str
    model: str
    serial: str | None = None
    physical_size: list[int] | None = None
    modes: list[Mode]
    current_mode: int | None = None
    is_custom_mode: bool
    logical: LogicalOutput | None = None
    vrr_supported: bool
    vrr_enabled: bool

class KeyboardLayouts(BaseModel):
    current_idx: int
    names: list[str]

class Overview(BaseModel):
    is_open: bool

class Timestamp(BaseModel):
    secs: int
    nanos: int
```

### 2.9 Error Hierarchy (`niri-pypc`)

```
NiriError
├── TransportError          # socket/framing IO
├── NiriTimeoutError        # also inherits TimeoutError
├── DecodeError             # validation/shape failure (has raw_payload)
├── EncodeError             # outbound encoding
├── ProtocolError           # wire contract violation
├── RemoteError             # compositor Err reply (has remote_message)
├── LifecycleError          # invalid state transition (has state)
├── ConfigError             # invalid/unresolved config
└── InternalError           # impossible state (bug)
```

---

## 3. Step 0: Workspace and Tooling Bootstrap

### 3.1 Create Package Structure

Create the following directory tree exactly. Every `__init__.py` and module file must contain `from __future__ import annotations` as its first code line.

```text
src/niri_state/
  __init__.py
  _version.py
  config.py
  errors.py
  _core/
    __init__.py
    models/
      __init__.py
      types.py
      entities.py
      snapshot.py
      health.py
      changes.py
      draft.py
      bootstrap_payload.py
    reducers/
      __init__.py
      root.py
      windows.py
      workspaces.py
      keyboard.py
      overview.py
    invariants.py
    snapshot_builder.py
  _runtime/
    __init__.py
    bootstrap.py
    store.py
    broadcaster.py
    waiters.py
    resync.py
  selectors/
    __init__.py
    outputs.py
    workspaces.py
    windows.py
    focus.py
    keyboard.py
    overview.py
    aggregates.py
```

Key differences from previous spec:
- `_core/models/draft.py` — new file for the mutable `DraftState` (review recommendation #1).
- `_core/models/bootstrap_payload.py` — `BootstrapPayload` lives in `_core`, not `_runtime`, to preserve the import boundary (review recommendation #2).

### 3.2 Create Test Directory Structure

```text
tests/
  __init__.py
  conftest.py
  test_config.py
  test_errors.py
  core/
    __init__.py
    models/
      __init__.py
      test_types.py
      test_entities.py
      test_snapshot.py
      test_health.py
      test_changes.py
      test_draft.py
    reducers/
      __init__.py
      test_root.py
      test_windows.py
      test_workspaces.py
      test_keyboard.py
      test_overview.py
    test_invariants.py
    test_snapshot_builder.py
  runtime/
    __init__.py
    test_bootstrap.py
    test_store.py
    test_broadcaster.py
    test_waiters.py
    test_resync.py
  selectors/
    __init__.py
    test_outputs.py
    test_workspaces.py
    test_windows.py
    test_focus.py
    test_keyboard.py
    test_overview.py
    test_aggregates.py
  integration/
    __init__.py
    test_bootstrap_convergence.py
    test_replay.py
```

### 3.3 Stub File Content

Every stub file should contain only:

```python
from __future__ import annotations
```

Exception: `_version.py` should contain:

```python
from __future__ import annotations

__version__ = "0.1.0"
```

And `src/niri_state/__init__.py` should contain:

```python
from __future__ import annotations

from niri_state._version import __version__

__all__ = ["__version__"]
```

### 3.4 Verify pyproject.toml

Ensure `niri-pypc` is listed as a dependency. The current `pyproject.toml` lists only `pydantic>=2.12.5`. Add:

```toml
dependencies = [
  "pydantic>=2.12.5",
  "niri-pypc",
]
```

If `niri-pypc` is not yet published to PyPI and must be installed from a local path or git, use:

```toml
[tool.uv.sources]
niri-pypc = { path = "../niri-pypc", editable = true }
```

Adjust the path to match your actual `niri-pypc` location.

### 3.5 Validation

```bash
devenv shell -- uv sync --extra dev
devenv shell -- python -c "import niri_state; print(niri_state.__version__)"
devenv shell -- ruff check .
devenv shell -- ruff format --check .
```

**Pass criteria:**
1. Import prints `0.1.0`.
2. Lint/format checks pass with zero warnings.

---

## 4. Step 1: Configuration and Error Contracts

### 4.1 Policy Enums (`config.py`)

```python
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
```

### 4.2 NiriStateConfig (Frozen Dataclass)

`NiriStateConfig` is a **frozen dataclass**, not a Pydantic model. Config objects are internal plumbing — they do not need Pydantic validation/serialization. This matches `NiriConfig`'s style and avoids awkward dataclass-inside-Pydantic nesting (review recommendation #3).

```python
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
```

### 4.3 Config Normalization

```python
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
        normalized_pypc = replace(
            config.pypc,
            backpressure_mode=BackpressureMode.FAIL_FAST,
        )
    except Exception as exc:
        raise StateConfigError(
            "Failed to normalize upstream backpressure for strict mode",
            cause=exc,
        ) from exc

    return replace(config, pypc=normalized_pypc)
```

### 4.4 Error Hierarchy (`errors.py`)

Note the two renamed errors from review recommendations #5:
- `SelectorWaitError` → **`WaitTimeoutError`** (it's a wait that timed out, not selector-specific)
- `WatchOverflowError` → **`SubscriptionOverflowError`** (affects all subscriber queues, not just watch)

```python
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
```

### 4.5 Tests for Step 1

**`tests/test_config.py`:**

```python
from __future__ import annotations

import pytest
from niri_pypc import BackpressureMode, NiriConfig

from niri_state.config import (
    CorrectnessMode,
    NiriStateConfig,
    normalize_config,
)
from niri_state.errors import StateConfigError


class TestNormalizeConfig:
    def test_strict_rewrites_backpressure_to_fail_fast(self) -> None:
        config = NiriStateConfig(
            pypc=NiriConfig(backpressure_mode=BackpressureMode.DROP_OLDEST),
            correctness_mode=CorrectnessMode.STRICT,
        )
        result = normalize_config(config)
        assert result.pypc.backpressure_mode is BackpressureMode.FAIL_FAST

    def test_strict_preserves_already_fail_fast(self) -> None:
        config = NiriStateConfig(
            pypc=NiriConfig(backpressure_mode=BackpressureMode.FAIL_FAST),
            correctness_mode=CorrectnessMode.STRICT,
        )
        result = normalize_config(config)
        assert result.pypc.backpressure_mode is BackpressureMode.FAIL_FAST

    def test_best_effort_leaves_backpressure_unchanged(self) -> None:
        config = NiriStateConfig(
            pypc=NiriConfig(backpressure_mode=BackpressureMode.DROP_OLDEST),
            correctness_mode=CorrectnessMode.BEST_EFFORT,
        )
        result = normalize_config(config)
        assert result.pypc.backpressure_mode is BackpressureMode.DROP_OLDEST

    def test_config_is_frozen(self) -> None:
        config = NiriStateConfig()
        with pytest.raises(AttributeError):
            config.correctness_mode = CorrectnessMode.STRICT  # type: ignore[misc]
```

**`tests/test_errors.py`:**

```python
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
```

### 4.6 Validation

```bash
devenv shell -- ruff check .
devenv shell -- ruff format --check .
devenv shell -- ty check .
devenv shell -- pytest -q tests/test_config.py tests/test_errors.py
```

**Pass criteria:**
1. Config normalization is deterministic: strict mode always produces FAIL_FAST.
2. All errors chain causes properly and carry relevant context fields.
3. `WaitTimeoutError` is catchable as `TimeoutError`.

---

## 5. Step 2: Core Immutable Models and DraftState

### 5.1 Type Aliases (`_core/models/types.py`)

```python
from __future__ import annotations

OutputName = str
WorkspaceId = int
WindowId = int
Revision = int
```

### 5.2 Entity Wrappers (`_core/models/entities.py`)

Wrap protocol models to isolate from upstream changes and provide stable identity keys. Each wrapper holds the upstream protocol model and exposes a stable identity field.

```python
from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from niri_pypc.types.generated.models import (
    KeyboardLayouts,
    Output,
    Overview,
    Window,
    Workspace,
)


class OutputState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    output_name: str
    protocol: Output


class WorkspaceState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    workspace_id: int
    protocol: Workspace


class WindowState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    window_id: int
    protocol: Window


class KeyboardState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    protocol: KeyboardLayouts
    current_name: str | None
    """Derived from protocol.names[protocol.current_idx] with bounds check."""


class OverviewState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    is_open: bool
```

### 5.3 Health State (`_core/models/health.py`)

```python
from __future__ import annotations

import enum


class HealthState(enum.Enum):
    BOOTSTRAPPING = "bootstrapping"
    LIVE = "live"
    STALE = "stale"
    RESYNCING = "resyncing"
    CLOSED = "closed"
    FAILED = "failed"
```

### 5.4 Diagnostics and Compatibility Metadata (`_core/models/snapshot.py`)

These types were undefined in the previous spec. They are now explicitly defined (review recommendation #6).

```python
from __future__ import annotations

from types import MappingProxyType
from pydantic import BaseModel, ConfigDict, field_validator

from niri_state._core.models.entities import (
    KeyboardState,
    OutputState,
    OverviewState,
    WindowState,
    WorkspaceState,
)
from niri_state._core.models.health import HealthState
from niri_state._core.models.types import (
    OutputName,
    Revision,
    WindowId,
    WorkspaceId,
)


class DiagnosticsInfo(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    last_transition_reason: str | None = None
    unknown_events_seen: int = 0
    last_invariant_violations: tuple[str, ...] | None = None


class CompatibilityInfo(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    compositor_version: str | None = None


class NiriSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    # Revisioning
    revision: Revision
    timestamp: float
    health: HealthState

    # Entity maps (MappingProxyType for enforced immutability)
    outputs: MappingProxyType[OutputName, OutputState]
    workspaces: MappingProxyType[WorkspaceId, WorkspaceState]
    windows: MappingProxyType[WindowId, WindowState]

    # Focus pointers
    focused_output_name: OutputName | None
    focused_workspace_id: WorkspaceId | None
    focused_window_id: WindowId | None

    # Domain state
    keyboard: KeyboardState
    overview: OverviewState

    # Precomputed indexes (MappingProxyType + tuple for full immutability)
    workspaces_by_output: MappingProxyType[OutputName, tuple[WorkspaceId, ...]]
    windows_by_workspace: MappingProxyType[WorkspaceId, tuple[WindowId, ...]]
    active_workspace_by_output: MappingProxyType[OutputName, WorkspaceId]

    # Metadata
    diagnostics: DiagnosticsInfo
    compatibility: CompatibilityInfo

    @field_validator(
        "outputs", "workspaces", "windows",
        "workspaces_by_output", "windows_by_workspace", "active_workspace_by_output",
        mode="before",
    )
    @classmethod
    def _wrap_in_mapping_proxy(cls, v: dict | MappingProxyType) -> MappingProxyType:
        if isinstance(v, MappingProxyType):
            return v
        return MappingProxyType(v)
```

**Why `MappingProxyType`:** Pydantic's `frozen=True` prevents `snapshot.outputs = new_dict` but does NOT prevent `snapshot.outputs[key] = value` on a regular dict. `MappingProxyType` enforces true read-only access on the container level. Index values use `tuple` (already immutable). This is review recommendation #4.

Note: `arbitrary_types_allowed=True` is required because `MappingProxyType` is not a standard Pydantic type.

### 5.5 ChangeSet (`_core/models/changes.py`)

```python
from __future__ import annotations

import enum

from pydantic import BaseModel, ConfigDict

from niri_state._core.models.types import Revision


class ChangeCause(enum.Enum):
    BOOTSTRAP = "bootstrap"
    EVENT = "event"
    RESYNC = "resync"
    STALE_TRANSITION = "stale_transition"
    LIFECYCLE = "lifecycle"


class ChangedDomain(enum.Enum):
    OUTPUTS = "outputs"
    WORKSPACES = "workspaces"
    WINDOWS = "windows"
    FOCUS = "focus"
    KEYBOARD = "keyboard"
    OVERVIEW = "overview"
    HEALTH = "health"


class ChangeSet(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    revision: Revision
    timestamp: float
    cause: ChangeCause
    changed_domains: frozenset[ChangedDomain]
    event_type: str | None = None
    event_summary: str | None = None
```

### 5.6 DraftState (`_core/models/draft.py`)

This is the **mutable intermediate** that reducers operate on (review recommendation #1). Reducers mutate the draft; a `freeze()` call constructs an immutable `NiriSnapshot`.

```python
from __future__ import annotations

import time
from types import MappingProxyType

from niri_pypc.types.generated.models import KeyboardLayouts, Overview

from niri_state._core.models.entities import (
    KeyboardState,
    OutputState,
    OverviewState,
    WindowState,
    WorkspaceState,
)
from niri_state._core.models.health import HealthState
from niri_state._core.models.snapshot import (
    CompatibilityInfo,
    DiagnosticsInfo,
    NiriSnapshot,
)
from niri_state._core.models.types import (
    OutputName,
    Revision,
    WindowId,
    WorkspaceId,
)


class DraftState:
    """Mutable state representation for reducers.

    Reducers modify entity maps, focus pointers, and domain state on this
    object. Call freeze() to produce an immutable NiriSnapshot for publication.
    """

    def __init__(
        self,
        *,
        outputs: dict[OutputName, OutputState],
        workspaces: dict[WorkspaceId, WorkspaceState],
        windows: dict[WindowId, WindowState],
        focused_output_name: OutputName | None,
        focused_workspace_id: WorkspaceId | None,
        focused_window_id: WindowId | None,
        keyboard: KeyboardState,
        overview: OverviewState,
        health: HealthState,
        diagnostics: DiagnosticsInfo,
        compatibility: CompatibilityInfo,
    ) -> None:
        self.outputs = outputs
        self.workspaces = workspaces
        self.windows = windows
        self.focused_output_name = focused_output_name
        self.focused_workspace_id = focused_workspace_id
        self.focused_window_id = focused_window_id
        self.keyboard = keyboard
        self.overview = overview
        self.health = health
        self.diagnostics = diagnostics
        self.compatibility = compatibility

    @classmethod
    def from_snapshot(cls, snapshot: NiriSnapshot) -> DraftState:
        """Create a mutable draft from a published snapshot."""
        return cls(
            outputs=dict(snapshot.outputs),
            workspaces=dict(snapshot.workspaces),
            windows=dict(snapshot.windows),
            focused_output_name=snapshot.focused_output_name,
            focused_workspace_id=snapshot.focused_workspace_id,
            focused_window_id=snapshot.focused_window_id,
            keyboard=snapshot.keyboard,
            overview=snapshot.overview,
            health=snapshot.health,
            diagnostics=snapshot.diagnostics,
            compatibility=snapshot.compatibility,
        )

    def build_indexes(
        self,
    ) -> tuple[
        dict[OutputName, tuple[WorkspaceId, ...]],
        dict[WorkspaceId, tuple[WindowId, ...]],
        dict[OutputName, WorkspaceId],
    ]:
        """Compute derived indexes from current entity maps."""
        workspaces_by_output: dict[OutputName, list[WorkspaceId]] = {}
        active_workspace_by_output: dict[OutputName, WorkspaceId] = {}
        for ws_id, ws in self.workspaces.items():
            output = ws.protocol.output
            if output is not None:
                workspaces_by_output.setdefault(output, []).append(ws_id)
                if ws.protocol.is_active:
                    active_workspace_by_output[output] = ws_id

        windows_by_workspace: dict[WorkspaceId, list[WindowId]] = {}
        for win_id, win in self.windows.items():
            ws_id = win.protocol.workspace_id
            if ws_id is not None:
                windows_by_workspace.setdefault(ws_id, []).append(win_id)
        # Note: windows with workspace_id=None (floating/unassigned) are
        # intentionally excluded from this index. Access them via the
        # windows entity map directly or use selectors.get_floating_windows().

        return (
            {k: tuple(sorted(v)) for k, v in workspaces_by_output.items()},
            {k: tuple(sorted(v)) for k, v in windows_by_workspace.items()},
            active_workspace_by_output,
        )

    def freeze(self, *, revision: Revision) -> NiriSnapshot:
        """Freeze draft into an immutable published snapshot."""
        ws_by_output, win_by_ws, active_ws = self.build_indexes()

        return NiriSnapshot(
            revision=revision,
            timestamp=time.monotonic(),
            health=self.health,
            outputs=MappingProxyType(dict(self.outputs)),
            workspaces=MappingProxyType(dict(self.workspaces)),
            windows=MappingProxyType(dict(self.windows)),
            focused_output_name=self.focused_output_name,
            focused_workspace_id=self.focused_workspace_id,
            focused_window_id=self.focused_window_id,
            keyboard=self.keyboard,
            overview=self.overview,
            workspaces_by_output=MappingProxyType(ws_by_output),
            windows_by_workspace=MappingProxyType(win_by_ws),
            active_workspace_by_output=MappingProxyType(active_ws),
            diagnostics=self.diagnostics,
            compatibility=self.compatibility,
        )
```

**Floating window indexing (review recommendation #7):** Windows with `workspace_id=None` are intentionally excluded from `windows_by_workspace`. They are accessible via `snapshot.windows` directly. Selectors will provide `get_floating_windows()` for ergonomic access.

### 5.7 BootstrapPayload (`_core/models/bootstrap_payload.py`)

Lives in `_core` to maintain the import boundary (review recommendation #2). The runtime bootstrap orchestrator populates it; the core snapshot builder consumes it.

```python
from __future__ import annotations

from dataclasses import dataclass

from niri_pypc.types.generated.models import (
    KeyboardLayouts,
    Output,
    Overview,
    Window,
    Workspace,
)


@dataclass(frozen=True, slots=True)
class BootstrapPayload:
    """Normalized query results ready for initial snapshot construction.

    Populated by _runtime/bootstrap.py, consumed by _core/snapshot_builder.py.
    """

    outputs: dict[str, Output]
    workspaces: list[Workspace]
    windows: list[Window]
    focused_output: Output | None
    focused_window: Window | None
    keyboard_layouts: KeyboardLayouts
    overview: Overview
    compositor_version: str | None = None
```

### 5.8 Tests for Step 2

**`tests/core/models/test_snapshot.py`:**

```python
from __future__ import annotations

from types import MappingProxyType

import pytest
from niri_state._core.models.health import HealthState
from niri_state._core.models.snapshot import (
    CompatibilityInfo,
    DiagnosticsInfo,
    NiriSnapshot,
)
from niri_state._core.models.entities import (
    KeyboardState,
    OverviewState,
)
from niri_pypc.types.generated.models import KeyboardLayouts


def _make_minimal_snapshot(**overrides):
    """Build a minimal valid snapshot for testing."""
    defaults = dict(
        revision=1,
        timestamp=0.0,
        health=HealthState.LIVE,
        outputs={},
        workspaces={},
        windows={},
        focused_output_name=None,
        focused_workspace_id=None,
        focused_window_id=None,
        keyboard=KeyboardState(
            protocol=KeyboardLayouts(current_idx=0, names=["us"]),
            current_name="us",
        ),
        overview=OverviewState(is_open=False),
        workspaces_by_output={},
        windows_by_workspace={},
        active_workspace_by_output={},
        diagnostics=DiagnosticsInfo(),
        compatibility=CompatibilityInfo(),
    )
    defaults.update(overrides)
    return NiriSnapshot(**defaults)


class TestSnapshotImmutability:
    def test_attribute_assignment_raises(self) -> None:
        snap = _make_minimal_snapshot()
        with pytest.raises(Exception):
            snap.revision = 2  # type: ignore[misc]

    def test_entity_map_is_mapping_proxy(self) -> None:
        snap = _make_minimal_snapshot()
        assert isinstance(snap.outputs, MappingProxyType)
        assert isinstance(snap.workspaces, MappingProxyType)
        assert isinstance(snap.windows, MappingProxyType)

    def test_entity_map_mutation_raises(self) -> None:
        snap = _make_minimal_snapshot()
        with pytest.raises(TypeError):
            snap.outputs["test"] = None  # type: ignore[index]

    def test_index_map_mutation_raises(self) -> None:
        snap = _make_minimal_snapshot()
        with pytest.raises(TypeError):
            snap.workspaces_by_output["test"] = ()  # type: ignore[index]
```

**`tests/core/models/test_draft.py`:**

```python
from __future__ import annotations

from types import MappingProxyType

from niri_pypc.types.generated.models import KeyboardLayouts, Workspace

from niri_state._core.models.draft import DraftState
from niri_state._core.models.entities import (
    KeyboardState,
    OverviewState,
    WorkspaceState,
)
from niri_state._core.models.health import HealthState
from niri_state._core.models.snapshot import (
    CompatibilityInfo,
    DiagnosticsInfo,
)


def _make_draft(**overrides) -> DraftState:
    defaults = dict(
        outputs={},
        workspaces={},
        windows={},
        focused_output_name=None,
        focused_workspace_id=None,
        focused_window_id=None,
        keyboard=KeyboardState(
            protocol=KeyboardLayouts(current_idx=0, names=["us"]),
            current_name="us",
        ),
        overview=OverviewState(is_open=False),
        health=HealthState.LIVE,
        diagnostics=DiagnosticsInfo(),
        compatibility=CompatibilityInfo(),
    )
    defaults.update(overrides)
    return DraftState(**defaults)


class TestDraftState:
    def test_mutable_entity_maps(self) -> None:
        draft = _make_draft()
        ws = Workspace(
            id=1, idx=0, is_active=True, is_focused=True,
            is_urgent=False, output="eDP-1",
        )
        draft.workspaces[1] = WorkspaceState(workspace_id=1, protocol=ws)
        assert 1 in draft.workspaces

    def test_freeze_produces_immutable_snapshot(self) -> None:
        draft = _make_draft()
        snap = draft.freeze(revision=1)
        assert snap.revision == 1
        assert isinstance(snap.outputs, MappingProxyType)

    def test_build_indexes_workspaces_by_output(self) -> None:
        ws = Workspace(
            id=1, idx=0, is_active=True, is_focused=False,
            is_urgent=False, output="eDP-1",
        )
        draft = _make_draft(
            workspaces={1: WorkspaceState(workspace_id=1, protocol=ws)}
        )
        ws_by_out, _, active_ws = draft.build_indexes()
        assert ws_by_out["eDP-1"] == (1,)
        assert active_ws["eDP-1"] == 1

    def test_from_snapshot_roundtrip(self) -> None:
        draft = _make_draft()
        snap = draft.freeze(revision=1)
        draft2 = DraftState.from_snapshot(snap)
        snap2 = draft2.freeze(revision=2)
        assert snap2.revision == 2
        assert snap2.health == snap.health
```

### 5.9 Validation

```bash
devenv shell -- ruff check .
devenv shell -- ruff format --check .
devenv shell -- ty check .
devenv shell -- pytest -q tests/core/models/
```

**Pass criteria:**
1. `NiriSnapshot` is truly immutable — both attribute assignment and container mutation fail.
2. `DraftState` is freely mutable and `freeze()` produces correct snapshots.
3. Indexes are deterministic (sorted tuples).
4. `from_snapshot` → `freeze` roundtrip preserves state.

---

## 6. Step 3: Lifecycle FSM

### 6.1 Transition Table

Place the FSM in `_core/models/health.py` alongside `HealthState`, since it is pure logic with no IO.

```python
# Add to _core/models/health.py

from niri_state.errors import StateLifecycleError

_LEGAL_TRANSITIONS: dict[HealthState, frozenset[HealthState]] = {
    HealthState.BOOTSTRAPPING: frozenset({HealthState.LIVE, HealthState.FAILED}),
    HealthState.LIVE: frozenset({HealthState.STALE, HealthState.CLOSED}),
    HealthState.STALE: frozenset({
        HealthState.RESYNCING, HealthState.LIVE, HealthState.CLOSED,
    }),
    HealthState.RESYNCING: frozenset({
        HealthState.LIVE, HealthState.STALE, HealthState.FAILED, HealthState.CLOSED,
    }),
    HealthState.FAILED: frozenset({HealthState.CLOSED}),
    HealthState.CLOSED: frozenset(),
}


def validate_transition(
    current: HealthState,
    target: HealthState,
    *,
    reason: str,
) -> None:
    """Validate a lifecycle state transition.

    Raises StateLifecycleError if the transition is not legal.
    """
    legal = _LEGAL_TRANSITIONS.get(current, frozenset())
    if target not in legal:
        raise StateLifecycleError(
            f"Illegal transition {current.value} -> {target.value}: {reason}",
            current_state=current.value,
            target_state=target.value,
        )
```

The runtime will use this pure validation function before applying transitions. Single-owner mutation is enforced at the runtime level (the event consumer task is the sole writer).

### 6.2 Tests for Step 3

**`tests/core/models/test_health.py`:**

```python
from __future__ import annotations

import pytest
from niri_state._core.models.health import HealthState, validate_transition
from niri_state.errors import StateLifecycleError


class TestLifecycleFSM:
    @pytest.mark.parametrize(
        "current,target",
        [
            (HealthState.BOOTSTRAPPING, HealthState.LIVE),
            (HealthState.BOOTSTRAPPING, HealthState.FAILED),
            (HealthState.LIVE, HealthState.STALE),
            (HealthState.LIVE, HealthState.CLOSED),
            (HealthState.STALE, HealthState.RESYNCING),
            (HealthState.STALE, HealthState.LIVE),
            (HealthState.STALE, HealthState.CLOSED),
            (HealthState.RESYNCING, HealthState.LIVE),
            (HealthState.RESYNCING, HealthState.STALE),
            (HealthState.RESYNCING, HealthState.FAILED),
            (HealthState.RESYNCING, HealthState.CLOSED),
            (HealthState.FAILED, HealthState.CLOSED),
        ],
    )
    def test_legal_transitions_succeed(self, current: HealthState, target: HealthState) -> None:
        validate_transition(current, target, reason="test")

    @pytest.mark.parametrize(
        "current,target",
        [
            (HealthState.BOOTSTRAPPING, HealthState.STALE),
            (HealthState.BOOTSTRAPPING, HealthState.CLOSED),
            (HealthState.LIVE, HealthState.BOOTSTRAPPING),
            (HealthState.LIVE, HealthState.RESYNCING),
            (HealthState.LIVE, HealthState.FAILED),
            (HealthState.CLOSED, HealthState.LIVE),
            (HealthState.CLOSED, HealthState.BOOTSTRAPPING),
            (HealthState.FAILED, HealthState.LIVE),
            (HealthState.FAILED, HealthState.STALE),
        ],
    )
    def test_illegal_transitions_raise(self, current: HealthState, target: HealthState) -> None:
        with pytest.raises(StateLifecycleError) as exc_info:
            validate_transition(current, target, reason="test")
        assert exc_info.value.current_state == current.value
        assert exc_info.value.target_state == target.value

    def test_transition_reason_in_error(self) -> None:
        with pytest.raises(StateLifecycleError, match="some reason"):
            validate_transition(
                HealthState.CLOSED, HealthState.LIVE, reason="some reason"
            )
```

### 6.3 Validation

```bash
devenv shell -- ruff check .
devenv shell -- ruff format --check .
devenv shell -- pytest -q tests/core/models/test_health.py
```

**Pass criteria:**
1. Every legal transition from Section 6 of `FINAL_SPEC` succeeds.
2. Every illegal transition raises `StateLifecycleError` with correct context.
3. Transition reasons appear in error messages.

---

## 7. Step 4: Snapshot Builder and Index Construction

### 7.1 Implement `build_initial_snapshot(...)`

Create `_core/snapshot_builder.py` and implement:

```python
from __future__ import annotations

from niri_state._core.models.bootstrap_payload import BootstrapPayload
from niri_state._core.models.draft import DraftState
from niri_state._core.models.entities import (
    KeyboardState,
    OutputState,
    OverviewState,
    WindowState,
    WorkspaceState,
)
from niri_state._core.models.health import HealthState
from niri_state._core.models.snapshot import CompatibilityInfo, DiagnosticsInfo


def _derive_keyboard_current_name(layouts) -> str | None:
    if layouts.current_idx < 0:
        return None
    if layouts.current_idx >= len(layouts.names):
        return None
    return layouts.names[layouts.current_idx]


def build_initial_draft(payload: BootstrapPayload) -> DraftState:
    outputs = {
        name: OutputState(output_name=name, protocol=output)
        for name, output in payload.outputs.items()
    }
    workspaces = {
        ws.id: WorkspaceState(workspace_id=ws.id, protocol=ws)
        for ws in payload.workspaces
    }
    windows = {
        win.id: WindowState(window_id=win.id, protocol=win)
        for win in payload.windows
    }

    focused_output_name = payload.focused_output.name if payload.focused_output else None
    focused_window_id = payload.focused_window.id if payload.focused_window else None

    focused_workspace_id = None
    if payload.focused_window is not None:
        focused_workspace_id = payload.focused_window.workspace_id
    if focused_workspace_id is None and focused_output_name is not None:
        for ws in payload.workspaces:
            if ws.output == focused_output_name and ws.is_focused:
                focused_workspace_id = ws.id
                break

    keyboard = KeyboardState(
        protocol=payload.keyboard_layouts,
        current_name=_derive_keyboard_current_name(payload.keyboard_layouts),
    )
    overview = OverviewState(is_open=payload.overview.is_open)

    return DraftState(
        outputs=outputs,
        workspaces=workspaces,
        windows=windows,
        focused_output_name=focused_output_name,
        focused_workspace_id=focused_workspace_id,
        focused_window_id=focused_window_id,
        keyboard=keyboard,
        overview=overview,
        health=HealthState.BOOTSTRAPPING,
        diagnostics=DiagnosticsInfo(),
        compatibility=CompatibilityInfo(compositor_version=payload.compositor_version),
    )
```

### 7.2 Key Rules

1. Do not run invariants in the builder itself if you need draft mutation first; run invariants immediately after builder output in orchestrator.
2. Replace-all identity is map-key-based: output name, workspace id, window id.
3. Focus pointers may be `None`; never synthesize fake ids.

### 7.3 Tests for Step 4

1. `tests/core/test_snapshot_builder.py`:
- builds maps with expected keys.
- derives focus from focused window when available.
- fallback focus derivation from focused workspace on focused output.
- keyboard `current_idx` out of range yields `current_name is None`.
- compatibility info carries version string.
2. Add edge test: duplicate ids in bootstrap lists should deterministically keep the last element and log diagnostic decision (or fail, if you choose strict behavior; document choice).

### 7.4 Validation

```bash
devenv shell -- ruff check .
devenv shell -- ruff format --check .
devenv shell -- ty check .
devenv shell -- pytest -q tests/core/test_snapshot_builder.py
```

**Pass criteria:**
1. Snapshot builder output is deterministic.
2. Derived fields match explicit rules.

---

## 8. Step 5: Invariant Engine

### 8.1 Implement explicit invariant checks in `_core/invariants.py`

Required checks:
1. Map key matches wrapper identity field.
2. `focused_workspace_id` exists when non-null.
3. `focused_window_id` exists when non-null.
4. If focused window has workspace id, it matches `focused_workspace_id` (when both non-null).
5. Workspace `active_window_id` references existing window when non-null.
6. Window `workspace_id` references existing workspace when non-null.
7. `workspaces_by_output` entries reference existing workspaces and workspace output matches key.
8. `windows_by_workspace` entries reference existing windows and window workspace matches key.
9. `active_workspace_by_output` points to existing workspace with matching output and `is_active=True`.
10. Duplicate ids do not appear inside index tuples.

Suggested API:

```python
from __future__ import annotations

from niri_state._core.models.snapshot import NiriSnapshot


def collect_invariant_violations(snapshot: NiriSnapshot) -> tuple[str, ...]:
    violations: list[str] = []
    ...
    return tuple(violations)


def assert_invariants(snapshot: NiriSnapshot) -> None:
    violations = collect_invariant_violations(snapshot)
    if violations:
        from niri_state.errors import InvariantError
        raise InvariantError(
            "Snapshot invariants violated",
            violations=violations,
            revision=snapshot.revision,
        )
```

### 8.2 Policy handling contract

Invariant engine stays policy-agnostic. Policy (`FAIL` vs `STALE`) is applied by runtime caller.

### 8.3 Tests for Step 5

1. One test per invariant rule violation.
2. One aggregated test with multiple violations verifies deterministic message order.
3. One valid snapshot test asserts no violations.

### 8.4 Validation

```bash
devenv shell -- ruff check .
devenv shell -- ruff format --check .
devenv shell -- pytest -q tests/core/test_invariants.py
```

**Pass criteria:**
1. Violations are specific and stable.
2. Valid snapshots pass with zero noise.

---

## 9. Step 6: Domain Reducers

### 9.1 Reducer signatures

Use a consistent signature pattern:

```python
def apply_<domain>_event(draft: DraftState, event: <EventType>) -> bool:
    """Mutate draft. Return True if state changed."""
```

Return value drives `changed_domains` accuracy.

### 9.2 `windows.py`

Implement handlers for:
1. `WindowsChangedEvent`: full replacement of window map.
2. `WindowOpenedOrChangedEvent`: upsert window by id.
3. `WindowClosedEvent`: remove window id if present.
4. `WindowFocusChangedEvent`: update `focused_window_id`; update `focused_workspace_id` from target window.
5. `WindowUrgencyChangedEvent`: patch `is_urgent`.
6. `WindowFocusTimestampChangedEvent`: patch `focus_timestamp`.
7. `WindowLayoutsChangedEvent`: patch per-window `layout` from `changes` list.

Use `model_copy(update=...)` to keep wrapper models frozen:

```python
updated_protocol = old.protocol.model_copy(update={"is_urgent": event.urgent})
draft.windows[event.id] = old.model_copy(update={"protocol": updated_protocol})
```

### 9.3 `workspaces.py`

Implement handlers for:
1. `WorkspacesChangedEvent`: full replacement.
2. `WorkspaceActivatedEvent`: set target workspace `is_active=True`; clear `is_active` from others on same output; if `focused=True`, update `is_focused` and `draft.focused_workspace_id`.
3. `WorkspaceActiveWindowChangedEvent`: patch target workspace `active_window_id`.
4. `WorkspaceUrgencyChangedEvent`: patch `is_urgent`.

### 9.4 `keyboard.py`

1. `KeyboardLayoutsChangedEvent`: replace protocol payload; recompute `current_name` with bounds checks.
2. `KeyboardLayoutSwitchedEvent`: patch `current_idx`; recompute `current_name`.

### 9.5 `overview.py`

1. `OverviewOpenedOrClosedEvent`: set `overview.is_open`.

### 9.6 Tests for Step 6

1. Variant-by-variant tests.
2. No-op tests when event does not change current value.
3. Replace-all tests proving stale entities are removed.
4. Cross-field consistency tests (focus/workspace coupling).

### 9.7 Validation

```bash
devenv shell -- ruff check .
devenv shell -- ruff format --check .
devenv shell -- ty check .
devenv shell -- pytest -q tests/core/reducers/
```

**Pass criteria:**
1. Every required variant is covered.
2. Reducers are pure draft mutators (no IO/time).

---

## 10. Step 7: Root Reducer and Unknown Event Policy

### 10.1 Implement root dispatch with `match/case`

In `_core/reducers/root.py`, dispatch on concrete classes:

```python
match event:
    case WindowsChangedEvent() as e:
        ...
    case WindowOpenedOrChangedEvent() as e:
        ...
    case WorkspacesChangedEvent() as e:
        ...
    case KeyboardLayoutsChangedEvent() as e:
        ...
    case OverviewOpenedOrClosedEvent() as e:
        ...
    case ConfigLoadedEvent() as e:
        ...  # metadata no-op
    case ScreenshotCapturedEvent() as e:
        ...  # metadata no-op
    case UnknownEvent() as e:
        ...  # policy path
    case _:
        ...  # defensive stale/fail path
```

### 10.2 Define reducer result contract

Create result model:

```python
class ReduceResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    applied: bool
    changed_domains: frozenset[ChangedDomain]
    cause: ChangeCause
    event_type: str | None = None
    event_summary: str | None = None
```

### 10.3 Unknown event policy semantics

1. `STALE`:
- increment diagnostics unknown counter.
- set health `STALE`.
- return `applied=True`, changed domains include `HEALTH`.
2. `FAIL`:
- raise `DesyncError(event_type=variant_name)`.
3. `IGNORE`:
- allow only if configured and event marked harmless category.
- add diagnostic note.
- `applied=False` unless diagnostics mutation is treated as change.

### 10.4 Metadata events

`ConfigLoadedEvent` and `ScreenshotCapturedEvent` must be explicit branches; add diagnostic breadcrumbs (optional), but do not mutate domain state maps.

### 10.5 Tests for Step 7

1. Dispatch coverage test for all known event classes.
2. Unknown event tests for each policy.
3. Metadata no-op tests.
4. Fallback branch test for unexpected type.

### 10.6 Validation

```bash
devenv shell -- ruff check .
devenv shell -- ruff format --check .
devenv shell -- pytest -q tests/core/reducers/test_root.py
```

**Pass criteria:**
1. Unknown impactful input never silently preserves `LIVE` in stale/fail policies.
2. Root reducer result metadata is accurate.

---

## 11. Step 8: Bootstrap Pipeline

### 11.1 Runtime bootstrap contract in `_runtime/bootstrap.py`

Implement an orchestrator function used by `NiriState.connect()`:

```python
async def run_bootstrap(config: NiriStateConfig) -> BootstrapOutcome:
    ...
```

`BootstrapOutcome` includes:
1. opened `NiriConnectionBundle`
2. first published snapshot candidate
3. first `ChangeSet`
4. any buffered/replayed event count metrics

### 11.2 Exact sequence

1. Normalize config (`normalize_config`).
2. Open bundle (`await NiriConnectionBundle.open(config.pypc)`).
3. Start event buffer task immediately:
- read `bundle.events.next()` in a loop and append to buffer queue/list.
- stop buffer only after query phase ends.
4. Execute mandatory query suite via `bundle.client.request(...)` in fixed order.
5. Validate response types; map to `BootstrapPayload`.
6. Build draft via `build_initial_draft(payload)`.
7. Freeze to revision `0` (bootstrap internal snapshot).
8. Run invariants.
9. Replay buffered events through root reducer into draft.
10. Freeze replay-closed snapshot at revision `1` with `health=LIVE`.
11. Run invariants again.
12. Return outcome.

### 11.3 Response normalization helpers

Implement per-query helper functions that assert response variant type explicitly and raise `BootstrapError(query="...")` on mismatch.

### 11.4 Failure behavior

1. Any query failure: raise `BootstrapError` with chained cause.
2. Ensure bundle closes on bootstrap failure.
3. If buffer task fails, surface cause as bootstrap failure.

### 11.5 Tests for Step 8

1. Happy path test with mocked bundle + query responses + buffered events.
2. Type mismatch tests for each mandatory query.
3. Race-closure test: assert no `LIVE` snapshot before replay completion.
4. Cleanup-on-failure test (bundle closed).
5. Unknown event in buffer obeys policy.

### 11.6 Validation

```bash
devenv shell -- ruff check .
devenv shell -- ruff format --check .
devenv shell -- ty check .
devenv shell -- pytest -q tests/runtime/test_bootstrap.py
```

**Pass criteria:**
1. First externally visible `LIVE` snapshot is replay-closed.
2. All bootstrap failures are typed and actionable.

---

## 12. Step 9: Store and Subscription Runtime

### 12.1 Implement `NiriState` composition model

`NiriState` should compose runtime pieces rather than embedding all logic in one class.

Core responsibilities:
1. Hold current snapshot.
2. Own single mutation loop task.
3. Own broadcaster/subscriber registry.
4. Expose public API: `snapshot`, `subscribe`, `watch`, `wait_until`, `refresh`, `close`.

### 12.2 Single-owner mutation loop

In `_runtime/store.py`, create an internal event consumer task that:
1. reads events from `bundle.events`.
2. applies root reducer.
3. freezes next snapshot with incremented revision.
4. runs invariants.
5. emits `ChangeSet` + snapshot to broadcaster.

Only this loop may mutate runtime state.

### 12.3 Broadcaster (`_runtime/broadcaster.py`)

Implement:
1. subscriber registration returning async iterator.
2. bounded queue per subscriber.
3. overflow policy:
- `DROP_OLDEST`: drop oldest item then enqueue new item.
- `FAIL_FAST`: raise `SubscriptionOverflowError`, mark runtime stale/failed per policy.
4. shutdown signaling to all subscribers on close.

### 12.4 `close()` behavior

1. Idempotent.
2. Cancel loop tasks.
3. Close bundle.
4. Transition health to `CLOSED` if legal.
5. Terminate subscribers/watchers/waiters with explicit lifecycle signal.

### 12.5 Tests for Step 9

1. Revision monotonicity test.
2. Atomic publish test (no partial snapshot).
3. Multi-subscriber test.
4. Slow subscriber overflow tests for both modes.
5. Idempotent close test.
6. Event stream terminal error propagation test.

### 12.6 Validation

```bash
devenv shell -- ruff check .
devenv shell -- ruff format --check .
devenv shell -- pytest -q tests/runtime/test_store.py tests/runtime/test_broadcaster.py
```

**Pass criteria:**
1. Publication is atomic and monotonic.
2. Overflow behavior is deterministic and policy-correct.

---

## 13. Step 10: Wait/Watch APIs

### 13.1 Implement waits in `_runtime/waiters.py`

`wait_until(predicate, timeout=None, health_policy=None)` behavior:
1. evaluate immediately against current snapshot.
2. if unsatisfied, subscribe to publication stream.
3. on each publication, apply health gate then predicate.
4. timeout => `WaitTimeoutError(timeout=...)`.
5. close/cancel => propagate lifecycle/cancel cleanly.

### 13.2 Implement watch

`watch(selector)` behavior:
1. emit selector value from current snapshot first.
2. only emit again when `new_value != previous_value`.
3. terminate on close.

### 13.3 Selector-based helpers

Optional helper:

```python
async def wait_for_selector(
    selector: Callable[[NiriSnapshot], T],
    predicate: Callable[[T], bool],
    ...
) -> T: ...
```

### 13.4 Tests for Step 10

1. immediate success wait.
2. timeout wait.
3. cancellation wait.
4. live-only gate rejects stale snapshots.
5. allow-stale gate accepts stale snapshots.
6. watch emits initial value once.
7. watch emits only on equality changes.
8. watch terminates on close.

### 13.5 Validation

```bash
devenv shell -- ruff check .
devenv shell -- ruff format --check .
devenv shell -- pytest -q tests/runtime/test_waiters.py
```

**Pass criteria:**
1. Wait/watch are event-driven.
2. Timeout and close semantics are correct and deterministic.

---

## 14. Step 11: Resync/Recovery Coordinator

### 14.1 Implement `_runtime/resync.py`

Key APIs:
1. `mark_stale(reason: str, *, event_type: str | None = None)`
2. `refresh()`
3. `attempt_auto_resync()`

### 14.2 Manual policy (`ResyncPolicy.MANUAL`)

1. On stale trigger, transition `LIVE -> STALE`.
2. Do not auto-bootstrap.
3. Wait for `refresh()` call.
4. `refresh()` executes bootstrap+replay and publishes new `LIVE` snapshot.

### 14.3 Auto policy (`ResyncPolicy.AUTO`)

1. On stale trigger, transition `LIVE -> STALE -> RESYNCING`.
2. Retry bootstrap with bounded attempts and backoff.
3. Success => publish `LIVE`.
4. Failure => `STALE` or `FAILED` per policy decision.

### 14.4 `refresh()` semantics in AUTO mode

`refresh()` should force immediate resync attempt even in AUTO mode (review requirement from intro paragraph).

### 14.5 Tests for Step 11

1. manual stale remains stale until refresh.
2. manual refresh success returns live.
3. auto stale triggers resync loop.
4. auto retry exhaustion path.
5. refresh in AUTO short-circuits waiting and triggers immediate attempt.
6. historical snapshots remain immutable across resync.

### 14.6 Validation

```bash
devenv shell -- ruff check .
devenv shell -- ruff format --check .
devenv shell -- pytest -q tests/runtime/test_resync.py
```

**Pass criteria:**
1. Policy-specific behavior is exact.
2. Resync transitions are legal and observable.

---

## 15. Step 12: Selector Modules and Public Exports

### 15.1 Implement selector families

In `selectors/`:
1. `outputs.py`: output lookup/list helpers.
2. `workspaces.py`: workspace lookup per output/active/focused helpers.
3. `windows.py`: window lookup, windows by workspace, floating windows helpers.
4. `focus.py`: focused output/workspace/window selectors.
5. `keyboard.py`: layout names/current layout selectors.
6. `overview.py`: open-state selector.
7. `aggregates.py`: high-level combined views.

### 15.2 Selector rules

1. Pure functions only.
2. Missing keys return `None`/empty tuple/list (document exact type).
3. Do not expose mutable internals.
4. For refresh-backed or query-only surfaces, add docstring freshness notes.

### 15.3 Exports

1. `selectors/__init__.py` exports stable selector symbols.
2. `niri_state/__init__.py` exports `NiriState`, config enums, errors, and selector namespace.

### 15.4 Tests for Step 12

1. correctness tests per selector.
2. missing-entity behavior tests.
3. floating window selector tests (`workspace_id is None`).
4. API import surface test.

### 15.5 Validation

```bash
devenv shell -- ruff check .
devenv shell -- ruff format --check .
devenv shell -- ty check .
devenv shell -- pytest -q tests/selectors/
```

**Pass criteria:**
1. Selector outputs are stable and predictable.
2. Public exports match docs.

---

## 16. Step 13: Integration and Replay Harness

### 16.1 Integration tests (`tests/integration/test_bootstrap_convergence.py`)

Cover:
1. bootstrap snapshot + replayed events converge to expected state.
2. event stream EOF/terminal error transitions.
3. stale->resync->live path.

Use in-process Unix socket mock servers similar to `.context/niri-pypc/tests` patterns.

### 16.2 Replay harness (`tests/integration/test_replay.py`)

Define trace format:

```python
@dataclass(frozen=True)
class ReplayTrace:
    name: str
    bootstrap: BootstrapPayload
    events: tuple[object, ...]
    expected_final_health: HealthState
    expected_window_ids: tuple[int, ...]
    ...
```

Replay runner:
1. build draft from bootstrap.
2. replay events through root reducer.
3. freeze snapshot.
4. assert expected fields.

### 16.3 Determinism assertions

For each trace, run replay twice and assert equality of serialized snapshot projection (ignore timestamp field or inject deterministic clock).

### 16.4 Tests for Step 13

1. replace-all + incremental sequence.
2. unknown event stale policy trace.
3. unknown event fail policy trace.
4. multi-output active workspace correctness trace.
5. floating-window persistence trace.

### 16.5 Validation

```bash
devenv shell -- ruff check .
devenv shell -- ruff format --check .
devenv shell -- pytest -q tests/integration/
```

**Pass criteria:**
1. Replay uses same reducer path as runtime.
2. Determinism is proven by repeated replay.

---

## 17. Step 14: API Polish and Packaging

### 17.1 Public API consistency pass

1. audit naming across docs/spec/code for exact match.
2. ensure deprecated names are not exported.
3. confirm error names: `WaitTimeoutError`, `SubscriptionOverflowError`.

### 17.2 Documentation updates

Update README and package docs with:
1. connection lifecycle + health states.
2. freshness semantics.
3. unknown-event policy and stale behavior.
4. wait/watch examples.
5. resync policy examples.

### 17.3 Packaging checks

1. verify `pyproject.toml` metadata (`name = "niri-state"`, version source).
2. ensure `src` layout install works.
3. confirm editable install imports expected package.

### 17.4 Tests for Step 14

1. doc snippet tests (or simple smoke tests mirroring docs examples).
2. import surface smoke test for key public symbols.

### 17.5 Validation

```bash
devenv shell -- ruff check .
devenv shell -- ruff format --check .
devenv shell -- ty check .
devenv shell -- pytest -q
```

**Pass criteria:**
1. Full suite passes.
2. Documentation examples remain valid.

---

## 18. Mandatory Validation Matrix

Run on every behavior-changing step:
1. `devenv shell -- ruff check .`
2. `devenv shell -- ruff format --check .`
3. `devenv shell -- ty check .` when interfaces/types changed.
4. targeted `devenv shell -- pytest -q ...`.

Before final merge/release:
1. `devenv shell -- uv sync --extra dev`
2. `devenv shell -- ruff check .`
3. `devenv shell -- ruff format --check .`
4. `devenv shell -- ty check .`
5. `devenv shell -- pytest -q`

Mandatory evidence to record in PR description:
1. command outputs summary (pass/fail).
2. list of replay traces executed.
3. list of policy-mode tests executed (`STALE`, `FAIL`, `IGNORE`, `MANUAL`, `AUTO`).

---

## 19. Completion Checklist

Implementation is complete only if all are true:
1. package/module layout matches final spec.
2. first published `LIVE` snapshot is replay-closed.
3. reducers are deterministic and pure.
4. invariant checks run on build and publish paths.
5. unknown events are policy-handled and audited.
6. publication path is single-owner and atomic.
7. wait/watch/subscribe/refresh/close semantics are tested.
8. manual and auto resync policies are implemented and tested.
9. replay determinism harness exists and passes.
10. full quality gate passes without suppressing failures.

If any item is false, do not claim completion.
