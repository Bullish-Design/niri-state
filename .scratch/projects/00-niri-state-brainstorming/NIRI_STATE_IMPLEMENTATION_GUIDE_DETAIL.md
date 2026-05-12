Absolutely. Here’s the intern-facing version: a concrete build order, file-by-file tasks, and starter code for the pieces that matter most.

The governing idea is still the same: `niri-state` is a downstream state engine over `niri-pypc`, not a second protocol client. It owns bootstrap, normalization, reducers, immutable snapshots, selectors, wait/watch APIs, health, stale/desync handling, and resync; `niri-pypc` owns typed requests/replies/events, decoding, sockets, and bundle lifecycle. It also needs to model observed truth only, preserve atomic snapshots, and explicitly distinguish live vs refresh-backed domains.  

From the attached `niri-pypc` export, the intern should code against these current realities:

* `NiriClient` is one-connection-per-request.
* `NiriEventStream` is the long-lived stream, backed by a bounded `asyncio.Queue`.
* upstream backpressure can be `DROP_OLDEST` or `FAIL_FAST`.
* `client.request(...)` unwraps `Reply` into typed response payload variants like `OutputsResponse`, `FocusedWindowResponse`, etc.
* unknown event variants decode into `UnknownEvent`.
* current request surface includes `OutputsRequest`, `WorkspacesRequest`, `WindowsRequest`, `FocusedOutputRequest`, `FocusedWindowRequest`, `KeyboardLayoutsRequest`, `OverviewStateRequest`, plus optional `LayersRequest` and `VersionRequest`.
* current event surface includes the required workspace/window/focus/keyboard/overview/config events, plus `ScreenshotCapturedEvent`, `WindowFocusTimestampChangedEvent`, and `WindowLayoutsChangedEvent`.

That fits the spec’s requirement that `niri-state` be written against the actual attached `niri-pypc`, not older assumptions.  

---

# Recommended build order

Build in this order:

1. `pyproject.toml`, package skeleton
2. `models/common.py`, `errors.py`, `config.py`
3. `models/health.py`, `entities.py`, `snapshot.py`, `change_set.py`
4. `tests/conftest.py` fixture builders
5. `reducers/bootstrap.py`
6. `reducers/invariants.py`
7. `reducers/windows.py`, `workspaces.py`, `focus.py`, `keyboard.py`, `overview.py`, `root.py`
8. `store/broadcaster.py`, `store/waiters.py`
9. `sync/bootstrap.py`
10. `sync/resync.py`
11. `store/live_state.py`
12. `selectors/*`
13. replay/integration/live tests
14. docs and final public exports

That order matches the spec’s package structure, bootstrap contract, reducer purity rules, and test plan.  

---

# 1. `pyproject.toml` and repo skeleton

## What to do

Create the exact package layout from the spec. Do not improvise a flatter structure. Reducers, sync code, selectors, and store logic are intentionally separated. 

## Starter `pyproject.toml`

```toml
[project]
name = "niri-state"
version = "0.1.0"
description = "Live observed compositor state built on top of niri-pypc"
requires-python = ">=3.13"
dependencies = [
  "pydantic>=2.8,<3",
  "niri-pypc>=0.1.0,<0.2.0",
]

[project.optional-dependencies]
dev = [
  "pytest>=8",
  "pytest-asyncio>=0.23",
  "ruff>=0.6",
  "ty>=0.0.1a12",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]

[tool.ty.src]
include = ["src", "tests"]
```

## Validate

* `python -c "import niri_state"` works
* `pytest -q` discovers an empty test tree cleanly
* `ruff check .` passes on skeleton

---

# 2. `src/niri_state/models/common.py`

## What to do

Create the immutable base model and identifier aliases first. Every public state model should build on this. The spec is explicit: public models are frozen Pydantic models, and protocol identifiers should be preserved directly. 

## Starter code

```python
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

OutputName = str
WorkspaceId = int
WindowId = int
Revision = int


class FrozenModel(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )
```

## Validate

Create `tests/test_models_common.py`:

```python
from pydantic import ValidationError

from niri_state.models.common import FrozenModel


class Demo(FrozenModel):
    value: int


def test_frozen_model_is_immutable() -> None:
    model = Demo(value=1)
    try:
        model.value = 2
    except ValidationError:
        pass
    else:
        raise AssertionError("Expected frozen model mutation to fail")
```

---

# 3. `src/niri_state/errors.py`

## What to do

Implement the state-specific error taxonomy now, before the first reducer or sync helper is written. This keeps error mapping consistent later. The spec requires contextual fields like `revision`, `last_good_revision`, `health`, `event_type`, and `selector_name`. 

## Starter code

```python
from __future__ import annotations

from niri_state.models.common import Revision


class NiriStateError(Exception):
    def __init__(
        self,
        message: str,
        *,
        revision: Revision | None = None,
        last_good_revision: Revision | None = None,
        health: str | None = None,
        event_type: str | None = None,
        selector_name: str | None = None,
        retryable: bool = False,
    ) -> None:
        self.revision = revision
        self.last_good_revision = last_good_revision
        self.health = health
        self.event_type = event_type
        self.selector_name = selector_name
        self.retryable = retryable
        super().__init__(message)


class StateConfigError(NiriStateError): ...
class BootstrapError(NiriStateError): ...
class ReductionError(NiriStateError): ...
class InvariantError(NiriStateError): ...
class DesyncError(NiriStateError): ...
class ResyncError(NiriStateError): ...
class StateLifecycleError(NiriStateError): ...
class SelectorWaitError(NiriStateError, TimeoutError): ...
class WatchOverflowError(NiriStateError): ...
class CompatibilityError(NiriStateError): ...
```

## Validate

* test `SelectorWaitError` is `isinstance(err, TimeoutError)`
* test contextual fields are stored
* later, test mapped `niri-pypc` exceptions preserve chaining with `raise ... from exc`

---

# 4. `src/niri_state/config.py`

## What to do

Implement the full config surface from the spec. Also add one helper that normalizes strict correctness mode into upstream `FAIL_FAST` backpressure, because the attached `niri-pypc.NiriConfig` defaults to `DROP_OLDEST`. In strict mode, that is not acceptable for a correctness-preserving state engine.  

## Starter code

```python
from __future__ import annotations

import enum
from dataclasses import replace

from pydantic import BaseModel, ConfigDict, Field

from niri_pypc import BackpressureMode, NiriConfig

from niri_state.errors import StateConfigError


class CorrectnessMode(enum.StrEnum):
    STRICT = "strict"
    BEST_EFFORT = "best_effort"


class ResyncPolicy(enum.StrEnum):
    MANUAL = "manual"
    AUTO = "auto"


class StoreOverflowMode(enum.StrEnum):
    DROP_OLDEST = "drop_oldest"
    FAIL_FAST = "fail_fast"


class UnknownEventPolicy(enum.StrEnum):
    STALE = "stale"
    FAIL = "fail"


class InvariantFailurePolicy(enum.StrEnum):
    STALE = "stale"
    FAIL = "fail"


class WaitHealthPolicy(enum.StrEnum):
    REQUIRE_LIVE = "require_live"
    ALLOW_STALE = "allow_stale"


class NiriStateConfig(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        arbitrary_types_allowed=True,
    )

    pypc: NiriConfig = Field(default_factory=NiriConfig)
    correctness_mode: CorrectnessMode = CorrectnessMode.STRICT

    bootstrap_timeout: float = 10.0
    bootstrap_event_buffer_capacity: int = 1024

    changes_queue_capacity: int = 256
    watcher_queue_capacity: int = 256
    overflow_mode: StoreOverflowMode = StoreOverflowMode.DROP_OLDEST

    resync_policy: ResyncPolicy = ResyncPolicy.MANUAL
    unknown_event_policy: UnknownEventPolicy = UnknownEventPolicy.STALE
    invariant_failure_policy: InvariantFailurePolicy = InvariantFailurePolicy.STALE
    wait_health_policy: WaitHealthPolicy = WaitHealthPolicy.REQUIRE_LIVE

    max_consecutive_resync_failures: int = 3
    emit_initial_watch_value: bool = True
    dedupe_watch_values: bool = True
    bootstrap_query_plan_name: str = "default"

    include_query_only_layers: bool = False
    perform_version_query: bool = False
    strict_version_match: bool = False


def effective_pypc_config(config: NiriStateConfig) -> NiriConfig:
    pypc = config.pypc
    if config.correctness_mode is CorrectnessMode.BEST_EFFORT:
        return pypc

    if pypc.backpressure_mode is BackpressureMode.FAIL_FAST:
        return pypc

    try:
        return replace(pypc, backpressure_mode=BackpressureMode.FAIL_FAST)
    except Exception as exc:
        raise StateConfigError(
            "Strict correctness mode requires FAIL_FAST upstream backpressure",
        ) from exc
```

