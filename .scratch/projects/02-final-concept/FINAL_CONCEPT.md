# FINAL_CONCEPT

Final architecture contract for `niri-state`, fully revised per `FINAL_CONCEPT_ANALYSIS.md` and grounded in `niri-pypc` dependency reality.

## Table of Contents

1. Authority and Scope
- Defines this document’s role and canonical source order.

2. Reality Framing and Complexity Budget
- Grounds architecture choices in the actual domain size, event volume, and operational needs.

3. Identity, Layering, and Package Strategy
- Confirms package identity, dependency direction, and internal core/runtime boundary strategy.

4. Core Goals
- Lists non-negotiable product outcomes.

5. Non-Goals and Deferred Architecture
- States explicit exclusions and deferrals.

6. Dependency Contracts from `niri-pypc`
- Captures upstream behavior `niri-state` must conform to.

7. State Truth and Freshness Semantics
- Defines what `niri-state` can claim as live versus refresh-backed or query-only.

8. High-Level Architecture
- Describes the end-to-end runtime and data-flow model.

9. Internal Package Structure
- Defines module organization that enforces a pure core and async runtime shell.

10. Snapshot Model and Lifecycle FSM
- Specifies immutable snapshot shape, revisioning, diagnostics, and legal health transitions.

11. Reduction Model
- Defines reducer purity, dispatch approach, event handling policy, and index strategy.

12. Bootstrap and Race Closure Contract
- Defines query normalization, initial snapshot creation, and buffered event replay guarantees.

13. Publication, Subscription, and Wait/Watch Contract
- Specifies store publication semantics and consumer-facing reactive behavior.

14. Error and Configuration Contract
- Specifies error hierarchy, policy knobs, and strict-mode normalization behavior.

15. Testing and Verification Contract
- Defines required confidence gates for reducer correctness and runtime behavior.

16. Implementation Phasing
- Provides concrete execution order from concept to deliverable implementation.

17. Final Invariants
- Lists architectural rules that must remain true over time.

## 1. Authority and Scope

`FINAL_CONCEPT.md` is the governing architecture contract for `niri-state` implementation planning and execution.

Canonical truth order:
1. Actual `niri-pypc` behavior (code/tests) as dependency reality.
2. This `FINAL_CONCEPT.md`.
3. Supporting planning and analysis docs.

If planning text conflicts with `niri-pypc` behavior, planning is wrong and must be updated.

## 2. Reality Framing and Complexity Budget

`niri-state` is a focused state tracker for one compositor instance, with a small domain surface and human-scale event rates. It is not a distributed system, durable event store, or generalized state platform.

Implications:
1. Prefer minimal, explicit architecture over speculative abstraction.
2. Optimize first for correctness and debuggability, then ergonomics.
3. Defer complexity unless concrete usage requires it.

## 3. Identity, Layering, and Package Strategy

- Package: `niri-state` (`niri_state`).
- Role: derive, publish, and query observed compositor state.
- Dependency direction: `niri-state -> niri-pypc` only.

Package strategy:
1. Ship one package now.
2. Enforce an internal boundary:
- `_core/`: pure domain logic.
- `_runtime/`: async IO/lifecycle orchestration.
3. Keep extraction to separate packages as a future option, not current scope.

## 4. Core Goals

1. Deterministic reduction from bootstrap payload plus ordered event stream.
2. Atomic immutable snapshot publication for every revision.
3. Explicit lifecycle/health semantics with auditable transitions.
4. Consumer ergonomics via selectors, subscriptions, and waits.
5. Strict alignment with `niri-pypc` runtime/protocol contracts.
6. Replayable behavior for regression and integration confidence.

## 5. Non-Goals and Deferred Architecture

Not in scope for the initial implementation:
1. Separate `core` and `runtime` distributions.
2. Append-only internal event log as system source of truth.
3. Type-wrapper freshness encoding (`Live[T]`, etc.).
4. Full protocol-to-domain event adapter layer.
5. Declarative condition DSL replacing predicate waits.
6. Snapshot checkpointing or durable fast-recovery cache.
7. Unknown-event semantic guessing/adapters.

These may be revisited only when real usage pressure justifies complexity.

## 6. Dependency Contracts from `niri-pypc`

Design assumptions `niri-state` must honor:
1. Request client behavior is short-lived request/reply per call.
2. Event stream is long-lived and queue-backed.
3. Backpressure modes exist; strict correctness relies on fail-fast semantics.
4. Bundle open sequence yields client + event stream with failure cleanup guarantees.
5. Request responses are typed payload variants; error replies surface as raised errors.
6. Unknown event variants can surface and must be policy-handled.
7. Event surface includes workspace/window/focus/keyboard/overview and metadata-style events (`ConfigLoaded`, `ScreenshotCaptured`, etc.).
8. Query payload shapes (dict/list/nullability) must be normalized exactly before snapshot construction.

## 7. State Truth and Freshness Semantics

`niri-state` models observed truth, not authoritative compositor internals.

Domain classes:
1. Event-reduced live domains: windows, workspaces, focus, keyboard layouts, overview.
2. Refresh-backed domains: outputs.
3. Query-only domains: surfaces without event coverage (for example, layers).

Freshness signaling strategy:
1. Health state and diagnostics on snapshots.
2. Selector naming/docs that reflect domain freshness limits.
3. No claim of stronger freshness than event coverage supports.

## 8. High-Level Architecture

