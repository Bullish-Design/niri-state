# NIRI_STATE_CONCEPT

## Authority and Scope
This document is the guiding concept for **`niri-state`**.

`niri-state` is a downstream Python library built on top of **`niri-pypc`**. It owns:
- event application,
- live derived compositor state,
- snapshots,
- selectors,
- and reconciliation-oriented waiting/observation APIs.

It does **not** own:
- raw protocol code generation,
- transport or socket lifecycle,
- raw wire codecs,
- or the authoritative IPC type surface.

This concept assumes:
- `niri-pypc` remains the pinned protocol/runtime layer,
- `niri-pypc` owns typed requests, responses, actions, and event decoding/delivery,
- `niri-state` owns event application and state derivation,
- higher-level libraries/apps may depend on both,
- and `niri-state` is where event-derived compositor truth lives.

---

## Project Identity
### Library name
- **Project name:** `niri-state`
- Suggested import root: `niri_state`

### Naming rationale
The name intentionally communicates:
- **Niri** as the compositor authority,
- **state** as the library's responsibility,
- a reduced, live, queryable model rather than a raw wire protocol surface.

---

## Core Goals
1. **High-confidence observed state**
   - Maintain a coherent in-memory view of compositor state as observed through bootstrap queries plus the event stream.
   - Never silently invent state that is not justified by protocol data.

2. **Clear separation from `niri-pypc`**
   - `niri-pypc` owns protocol correctness and transport/runtime behavior.
   - `niri-state` owns state reduction and consumer-facing state APIs.

3. **Deterministic reducer behavior**
   - Given the same bootstrap payloads and the same ordered event sequence, the library must produce the same state and the same revision history.

4. **Atomic snapshots**
   - Consumers read immutable snapshots representing one coherent revision.
   - Partial application must never leak into the public surface.

5. **Ergonomic read/query APIs**
   - Common state lookups should be easy and typed.
   - Selectors and wait helpers should support higher-level orchestration without re-implementing state plumbing.

6. **Explicit desync and resync handling**
   - Unknown events, invariant failures, disconnects, and bootstrap failures must have clear consequences.
   - State health must be observable.

7. **Replayable correctness**
   - Recorded traces should be usable to verify reducers, selectors, convergence behavior, and regression scenarios.

---

## Non-Goals
1. Owning raw Niri IPC transport, framing, socket lifecycle, or decode/encode logic.
2. Replacing `niri-pypc` as the authoritative protocol layer.
3. Planning actions, expressing UI/business policy, or deciding desired layout outcomes.
4. Silently recovering from unsupported/unknown events by guessing state changes.
5. Acting as a durable database or long-term history store.
6. Hiding all protocol realities; this library is state-centric, but still grounded in actual IPC semantics.
7. Supporting arbitrary untyped dict-based event ingestion as a primary public API.

---

## Relationship to `niri-pypc`
`niri-state` depends on `niri-pypc` and should be treated as a downstream companion library, not as a sibling protocol implementation.

### `niri-pypc` owns
- the pinned upstream protocol alignment,
- generated protocol types,
- typed requests/responses/actions/events,
- event decoding and delivery,
- command/event socket behavior,
- and runtime lifecycle/error handling.

### `niri-state` owns
- initial state bootstrap,
- event application,
- reducer composition,
- immutable snapshots,
- selectors and query helpers,
- wait/observe APIs,
- state health and desync tracking,
- and resync coordination.

### External dependency direction
```text
niri-state -> niri-pypc
higher-level apps/libraries -> niri-state, niri-pypc
niri-pypc -X-> niri-state
```

The one-way dependency is a hard architectural rule.

---

## Source-of-Truth Model
`niri-state` should model **observed compositor truth**, not desired truth.

That means:
- the library reflects what Niri has reported,
- the library may derive deterministic indexes and conveniences from observed data,
- but it must not speculate about pending actions, user intent, or desired future layout.

