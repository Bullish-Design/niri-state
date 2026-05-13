Here is the rewrite blueprint I would actually execute.

The short version is: **replace `niri-state` with a new, smaller library whose only job is to maintain a deterministic, reconciled, immutable state view on top of canonical `niri-pypc` models and events**. The intern memo is useful as a reminder to fix config/dataclass mismatches, but I would reject its core framing because it treats the goal as “match `niri-pypc`’s Pydantic patterns while keeping the current shape,” instead of asking what the cleanest architecture actually is. 

## Canonical decision

**Do a greenfield rewrite inside the repo.**

Do not start by refactoring the old modules in place.
Do not preserve the wrapper-model architecture.
Do not preserve the current public surface if it makes the design worse.

The clean target is:

* `niri-pypc` owns protocol models, request/response typing, wire decoding, and event stream lifecycle.
* `niri-state` owns bootstrap orchestration, deterministic event reduction, reconciliation, immutable snapshots, subscriptions, health transitions, and selectors.

That is the boundary.

## What `niri-state` should be

`niri-state` should be a **state engine**, not a parallel domain model.

Its core responsibilities should be:

* fetch the initial compositor state through typed `niri-pypc` requests,
* ingest typed `niri-pypc` events,
* reduce them into canonical in-memory state,
* reconcile any derived relationships,
* publish immutable snapshots,
* expose selectors and waiting/subscription helpers,
* track health, desync, and resync policy.

It should **not**:

* wrap upstream protocol objects in redundant `*.protocol` containers,
* duplicate upstream IDs in both dict keys and model fields,
* carry hand-maintained secondary indexes as first-class mutable state unless profiling proves they are necessary,
* imitate `ProtocolModel` patterns internally just because upstream uses them at the wire boundary.

## What the final architecture should look like

I would collapse the library into a simpler shape like this:

```text
niri_state/
  __init__.py

  protocol.py          # thin local façade over niri_pypc types
  config.py            # frozen public config model
  errors.py            # structured exception taxonomy
  health.py            # state lifecycle enum + transitions
  changes.py           # immutable change publication model
  diagnostics.py       # state-local diagnostics / compatibility / invariants

  snapshot.py          # immutable published snapshot
  engine_state.py      # mutable internal state, not pydantic
  reconcile.py         # central normalization/reconciliation rules

  bootstrap.py         # typed bootstrap queries + event-stream startup
  reducers.py          # event dispatch + concrete reducers
  store.py             # runtime mutation loop / publish loop / close lifecycle
  resync.py            # resync coordinator

  selectors/
    __init__.py
    focus.py
    outputs.py
    workspaces.py
    windows.py
    keyboard.py
    overview.py
    aggregates.py

tests/
  factories/
    protocol.py
    state.py
  unit/
  integration/
  replay/
```

The existing `_core` / `_runtime` split is not buying enough clarity to justify the complexity. A flatter structure is cleaner.

## The central architectural rule

**Store upstream models directly.**

The canonical state should use:

* `Output`
* `Workspace`
* `Window`
* `KeyboardLayouts`
* `Overview`

directly from `niri-pypc`.

Not:

* `OutputState(output_name, protocol: Output)`
* `WorkspaceState(workspace_id, protocol: Workspace)`
* `WindowState(window_id, protocol: Window)`
* `KeyboardState(protocol, current_name)`
* `OverviewState(is_open)`

Those wrappers are the main architectural smell.

They duplicate identity, force redundant invariants, and make reducers noisier than they need to be.

## Canonical state model

There should be exactly two internal representations.

### 1. Mutable engine state

This is internal-only and should be a plain Python class or a slotted stdlib dataclass.

Not Pydantic.

Reason:

* it is hot-path mutable state,
* its values are already typed and validated by `niri-pypc`,
* and Pydantic adds very little here besides ceremony.

Suggested shape:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from niri_state.health import HealthState
from niri_state.diagnostics import Diagnostics, Compatibility
from niri_state.protocol import Output, Workspace, Window, KeyboardLayouts, Overview


@dataclass(slots=True)
class EngineState:
    outputs: dict[str, Output] = field(default_factory=dict)
    workspaces: dict[int, Workspace] = field(default_factory=dict)
    windows: dict[int, Window] = field(default_factory=dict)

    focused_workspace_id: int | None = None
    focused_window_id: int | None = None

    keyboard_layouts: KeyboardLayouts | None = None
    overview: Overview | None = None

    health: HealthState = HealthState.BOOTSTRAPPING
    diagnostics: Diagnostics = field(default_factory=Diagnostics)
    compatibility: Compatibility = field(default_factory=Compatibility)
