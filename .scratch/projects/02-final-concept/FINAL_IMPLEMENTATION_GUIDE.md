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


# Step 4: Implement Snapshot Builder and Index Construction

Implementation work:
1. Implement `BootstrapPayload` model (likely in bootstrap/runtime layer with core-compatible shape).
2. Implement `_core/snapshot_builder.py::build_initial_snapshot(...)`.
3. Construct maps:
- outputs keyed by output name.
- workspaces keyed by workspace id.
- windows keyed by window id.
4. Build indexes:
- `workspaces_by_output`
- `windows_by_workspace`
- `active_workspace_by_output`
5. Derive focus pointers from focused output/window payloads and inferred workspace relationship.
6. Derive keyboard `current_name` safely with index bounds checks.
7. Initialize overview/diagnostics/compatibility metadata.

Validation for Step 4:
1. Tests for nominal bootstrap mapping.
2. Tests for null-focused output/window cases.
3. Tests where focused window/workspace references missing entities (must follow defined policy).
4. Tests for keyboard out-of-range `current_idx` behavior.
5. `devenv shell -- ruff check .`
6. `devenv shell -- ruff format --check .`
7. `devenv shell -- ty check .`

Pass criteria:
1. Snapshot build is deterministic for equivalent payload input.
2. Derived indexes match source entities exactly.

## 8. Step 5: Implement Invariant Engine

Implementation work:
1. Implement `_core/invariants.py` with explicit checks:
- key identity coherence.
- referential integrity across workspace/output/window links.
- focus pointer validity when non-null.
- one active workspace per output consistency.
- index completeness, no duplicates, no dangling references.
2. Return structured violations or raise `InvariantError` depending on policy call-site.
3. Add helper for post-reducer invariant enforcement.

Validation for Step 5:
1. Unit tests with valid snapshots (no violations).
2. Unit tests for each violation class individually.
3. Unit tests for multiple simultaneous violations and deterministic message ordering.
4. `devenv shell -- ruff check .`
5. `devenv shell -- ruff format --check .`
6. `devenv shell -- pytest -q tests/...` (invariant tests)

Pass criteria:
1. Violations are precise and actionable.
2. Invariant engine is pure and side-effect free.

## 9. Step 6: Implement Domain Reducers

Implementation work:
1. Create reducers in `_core/reducers/`:
- `windows.py`
- `workspaces.py`
- `keyboard.py`
- `overview.py`
2. Windows reducer coverage:
- `WindowsChangedEvent` (replace-all)
- `WindowOpenedOrChangedEvent` (upsert)
- `WindowClosedEvent`
- `WindowFocusChangedEvent`
- `WindowUrgencyChangedEvent`
- `WindowFocusTimestampChangedEvent`
- `WindowLayoutsChangedEvent`
3. Workspaces reducer coverage:
- `WorkspacesChangedEvent` (replace-all)
- `WorkspaceActivatedEvent`
- `WorkspaceActiveWindowChangedEvent`
- `WorkspaceUrgencyChangedEvent`
4. Keyboard reducer coverage:
- `KeyboardLayoutsChangedEvent`
- `KeyboardLayoutSwitchedEvent`
5. Overview reducer coverage:
- `OverviewOpenedOrClosedEvent`

Validation for Step 6:
1. Unit tests for each handled event variant, including no-op-on-no-change behavior where expected.
2. Tests proving replace-all events overwrite stale state completely.
3. Tests for deterministic conflict resolution order where multiple related updates occur.
4. `devenv shell -- ruff check .`
5. `devenv shell -- ruff format --check .`
6. `devenv shell -- ty check .`
7. `devenv shell -- pytest -q tests/...` (reducers)

Pass criteria:
1. All mandatory event variants are handled and tested.
2. Reducers remain pure (no IO, no clocks, no locks, no async).

## 10. Step 7: Implement Root Reducer + Unknown Event Policy

Implementation work:
1. Implement `_core/reducers/root.py` explicit dispatch on concrete event model classes from `niri_pypc.types.generated.event`.
2. Handle metadata events explicitly:
- `ConfigLoadedEvent`
- `ScreenshotCapturedEvent`
3. Implement unknown/unimplemented impactful event flow using `UnknownEventPolicy`:
- `STALE`: mark stale + diagnostics.
- `FAIL`: raise desync/failure error path.
- `IGNORE`: only for declared harmless cases, still add diagnostics.
4. Return reducer result envelope with `applied`, changed domains, cause, optional event type/summary.
5. Recompute indexes as needed and run invariants before candidate snapshot is publishable.

Validation for Step 7:
1. Tests for each policy mode on `UnknownEvent` input.
2. Tests verifying metadata events are intentional no-op/diagnostic, not accidental fallthrough.
3. Tests ensuring invariant failure routes correctly based on invariant failure policy.
4. `devenv shell -- ruff check .`
5. `devenv shell -- ruff format --check .`
6. `devenv shell -- pytest -q tests/...` (root reducer + policy)