Examples of valid derived state:
- lookup maps keyed by output/workspace/window identifiers,
- active/focused entity references,
- ordered collections normalized into convenient indexes,
- revision counters,
- state health flags,
- and selector-friendly aggregates that are purely computed from observed state.

Examples of invalid state for this layer:
- "planned" layout transitions,
- action queues,
- desired policy overlays,
- inferred state that is not grounded in bootstrap data or events.

---

## High-Level Architecture
`niri-state` is organized into five major concerns.

### 1. Bootstrap/synchronization
Responsible for obtaining an initial coherent state using `niri-pypc` request and event-stream APIs.

Responsibilities:
- open a coordinated command/event session through `niri-pypc`,
- subscribe to the event stream,
- buffer events during bootstrap,
- run the initial query suite,
- materialize the first state revision,
- replay buffered events in order,
- and mark the store as live only after the bootstrap boundary is satisfied.

### 2. Reducer engine
Responsible for deterministic event application.

Responsibilities:
- apply typed events to normalized state,
- enforce invariants,
- produce state deltas/change metadata,
- distinguish supported, unsupported, and unknown inputs,
- remain pure and side-effect free.

### 3. Snapshot/state model
Responsible for the public in-memory representation.

Responsibilities:
- define immutable snapshot types,
- expose normalized entity collections,
- carry revision/health metadata,
- expose typed references to active/focused entities,
- and support stable selector usage.

### 4. Selector/query layer
Responsible for read ergonomics.

Responsibilities:
- provide common lookups and filters,
- concentrate derived query logic outside application code,
- remain deterministic and side-effect free,
- and avoid embedding action policy.

### 5. Observation/waiting/resync coordination
Responsible for long-lived live usage.

Responsibilities:
- publish change notifications,
- support `wait_until` / `wait_for_selector` style APIs,
- expose health transitions,
- trigger or coordinate resyncs,
- and settle consumers predictably on close/failure.

---

## State Model Design
The public state surface should use **hand-written Pydantic models** consistently.

### Design priorities
1. Strong typing over free-form dicts.
2. Immutable public snapshots.
3. Normalized entities plus convenient derived indexes.
4. Stable equality and revision semantics.
5. Machine-friendly diagnostics when invariants fail.

### Suggested top-level snapshot shape
A `NiriSnapshot` should include, conceptually:
- protocol/runtime compatibility metadata,
- snapshot revision,
- bootstrap status,
- health/state freshness status,
- outputs,
- workspaces,
- windows,
- layers and other supported surfaces,
- focus/active-location fields,
- and last-applied event metadata where useful.

### Entity modeling guidance
- Store entities in normalized mappings keyed by stable identifiers when the protocol provides them.
- Preserve protocol identifiers directly whenever possible.
- Avoid key schemes that require consumers to understand protocol accidents.
- Derived ordering should be explicit rather than implicit in dict iteration.

### Public immutability rule
Snapshots exposed to consumers must be treated as immutable.

Implementation detail may be optimized internally, but the public rule is:
- once a snapshot is published for revision `N`, it never mutates,
- revision `N+1` is a new coherent snapshot.

---

## Snapshot Health and Lifecycle
`niri-state` should expose explicit lifecycle/health states such as:
- `bootstrapping`
- `live`
- `stale`
- `resyncing`
- `closed`
- `failed`

### Health semantics
- **bootstrapping**: initial sync is still in progress; state should not yet be treated as complete.
- **live**: state is coherent and advancing normally.
- **stale**: state is readable but no longer guaranteed current/correct because of an unknown event, invariant failure, or transport issue.
- **resyncing**: a refresh/bootstrap sequence is in progress.
- **closed**: the live store has been shut down intentionally.
- **failed**: a terminal unrecoverable error occurred.

This health signal should be part of the public contract, not hidden implementation detail.

---

## Bootstrap and Synchronization Strategy
The initial synchronization workflow is the center of the library.

