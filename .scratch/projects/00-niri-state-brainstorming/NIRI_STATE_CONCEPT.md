Below is a rewritten `NIRI_STATE_CONCEPT` aligned to the current attached `niri-pypc` implementation. It preserves the original architecture, but narrows the live-state contract to what the actual dependency can support today.    

# NIRI_STATE_CONCEPT

## Authority and Scope

This document is the guiding concept for **`niri-state`**.

`niri-state` is a downstream Python library built on top of **`niri-pypc`**. It owns:

* initial state bootstrap,
* event application,
* live reduced compositor state,
* immutable snapshots,
* selectors,
* waiting and observation APIs,
* health and desync tracking,
* and resync coordination.

It does **not** own:

* protocol schema generation,
* transport or socket lifecycle,
* raw wire codecs,
* raw request or event decoding,
* or the authoritative IPC type surface.

This concept assumes:

* the attached `niri-pypc` implementation is the canonical truth,
* `niri-pypc` remains the pinned protocol/runtime dependency,
* `niri-pypc` owns typed requests, typed response wrappers, typed events, and socket/runtime behavior,
* `niri-state` consumes those types and derives observed state from them,
* and higher-level libraries/apps may depend on both.

---

## Project Identity

### Library name

* **Project name:** `niri-state`
* Suggested import root: `niri_state`

### Naming rationale

The name intentionally communicates:

* **Niri** as the compositor authority,
* **state** as the library’s responsibility,
* and a reduced, coherent, queryable model rather than a raw protocol surface.

---

## Core Goals

1. **High-confidence observed state**

   * Maintain a coherent in-memory view of compositor state derived from bootstrap queries plus the live event stream.
   * Never silently invent state that is not justified by protocol data.

2. **Tight alignment with the real `niri-pypc` implementation**

   * Design around the actual current request, response, event, bundle, and lifecycle behavior exposed by the attached dependency.
   * Do not assume features that exist only in aspirational docs.

3. **Deterministic reducer behavior**

   * Given the same bootstrap payload and the same ordered event sequence, the library must produce the same snapshots and revision history.

4. **Atomic snapshots**

   * Consumers read immutable snapshots representing one coherent revision.
   * Partial application must never leak into the public surface.

5. **Explicit correctness boundaries**

   * Unknown events, queue overflow, invariant failure, transport loss, and refresh-backed domains must all have explicit semantics.
   * The library must not continue claiming fully live correctness when that guarantee is no longer defensible.

6. **Ergonomic read/query APIs**

   * Common lookups should be easy and typed.
   * Selectors and wait helpers should support orchestration without forcing applications to reimplement state plumbing.

7. **Replayable correctness**

   * Reducers, selectors, and convergence behavior should be testable from recorded traces.

---

## Non-Goals

1. Owning raw Niri IPC transport, framing, socket lifecycle, or decode/encode logic.
2. Replacing `niri-pypc` as the authoritative protocol/runtime layer.
3. Planning actions, expressing UI/business policy, or deciding desired layout outcomes.
4. Silently recovering from unsupported or unknown events by guessing state changes.
5. Acting as a durable database or long-term history store.
6. Pretending every queryable protocol surface is equally live.
7. Supporting arbitrary untyped dict-based event ingestion as a primary public API.

---

## Relationship to `niri-pypc`

`niri-state` depends on `niri-pypc` and should be treated as a downstream companion library, not as a sibling protocol implementation.

### `niri-pypc` owns

* the pinned upstream protocol alignment,
* generated protocol types,
* typed request models,
* typed response wrapper models,
* typed event models,
* event decoding and delivery,
* command/event socket behavior,
* bundle lifecycle,
* and runtime error handling.

### `niri-state` owns

* coordinated bootstrap,
* response normalization into reducer input,
* event application,
* immutable snapshots,
* selectors and query helpers,
* waiting and observation APIs,
* health and desync tracking,
* and resync coordination.

### External dependency direction

```text
niri-state -> niri-pypc
higher-level apps/libraries -> niri-state, niri-pypc
niri-pypc -X-> niri-state
```

The one-way dependency is a hard architectural rule.

---

## Source-of-Truth Model

`niri-state` models **observed compositor truth**, not desired truth.

That means:

* the library reflects what Niri has reported through `niri-pypc`,
* it may derive deterministic indexes and conveniences from observed data,
* but it must not speculate about pending actions, user intent, or desired future layout.

