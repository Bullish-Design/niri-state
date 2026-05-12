# FINAL_SPEC

Implementation specification for `niri-state`, revised to match `FINAL_CONCEPT.md` and dependency reality from `niri-pypc`.

## Table of Contents

1. Authority and Scope
- Defines specification authority and conflict resolution order.

2. Dependency Contracts (`niri-pypc`)
- Captures concrete upstream runtime/protocol assumptions the implementation must obey.

3. Package Architecture and Boundaries
- Specifies final internal module layout and pure-core/async-runtime separation.

4. Runtime, Typing, and Model Conventions
- Defines Python/runtime constraints and modeling rules.

5. Snapshot Model Specification
- Specifies required snapshot fields, immutability, revisioning, and compatibility metadata.

6. Lifecycle FSM Specification
- Defines health states, legal transitions, and transition diagnostics contract.

7. Configuration Specification
- Defines config enums, required fields, normalization rules, and policy behavior.

8. Error Specification
- Defines required error hierarchy and error context propagation behavior.

9. Bootstrap Specification
- Defines mandatory query plan, response normalization, and `BootstrapPayload` contract.

10. Initial Snapshot Build Specification
- Defines entity-map/index construction, focus derivation, and initial invariant checks.

11. Invariant Specification
- Defines required invariant checks and failure-policy behavior.

12. Reduction Specification
- Defines root dispatch, domain reducer coverage, event semantics, and result contract.

13. Unknown/Unsupported Event Policy
- Defines policy-specific behavior for unknown and unimplemented impactful inputs.

14. Store Publication and Subscription Specification
- Defines single-owner mutation/publication, `ChangeSet` semantics, and subscriber overflow behavior.

15. Wait/Watch Specification
- Defines wait/watch API behavior, health gating, timeout/cancel semantics, and change emission rules.

16. Resync and Recovery Specification
- Defines stale triggers, manual/auto policy behavior, and successful/failed recovery semantics.

17. Selectors Specification
- Defines selector families, purity/stability contracts, and missing-entity behavior.

18. Replay Trace Specification
- Defines replay input format and determinism guarantees.

19. Test Specification
- Defines required coverage, fixture expectations, and prioritized confidence gates.

20. Tooling and Quality Gates
- Defines required repo commands and Python quality checks.

21. Definition of Done
- Defines implementation completion criteria.

## 1. Authority and Scope

`FINAL_SPEC.md` is the implementation contract for `niri-state`.

Conflict resolution order:
1. `niri-pypc` observed runtime/type behavior.
2. `.scratch/projects/02-final-concept/FINAL_CONCEPT.md`.
3. This `FINAL_SPEC.md` as executable implementation guidance.

`niri-state` is a downstream observed-state library and must not reimplement protocol transport or wire framing concerns owned by `niri-pypc`.

## 2. Dependency Contracts (`niri-pypc`)

Implementation must assume:
1. Request client operations are request/reply and short-lived per call.
2. Event stream is long-lived and queue-backed.
3. Upstream queue backpressure policy is configurable; strict correctness mode requires fail-fast effective behavior.
4. Connection bundle open returns request client + event stream together with cleanup guarantees on partial failure.
5. Request responses are typed variants with explicit payload shapes/nullability.
6. Unknown event variants can surface and must enter configured unknown-event policy flow.
7. State-relevant event families include windows, workspaces, focus, keyboard layouts, overview, plus metadata-style events (`ConfigLoaded`, `ScreenshotCaptured`, and typed layout/timestamp events).

## 3. Package Architecture and Boundaries

Required module structure:

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

Boundary rules:
1. `_core` is pure domain logic: reducers, invariants, models, snapshot build.
2. `_runtime` owns async lifecycle, stream consumption, publication, waits/watches, recovery.
3. `selectors` are pure and publicly importable.
4. No `_core` module may import runtime orchestration modules.

## 4. Runtime, Typing, and Model Conventions