## Validate

```python
from niri_pypc import BackpressureMode, NiriConfig

from niri_state.config import CorrectnessMode, NiriStateConfig, effective_pypc_config


def test_strict_mode_forces_fail_fast() -> None:
    cfg = NiriStateConfig(
        correctness_mode=CorrectnessMode.STRICT,
        pypc=NiriConfig(backpressure_mode=BackpressureMode.DROP_OLDEST),
    )
    eff = effective_pypc_config(cfg)
    assert eff.backpressure_mode is BackpressureMode.FAIL_FAST
```

---

# 5. `src/niri_state/models/health.py`

## What to do

Implement:

* `CompatibilityStatus`
* `CompatibilityInfo`
* `StoreHealth`
* `SnapshotDiagnostics`

The spec also requires health and revision semantics to be explicit and part of the public contract.  

## Starter code

```python
from __future__ import annotations

import enum

from niri_state.models.common import FrozenModel


class CompatibilityStatus(enum.StrEnum):
    UNCHECKED = "unchecked"
    MATCHED = "matched"
    MISMATCHED = "mismatched"
    UNKNOWN = "unknown"


class CompatibilityInfo(FrozenModel):
    status: CompatibilityStatus = CompatibilityStatus.UNCHECKED
    niri_state_version: str
    niri_pypc_version: str
    upstream_crate: str = "niri-ipc"
    upstream_version: str | None = None
    compositor_version: str | None = None
    message: str | None = None


class StoreHealth(enum.StrEnum):
    BOOTSTRAPPING = "bootstrapping"
    LIVE = "live"
    STALE = "stale"
    RESYNCING = "resyncing"
    CLOSED = "closed"
    FAILED = "failed"


class SnapshotDiagnostics(FrozenModel):
    last_error: str | None = None
    last_desync_reason: str | None = None
    buffered_event_count_during_bootstrap: int = 0
    replayed_event_count_during_bootstrap: int = 0
    last_event_type: str | None = None
    last_refresh_reason: str | None = None
    upstream_backpressure_mode: str | None = None
    correctness_mode: str | None = None
```

## Validate

* enum values match spec exactly
* diagnostics default cleanly
* compatibility info can be built even before runtime version query

---

# 6. `src/niri_state/models/entities.py`, `snapshot.py`, `change_set.py`

## What to do

Implement the public state surface exactly once and treat it as authoritative. The spec is explicit about focused vs active semantics, output freshness, and the fact that keyboard layouts must preserve the full protocol model instead of collapsing to one string.  

## Starter code

```python
from __future__ import annotations

import enum
from typing import Any

from pydantic import Field

from niri_pypc.types import KeyboardLayouts, Output, Overview, Window, Workspace

from niri_state.models.common import FrozenModel, OutputName, Revision, WindowId, WorkspaceId
from niri_state.models.health import CompatibilityInfo, SnapshotDiagnostics, StoreHealth


class OutputState(FrozenModel):
    name: OutputName
    raw: Output
    workspace_ids: tuple[WorkspaceId, ...] = ()
    focused_workspace_id: WorkspaceId | None = None
    is_live_config_current: bool = False


class WorkspaceState(FrozenModel):
    id: WorkspaceId
    raw: Workspace
    output_name: OutputName | None = None
    active_window_id: WindowId | None = None
    is_active: bool = False
    is_focused: bool = False


class WindowState(FrozenModel):
    id: WindowId
    raw: Window
    workspace_id: WorkspaceId | None = None
    is_focused: bool = False


class KeyboardLayoutsState(FrozenModel):
    raw: KeyboardLayouts
    current_idx: int | None = None
    current_name: str | None = None


class OverviewState(FrozenModel):
    raw: Overview | None = None
    is_open: bool | None = None


class SnapshotIndexes(FrozenModel):
    output_order: tuple[OutputName, ...] = ()
    workspace_order: tuple[WorkspaceId, ...] = ()
    window_order: tuple[WindowId, ...] = ()


class NiriSnapshot(FrozenModel):
    revision: Revision
    health: StoreHealth
    compatibility: CompatibilityInfo
    bootstrapped: bool

    outputs_by_name: dict[OutputName, OutputState]
    workspaces_by_id: dict[WorkspaceId, WorkspaceState]
    windows_by_id: dict[WindowId, WindowState]

    indexes: SnapshotIndexes = SnapshotIndexes()

    focused_output_name: OutputName | None = None
    focused_workspace_id: WorkspaceId | None = None
    focused_window_id: WindowId | None = None
    active_workspace_ids_by_output: dict[OutputName, tuple[WorkspaceId, ...]] = Field(
        default_factory=dict
    )

    keyboard_layouts: KeyboardLayoutsState | None = None
    overview: OverviewState | None = None

    last_good_revision: Revision | None = None
    diagnostics: SnapshotDiagnostics = SnapshotDiagnostics()


class ChangeCause(enum.StrEnum):
    BOOTSTRAP = "bootstrap"
    EVENT = "event"
    MANUAL_REFRESH = "manual_refresh"
    MANUAL_RESYNC = "manual_resync"
    AUTO_RESYNC = "auto_resync"
    STALE_TRANSITION = "stale_transition"
    CLOSE = "close"
    FAILURE = "failure"


class ChangeDomain(enum.StrEnum):
    OUTPUTS = "outputs"
    WORKSPACES = "workspaces"
    WINDOWS = "windows"
    FOCUS = "focus"
    KEYBOARD = "keyboard"
    OVERVIEW = "overview"
    HEALTH = "health"
    METADATA = "metadata"


class ChangeSet(FrozenModel):
    old_revision: Revision | None = None
    new_revision: Revision
    cause: ChangeCause
    domains: tuple[ChangeDomain, ...] = ()
    event_type: str | None = None
    health_before: StoreHealth | None = None
    health_after: StoreHealth
    applied: bool = True
    snapshot: NiriSnapshot
    summary: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
```

## Validate

* `NiriSnapshot` rejects a singular `active_workspace_id`
* `ChangeSet.snapshot.revision == ChangeSet.new_revision`
* keyboard layouts preserve raw object and derived index/name separately

---

# 7. `tests/conftest.py`: fixture builders

## What to do

Do this early. The reducer work goes much faster if the intern has clean factories for real generated `niri_pypc.types` models.

## Starter code