### Core problem
Because command and event flow are separate concerns in `niri-pypc`, `niri-state` must avoid races between:
- taking an initial snapshot via request calls,
- and receiving live events that may arrive during bootstrap.

### Recommended bootstrap sequence
1. Open a coordinated connection bundle/session via `niri-pypc`.
2. Subscribe to events and begin buffering them.
3. Execute the initial query suite needed to build state.
4. Build the initial normalized snapshot from those query results.
5. Replay buffered events in order through the same reducer pipeline.
6. Publish the first live revision and transition health to `live`.

### Bootstrap rule
The library must not publish a "live" snapshot until the race window has been closed according to the chosen synchronization strategy.

### Initial query suite
The query suite should cover only state surfaces that `niri-state` intends to model. It should remain explicit and versioned, not accidental.

Examples may include:
- outputs,
- workspaces,
- windows,
- focused/active state,
- keyboard layout state,
- and other protocol surfaces that are actually reduced into the snapshot model.

### Bootstrap output
Bootstrap should produce:
- revision `0` or `1` as the first coherent snapshot,
- explicit metadata about whether buffered events were replayed,
- compatibility/health information,
- and a consistent basis for all later selectors and waits.

---

## Reducer Design
Reducers are the heart of `niri-state`.

### Reducer rules
1. Reducers are pure functions.
2. Reducers do not perform I/O.
3. Reducers do not send commands.
4. Reducers accept typed inputs from `niri-pypc`, not raw wire JSON.
5. Reducers either apply a change deterministically, no-op explicitly, or fail with a clear reason.

### Composition model
A recommended structure is:
- domain reducers for outputs/workspaces/windows/focus/etc.,
- a root reducer that dispatches by event type,
- invariant checks after each applied change or after each batch,
- a shared normalization layer for bootstrap payloads and event payloads.

### Bootstrap consistency rule
Where practical, bootstrap data should enter the state model through the same normalization/reducer paths used by live events. That reduces drift between "initial load" and "incremental update" behavior.

### Invariant examples
- active workspace references a known workspace,
- focused window references a known window when present,
- workspace-to-output relationships are internally consistent,
- entity uniqueness constraints hold,
- removal events do not leave dangling references.

Invariant failures must not be ignored.

---

## Change Model
Each successful state transition should produce a typed `ChangeSet` or equivalent metadata object.

A `ChangeSet` should include, conceptually:
- old revision,
- new revision,
- transition cause (`bootstrap`, `event`, `resync`, `manual_refresh`),
- applied event type(s),
- affected domains or entity identifiers where useful,
- health transition if any,
- and access to the new snapshot.

The goal is to support:
- async observers,
- selector subscriptions,
- debug logging,
- replay tests,
- and higher-level orchestration.

---

## Unknown and Unsupported Event Policy
`niri-pypc` may decode inbound unknown variants into explicit unknown sentinel models. `niri-state` must define what those mean for state correctness.

### Recommended policy
For `niri-state`, prefer:
- **strict known-event reduction**,
- **no silent ignore of unknown state-affecting inputs**,
- **transition to `stale` on unknown/unsupported reducer inputs by default**,
- **optional auto-resync policy when configured**.

### Rationale
A state library has a stronger correctness burden than a raw protocol library. Preserving an unknown inbound event for diagnostics is useful, but continuing to claim that state is definitely correct after an unhandled change is risky.

### Supported behavior modes
#### Option A: strict
- raise/terminate the live state flow on unknown or unsupported state-affecting events.
- best for maximal fail-fast correctness.

#### Option B: stale-and-observable
- mark the store stale,
- preserve diagnostics,
- keep the last coherent snapshot readable,
- require explicit resync or allow configured auto-resync.

### Recommended default
Use **stale-and-observable** as the default public behavior.

That gives consumers:
- a readable last-known-good snapshot,
- a strong signal that correctness is no longer guaranteed,
- and a controlled path back to coherence.

---

## Resync Strategy
Resynchronization should be a first-class feature, not an afterthought.

