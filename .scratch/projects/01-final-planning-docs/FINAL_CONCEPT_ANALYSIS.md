# FINAL_CONCEPT_ANALYSIS

Architectural recommendations for `niri-state`, grounded in the actual `niri-pypc` dependency contracts, the finalized CONCEPT/SPEC, and critical evaluation of CONCEPT_RETHINK proposals.

## Table of Contents

1. Framing: What This Library Actually Is
2. Evaluation of CONCEPT_RETHINK Proposals
3. Recommended Architecture
4. Package Structure
5. Model Layer Design
6. Reducer Design
7. Bootstrap and Sync Design
8. Store and Publication Design
9. Selector Design
10. Wait/Watch Design
11. Error Design
12. Configuration Design
13. Testing Strategy
14. What to Defer
15. Design Principles Summary

---

## 1. Framing: What This Library Actually Is

Before evaluating architecture, ground the design in reality:

- `niri-state` tracks the observed state of a single Wayland compositor instance.
- The compositor has ~6 state domains: windows, workspaces, outputs, focus, keyboard layouts, overview.
- The event surface is 17 typed variants. The query surface is ~8 request types.
- The primary consumers are automation scripts, status bars, and compositor management tools.
- Bootstrap is fast (a handful of local Unix socket calls).
- Event volume is low (human-driven: window open/close, workspace switch, focus change).
- The entire state fits comfortably in memory many times over.

This context matters because it sets the complexity budget. `niri-state` is a focused state tracker for a desktop compositor, not a distributed event store, a database, or a multi-tenant platform. Every architectural choice should be evaluated against this reality.

---

## 2. Evaluation of CONCEPT_RETHINK Proposals

### 2.1 Core/Runtime Split — Defer, Maintain Internal Boundary

**Proposal:** Ship `niri-state-core` (pure domain) and `niri-state-runtime` (async/IO) as separate packages.

**Assessment:** The conceptual separation is sound, but splitting into two packages now creates coordination overhead (two release cycles, cross-package version compatibility, import path complexity) without proportional benefit. The pure domain core is small — maybe 5-8 modules. The payoff of separate packages is real only when external teams need to embed the core in custom runtimes, which is not a current need.

**Recommendation:** Ship as one package (`niri-state`). Enforce the core/runtime boundary internally through module layout and import discipline. The directory structure should make the boundary obvious: `_core/` for pure domain logic, `_runtime/` for async/IO orchestration. If the need for a separate core package materializes later, extraction is straightforward because the boundary already exists in code.

### 2.2 Event-Sourced-First / Append-Only Log — No

**Proposal:** Keep an append-only internal domain event log as source of truth; materialize snapshots as views.

**Assessment:** This is architecturally elegant in theory but mismatched to the problem:
- The compositor is the source of truth, not our log. We're modeling observed state, not authoritative state.
- Event volume is low and state is small. There's no performance case for incremental materialization over full snapshot replacement.
- Log retention, compaction, and sequence management add complexity with no consumer-facing benefit.
- The debugging value of "what happened?" is better served by replay traces (which are already in the spec) and structured diagnostics on snapshots.

**Recommendation:** Materialize snapshots directly from reducer output. Support replay traces as a testing/debugging tool (captured event sequences replayed through the same reducer path), but don't maintain a live event log as architectural source of truth.

### 2.3 Typed Lifecycle State Machine — Yes, Simplified

**Proposal:** Replace loose health flags with an explicit FSM with guarded transitions.

**Assessment:** This is one of the strongest ideas. The original spec's health states are essentially an FSM already; making it explicit with typed transitions and guards improves correctness and debuggability.

The RETHINK's `degraded` state (vs the original `stale`) is a naming change without semantic difference. The original set is fine.

**Recommendation:** Implement an explicit lifecycle FSM with:
- States: `BOOTSTRAPPING`, `LIVE`, `STALE`, `RESYNCING`, `CLOSED`, `FAILED`.
- Guarded transitions (only legal transitions allowed).
- Transition reasons tracked for diagnostics.
- No `asyncio.Lock` needed if state transitions are confined to a single task (the event consumer).

### 2.4 Freshness as Type-Level Contract — No

**Proposal:** Wrap domain values in `Live[T]`, `RefreshBacked[T]`, `QueryOnly[T]` generic types.