```python
from __future__ import annotations

import pytest
from niri_pypc.types import KeyboardLayouts, Output, Overview, Window, Workspace


def make_output(name: str = "HDMI-A-1") -> Output:
    return Output(
        name=name,
        make="Dell",
        model="U2720Q",
        serial=None,
        physical_size=[600, 340],
        modes=[],
        current_mode=None,
        vrr_supported=False,
        vrr_enabled=False,
        logical=None,
        is_custom_mode=False,
    )


def make_workspace(
    workspace_id: int,
    *,
    output: str | None = "HDMI-A-1",
    is_active: bool = False,
    is_focused: bool = False,
    active_window_id: int | None = None,
) -> Workspace:
    return Workspace(
        id=workspace_id,
        idx=workspace_id,
        name=f"ws-{workspace_id}",
        output=output,
        is_active=is_active,
        is_focused=is_focused,
        is_urgent=False,
        active_window_id=active_window_id,
    )


def make_window(
    window_id: int,
    *,
    workspace_id: int | None = None,
    is_focused: bool = False,
) -> Window:
    return Window(
        id=window_id,
        title=f"win-{window_id}",
        app_id="demo.app",
        pid=1234,
        workspace_id=workspace_id,
        is_focused=is_focused,
        is_floating=False,
        is_urgent=False,
        focus_timestamp=None,
        layout={"Tile": {}},  # replace with real WindowLayout helper if needed
    )


def make_keyboard_layouts(current_idx: int = 0) -> KeyboardLayouts:
    return KeyboardLayouts(current_idx=current_idx, names=["us", "de"])


def make_overview(is_open: bool = False) -> Overview:
    return Overview(is_open=is_open)
```

## Validate

* every factory returns a real generated model
* factory defaults are enough to build minimal snapshots
* add a second-output helper for multi-output active/focused tests

---

# 8. `src/niri_state/reducers/bootstrap.py`

## What to do

This file should hold:

* `BootstrapPayload`
* optional internal `BootstrapResponses`
* `normalize_bootstrap_responses(...)`
* `build_initial_snapshot(...)`

Bootstrap must normalize typed response wrappers before reducers see them. That is part of `niri-state`’s contract.  

## Starter code: payload and normalization

```python
from __future__ import annotations

from niri_pypc.types import (
    FocusedOutputResponse,
    FocusedWindowResponse,
    KeyboardLayouts,
    KeyboardLayoutsResponse,
    LayersResponse,
    Output,
    OutputsResponse,
    Overview,
    OverviewStateResponse,
    VersionResponse,
    Window,
    WindowsResponse,
    Workspace,
    WorkspacesResponse,
)

from niri_state.errors import BootstrapError
from niri_state.models.common import FrozenModel, OutputName, WindowId
from niri_state.models.health import CompatibilityInfo


class BootstrapPayload(FrozenModel):
    outputs: tuple[Output, ...] = ()
    workspaces: tuple[Workspace, ...] = ()
    windows: tuple[Window, ...] = ()
    focused_output_name: OutputName | None = None
    focused_window_id: WindowId | None = None
    keyboard_layouts: KeyboardLayouts | None = None
    overview: Overview | None = None
    layers_raw: object | None = None
    compatibility: CompatibilityInfo
    query_plan_name: str


class BootstrapResponses(FrozenModel):
    outputs: OutputsResponse | None = None
    workspaces: WorkspacesResponse | None = None
    windows: WindowsResponse | None = None
    focused_output: FocusedOutputResponse | None = None
    focused_window: FocusedWindowResponse | None = None
    keyboard_layouts: KeyboardLayoutsResponse | None = None
    overview: OverviewStateResponse | None = None
    layers: LayersResponse | None = None
    version: VersionResponse | None = None


def normalize_bootstrap_responses(
    responses: BootstrapResponses,
    *,
    query_plan_name: str,
    compatibility: CompatibilityInfo,
    include_query_only_layers: bool = False,
) -> BootstrapPayload:
    if responses.outputs is None:
        raise BootstrapError("Missing OutputsResponse during bootstrap")
    if responses.workspaces is None:
        raise BootstrapError("Missing WorkspacesResponse during bootstrap")
    if responses.windows is None:
        raise BootstrapError("Missing WindowsResponse during bootstrap")
    if responses.focused_output is None:
        raise BootstrapError("Missing FocusedOutputResponse during bootstrap")
    if responses.focused_window is None:
        raise BootstrapError("Missing FocusedWindowResponse during bootstrap")
    if responses.keyboard_layouts is None:
        raise BootstrapError("Missing KeyboardLayoutsResponse during bootstrap")
    if responses.overview is None:
        raise BootstrapError("Missing OverviewStateResponse during bootstrap")

    focused_output_name = None
    if responses.focused_output.payload is not None:
        focused_output_name = responses.focused_output.payload.name

    focused_window_id = None
    if responses.focused_window.payload is not None:
        focused_window_id = responses.focused_window.payload.id

    return BootstrapPayload(
        outputs=tuple(responses.outputs.payload.values()),
        workspaces=tuple(responses.workspaces.payload),
        windows=tuple(responses.windows.payload),
        focused_output_name=focused_output_name,
        focused_window_id=focused_window_id,
        keyboard_layouts=responses.keyboard_layouts.payload,
        overview=responses.overview.payload,
        layers_raw=responses.layers.payload if include_query_only_layers and responses.layers else None,
        compatibility=compatibility,
        query_plan_name=query_plan_name,
    )
```

## Starter code: initial snapshot build

```python
from niri_state.models.entities import (
    KeyboardLayoutsState,
    NiriSnapshot,
    OutputState,
    OverviewState,
    SnapshotIndexes,
    WindowState,
    WorkspaceState,
)
from niri_state.models.health import SnapshotDiagnostics, StoreHealth
from niri_state.reducers.common import ReducerContext, ReductionResult


def _keyboard_name(raw: KeyboardLayouts | None, idx: int | None) -> str | None:
    if raw is None or idx is None:
        return None
    if idx < 0 or idx >= len(raw.names):
        return None
    return raw.names[idx]


def build_initial_snapshot(
    payload: BootstrapPayload,
    *,
    revision: int,
    context: ReducerContext,
) -> ReductionResult:
    outputs_by_name = {
        output.name: OutputState(
            name=output.name,
            raw=output,
            workspace_ids=(),
            focused_workspace_id=None,
            is_live_config_current=False,
        )
        for output in payload.outputs
    }

    workspaces_by_id = {
        ws.id: WorkspaceState(
            id=ws.id,
            raw=ws,
            output_name=ws.output,
            active_window_id=ws.active_window_id,
            is_active=ws.is_active,
            is_focused=ws.is_focused,
        )
        for ws in payload.workspaces
    }

    windows_by_id = {
        window.id: WindowState(
            id=window.id,
            raw=window,
            workspace_id=window.workspace_id,
            is_focused=window.is_focused,
        )
        for window in payload.windows
    }

    active_by_output: dict[str, list[int]] = {}
    for ws in payload.workspaces:
        if ws.output is not None and ws.is_active:
            active_by_output.setdefault(ws.output, []).append(ws.id)

    outputs_by_name = {
        name: state.model_copy(
            update={
                "workspace_ids": tuple(
                    ws.id for ws in payload.workspaces if ws.output == name
                ),
                "focused_workspace_id": next(
                    (ws.id for ws in payload.workspaces if ws.output == name and ws.is_focused),
                    None,
                ),
            }
        )
        for name, state in outputs_by_name.items()
    }

    focused_workspace_id = next(
        (ws.id for ws in payload.workspaces if ws.is_focused),
        None,
    )
    if focused_workspace_id is None and payload.focused_window_id is not None:
        focused_window = windows_by_id.get(payload.focused_window_id)
        if focused_window is not None:
            focused_workspace_id = focused_window.workspace_id

    snapshot = NiriSnapshot(
        revision=revision,
        health=StoreHealth.LIVE,
        compatibility=payload.compatibility,
        bootstrapped=True,
        outputs_by_name=outputs_by_name,
        workspaces_by_id=workspaces_by_id,
        windows_by_id=windows_by_id,
        indexes=SnapshotIndexes(
            output_order=tuple(output.name for output in payload.outputs),
            workspace_order=tuple(ws.id for ws in payload.workspaces),
            window_order=tuple(win.id for win in payload.windows),
        ),
        focused_output_name=payload.focused_output_name,
        focused_workspace_id=focused_workspace_id,
        focused_window_id=payload.focused_window_id,
        active_workspace_ids_by_output={
            name: tuple(ids) for name, ids in active_by_output.items()
        },
        keyboard_layouts=(
            KeyboardLayoutsState(
                raw=payload.keyboard_layouts,
                current_idx=payload.keyboard_layouts.current_idx,
                current_name=_keyboard_name(
                    payload.keyboard_layouts,
                    payload.keyboard_layouts.current_idx,
                ),
            )
            if payload.keyboard_layouts is not None
            else None
        ),
        overview=(
            OverviewState(raw=payload.overview, is_open=payload.overview.is_open)
            if payload.overview is not None
            else None
        ),
        last_good_revision=revision,
        diagnostics=SnapshotDiagnostics(
            correctness_mode=context.metadata.get("correctness_mode"),
            upstream_backpressure_mode=context.metadata.get("upstream_backpressure_mode"),
        ),
    )

    return ReductionResult(
        snapshot=snapshot,
        domains=(),
        applied=True,
        summary="Built initial snapshot",
    )
```