### Resync triggers
- transport disconnect/reconnect,
- explicit unknown event,
- invariant failure,
- bootstrap incompatibility,
- manual refresh request,
- or selector/wait consumer opting into freshness guarantees.

### Resync policies
#### Manual only
- mark stale,
- expose diagnostics,
- do not automatically resync.

#### Auto-resync
- transition to `resyncing`,
- perform a fresh bootstrap,
- publish a new live revision if successful,
- otherwise transition to `failed` or remain `stale` based on configuration.

### Resync contract
A successful resync should produce a new coherent snapshot revision and should not mutate older snapshots in place.

---

## Selector and Query Design
Selectors are a major reason the library exists.

### Selector rules
1. Selectors are pure.
2. Selectors accept a snapshot and return typed results.
3. Selectors do not perform I/O.
4. Selectors do not mutate state.
5. Selectors should prefer composability over giant convenience surfaces.

### Selector categories
- direct lookup selectors: `workspace_by_id`, `window_by_id`, `output_by_name`
- relationship selectors: `windows_on_workspace`, `workspace_for_window`
- active/focused selectors: `focused_window`, `active_output`, `active_workspace`
- aggregate selectors: visible windows, outputs with active workspaces, etc.
- guard selectors: predicates for wait conditions

### Boundary rule
Selectors may compute convenient derived answers from the snapshot, but they must not embed orchestration policy or command issuance.

---

## Waiting and Observation APIs
A live state library should support both pull and push usage.

### Pull-oriented APIs
Suggested concepts:
- `state.current()` -> returns the latest snapshot
- `await state.snapshot()` -> optionally await bootstrap completion and return a coherent snapshot
- `state.health()` -> returns current health/lifecycle state

### Push-oriented APIs
Suggested concepts:
- `async for change in state.changes(): ...`
- `async for value in state.watch_selector(selector): ...`

### Waiting APIs
Suggested concepts:
- `await state.wait_until(predicate, timeout=...)`
- `await state.wait_for_selector(selector, predicate=..., timeout=...)`

### Waiting semantics
- waits should be event-driven rather than polling-based,
- timeouts and cancellation should be explicit,
- waiting on a stale/failed store should fail predictably unless configured otherwise,
- and waits should operate on coherent snapshots only.

---

## Public API Concept
The public API should be small and disciplined.

### Live state API
```python
async with NiriState.connect(config) as state:
    snapshot = await state.snapshot()
    focused = snapshot.focused_window
```

### Change observation API
```python
async with NiriState.connect(config) as state:
    async for change in state.changes():
        print(change.new_revision, change.affected_domains)
```

### Wait helper API
```python
async with NiriState.connect(config) as state:
    await state.wait_until(lambda s: s.focused_window is not None, timeout=5.0)
```

### Selector watch API
```python
async with NiriState.connect(config) as state:
    async for workspace in state.watch_selector(selectors.active_workspace):
        print(workspace)
```

### Important behavioral rule
The API should present **coherent state**, not raw transport behavior. But it must not conceal correctness boundaries such as stale state, resync, or bootstrap incompleteness.

---

## Dependency Rules
Allowed dependency direction, conceptually:

```text
store/live API -> sync, reducers, selectors, models, errors, niri-pypc
sync -> reducers, models, errors, niri-pypc
reducers -> models, errors, niri-pypc types
selectors -> models
models -> (internal helpers only)
errors -> no internal deps
```

Forbidden couplings:
1. `niri-state` must not reimplement transport/runtime concerns that belong to `niri-pypc`.
2. Reducers must not import application/business policy modules.
3. Selectors must not perform I/O or issue commands.
4. Public convenience APIs must not bypass reducer/state-health rules.
5. `niri-state` must not depend on downstream application packages.

---

## Error Model
Define a state-focused error taxonomy.

Suggested categories:
1. `BootstrapError`
2. `ReductionError`
3. `InvariantError`
4. `DesyncError`
5. `ResyncError`
6. `StateLifecycleError`
7. `SelectorWaitError`