Implementation constraints:
1. Python `>=3.13`.
2. `asyncio` runtime primitives only.
3. `from __future__ import annotations` throughout package modules.
4. Public state/change models use Pydantic v2 frozen models (`ConfigDict(frozen=True, extra="forbid")`).

Core aliases:
- `OutputName = str`
- `WorkspaceId = int`
- `WindowId = int`
- `Revision = int`

Entity-wrapper rules:
1. Wrap protocol models rather than duplicating full protocol fields.
2. Keep stable identity key on wrapper (`output_name`, `workspace_id`, `window_id`).
3. Derived fields allowed where needed for ergonomics (`current_name`, `is_open`, etc.).

## 5. Snapshot Model Specification

`NiriSnapshot` is the main published state artifact and must include:
1. `revision: int`.
2. `health: HealthState`.
3. publication `timestamp`.
4. entity maps:
- `outputs: dict[str, OutputState]`
- `workspaces: dict[int, WorkspaceState]`
- `windows: dict[int, WindowState]`
5. focus pointers:
- `focused_output_name: str | None`
- `focused_workspace_id: int | None`
- `focused_window_id: int | None`
6. domain wrappers:
- `keyboard: KeyboardState`
- `overview: OverviewState`
7. derived indexes:
- `workspaces_by_output: dict[str, tuple[int, ...]]`
- `windows_by_workspace: dict[int, tuple[int, ...]]`
- `active_workspace_by_output: dict[str, int]`
8. diagnostics and compatibility metadata.

Publication/immutability rules:
1. Published snapshots are immutable by contract.
2. Revision increments only when a new snapshot is published.
3. No partially reduced state may be externally visible.

## 6. Lifecycle FSM Specification

Health states:
- `BOOTSTRAPPING`
- `LIVE`
- `STALE`
- `RESYNCING`
- `CLOSED`
- `FAILED`

Minimum legal transition set:
1. `BOOTSTRAPPING -> LIVE | FAILED`.
2. `LIVE -> STALE | CLOSED`.
3. `STALE -> RESYNCING | LIVE | CLOSED`.
4. `RESYNCING -> LIVE | STALE | FAILED | CLOSED`.
5. `FAILED -> CLOSED`.

FSM requirements:
1. Transition legality is explicitly validated.
2. Transition reason is recorded for diagnostics.
3. Illegal transitions raise lifecycle errors.
4. Runtime uses single-owner mutation flow for transitions and snapshot updates.

## 7. Configuration Specification

Required enums:
1. `CorrectnessMode {STRICT, BEST_EFFORT}`
2. `ResyncPolicy {MANUAL, AUTO}`
3. `UnknownEventPolicy {STALE, FAIL, IGNORE}`
4. `InvariantFailurePolicy {STALE, FAIL}`
5. `WaitHealthPolicy {LIVE_ONLY, ALLOW_STALE}`
6. `StoreOverflowMode {DROP_OLDEST, FAIL_FAST}`

`NiriStateConfig` minimum fields:
1. `pypc: NiriConfig`.
2. correctness/resync/unknown/invariant/wait policies.
3. subscriber queue and overflow configuration.
4. optional runtime knobs for recovery behavior/timeouts.

Normalization rule:
1. If correctness mode is `STRICT`, effective upstream backpressure must be `FAIL_FAST`.
2. Build effective config via `dataclasses.replace()` on frozen upstream config.
3. On invalid replacement, raise `StateConfigError`.

## 8. Error Specification

Base error:
- `NiriStateError`

Required subtypes:
1. `StateConfigError`
2. `StateLifecycleError`
3. `BootstrapError`
4. `ReductionError`
5. `InvariantError`
6. `DesyncError`
7. `ResyncError`
8. `WatchOverflowError`
9. `SelectorWaitError` (must inherit `TimeoutError`)

Error context behavior:
1. Attach revision/health/event type/selector context where relevant.
2. Preserve underlying causes (`raise ... from exc`).
3. Map upstream runtime/decode/remote failures into state-layer errors with explicit lifecycle outcomes.

## 9. Bootstrap Specification