Pass criteria:
1. Unknown impactful input cannot silently preserve `LIVE` claim.
2. Dispatch is explicit and exhaustive for supported variants.

## 11. Step 8: Implement Bootstrap Query + Normalization Pipeline

Implementation work:
1. Implement `_runtime/bootstrap.py` orchestrator:
- normalize config
- open `NiriConnectionBundle`
- start event buffering immediately
- run mandatory query suite
- normalize to `BootstrapPayload`
- build initial snapshot
- replay buffered events through root reducer
- validate invariants
- publish first `LIVE` snapshot
2. Mandatory query requests via `NiriClient.request(...)`:
- `OutputsRequest`
- `WorkspacesRequest`
- `WindowsRequest`
- `FocusedOutputRequest`
- `FocusedWindowRequest`
- `KeyboardLayoutsRequest`
- `OverviewStateRequest`
3. Optional queries:
- `VersionRequest` (and any clearly documented query-only surfaces)
4. Normalize exact reply shapes from `niri_pypc` response variants:
- outputs: dict[str, Output]
- workspaces/windows: list payloads
- focused output/window: nullable
- keyboard layouts: object with `names` and `current_idx`
- overview: object with `is_open`

Validation for Step 8:
1. Tests for each query-normalization branch and mismatch failure (`BootstrapError`).
2. Race-closure test proving no first `LIVE` publication before replay of buffered events.
3. Test where unknown event appears during bootstrap window and policy is enforced.
4. Test for bundle cleanup on bootstrap failure path.
5. `devenv shell -- ruff check .`
6. `devenv shell -- ruff format --check .`
7. `devenv shell -- ty check .`
8. `devenv shell -- pytest -q tests/...` (bootstrap)

Pass criteria:
1. First externally visible live snapshot is fully replay-closed.
2. Bootstrap failures are explicit and typed.

## 12. Step 9: Implement Store Publication and Subscription Runtime

Implementation work:
1. Implement `_runtime/store.py` and `_runtime/broadcaster.py` with one task owning mutation/publication.
2. Ensure each publication emits immutable snapshot + `ChangeSet`.
3. Implement subscriber registration with bounded per-subscriber queue.
4. Overflow policy handling:
- drop-oldest mode at store layer when configured.
- fail-fast overflow path with `WatchOverflowError`/lifecycle consequences.
5. Implement runtime lifecycle methods:
- `snapshot()`
- `subscribe()`
- `refresh()` hook integration point
- `close()` idempotent resource shutdown

Validation for Step 9:
1. Concurrency tests proving no torn/partial snapshot visibility.
2. Subscription tests for multiple subscribers, slow subscriber, and overflow modes.
3. Close semantics tests: idempotent close, subscriber termination, pending waits/watches termination behavior.
4. `devenv shell -- ruff check .`
5. `devenv shell -- ruff format --check .`
6. `devenv shell -- pytest -q tests/...` (store/broadcaster)

Pass criteria:
1. Publication revision is monotonic and atomic.
2. Overflow behavior matches configured policy exactly.

## 13. Step 10: Implement Wait/Watch APIs

Implementation work:
1. Implement `_runtime/waiters.py` with:
- `wait_until(predicate, timeout=None, health_policy=...)`
2. Implement `watch(selector)` that yields initial selector value then value changes only.
3. Enforce health gating:
- `LIVE_ONLY`: stale snapshots do not satisfy waits.
- `ALLOW_STALE`: stale snapshots may satisfy.
4. Ensure timeout raises `SelectorWaitError` and preserves cause context.
5. Ensure cancellation propagates cleanly and leaves runtime healthy.

Validation for Step 10:
1. Wait immediate-success test against current snapshot.
2. Wait timeout test.
3. Wait cancellation test.
4. Health policy gating tests.
5. Watch equality-change suppression tests.
6. Watch termination-on-close test.
7. `devenv shell -- ruff check .`
8. `devenv shell -- ruff format --check .`
9. `devenv shell -- pytest -q tests/...` (wait/watch)

Pass criteria:
1. Wait/watch are event-driven (no busy loop).
2. Timeout/cancel/close semantics are deterministic.

## 14. Step 11: Implement Resync/Recovery Coordinator

Implementation work:
1. Implement `_runtime/resync.py` coordinating stale/resync transitions.
2. Define stale triggers from spec:
- unknown impactful event under stale policy
- invariant failure under stale policy
- stream terminal/overflow failures
- manual refresh
3. Implement `ResyncPolicy` behavior:
- `MANUAL`: stale until explicit `refresh()`.
- `AUTO`: transition `STALE -> RESYNCING`, run coordinated re-bootstrap.
4. On successful re-bootstrap, publish coherent new `LIVE` snapshot.
5. On failed auto recovery, transition per configured strategy (`STALE`/`FAILED`) with diagnostics.