## Validate

Add `tests/reducers/test_bootstrap.py`:

```python
from niri_state.models.health import CompatibilityInfo
from niri_state.reducers.bootstrap import (
    BootstrapPayload,
    build_initial_snapshot,
)
from niri_state.reducers.common import ReducerContext
from niri_state.config import InvariantFailurePolicy, UnknownEventPolicy
from tests.conftest import make_keyboard_layouts, make_output, make_overview, make_window, make_workspace


def test_build_initial_snapshot_basic() -> None:
    payload = BootstrapPayload(
        outputs=(make_output("HDMI-A-1"),),
        workspaces=(make_workspace(1, is_active=True, is_focused=True),),
        windows=(make_window(10, workspace_id=1, is_focused=True),),
        focused_output_name="HDMI-A-1",
        focused_window_id=10,
        keyboard_layouts=make_keyboard_layouts(0),
        overview=make_overview(False),
        compatibility=CompatibilityInfo(
            niri_state_version="0.1.0",
            niri_pypc_version="0.1.0",
        ),
        query_plan_name="default",
    )
    result = build_initial_snapshot(
        payload,
        revision=1,
        context=ReducerContext(
            cause="bootstrap",
            unknown_event_policy=UnknownEventPolicy.STALE,
            invariant_failure_policy=InvariantFailurePolicy.STALE,
        ),
    )
    assert result.snapshot.revision == 1
    assert result.snapshot.focused_window_id == 10
    assert result.snapshot.focused_workspace_id == 1
    assert result.snapshot.outputs_by_name["HDMI-A-1"].is_live_config_current is False
```

---

# 9. `src/niri_state/reducers/common.py`

## What to do

Add the shared reducer types used by bootstrap and event reducers.

## Starter code

```python
from __future__ import annotations

from typing import Any

from pydantic import Field

from niri_state.config import InvariantFailurePolicy, UnknownEventPolicy
from niri_state.models.common import FrozenModel
from niri_state.models.entities import NiriSnapshot
from niri_state.models.change_set import ChangeCause, ChangeDomain
from niri_state.models.health import CompatibilityInfo


class ReducerContext(FrozenModel):
    cause: ChangeCause
    unknown_event_policy: UnknownEventPolicy
    invariant_failure_policy: InvariantFailurePolicy
    compatibility: CompatibilityInfo
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReductionResult(FrozenModel):
    snapshot: NiriSnapshot
    domains: tuple[ChangeDomain, ...] = ()
    event_type: str | None = None
    applied: bool = True
    summary: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
```

---

# 10. `src/niri_state/reducers/invariants.py`

## What to do

Implement the full invariant checker before writing the root reducer. Invariant failure handling is central to stale/fail policy.  

## Starter code

```python
from __future__ import annotations

from niri_state.models.common import FrozenModel
from niri_state.models.change_set import ChangeDomain
from niri_state.models.entities import NiriSnapshot


class InvariantViolation(FrozenModel):
    code: str
    message: str
    domains: tuple[ChangeDomain, ...] = ()
    entity_ids: tuple[str, ...] = ()


def check_snapshot_invariants(snapshot: NiriSnapshot) -> tuple[InvariantViolation, ...]:
    violations: list[InvariantViolation] = []

    for key, output in snapshot.outputs_by_name.items():
        if output.name != key:
            violations.append(
                InvariantViolation(
                    code="output_key_mismatch",
                    message=f"Output key {key!r} != output.name {output.name!r}",
                    domains=(ChangeDomain.OUTPUTS,),
                    entity_ids=(str(key),),
                )
            )

    for key, workspace in snapshot.workspaces_by_id.items():
        if workspace.id != key:
            violations.append(
                InvariantViolation(
                    code="workspace_key_mismatch",
                    message=f"Workspace key {key!r} != workspace.id {workspace.id!r}",
                    domains=(ChangeDomain.WORKSPACES,),
                    entity_ids=(str(key),),
                )
            )
        if workspace.output_name and workspace.output_name not in snapshot.outputs_by_name:
            violations.append(
                InvariantViolation(
                    code="workspace_unknown_output",
                    message=f"Workspace {workspace.id} references unknown output {workspace.output_name!r}",
                    domains=(ChangeDomain.WORKSPACES, ChangeDomain.OUTPUTS),
                    entity_ids=(str(workspace.id), workspace.output_name),
                )
            )

    for key, window in snapshot.windows_by_id.items():
        if window.id != key:
            violations.append(
                InvariantViolation(
                    code="window_key_mismatch",
                    message=f"Window key {key!r} != window.id {window.id!r}",
                    domains=(ChangeDomain.WINDOWS,),
                    entity_ids=(str(key),),
                )
            )
        if window.workspace_id is not None and window.workspace_id not in snapshot.workspaces_by_id:
            violations.append(
                InvariantViolation(
                    code="window_unknown_workspace",
                    message=f"Window {window.id} references unknown workspace {window.workspace_id}",
                    domains=(ChangeDomain.WINDOWS, ChangeDomain.WORKSPACES),
                    entity_ids=(str(window.id), str(window.workspace_id)),
                )
            )

    if snapshot.focused_window_id is not None:
        if snapshot.focused_window_id not in snapshot.windows_by_id:
            violations.append(
                InvariantViolation(
                    code="focused_window_unknown",
                    message="focused_window_id points to unknown window",
                    domains=(ChangeDomain.FOCUS, ChangeDomain.WINDOWS),
                )
            )

    focused_windows = [w.id for w in snapshot.windows_by_id.values() if w.is_focused]
    if snapshot.focused_window_id is not None:
        if focused_windows != [snapshot.focused_window_id]:
            violations.append(
                InvariantViolation(
                    code="focused_window_flag_mismatch",
                    message="focused window flags do not match focused_window_id",
                    domains=(ChangeDomain.FOCUS, ChangeDomain.WINDOWS),
                )
            )

    return tuple(violations)
```

## Validate

Create:

* `tests/reducers/test_invariants.py`
* one test for each invariant family
* one test that creates multiple violations and confirms all are returned

---

# 11. `src/niri_state/reducers/windows.py`, `workspaces.py`, `focus.py`, `keyboard.py`, `overview.py`

## What to do

Implement one reducer function per event family. Keep them pure. No I/O, no waiting, no logging side effects. The concept and spec both treat reducers as deterministic pure functions.  

## Key snippet: window opened/changed

```python
from __future__ import annotations

from niri_pypc.types import WindowOpenedOrChangedEvent

from niri_state.models.change_set import ChangeDomain
from niri_state.models.entities import WindowState
from niri_state.reducers.common import ReductionResult


def apply_window_opened_or_changed(snapshot, event: WindowOpenedOrChangedEvent) -> ReductionResult:
    window = event.window
    old = snapshot.windows_by_id.get(window.id)

    new_state = WindowState(
        id=window.id,
        raw=window,
        workspace_id=window.workspace_id,
        is_focused=window.is_focused,
    )

    if old == new_state:
        return ReductionResult(
            snapshot=snapshot,
            domains=(ChangeDomain.WINDOWS,),
            event_type=type(event).__name__,
            applied=False,
            summary="Window unchanged",
        )

    windows_by_id = dict(snapshot.windows_by_id)
    windows_by_id[window.id] = new_state

    window_order = snapshot.indexes.window_order
    if window.id not in windows_by_id or window.id not in window_order:
        window_order = (*window_order, window.id)

    next_snapshot = snapshot.model_copy(
        update={
            "windows_by_id": windows_by_id,
            "indexes": snapshot.indexes.model_copy(update={"window_order": window_order}),
        }
    )
    return ReductionResult(
        snapshot=next_snapshot,
        domains=(ChangeDomain.WINDOWS,),
        event_type=type(event).__name__,
        applied=True,
        summary=f"Upserted window {window.id}",
    )
```