Examples of valid derived state:

* lookup maps keyed by protocol identifiers,
* focused window/output/workspace pointers,
* per-output active workspace relationships,
* normalized ordering indexes,
* revision counters,
* health flags,
* and selector-friendly aggregates that are purely computed from observed state.

Examples of invalid state for this layer:

* planned layout transitions,
* action queues,
* desired policy overlays,
* guessed visibility semantics without a clear derivation rule,
* or claims of live correctness for domains that are only queryable.

---

## High-Level Architecture

`niri-state` is organized into five major concerns.

### 1. Bootstrap and synchronization

Responsible for obtaining the first coherent state using `niri-pypc` request and event-stream APIs.

Responsibilities:

* open a coordinated command + event bundle through `niri-pypc`,
* begin consuming and buffering typed events,
* execute an explicit query plan,
* normalize typed response wrappers into an internal bootstrap payload,
* build the base snapshot,
* replay buffered events in order,
* and publish the first live revision only after replay completes successfully.

### 2. Reducer engine

Responsible for deterministic event application.

Responsibilities:

* apply typed `niri-pypc` event variants to normalized state,
* enforce invariants,
* produce change metadata,
* distinguish supported, unsupported, and unknown inputs,
* and remain pure and side-effect free.

### 3. Snapshot/state model

Responsible for the public in-memory representation.

Responsibilities:

* define immutable snapshot types,
* expose normalized entity collections,
* carry revision, health, and diagnostics metadata,
* expose typed focused/active relationships,
* and keep raw protocol payloads available where they remain the authoritative source.

### 4. Selector/query layer

Responsible for read ergonomics.

Responsibilities:

* provide common lookups and filters,
* concentrate derived query logic outside application code,
* remain deterministic and side-effect free,
* and avoid embedding action policy.

### 5. Observation, waiting, and resync coordination

Responsible for long-lived live usage.

Responsibilities:

* publish change notifications,
* support `wait_until` / `wait_for_selector` style APIs,
* expose health transitions,
* coordinate refresh/resync,
* and settle consumers predictably on close or failure.

---

## State Model Design

The public state surface should use **hand-written Pydantic models** consistently.

### Design priorities

1. Strong typing over free-form dicts.
2. Immutable public snapshots.
3. Normalized entities plus convenient derived indexes.
4. Stable equality and revision semantics.
5. Machine-friendly diagnostics when correctness breaks.
6. Clear distinction between:

   * **event-reduced live domains**,
   * **refresh-backed domains**,
   * and **query-only optional domains**.

### Core live domains

Based on the current `niri-pypc` implementation, `niri-state` should treat these as primary live state domains:

* windows,
* workspaces,
* focused window,
* focused output,
* focused workspace,
* active workspace relationships,
* keyboard layouts,
* overview state,
* and config-load / store diagnostics.

These domains are suitable for reducer-driven incremental updates.

### Refresh-backed domains

Some protocol surfaces are useful to expose but should not be represented as fully reducer-backed live truth.

#### Outputs

Outputs may be bootstrapped and kept partially current through workspace relationships, but raw output configuration should be treated as **refresh-backed** unless the current event model can justify live updates.

That means:

* outputs may appear in the snapshot,
* but `niri-state` must not promise that every output field remains incrementally current forever without refresh.

### Optional query-only domains

#### Layers

Layers are queryable in the protocol surface, but the current `niri-pypc` event model does not provide a corresponding live layer event stream.

Therefore, layers should be either:

* omitted from the initial `niri-state` v1 core snapshot,
* or exposed only as an explicitly non-live query/refresh-backed surface.

They should not be presented as first-class live reducer-backed state unless the upstream event surface changes.

### Suggested top-level snapshot shape

A `NiriSnapshot` should include, conceptually:

* protocol/runtime compatibility metadata,
* snapshot revision,
* bootstrap status,
* health/state freshness status,
* outputs,
* workspaces,
* windows,
* keyboard layouts,
* overview state,
* focused output name,
* focused workspace id,
* focused window id,
* per-output active workspace relationships,
* diagnostics,
* and last-good revision metadata.

### Entity modeling guidance

