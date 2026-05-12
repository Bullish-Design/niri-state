# FINAL_IMPLEMENTATION_GUIDE

Implementation runbook for building `niri-state` from zero to done, aligned to:
- `.scratch/projects/02-final-concept/FINAL_CONCEPT.md`
- `.scratch/projects/02-final-concept/FINAL_SPEC.md`
- `.context/niri-pypc` dependency behavior

## Table of Contents

1. How to Use This Guide
- Operating rules, expectations, and definition of workflow discipline.

2. Dependency Reality You Must Honor (`niri-pypc`)
- Concrete upstream contracts this implementation must never violate.

3. Step 0: Workspace and Tooling Bootstrap
- Create baseline package scaffolding and ensure local quality tooling works.

4. Step 1: Define Public Configuration and Error Contracts
- Implement policy enums, config normalization, and state-layer error taxonomy.

5. Step 2: Implement Core Immutable Models
- Build identity aliases, entity wrappers, snapshot model, health/lifecycle, and changesets.

6. Step 3: Implement Lifecycle FSM and Transition Diagnostics
- Enforce legal state transitions and reason tracking for observability.

7. Step 4: Implement Snapshot Builder and Index Construction
- Build deterministic initial snapshot from normalized bootstrap payload.

8. Step 5: Implement Invariant Engine
- Validate referential integrity and consistency guarantees post-build/post-reduce.

9. Step 6: Implement Domain Reducers
- Add deterministic reducers for windows, workspaces, keyboard, and overview.

10. Step 7: Implement Root Reducer + Unknown Event Policy
- Central dispatch, metadata handling, and stale/fail/ignore behavior.

11. Step 8: Implement Bootstrap Query + Normalization Pipeline
- Build race-safe startup path around `NiriConnectionBundle` and query normalization.

12. Step 9: Implement Store Publication and Subscription Runtime
- Single-owner mutation/publish path with bounded subscriber queues.

13. Step 10: Implement Wait/Watch APIs
- Predicate waits and selector watches with timeout/health policy semantics.

14. Step 11: Implement Resync/Recovery Coordinator
- Manual/auto stale recovery with explicit lifecycle transitions.

15. Step 12: Implement Selector Modules and Public Exports
- Stable pure selector API surface aligned with snapshot/index design.

16. Step 13: Integration and Replay Determinism Harness
- Add bootstrap+stream convergence tests and replay trace regression tests.

17. Step 14: API Polish, Docs, and Packaging Finish
- Finalize public ergonomics, docs, and package wiring.

18. Mandatory Validation Matrix (Per Step + Final)
- Required command/test sequence and pass criteria before merge.

19. Intern Handoff Checklist
- Concrete completion checklist to confirm production-readiness.

## 1. How to Use This Guide

1. Follow steps in order. Do not skip ahead.
2. At each step, implement only that scope, then run the listed validation before moving on.
3. If validation fails, fix immediately; do not accumulate unresolved failures.
4. Keep implementation aligned to `FINAL_CONCEPT.md` and `FINAL_SPEC.md`; if code and spec conflict, fix code unless spec is proven wrong by `niri-pypc` reality.
5. Keep `_core` pure and `_runtime` async/orchestration-only at all times.

## 2. Dependency Reality You Must Honor (`niri-pypc`)

These are non-negotiable upstream facts verified from `.context/niri-pypc`:
1. `NiriClient` is one-connection-per-request and returns unwrapped `Response` payloads; compositor `Err` replies raise `RemoteError`.
2. `NiriEventStream` is long-lived and queue-backed with backpressure modes:
- `DROP_OLDEST` drops oldest event on full queue.
- `FAIL_FAST` terminally errors stream with protocol error on queue full.
3. Unknown events decode into `UnknownEvent` sentinel (not a decode crash).
4. `NiriConnectionBundle.open()` creates both client and event stream and cleans up client if event stream creation fails.
5. Event stream `next()` can raise lifecycle or terminal errors and should be treated as runtime health input.
6. Request/reply/event models are generated Pydantic models with specific variant names (`WindowsChanged`, `WorkspacesChanged`, `KeyboardLayoutsChanged`, `OverviewOpenedOrClosed`, etc.).

## 3. Step 0: Workspace and Tooling Bootstrap