**Assessment:** Python's type system is not strong enough to make this genuinely safe at "compile time." A `Live[WindowRef]` is still just a `WindowRef` at runtime. The wrapper adds API friction (`.value` access, type narrowing boilerplate) without real safety guarantees. Consumers will end up calling `.value` reflexively, negating the intent.

**Recommendation:** Express freshness through documentation, naming conventions, and snapshot metadata. The snapshot itself carries health state. Selectors for refresh-backed domains (outputs) can include docstrings and naming that signal their nature. This is the pragmatic Python approach.

### 2.5 Protocol Ingress Normalization Boundary — Partial

**Proposal:** Map `niri-pypc` protocol events to internal domain events at an adapter boundary, insulating reducers from protocol types.

**Assessment:** The motivation is sound (decouple from protocol churn), but the cost is high for this project:
- It doubles the event type surface (17 protocol events → 17+ domain events).
- The mapping layer must be maintained in lockstep with `niri-pypc` updates.
- `niri-state` already declares a compatible `niri-pypc` version range. Protocol churn is managed by version pinning, not by an abstraction layer.
- The reducers are simple enough that protocol type coupling is manageable.

**Recommendation:** Reducers consume `niri-pypc` event types directly. The dispatch layer (root reducer) provides a clean boundary: it pattern-matches on event variant type and routes to domain reducers. If a future protocol version requires adaptation, the dispatch layer is the natural place to add version-specific mapping without an upfront abstraction tax.

One partial adoption worth making: bootstrap response normalization. The bootstrap layer should extract and normalize query responses into a clean `BootstrapPayload` dataclass, insulating the snapshot builder from response envelope shapes. This is already in the original spec and is the right call.

### 2.6 Incremental Indexes — Yes

**Proposal:** Maintain secondary indexes during reduction for cheap selector access.

**Assessment:** Good idea, well-scoped. The indexes are small and deterministic. Building them during reduction (or snapshot construction) avoids repeated scans in selectors.

**Recommendation:** Maintain these indexes as part of the snapshot:
- `windows_by_workspace: dict[WorkspaceId, tuple[WindowId, ...]]`
- `workspaces_by_output: dict[OutputName, tuple[WorkspaceId, ...]]`
- `active_workspace_by_output: dict[OutputName, WorkspaceId]`

Build indexes during snapshot construction. Validate index soundness as part of invariant checks.

### 2.7 Declarative Conditions / Condition DSL — No

**Proposal:** Replace `wait_until(predicate)` with a declarative `Condition` DSL that compiles to selector+predicate plans.

**Assessment:** Over-engineered for the use case. The consumers are automation scripts that want to wait for a window to appear or a workspace to activate. `wait_until(lambda snap: snap.windows.get(42) is not None)` is clear, composable, and Pythonic. A condition DSL adds API surface, learning cost, and maintenance burden without making the common cases meaningfully better.

**Recommendation:** Keep simple predicate-based waits:
- `wait_until(predicate: Callable[[NiriSnapshot], bool], timeout, health_policy)`
- `watch(selector: Callable[[NiriSnapshot], T])` → async iterator of `T` values, emitted on change.

These are composable, testable, and immediately understandable. If a structured condition builder proves needed later, it can be layered on top without changing the core wait machinery.

### 2.8 Checkpointing and Fast Recovery — No

**Proposal:** Periodic compacted checkpoints for fast startup and recovery.

**Assessment:** Bootstrap is a handful of local Unix socket requests. It completes in milliseconds. Checkpointing adds format versioning, storage lifecycle, and migration complexity for negligible time savings.