## Key snippet: workspace activated

```python
from niri_pypc.types import WorkspaceActivatedEvent

from niri_state.models.change_set import ChangeDomain
from niri_state.reducers.common import ReductionResult


def apply_workspace_activated(snapshot, event: WorkspaceActivatedEvent) -> ReductionResult:
    ws = snapshot.workspaces_by_id.get(event.id)
    if ws is None:
        return ReductionResult(
            snapshot=snapshot,
            domains=(ChangeDomain.WORKSPACES, ChangeDomain.FOCUS),
            event_type=type(event).__name__,
            applied=False,
            summary=f"Workspace {event.id} missing; ignoring activation",
        )

    output_name = ws.output_name
    workspaces_by_id = dict(snapshot.workspaces_by_id)
    active_map = {k: list(v) for k, v in snapshot.active_workspace_ids_by_output.items()}

    if output_name is not None:
        current_ids = active_map.get(output_name, [])
        # Preserve actives on other outputs; replace only this output's active set.
        active_map[output_name] = [event.id]

        for workspace_id, workspace in workspaces_by_id.items():
            if workspace.output_name == output_name:
                workspaces_by_id[workspace_id] = workspace.model_copy(
                    update={"is_active": workspace_id == event.id}
                )

    if event.focused:
        for workspace_id, workspace in workspaces_by_id.items():
            workspaces_by_id[workspace_id] = workspace.model_copy(
                update={"is_focused": workspace_id == event.id}
            )
        focused_workspace_id = event.id
    else:
        focused_workspace_id = snapshot.focused_workspace_id

    next_snapshot = snapshot.model_copy(
        update={
            "workspaces_by_id": workspaces_by_id,
            "active_workspace_ids_by_output": {
                name: tuple(ids) for name, ids in active_map.items()
            },
            "focused_workspace_id": focused_workspace_id,
        }
    )
    return ReductionResult(
        snapshot=next_snapshot,
        domains=(ChangeDomain.WORKSPACES, ChangeDomain.FOCUS),
        event_type=type(event).__name__,
        summary=f"Activated workspace {event.id}",
    )
```

## Key snippet: focus change

```python
from niri_pypc.types import WindowFocusChangedEvent

from niri_state.models.change_set import ChangeDomain
from niri_state.reducers.common import ReductionResult


def apply_window_focus_changed(snapshot, event: WindowFocusChangedEvent) -> ReductionResult:
    windows_by_id = {
        window_id: window.model_copy(update={"is_focused": window_id == event.id})
        for window_id, window in snapshot.windows_by_id.items()
    }

    focused_workspace_id = snapshot.focused_workspace_id
    focused_output_name = snapshot.focused_output_name

    if event.id is not None and event.id in windows_by_id:
        focused_window = windows_by_id[event.id]
        focused_workspace_id = focused_window.workspace_id
        if focused_workspace_id is not None:
            ws = snapshot.workspaces_by_id.get(focused_workspace_id)
            if ws is not None:
                focused_output_name = ws.output_name

    next_snapshot = snapshot.model_copy(
        update={
            "windows_by_id": windows_by_id,
            "focused_window_id": event.id,
            "focused_workspace_id": focused_workspace_id,
            "focused_output_name": focused_output_name,
        }
    )
    return ReductionResult(
        snapshot=next_snapshot,
        domains=(ChangeDomain.FOCUS, ChangeDomain.WINDOWS, ChangeDomain.WORKSPACES),
        event_type=type(event).__name__,
        summary=f"Focused window changed to {event.id}",
    )
```

## Key snippet: keyboard + overview

```python
from niri_pypc.types import KeyboardLayoutSwitchedEvent, KeyboardLayoutsChangedEvent, OverviewOpenedOrClosedEvent

from niri_state.models.change_set import ChangeDomain
from niri_state.models.entities import KeyboardLayoutsState, OverviewState
from niri_state.reducers.common import ReductionResult


def apply_keyboard_layout_switched(snapshot, event: KeyboardLayoutSwitchedEvent) -> ReductionResult:
    state = snapshot.keyboard_layouts
    if state is None:
        return ReductionResult(
            snapshot=snapshot,
            domains=(ChangeDomain.KEYBOARD,),
            event_type=type(event).__name__,
            applied=False,
        )
    name = None
    if 0 <= event.idx < len(state.raw.names):
        name = state.raw.names[event.idx]
    next_snapshot = snapshot.model_copy(
        update={
            "keyboard_layouts": state.model_copy(
                update={"current_idx": event.idx, "current_name": name}
            )
        }
    )
    return ReductionResult(
        snapshot=next_snapshot,
        domains=(ChangeDomain.KEYBOARD,),
        event_type=type(event).__name__,
    )


def apply_keyboard_layouts_changed(snapshot, event: KeyboardLayoutsChangedEvent) -> ReductionResult:
    raw = event.keyboard_layouts
    idx = raw.current_idx
    name = raw.names[idx] if 0 <= idx < len(raw.names) else None
    next_snapshot = snapshot.model_copy(
        update={
            "keyboard_layouts": KeyboardLayoutsState(raw=raw, current_idx=idx, current_name=name)
        }
    )
    return ReductionResult(
        snapshot=next_snapshot,
        domains=(ChangeDomain.KEYBOARD,),
        event_type=type(event).__name__,
    )


def apply_overview_opened_or_closed(snapshot, event: OverviewOpenedOrClosedEvent) -> ReductionResult:
    current = snapshot.overview
    next_state = (
        OverviewState(raw=current.raw if current else None, is_open=event.is_open)
        if current is not None
        else OverviewState(raw=None, is_open=event.is_open)
    )
    next_snapshot = snapshot.model_copy(update={"overview": next_state})
    return ReductionResult(
        snapshot=next_snapshot,
        domains=(ChangeDomain.OVERVIEW,),
        event_type=type(event).__name__,
    )
```

## Important note

For the extra current event variants from the attached export:

* `ScreenshotCapturedEvent`
* `WindowFocusTimestampChangedEvent`
* `WindowLayoutsChangedEvent`

Either handle them meaningfully, or explicitly no-op them in `root.py`. Do not silently omit them.

## Validate

Create:

* `tests/reducers/test_windows.py`
* `test_workspaces.py`
* `test_focus.py`
* `test_keyboard.py`
* `test_overview.py`

Each should cover:

* add/update/remove or replace-all flows
* no-op cases
* focused pointer updates
* active-vs-focused correctness across multiple outputs

---

# 12. `src/niri_state/reducers/root.py`

## What to do

Dispatch by concrete event class, not by strings. Unknown sentinels must follow `UnknownEventPolicy`: stale transition or hard failure. The concept is very explicit that unknown/unsupported inputs must not be silently ignored. 

## Starter code