Mandatory bootstrap query suite:
1. outputs
2. workspaces
3. windows
4. focused output
5. focused window
6. keyboard layouts
7. overview state

Optional query suite:
1. compositor version
2. other query-only domains explicitly marked as non-live

`BootstrapPayload` contract includes normalized typed payload fields for all mandatory queries and optional fields for optional queries.

Normalization rules:
1. Match concrete response variants explicitly.
2. Enforce nullability contracts exactly.
3. Unknown/missing required responses raise `BootstrapError`.
4. Include compatibility metadata when available.

Bootstrap sequence:
1. normalize config
2. open connection bundle
3. begin event buffering
4. execute query suite
5. normalize payload
6. build base snapshot
7. replay buffered events via root reducer
8. validate invariants
9. publish first `LIVE` snapshot

No `LIVE` publication before replay completion.

## 10. Initial Snapshot Build Specification

`build_initial_snapshot(...)` must:
1. construct keyed entity maps from bootstrap payload.
2. build deterministic indexes.
3. derive focus pointers from focused payloads and resolvable relationships.
4. derive keyboard current-name fields with index bounds checks.
5. derive overview convenience fields.
6. initialize diagnostics and compatibility metadata.
7. run invariants before publishing.

Domain truth flags/interpretation:
1. outputs are refresh-backed.
2. event-reduced domains receive live semantics only after replay-closed publication.

## 11. Invariant Specification

Invariant checker must validate at minimum:
1. map-key identity coherence.
2. referential integrity across entity relationships.
3. focus-pointer referential validity when set.
4. active-workspace-per-output consistency.
5. index completeness/no duplicates/no dangling references.

Policy behavior:
1. `InvariantFailurePolicy.FAIL`: raise `InvariantError` and follow lifecycle failure path.
2. `InvariantFailurePolicy.STALE`: transition to stale path with diagnostics and policy-compliant publication behavior.

## 12. Reduction Specification

Reducer contract:
1. deterministic pure functions only.
2. no IO or external side effects.
3. explicit dispatch on concrete event variants in root reducer.
4. every applied event returns changed-domain metadata.

Required handled event categories:
1. Window events (open/update, close, replace-all, focus, urgency, focus timestamp, layout changes).
2. Workspace events (replace-all, activation, active-window change, urgency).
3. Keyboard events (layouts changed, layout switched).
4. Overview events (opened/closed).
5. Metadata events (`ConfigLoaded`, `ScreenshotCaptured`) with explicit no-op/diagnostic behavior.

Semantics:
1. replace-all events are authoritative full replacement.
2. incremental events patch affected domain deterministically.
3. cross-domain derived indexes are recomputed/updated before freeze.
4. invariant checks run on post-event candidate snapshot before publication.

Reducer output contract:
1. `applied` flag.
2. changed domains set.
3. cause classification.
4. optional event type + diagnostic summary.

## 13. Unknown/Unsupported Event Policy

Unknown/unimplemented impactful input handling:

`STALE` policy (default):
1. preserve entity state.
2. transition snapshot health to `STALE`.
3. publish stale transition with health/metadata domain changes.
4. append diagnostics with event identity and policy reason.

`FAIL` policy:
1. raise desync/failure pathway error.
2. transition lifecycle per failure strategy.

`IGNORE` policy:
1. allowed only for explicitly declared harmless classes.
2. must emit auditable diagnostic record.
3. may not be implicit fallthrough.

## 14. Store Publication and Subscription Specification

`NiriState.connect()` must:
1. validate/normalize config.
2. execute bootstrap and first `LIVE` publication.
3. start runtime event consumer loop.

Publication model:
1. single runtime mutation/publish owner.
2. each publication emits immutable snapshot and `ChangeSet` metadata.
3. monotonic revision progression.

`ChangeSet` minimum fields:
1. revision
2. timestamp
3. cause
4. changed domains
5. optional event type
6. snapshot reference