* Store entities in normalized mappings keyed by protocol identifiers.
* Preserve protocol identifiers directly whenever possible.
* Carry raw `niri_pypc.types` models inside entity models where those raw models remain authoritative.
* Derived ordering should be explicit rather than implicit in dict iteration.

### Important semantic correction: focused vs active

The current library should not collapse `focused` and `active` into one global concept.

Recommended model:

* one global **focused window**,
* one global **focused output**,
* one global **focused workspace**,
* and **active workspaces tracked per output** when protocol semantics permit multiple active workspaces across outputs.

Avoid a design that assumes one singular global active workspace unless the actual observed protocol surface justifies it.

### Public immutability rule

Snapshots exposed to consumers must be treated as immutable.

Once a snapshot is published for revision `N`, it never mutates. Revision `N+1` is a new coherent snapshot.

---

## Snapshot Health and Lifecycle

`niri-state` should expose explicit lifecycle and health states such as:

* `bootstrapping`
* `live`
* `stale`
* `resyncing`
* `closed`
* `failed`

### Health semantics

* **bootstrapping**: initial sync is in progress; no coherent public state has been established yet.
* **live**: event-reduced domains are coherent and advancing normally.
* **stale**: state is readable but no longer guaranteed correct enough to claim live coherence.
* **resyncing**: a fresh bootstrap/refresh is in progress.
* **closed**: the store has been shut down intentionally.
* **failed**: a terminal unrecoverable error occurred.

This health signal is part of the public contract.

### Live guarantee rule

`live` means:

* reducer-backed domains are coherent,
* no known correctness break has occurred,
* and upstream event delivery has not violated the library’s correctness assumptions.

It does **not** mean every query-only or refresh-backed domain is fully current at all times.

---

## Bootstrap and Synchronization Strategy

The initial synchronization workflow is the center of the library.

### Core problem

Because command and event flow are separate concerns in `niri-pypc`, `niri-state` must avoid races between:

* taking the initial query snapshot,
* and receiving live events during bootstrap.

### Required bootstrap sequence

1. Open a `NiriConnectionBundle` via `niri-pypc`.
2. Start event consumption immediately.
3. Buffer typed event variants in FIFO order.
4. Execute the explicit initial query suite using the command client.
5. Normalize typed response wrappers into an internal bootstrap payload.
6. Build the base normalized snapshot from query results.
7. Replay buffered events through the same reducer pipeline used for live events.
8. Publish the first `live` snapshot only after replay completes successfully.

### Bootstrap rule

The library must not publish a `live` snapshot until the race window has been closed according to the chosen synchronization strategy.

### Typed response normalization rule

The current `niri-pypc` implementation returns typed response wrapper models rather than naked payloads.

Therefore bootstrap must include an explicit normalization stage that:

* matches each response variant,
* extracts payload fields,
* and converts those into a reducer-friendly bootstrap payload.

This normalization step is part of `niri-state`’s responsibility.

### Initial query suite

The query plan should remain explicit and versioned. It should cover only domains that `niri-state` actually models.

Typical included surfaces:

* outputs,
* workspaces,
* windows,
* focused output,
* focused window,
* keyboard layouts,
* overview state,
* and optional query-only surfaces where desired.

### Correctness-preserving backpressure rule

The current `niri-pypc` event stream has its own bounded queue before `niri-state` sees events.

Because of that, `niri-state` must distinguish two modes:

#### Correctness-preserving mode

* require upstream `niri-pypc` event backpressure to be configured as **fail-fast**,
* treat any upstream overflow as a desync trigger,
* and only present the store as coherent live state in this mode.

#### Best-effort mode

* allow upstream drop-oldest behavior only if explicitly configured,
* but do not present that mode as equivalent to correctness-preserving live state.

The recommended default for `niri-state` is correctness-preserving mode.

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

* domain reducers for windows, workspaces, focus, keyboard, overview, and refresh-backed metadata,
* a root reducer that dispatches by concrete event variant type,
* invariant checks after each applied change,
* and a shared normalization layer for bootstrap payloads.

### Bootstrap consistency rule

Where practical, bootstrap data should enter the state model through the same normalization and reduction paths used by live events. That reduces drift between initial load and incremental update behavior.

### Invariant examples

* focused window references a known window when present,
* focused workspace references a known workspace when present,
* focused output references a known output when present,
* workspace-to-output relationships are internally consistent,
* active workspace relationships are internally consistent,
* entity uniqueness constraints hold,
* and removal/update flows do not leave dangling references.