Suggested context fields:
- revision,
- last good revision,
- health state,
- event type,
- selector name or predicate label,
- resync policy,
- compatibility metadata,
- wrapped cause,
- and bounded diagnostic payload excerpts where relevant.

The library should preserve enough context to explain whether a problem was:
- protocol/runtime-originated in `niri-pypc`,
- reducer/invariant-originated in `niri-state`,
- or a freshness/health contract problem for a state consumer.

---

## Compatibility and Versioning
`niri-state` is not the protocol authority; `niri-pypc` is.

Therefore release compatibility should be expressed in terms of:
- compatible `niri-pypc` versions,
- and, transitively, the upstream `niri-ipc` pin(s) exposed by those versions.

### Compatibility rules
1. `niri-state` should declare an explicit compatible range or exact requirement for `niri-pypc`.
2. Public state model or selector breaking changes require normal package versioning discipline.
3. Release notes should state the compatible `niri-pypc` version(s) and corresponding upstream protocol pin(s).

---

## Proposed Repository Layout
```text
niri-state/
├─ devenv.nix
├─ devenv.yaml
├─ pyproject.toml
├─ README.md
├─ CHANGELOG.md
├─ .gitignore
├─ src/
│  └─ niri_state/
│     ├─ __init__.py
│     ├─ errors.py
│     ├─ config.py
│     ├─ models/
│     │  ├─ __init__.py
│     │  ├─ snapshot.py
│     │  ├─ entities.py
│     │  ├─ change_set.py
│     │  └─ health.py
│     ├─ reducers/
│     │  ├─ __init__.py
│     │  ├─ root.py
│     │  ├─ bootstrap.py
│     │  ├─ outputs.py
│     │  ├─ workspaces.py
│     │  ├─ windows.py
│     │  ├─ focus.py
│     │  └─ invariants.py
│     ├─ selectors/
│     │  ├─ __init__.py
│     │  ├─ outputs.py
│     │  ├─ workspaces.py
│     │  ├─ windows.py
│     │  └─ focus.py
│     ├─ sync/
│     │  ├─ __init__.py
│     │  ├─ bootstrap.py
│     │  ├─ resync.py
│     │  └─ policies.py
│     └─ store/
│        ├─ __init__.py
│        ├─ live_state.py
│        ├─ observers.py
│        └─ waiters.py
└─ tests/
   ├─ reducers/
   ├─ selectors/
   ├─ sync/
   ├─ store/
   ├─ integration/
   ├─ replay/
   └─ live/
```

---

## Testing Strategy
The testing strategy should treat reducers and convergence behavior as first-class surfaces.

## 1. Reducer tests
Location:
- `tests/reducers/`

### Required categories
- per-event reducer correctness,
- add/update/remove flows,
- focus/active state transitions,
- invariants after each transition,
- unknown/unsupported event handling,
- no-op behavior where appropriate.

## 2. Selector tests
Location:
- `tests/selectors/`

### Required categories
- direct lookups,
- relationship selectors,
- aggregate selectors,
- empty/missing cases,
- selector stability across revisions.

## 3. Bootstrap/sync tests
Location:
- `tests/sync/`

### Required categories
- initial query suite to first snapshot,
- buffered-event replay during bootstrap,
- disconnect during bootstrap,
- resync from stale state,
- version/compatibility mismatch behavior.

## 4. Store/waiter tests
Location:
- `tests/store/`

### Required categories
- snapshot visibility semantics,
- change stream behavior,
- selector watch behavior,
- timeout/cancellation of waits,
- close/fail/stale behavior for consumers.

## 5. Replay tests
Location:
- `tests/replay/`

### Required categories
- recorded trace replay,
- regression traces for previously fixed bugs,
- convergence on long event sequences,
- deterministic revision history for identical inputs.

## 6. Integration tests
Location:
- `tests/integration/`

