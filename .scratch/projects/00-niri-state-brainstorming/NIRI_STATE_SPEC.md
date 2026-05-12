# NIRI_STATE_SPEC

Implementation specification for `niri-state`.

This document translates the refined `niri-state` concept into precise, implementable contracts. It is written against the current attached `niri-pypc` implementation as canonical truth, not against aspirational or older protocol-client drafts.

`niri-state` is a downstream state engine. It depends on `niri-pypc` for typed protocol models, request/response handling, event decoding, socket lifecycle, and bundle management. It owns bootstrap, response normalization, event reduction, immutable snapshots, selectors, waiting, observation, health, desync handling, and resync.

---

## Table of Contents

1. [Notation and Conventions](#1-notation-and-conventions)
2. [Package Structure and Module Map](#2-package-structure-and-module-map)
3. [Core Identifier Types and Compatibility Metadata](#3-core-identifier-types-and-compatibility-metadata)
4. [State Model Specification](#4-state-model-specification)
5. [Live, Refresh-Backed, and Query-Only Domains](#5-live-refresh-backed-and-query-only-domains)
6. [Health, Lifecycle, and Revision Semantics](#6-health-lifecycle-and-revision-semantics)
7. [Change Model Specification](#7-change-model-specification)
8. [Config Module Specification](#8-config-module-specification)
9. [Error Module Specification](#9-error-module-specification)
10. [Bootstrap Payload and Response Normalization](#10-bootstrap-payload-and-response-normalization)
11. [Reducer Module Specification](#11-reducer-module-specification)
12. [Invariant Module Specification](#12-invariant-module-specification)
13. [Selector Module Specification](#13-selector-module-specification)
14. [Bootstrap and Synchronization Specification](#14-bootstrap-and-synchronization-specification)
15. [Resync Coordination Specification](#15-resync-coordination-specification)
16. [Store Module Specification](#16-store-module-specification)
17. [Observation and Waiting Specification](#17-observation-and-waiting-specification)
18. [Public Package API Specification](#18-public-package-api-specification)
19. [Replay Trace Specification](#19-replay-trace-specification)
20. [Devenv Integration Specification](#20-devenv-integration-specification)
21. [Test Specification](#21-test-specification)
22. [Definition of Done](#22-definition-of-done)

---

## 1. Notation and Conventions

### Naming

- Package name: `niri-state`
- Import root: `niri_state`
- Public class: `NiriState`
- All Python identifiers follow PEP 8.
- Public data models are hand-written Pydantic v2 `BaseModel` subclasses.
- Internal enums use `enum.StrEnum` where a string-valued enum is appropriate.
- Selectors are typed Python callables or simple functions; they are not classes unless stateful configuration is required.

### Python Version and Runtime

- Minimum Python version: **3.13**.
- Async runtime: **`asyncio` only**.
- Operating system support: Linux/Unix environments where `niri-pypc` can reach the Niri IPC Unix socket.
- No Windows support.

### Immutability Rule

All public snapshot, entity, change, diagnostics, and health models are immutable.

```python
from pydantic import BaseModel, ConfigDict


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
```

All public models in `niri-state` inherit from `FrozenModel` or use equivalent frozen configuration.

### Type Annotation Rules

- Use `from __future__ import annotations` in all modules.
- Use `T | None`, `list[T]`, `tuple[T, ...]`, and `dict[K, V]` forms.
- Public methods and functions require complete type annotations.
- Public Pydantic fields should prefer immutable collection types such as `tuple[...]`.

### Dependency Boundary Rule

`niri-state` depends on `niri-pypc`; the reverse dependency is forbidden.

`niri-state` may import:

- `niri_pypc.NiriConfig`
- `niri_pypc.BackpressureMode`
- `niri_pypc.NiriClient`
- `niri_pypc.NiriEventStream`
- `niri_pypc.NiriConnectionBundle`
- `niri_pypc` error classes
- generated protocol types from `niri_pypc.types`

`niri-state` must not reimplement socket transport, wire framing, or raw codec behavior.

### Canonical Dependency Rule

The attached current `niri-pypc` implementation is the canonical behavioral dependency. If old `niri-state` design text conflicts with the current `niri-pypc` code, update `niri-state` rather than assuming additional `niri-pypc` features exist.

---

## 2. Package Structure and Module Map

```text
src/niri_state/
├─ __init__.py                     # Public re-exports
├─ _version.py                     # Package version constant
├─ errors.py                       # State-specific error taxonomy
├─ config.py                       # Store, resync, watcher, and wait config
├─ models/
│  ├─ __init__.py                  # Re-exports all public state models
│  ├─ common.py                    # FrozenModel, id aliases, helper types
│  ├─ health.py                    # StoreHealth, compatibility metadata, diagnostics
│  ├─ entities.py                  # OutputState, WorkspaceState, WindowState
│  ├─ snapshot.py                  # NiriSnapshot, SnapshotIndexes
│  └─ change_set.py                # ChangeSet, ChangeDomain, ChangeCause
├─ reducers/
│  ├─ __init__.py
│  ├─ common.py                    # ReducerContext, ReductionResult, helpers
│  ├─ bootstrap.py                 # Bootstrap payload normalization and base build
│  ├─ root.py                      # apply_event / apply_bootstrap dispatch entrypoints
│  ├─ workspaces.py                # Workspace-related event reduction
│  ├─ windows.py                   # Window-related event reduction
│  ├─ focus.py                     # Focus pointer reduction
│  ├─ keyboard.py                  # Keyboard layout reduction
│  ├─ overview.py                  # Overview state reduction
│  └─ invariants.py                # Post-reduction invariant checks
├─ selectors/
│  ├─ __init__.py
│  ├─ outputs.py                   # Output selectors
│  ├─ workspaces.py                # Workspace selectors
│  ├─ windows.py                   # Window selectors
│  ├─ focus.py                     # Focus selectors
│  └─ aggregates.py                # Cross-domain aggregate selectors
├─ sync/
│  ├─ __init__.py
│  ├─ bootstrap.py                 # Coordinated initial sync over niri-pypc
│  ├─ resync.py                    # Resync coordinator implementation
│  └─ policies.py                  # Policy helpers for stale/fail/resync decisions
└─ store/
   ├─ __init__.py
   ├─ live_state.py                # NiriState public class
   ├─ broadcaster.py               # Change/watch subscriber fan-out
   └─ waiters.py                   # wait_until / wait_for_selector primitives
```

### Dependency DAG

```text
store.live_state   -> sync.bootstrap, sync.resync, reducers.root, selectors, models, errors, config, niri-pypc
store.broadcaster  -> models, errors, config
store.waiters      -> selectors, models, errors, config
sync.bootstrap     -> reducers.bootstrap, reducers.root, models, errors, config, niri-pypc
sync.resync        -> sync.bootstrap, reducers.root, models, errors, config, niri-pypc
reducers.root      -> reducers.*, models, errors, niri-pypc.types
reducers.*         -> models, errors, niri-pypc.types
selectors.*        -> models
models.*           -> internal model helpers only
errors             -> no internal deps
config             -> niri-pypc config types only
```

### Architectural Rules

1. Reducers are pure: no I/O, sleeping, IPC, socket access, or command issuance.
2. Selectors are pure: no I/O and no mutation.
3. Sync code owns bootstrap races, buffering, and bundle lifecycle.
4. Store code owns publication, observers, waiters, and lifecycle transitions.
5. Public APIs never expose mutable internal state.
6. Public state must distinguish live, refresh-backed, and query-only domains.

---

## 3. Core Identifier Types and Compatibility Metadata

### Identifier Aliases

```python
OutputName = str
WorkspaceId = int
WindowId = int
Revision = int
```

Rules:

1. Preserve protocol identifiers instead of inventing new key spaces.
2. `OutputName` is the stable key for outputs.
3. `WorkspaceId` and `WindowId` are protocol identifiers.
4. If a future `niri-pypc` pin changes identifier shape, update these aliases deliberately.
5. Public snapshots must not mix protocol identifiers with synthetic identifiers.

### Compatibility Metadata

`niri-state` is not the protocol authority, but it surfaces compatibility metadata useful to state consumers.

```python
import enum


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
3. `upstream_version` may be read from `niri_pypc.types.generated._metadata` if available.
4. `compositor_version` is populated only if a runtime version query succeeds.
5. If no version check is performed, `status=UNCHECKED`.
6. `niri-state` must not assume `niri-pypc` has already enforced runtime compatibility.
7. Strict compatibility rejection, if enabled by `niri-state`, raises before returning a live store.

---

## 4. State Model Specification

### Common Base

```python
from pydantic import BaseModel, ConfigDict


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
```

### Entity Models

The public state model uses normalized entities plus selected relationship fields. Each entity carries the corresponding raw protocol model from `niri-pypc` when that raw model is the authoritative source for wire-derived fields.

#### `OutputState`

```python
from niri_pypc.types import Output


class OutputState(FrozenModel):
    name: OutputName
    raw: Output
    workspace_ids: tuple[WorkspaceId, ...] = ()
    focused_workspace_id: WorkspaceId | None = None
    is_live_config_current: bool = False
```

Rules:

1. `name` is equal to `raw.name`.
2. `workspace_ids` is explicit and immutable.
3. `focused_workspace_id`, if set, must appear in `workspace_ids`.
4. `is_live_config_current=False` means the output's raw configuration is bootstrap/refresh-backed, not event-reduced live truth.
5. Do not expose `is_active` on outputs unless the exact protocol meaning is defined from observed data.

#### `WorkspaceState`

```python
from niri_pypc.types import Workspace


class WorkspaceState(FrozenModel):
    id: WorkspaceId
    raw: Workspace
    output_name: OutputName | None = None
    active_window_id: WindowId | None = None
    is_active: bool = False
    is_focused: bool = False
```

Rules:

1. `id` is equal to the workspace id from the protocol model.
2. `output_name` is `None` only when the protocol does not associate the workspace with an output.
3. `active_window_id`, if set, must reference an existing window after invariant validation.
4. `is_active` and `is_focused` are preserved as separate concepts.
5. Multiple workspaces may be active across outputs if the observed protocol data reports that state.
6. Do not add `is_visible` unless a strict derivation rule is documented and tested.

#### `WindowState`

```python
from niri_pypc.types import Window


class WindowState(FrozenModel):
    id: WindowId
    raw: Window
    workspace_id: WorkspaceId | None = None
    is_focused: bool = False
```

Rules:

1. `id` is equal to the window id from the protocol model.
2. `workspace_id` is a normalized relationship field derived from observed data.
3. `is_focused=True` must agree with `NiriSnapshot.focused_window_id`.
4. Do not add `output_name` unless it is derived through workspace membership.
5. Do not add `is_visible` unless a strict derivation rule is documented and tested.

#### `KeyboardLayoutsState`

The keyboard layout domain must preserve the full protocol model rather than collapsing it to a single string.

```python
from niri_pypc.types import KeyboardLayouts


class KeyboardLayoutsState(FrozenModel):
    raw: KeyboardLayouts
    current_idx: int | None = None
    current_name: str | None = None
```

Rules:

1. `raw` carries the full protocol payload.
2. `current_idx` is derived from `raw` when available or from layout switch events.
3. `current_name` is derived only when `current_idx` and the names/list payload permit it.
4. Absence of `current_name` is valid if the protocol data is insufficient.

#### `OverviewState`

```python
from niri_pypc.types import Overview


class OverviewState(FrozenModel):
    raw: Overview | None = None
    is_open: bool | None = None
```

Rules:

1. `raw` is populated from bootstrap query results when available.
2. `is_open` is updated by overview open/close events.
3. `None` means unknown, not closed.

### Snapshot Diagnostics

```python
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

### Snapshot Indexes

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
4. Ordering must come from protocol ordering where available; otherwise it must be deterministic and documented.

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

    focused_output_name: OutputName | None = None
    focused_workspace_id: WorkspaceId | None = None
    focused_window_id: WindowId | None = None
    active_workspace_ids_by_output: dict[OutputName, tuple[WorkspaceId, ...]] = {}

    keyboard_layouts: KeyboardLayoutsState | None = None
    overview: OverviewState | None = None

    last_good_revision: Revision | None = None
    diagnostics: SnapshotDiagnostics = SnapshotDiagnostics()
```

Rules:

1. `revision` is monotonically increasing for every published snapshot.
2. `bootstrapped=True` iff bootstrap completed successfully at least once for this store lifetime.
3. `last_good_revision` is:
   - equal to `revision` for `LIVE` snapshots,
   - equal to the most recent coherent `LIVE` revision for `STALE`, `RESYNCING`, `FAILED`, or `CLOSED` snapshots,
   - `None` only before any coherent snapshot has ever been published.
4. `focused_output_name`, if set, must exist in `outputs_by_name`.
5. `focused_workspace_id`, if set, must exist in `workspaces_by_id`.
6. `focused_window_id`, if set, must exist in `windows_by_id`.
7. `active_workspace_ids_by_output` keys must exist in `outputs_by_name`.
8. Every workspace id in `active_workspace_ids_by_output` must exist in `workspaces_by_id`.
9. The snapshot must not expose a singular global `active_workspace_id`.
10. The snapshot must not collapse keyboard layouts to one string.

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

This placeholder is internal-only unless explicitly documented otherwise. The default public behavior is that `NiriState.connect()` returns only after a coherent first snapshot is available.

---

## 5. Live, Refresh-Backed, and Query-Only Domains

`niri-state` must be explicit about domain freshness.

### Domain Freshness Kinds

```python
class DomainFreshnessKind(enum.StrEnum):
    EVENT_REDUCED_LIVE = "event_reduced_live"
    REFRESH_BACKED = "refresh_backed"
    QUERY_ONLY = "query_only"
    UNSUPPORTED = "unsupported"
```

### Required Domain Classification

| Domain | Classification | Notes |
|---|---|---|
| windows | event-reduced live | Supported by current window events. |
| workspaces | event-reduced live | Supported by current workspace events. |
| focus | event-reduced live | Supported by focused window/output/workspace-related events and queries. |
| keyboard layouts | event-reduced live | Bootstrap from query; update from keyboard layout events. |
| overview | event-reduced live | Bootstrap from query; update from overview events. |
| outputs | refresh-backed | Bootstrap/queryable; no dedicated direct output-change event in current event surface. |
| layers | query-only or unsupported | Queryable, but not event-reduced live in current event surface. |

### Rules

1. Only event-backed domains may be described as fully live.
2. Refresh-backed domains may be present in snapshots, but their raw fields may become stale until refresh.
3. Query-only domains are not part of the default coherent live-state guarantee.
4. Selectors must not hide this distinction when freshness matters.
5. Documentation must state which domains are live for the current `niri-pypc` dependency.

---

## 6. Health, Lifecycle, and Revision Semantics

### `StoreHealth`

```python
class StoreHealth(enum.StrEnum):
    BOOTSTRAPPING = "bootstrapping"
    LIVE = "live"
    STALE = "stale"
    RESYNCING = "resyncing"
    CLOSED = "closed"
    FAILED = "failed"
```

### Health Semantics

- `BOOTSTRAPPING`: initial sync is in progress; no complete public live state exists.
- `LIVE`: event-reduced domains are coherent and advancing normally.
- `STALE`: last snapshot is readable, but correctness is no longer guaranteed.
- `RESYNCING`: a fresh bootstrap/refresh is in progress.
- `CLOSED`: the store was intentionally closed.
- `FAILED`: a terminal unrecoverable error occurred.

### Valid Health Transitions

```text
BOOTSTRAPPING -> LIVE
BOOTSTRAPPING -> FAILED
BOOTSTRAPPING -> CLOSED

LIVE -> LIVE
LIVE -> STALE
LIVE -> RESYNCING
LIVE -> CLOSED
LIVE -> FAILED

STALE -> STALE
STALE -> RESYNCING
STALE -> CLOSED
STALE -> FAILED

RESYNCING -> LIVE
RESYNCING -> STALE
RESYNCING -> CLOSED
RESYNCING -> FAILED

FAILED -> CLOSED
```

Invalid transitions raise `StateLifecycleError` internally and are treated as implementation bugs.

### Revision Rules

1. Every published snapshot increments the revision by exactly 1.
2. A health-only transition still publishes a new revision.
3. A pure no-op event publishes no new revision unless diagnostics or health changed.
4. `ChangeSet.old_revision` and `ChangeSet.new_revision` must reflect the actual published transition.
5. Revisions are store-local and restart after a fresh `NiriState.connect()`.

### Coherence Rule

A public snapshot is coherent if and only if:

1. it represents a complete state after reducer application,
2. invariant validation has either passed or the store has transitioned to a health state that explicitly permits publication,
3. no partial reducer mutation is visible,
4. all published relationship pointers satisfy documented invariants for the current health state.

---

## 7. Change Model Specification

### `ChangeCause`

```python
class ChangeCause(enum.StrEnum):
    BOOTSTRAP = "bootstrap"
    EVENT = "event"
    MANUAL_REFRESH = "manual_refresh"
    MANUAL_RESYNC = "manual_resync"
    AUTO_RESYNC = "auto_resync"
    STALE_TRANSITION = "stale_transition"
    CLOSE = "close"
    FAILURE = "failure"
```

### `ChangeDomain`

```python
class ChangeDomain(enum.StrEnum):
    OUTPUTS = "outputs"
    WORKSPACES = "workspaces"
    WINDOWS = "windows"
    FOCUS = "focus"
    KEYBOARD = "keyboard"
    OVERVIEW = "overview"
    HEALTH = "health"
    METADATA = "metadata"
```

`LAYERS` is intentionally omitted from the default domain enum because layers are not event-reduced live in the current `niri-pypc` surface. If an optional layer module is introduced, it must clearly identify itself as query-only or refresh-backed.

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
3. `domains` must be deduplicated and sorted in stable enum order before publication.
4. `event_type` is the concrete event variant class name for event-driven changes.
5. `details` is for small structured diagnostics only and must remain JSON-serializable.
6. Every published snapshot has exactly one corresponding `ChangeSet`.
7. Subscribers receive changes in ascending `new_revision` order.

---

## 8. Config Module Specification

### Config Types

```python
from __future__ import annotations

import enum
from pydantic import BaseModel, ConfigDict, Field
from niri_pypc import NiriConfig


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
```

### `NiriStateConfig`

```python
class NiriStateConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

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
```

### Config Semantics

1. `pypc` contains transport/socket/timeouts/event queue settings owned by `niri-pypc`.
2. `correctness_mode=STRICT` requires upstream event backpressure to be fail-fast.
3. `correctness_mode=BEST_EFFORT` may allow drop-oldest upstream backpressure but must not claim full correctness if an event is dropped.
4. `bootstrap_timeout` bounds the full initial synchronization operation.
5. `bootstrap_event_buffer_capacity` bounds the local `niri-state` bootstrap replay buffer.
6. `changes_queue_capacity` applies per change subscriber.
7. `watcher_queue_capacity` applies per selector watch subscriber.
8. `overflow_mode` controls subscriber queue overflow, not upstream event stream overflow.
9. `resync_policy=AUTO` permits automatic resync attempts on configured desync triggers.
10. `include_query_only_layers=True` enables optional layer query support but does not make layers live.
11. `perform_version_query=True` asks `niri-state` to issue a version request during bootstrap for metadata.
12. `strict_version_match=True` makes version mismatch a bootstrap failure when a check is performed.

### Upstream Backpressure Normalization

In strict correctness mode, `niri-state` must ensure the `NiriConfig` passed to `niri-pypc` uses fail-fast event backpressure when the current `niri-pypc` API exposes that setting.

Rules:

1. If `config.correctness_mode == STRICT` and `config.pypc.backpressure_mode != FAIL_FAST`, `NiriState.connect()` must either:
   - create a copied `NiriConfig` with fail-fast backpressure, or
   - raise `StateConfigError` if copying is impossible.
2. The store must record the effective upstream backpressure mode in diagnostics.
3. Drop-oldest upstream behavior is not correctness-preserving for a state store.

### Queue Overflow Rules

For `niri-state` subscriber queues:

- `DROP_OLDEST`: evict the oldest queued item, enqueue the new item, and record a warning/diagnostic.
- `FAIL_FAST`: terminate the specific subscription with `WatchOverflowError`.

For the local bootstrap event buffer:

- overflow is always a bootstrap failure, because the race window can no longer be proven closed.

For the upstream `niri-pypc` event queue:

- fail-fast overflow is a desync trigger;
- drop-oldest overflow is incompatible with strict correctness mode.

---

## 9. Error Module Specification

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


class StateConfigError(NiriStateError):
    """Invalid niri-state configuration."""


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
4. Wrapped `niri-pypc` exceptions must use Python exception chaining.
5. `SelectorWaitError` should be catchable as `TimeoutError` when timeouts are the root cause.
6. `DesyncError` is used for freshness/correctness breakage, not merely any reducer exception.

### Mapping Rules from `niri-pypc`

| Source error | Phase | `niri-state` mapping |
|---|---|---|
| `ConfigError` | connect/bootstrap | `BootstrapError` or `StateConfigError` |
| `TransportError` | bootstrap | `BootstrapError` |
| `TransportError` | live event loop | stale transition or `DesyncError` |
| `NiriTimeoutError` | bootstrap | `BootstrapError` |
| `NiriTimeoutError` | waits | `SelectorWaitError` |
| `RemoteError` | bootstrap query | `BootstrapError` |
| `DecodeError` | bootstrap/live | `BootstrapError` or stale transition depending on phase |
| `LifecycleError` | store lifecycle | `StateLifecycleError` |

---

## 10. Bootstrap Payload and Response Normalization

### Purpose

The current `niri-pypc` client returns typed response wrapper models. `niri-state` must normalize those wrappers into reducer-friendly bootstrap payloads.

### `BootstrapPayload`

```python
from niri_pypc.types import Output, Workspace, Window, KeyboardLayouts, Overview


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
```

### Response Normalization Contract

```python
def normalize_bootstrap_responses(
    responses: BootstrapResponses,
    *,
    query_plan_name: str,
    compatibility: CompatibilityInfo,
    include_query_only_layers: bool = False,
) -> BootstrapPayload: ...
```

`BootstrapResponses` may be a frozen internal model carrying each typed response returned by `niri-pypc`.

Rules:

1. Match on concrete response variant classes from `niri_pypc.types`.
2. Extract payloads explicitly.
3. Do not pass raw response wrappers into reducers.
4. Treat missing required response variants as `BootstrapError`.
5. Preserve raw query-only layer payloads only if `include_query_only_layers=True`.
6. Unknown reply sentinels during bootstrap are bootstrap failures by default.

### Default Bootstrap Query Plan

The default query plan should include:

- `OutputsRequest`
- `WorkspacesRequest`
- `WindowsRequest`
- `FocusedOutputRequest`
- `FocusedWindowRequest`
- `KeyboardLayoutsRequest`
- `OverviewStateRequest`

Optional:

- `LayersRequest`, only when `include_query_only_layers=True`
- `VersionRequest`, only when `perform_version_query=True`

Rules:

1. The query plan is explicit and named.
2. Query order must be deterministic.
3. Query results must be normalized before reducer entry.
4. Adding/removing default query surfaces is a documented behavioral change.

---

## 11. Reducer Module Specification

### Reducer Principles

Reducers are pure functions:

- input: snapshot and typed protocol input,
- output: new snapshot candidate and metadata,
- no side effects,
- no I/O,
- no hidden mutation.

### Reducer Support Types

```python
from typing import Any
from pydantic import Field


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

### Bootstrap Entry Point

```python
def build_initial_snapshot(
    payload: BootstrapPayload,
    *,
    revision: Revision,
    context: ReducerContext,
) -> ReductionResult:
    """Build the first coherent snapshot from normalized bootstrap query results."""
```

Rules:

1. Does not replay buffered live events.
2. Produces a coherent base snapshot candidate.
3. Builds normalized mappings and indexes.
4. Preserves raw `niri-pypc` model payloads in entity state.
5. Marks output raw configuration as refresh-backed, not fully event-live.

### Event Entry Point

```python
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

- concrete event variant model instances from `niri_pypc.types`,
- explicit unknown sentinel models from `niri-pypc` inbound decoding.

Rules:

1. Dispatch by concrete event variant type, not raw dict keys.
2. Unknown sentinel handling follows `UnknownEventPolicy`.
3. Unsupported but known event variants must be explicit.
4. If an event is redundant under current state, return `applied=False`.
5. Event reducers must not update query-only layers.

### Required Event Reducer Coverage

Reducers must cover the current event-backed domains exposed by the current `niri-pypc` event surface, including:

- window opened/changed,
- window closed,
- windows changed,
- window focus changed,
- window urgency changed,
- workspace activated,
- workspace active window changed,
- workspace urgency changed,
- workspaces changed,
- keyboard layout switched,
- keyboard layouts changed,
- overview opened,
- overview closed,
- config loaded.

If an event variant exists in the current `niri-pypc` type surface but is intentionally not state-affecting, the root reducer must document and no-op it explicitly.

### Unknown / Unsupported Event Handling

Default behavior with `unknown_event_policy=STALE`:

- publish a new snapshot with:
  - incremented revision,
  - unchanged entity state,
  - `health=STALE`,
  - diagnostics recording the event,
  - `ChangeCause.STALE_TRANSITION`,
  - `ChangeDomain.HEALTH` and `ChangeDomain.METADATA`.

With `unknown_event_policy=FAIL`:

- raise `DesyncError`.

### No-Op Handling

A reducer may return `applied=False` only when:

1. the event is semantically redundant,
2. health and diagnostics remain unchanged,
3. no invariant consequences exist.

---

## 12. Invariant Module Specification

### `check_snapshot_invariants`

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
6. Every `output.workspace_ids` entry exists in `workspaces_by_id`.
7. Every `output.focused_workspace_id`, when non-`None`, exists in `workspaces_by_id`.
8. Every `workspace.active_window_id`, when non-`None`, exists in `windows_by_id`.

#### Pointer Invariants

9. `focused_output_name`, if set, exists in `outputs_by_name`.
10. `focused_workspace_id`, if set, exists in `workspaces_by_id`.
11. `focused_window_id`, if set, exists in `windows_by_id`.
12. If `focused_window_id` is set, exactly one window has `is_focused=True` and it is that window.
13. If `focused_workspace_id` is set, the referenced workspace has `is_focused=True`.

#### Active Workspace Invariants

14. Every key in `active_workspace_ids_by_output` exists in `outputs_by_name`.
15. Every workspace id in `active_workspace_ids_by_output` exists in `workspaces_by_id`.
16. A workspace listed as active for an output should either have matching `output_name` or the invariant checker should flag an inconsistency.
17. Multiple active workspaces are permitted globally if they are associated with different outputs or if the protocol reports them.

#### Ordering Invariants

18. `indexes.output_order` contains each output exactly once.
19. `indexes.workspace_order` contains each workspace exactly once.
20. `indexes.window_order` contains each window exactly once.

### Enforcement Policy

After each non-no-op reducer result:

1. run `check_snapshot_invariants()`,
2. if violations are empty, continue,
3. if violations exist and `invariant_failure_policy=STALE`, convert the result into a stale snapshot publication,
4. if violations exist and `invariant_failure_policy=FAIL`, raise `InvariantError`.

---

## 13. Selector Module Specification

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
3. Prefer `None` or empty tuple for absence.
4. Selectors are deterministic and side-effect free.
5. Selectors must not perform refreshes or IPC.
6. Selectors must not conceal domain freshness when freshness matters.

### Output Selectors

```python
def output_by_name(snapshot: NiriSnapshot, name: OutputName) -> OutputState | None: ...
def outputs(snapshot: NiriSnapshot) -> tuple[OutputState, ...]: ...
def focused_output(snapshot: NiriSnapshot) -> OutputState | None: ...
def workspaces_on_output(snapshot: NiriSnapshot, name: OutputName) -> tuple[WorkspaceState, ...]: ...
def output_config_is_live_current(snapshot: NiriSnapshot, name: OutputName) -> bool: ...
```

### Workspace Selectors

```python
def workspace_by_id(snapshot: NiriSnapshot, workspace_id: WorkspaceId) -> WorkspaceState | None: ...
def workspaces(snapshot: NiriSnapshot) -> tuple[WorkspaceState, ...]: ...
def focused_workspace(snapshot: NiriSnapshot) -> WorkspaceState | None: ...
def active_workspaces_on_output(snapshot: NiriSnapshot, name: OutputName) -> tuple[WorkspaceState, ...]: ...
def windows_on_workspace(snapshot: NiriSnapshot, workspace_id: WorkspaceId) -> tuple[WindowState, ...]: ...
```

Do not provide a default singular `active_workspace(snapshot)` selector unless its semantics are explicitly documented as a convenience over `focused_workspace` or over a specific output.

### Window Selectors

```python
def window_by_id(snapshot: NiriSnapshot, window_id: WindowId) -> WindowState | None: ...
def windows(snapshot: NiriSnapshot) -> tuple[WindowState, ...]: ...
def focused_window(snapshot: NiriSnapshot) -> WindowState | None: ...
def workspace_for_window(snapshot: NiriSnapshot, window_id: WindowId) -> WorkspaceState | None: ...
```

`visible_windows()` is not part of the required v1 selector surface unless visibility is precisely defined and tested.

### Focus Selectors

```python
def focused_window_id(snapshot: NiriSnapshot) -> WindowId | None: ...
def focused_workspace_id(snapshot: NiriSnapshot) -> WorkspaceId | None: ...
def focused_output_name(snapshot: NiriSnapshot) -> OutputName | None: ...
```

### Keyboard and Overview Selectors

```python
def keyboard_layouts(snapshot: NiriSnapshot) -> KeyboardLayoutsState | None: ...
def current_keyboard_layout_name(snapshot: NiriSnapshot) -> str | None: ...
def current_keyboard_layout_index(snapshot: NiriSnapshot) -> int | None: ...
def overview_is_open(snapshot: NiriSnapshot) -> bool | None: ...
```

### Aggregate Selectors

```python
def window_count(snapshot: NiriSnapshot) -> int: ...
def workspace_count(snapshot: NiriSnapshot) -> int: ...
def output_count(snapshot: NiriSnapshot) -> int: ...
def has_window(snapshot: NiriSnapshot, window_id: WindowId) -> bool: ...
def is_live(snapshot: NiriSnapshot) -> bool: ...
def is_stale(snapshot: NiriSnapshot) -> bool: ...
```

### Selector Stability Rules

1. Given equal snapshots, selector outputs must compare equal.
2. Ordering selectors must use snapshot indexes.
3. `watch_selector()` deduplication uses normal Python equality on selector results.

---

## 14. Bootstrap and Synchronization Specification

### Sync Goal

Bootstrap must produce a first coherent `LIVE` snapshot while closing the race between initial command queries and incoming live events.

### `BootstrapArtifacts`

```python
class BootstrapArtifacts(FrozenModel):
    payload: BootstrapPayload
    base_result: ReductionResult
    replay_results: tuple[ReductionResult, ...] = ()
    first_live_snapshot: NiriSnapshot
    replayed_event_count: int = 0
```

### `run_bootstrap`

```python
async def run_bootstrap(
    bundle: NiriConnectionBundle,
    config: NiriStateConfig,
) -> BootstrapArtifacts:
    """Run coordinated bootstrap and return the first live snapshot artifacts."""
```

### Required Bootstrap Sequence

1. Normalize config and enforce correctness-mode constraints.
2. Open a `NiriConnectionBundle` using `niri-pypc`.
3. Confirm the event stream is connected.
4. Start buffering incoming typed events into an internal FIFO buffer.
5. Optionally perform a version query and build compatibility metadata.
6. Execute the explicit initial query suite using the command client.
7. Normalize typed response wrappers into a `BootstrapPayload`.
8. Build a base snapshot using `reducers.bootstrap.build_initial_snapshot()`.
9. Replay buffered events in arrival order using `reducers.root.apply_event()`.
10. Run invariant checks after each applied event.
11. Publish the first `LIVE` snapshot only after replay succeeds.

### Event Buffering Rules

1. The local bootstrap event buffer is FIFO.
2. Each buffered item is a decoded typed event variant from `niri-pypc`, not raw JSON.
3. Buffer overflow causes bootstrap failure.
4. Buffered events are replayed exactly once.
5. If replay fails under configured policy, bootstrap fails or transitions stale according to policy before public return.

### Upstream Queue Correctness Rule

The local bootstrap buffer is not the only queue. The upstream `niri-pypc` event stream has its own bounded queue.

Rules:

1. In strict correctness mode, upstream queue overflow must surface as failure/stale, never as silent loss.
2. In strict correctness mode, `niri-state` must configure or require fail-fast upstream backpressure.
3. If upstream drop-oldest is used, the store is best-effort and must not claim strict coherent live correctness.

### Bootstrap Failure Rules

Any of the following raise `BootstrapError`:

- command request failure,
- response normalization failure,
- required query response missing,
- local bootstrap event buffer overflow,
- upstream fail-fast stream overflow during bootstrap,
- event replay reduction failure under fail policy,
- transport loss during bootstrap,
- timeout of the overall bootstrap operation,
- strict compatibility mismatch.

If bootstrap fails, `NiriState.connect()` does not return a usable live store.

---

## 15. Resync Coordination Specification

### `ResyncCoordinator`

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
5. On success, resync publishes a new `LIVE` snapshot derived from fresh bootstrap.
6. On failure:
   - if the store has a coherent last-known-good snapshot, publish `STALE`,
   - otherwise publish `FAILED`.

### Resync Triggers

Required trigger set:

- explicit manual refresh/resync call,
- transport loss in live event loop,
- upstream fail-fast backpressure overflow,
- unknown inbound event when stale-on-unknown policy is active,
- unsupported known event when it may affect state,
- invariant failure when stale-on-invariant policy is active.

### Auto-Resync Rules

With `resync_policy=AUTO`:

1. the store automatically schedules resync after a stale-causing trigger,
2. automatic attempts stop after `max_consecutive_resync_failures`,
3. exceeding that threshold transitions the store to `FAILED`.

With `resync_policy=MANUAL`:

1. the store transitions to `STALE` and remains readable,
2. no automatic attempt occurs,
3. callers may invoke `await state.refresh()` explicitly.

---

## 16. Store Module Specification

### Public Class: `NiriState`

```python
from __future__ import annotations

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

- latest published snapshot,
- change broadcaster,
- selector watch subscriptions,
- active `niri-pypc` bundle,
- background event-consumer task,
- optional resync task,
- lifecycle locks.

### Connect Flow

`NiriState.connect()` performs:

1. config normalization,
2. correctness-mode validation,
3. initial bundle open via `niri-pypc`,
4. bootstrap run,
5. first live snapshot publication,
6. start of the live event-consumer task,
7. return of a usable store instance.

If any step fails, connect raises and no half-live object is returned.

### Event Consumer Task

The live store runs one background event-consumer task.

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
4. Subscribers observe the same published revision order.
5. Any event-stream exception is converted to a stale/fail/resync path according to policy.

### Snapshot Publication

Publication responsibilities:

1. replace the current snapshot atomically,
2. update internal revision pointer,
3. fan out `ChangeSet` to subscribers,
4. notify waiters/selectors,
5. record diagnostics if present.

### Close Semantics

`close()` must:

1. be idempotent,
2. cancel or settle the event-consumer task,
3. close the underlying `niri-pypc` bundle,
4. publish a final `CLOSED` snapshot if a store had been live/readable,
5. complete change/watch iterators cleanly after final publication,
6. reject new `refresh()` calls and new subscriptions after close starts.

---

## 17. Observation and Waiting Specification

### Broadcaster Model

The broadcaster manages independent subscriber queues for:

- raw `ChangeSet` subscribers,
- selector-derived value subscribers.

### Change Subscriber Rules

1. Every `changes()` call allocates a per-subscriber queue.
2. Each subscriber queue has capacity `changes_queue_capacity`.
3. Overflow behavior follows `StoreOverflowMode`.
4. Closing the store terminates all subscriptions after final publication.

### `wait_until`

Required behavior:

1. Evaluate the predicate against the current snapshot first.
2. If already satisfied, return immediately.
3. Otherwise subscribe to changes and re-evaluate after each published snapshot.
4. On timeout, raise `SelectorWaitError`.
5. On stale/failed/closed health:
   - `REQUIRE_LIVE`: fail with `SelectorWaitError`,
   - `ALLOW_STALE`: continue using the last published snapshot until timeout/close/failure semantics say otherwise.

### `wait_for_selector`

Required behavior:

1. Compute the selector on the current snapshot.
2. If a predicate is provided and already satisfied, return immediately.
3. If no predicate is provided, wait for the next distinct selector value.
4. Recompute selector values after each published snapshot.
5. Timeouts raise `SelectorWaitError`.

### `watch_selector`

Required behavior:

1. Selector values are computed from coherent snapshots only.
2. If `emit_initial=True`, yield the selector result from the current snapshot first.
3. If `dedupe=True`, suppress consecutive equal values.
4. A selector exception terminates only that subscription.
5. Subscriber queue overflow follows `StoreOverflowMode`.

---

## 18. Public Package API Specification

### `src/niri_state/__init__.py`

```python
"""niri-state: live observed compositor state built on top of niri-pypc."""

from niri_state._version import __version__
from niri_state.config import (
    NiriStateConfig,
    CorrectnessMode,
    ResyncPolicy,
    StoreOverflowMode,
    UnknownEventPolicy,
    InvariantFailurePolicy,
    WaitHealthPolicy,
)
from niri_state.errors import (
    NiriStateError,
    StateConfigError,
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
from niri_state.models import *
from niri_state import selectors
```

### Import Conventions for Users

```python
from niri_state import NiriState, NiriStateConfig, selectors
from niri_state.models import NiriSnapshot, ChangeSet, StoreHealth
from niri_state.errors import SelectorWaitError
```

### Public Boundary Rules

1. Public consumers interact through `NiriState`, public models, and selectors.
2. Reducers, sync helpers, and broadcaster internals are not public API.
3. `niri-state` may expose `selectors` as a package namespace.
4. Raw `niri-pypc` model payloads may appear inside public state entities, but raw transport/client objects do not.

---

## 19. Replay Trace Specification

### Purpose

Replay traces provide deterministic regression inputs for reducer and convergence testing.

### File Format

Preferred format: JSON Lines (`.jsonl`).

Each line is one record with a `kind` field.

Supported record kinds:

1. `bootstrap_payload`
2. `event`
3. `expect_revision`
4. `expect_health`
5. `expect_selector`

Example:

```json
{"kind":"bootstrap_payload","data":{}}
{"kind":"event","data":{"WorkspaceActivated":{"id":1,"focused":true}}}
{"kind":"expect_revision","value":2}
{"kind":"expect_health","value":"live"}
{"kind":"expect_selector","selector":"focused_workspace_id","value":1}
```

### Trace Rules

1. Bootstrap payload records use the normalized `BootstrapPayload` schema.
2. Event records may use externally-tagged event JSON converted through `niri-pypc` generated event models.
3. Replay tests must prove deterministic revision history.
4. Regression traces should be minimal and named for the scenario they cover.

### Replay Engine Contract

```python
def replay_trace(path: Path) -> tuple[NiriSnapshot, list[ChangeSet]]: ...
```

This helper:

1. builds the initial snapshot from the trace payload,
2. applies events in order through the same reducers as the live store,
3. returns the final snapshot and all produced changes.

---

## 20. Devenv Integration Specification

### `devenv.nix` Additions

`niri-state` has no schema export pipeline of its own. Its environment must include:

- Python 3.13,
- `uv`,
- test/lint/typecheck tooling,
- the compatible `niri-pypc` dependency.

Example script surface:

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

---

## 21. Test Specification

### Test Directory Structure

```text
tests/
├─ conftest.py
├─ reducers/
│  ├─ test_bootstrap.py
│  ├─ test_workspaces.py
│  ├─ test_windows.py
│  ├─ test_focus.py
│  ├─ test_keyboard.py
│  ├─ test_overview.py
│  ├─ test_unknown_events.py
│  └─ test_invariants.py
├─ selectors/
│  ├─ test_outputs.py
│  ├─ test_workspaces.py
│  ├─ test_windows.py
│  ├─ test_focus.py
│  ├─ test_keyboard.py
│  └─ test_aggregates.py
├─ sync/
│  ├─ test_bootstrap.py
│  ├─ test_response_normalization.py
│  ├─ test_bootstrap_buffering.py
│  ├─ test_backpressure_contract.py
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

### Required Test Categories

#### Reducer Tests

1. build initial snapshot from normalized bootstrap payload,
2. add/update/remove flows per live domain,
3. focus movement and pointer updates,
4. keyboard layout transitions,
5. overview open/close transitions,
6. no-op handling,
7. stale-on-unknown and fail-on-unknown behavior,
8. stale-on-invariant and fail-on-invariant behavior.

#### Selector Tests

1. direct lookups by id/name,
2. relationship traversal,
3. aggregate selectors,
4. empty/missing cases,
5. stability across unchanged revisions,
6. focused vs active workspace semantics.

#### Sync Tests

1. response wrapper normalization,
2. bootstrap closes race by buffering and replaying events,
3. local bootstrap buffer overflow fails bootstrap,
4. strict mode enforces fail-fast upstream backpressure,
5. command error fails bootstrap,
6. unknown reply sentinel fails bootstrap,
7. successful resync publishes `RESYNCING` then `LIVE`,
8. failed resync yields `STALE` or `FAILED` per policy/context.

#### Store / Wait Tests

1. `current()` returns latest snapshot,
2. `snapshot(wait_for_live=True)` waits during resync,
3. `changes()` yields ordered change sets,
4. `watch_selector()` emits initial value and dedupes when configured,
5. subscriber overflow follows configured mode,
6. wait APIs are event-driven, cancellable, and timeout correctly,
7. close emits final terminal behavior predictably.

#### Integration Tests

Use `niri-pypc` against a mock or controlled Niri-like session.

Required categories:

1. full bootstrap + live event tracking,
2. transport loss -> stale/resync behavior,
3. unknown event -> stale transition,
4. fail-fast upstream overflow -> stale/resync behavior,
5. revision ordering is monotonic and gap-free for published changes,
6. manual `refresh()` produces a new coherent live snapshot.

#### Replay Tests

1. recorded traces replay deterministically,
2. regression traces protect previously fixed bugs,
3. long event sequences converge consistently,
4. expected selectors and health states match trace assertions.

#### Live Tests

Gated by `NIRI_SOCKET` and skipped in CI by default.

Minimum required live checks:

1. bootstrap against a real compositor,
2. observe at least one real event-driven change,
3. manual refresh smoke test.

### CI Gate Sequence

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

Optional environment-dependent gate:

```bash
pytest tests/live -q
```

---

## 22. Definition of Done

Implementation is complete only when all are true:

1. first bootstrap produces a coherent live snapshot,
2. response wrappers from `niri-pypc` are normalized explicitly,
3. strict correctness mode enforces fail-fast upstream event backpressure,
4. event reduction is deterministic and invariant-checked,
5. live, refresh-backed, and query-only domains are documented and tested,
6. snapshots are immutable and revisioned,
7. selectors and waits are pure, event-driven, and predictable,
8. stale and resync behavior are explicit and test-covered,
9. replay traces validate regression stability,
10. the dependency direction remains `niri-state -> niri-pypc` only.

---

*End of specification.*