```

### 2. Immutable published snapshot

This should be a frozen Pydantic model.

Reason:

* it is the public state surface,
* it benefits from validation/serialization/schema support,
* and this is where Pydantic is the right tool.

Pydantic’s docs explicitly note that Pydantic dataclasses are **not** a replacement for Pydantic models, and that there are cases where models are the better choice. They also note that `BaseModel` workflows are stronger around validation, dumping, and JSON schema generation. ([Pydantic][1])

Suggested shape:

```python
from __future__ import annotations

from types import MappingProxyType
from pydantic import BaseModel, ConfigDict

from niri_state.health import HealthState
from niri_state.diagnostics import Diagnostics, Compatibility
from niri_state.protocol import Output, Workspace, Window, KeyboardLayouts, Overview


class Snapshot(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    revision: int
    timestamp: float
    health: HealthState

    outputs: MappingProxyType[str, Output]
    workspaces: MappingProxyType[int, Workspace]
    windows: MappingProxyType[int, Window]

    focused_workspace_id: int | None
    focused_window_id: int | None

    keyboard_layouts: KeyboardLayouts
    overview: Overview

    diagnostics: Diagnostics
    compatibility: Compatibility
```

## Stored fields vs derived fields

This is where the rewrite becomes elegant.

### Stored

Store only canonical, primary state:

* outputs
* workspaces
* windows
* focused workspace id
* focused window id
* keyboard layouts
* overview
* health
* diagnostics / compatibility

### Derived

Do **not** store:

* `focused_output_name`
* `workspaces_by_output`
* `windows_by_workspace`
* `active_workspace_by_output`
* `keyboard_current_name`

Those should be derived from canonical fields.

If you want them available on `Snapshot`, prefer plain cached properties first.

Pydantic’s docs say `computed_field` is useful for including `property` / `cached_property` values in serialization, but also note that Pydantic does not perform validation or cache invalidation on those wrapped properties. The current docs mark `computed_field` as new in v2.13, and the latest docs are for v2.13.4. That means if you truly want a 2.12+ floor, I would avoid making core design depend on `computed_field`; use ordinary properties or `cached_property` unless you later pin to `>=2.13`. ([Pydantic][2])

## The one reconciliation pass

This is the heart of the rewrite.

Instead of hand-patching focus/index relationships in reducers, there should be one central reconciliation step that runs after any state mutation.

That reconciliation pass should:

* clear `focused_window_id` if the window no longer exists,
* derive `focused_workspace_id` from the focused window when possible,
* clear `focused_workspace_id` if the workspace no longer exists,
* if no focused workspace is known, recover it from `Workspace.is_focused`,
* derive `focused_output_name` from the focused workspace,
* verify that active-workspace assumptions still hold,
* normalize any stale diagnostic pointers.

Sketch:

```python
def reconcile(engine: EngineState) -> None:
    if engine.focused_window_id is not None:
        win = engine.windows.get(engine.focused_window_id)
        if win is None:
            engine.focused_window_id = None
        else:
            engine.focused_workspace_id = win.workspace_id

    if (
        engine.focused_workspace_id is not None
        and engine.focused_workspace_id not in engine.workspaces
    ):
        engine.focused_workspace_id = None

    if engine.focused_workspace_id is None:
        for ws_id, ws in engine.workspaces.items():
            if ws.is_focused:
                engine.focused_workspace_id = ws_id
                break
```

This one design choice removes a huge amount of reducer complexity.

## Bootstrap should be typed and boring

`bootstrap.py` should not contain generic response-unwrapping cleverness.

Use the typed `niri-pypc` client directly.

The bootstrap layer should have small, explicit helpers like:

* `query_outputs() -> dict[str, Output]`
* `query_workspaces() -> list[Workspace]`
* `query_windows() -> list[Window]`
* `query_focused_output() -> Output | None`
* `query_focused_window() -> Window | None`
* `query_keyboard_layouts() -> KeyboardLayouts`
* `query_overview() -> Overview`
* `query_version() -> VersionResponse` or a narrower compatibility object

That is cleaner than a generic `_extract_payload()` abstraction.

## Event reduction model

Use a typed dispatch table.

Not a giant hand-maintained `match` chain.

Pattern:

```python
Reducer = Callable[[EngineState, EventValue], frozenset[ChangedDomain]]

EVENT_REDUCERS: dict[type[EventValue], Reducer] = {
    WindowsChangedEvent: reduce_windows_changed,
    WindowOpenedOrChangedEvent: reduce_window_opened_or_changed,
    WindowClosedEvent: reduce_window_closed,
    WindowFocusChangedEvent: reduce_window_focus_changed,
    WorkspacesChangedEvent: reduce_workspaces_changed,
    WorkspaceActivatedEvent: reduce_workspace_activated,
    KeyboardLayoutsChangedEvent: reduce_keyboard_layouts_changed,
    KeyboardLayoutSwitchedEvent: reduce_keyboard_layout_switched,
    OverviewOpenedOrClosedEvent: reduce_overview_opened_or_closed,
}
```

Then the runtime loop is conceptually:

1. receive typed event
2. dispatch reducer
3. mutate `EngineState`
4. `reconcile(engine)`
5. `freeze(engine)` into `Snapshot`
6. run invariants
7. publish `ChangeSet`

That should be the mental model of the entire library.

## Invariants

Invariants should become **smaller** and **more structured**.

Once wrappers are deleted, you no longer need:

* output key == wrapper output name
* workspace key == wrapper workspace id
* window key == wrapper window id

Those invariants disappear because the duplication disappears.

The invariants that remain valuable are:

* focused window refers to a real window
* focused workspace refers to a real workspace
* every window’s `workspace_id` points to an existing workspace
* active window / focused workspace relationships remain coherent
* workspaces belong to valid outputs
* any published derived index matches canonical maps

Represent invariant failures as structured objects:

```python
class InvariantViolation(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    path: tuple[str | int, ...] = ()
```

That is much better than plain strings.

## Config design

`NiriStateConfig` should absolutely be a frozen `BaseModel`, not a stdlib dataclass. That part of the intern memo is correct. 

But I would go further and simplify the config.

I would strongly consider removing `correctness_mode` entirely.

It is not a clean abstraction. It mainly acts as a macro that mutates lower-level policy. That makes the true behavior less explicit.

A better config is direct and policy-first:

```python
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
```

If you still want an opinionated “strict preset,” expose it as a helper constructor, not a first-class config field.

Pydantic’s docs also point out that model configuration can be expressed either via `model_config` or class arguments like `frozen=True`, and that class arguments are better recognized by static type checkers. ([Pydantic][3])

## Errors

Keep exception subclasses, but make them carry structured attributes.

Do not turn them into Pydantic models.

That would be the wrong abstraction.

Good shape:

```python
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
```

Subclasses should add narrow, meaningful fields:

* `BootstrapError(query=...)`
* `ReductionError(event_type=..., revision=...)`
* `InvariantError(violations=..., revision=...)`
* `DesyncError(event_type=..., revision=...)`
* `WaitTimeoutError(timeout=...)`

This is one place where the intern memo is right in spirit. 

## Thin protocol façade

Create `niri_state.protocol` and re-export all upstream types `niri-state` needs.

For example:

```python
from niri_pypc.types.generated.models import Output, Workspace, Window, KeyboardLayouts, Overview
from niri_pypc.types.generated.event import EventValue, UnknownEvent
from niri_pypc.types.generated.request import ...
from niri_pypc.types.generated.reply import ...
```

Then the rest of the package imports from `niri_state.protocol`, not `niri_pypc.types.generated.*` directly.

That single indirection buys you a much cleaner dependency boundary.

## Selectors

Selectors should become tiny and obvious because the snapshot stores canonical upstream models directly.

Examples:

* `get_window(snapshot, id) -> Window | None`
* `get_workspace(snapshot, id) -> Workspace | None`
* `get_focused_window(snapshot) -> Window | None`
* `list_windows_on_workspace(snapshot, workspace_id) -> tuple[Window, ...]`
* `get_focused_output_name(snapshot) -> str | None`
* `get_keyboard_current_name(snapshot) -> str | None`

No more `.protocol` drilling.

## Testing strategy for the rewrite

Rewrite the tests as executable specification, not as compatibility scaffolding.

### Factories first

Build `tests/factories/protocol.py` with helpers that construct valid upstream models:

* `make_output(...)`
* `make_workspace(...)`
* `make_window(...)`
* `make_keyboard_layouts(...)`
* `make_overview(...)`
* `make_event(...)`

### Then write tests in four layers

#### 1. Pure reducer tests

Each event mutates engine state correctly.

#### 2. Reconciliation tests

These are the most important new tests.
Examples:

* closing focused window clears/re-derives focus,
* replacing workspaces repairs focused workspace,
* focused output derives correctly from focused workspace.

#### 3. Bootstrap contract tests

These should model the actual `niri-pypc` event-stream handshake and typed request flow.

#### 4. Replay / end-to-end tests

Feed realistic event sequences and assert final snapshot equality.

For fixture validation and raw collection parsing, use cached module-level `TypeAdapter`s. Pydantic explicitly recommends instantiating a `TypeAdapter` once and reusing it because each instantiation constructs validators/serializers. ([Pydantic][4])

## What I would delete outright

These should go away in the rewrite:

* wrapper entity models
* `BootstrapPayload` as a first-class abstraction
* reducer-local focus bookkeeping
* stored derived indexes
* generic response/payload extraction helpers
* any compatibility logic tied to older `niri-pypc` wrapper patterns
* any attempt to make internal orchestration models inherit from upstream `ProtocolModel`

That last one is where I most strongly disagree with the intern memo. `ProtocolModel` belongs at the wire boundary, not in `niri-state`’s internal architecture. 

## Exact implementation sequence

This is the order I would actually use.

### Phase 1: Architecture skeleton

Create the new modules only:

* `protocol.py`
* `config.py`
* `health.py`
* `changes.py`
* `diagnostics.py`
* `snapshot.py`
* `engine_state.py`
* `reconcile.py`

No runtime yet.

### Phase 2: Bootstrap

Implement typed bootstrap queries and build the first `EngineState` from upstream models.

### Phase 3: Reducers

Implement one reducer per event plus dispatch registry.

### Phase 4: Freeze/publish

Implement snapshot freezing and change publication.

### Phase 5: Store/runtime

Implement:

* mutation loop
* broadcaster
* refresh/resync
* close lifecycle

### Phase 6: Selectors

Write the simple direct selectors after the snapshot model stabilizes.

### Phase 7: Test rewrite

Replace old fixture scaffolding with protocol factories and replay specs.

### Phase 8: Delete legacy tree

After the new path is passing, remove the old wrapper-based architecture completely.

## The few Pydantic-specific rules I would enforce

1. Use `BaseModel` for config and published immutable state. ([Pydantic][1])

2. Do not put Pydantic in the mutable reducer core unless profiling proves a need.

3. Use `computed_field` only if you later decide to require `>=2.13` and you specifically want derived data included in serialization. Otherwise, use plain properties or `cached_property`. ([Pydantic][2])

4. Be careful with `model_copy()`: Pydantic documents that `update` data is not validated, and that `model_copy()` copies the underlying `__dict__`, which can have side effects if you store cached-property state there. That is another reason to prefer rebuilding snapshots cleanly rather than patching them aggressively. ([Pydantic][5])

5. Use `TypeAdapter` in factories/tests and instantiate it once per type, not inside hot functions. ([Pydantic][4])

## Final canonical recommendation

If the only goal is the best, cleanest, most elegant codebase possible, then the answer is:

**rewrite `niri-state` as a small, sharp state engine over canonical `niri-pypc` models; do not preserve the current wrapper/entity architecture; and use Pydantic selectively at the public immutable boundary, not everywhere.**

That is the design I would endorse.

The most useful next artifact would be a concrete **module-by-module implementation spec** with exact class/function signatures for the new files.

[1]: https://pydantic.dev/docs/validation/latest/concepts/dataclasses/?utm_source=chatgpt.com "Dataclasses | Pydantic Docs"
[2]: https://pydantic.dev/docs/validation/latest/concepts/fields/?utm_source=chatgpt.com "Fields | Pydantic Docs"
[3]: https://pydantic.dev/docs/validation/latest/concepts/config/?utm_source=chatgpt.com "Configuration | Pydantic Docs"
[4]: https://pydantic.dev/docs/validation/latest/concepts/performance/?utm_source=chatgpt.com "Performance | Pydantic Docs"
[5]: https://pydantic.dev/docs/validation/2.9/api/pydantic/base_model/?utm_source=chatgpt.com "BaseModel | Pydantic Docs"