```python
from __future__ import annotations

from niri_pypc.types import (
    ConfigLoadedEvent,
    KeyboardLayoutSwitchedEvent,
    KeyboardLayoutsChangedEvent,
    OverviewOpenedOrClosedEvent,
    ScreenshotCapturedEvent,
    UnknownEvent,
    WindowClosedEvent,
    WindowFocusChangedEvent,
    WindowFocusTimestampChangedEvent,
    WindowLayoutsChangedEvent,
    WindowOpenedOrChangedEvent,
    WindowUrgencyChangedEvent,
    WindowsChangedEvent,
    WorkspaceActivatedEvent,
    WorkspaceActiveWindowChangedEvent,
    WorkspaceUrgencyChangedEvent,
    WorkspacesChangedEvent,
)

from niri_state.config import UnknownEventPolicy
from niri_state.errors import DesyncError
from niri_state.models.change_set import ChangeCause, ChangeDomain
from niri_state.models.health import StoreHealth
from niri_state.reducers.common import ReducerContext, ReductionResult


def apply_event(snapshot, event, *, next_revision: int, context: ReducerContext) -> ReductionResult:
    if isinstance(event, UnknownEvent):
        if context.unknown_event_policy is UnknownEventPolicy.FAIL:
            raise DesyncError(
                f"Unknown event variant {event.variant_name!r}",
                revision=snapshot.revision,
                last_good_revision=snapshot.last_good_revision,
                health=snapshot.health.value,
                event_type=type(event).__name__,
            )
        stale = snapshot.model_copy(
            update={
                "revision": next_revision,
                "health": StoreHealth.STALE,
                "diagnostics": snapshot.diagnostics.model_copy(
                    update={
                        "last_event_type": type(event).__name__,
                        "last_desync_reason": f"Unknown event {event.variant_name!r}",
                    }
                ),
            }
        )
        return ReductionResult(
            snapshot=stale,
            domains=(ChangeDomain.HEALTH, ChangeDomain.METADATA),
            event_type=type(event).__name__,
            applied=True,
            summary="Transitioned store to stale due to unknown event",
        )

    if isinstance(event, WindowOpenedOrChangedEvent):
        return apply_window_opened_or_changed(snapshot, event)
    if isinstance(event, WindowClosedEvent):
        return apply_window_closed(snapshot, event)
    if isinstance(event, WindowsChangedEvent):
        return apply_windows_changed(snapshot, event)

    if isinstance(event, WindowFocusChangedEvent):
        return apply_window_focus_changed(snapshot, event)

    if isinstance(event, WorkspaceActivatedEvent):
        return apply_workspace_activated(snapshot, event)

    if isinstance(event, KeyboardLayoutSwitchedEvent):
        return apply_keyboard_layout_switched(snapshot, event)
    if isinstance(event, KeyboardLayoutsChangedEvent):
        return apply_keyboard_layouts_changed(snapshot, event)
    if isinstance(event, OverviewOpenedOrClosedEvent):
        return apply_overview_opened_or_closed(snapshot, event)

    if isinstance(event, (ScreenshotCapturedEvent, WindowFocusTimestampChangedEvent, WindowLayoutsChangedEvent)):
        return ReductionResult(
            snapshot=snapshot,
            domains=(),
            event_type=type(event).__name__,
            applied=False,
            summary=f"Explicit no-op for {type(event).__name__}",
        )

    raise DesyncError(
        f"Unhandled known event type {type(event).__name__}",
        revision=snapshot.revision,
        last_good_revision=snapshot.last_good_revision,
        health=snapshot.health.value,
        event_type=type(event).__name__,
    )
```

## Validate

Create `tests/reducers/test_unknown_events.py`:

* unknown event + stale policy => new stale snapshot
* unknown event + fail policy => `DesyncError`
* explicit no-op event => `applied=False`, no new revision on publish layer
* unsupported known event => `DesyncError`

---

# 13. `src/niri_state/store/broadcaster.py`

## What to do

Implement per-subscriber queues for changes and selector watch values. This is where subscriber overflow policy lives. The spec requires independent subscriber queues and queue overflow modes. 

## Starter code

```python
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Generic, TypeVar

from niri_state.config import StoreOverflowMode
from niri_state.errors import WatchOverflowError

T = TypeVar("T")


class _Subscription(Generic[T]):
    def __init__(self, capacity: int, overflow_mode: StoreOverflowMode) -> None:
        self.queue: asyncio.Queue[T | BaseException | None] = asyncio.Queue(maxsize=capacity)
        self.overflow_mode = overflow_mode
        self.closed = False

    def push(self, item: T) -> None:
        if self.closed:
            return
        try:
            self.queue.put_nowait(item)
        except asyncio.QueueFull:
            if self.overflow_mode is StoreOverflowMode.DROP_OLDEST:
                _ = self.queue.get_nowait()
                self.queue.put_nowait(item)
            else:
                self.queue.put_nowait(
                    WatchOverflowError("Subscriber queue overflowed", retryable=False)
                )

    async def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        await self.queue.put(None)


class Broadcaster(Generic[T]):
    def __init__(self, *, capacity: int, overflow_mode: StoreOverflowMode) -> None:
        self._capacity = capacity
        self._overflow_mode = overflow_mode
        self._subs: set[_Subscription[T]] = set()

    def publish(self, item: T) -> None:
        for sub in tuple(self._subs):
            sub.push(item)

    async def close(self) -> None:
        for sub in tuple(self._subs):
            await sub.close()

    async def subscribe(self) -> AsyncIterator[T]:
        sub = _Subscription[T](self._capacity, self._overflow_mode)
        self._subs.add(sub)
        try:
            while True:
                item = await sub.queue.get()
                if item is None:
                    return
                if isinstance(item, BaseException):
                    raise item
                yield item
        finally:
            self._subs.discard(sub)
```

## Validate

* one slow subscriber doesn’t block others
* `DROP_OLDEST` evicts oldest
* `FAIL_FAST` terminates just that subscription

---

# 14. `src/niri_state/store/waiters.py`

## What to do

Implement `wait_until` and `wait_for_selector` as event-driven helpers over the change stream. The spec requires “check current first, then re-evaluate after each publish.” 

## Starter code

```python
from __future__ import annotations

import asyncio
from collections.abc import Callable

from niri_state.config import WaitHealthPolicy
from niri_state.errors import SelectorWaitError
from niri_state.models.entities import NiriSnapshot
from niri_state.models.health import StoreHealth


async def wait_until(
    current: Callable[[], NiriSnapshot],
    changes,
    predicate: Callable[[NiriSnapshot], bool],
    *,
    timeout: float | None = None,
    description: str | None = None,
    health_policy: WaitHealthPolicy = WaitHealthPolicy.REQUIRE_LIVE,
) -> NiriSnapshot:
    snapshot = current()
    if predicate(snapshot):
        return snapshot

    async def _run() -> NiriSnapshot:
        async for change in changes():
            snapshot = change.snapshot
            if health_policy is WaitHealthPolicy.REQUIRE_LIVE and snapshot.health is not StoreHealth.LIVE:
                raise SelectorWaitError(
                    description or "Store left LIVE health while waiting",
                    revision=snapshot.revision,
                    last_good_revision=snapshot.last_good_revision,
                    health=snapshot.health.value,
                )
            if predicate(snapshot):
                return snapshot
        raise SelectorWaitError(description or "Change stream ended while waiting")

    try:
        return await asyncio.wait_for(_run(), timeout=timeout)
    except TimeoutError as exc:
        raise SelectorWaitError(description or "Timed out waiting for predicate") from exc


async def wait_for_selector(
    current: Callable[[], NiriSnapshot],
    changes,
    selector,
    *,
    predicate=None,
    timeout: float | None = None,
    description: str | None = None,
    health_policy: WaitHealthPolicy = WaitHealthPolicy.REQUIRE_LIVE,
):
    snapshot = current()
    initial = selector(snapshot)

    if predicate is not None and predicate(initial):
        return initial

    if predicate is None:
        predicate = lambda value: value != initial

    result_snapshot = await wait_until(
        current=current,
        changes=changes,
        predicate=lambda s: predicate(selector(s)),
        timeout=timeout,
        description=description,
        health_policy=health_policy,
    )
    return selector(result_snapshot)
```

## Validate

Create:

* `tests/store/test_wait_until.py`
* `tests/store/test_watch_selector.py`

Cover:

* immediate success
* success on next publish
* timeout
* stale behavior under both health policies
* dedupe-on-equality

---

# 15. `src/niri_state/sync/bootstrap.py`