Subscription behavior:
1. per-subscriber bounded queues.
2. overflow policy is deterministic and configured.
3. closure terminates subscriber streams predictably.

`close()` behavior:
1. idempotent.
2. stop tasks, close stream/bundle resources.
3. transition to closed state.
4. terminate waits/watches/subscriptions with explicit lifecycle signaling.

## 15. Wait/Watch Specification

Wait APIs:
1. `wait_until(predicate, timeout=None, health_policy=...)`
2. optional selector-based wait helper may be layered, but predicate wait is baseline contract.

Wait behavior:
1. immediate check against current snapshot first.
2. event-driven wakeups from publication stream (no busy polling).
3. timeout raises `SelectorWaitError`.
4. cancellation propagates cleanly.
5. health policy gating:
- `LIVE_ONLY`: stale snapshots do not satisfy.
- `ALLOW_STALE`: stale snapshots may satisfy.

Watch behavior:
1. selector watch yields current selected value first.
2. subsequent values emit only on equality change.
3. watch stream terminates on close with explicit lifecycle semantics.

## 16. Resync and Recovery Specification

Stale/desync triggers include:
1. unknown impactful event under stale policy.
2. invariant failure under stale policy.
3. stream terminal/overflow failures.
4. explicit manual refresh.

Policy modes:
1. `MANUAL`: enter `STALE`, recover only on `refresh()`.
2. `AUTO`: enter `RESYNCING`, perform coordinated re-bootstrap.

Recovery outcome rules:
1. successful recovery publishes a coherent new `LIVE` snapshot.
2. failed auto recovery transitions to stale/failed state per policy with diagnostics.
3. existing historical snapshots remain immutable.

## 17. Selectors Specification

Selectors are pure functions over `NiriSnapshot` and grouped by domain modules.

Required selector families:
1. outputs
2. workspaces
3. windows
4. focus pointers
5. keyboard/overview
6. aggregates

Selector contract:
1. no mutation.
2. stable return-type semantics across compatible versions.
3. missing entities return `None` or empty collections by default.
4. refresh-backed/query-only selector docs must clearly state freshness limits.

## 18. Replay Trace Specification

Replay traces exist for deterministic regression verification.

Trace format requirements:
1. bootstrap payload section.
2. ordered event sequence section.
3. expected outcome assertions (final and optional checkpoints).

Replay guarantees:
1. same trace + same code path => same outcome.
2. replay uses the same root reducer path as live runtime.

## 19. Test Specification

Required coverage categories:
1. models and immutability behavior.
2. bootstrap response normalization and error cases.
3. invariant checks (single and multiple violations).
4. reducer behavior per required event variant.
5. unknown-event policy outcomes.
6. lifecycle/publication/subscription behavior.
7. wait/watch timeout/cancel/health-policy semantics.
8. resync manual/auto paths.
9. replay regression traces.
10. multi-output focus/active correctness behavior.

Fixture requirements:
1. use real protocol-generated models wherever practical.
2. include edge cases for nullability, replace-all events, and stale-trigger scenarios.

Priority rule:
- Reducer and invariant correctness are the top test priority.

## 20. Tooling and Quality Gates

For Python edits:
1. `devenv shell -- ruff check .`
2. `devenv shell -- ruff format --check .`
3. `devenv shell -- ty check .` when changing signatures/public types/interfaces.
4. targeted tests for changed behavior; full suite for cross-cutting changes.

Session rule before first test run:
1. `devenv shell -- uv sync --extra dev`

All environment-dependent commands must run via `devenv shell -- ...`.

## 21. Definition of Done

Implementation is complete when:
1. package/module structure matches this spec.
2. bootstrap-to-live race closure is implemented and tested.
3. required reducer/event coverage is complete and deterministic.
4. lifecycle, stale/desync/resync behavior matches policy contracts.
5. selectors/wait/watch APIs are stable and tested.
6. replay traces validate deterministic regression behavior.
7. quality gates pass cleanly.
8. docs remain aligned to `FINAL_CONCEPT.md` and `niri-pypc` dependency reality.