Validation for Step 11:
1. Tests for manual policy staying stale until `refresh()`.
2. Tests for auto policy successful recovery path.
3. Tests for auto recovery failure diagnostics and resulting state.
4. Tests preserving immutability of pre-recovery snapshots.
5. `devenv shell -- ruff check .`
6. `devenv shell -- ruff format --check .`
7. `devenv shell -- pytest -q tests/...` (resync)

Pass criteria:
1. Recovery behavior is policy-accurate and observable.
2. No mutation of historical snapshots.

## 15. Step 12: Implement Selector Modules and Public Exports

Implementation work:
1. Implement pure selectors in `selectors/` modules:
- outputs
- workspaces
- windows
- focus
- keyboard
- overview
- aggregates
2. Return stable, documented types.
3. Ensure missing entities return `None`/empty collection defaults as specified.
4. Document freshness boundaries for refresh-backed/query-only domains.
5. Wire public exports through `selectors/__init__.py` and top-level `niri_state/__init__.py`.

Validation for Step 12:
1. Unit tests for selector correctness and missing-entity semantics.
2. Tests verifying selectors are pure (no mutation side effects).
3. API import tests for expected public symbols.
4. `devenv shell -- ruff check .`
5. `devenv shell -- ruff format --check .`
6. `devenv shell -- ty check .`
7. `devenv shell -- pytest -q tests/...` (selectors/public API)

Pass criteria:
1. Public selector API is stable and documented.
2. Freshness semantics are explicit and accurate.

## 16. Step 13: Integration and Replay Determinism Harness

Implementation work:
1. Add integration tests for full bootstrap + event stream + replay convergence.
2. Add replay-trace harness (bootstrap payload + ordered events + expected assertions).
3. Ensure replay path calls same root reducer logic as live runtime.
4. Add edge-case traces:
- replace-all then incremental updates
- unknown event stale/fail cases
- multi-output focus/workspace updates

Validation for Step 13:
1. Determinism tests: same trace run twice yields identical outcome.
2. Integration tests for stream closure and recovery transitions.
3. Regression tests for previously fixed bugs (add trace fixtures as permanent guardrails).
4. `devenv shell -- ruff check .`
5. `devenv shell -- ruff format --check .`
6. `devenv shell -- pytest -q tests/integration tests/replay`

Pass criteria:
1. Replay determinism is proven.
2. Integration converges to correct snapshots under race and failure cases.

## 17. Step 14: API Polish, Docs, and Packaging Finish

Implementation work:
1. Finalize `niri_state.__init__` ergonomic exports.
2. Add package docs describing:
- architecture boundary (`_core` vs `_runtime`)
- lifecycle/health semantics
- freshness model
- unknown-event policy implications
- wait/watch usage
3. Ensure versioning metadata exists and aligns with packaging.
4. Confirm `FINAL_CONCEPT`/`FINAL_SPEC` terminology matches implementation names.

Validation for Step 14:
1. Doc examples import and run in tests (doctest or dedicated snippet tests).
2. Full quality gate run (see section 18).

Pass criteria:
1. API and docs are coherent for first-time users.
2. No public naming drift from final spec.

## 18. Mandatory Validation Matrix (Per Step + Final)

Run these every step where applicable:
1. `devenv shell -- ruff check .`
2. `devenv shell -- ruff format --check .`
3. `devenv shell -- ty check .` when typed interfaces/signatures/public models change.
4. `devenv shell -- pytest -q <targeted-tests>` for just-implemented behavior.

Before declaring implementation complete, run:
1. `devenv shell -- uv sync --extra dev` (if not already run in current session before tests)
2. `devenv shell -- ruff check .`
3. `devenv shell -- ruff format --check .`
4. `devenv shell -- ty check .`
5. `devenv shell -- pytest -q`

Final pass criteria:
1. All commands pass with zero failures.
2. No xfail/skip added to hide failing behavior without documented rationale.
3. Unknown event and invariant-failure paths are covered by explicit tests.
4. Bootstrap race closure is covered by explicit integration test.

## 19. Intern Handoff Checklist

The implementation is done only when all items are true:
1. Module tree matches `FINAL_SPEC` structure.
2. `NiriState.connect()` performs full bootstrap with event buffering + replay before first `LIVE` publication.
3. Reducers are deterministic and pure.
4. Invariants run on initial build and post-reduction publish path.
5. Unknown event behavior is policy-driven (`STALE`/`FAIL`/`IGNORE`) and audited.
6. Store publication is atomic and single-owner.
7. `snapshot()`, `subscribe()`, `watch()`, `wait_until()`, `refresh()`, `close()` semantics are tested.
8. Resync policy behavior (`MANUAL` and `AUTO`) is implemented and tested.
9. Replay-trace tests prove deterministic outcomes.
10. Ruff, Ty, and pytest full suite all pass cleanly.

If any checklist item fails, the project is not complete.