## What to do

This is the hardest file.

The important implementation rule is: do not let two tasks independently consume `bundle.events.next()` at the same time. During bootstrap, use one event reader path that buffers events while requests run, then replay that buffer before publishing first live state. The spec requires the race window to be closed before the first `LIVE` snapshot is published. 

## Suggested implementation pattern

Use a single bootstrap event pump task during initial sync. It appends typed events into a local FIFO until query collection is done.

## Starter code

```python
from __future__ import annotations

import asyncio
from collections import deque

from niri_pypc import NiriConnectionBundle
from niri_pypc.types import (
    FocusedOutputRequest,
    FocusedWindowRequest,
    KeyboardLayoutsRequest,
    OutputsRequest,
    OverviewStateRequest,
    VersionRequest,
    WindowsRequest,
    WorkspacesRequest,
)

from niri_state.config import NiriStateConfig, effective_pypc_config
from niri_state.errors import BootstrapError
from niri_state.models.health import CompatibilityInfo
from niri_state.reducers.bootstrap import BootstrapResponses, build_initial_snapshot, normalize_bootstrap_responses


class BootstrapArtifacts(FrozenModel):
    payload: BootstrapPayload
    base_result: ReductionResult
    replay_results: tuple[ReductionResult, ...] = ()
    first_live_snapshot: NiriSnapshot
    replayed_event_count: int = 0


async def run_bootstrap(bundle: NiriConnectionBundle, config: NiriStateConfig) -> BootstrapArtifacts:
    buffer: deque[object] = deque()
    buffering_done = asyncio.Event()
    buffered_error: Exception | None = None

    async def _pump_events() -> None:
        nonlocal buffered_error
        try:
            while not buffering_done.is_set():
                event = await bundle.events.next()
                if len(buffer) >= config.bootstrap_event_buffer_capacity:
                    raise BootstrapError("Bootstrap event buffer overflow")
                buffer.append(event)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            buffered_error = exc

    pump_task = asyncio.create_task(_pump_events())

    try:
        compatibility = CompatibilityInfo(
            niri_state_version="0.1.0",
            niri_pypc_version="0.1.0",
        )

        responses = BootstrapResponses(
            outputs=await bundle.client.request(OutputsRequest()),
            workspaces=await bundle.client.request(WorkspacesRequest()),
            windows=await bundle.client.request(WindowsRequest()),
            focused_output=await bundle.client.request(FocusedOutputRequest()),
            focused_window=await bundle.client.request(FocusedWindowRequest()),
            keyboard_layouts=await bundle.client.request(KeyboardLayoutsRequest()),
            overview=await bundle.client.request(OverviewStateRequest()),
            version=(await bundle.client.request(VersionRequest())) if config.perform_version_query else None,
        )

        if buffered_error is not None:
            raise buffered_error

        payload = normalize_bootstrap_responses(
            responses,
            query_plan_name=config.bootstrap_query_plan_name,
            compatibility=compatibility,
            include_query_only_layers=config.include_query_only_layers,
        )

        base_result = build_initial_snapshot(
            payload,
            revision=1,
            context=build_bootstrap_context(config, compatibility),
        )

        current = base_result.snapshot
        replay_results: list[ReductionResult] = []
        next_revision = 2

        for event in tuple(buffer):
            result = apply_event(
                current,
                event,
                next_revision=next_revision,
                context=build_event_context(config, compatibility),
            )
            if result.applied:
                current = result.snapshot.model_copy(update={"revision": next_revision})
                replay_results.append(result.model_copy(update={"snapshot": current}))
                next_revision += 1

        current = current.model_copy(
            update={
                "diagnostics": current.diagnostics.model_copy(
                    update={
                        "buffered_event_count_during_bootstrap": len(buffer),
                        "replayed_event_count_during_bootstrap": len(replay_results),
                    }
                )
            }
        )

        return BootstrapArtifacts(
            payload=payload,
            base_result=base_result,
            replay_results=tuple(replay_results),
            first_live_snapshot=current,
            replayed_event_count=len(replay_results),
        )
    finally:
        buffering_done.set()
        pump_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await pump_task
```

## Important correction for the intern

The snippet above is the right shape, but the final implementation should use a cleaner handoff than “cancel the pump after bootstrap,” because the live consumer must start without introducing a second race. The cleanest real implementation is:

* one consumer phase during bootstrap that writes to local FIFO
* after replay succeeds, transition that same logical consumer path into “publish mode”

Do not end up with two concurrent event readers on the same `NiriEventStream`.

## Validate

Create:

* `tests/sync/test_response_normalization.py`
* `test_bootstrap.py`
* `test_bootstrap_buffering.py`
* `test_backpressure_contract.py`
* `test_compatibility.py`

Focus on:

* response wrapper normalization
* buffer overflow fails bootstrap
* upstream fail-fast overflow surfaces as bootstrap failure
* command errors fail bootstrap
* strict version mismatch rejects startup

---

# 16. `src/niri_state/sync/resync.py`

## What to do

Resync owns stale-to-live recovery. It should serialize attempts and publish `RESYNCING` before trying a fresh bootstrap. The concept and spec both make resync a first-class responsibility of `niri-state`.  

## Starter code

```python
from __future__ import annotations

import asyncio

from niri_pypc import NiriConnectionBundle

from niri_state.config import NiriStateConfig
from niri_state.errors import ResyncError


class ResyncCoordinator:
    def __init__(self, config: NiriStateConfig) -> None:
        self._config = config
        self._lock = asyncio.Lock()
        self._consecutive_failures = 0

    @property
    def in_progress(self) -> bool:
        return self._lock.locked()

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    async def run(self, state: "NiriState"):
        async with self._lock:
            try:
                await state._publish_resyncing()
                bundle = await NiriConnectionBundle.open(state._effective_pypc_config)
                artifacts = await run_bootstrap(bundle, state._config)
                await state._replace_bundle_and_publish_live(bundle, artifacts.first_live_snapshot)
                self._consecutive_failures = 0
                return state._latest_snapshot
            except Exception as exc:
                self._consecutive_failures += 1
                await state._publish_resync_failure(exc)
                raise ResyncError("Resync failed", retryable=True) from exc
```

## Validate

Create `tests/sync/test_resync.py`:

* successful resync publishes `RESYNCING` then `LIVE`
* failed resync yields `STALE` or `FAILED`
* only one resync may run at once

---

# 17. `src/niri_state/store/live_state.py`

## What to do

This file should mostly orchestrate already-tested parts. `connect()` should not return until first live snapshot exists. That is a hard contract. 

## Starter code