Invariant failures must not be ignored.

---

## Change Model

Each successful state transition should produce a typed `ChangeSet` or equivalent metadata object.

A `ChangeSet` should include, conceptually:

* old revision,
* new revision,
* transition cause (`bootstrap`, `event`, `manual_refresh`, `auto_resync`, `close`, `failure`),
* applied event type where relevant,
* affected domains where useful,
* health transition if any,
* and access to the new snapshot.

The goal is to support:

* async observers,
* selector subscriptions,
* debug logging,
* replay tests,
* and higher-level orchestration.

---

## Unknown and Unsupported Event Policy

`niri-pypc` may decode inbound unknown variants into explicit unknown sentinel models. `niri-state` must define what those mean for state correctness.

### Recommended policy

For `niri-state`, prefer:

* strict known-event reduction,
* no silent ignore of unknown or unsupported state-affecting inputs,
* transition to `stale` on unknown or unsupported reducer inputs by default,
* and optional auto-resync when configured.

### Rationale

A state library has a stronger correctness burden than a raw protocol library. Preserving an unknown inbound event for diagnostics is useful, but continuing to claim that state is definitely correct after an unhandled change is risky.

### Recommended default

Use **stale-and-observable** as the default public behavior:

* preserve the last coherent snapshot,
* record diagnostics,
* expose health as `stale`,
* and require explicit refresh or configured auto-resync.

---

## Resync Strategy

Resynchronization should be a first-class feature.

### Why `niri-state` owns resync

The current `niri-pypc` implementation does not own reconnection policy or state recovery policy.

Therefore `niri-state` must own:

* refresh orchestration,
* fresh bundle creation,
* stale-to-live recovery,
* and retry/failure policy.

### Resync triggers

* transport disconnect,
* upstream fail-fast event-stream overflow,
* unknown event,
* invariant failure,
* manual refresh request,
* or any other condition that breaks the library’s live correctness guarantee.

### Resync policies

#### Manual only

* mark stale,
* expose diagnostics,
* do not automatically resync.

#### Auto-resync

* transition to `resyncing`,
* perform a fresh bootstrap,
* publish a new live revision if successful,
* otherwise remain `stale` or transition to `failed` based on configuration.

### Resync contract

A successful resync produces a new coherent snapshot revision and never mutates older snapshots in place.

---

## Selector and Query Design

Selectors are a major reason the library exists.

### Selector rules

1. Selectors are pure.
2. Selectors accept a snapshot and return typed results.
3. Selectors do not perform I/O.
4. Selectors do not mutate state.
5. Selectors should prefer composability over giant convenience surfaces.

### Recommended selector categories

* direct lookup selectors: `workspace_by_id`, `window_by_id`, `output_by_name`
* relationship selectors: `windows_on_workspace`, `workspaces_on_output`
* focus selectors: `focused_window`, `focused_workspace`, `focused_output`
* active relationship selectors: `active_workspaces_on_output`
* aggregate selectors grounded in observed data only

### Selector caution

Selectors should avoid promising semantics that are not clearly grounded in the current protocol surface.

Examples:

* a “visible windows” selector is acceptable only if visibility is carefully and explicitly defined from observed fields,
* a singular global “active workspace” selector is discouraged unless that meaning is clearly justified by the current event model.

---

## Waiting and Observation APIs

A live state library should support both pull and push usage.

### Pull-oriented APIs

Suggested concepts:

* `state.current()` -> returns the latest published snapshot
* `await state.snapshot()` -> returns a coherent snapshot, optionally waiting for `live`
* `state.health()` -> returns current lifecycle state

### Push-oriented APIs

Suggested concepts:

* `async for change in state.changes(): ...`
* `async for value in state.watch_selector(selector): ...`

### Waiting APIs

Suggested concepts:

* `await state.wait_until(predicate, timeout=...)`
* `await state.wait_for_selector(selector, predicate=..., timeout=...)`

### Waiting semantics

* waits should be event-driven rather than polling-based,
* timeouts and cancellation should be explicit,
* waiting on a stale or failed store should fail predictably unless configured otherwise,
* and waits should operate on coherent snapshots only.

---

## Public API Concept

The public API should be small and disciplined.

### Live state API