**Recommendation:** Defer entirely. If bootstrap latency ever becomes a problem (it won't for local IPC), revisit then.

### 2.9 Unknown Event Evolution / Compat Adapters — No

**Proposal:** Treat unknown events as schema evolution input with adapter mapping.

**Assessment:** Speculative adapter mapping of unknown events is fragile and hard to validate. The original spec's three-tier policy (`STALE`/`FAIL`/`IGNORE`) is the right approach: explicit, auditable, and safe.

**Recommendation:** Keep the original unknown event policy. Unknown events are either:
- Explicitly harmless (no-op, logged),
- Staleness triggers (default, safe),
- Failure triggers (strict mode).

No guessing at semantics.

### 2.10 Test Architecture as Product Feature — Partially

**Proposal:** Treat replay, property tests, and chaos tests as first-class product surface.

**Assessment:** Replay traces for regression testing: yes. Property tests for reducer determinism: yes if practical. Chaos testing for runtime recovery: good for CI but not a product feature. A public conformance harness: premature.

**Recommendation:** Invest in:
1. Golden replay traces (captured event sequences + expected snapshots).
2. Reducer determinism tests (same input → same output, always).
3. Bootstrap/resync integration tests with mock servers.
4. Defer property testing and chaos testing to later maturity.

---

## 3. Recommended Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Public API Surface                    │
│  NiriState.connect()  .snapshot()  .watch()  .close()   │
└────────────────────────────┬────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────┐
│                    Store (_runtime/)                     │
│  Lifecycle FSM · Publication · Broadcaster · Waiters    │
└────────────────────────────┬────────────────────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
         ▼                   ▼                   ▼
┌────────────────┐ ┌────────────────┐ ┌─────────────────┐
│   Bootstrap    │ │  Root Reducer  │ │     Resync      │
│   (_runtime/)  │ │   (_core/)     │ │   (_runtime/)   │
│ Query+normalize│ │ Dispatch+apply │ │ Recovery coord  │
└────────┬───────┘ └────────┬───────┘ └─────────────────┘
         │                  │
         ▼                  ▼
┌────────────────────────────────────────────────────────┐
│                  Snapshot + Models (_core/)              │
│  Entities · Indexes · Health · Revision · Diagnostics   │
└────────────────────────────────────────────────────────┘
         ▲                  ▲
         │                  │
┌────────────────┐ ┌────────────────┐
│   Invariants   │ │   Selectors    │
│   (_core/)     │ │   (_core/)     │
└────────────────┘ └────────────────┘
```

Data flow:
1. Bootstrap queries compositor, normalizes responses, builds initial snapshot, validates invariants.
2. Root reducer receives protocol events, dispatches to domain reducers, produces new snapshot, validates invariants.
3. Store publishes immutable snapshots with change metadata.
4. Selectors are pure functions over snapshots. Waiters/watchers react to publications.
5. Resync coordinator handles recovery when state becomes stale.

---

## 4. Package Structure

```
src/niri_state/
  __init__.py                  # Public API re-exports
  _version.py                  # Version metadata
  config.py                    # NiriStateConfig + policy enums
  errors.py                    # Error hierarchy

  _core/
    __init__.py
    models/
      __init__.py
      types.py                 # Type aliases (OutputName, WindowId, etc.)
      entities.py              # OutputState, WorkspaceState, WindowState, etc.
      snapshot.py              # NiriSnapshot (frozen, revisioned, indexed)
      health.py                # HealthState enum + lifecycle FSM
      changes.py               # ChangeSet, ChangeCause, ChangeDomain
    reducers/
      __init__.py
      root.py                  # Root dispatcher
      windows.py               # Window domain reducer
      workspaces.py            # Workspace domain reducer
      focus.py                 # Focus pointer reducer
      keyboard.py              # Keyboard layout reducer
      overview.py              # Overview state reducer
    invariants.py              # Snapshot invariant checks
    snapshot_builder.py        # Build snapshot from entities + indexes

  _runtime/
    __init__.py
    bootstrap.py               # Query plan, response normalization, initial build
    store.py                   # NiriState (public entry), lifecycle, publication
    broadcaster.py             # Change subscription distribution
    waiters.py                 # Wait/watch helpers
    resync.py                  # Recovery coordination

  selectors/
    __init__.py
    outputs.py
    workspaces.py
    windows.py
    focus.py
    keyboard.py
    overview.py
    aggregates.py

tests/
  conftest.py                  # Shared fixtures, factory helpers
  _core/
    test_models.py
    test_reducers.py
    test_invariants.py
    test_snapshot_builder.py
  _runtime/
    test_bootstrap.py
    test_store.py
    test_broadcaster.py
    test_waiters.py
    test_resync.py
  selectors/
    test_selectors.py
  integration/
    test_lifecycle.py
  traces/
    # Golden replay trace files
```

Key structural decisions:
- `_core/` is pure: no imports from `asyncio`, no IO, no `niri-pypc` client/stream APIs. It only imports `niri-pypc` type definitions (models, events).
- `_runtime/` owns all async IO, lifecycle management, and `niri-pypc` client/stream usage.
- `selectors/` is at the top level because selectors are part of the public API surface and are pure functions — they belong to neither core nor runtime conceptually.
- The underscore prefix on `_core/` and `_runtime/` signals these are internal implementation packages. The public API is re-exported from `__init__.py`.

---

## 5. Model Layer Design

### 5.1 Entity Wrappers

Entity wrappers embed raw protocol models and add derived convenience fields. They are frozen Pydantic models.

```python
class OutputState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    output_name: str           # Map key, equals raw.name
    raw: Output                # Protocol model
    # No derived fields needed — Output is already rich

class WorkspaceState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    workspace_id: int          # Map key, equals raw.id
    raw: Workspace             # Protocol model
    # Derived fields available via raw: idx, name, output, is_active, etc.

class WindowState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    window_id: int             # Map key, equals raw.id
    raw: Window                # Protocol model
    # Derived fields available via raw: title, app_id, is_focused, etc.

class KeyboardState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    raw: KeyboardLayouts | None
    current_idx: int | None
    current_name: str | None   # Derived: names[current_idx] if valid

class OverviewState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    raw: Overview | None
    is_open: bool | None       # Derived from raw.is_open
```

Design rationale: Entity wrappers are thin. They exist primarily to provide a stable identity key and a place for derived fields. They do NOT duplicate raw model fields — consumers access `window_state.raw.title`, not `window_state.title`. This avoids maintaining synchronization between wrapper fields and protocol model evolution.

### 5.2 Snapshot

The snapshot is the primary public artifact. It is immutable, revisioned, and self-describing.

```python
class NiriSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    # Revision and health
    revision: int
    health: HealthState
    timestamp: float               # time.monotonic() at publication

    # Entity maps (keyed for O(1) lookup)
    outputs: dict[str, OutputState]
    workspaces: dict[int, WorkspaceState]
    windows: dict[int, WindowState]

    # Focus pointers (nullable)
    focused_output_name: str | None
    focused_workspace_id: int | None
    focused_window_id: int | None

    # Domain wrappers
    keyboard: KeyboardState
    overview: OverviewState

    # Derived indexes (for cheap selector access)
    workspaces_by_output: dict[str, tuple[int, ...]]
    windows_by_workspace: dict[int, tuple[int, ...]]
    active_workspace_by_output: dict[str, int]

    # Metadata
    diagnostics: tuple[str, ...]   # Accumulated diagnostic messages
    compatibility: CompatibilityInfo | None
```

Design rationale:
- Frozen Pydantic model ensures immutability.
- `dict` for entity maps provides O(1) keyed access. While Pydantic frozen models don't deeply freeze dicts, the contract is enforced by convention and tests (consumers must not mutate).
- Indexes are pre-computed `tuple`s for stable ordering and immutability.
- `diagnostics` accumulates structured messages about stale transitions, unknown events, config load failures, etc.
- `CompatibilityInfo` captures `niri_state` version, `niri_pypc` version, and upstream protocol pin for operational introspection.

### 5.3 Health and Lifecycle

```python
class HealthState(str, Enum):
    BOOTSTRAPPING = "bootstrapping"
    LIVE = "live"
    STALE = "stale"
    RESYNCING = "resyncing"
    CLOSED = "closed"
    FAILED = "failed"
```

Legal transitions:
```
BOOTSTRAPPING → LIVE          (successful bootstrap + replay)
BOOTSTRAPPING → FAILED        (bootstrap failure)
LIVE → STALE                  (desync trigger)
LIVE → CLOSED                 (explicit close)
STALE → RESYNCING             (auto resync)
STALE → LIVE                  (manual refresh success)
STALE → CLOSED                (explicit close)
RESYNCING → LIVE              (resync success)
RESYNCING → STALE             (resync failure, retry possible)
RESYNCING → FAILED            (resync failure, terminal)
RESYNCING → CLOSED            (explicit close during resync)
FAILED → CLOSED               (explicit close)
```

The lifecycle FSM is implemented as a simple class with a `transition(target, reason)` method that validates the transition is legal and records the reason. No lock needed if transitions are confined to a single async task.

### 5.4 ChangeSet

```python
class ChangeCause(str, Enum):
    BOOTSTRAP = "bootstrap"
    EVENT = "event"
    STALE_TRANSITION = "stale_transition"
    RESYNC = "resync"
    CLOSE = "close"

class ChangeDomain(str, Enum):
    WINDOWS = "windows"
    WORKSPACES = "workspaces"
    FOCUS = "focus"
    KEYBOARD = "keyboard"
    OVERVIEW = "overview"
    OUTPUTS = "outputs"
    HEALTH = "health"
    METADATA = "metadata"

class ChangeSet(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    revision: int
    timestamp: float
    cause: ChangeCause
    domains: frozenset[ChangeDomain]
    event_type: str | None         # Event class name if cause is EVENT
    snapshot: NiriSnapshot
```

---

## 6. Reducer Design

### 6.1 Reducer Contract

Each domain reducer is a pure function:

```python
def reduce_<domain>(snapshot_data: SnapshotDraft, event: <EventType>) -> ReductionResult
```

Where `SnapshotDraft` is a mutable working copy of snapshot fields (not the frozen model), and `ReductionResult` captures:

```python
@dataclass
class ReductionResult:
    applied: bool
    changed_domains: set[ChangeDomain]
    summary: str                   # Human-readable for diagnostics
```

Design choice — **mutable draft vs immutable copy**: Since Python doesn't have efficient persistent data structures, building a new frozen snapshot from scratch on every event is wasteful (even if cheap in absolute terms). Instead, reducers operate on a mutable draft (a plain dataclass or dict-of-dicts working copy). After all reductions for an event complete, the draft is frozen into an immutable `NiriSnapshot`. This keeps reducers simple and avoids excessive object allocation.

### 6.2 Root Reducer / Dispatch

```python
def reduce(draft: SnapshotDraft, event: BaseModel, config: NiriStateConfig) -> ReductionResult:
    match event:
        case WindowOpenedOrChangedEvent():
            return reduce_window_opened_or_changed(draft, event)
        case WindowClosedEvent():
            return reduce_window_closed(draft, event)
        case WindowsChangedEvent():
            return reduce_windows_changed(draft, event)
        case WindowFocusChangedEvent():
            return reduce_window_focus_changed(draft, event)
        # ... etc for all event types
        case ConfigLoadedEvent():
            return reduce_config_loaded(draft, event)
        case ScreenshotCapturedEvent():
            return ReductionResult(applied=False, changed_domains=set(), summary="no-op: screenshot")
        case UnknownEvent():
            return handle_unknown_event(draft, event, config)
        case _:
            return handle_unimplemented_event(draft, event, config)
```

The `match` statement on concrete types is the dispatch boundary. It is explicit, exhaustive, and easy to audit. Adding a new event type means adding a case — if you miss it, `handle_unimplemented_event` catches it and applies the configured unknown event policy.

### 6.3 Domain Reducer Details

**Windows reducer** handles:
- `WindowOpenedOrChangedEvent`: upsert window in map, rebuild indexes.
- `WindowClosedEvent`: remove window from map, clear focus if it was focused, rebuild indexes.
- `WindowsChangedEvent`: full replacement of window map and indexes.
- `WindowFocusChangedEvent`: update `focused_window_id`, update `is_focused` on affected windows.
- `WindowUrgencyChangedEvent`: update `is_urgent` on window.
- `WindowFocusTimestampChangedEvent`: update `focus_timestamp` on window.
- `WindowLayoutsChangedEvent`: apply layout changes by `(window_id, WindowLayout)` tuples.

**Workspaces reducer** handles:
- `WorkspacesChangedEvent`: full replacement of workspace map and indexes.
- `WorkspaceActivatedEvent`: update `is_active`/`is_focused` on workspace, update `active_workspace_by_output`.
- `WorkspaceActiveWindowChangedEvent`: update `active_window_id` on workspace.
- `WorkspaceUrgencyChangedEvent`: update `is_urgent` on workspace.

**Focus reducer**: Focus changes are handled inline by window/workspace reducers rather than as a separate reducer, because focus state is updated as a side effect of window focus events and workspace activation events. The snapshot fields `focused_output_name`, `focused_workspace_id`, `focused_window_id` are updated by the relevant domain reducer.

**Keyboard reducer** handles:
- `KeyboardLayoutsChangedEvent`: replace keyboard state entirely.
- `KeyboardLayoutSwitchedEvent`: update `current_idx` and derive `current_name`.

**Overview reducer** handles:
- `OverviewOpenedOrClosedEvent`: update `is_open`.

### 6.4 Replace-All Event Semantics

`WindowsChangedEvent` and `WorkspacesChangedEvent` carry the full current list. These are authoritative: the reducer replaces the entire domain map and rebuilds all indexes. Focus pointers and cross-references must be revalidated after replacement.

This is important for correctness: after a replace-all event, any window/workspace that was in the old map but not in the new list is gone. Focus pointers to removed entities must be cleared.

---

## 7. Bootstrap and Sync Design

### 7.1 Bootstrap Sequence

```
1. Normalize config (enforce strict correctness → fail-fast backpressure).
2. Open NiriConnectionBundle (client + event stream).
3. Event stream starts buffering immediately into its internal queue.
4. Execute query plan via client:
   - OutputsRequest → dict[str, Output]
   - WorkspacesRequest → list[Workspace]
   - WindowsRequest → list[Window]
   - FocusedOutputRequest → Output | None
   - FocusedWindowRequest → Window | None
   - KeyboardLayoutsRequest → KeyboardLayouts
   - OverviewStateRequest → Overview
   - (optional) VersionRequest → str
5. Normalize responses into BootstrapPayload.
6. Build initial snapshot (entities, indexes, focus pointers, invariants).
7. Drain and replay buffered events through root reducer.
8. Validate final snapshot invariants.
9. Publish first LIVE snapshot.
```

### 7.2 BootstrapPayload

```python
@dataclass(frozen=True)
class BootstrapPayload:
    outputs: dict[str, Output]
    workspaces: list[Workspace]
    windows: list[Window]
    focused_output: Output | None
    focused_window: Window | None
    keyboard_layouts: KeyboardLayouts
    overview: Overview
    version: str | None
```

Response normalization matches on concrete response class types (not duck typing) and raises `BootstrapError` for unexpected variants.

### 7.3 Race Closure

The event stream starts buffering before queries execute. Events that arrive during the query window describe state transitions that may or may not be reflected in query results. Replaying these events through the normal reducer path after building the initial snapshot from queries closes the race:

- If an event describes a change already reflected in the query result (e.g., a window that was already open when queried), the reducer applies it idempotently (upsert overwrites with same data).
- If an event describes a change that happened after the query (e.g., a window opened between the WindowsRequest and now), the reducer applies it normally.

This is correct because the reducer is designed to handle events regardless of prior state. Replace-all events are authoritative, and incremental events are idempotent or additive.

---

## 8. Store and Publication Design

### 8.1 NiriState (Public Entry Point)

```python
class NiriState:
    @classmethod
    async def connect(cls, config: NiriStateConfig | None = None) -> NiriState: ...

    @property
    def snapshot(self) -> NiriSnapshot: ...

    @property
    def health(self) -> HealthState: ...

    @property
    def revision(self) -> int: ...

    def subscribe(self) -> AsyncIterator[ChangeSet]: ...

    def watch(self, selector: Callable[[NiriSnapshot], T]) -> AsyncIterator[T]: ...

    async def wait_until(
        self,
        predicate: Callable[[NiriSnapshot], bool],
        *,
        timeout: float | None = None,
        health_policy: WaitHealthPolicy = WaitHealthPolicy.LIVE_ONLY,
    ) -> NiriSnapshot: ...

    async def refresh(self) -> NiriSnapshot: ...

    async def close(self) -> None: ...

    async def __aenter__(self) -> NiriState: ...
    async def __aexit__(self, *exc) -> None: ...
```

### 8.2 Publication Flow

All state mutations flow through a single async task (the event consumer). This task:
1. Reads the next event from `NiriEventStream`.
2. Creates a mutable draft from the current snapshot.
3. Runs the root reducer.
4. If the event was applied (or triggered a health change), runs invariant checks.
5. Freezes the draft into a new `NiriSnapshot`.
6. Publishes the snapshot + `ChangeSet` to the broadcaster.

Single-task affinity eliminates the need for locks on the snapshot. The `snapshot` property returns a reference to the latest immutable snapshot, which is safe to read from any task.

### 8.3 Broadcaster

The broadcaster distributes `ChangeSet`s to subscribers. Each subscriber has a bounded `asyncio.Queue`. Overflow behavior follows the configured policy (drop oldest or fail).

```python
class Broadcaster:
    def subscribe(self) -> Subscription: ...
    def publish(self, change_set: ChangeSet) -> None: ...
    def close(self) -> None: ...
```

A `Subscription` is an async iterator over `ChangeSet`s with cleanup on close.

### 8.4 Snapshot Access

The current snapshot is stored as a single reference (`self._snapshot: NiriSnapshot`). The `snapshot` property returns this reference directly. Because snapshots are immutable, this is inherently thread-safe and lock-free.

---

## 9. Selector Design

Selectors are pure functions, not methods on the snapshot. This keeps the snapshot model clean and allows selectors to be composed, tested, and versioned independently.

```python
# selectors/windows.py
def window_by_id(snapshot: NiriSnapshot, window_id: int) -> WindowState | None:
    return snapshot.windows.get(window_id)

def windows(snapshot: NiriSnapshot) -> tuple[WindowState, ...]:
    return tuple(snapshot.windows.values())

def focused_window(snapshot: NiriSnapshot) -> WindowState | None:
    if snapshot.focused_window_id is None:
        return None
    return snapshot.windows.get(snapshot.focused_window_id)

def windows_on_workspace(snapshot: NiriSnapshot, workspace_id: int) -> tuple[WindowState, ...]:
    window_ids = snapshot.windows_by_workspace.get(workspace_id, ())
    return tuple(snapshot.windows[wid] for wid in window_ids if wid in snapshot.windows)
```

Selectors return `None` or empty tuples for missing entities — they never raise. This makes them safe to use in predicates and watch expressions without defensive error handling.

The selector module also provides convenience re-exports so consumers can do:
```python
from niri_state.selectors import focused_window, windows_on_workspace
```

---

## 10. Wait/Watch Design

### 10.1 wait_until

```python
async def wait_until(self, predicate, *, timeout=None, health_policy=LIVE_ONLY) -> NiriSnapshot:
```

Implementation:
1. Check current snapshot against predicate. If satisfied, return immediately.
2. Subscribe to broadcaster.
3. On each `ChangeSet`, check predicate against new snapshot.
4. If health policy is `LIVE_ONLY`, skip stale snapshots.
5. On timeout, raise `SelectorWaitError` (which is also a `TimeoutError`).
6. On close, raise `StateLifecycleError`.
7. Clean up subscription on exit (via `async with` or `try/finally`).

### 10.2 watch

```python
def watch(self, selector: Callable[[NiriSnapshot], T]) -> AsyncIterator[T]:
```

Implementation:
1. Yield current selector value.
2. Subscribe to broadcaster.
3. On each `ChangeSet`, compute selector value. If changed (by equality), yield it.
4. On close, terminate iteration.

Change detection by equality (`==`) is the simplest correct approach. For selectors returning Pydantic models, equality is structural. For selectors returning primitives, equality is value-based.

---

## 11. Error Design

```
NiriStateError (base)
├── StateConfigError              # Invalid configuration
├── StateLifecycleError           # Wrong state for operation
├── BootstrapError                # Bootstrap query/normalization failure
│   └── (chains niri-pypc causes)
├── ReductionError                # Reducer failure (bug indicator)
├── InvariantError                # Snapshot invariant violation
│   └── violations: list[str]
├── DesyncError                   # State coherence lost
│   └── trigger: str
├── ResyncError                   # Recovery attempt failure
│   └── (chains underlying cause)
├── WatchOverflowError            # Subscriber queue overflow
└── SelectorWaitError(TimeoutError)  # Wait timeout
```

All errors include `revision` (if available) and chain the underlying cause via `raise ... from exc`.

Key mapping from `niri-pypc` errors:
- `TransportError`/`DecodeError` during bootstrap → `BootstrapError`
- `RemoteError` during bootstrap → `BootstrapError`
- `ProtocolError` (fail-fast overflow) on event stream → desync trigger → `DesyncError` or stale transition
- `TransportError` on event stream → desync trigger

---

## 12. Configuration Design

```python
class CorrectnessMode(str, Enum):
    STRICT = "strict"          # Fail-fast backpressure, stale on unknown
    BEST_EFFORT = "best_effort"

class ResyncPolicy(str, Enum):
    MANUAL = "manual"          # Enter STALE, wait for explicit refresh()
    AUTO = "auto"              # Enter RESYNCING, attempt automatic recovery

class UnknownEventPolicy(str, Enum):
    STALE = "stale"            # Default: mark state stale
    FAIL = "fail"              # Raise error
    IGNORE = "ignore"          # Log and continue (only for declared harmless)

class InvariantFailurePolicy(str, Enum):
    STALE = "stale"            # Mark state stale with diagnostics
    FAIL = "fail"              # Raise InvariantError

class WaitHealthPolicy(str, Enum):
    LIVE_ONLY = "live_only"    # Stale snapshots don't satisfy waits
    ALLOW_STALE = "allow_stale"

@dataclass(frozen=True)
class NiriStateConfig:
    pypc: NiriConfig = field(default_factory=NiriConfig)
    correctness_mode: CorrectnessMode = CorrectnessMode.STRICT
    resync_policy: ResyncPolicy = ResyncPolicy.MANUAL
    unknown_event_policy: UnknownEventPolicy = UnknownEventPolicy.STALE
    invariant_failure_policy: InvariantFailurePolicy = InvariantFailurePolicy.STALE
    subscriber_queue_size: int = 64
    subscriber_overflow: StoreOverflowMode = StoreOverflowMode.DROP_OLDEST
```

Config normalization during `connect()`:
- If `correctness_mode == STRICT` and `pypc.backpressure_mode != FAIL_FAST`, derive a new `NiriConfig` with `backpressure_mode=FAIL_FAST` using `dataclasses.replace()`.

---

## 13. Testing Strategy

### 13.1 Priority Order

1. **Reducer unit tests** (highest priority): Each event type gets deterministic input/output tests. These are the core correctness guarantees.
2. **Invariant tests**: Construct valid and invalid snapshots, verify invariant checker catches violations.
3. **Bootstrap normalization tests**: Mock responses, verify `BootstrapPayload` construction and error cases.
4. **Snapshot builder tests**: Verify index construction, focus derivation, entity mapping.
5. **Store lifecycle tests**: Mock event stream, verify health transitions, publication, close semantics.
6. **Wait/watch tests**: Verify timeout, cancellation, health gating, change detection.
7. **Replay trace tests**: Golden traces that exercise full bootstrap→reduce→publish flow.
8. **Integration tests**: End-to-end with mock Unix socket server.

### 13.2 Test Fixtures

Build factory helpers that construct valid protocol models:

```python
def make_window(id: int = 1, title: str = "test", workspace_id: int = 1, **overrides) -> Window: ...
def make_workspace(id: int = 1, idx: int = 0, output: str = "DP-1", **overrides) -> Workspace: ...
def make_output(name: str = "DP-1", **overrides) -> Output: ...
def make_snapshot(**overrides) -> NiriSnapshot: ...
```

These ensure tests work with real protocol types, not dicts or mocks.

### 13.3 Replay Traces

A replay trace is a JSON file containing:
```json
{
  "bootstrap": { ... BootstrapPayload fields ... },
  "events": [ ... ordered list of serialized events ... ],
  "expected": {
    "final_health": "live",
    "window_count": 3,
    "focused_window_id": 42,
    ...
  }
}
```

The replay runner deserializes the trace, builds the initial snapshot, reduces all events, and asserts expected outcomes. Same code path as live operation.

---

## 14. What to Defer

These items are explicitly deferred from the initial implementation:

1. **Package split** (core/runtime as separate packages): Internal boundary exists; extraction later if needed.
2. **Event log / event sourcing**: Snapshots are materialized directly.
3. **Typed freshness wrappers**: Documentation and naming suffice.
4. **Ingress normalization layer**: Reducers consume protocol types directly.
5. **Declarative condition DSL**: Predicate-based waits are sufficient.
6. **Checkpointing**: Bootstrap is fast enough.
7. **Schema evolution adapters**: Version pinning handles protocol changes.
8. **Property-based testing**: Add when reducer complexity warrants it.
9. **Layers domain**: Query-only, no event coverage; add when useful.
10. **Output refresh mechanism**: Outputs are bootstrap-only initially; add periodic refresh when needed.

---

## 15. Design Principles Summary

1. **Complexity budget is real.** Every abstraction must earn its place against the actual problem size (6 domains, 17 events, local IPC).

2. **Snapshots are the product.** The library exists to produce coherent, immutable, revisioned snapshots of compositor state. Everything else serves this.

3. **Pure core, async shell.** Reducers, invariants, selectors, and snapshot construction are pure functions. Async IO and lifecycle are confined to the runtime shell.

4. **Explicit over magic.** Health states, freshness limitations, unknown event policies — all are visible and configurable, never hidden.

5. **Protocol types flow through.** Entity wrappers embed raw protocol models rather than duplicating fields. This minimizes maintenance surface and keeps protocol richness accessible.

6. **Single-task publication.** One async task owns state mutation. No locks on the hot path. Immutable snapshots are safe to share.

7. **Defer what isn't needed.** The initial implementation should be minimal and correct. Abstractions like event sourcing, condition DSLs, and checkpointing can be added later if warranted by real usage.

8. **Test the reducers first.** Reducer correctness is the foundation. If reducers are wrong, nothing else matters. If reducers are right, everything else is plumbing.