```python
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any, TypeVar

from niri_pypc import NiriConnectionBundle

from niri_state.config import NiriStateConfig, WaitHealthPolicy, effective_pypc_config
from niri_state.models.change_set import ChangeCause, ChangeSet
from niri_state.models.entities import NiriSnapshot
from niri_state.models.health import StoreHealth
from niri_state.store.broadcaster import Broadcaster
from niri_state.store.waiters import wait_for_selector, wait_until
from niri_state.sync.bootstrap import run_bootstrap
from niri_state.sync.resync import ResyncCoordinator

T = TypeVar("T")


class NiriState:
    def __init__(self, config: NiriStateConfig) -> None:
        self._config = config
        self._effective_pypc_config = effective_pypc_config(config)
        self._latest_snapshot: NiriSnapshot | None = None
        self._changes = Broadcaster[ChangeSet](
            capacity=config.changes_queue_capacity,
            overflow_mode=config.overflow_mode,
        )
        self._bundle: NiriConnectionBundle | None = None
        self._closed = False
        self._event_task: asyncio.Task[None] | None = None
        self._resync = ResyncCoordinator(config)

    @classmethod
    async def connect(cls, config: NiriStateConfig | None = None) -> "NiriState":
        config = config or NiriStateConfig()
        self = cls(config)

        bundle = await NiriConnectionBundle.open(self._effective_pypc_config)
        artifacts = await run_bootstrap(bundle, config)

        self._bundle = bundle
        self._latest_snapshot = artifacts.first_live_snapshot
        self._event_task = asyncio.create_task(self._run_events())
        return self

    def current(self) -> NiriSnapshot:
        assert self._latest_snapshot is not None
        return self._latest_snapshot

    async def snapshot(
        self,
        *,
        wait_for_live: bool = False,
        timeout: float | None = None,
    ) -> NiriSnapshot:
        if not wait_for_live:
            return self.current()
        return await wait_until(
            current=self.current,
            changes=self.changes,
            predicate=lambda s: s.health is StoreHealth.LIVE,
            timeout=timeout,
            description="Waiting for LIVE snapshot",
            health_policy=WaitHealthPolicy.ALLOW_STALE,
        )

    def health(self) -> StoreHealth:
        return self.current().health

    async def changes(self) -> AsyncIterator[ChangeSet]:
        async for change in self._changes.subscribe():
            yield change

    async def wait_until(self, predicate, *, timeout=None, description=None, health_policy=None):
        return await wait_until(
            current=self.current,
            changes=self.changes,
            predicate=predicate,
            timeout=timeout,
            description=description,
            health_policy=health_policy or self._config.wait_health_policy,
        )

    async def wait_for_selector(
        self,
        selector,
        *,
        predicate=None,
        timeout=None,
        description=None,
        health_policy=None,
    ):
        return await wait_for_selector(
            current=self.current,
            changes=self.changes,
            selector=selector,
            predicate=predicate,
            timeout=timeout,
            description=description,
            health_policy=health_policy or self._config.wait_health_policy,
        )

    async def refresh(self) -> NiriSnapshot:
        return await self._resync.run(self)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._event_task is not None:
            self._event_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._event_task
        if self._bundle is not None:
            await self._bundle.close()
        await self._changes.close()

    async def _run_events(self) -> None:
        assert self._bundle is not None
        while not self._closed:
            event = await self._bundle.events.next()
            # apply reducer, publish change, handle stale/resync paths
```

## Validate

Create:

* `tests/store/test_live_state.py`
* `tests/store/test_changes.py`
* `tests/store/test_close_and_failure.py`

Check:

* `connect()` returns readable live state
* `current()` always returns latest snapshot
* `changes()` yields monotonic revisions
* `close()` is idempotent
* new refresh or subscriptions are rejected after close begins

---

# 18. `src/niri_state/selectors/*`

## What to do

Implement only the selectors the spec requires. Keep them pure, deterministic, and snapshot-only. 

## Starter code

```python
# selectors/windows.py
from __future__ import annotations

from niri_state.models.entities import NiriSnapshot, WindowState, WorkspaceState


def window_by_id(snapshot: NiriSnapshot, window_id: int) -> WindowState | None:
    return snapshot.windows_by_id.get(window_id)


def windows(snapshot: NiriSnapshot) -> tuple[WindowState, ...]:
    return tuple(snapshot.windows_by_id[wid] for wid in snapshot.indexes.window_order)


def focused_window(snapshot: NiriSnapshot) -> WindowState | None:
    if snapshot.focused_window_id is None:
        return None
    return snapshot.windows_by_id.get(snapshot.focused_window_id)


def workspace_for_window(snapshot: NiriSnapshot, window_id: int) -> WorkspaceState | None:
    window = snapshot.windows_by_id.get(window_id)
    if window is None or window.workspace_id is None:
        return None
    return snapshot.workspaces_by_id.get(window.workspace_id)
```

```python
# selectors/aggregates.py
from __future__ import annotations

from niri_state.models.entities import NiriSnapshot
from niri_state.models.health import StoreHealth


def window_count(snapshot: NiriSnapshot) -> int:
    return len(snapshot.windows_by_id)


def workspace_count(snapshot: NiriSnapshot) -> int:
    return len(snapshot.workspaces_by_id)


def output_count(snapshot: NiriSnapshot) -> int:
    return len(snapshot.outputs_by_name)


def has_window(snapshot: NiriSnapshot, window_id: int) -> bool:
    return window_id in snapshot.windows_by_id


def is_live(snapshot: NiriSnapshot) -> bool:
    return snapshot.health is StoreHealth.LIVE


def is_stale(snapshot: NiriSnapshot) -> bool:
    return snapshot.health is StoreHealth.STALE
```

## Validate

Create:

* `tests/selectors/test_outputs.py`
* `test_workspaces.py`
* `test_windows.py`
* `test_focus.py`
* `test_keyboard.py`
* `test_aggregates.py`

Include:

* direct lookup
* missing cases
* relationship traversal
* focused vs active semantics
* stable ordering via snapshot indexes

---

# 19. Replay support

## What to do

Use the same bootstrap builder and root reducer as live code. Replay should not have separate semantics. The spec explicitly makes replay traces part of regression validation.  

## Starter code

```python
from __future__ import annotations

import json
from pathlib import Path

from niri_pypc.types import Event

from niri_state.models.change_set import ChangeCause, ChangeSet
from niri_state.models.health import CompatibilityInfo
from niri_state.reducers.bootstrap import BootstrapPayload, build_initial_snapshot
from niri_state.reducers.root import apply_event


def replay_trace(path: Path):
    changes: list[ChangeSet] = []
    snapshot = None

    with path.open() as fh:
        for raw_line in fh:
            record = json.loads(raw_line)
            kind = record["kind"]

            if kind == "bootstrap_payload":
                payload = BootstrapPayload.model_validate(record["data"])
                snapshot = build_initial_snapshot(
                    payload,
                    revision=1,
                    context=build_bootstrap_context(...),
                ).snapshot
                continue

            if kind == "event":
                assert snapshot is not None
                event = Event.model_validate(record["data"]).variant
                result = apply_event(
                    snapshot,
                    event,
                    next_revision=snapshot.revision + 1,
                    context=build_event_context(...),
                )
                if result.applied:
                    snapshot = result.snapshot.model_copy(
                        update={"revision": snapshot.revision + 1}
                    )

    assert snapshot is not None
    return snapshot, changes
```

## Validate

Create:

* `tests/replay/test_replay_traces.py`
* `tests/replay/traces/*.jsonl`

Minimum cases:

* focused workspace movement
* unknown event stale transition
* long mixed windows/workspaces stream

---

# 20. Integration and live tests

## What to do

Most correctness should be covered without a real compositor. Use:

* fake bundle/client/event-stream objects for sync/store tests
* a controlled mock Niri-like server for integration tests
* real `NIRI_SOCKET` live tests only as smoke coverage

That matches the spec’s test pyramid.  

## High-value integration cases

1. bootstrap + replay + live event tracking
2. transport loss → stale or auto-resync
3. unknown event → stale
4. fail-fast upstream overflow → stale/resync
5. monotonic, gap-free published revisions
6. manual `refresh()` returns a coherent new live snapshot

---

# Three extra implementation notes for the intern

## A. Treat replace-all events as authoritative

`WindowsChangedEvent` and `WorkspacesChangedEvent` should replace their domains from scratch. That will keep reducers deterministic and easier to reason about.

## B. Keep publication centralized

Have one private method on `NiriState` that:

* increments revision
* swaps current snapshot
* builds `ChangeSet`
* fans out to change subscribers
* wakes waiters/watchers

That prevents revision/change ordering bugs.

## C. Do not conflate active and focused

This is one of the easiest ways to get the state model subtly wrong. Focus is global; active workspaces are per-output.  

---

# Minimal “definition of done” checklist for the intern

The implementation is not done until all of these are true:

* first bootstrap returns a coherent live snapshot
* response wrappers are normalized explicitly
* strict mode enforces upstream fail-fast backpressure
* reducers are deterministic and invariant-checked
* outputs are treated as refresh-backed, not fully live
* unknown/unsupported changes cause stale/fail behavior, not silent drift
* selectors and waits are pure and event-driven
* resync is explicit and test-covered
* replay traces pass
* dependency direction stays `niri-state -> niri-pypc` only 