```python
async with NiriState.connect(config) as state:
    snapshot = await state.snapshot()
    focused = snapshot.focused_window_id
```

### Change observation API

```python
async with NiriState.connect(config) as state:
    async for change in state.changes():
        print(change.new_revision, change.domains)
```

### Wait helper API

```python
async with NiriState.connect(config) as state:
    await state.wait_until(lambda s: s.focused_window_id is not None, timeout=5.0)
```

### Selector watch API

```python
async with NiriState.connect(config) as state:
    async for output in state.watch_selector(selectors.focused_output):
        print(output)
```

### Important behavioral rule

The API should present coherent state, not raw transport behavior. But it must not conceal correctness boundaries such as stale state, resync, refresh-backed domains, or bootstrap incompleteness.

---

## Dependency Rules

Allowed dependency direction, conceptually:

```text
store/live API -> sync, reducers, selectors, models, errors, niri-pypc
sync -> reducers, models, errors, niri-pypc
reducers -> models, errors, niri-pypc types
selectors -> models
models -> internal helpers only
errors -> no internal deps
```

Forbidden couplings:

1. `niri-state` must not reimplement transport/runtime concerns that belong to `niri-pypc`.
2. Reducers must not import application/business policy modules.
3. Selectors must not perform I/O or issue commands.
4. Public convenience APIs must not bypass health and reducer rules.
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
8. `CompatibilityError`

Suggested context fields:

* revision,
* last good revision,
* health state,
* event type,
* selector name or predicate label,
* resync policy,
* compatibility metadata,
* wrapped cause,
* and bounded diagnostic payload excerpts where relevant.

The library should preserve enough context to explain whether a problem was:

* protocol/runtime-originated in `niri-pypc`,
* reducer/invariant-originated in `niri-state`,
* or a freshness/health contract problem for a state consumer.

---

## Compatibility and Versioning

`niri-state` is not the protocol authority; `niri-pypc` is.

But `niri-state` should not assume that `niri-pypc` has already enforced every runtime compatibility check on its behalf.

### Compatibility rules

1. `niri-state` should declare an explicit compatible range or exact requirement for `niri-pypc`.
2. `niri-state` may perform an explicit compositor version query during bootstrap if it wants runtime compatibility metadata.
3. `niri-state` should surface compatibility metadata in snapshots.
4. Public state model or selector breaking changes require normal package versioning discipline.
5. Release notes should state the compatible `niri-pypc` version(s) and corresponding upstream protocol pin(s).

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
│     │  ├─ windows.py
│     │  ├─ workspaces.py
│     │  ├─ focus.py
│     │  ├─ keyboard.py
│     │  ├─ overview.py
│     │  └─ invariants.py
│     ├─ selectors/
│     │  ├─ __init__.py
│     │  ├─ outputs.py
│     │  ├─ workspaces.py
│     │  ├─ windows.py
│     │  ├─ focus.py
│     │  └─ aggregates.py
│     ├─ sync/
│     │  ├─ __init__.py
│     │  ├─ bootstrap.py
│     │  ├─ resync.py
│     │  └─ policies.py
│     └─ store/
│        ├─ __init__.py
│        ├─ live_state.py
│        ├─ broadcaster.py
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

The testing strategy should treat reducers, synchronization, and convergence behavior as first-class surfaces.

## 1. Reducer tests

Location:

* `tests/reducers/`

### Required categories

* per-event reducer correctness,
* add/update/remove flows,
* focus and workspace relationship transitions,
* keyboard and overview transitions,
* invariants after each transition,
* unknown/unsupported event handling,
* no-op behavior where appropriate.

## 2. Selector tests

Location:

* `tests/selectors/`

### Required categories

* direct lookups,
* relationship selectors,
* aggregate selectors,
* empty/missing cases,
* selector stability across revisions.

## 3. Bootstrap and sync tests

Location:

* `tests/sync/`

### Required categories

* initial query suite to first coherent snapshot,
* buffered-event replay during bootstrap,
* bootstrap failure on upstream or local overflow,
* disconnect during bootstrap,
* resync from stale state,
* compatibility metadata behavior.

## 4. Store and waiter tests

Location:

* `tests/store/`

### Required categories

* snapshot visibility semantics,
* change stream behavior,
* selector watch behavior,
* timeout and cancellation of waits,
* close/fail/stale behavior for consumers.