Implementation work:
1. Create target package structure under `src/niri_state/` exactly per `FINAL_SPEC.md` section 3.
2. Ensure project metadata (`pyproject.toml`, package name/import path, entry points if any) matches `niri-state` identity.
3. Add base test directories mirroring module layout.
4. Add empty module stubs with `from __future__ import annotations`.

Validation for Step 0:
1. `devenv shell -- uv sync --extra dev`
2. `devenv shell -- python -c "import niri_state"`
3. `devenv shell -- ruff check .`
4. `devenv shell -- ruff format --check .`

Pass criteria:
1. Imports succeed.
2. Lint/format checks are clean with no rule suppressions introduced unnecessarily.

## 4. Step 1: Define Public Configuration and Error Contracts

Implementation work:
1. Implement `config.py` with enums:
- `CorrectnessMode`, `ResyncPolicy`, `UnknownEventPolicy`, `InvariantFailurePolicy`, `WaitHealthPolicy`, `StoreOverflowMode`.
2. Add `NiriStateConfig` including `pypc: NiriConfig` and all runtime policy knobs from spec.
3. Implement config normalization function that enforces strict-mode backpressure normalization to `BackpressureMode.FAIL_FAST` using `dataclasses.replace`.
4. Implement `errors.py` hierarchy:
- `NiriStateError` and required subclasses (`StateConfigError`, `StateLifecycleError`, `BootstrapError`, `ReductionError`, `InvariantError`, `DesyncError`, `ResyncError`, `WatchOverflowError`, `SelectorWaitError`).
5. Ensure `SelectorWaitError` subclasses `TimeoutError`.

Validation for Step 1:
1. Unit tests for config normalization:
- strict mode rewrites upstream backpressure to fail-fast.
- best-effort leaves backpressure unchanged.
- invalid replacement raises `StateConfigError` with chained cause.
2. Unit tests for error inheritance tree and context payload fields.
3. `devenv shell -- ruff check .`
4. `devenv shell -- ruff format --check .`
5. `devenv shell -- ty check .`
6. `devenv shell -- pytest -q tests/...` (targeted for config/errors)

Pass criteria:
1. Policy normalization behavior is deterministic and tested.
2. Errors are typed correctly and chain root causes.

## 5. Step 2: Implement Core Immutable Models

Implementation work:
1. In `_core/models/types.py`, add aliases (`OutputName`, `WorkspaceId`, `WindowId`, `Revision`).
2. In `_core/models/entities.py`, create frozen wrapper models around `niri_pypc` models for output/workspace/window/keyboard/overview state.
3. In `_core/models/health.py`, define lifecycle state enum for snapshot health (`BOOTSTRAPPING`, `LIVE`, `STALE`, `RESYNCING`, `CLOSED`, `FAILED`).
4. In `_core/models/snapshot.py`, define `NiriSnapshot` immutable model with required maps, focus pointers, indexes, diagnostics, compatibility metadata, and revision/timestamp.
5. In `_core/models/changes.py`, define `ChangeSet` contract including revision, cause, changed domains, event metadata, timestamp, snapshot ref.

Validation for Step 2:
1. Unit tests asserting model immutability (mutation attempts fail).
2. Unit tests asserting wrapper identity keys equal map keys used later.
3. Unit tests asserting serialization compatibility where needed for diagnostics/replay traces.
4. `devenv shell -- ruff check .`
5. `devenv shell -- ruff format --check .`
6. `devenv shell -- ty check .`

Pass criteria:
1. Frozen state contract is enforced.
2. Snapshot model contains every required field from final spec.

## 6. Step 3: Implement Lifecycle FSM and Transition Diagnostics

Implementation work:
1. Add lifecycle transition table in core/runtime boundary (wherever `FINAL_SPEC` places enforcement).
2. Implement validation for legal transitions only.
3. Record transition reason and optional context in diagnostics.
4. Raise `StateLifecycleError` on illegal transitions.
5. Guarantee single-owner mutation access (lock or single task ownership invariant).

Validation for Step 3:
1. Tests for every legal transition.
2. Tests for illegal transitions raising `StateLifecycleError`.
3. Test ensuring transition reasons are recorded and visible on resulting snapshot or runtime diagnostics.
4. `devenv shell -- ruff check .`
5. `devenv shell -- ruff format --check .`
6. `devenv shell -- pytest -q tests/...` (targeted lifecycle tests)

Pass criteria:
1. FSM rejects invalid edges deterministically.
2. Transition reason trail is auditable.

## 7. Step 4: Implement Snapshot Builder and Index Construction

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