Core runtime flow:
1. Bootstrap opens bundle, executes query suite, normalizes responses.
2. Snapshot builder constructs base snapshot and indexes.
3. Buffered bootstrap-window events replay through the same root reducer.
4. Store publishes immutable snapshots with changeset metadata.
5. Subscribers, selector watches, and waits react to publications.
6. Resync coordinator handles stale/resync transitions and recovery.

Design principle: pure core, async shell.

## 9. Internal Package Structure

Target structure:

```text
src/niri_state/
  __init__.py
  _version.py
  config.py
  errors.py
  _core/
    models/
    reducers/
    invariants.py
    snapshot_builder.py
  _runtime/
    bootstrap.py
    store.py
    broadcaster.py
    waiters.py
    resync.py
  selectors/
    *.py
```

Rules:
1. `_core` has no runtime IO concerns.
2. `_runtime` owns async, stream consumption, lifecycle transitions.
3. `selectors/` remain pure and publicly importable.

## 10. Snapshot Model and Lifecycle FSM

Snapshot contract:
1. Immutable published object.
2. Monotonic revision increments per publication.
3. Entity maps for outputs/workspaces/windows keyed for direct lookup.
4. Focus pointers as nullable ids/names.
5. Precomputed indexes for common selector access.
6. Diagnostics and compatibility metadata included.

Lifecycle states:
- `BOOTSTRAPPING`, `LIVE`, `STALE`, `RESYNCING`, `CLOSED`, `FAILED`.

FSM contract:
1. Legal transitions are explicit and enforced.
2. Every transition carries a reason for diagnostics.
3. Invalid transitions are rejected as lifecycle errors.
4. State mutation remains single-task owned.

## 11. Reduction Model

Reducer requirements:
1. Pure deterministic functions; no IO, no side-effecting commands.
2. Explicit root dispatch over concrete event variants.
3. Unknown/unimplemented impactful inputs use configured policy (`stale`, `fail`, or tightly controlled `ignore`).
4. Invariants run after applied transitions.
5. Same inputs must always produce same outputs.

State assembly approach:
1. Apply events into a mutable draft representation.
2. Recompute/update required indexes.
3. Freeze into immutable snapshot before publication.

Event semantics:
1. Replace-all events (`WindowsChanged`, `WorkspacesChanged`) are authoritative.
2. Incremental events upsert/remove/update domain entities deterministically.
3. Metadata-style events are explicitly no-op/diagnostic, never accidental fallthrough.

## 12. Bootstrap and Race Closure Contract

Required bootstrap sequence:
1. Normalize config and strict-mode behavior.
2. Open connection bundle.
3. Start event buffering immediately.
4. Execute initial query plan.
5. Normalize responses into `BootstrapPayload`.
6. Build and validate base snapshot.
7. Replay buffered events through root reducer.
8. Revalidate and publish first `LIVE` snapshot.

Race closure rule:
- No live snapshot publication before buffer replay completes successfully.

## 13. Publication, Subscription, and Wait/Watch Contract

Store publication model:
1. One runtime task owns snapshot mutation/publication.
2. Published unit is `ChangeSet` + immutable snapshot reference.
3. Subscriber queues are bounded with configurable overflow policy.

Public behavior:
1. `snapshot()` returns current immutable snapshot.
2. `subscribe()` yields state changes.
3. `watch(selector)` emits selector values on value change.
4. `wait_until(predicate, timeout, health_policy)` blocks until satisfied or timeout/close.
5. `refresh()` triggers manual recovery bootstrap.
6. `close()` terminates runtime and subscriptions predictably.

## 14. Error and Configuration Contract

Error taxonomy must include:
1. Configuration errors.
2. Bootstrap/normalization failures.
3. Reduction/invariant failures.
4. Desync/resync failures.
5. Subscription overflow and wait timeout lifecycle errors.

Configuration policy surface:
1. Correctness mode (`strict`, `best_effort`).
2. Resync policy (`manual`, `auto`).
3. Unknown event policy.
4. Invariant failure policy.
5. Wait health policy.
6. Subscriber queue sizing/overflow policy.

Strict-mode normalization rule:
- If strict correctness is requested, runtime backpressure configuration is normalized to fail-fast behavior.

## 15. Testing and Verification Contract

Required confidence gates:
1. Reducer unit tests for all handled event variants.
2. Invariant tests for valid and invalid snapshots.
3. Bootstrap response normalization tests.
4. Store lifecycle tests covering transitions and closure behavior.
5. Wait/watch behavior tests for timeout, cancellation, and health-policy filtering.
6. Replay-trace regression tests using real reducer path.
7. Integration tests for bootstrap + stream + replay convergence.

Priority rule:
- Reducer correctness is foundational and takes precedence.

## 16. Implementation Phasing

Recommended order:
1. `config.py`, `errors.py`, base model types.
2. Snapshot models, indexes, invariants, lifecycle FSM.
3. Domain reducers + root reducer dispatch.
4. Bootstrap normalization and builder pipeline.
5. Store publication path + broadcaster.
6. Wait/watch APIs.
7. Resync coordination.
8. Selector module completion and ergonomic re-exports.
9. Replay/integration hardening and docs alignment.

## 17. Final Invariants

These must remain true:
1. No freshness claim beyond event/query coverage reality.
2. Unknown impactful input cannot silently preserve `LIVE` correctness claims.
3. Publication is atomic; snapshots are immutable.
4. Core reducers/selectors/invariants remain pure.
5. State mutation is runtime-single-owner.
6. Dependency direction remains one-way to `niri-pypc`.
7. Behavior remains testable via deterministic replay and integration flows.