## 5. Replay tests

Location:

* `tests/replay/`

### Required categories

* recorded trace replay,
* regression traces for previously fixed bugs,
* convergence on long event sequences,
* deterministic revision history for identical inputs.

## 6. Integration tests

Location:

* `tests/integration/`

Use `niri-pypc` against a mock or controlled Niri-like session to verify end-to-end bootstrap and state updates.

### Required categories

* live state tracking over command + event flow,
* stale transition on unknown or desync-triggering inputs,
* resync success/failure,
* compatibility metadata propagation,
* change emission ordering.

## 7. Live tests

Location:

* `tests/live/`

Gated by environment such as `NIRI_SOCKET`.

### Required categories

* bootstrap against a running compositor,
* event-driven state updates during real compositor activity,
* focus/workspace/window transitions,
* manual refresh/resync smoke tests.

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

* benchmark subset for hot selector/reducer paths,
* fixture trace minimization checks,
* property-based tests for reducer invariants.

---

## Documentation Plan

The repo should include:

1. a high-level README,
2. a bootstrap/resync behavior guide,
3. a reducer and selector authoring guide,
4. examples for snapshots, selectors, and waits,
5. guidance on live vs refresh-backed domains,
6. and guidance on observed truth vs desired policy.

### README should clearly explain

* `niri-state` depends on `niri-pypc`,
* `niri-pypc` owns the protocol/runtime layer,
* `niri-state` owns live reduced state,
* not every queryable protocol surface is equally live,
* stale/desync behavior is explicit,
* and higher-level policy/orchestration remains outside this library.

---

## Recommended Immediate Implementation Plan

### Phase A: Repository skeleton

1. create repo layout,
2. add `pyproject.toml`,
3. add `devenv.nix` scripts,
4. wire dependency on `niri-pypc`.

Exit criteria:

* environment works,
* package imports,
* dependency boundaries are in place.

### Phase B: State models and reducers

1. define snapshot, entity, change, and health models,
2. define live domains and refresh-backed domains explicitly,
3. implement root reducer and first domain reducers,
4. add invariant checks.

Exit criteria:

* reducer tests pass for core live domains.

### Phase C: Bootstrap and live store

1. implement coordinated bootstrap over `niri-pypc`,
2. normalize typed response wrappers into bootstrap payloads,
3. buffer and replay bootstrap-window events,
4. require or enforce correctness-preserving upstream backpressure for live mode,
5. publish atomic snapshots,
6. expose current snapshot and change stream.

Exit criteria:

* integration tests reach stable live state.

### Phase D: Selectors and waiting APIs

1. implement core selectors,
2. implement selector watch and wait helpers,
3. finalize timeout/cancellation semantics.

Exit criteria:

* selector and store tests pass.

### Phase E: Desync and resync behavior

1. finalize stale-state policy,
2. implement resync coordinator,
3. expose diagnostics and health transitions.

Exit criteria:

* stale/resync scenarios are test-covered and predictable.

### Phase F: Replay and live hardening

1. add recorded trace replay suite,
2. add live smoke coverage,
3. document guarantees and limitations.

Exit criteria:

* replay and live suites provide confidence in convergence behavior.

---

## Design Principles to Preserve

1. **Observed truth before convenience**
2. **No silent drift after unknown inputs**
3. **Pure reducers before orchestration**
4. **Atomic snapshots, never partial public state**
5. **Replayability as a correctness tool**
6. **Explicit health and resync behavior**
7. **Strict layering over `niri-pypc`**
8. **Live where event-backed, refresh-backed where query-only**

---

## Summary Recommendation

`niri-state` should be a dedicated downstream Python library that:

* depends on `niri-pypc` for protocol/runtime behavior,
* builds a coherent live compositor state model from bootstrap queries plus the event stream,
* exposes immutable snapshots, selectors, and wait/observe APIs,
* treats unknown or unsupported changes as explicit correctness events rather than silently ignoring them,
* distinguishes event-reduced live domains from refresh-backed and query-only domains,
* and makes stale/resync semantics part of the public contract.

That gives the ecosystem a clean middle layer between:

* raw protocol/runtime correctness in `niri-pypc`,
* and higher-level orchestration/UI/policy libraries above it.

The next document to update should be the spec, especially snapshot fields, bootstrap flow, selector names, and the backpressure/correctness contract.
