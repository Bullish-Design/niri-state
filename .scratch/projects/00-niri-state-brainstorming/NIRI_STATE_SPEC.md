# NIRI_STATE_SPEC

Implementation specification for `niri-state`.

This document translates the concept document into precise, implementable contracts: file-level module responsibilities, public and internal APIs, snapshot/data structures, reducer signatures, health/lifecycle rules, synchronization flows, and test requirements. It is designed to align with `NIRI_PYPC_SPEC.md` so the two libraries fit together cleanly.

---

## Table of Contents

1. [Notation and Conventions](#1-notation-and-conventions)
2. [Package Structure and Module Map](#2-package-structure-and-module-map)
3. [Core Identifier Types and Compatibility Metadata](#3-core-identifier-types-and-compatibility-metadata)
4. [State Model Specification](#4-state-model-specification)
5. [Health, Lifecycle, and Revision Semantics](#5-health-lifecycle-and-revision-semantics)
6. [Change Model Specification](#6-change-model-specification)
7. [Config Module Specification](#7-config-module-specification)
8. [Error Module Specification](#8-error-module-specification)
9. [Reducer Module Specification](#9-reducer-module-specification)
10. [Invariant Module Specification](#10-invariant-module-specification)
11. [Selector Module Specification](#11-selector-module-specification)
12. [Bootstrap and Synchronization Specification](#12-bootstrap-and-synchronization-specification)
13. [Resync Coordination Specification](#13-resync-coordination-specification)
14. [Store Module Specification](#14-store-module-specification)
15. [Observation and Waiting Specification](#15-observation-and-waiting-specification)
16. [Public Package API Specification](#16-public-package-api-specification)
17. [Replay Trace Specification](#17-replay-trace-specification)
18. [Devenv Integration Specification](#18-devenv-integration-specification)
19. [Test Specification](#19-test-specification)

---

## 1. Notation and Conventions

**Implements concept:** Authority and Scope, State Model Design, Public API Concept

### Naming

- Package name: `niri-state`
- Import root: `niri_state`
- All Python identifiers follow PEP 8.
- Public data models are hand-written Pydantic v2 `BaseModel` subclasses.
- Internal enums use `enum.StrEnum` where a string-valued enum is appropriate.
- Selectors are regular typed Python callables; they are not classes unless stateful configuration is required.

### Python Version and Runtime

- Minimum Python version: **3.13**.
- Async runtime: **`asyncio` only**.
- Operating system support: Linux/Unix environments where `niri-pypc` can reach the Niri IPC Unix socket.
- No Windows support.

### Immutability Rule

All public snapshot, entity, change, and diagnostics models are immutable:

```python
from pydantic import BaseModel, ConfigDict, Field


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
```

All public models in `niri-state` inherit from a shared `FrozenModel` base or equivalent frozen configuration.

### Type Annotation Rules

- Use `from __future__ import annotations` in all modules.
- Use `T | None`, `list[T]`, `tuple[T, ...]`, and `dict[K, V]` forms.
- Public methods and functions require complete type annotations.
- Pydantic fields should prefer concrete immutable collections (`tuple[...]`) on public models.

### Dependency Boundary Rule

`niri-state` depends on `niri-pypc`; the reverse dependency is forbidden.

`niri-state` may import:
- `niri_pypc.NiriConfig`
- `niri_pypc.NiriClient`
- `niri_pypc.NiriEventStream`
- `niri_pypc.NiriConnectionBundle`
- `niri_pypc` error classes
- generated protocol types from `niri_pypc.types`

`niri-state` must not reimplement socket transport, wire framing, or raw codec behavior.

---

## 2. Package Structure and Module Map

**Implements concept:** High-Level Architecture, Dependency Rules, Proposed Repository Layout

```text
src/niri_state/
├─ __init__.py                     # Public re-exports (Section 16)
├─ _version.py                     # Package version constant
├─ errors.py                       # State-specific error taxonomy (Section 8)
├─ config.py                       # Store, resync, watcher, and wait config (Section 7)
├─ models/
│  ├─ __init__.py                  # Re-exports all public state models
│  ├─ common.py                    # FrozenModel, id aliases, small helper types
│  ├─ health.py                    # StoreHealth, compatibility metadata, diagnostics
│  ├─ entities.py                  # OutputState, WorkspaceState, WindowState, etc.
│  ├─ snapshot.py                  # NiriSnapshot, SnapshotIndexes
│  └─ change_set.py                # ChangeSet, ChangeDomain, ChangeCause
├─ reducers/
│  ├─ __init__.py
│  ├─ common.py                    # ReducerContext, ReductionResult, helpers
│  ├─ bootstrap.py                 # Bootstrap payload normalization
│  ├─ root.py                      # apply_event / apply_bootstrap dispatch entrypoints
│  ├─ outputs.py                   # Output-related event reduction
│  ├─ workspaces.py                # Workspace-related event reduction
│  ├─ windows.py                   # Window-related event reduction
│  ├─ focus.py                     # Focus/active pointer reduction
│  ├─ keyboard.py                  # Keyboard layout / similar domain reduction
│  └─ invariants.py                # Post-reduction invariant checks
├─ selectors/
│  ├─ __init__.py
│  ├─ outputs.py                   # Output selectors
│  ├─ workspaces.py                # Workspace selectors
│  ├─ windows.py                   # Window selectors
│  ├─ focus.py                     # Focus/active selectors
│  └─ aggregates.py                # Cross-domain aggregate selectors
├─ sync/
│  ├─ __init__.py
│  ├─ bootstrap.py                 # Coordinated initial sync over niri-pypc
│  ├─ resync.py                    # Resync coordinator implementation
│  └─ policies.py                  # Policy helpers for stale/fail/resync decisions
└─ store/
   ├─ __init__.py
   ├─ live_state.py                # NiriState public class (Section 14)
   ├─ broadcaster.py               # Change/watch subscriber fan-out
   └─ waiters.py                   # wait_until / wait_for_selector primitives
```

### Dependency DAG

```
store.live_state   ──→ sync.bootstrap, sync.resync, reducers.root, selectors, models, errors, config, niri-pypc
store.broadcaster  ──→ models, errors, config
store.waiters      ──→ selectors, models, errors, config
sync.bootstrap     ──→ reducers.bootstrap, reducers.root, models, errors, config, niri-pypc
sync.resync        ──→ sync.bootstrap, reducers.root, models, errors, config, niri-pypc
reducers.root      ──→ reducers.*, models, errors, niri-pypc.types
reducers.*         ──→ models, errors, niri-pypc.types
selectors.*        ──→ models
models.*           ──→ (internal model helpers only)
errors             ──→ (no internal deps)
config             ──→ niri-pypc config types only
```

### Architectural Rules

1. **Reducers are pure**: no I/O, no sleeping, no IPC, no command issuance.
2. **Selectors are pure**: no I/O and no mutation.
3. **Sync code owns races and buffering**: reducers do not know about sockets or event streams.
4. **Store code owns publication**: reducers return results; store decides whether and how to publish them.
5. **Public APIs never expose mutable internal state**.

---

## 3. Core Identifier Types and Compatibility Metadata

**Implements concept:** Source-of-Truth Model, Compatibility and Versioning

### Identifier Aliases

The state layer should preserve protocol identifiers instead of inventing new key spaces.

```python
OutputName = str
WorkspaceId = int
WindowId = int
LayerId = str
KeyboardLayoutId = str
Revision = int
```

Rules:
1. `OutputName` is the stable key for outputs.
2. `WorkspaceId` and `WindowId` are protocol identifiers when the pin exposes them.
3. If a future protocol pin changes identifier shape, `niri-state` must update these aliases deliberately.
4. Public snapshots must not mix protocol ids with synthetic ids.

### Compatibility Metadata

`niri-state` is not the protocol authority, but it must surface enough compatibility information for consumers.

```python
import enum
from pydantic import Field


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
```

Rules:
1. `niri_state_version` comes from `niri_state._version.__version__`.
2. `niri_pypc_version` comes from `niri_pypc.__version__`.
3. `upstream_version` is the upstream `niri-ipc` version exposed by the compatible `niri-pypc` release or direct metadata import.
4. `compositor_version` is populated only if a runtime version query succeeds.
5. If no version check is performed, `status=UNCHECKED`.
6. A strict mismatch that prevents startup raises before returning a live store; when surfaced in snapshots later, `status=MISMATCHED` must be explicit.

---

## 4. State Model Specification

**Implements concept:** State Model Design, Public immutability rule, Suggested top-level snapshot shape

### Common Base

All public models inherit frozen configuration:

```python
from pydantic import BaseModel, ConfigDict


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
```

### Entity Models

The public state model uses normalized entities plus selected relationship fields. Each entity carries the corresponding raw protocol model from `niri-pypc` when that is the authoritative source for wire-derived fields.

#### `OutputState`

```python
from niri_pypc.types import Output


class OutputState(FrozenModel):
    name: OutputName
    raw: Output
    workspace_ids: tuple[WorkspaceId, ...] = ()
    focused_workspace_id: WorkspaceId | None = None
    is_active: bool = False
```

Rules:
1. `name` is always equal to `raw.name`.
2. `workspace_ids` is explicitly ordered and immutable.
3. `focused_workspace_id`, if set, must appear in `workspace_ids`.
4. `is_active` is derived state, not an independent source of truth.

#### `WorkspaceState`

```python
from niri_pypc.types import Workspace


class WorkspaceState(FrozenModel):
    id: WorkspaceId
    raw: Workspace
    output_name: OutputName | None = None
    window_ids: tuple[WindowId, ...] = ()
    is_active: bool = False
    is_focused: bool = False
    is_visible: bool = False
```

Rules:
1. `id` is always equal to the workspace id from the protocol model.
2. `output_name` is `None` only when the protocol does not associate the workspace with an output.
3. `window_ids` is explicitly ordered and immutable.
4. At most one workspace may have `is_active=True` if the pin models a singular active workspace.
5. `is_focused=True` implies `is_visible=True`.

#### `WindowState`

```python
from niri_pypc.types import Window


class WindowState(FrozenModel):
    id: WindowId
    raw: Window
    workspace_id: WorkspaceId | None = None
    output_name: OutputName | None = None
    is_focused: bool = False
    is_visible: bool = False
```

Rules:
1. `id` is always equal to the window id from the protocol model.
2. `workspace_id` and `output_name` are normalized relationship fields.
3. `is_focused=True` implies `is_visible=True`.
4. At most one window may have `is_focused=True`.

#### Optional Domain Models

The exact supported domain set is pin-dependent. Additional public entity models may be introduced for protocol surfaces that are explicitly included in the state model:

- `LayerSurfaceState`
- `KeyboardLayoutState`
- `CastState`
- similar pin-specific domain entities

All such models follow the same rules:
1. Preserve protocol ids where available.
2. Carry raw protocol payload in `raw` unless the state surface is already fully normalized.
3. Add only deterministic derived relationship fields.

### Snapshot Diagnostics

```python
class SnapshotDiagnostics(FrozenModel):
    last_error: str | None = None
    last_desync_reason: str | None = None
    buffered_event_count_during_bootstrap: int = 0
    replayed_event_count_during_bootstrap: int = 0
    last_event_type: str | None = None
```

### Snapshot Indexes

To keep selector logic simple and deterministic, the snapshot includes stable explicit orderings.

```python
class SnapshotIndexes(FrozenModel):
    output_order: tuple[OutputName, ...] = ()
    workspace_order: tuple[WorkspaceId, ...] = ()
    window_order: tuple[WindowId, ...] = ()
```

Rules:
1. Orders are explicit and must not rely on `dict` iteration order.
2. Every id in an order tuple must exist in the corresponding mapping.
3. No duplicates are allowed.

### `NiriSnapshot`

```python
class NiriSnapshot(FrozenModel):
    revision: Revision
    health: StoreHealth
    compatibility: CompatibilityInfo
    bootstrapped: bool
    outputs_by_name: dict[OutputName, OutputState]
    workspaces_by_id: dict[WorkspaceId, WorkspaceState]
    windows_by_id: dict[WindowId, WindowState]
    indexes: SnapshotIndexes = SnapshotIndexes()
    active_output_name: OutputName | None = None
    active_workspace_id: WorkspaceId | None = None
    focused_window_id: WindowId | None = None
    keyboard_layout: str | None = None
    last_good_revision: Revision | None = None
    diagnostics: SnapshotDiagnostics = SnapshotDiagnostics()
```

Rules:
1. `revision` is monotonically increasing for every published snapshot.
2. `bootstrapped=True` iff the bootstrap sequence completed successfully at least once for this store lifetime.
3. `last_good_revision` is:
   - equal to `revision` for `LIVE` snapshots,
   - equal to the most recent coherent `LIVE` revision for `STALE`, `RESYNCING`, `FAILED`, or `CLOSED` snapshots,
   - `None` only before any coherent snapshot has ever been published.
4. `active_workspace_id` must reference an existing workspace when non-`None`.
5. `focused_window_id` must reference an existing window when non-`None`.
6. If `active_output_name` is non-`None`, it must exist in `outputs_by_name`.

### Empty Bootstrapping Snapshot

The store may maintain an internal placeholder snapshot before first publish.

```python
EMPTY_BOOTSTRAPPING_SNAPSHOT = NiriSnapshot(
    revision=0,
    health=StoreHealth.BOOTSTRAPPING,
    compatibility=CompatibilityInfo(
        niri_state_version="<version>",
        niri_pypc_version="<version>",
    ),
    bootstrapped=False,
    outputs_by_name={},
    workspaces_by_id={},
    windows_by_id={},
)
```

This placeholder is internal-only unless explicitly documented otherwise. The public default behavior is that `NiriState.connect()` returns only after a coherent first snapshot is available.

---

## 5. Health, Lifecycle, and Revision Semantics

**Implements concept:** Snapshot Health and Lifecycle, Resync Strategy, Waiting semantics

### `StoreHealth`

```python
import enum


class StoreHealth(enum.StrEnum):
    BOOTSTRAPPING = "bootstrapping"
    LIVE = "live"
    STALE = "stale"
    RESYNCING = "resyncing"
    CLOSED = "closed"
    FAILED = "failed"
```

### Health Transition Rules

Valid transitions:

```text
BOOTSTRAPPING -> LIVE
BOOTSTRAPPING -> STALE
BOOTSTRAPPING -> FAILED
BOOTSTRAPPING -> CLOSED

LIVE -> LIVE            # normal event application
LIVE -> STALE           # unknown event, invariant failure, transport loss
LIVE -> RESYNCING       # explicit/manual/automatic resync start
LIVE -> CLOSED          # graceful close
LIVE -> FAILED          # unrecoverable internal/state failure

STALE -> STALE          # repeated stale-causing inputs or diagnostics update
STALE -> RESYNCING      # manual or automatic resync start
STALE -> CLOSED         # graceful close
STALE -> FAILED         # unrecoverable failure

RESYNCING -> LIVE       # successful fresh bootstrap
RESYNCING -> STALE      # resync failed but store remains readable last-known-good
RESYNCING -> FAILED     # terminal failure
RESYNCING -> CLOSED     # explicit close during resync

FAILED -> CLOSED        # final teardown
```

Invalid transitions raise `StateLifecycleError` internally and are treated as bugs.

### Revision Rules

1. Every published snapshot increments the revision by exactly 1.
2. A health-only transition still publishes a new revision.
3. A no-op event that does not alter entities or health may either:
   - publish no new revision, or
   - publish a new revision with `applied=False`.

For `niri-state`, the required default is:
- **Do not publish a new revision for a pure no-op event** unless diagnostics or health changed.

4. `ChangeSet.old_revision` and `ChangeSet.new_revision` must reflect the actual published transition.
5. Revisions are store-local and restart from 1 after a fresh `NiriState.connect()`.

### Coherence Rule

A public snapshot is coherent if and only if:
1. It represents a full state after complete reducer application.
2. Invariant validation has either passed or the store has transitioned to a health state that explicitly permits publication (`STALE`, `FAILED`, `CLOSED`).
3. No partial reducer mutation is visible.

---

## 6. Change Model Specification

**Implements concept:** Change Model, Waiting and Observation APIs

### `ChangeCause`

```python
class ChangeCause(enum.StrEnum):
    BOOTSTRAP = "bootstrap"
    EVENT = "event"
    MANUAL_RESYNC = "manual_resync"
    AUTO_RESYNC = "auto_resync"
    MANUAL_REFRESH = "manual_refresh"
    CLOSE = "close"
    FAILURE = "failure"
    STALE_TRANSITION = "stale_transition"
```

### `ChangeDomain`

```python
class ChangeDomain(enum.StrEnum):
    OUTPUTS = "outputs"
    WORKSPACES = "workspaces"
    WINDOWS = "windows"
    FOCUS = "focus"
    KEYBOARD = "keyboard"
    LAYERS = "layers"
    HEALTH = "health"
    METADATA = "metadata"
```

### `ChangeSet`

```python
from typing import Any
from pydantic import Field


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

Rules:
1. `snapshot.revision == new_revision`.
2. `old_revision is None` only for the first published snapshot.
3. `domains` must be deduplicated and sorted in a stable order before publication.
4. `event_type` is the event variant name for event-driven changes and `None` for bootstrap-only transitions.
5. `details` is for small structured diagnostics only; it must remain JSON-serializable.

### Publication Rules

1. Every published snapshot publishes exactly one corresponding `ChangeSet`.
2. `changes()` subscribers receive `ChangeSet` values in ascending `new_revision` order.
3. `watch_selector()` is built on top of snapshots/change sets, not on ad hoc mutation callbacks.

---

## 7. Config Module Specification

**Implements concept:** Resync Strategy, Waiting semantics, Unknown and Unsupported Event Policy

### `config.py`

The config layer composes `niri-pypc` configuration with state-specific policies.

```python
from __future__ import annotations

import enum
from pydantic import BaseModel, ConfigDict, Field
from niri_pypc import NiriConfig


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
    model_config = ConfigDict(frozen=True, extra="forbid")

    pypc: NiriConfig = NiriConfig()
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
```

### Config Semantics

1. `pypc` contains all transport/socket/timeouts/backpressure config needed by `niri-pypc`.
2. `bootstrap_timeout` bounds the total initial synchronization operation.
3. `bootstrap_event_buffer_capacity` bounds the queue used to close the bootstrap race window.
4. `changes_queue_capacity` applies per subscriber, not globally.
5. `watcher_queue_capacity` applies per selector watch subscription.
6. `overflow_mode` controls subscriber queue overflow behavior for both change and selector watches.
7. `resync_policy=AUTO` permits automatic resync attempts on configured desync triggers.
8. `max_consecutive_resync_failures` protects against endless resync loops.
9. `bootstrap_query_plan_name` is a versioned logical name; changing the default plan is a documented behavioral change.

### Queue Overflow Rules

For subscriber queues:
- `DROP_OLDEST`: evict the oldest queued item, enqueue the new item, and record a warning/diagnostic.
- `FAIL_FAST`: terminate the specific subscription with `WatchOverflowError`.

Overflow of the **bootstrap event buffer** is different:
- it is always a bootstrap failure, because the race window can no longer be proven closed.

---

## 8. Error Module Specification

**Implements concept:** Error Model

### Class Hierarchy

```python
class NiriStateError(Exception):
    """Base exception for all niri-state errors."""

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
    ) -> None: ...


class BootstrapError(NiriStateError):
    """Initial synchronization failed before a coherent live snapshot was established."""


class ReductionError(NiriStateError):
    """Reducer failed to apply a bootstrap payload or event."""


class InvariantError(NiriStateError):
    """Snapshot invariants were violated."""


class DesyncError(NiriStateError):
    """Store correctness can no longer be guaranteed without resync."""


class ResyncError(NiriStateError):
    """A resync attempt failed."""


class StateLifecycleError(NiriStateError):
    """Invalid store lifecycle transition or operation."""


class SelectorWaitError(NiriStateError, TimeoutError):
    """A wait/watch operation could not satisfy its contract."""


class WatchOverflowError(NiriStateError):
    """A change or selector watch subscriber overflowed its queue."""


class CompatibilityError(NiriStateError):
    """Version or compatibility policy rejected startup or continued operation."""
```

### Error Context Rules

1. All state errors should include `revision`, `last_good_revision`, and `health` when known.
2. `event_type` is populated for event-driven failures.
3. `selector_name` is populated for selector wait/watch failures.
4. Wrapped `niri-pypc` exceptions must use Python exception chaining:

```python
raise BootstrapError("failed to collect bootstrap payload") from exc
```

5. `SelectorWaitError` should be catchable as `TimeoutError` when timeouts are the root cause.
6. `DesyncError` is used for freshness/correctness contract breakage, not merely any reducer exception.

### Mapping Rules from `niri-pypc`

| Source error | `niri-state` mapping |
|---|---|
| `TransportError` during bootstrap | `BootstrapError` |
| `RemoteError` during bootstrap query | `BootstrapError` |
| `DecodeError` in live event loop | `DesyncError` or `BootstrapError` depending on phase |
| `LifecycleError` during store close/start | `StateLifecycleError` |

---

## 9. Reducer Module Specification

**Implements concept:** Reducer Design, Bootstrap consistency rule, Unknown event policy

### Reducer Principles

Reducers are pure functions:
- input: snapshot and typed protocol input
- output: new snapshot candidate and metadata
- no side effects
- no I/O
- no hidden mutation

### Reducer Support Types

#### `ReducerContext`

```python
from typing import Any
from pydantic import Field


class ReducerContext(FrozenModel):
    cause: ChangeCause
    unknown_event_policy: UnknownEventPolicy
    invariant_failure_policy: InvariantFailurePolicy
    compatibility: CompatibilityInfo
    metadata: dict[str, Any] = Field(default_factory=dict)
```

#### `ReductionResult`

```python
from pydantic import Field


class ReductionResult(FrozenModel):
    snapshot: NiriSnapshot
    domains: tuple[ChangeDomain, ...] = ()
    event_type: str | None = None
    applied: bool = True
    summary: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
```

Rules:
1. `snapshot` is the fully built post-reduction candidate.
2. `domains` lists changed domains only.
3. `applied=False` indicates a deliberate no-op.
4. `ReductionResult` does not publish anything itself.

### Bootstrap Payload Model

The sync layer translates query responses into a reducer-friendly bootstrap payload.

```python
from niri_pypc.types import Output, Workspace, Window


class BootstrapPayload(FrozenModel):
    outputs: tuple[Output, ...] = ()
    workspaces: tuple[Workspace, ...] = ()
    windows: tuple[Window, ...] = ()
    keyboard_layout: str | None = None
    buffered_events: tuple[object, ...] = ()
    compatibility: CompatibilityInfo
    query_plan_name: str
```

Rules:
1. `buffered_events` contains typed `niri-pypc` event values already decoded by the event stream.
2. Query responses are normalized into the exact payload schema before entering reducer code.
3. Bootstrap payloads are versioned indirectly by `query_plan_name`.

### Public Reducer Entry Points

#### `reducers.bootstrap.build_initial_snapshot`

```python
def build_initial_snapshot(
    payload: BootstrapPayload,
    *,
    revision: Revision,
    context: ReducerContext,
) -> ReductionResult:
    """Build the first coherent snapshot from bootstrap query results only."""
```

Rules:
1. Does not replay buffered events.
2. Produces a coherent base snapshot candidate.
3. Runs the same normalization logic used by event reduction when practical.

#### `reducers.root.apply_event`

```python
from niri_pypc.types import Event, UnknownEvent


def apply_event(
    snapshot: NiriSnapshot,
    event: object,
    *,
    next_revision: Revision,
    context: ReducerContext,
) -> ReductionResult:
    """Apply one typed event to a snapshot and return the next snapshot candidate."""
```

Accepted `event` types:
- concrete event variant model instances from `niri_pypc.types`
- explicit unknown sentinel models from `niri_pypc` inbound decoding

Rules:
1. Dispatch by exact event type, not raw dict keys.
2. Unknown sentinel handling follows `UnknownEventPolicy`.
3. Unsupported but known events must be treated explicitly; they may not be silently ignored.
4. If an event is a no-op under current state, return `applied=False` and the original snapshot value unchanged.

### Domain Reducer Contracts

Each domain reducer follows the pattern:

```python
def reduce_<domain>_event(
    snapshot: NiriSnapshot,
    event: <SpecificEventType>,
    *,
    next_revision: Revision,
    context: ReducerContext,
) -> ReductionResult: ...
```

Domain reducers must:
1. Build an entirely new `NiriSnapshot` value or an immutable copy with updated fields.
2. Preserve untouched mappings exactly.
3. Update relationship fields consistently in all affected entities.
4. Never leave dangling ids in order tuples or relationship tuples.

### Unknown / Unsupported Event Handling

Default required behavior:
- with `unknown_event_policy=STALE`, publish a new snapshot with:
  - incremented revision,
  - unchanged entity state,
  - `health=STALE`,
  - diagnostics recording the unknown/unsupported event,
  - `ChangeCause.STALE_TRANSITION`,
  - `ChangeDomain.HEALTH` and `ChangeDomain.METADATA`
- with `unknown_event_policy=FAIL`, raise `DesyncError`

### No-Op Handling

A reducer may return `applied=False` only when:
1. the event is semantically redundant against the current snapshot,
2. health and diagnostics remain unchanged,
3. no invariant consequences exist.

Example: repeated focus event pointing to the already focused window.

---

## 10. Invariant Module Specification

**Implements concept:** Invariant examples, Reducer design

### `reducers.invariants.check_snapshot_invariants`

```python
class InvariantViolation(FrozenModel):
    code: str
    message: str
    domains: tuple[ChangeDomain, ...] = ()
    entity_ids: tuple[str, ...] = ()


def check_snapshot_invariants(snapshot: NiriSnapshot) -> tuple[InvariantViolation, ...]:
    """Return all invariant violations for a snapshot candidate."""
```

### Required Invariants

#### Identity / Mapping Invariants

1. Every `OutputState.name` equals its key in `outputs_by_name`.
2. Every `WorkspaceState.id` equals its key in `workspaces_by_id`.
3. Every `WindowState.id` equals its key in `windows_by_id`.

#### Relationship Invariants

4. Every `workspace.output_name`, when non-`None`, exists in `outputs_by_name`.
5. Every `window.workspace_id`, when non-`None`, exists in `workspaces_by_id`.
6. If `window.output_name` is non-`None`, it exists in `outputs_by_name`.
7. Every `workspace.window_ids` entry exists in `windows_by_id`.
8. Every `output.workspace_ids` entry exists in `workspaces_by_id`.

#### Pointer Invariants

9. `active_output_name`, if set, exists in `outputs_by_name`.
10. `active_workspace_id`, if set, exists in `workspaces_by_id`.
11. `focused_window_id`, if set, exists in `windows_by_id`.
12. If `focused_window_id` is set, the referenced window has `is_focused=True`.

#### Cardinality Invariants

13. At most one window has `is_focused=True`.
14. At most one output has `is_active=True`.
15. At most one workspace has `is_active=True` unless protocol semantics explicitly permit otherwise.

#### Ordering Invariants

16. `indexes.output_order` contains each output exactly once.
17. `indexes.workspace_order` contains each workspace exactly once.
18. `indexes.window_order` contains each window exactly once.

### Enforcement Policy

After each non-no-op reducer result:
1. Run `check_snapshot_invariants()`.
2. If violations are empty, continue.
3. If violations exist and `invariant_failure_policy=STALE`:
   - convert the result into a `STALE` snapshot publication,
   - record the invariant failure in diagnostics,
   - do not claim `LIVE` correctness.
4. If violations exist and `invariant_failure_policy=FAIL`, raise `InvariantError`.

---

## 11. Selector Module Specification

**Implements concept:** Selector and Query Design

### Selector Type Aliases

```python
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")
SnapshotSelector = Callable[[NiriSnapshot], T]
SnapshotPredicate = Callable[[NiriSnapshot], bool]
SelectorPredicate = Callable[[T], bool]
```

### Rules

1. Selectors accept a `NiriSnapshot` and return a typed value.
2. Selectors do not raise for missing state unless explicitly documented.
3. Prefer `None`/empty tuple for absence over ad hoc exceptions.
4. Selectors must be deterministic and side-effect free.

### Required Selector Surface

#### Output Selectors (`selectors.outputs`)

```python
def output_by_name(snapshot: NiriSnapshot, name: OutputName) -> OutputState | None: ...
def outputs(snapshot: NiriSnapshot) -> tuple[OutputState, ...]: ...
def active_output(snapshot: NiriSnapshot) -> OutputState | None: ...
def workspaces_on_output(snapshot: NiriSnapshot, name: OutputName) -> tuple[WorkspaceState, ...]: ...
```

#### Workspace Selectors (`selectors.workspaces`)

```python
def workspace_by_id(snapshot: NiriSnapshot, workspace_id: WorkspaceId) -> WorkspaceState | None: ...
def workspaces(snapshot: NiriSnapshot) -> tuple[WorkspaceState, ...]: ...
def active_workspace(snapshot: NiriSnapshot) -> WorkspaceState | None: ...
def windows_on_workspace(snapshot: NiriSnapshot, workspace_id: WorkspaceId) -> tuple[WindowState, ...]: ...
```

#### Window Selectors (`selectors.windows`)

```python
def window_by_id(snapshot: NiriSnapshot, window_id: WindowId) -> WindowState | None: ...
def windows(snapshot: NiriSnapshot) -> tuple[WindowState, ...]: ...
def focused_window(snapshot: NiriSnapshot) -> WindowState | None: ...
def visible_windows(snapshot: NiriSnapshot) -> tuple[WindowState, ...]: ...
```

#### Focus Selectors (`selectors.focus`)

```python
def focused_window_id(snapshot: NiriSnapshot) -> WindowId | None: ...
def active_workspace_id(snapshot: NiriSnapshot) -> WorkspaceId | None: ...
def active_output_name(snapshot: NiriSnapshot) -> OutputName | None: ...
```

#### Aggregate Selectors (`selectors.aggregates`)

```python
def window_count(snapshot: NiriSnapshot) -> int: ...
def workspace_count(snapshot: NiriSnapshot) -> int: ...
def output_count(snapshot: NiriSnapshot) -> int: ...
def has_window(snapshot: NiriSnapshot, window_id: WindowId) -> bool: ...
```

### Selector Stability Rules

1. Given equal snapshots, selector outputs must compare equal.
2. Ordering selectors must use snapshot indexes.
3. `watch_selector()` deduplication uses normal Python equality on selector results.

---

## 12. Bootstrap and Synchronization Specification

**Implements concept:** Bootstrap and Synchronization Strategy, Bootstrap rule

### Sync Goal

Bootstrap must produce a first coherent `LIVE` snapshot while closing the race between initial command queries and incoming live events.

### Module: `sync.bootstrap`

#### `BootstrapArtifacts`

```python
from typing import Any
from niri_pypc import NiriConnectionBundle


class BootstrapArtifacts(FrozenModel):
    payload: BootstrapPayload
    base_result: ReductionResult
    replay_results: tuple[ReductionResult, ...] = ()
    first_live_snapshot: NiriSnapshot
    replayed_event_count: int = 0
```

#### `run_bootstrap`

```python
async def run_bootstrap(
    bundle: NiriConnectionBundle,
    config: NiriStateConfig,
) -> BootstrapArtifacts:
    """Run the coordinated bootstrap sequence and return the first live snapshot artifacts."""
```

### Required Bootstrap Sequence

1. Open a `NiriConnectionBundle` using `niri-pypc`.
2. Confirm the event stream is connected.
3. Start buffering incoming typed events into an internal FIFO buffer.
4. Optionally perform compatibility/version checks.
5. Execute the explicit initial query suite using the command client.
6. Normalize command responses into a `BootstrapPayload`.
7. Build a base snapshot using `reducers.bootstrap.build_initial_snapshot()`.
8. Replay buffered events in arrival order using `reducers.root.apply_event()`.
9. Run invariant checks after each replayed event application using the normal reducer path.
10. Produce the first `LIVE` snapshot only after replay completes successfully.

### Bootstrap Query Plan

The query plan is explicit and versioned by logical name, not accidental call order.

Default plan name: `default`

The required default plan covers every domain modeled by the snapshot. At minimum, it should include enough request/response surfaces to populate:
- outputs
- workspaces
- windows
- focus/active pointers where not derivable from the above
- keyboard layout or equivalent state only if included in the state model

### Buffering Rules

1. The event buffer is FIFO.
2. Each buffered item is a decoded typed event from `niri-pypc`, not raw JSON.
3. Buffer overflow causes bootstrap failure.
4. Buffered events are replayed exactly once.
5. If replay fails under default strictness, bootstrap fails; no partial live state is published.

### Compatibility Check Rules

If enabled by policy:
1. Bootstrap may send a version query using `niri-pypc`.
2. If the compositor version is incompatible and policy is strict, raise `CompatibilityError`.
3. Compatibility metadata is embedded into the first live snapshot.

### Bootstrap Failure Rules

Any of the following raise `BootstrapError`:
- command request failure
- event buffer overflow
- replay reduction failure
- transport loss during bootstrap
- timeout of the overall bootstrap operation
- strict compatibility mismatch

If bootstrap fails, `NiriState.connect()` does not return a usable live store.

---

## 13. Resync Coordination Specification

**Implements concept:** Resync Strategy, Unknown and Unsupported Event Policy

### Module: `sync.resync`

#### `ResyncCoordinator`

```python
class ResyncCoordinator:
    """Serializes resync attempts and tracks failure counts."""

    def __init__(self, config: NiriStateConfig) -> None: ...

    @property
    def in_progress(self) -> bool: ...

    @property
    def consecutive_failures(self) -> int: ...

    async def run(self, state: "NiriState") -> ChangeSet | None: ...
```

### Resync Semantics

1. At most one resync may be in progress at a time.
2. A resync always uses a fresh `NiriConnectionBundle`.
3. The currently published snapshot remains readable during resync.
4. Resync begins by publishing a `RESYNCING` snapshot.
5. On success, resync publishes a new `LIVE` snapshot derived from a fresh bootstrap.
6. On failure:
   - if the store still has a coherent last-known-good snapshot, publish `STALE`
   - otherwise publish `FAILED`

### Resync Triggers

Required trigger set:
- explicit manual refresh/resync call
- transport loss in live event loop
- unknown inbound event when stale-on-unknown policy is active
- invariant failure when stale-on-invariant policy is active

### Auto-Resync Rules

With `resync_policy=AUTO`:
1. The store automatically schedules resync after a stale-causing trigger.
2. Automatic resync attempts stop after `max_consecutive_resync_failures`.
3. Exceeding that threshold transitions the store to `FAILED`.

With `resync_policy=MANUAL`:
1. The store transitions to `STALE` and remains readable.
2. No automatic attempt occurs.
3. The caller may invoke `await state.refresh()` explicitly.

---

## 14. Store Module Specification

**Implements concept:** Live state API, Change observation API, Wait helper API

### Public Class: `store.live_state.NiriState`

```python
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any, TypeVar

T = TypeVar("T")


class NiriState:
    """Live observed compositor state derived from niri-pypc requests and events."""

    def __init__(self, config: NiriStateConfig) -> None: ...

    @classmethod
    async def connect(
        cls,
        config: NiriStateConfig | None = None,
    ) -> "NiriState":
        """Create the store, run bootstrap, and return a live instance."""

    def current(self) -> NiriSnapshot:
        """Return the latest published snapshot immediately."""

    async def snapshot(
        self,
        *,
        wait_for_live: bool = False,
        timeout: float | None = None,
    ) -> NiriSnapshot:
        """Return the latest coherent snapshot, optionally waiting for LIVE health."""

    def health(self) -> StoreHealth:
        """Return the current store health."""

    async def changes(self) -> AsyncIterator[ChangeSet]:
        """Yield published change sets in revision order."""

    async def watch_selector(
        self,
        selector: SnapshotSelector[T],
        *,
        emit_initial: bool | None = None,
        dedupe: bool | None = None,
    ) -> AsyncIterator[T]:
        """Yield selector values when they change."""

    async def wait_until(
        self,
        predicate: SnapshotPredicate,
        *,
        timeout: float | None = None,
        description: str | None = None,
        health_policy: WaitHealthPolicy | None = None,
    ) -> NiriSnapshot:
        """Wait until predicate(snapshot) is true and return that snapshot."""

    async def wait_for_selector(
        self,
        selector: SnapshotSelector[T],
        *,
        predicate: SelectorPredicate[T] | None = None,
        timeout: float | None = None,
        description: str | None = None,
        health_policy: WaitHealthPolicy | None = None,
    ) -> T:
        """Wait until a selector-derived value satisfies its predicate."""

    async def refresh(self) -> NiriSnapshot:
        """Perform a manual resync and return the resulting snapshot."""

    async def close(self) -> None:
        """Close the store and settle observers predictably. Idempotent."""

    async def __aenter__(self) -> "NiriState": ...
    async def __aexit__(self, *exc: Any) -> None: ...
```

### Store Internal State

The store owns:
- latest published snapshot
- change broadcaster
- selector watch subscriptions
- active `niri-pypc` bundle for live operation
- background event-consumer task
- optional resync task
- lifecycle lock(s)

### Connect Flow

`NiriState.connect()` performs:
1. config normalization
2. initial bundle open via `niri-pypc`
3. bootstrap run
4. first live snapshot publication
5. start of the live event-consumer task
6. return of a usable store instance

If any step fails, connect raises and no half-live object is returned.

### Event Consumer Task

The live store runs one background event-consumer task.

Pseudo-flow:

```python
while not closed:
    event = await bundle.events.next()
    result = apply_event(current_snapshot, event, next_revision=..., context=...)
    publish(result)
```

Rules:
1. Exactly one event-consumer task exists per store instance.
2. Event application is serialized.
3. No two events may be reduced concurrently for one store.
4. Subscribers must observe the same published revision order.

### Snapshot Publication

The store owns a private `_publish(change: ChangeSet) -> None` method or equivalent.

Publication responsibilities:
1. replace the current snapshot atomically
2. update internal revision pointer
3. fan out `ChangeSet` to subscribers
4. notify waiters/selectors
5. record diagnostics/metrics if present

### Close Semantics

`close()` must:
1. be idempotent
2. cancel or settle the event-consumer task
3. close the underlying `niri-pypc` bundle
4. publish a final `CLOSED` snapshot if a store had been live/readable
5. complete change/watch iterators cleanly after the final publication
6. reject new `refresh()` calls and new subscriptions after close starts

### Concurrency Rules

1. `current()` is safe from any task.
2. `snapshot()` is safe from any task.
3. `changes()` may be called multiple times; each call creates an independent subscription.
4. `watch_selector()` may be called multiple times; each call creates an independent subscription.
5. `refresh()` is serialized; concurrent refresh calls await the same resync operation or fail with `StateLifecycleError` if policy forbids it.

---

## 15. Observation and Waiting Specification

**Implements concept:** Pull-oriented APIs, Push-oriented APIs, Waiting semantics

### Broadcaster Model (`store.broadcaster`)

The broadcaster manages independent subscriber queues for:
- raw `ChangeSet` subscribers
- selector-derived value subscribers

#### Change Subscriber Rules

1. Every `changes()` call allocates a per-subscriber queue.
2. Each subscriber queue has capacity `changes_queue_capacity`.
3. Overflow behavior follows `StoreOverflowMode`.
4. Closing the store terminates all subscriptions after final publication.

### Waiter Primitives (`store.waiters`)

Wait operations are event-driven and are implemented atop change publication, not polling.

#### `wait_until`

Required behavior:
1. Evaluate the predicate against the current snapshot first.
2. If already satisfied, return immediately.
3. Otherwise subscribe to changes and re-evaluate after each published snapshot.
4. On timeout, raise `SelectorWaitError`.
5. On stale/failed/closed health:
   - `REQUIRE_LIVE`: fail with `SelectorWaitError`
   - `ALLOW_STALE`: continue using the last published snapshot until timeout/close/failure semantics say otherwise

#### `wait_for_selector`

Required behavior:
1. Compute the selector on the current snapshot.
2. If `predicate` is `None`, truthiness is **not** used implicitly; the default predicate is equality to the next distinct value publication.
3. If a predicate is provided and already satisfied, return immediately.
4. Otherwise subscribe to changes, recompute the selector after each publication, and apply the predicate.
5. Timeouts raise `SelectorWaitError`.

### `watch_selector`

Required behavior:
1. Selector values are computed from coherent snapshots only.
2. If `emit_initial=True`, yield the selector result from the current snapshot first.
3. If `dedupe=True`, suppress consecutive equal values.
4. A selector exception terminates only that subscription.
5. Subscriber queue overflow follows `StoreOverflowMode`.

### Selector Naming for Errors

For user-friendly diagnostics, the store should derive a stable selector label when possible:
- explicit function `__name__`
- fallback to `repr(selector)`

This value is used in `SelectorWaitError.selector_name`.

---

## 16. Public Package API Specification

**Implements concept:** Public API Concept, Relationship to niri-pypc

### `src/niri_state/__init__.py`

```python
"""niri-state: live observed compositor state built on top of niri-pypc."""

from niri_state._version import __version__
from niri_state.config import (
    NiriStateConfig,
    ResyncPolicy,
    StoreOverflowMode,
    UnknownEventPolicy,
    InvariantFailurePolicy,
    WaitHealthPolicy,
)
from niri_state.errors import (
    NiriStateError,
    BootstrapError,
    ReductionError,
    InvariantError,
    DesyncError,
    ResyncError,
    StateLifecycleError,
    SelectorWaitError,
    WatchOverflowError,
    CompatibilityError,
)
from niri_state.store.live_state import NiriState
from niri_state.models import *  # public frozen models
from niri_state import selectors
```

### `src/niri_state/models/__init__.py`

Re-export:
- `CompatibilityInfo`, `CompatibilityStatus`, `StoreHealth`, `SnapshotDiagnostics`
- `OutputState`, `WorkspaceState`, `WindowState`, and any additional supported entities
- `SnapshotIndexes`, `NiriSnapshot`
- `ChangeSet`, `ChangeCause`, `ChangeDomain`

### Import Conventions for Users

```python
from niri_state import NiriState, NiriStateConfig, selectors
from niri_state.models import NiriSnapshot, ChangeSet, StoreHealth
from niri_state.errors import SelectorWaitError
```

### Public Boundary Rules

1. Public consumers interact through `NiriState`, public models, and selector functions.
2. Reducers, sync helpers, and broadcaster internals are not public API.
3. `niri-state` may expose `selectors` as a package namespace for ergonomic import.

---

## 17. Replay Trace Specification

**Implements concept:** Replayable correctness, Replay tests

### Purpose

Replay traces provide deterministic regression inputs for reducer and convergence testing.

### File Format

Preferred format: JSON Lines (`.jsonl`)

Each line is one record with a `kind` field.

#### Supported Record Kinds

1. `bootstrap_payload`
2. `event`
3. `expect_revision`
4. `expect_health`
5. `expect_selector`

Example:

```json
{"kind":"bootstrap_payload","data":{...}}
{"kind":"event","data":{"WorkspaceActivated":{...}}}
{"kind":"expect_revision","value":2}
{"kind":"expect_health","value":"live"}
{"kind":"expect_selector","selector":"focused_window_id","value":42}
```

### Trace Rules

1. Trace bootstrap payloads use the normalized `BootstrapPayload` schema, not ad hoc raw RPC transcripts.
2. Event records use the `niri-pypc` externally-tagged event JSON shape or pre-decoded typed fixtures converted from it.
3. Replay tests must prove deterministic revision history for identical input streams.
4. Regression traces should be kept minimal and named for the bug or scenario they cover.

### Replay Engine Contract

A test helper may expose:

```python
def replay_trace(path: Path) -> tuple[NiriSnapshot, list[ChangeSet]]: ...
```

This helper:
1. builds the initial snapshot from the trace payload,
2. applies events in order through the same reducers as the live store,
3. returns the final snapshot and all produced changes.

---

## 18. Devenv Integration Specification

**Implements concept:** Proposed Repository Layout, Recommended Immediate Implementation Plan

### `devenv.nix` Additions

`niri-state` has no schema export pipeline of its own, but its environment must include:
- Python 3.13
- `uv`
- testing/lint/typecheck tooling
- the compatible `niri-pypc` dependency

Example scripting surface:

```nix
{
  packages = [ pkgs.git pkgs.uv ];

  languages = {
    python = {
      enable = true;
      version = "3.13";
      venv.enable = true;
      uv.enable = true;
    };
  };

  scripts = {
    test-reducers.exec = "pytest tests/reducers -q";
    test-selectors.exec = "pytest tests/selectors -q";
    test-store.exec = "pytest tests/store tests/sync tests/integration -q";
    test-all.exec = "pytest -q";
    lint.exec = "ruff check . && ruff format --check .";
    typecheck.exec = "ty check .";
  };
}
```

### Workflow Commands

| Command | Purpose |
|---|---|
| `devenv shell -- uv sync --extra dev` | install project and dev deps |
| `devenv shell -- test-reducers` | run reducer suite |
| `devenv shell -- test-selectors` | run selector suite |
| `devenv shell -- test-store` | run sync/store/integration suite |
| `devenv shell -- test-all` | run full test suite |
| `devenv shell -- lint` | lint and format check |
| `devenv shell -- typecheck` | static type checking |

---

## 19. Test Specification

**Implements concept:** Testing Strategy, CI Quality Gates

### Test Directory Structure

```text
tests/
├─ conftest.py
├─ reducers/
│  ├─ test_bootstrap.py
│  ├─ test_outputs.py
│  ├─ test_workspaces.py
│  ├─ test_windows.py
│  ├─ test_focus.py
│  ├─ test_unknown_events.py
│  └─ test_invariants.py
├─ selectors/
│  ├─ test_outputs.py
│  ├─ test_workspaces.py
│  ├─ test_windows.py
│  ├─ test_focus.py
│  └─ test_aggregates.py
├─ sync/
│  ├─ test_bootstrap.py
│  ├─ test_bootstrap_buffering.py
│  ├─ test_resync.py
│  └─ test_compatibility.py
├─ store/
│  ├─ test_live_state.py
│  ├─ test_changes.py
│  ├─ test_watch_selector.py
│  ├─ test_wait_until.py
│  └─ test_close_and_failure.py
├─ integration/
│  ├─ conftest.py
│  ├─ test_end_to_end_tracking.py
│  ├─ test_desync_detection.py
│  ├─ test_resync_recovery.py
│  └─ test_change_ordering.py
├─ replay/
│  ├─ traces/
│  └─ test_replay_traces.py
└─ live/
   ├─ conftest.py
   └─ test_live_smoke.py
```

### Shared Fixtures

#### Snapshot Factory

A fixture creates minimal coherent snapshots for pure reducer/selector tests.

```python
@pytest.fixture
def snapshot_factory():
    def make(**overrides) -> NiriSnapshot: ...
    return make
```

#### Mock `niri-pypc` Bundle

For sync/store tests, provide a fake bundle with:
- canned command query responses
- a scripted event iterator
- controllable disconnect/error injection

This avoids re-testing `niri-pypc` transport details in unit suites.

### Required Test Categories

#### Reducer Tests

1. build initial snapshot from normalized bootstrap payload
2. add/update/remove flows per domain
3. focus movement and pointer updates
4. ordering updates
5. no-op handling
6. stale-on-unknown and fail-on-unknown behavior
7. stale-on-invariant and fail-on-invariant behavior

#### Selector Tests

1. direct lookups by id/name
2. relationship traversal
3. aggregate selectors
4. empty/missing cases
5. stability across unchanged revisions

#### Sync Tests

1. bootstrap closes the race by buffering and replaying events
2. bootstrap fails on buffer overflow
3. bootstrap fails on command error
4. strict compatibility mismatch rejects startup
5. successful resync publishes `RESYNCING` then `LIVE`
6. failed resync yields `STALE` or `FAILED` per policy/context

#### Store / Wait Tests

1. `current()` returns latest snapshot
2. `snapshot(wait_for_live=True)` waits correctly during resync
3. `changes()` yields ordered change sets
4. `watch_selector()` emits initial value and dedupes when configured
5. subscriber overflow follows configured mode
6. `wait_until()` and `wait_for_selector()` are event-driven, cancellable, and timeout correctly
7. close emits final terminal behavior predictably

#### Integration Tests

Use `niri-pypc` against a mock or controlled Niri-like session.

Required categories:
1. full bootstrap + live event tracking
2. transport loss -> stale/resync behavior
3. unknown event from inbound decode -> stale transition
4. revision ordering is monotonic and gap-free for published changes
5. manual `refresh()` produces a new coherent live snapshot

#### Replay Tests

1. recorded traces replay deterministically
2. regression traces protect previously fixed bugs
3. long event sequences converge consistently
4. expected selectors and health states match trace assertions

#### Live Tests

Gated by `NIRI_SOCKET` and skipped in CI by default.

Minimum required live checks:
1. bootstrap against a real compositor
2. observe at least one real event-driven change
3. manual refresh smoke test

### CI Gate Sequence

Required CI order:

```bash
uv sync --extra dev
pytest tests/reducers -q
pytest tests/selectors -q
pytest tests/sync tests/store tests/integration -q
pytest tests/replay -q
ruff check .
ruff format --check .
ty check .
```

Optional environment-dependent gates:
- `pytest tests/live -q`

### Definition of Done for `niri-state`

Implementation is complete only when all are true:
1. first bootstrap produces a coherent live snapshot
2. event reduction is deterministic and invariant-checked
3. stale and resync behavior are explicit and test-covered
4. snapshots are immutable and revisioned
5. selectors and waits are pure, event-driven, and predictable
6. replay traces validate regression stability

---

*End of specification.*