Use `niri-pypc` against a mock or controlled Niri-like server/session to verify end-to-end bootstrap and state updates.

### Required categories
- live state tracking over command + event flow,
- desync detection,
- resync success/failure,
- compatibility metadata propagation,
- change emission ordering.

## 7. Live tests
Location:
- `tests/live/`

Gated by environment such as `NIRI_SOCKET`.

### Required categories
- bootstrap against a running compositor,
- event-driven state updates during real compositor activity,
- focus/workspace/window transitions,
- manual refresh/resync smoke tests.

---

## CI Quality Gates
Required gates should include:
1. reducer test suite passes,
2. selector test suite passes,
3. bootstrap/store integration suite passes,
4. replay trace suite passes,
5. lint/type/import-boundary checks pass,
6. dependency guard confirms one-way dependency on `niri-pypc`,
7. live smoke tests run in suitable environments when available.

Optional but valuable:
- benchmark subset for hot selector/reducer paths,
- fixture trace minimization checks,
- property-based tests for reducer invariants.

---

## Documentation Plan
The repo should include:
1. a high-level README,
2. a bootstrap/resync behavior guide,
3. a reducer and selector authoring guide,
4. examples for snapshots, selectors, and waits,
5. guidance on observed truth vs desired policy.

### README should clearly explain
- `niri-state` depends on `niri-pypc`,
- `niri-pypc` owns the protocol/runtime layer,
- `niri-state` owns live reduced state,
- the library exposes snapshots/selectors/waits rather than raw transport,
- stale/desync behavior is explicit,
- and higher-level policy/orchestration remains outside this library.

---

## Recommended Immediate Implementation Plan
### Phase A: Repository skeleton
1. create repo layout,
2. add `pyproject.toml`,
3. add `devenv.nix` scripts,
4. wire dependency on `niri-pypc`.

Exit criteria:
- environment works,
- package imports,
- dependency boundaries are in place.

### Phase B: State models and reducers
1. define snapshot/entity/change/health models,
2. implement root reducer and first domain reducers,
3. add invariant checks.

Exit criteria:
- reducer tests pass for core domains.

### Phase C: Bootstrap and live store
1. implement coordinated bootstrap over `niri-pypc`,
2. buffer/replay bootstrap-window events,
3. publish atomic snapshots,
4. expose current snapshot and change stream.

Exit criteria:
- integration tests reach stable live state.

### Phase D: Selectors and waiting APIs
1. implement core selectors,
2. implement selector watch and wait helpers,
3. finalize timeout/cancellation semantics.

Exit criteria:
- selector/store tests pass.

### Phase E: Desync and resync behavior
1. finalize stale-state policy,
2. implement resync coordinator,
3. expose diagnostics and health transitions.

Exit criteria:
- stale/resync scenarios are test-covered and predictable.

### Phase F: Replay/live hardening
1. add recorded trace replay suite,
2. add live smoke coverage,
3. document guarantees and limitations.

Exit criteria:
- replay and live suites provide confidence in convergence behavior.

---

## Design Principles to Preserve
1. **Observed truth before convenience**
2. **No silent drift after unknown inputs**
3. **Pure reducers before orchestration**
4. **Atomic snapshots, never partial public state**
5. **Replayability as a correctness tool**
6. **Explicit health/resync behavior**
7. **Strict layering over `niri-pypc`**

---

## Summary Recommendation
`niri-state` should be a dedicated downstream Python library that:
- depends on `niri-pypc` for protocol/runtime behavior,
- builds a coherent live compositor state model from bootstrap queries plus the event stream,
- exposes immutable snapshots, selectors, and wait/observe APIs,
- treats unknown/unsupported changes as explicit correctness events rather than silently ignoring them,
- and makes desync/resync semantics part of the public contract.

That gives the ecosystem a clean middle layer between:
- raw protocol/runtime correctness in `niri-pypc`,
- and higher-level orchestration/UI/policy libraries above it.
