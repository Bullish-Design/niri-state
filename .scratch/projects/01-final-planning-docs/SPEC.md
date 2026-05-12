# SPEC

Implementation specification for `niri-state`, consolidated from:
- `00` brainstorming concept/spec/implementation guides,
- `DOC_MISALIGNMENT.md` and `DEPENDENCY_MISALIGNMENT.md`,
- and `.context/niri-pypc` source/tests as dependency truth.

## Table of Contents

1. Authority and Scope
2. Canonical Dependency Contracts (`niri-pypc`)
3. Architectural Boundary and Package Layout
4. Core Type System and Public Models
5. Domain Freshness and Truth Classification
6. Snapshot, Revision, and Health Semantics
7. Configuration Specification
8. Error Specification
9. Bootstrap Query Plan and Normalization
10. Initial Snapshot Build Contract
11. Invariant Specification
12. Event Reduction Specification
13. Unknown/Unsupported Event Policy
14. Resync and Recovery Specification
15. Store Lifecycle and Publication Specification
16. Selectors Specification
17. Wait/Watch Specification
18. Replay Trace Specification
19. Test Specification
20. Quality Gates and Tooling
21. Definition of Done

## 1. Authority and Scope

This document is the final implementation contract for `niri-state`.

Authority order when sources disagree:
1. `.context/niri-pypc` code and tests.
2. Brainstorming `NIRI_STATE_SPEC.md`.
3. Brainstorming concept and implementation guides.
4. Misalignment analysis documents.

`niri-state` is a downstream state engine, not a protocol transport client.

## 2. Canonical Dependency Contracts (`niri-pypc`)

From `.context/niri-pypc` (v`0.1.0`, upstream `niri-ipc 25.11`):

1. `NiriClient` uses one-connection-per-request semantics.
2. `client.request()` returns unwrapped typed `Response` variants via `unwrap_reply()`; compositor `Err` replies raise `RemoteError`.
3. `NiriEventStream` is long-lived and backed by bounded `asyncio.Queue`.
4. Backpressure:
- `DROP_OLDEST`: oldest event is dropped and warning logged.
- `FAIL_FAST`: queue overflow yields terminal `ProtocolError`.
5. `NiriConnectionBundle.open()` returns `{client, events}` and closes client if event stream connect fails.
6. Unknown event wire variants decode into `UnknownEvent` sentinel (not immediate decode failure).
7. Unknown reply variants decode into `UnknownReply`; later unwrapping may fail if unexpected.
8. Generated payload contracts relevant to `niri-state`:
- `OutputsResponse.payload: dict[str, Output]`
- `WorkspacesResponse.payload: list[Workspace]`
- `WindowsResponse.payload: list[Window]`
- `FocusedOutputResponse.payload: Output | None`
- `FocusedWindowResponse.payload: Window | None`
- `KeyboardLayoutsResponse.payload: KeyboardLayouts`
- `OverviewStateResponse.payload: Overview` (non-null)
- `VersionResponse.payload: str` (non-null)
9. Event contracts include `ConfigLoadedEvent(failed: bool)`, `WindowLayoutsChangedEvent(changes: list[tuple[int, WindowLayout]])`, `WindowFocusTimestampChangedEvent(focus_timestamp: Timestamp | None, id: int)`.

## 3. Architectural Boundary and Package Layout

Required package structure:

```text
src/niri_state/
  __init__.py
  _version.py
  config.py
  errors.py
  models/{common,health,entities,snapshot,change_set}.py
  reducers/{common,bootstrap,invariants,windows,workspaces,focus,keyboard,overview,root}.py
  selectors/{outputs,workspaces,windows,focus,aggregates}.py
  sync/{bootstrap,resync,policies}.py
  store/{live_state,broadcaster,waiters}.py
```

Boundary rules:
1. `niri-state` may consume `niri_pypc` public config/errors/types and client/stream/bundle APIs.
2. `niri-state` must not reimplement socket transport, framing, lifecycle state machine, or protocol decode.
3. Reducers and selectors are pure and side-effect-free.
4. Store/sync layers own I/O, lifecycle, publication, and recovery orchestration.

## 4. Core Type System and Public Models

Runtime and typing:
1. Python `>=3.13`.
2. `asyncio` only.
3. Pydantic v2 immutable public models.
4. `from __future__ import annotations` in all modules.

Base aliases:
- `OutputName = str`
- `WorkspaceId = int`
- `WindowId = int`
- `Revision = int`

Public model requirements:
1. Public models are frozen (`ConfigDict(frozen=True, extra="forbid")`).
2. Entity wrappers embed raw protocol models:
- `OutputState.raw: Output`
- `WorkspaceState.raw: Workspace`
- `WindowState.raw: Window`
3. `KeyboardLayoutsState`:
- `raw: KeyboardLayouts | None`
- `current_idx: int | None`
- `current_name: str | None`
- if `raw` exists, `raw.current_idx` is non-null `int`; `current_name` is derived.
4. `OverviewState`:
- `raw: Overview | None`
- `is_open: bool | None`
5. Snapshot indexes must be explicit immutable tuples for stable ordering.

## 5. Domain Freshness and Truth Classification

Domains:
1. Event-live: windows, workspaces, focus pointers, keyboard layouts, overview.
2. Refresh-backed: outputs/config surfaces lacking a full event contract.
3. Query-only optional: layers and other non-event-backed metadata.

Rules:
1. `niri-state` must not claim live freshness for refresh-backed/query-only domains.
2. Public docs and selectors must clearly expose this distinction.
3. Focused vs active semantics are separate:
- focused workspace/window are global focus pointers,
- active workspace membership is tracked per output (`active_workspace_ids_by_output`).

## 6. Snapshot, Revision, and Health Semantics

Health states:
- `BOOTSTRAPPING`
- `LIVE`
- `STALE`
- `RESYNCING`
- `CLOSED`
- `FAILED`

Revision rules:
1. Revision increments only on publication.
2. A published snapshot is immutable and atomically visible.
3. `last_good_revision` points to most recent coherent `LIVE` snapshot.
4. First successful bootstrap+replay publication creates revision `1` (or configured initial revision), then increments monotonically.

Coherence rules:
1. No partial reducer state may be externally visible.
2. Invariant failures block `LIVE` publication of invalid states.

## 7. Configuration Specification

Required enums:
- `CorrectnessMode {STRICT, BEST_EFFORT}`
- `ResyncPolicy {MANUAL, AUTO}`
- `StoreOverflowMode {DROP_OLDEST, FAIL_FAST}`
- `UnknownEventPolicy {STALE, FAIL, IGNORE}`
- `InvariantFailurePolicy {STALE, FAIL}`
- `WaitHealthPolicy {LIVE_ONLY, ALLOW_STALE}`

`NiriStateConfig` includes:
1. Embedded `pypc: NiriConfig`.
2. correctness/resync/unknown/invariant/wait policies.
3. store capacities/timeouts.

Strict correctness normalization:
1. If `correctness_mode == STRICT`, effective upstream `backpressure_mode` must be `FAIL_FAST`.
2. Since `NiriConfig` is frozen dataclass, use `dataclasses.replace()` to derive effective config.
3. If replacement cannot be formed, raise `StateConfigError`.
4. `BEST_EFFORT` preserves caller-provided backpressure.

## 8. Error Specification

Base type: `NiriStateError`.

Required families:
1. Lifecycle/config/bootstrap errors (`StateLifecycleError`, `StateConfigError`, `BootstrapError`).
2. Reduction/invariant/desync errors (`ReductionError`, `InvariantError`, `DesyncError`).
3. Observation/wait errors (`WatchOverflowError`, `SelectorWaitError` inheriting `TimeoutError`).
4. Recovery errors (`ResyncError`).

Context requirements:
1. Include revision, health, event type, selector id, and retryability where relevant.
2. Preserve chained causes (`raise ... from exc`).

Mapping from `niri-pypc`:
1. bootstrap request/transport/decode failures -> `BootstrapError`.
2. live stream terminal failures -> `STALE`/resync flow (or `FAILED` per policy), not raw passthrough only.
3. remote command failures -> mapped state errors with cause context.

## 9. Bootstrap Query Plan and Normalization

Default mandatory query suite:
1. `OutputsRequest`
2. `WorkspacesRequest`
3. `WindowsRequest`
4. `FocusedOutputRequest`
5. `FocusedWindowRequest`
6. `KeyboardLayoutsRequest`
7. `OverviewStateRequest`

Optional queries:
1. `LayersRequest`
2. `VersionRequest`

Normalization contract:
1. Match response variants by concrete class, not by duck typing.
2. Build internal `BootstrapPayload` with typed extracted payloads.
3. Unknown/missing required variants cause `BootstrapError`.
4. Enforce true nullability contracts:
- focused output/window may be `None`,
- overview/version are non-null payload types.
5. Include compatibility metadata from `niri_pypc.__version__` and `types.generated._metadata`.

## 10. Initial Snapshot Build Contract

`build_initial_snapshot(payload, config, revision)` must:
1. Normalize output/workspace/window entities into keyed maps.
2. Build stable indexes for deterministic iteration.
3. Derive focus pointers:
- `focused_output_name` from focused output payload if present,
- `focused_window_id` from focused window payload if present,
- `focused_workspace_id` from focused window workspace if resolvable, otherwise workspace focus indicators.
4. Derive `active_workspace_ids_by_output` from workspace `is_active` + `output`.
5. Construct keyboard/overview wrappers:
- keyboard name derived by bounds-checked lookup `names[current_idx]`.
6. Set initial domain freshness flags (`outputs` refresh-backed).
7. Run invariants before publishing live snapshot.

## 11. Invariant Specification

`check_snapshot_invariants(snapshot) -> list[InvariantViolation]` minimum checks:
1. Map key/id coherence:
- output map key equals `OutputState.output_name`,
- workspace key equals `WorkspaceState.workspace_id`,
- window key equals `WindowState.window_id`.
2. Referential integrity:
- workspace `output_name` exists when non-null,
- window `workspace_id` exists when non-null.
3. Output-workspace consistency:
- output workspace memberships reference existing workspaces.
4. Focus consistency:
- focused pointers reference existing entities when set,
- at most one focused window marked in raw windows when focused id exists.
5. Active workspace consistency:
- every active workspace id in per-output map belongs to that output.
6. Index soundness:
- no duplicates, no missing ids relative to entity maps.

Policy behavior:
1. `InvariantFailurePolicy.FAIL` -> raise `InvariantError`.
2. `InvariantFailurePolicy.STALE` -> publish stale transition with diagnostics and preserve previous good snapshot where required by policy.

## 12. Event Reduction Specification

Reducer properties:
1. deterministic pure functions.
2. no I/O, no sleeps, no mutable global state.

Required handled event families:
1. windows:
- `WindowOpenedOrChangedEvent`
- `WindowClosedEvent`
- `WindowsChangedEvent`
- `WindowFocusChangedEvent`
- `WindowUrgencyChangedEvent`
- `WindowFocusTimestampChangedEvent`
- `WindowLayoutsChangedEvent`
2. workspaces:
- `WorkspaceActivatedEvent`
- `WorkspaceActiveWindowChangedEvent`
- `WorkspaceUrgencyChangedEvent`
- `WorkspacesChangedEvent`
3. keyboard:
- `KeyboardLayoutsChangedEvent`
- `KeyboardLayoutSwitchedEvent`
4. overview:
- `OverviewOpenedOrClosedEvent`
5. metadata/no-op:
- `ConfigLoadedEvent` (must be metadata-bearing via `failed` field)
- `ScreenshotCapturedEvent` (explicit no-op or metadata-only)

Event semantics requirements:
1. Replace-all events (`WindowsChanged`, `WorkspacesChanged`) are authoritative full replacement for that domain.
2. Incremental events patch existing state deterministically.
3. Window/workspace focused/active/urgency fields are updated in both wrapper-derived fields and raw model coherence as defined by implementation contract.
4. `WindowLayoutsChangedEvent.changes` applies by tuple `(window_id, WindowLayout)`.
5. `WindowFocusTimestampChangedEvent` uses full `Timestamp | None` payload.
6. `ConfigLoadedEvent.failed` updates diagnostics metadata at minimum.

Reducer return contract:
1. include whether event applied.
2. include changed domains.
3. include cause (`ChangeCause`) for publication.
4. include summary for diagnostics/debugging.

## 13. Unknown/Unsupported Event Policy

When receiving `UnknownEvent` or known-but-unimplemented impactful event:

Default (`UnknownEventPolicy.STALE`):
1. publish new snapshot with incremented revision,
2. keep entity state unchanged,
3. set `health=STALE`,
4. set cause `ChangeCause.STALE_TRANSITION`,
5. include `ChangeDomain.HEALTH` and `ChangeDomain.METADATA`,
6. append diagnostics with event variant name and payload excerpt.

Alternative policies:
1. `FAIL`: raise `DesyncError` and transition lifecycle to failure path.
2. `IGNORE`: allowed only for explicitly declared harmless events; must be auditable and documented.

## 14. Resync and Recovery Specification

Resync trigger sources:
1. unknown/unsupported impactful event,
2. invariant violation under stale policy,
3. upstream fail-fast overflow (`ProtocolError`),
4. stream transport/decode terminal failure,
5. explicit user refresh.

Policy modes:
1. `MANUAL`: enter `STALE`, await explicit `refresh()`.
2. `AUTO`: enter `RESYNCING`, attempt coordinated bootstrap.

Resync contract:
1. successful resync publishes a new coherent `LIVE` snapshot with incremented revision.
2. failed auto-resync retains stale/failed health per policy and records diagnostics.
3. previous snapshots remain immutable and accessible to existing consumers.

## 15. Store Lifecycle and Publication Specification

`NiriState` lifecycle:
1. `connect()`:
- validate/normalize config,
- open bundle,
- begin buffering events,
- run bootstrap queries,
- build initial snapshot,
- replay buffered events,
- publish first coherent `LIVE` snapshot,
- start live event consumer.
2. `close()`:
- idempotent,
- stop event task,
- close bundle resources,
- transition health/lifecycle to closed state,
- terminate watches/waits with explicit closure behavior.

Publication rules:
1. single serialization point (lock or task affinity) for snapshot publication.
2. each publication emits `ChangeSet` with revision, timestamp, cause, domains, and optional event type.
3. broadcaster overflow behavior follows configured policy.

## 16. Selectors Specification

Selectors are pure functions over `NiriSnapshot`.

Required selector families:
1. outputs:
- `output_by_name`, `outputs`, `focused_output`, `workspaces_on_output`, `output_config_is_live_current`
2. workspaces:
- `workspace_by_id`, `workspaces`, `focused_workspace`, `active_workspaces_on_output`, `windows_on_workspace`
3. windows:
- `window_by_id`, `windows`, `focused_window`, `workspace_for_window`
4. focus:
- `focused_window_id`, `focused_workspace_id`, `focused_output_name`
5. keyboard/overview:
- `keyboard_layouts`, `current_keyboard_layout_name`, `current_keyboard_layout_index`, `overview_is_open`
6. aggregates:
- `window_count`, `workspace_count`, `output_count`, `has_window`, `is_live`, `is_stale`

Stability rules:
1. selectors must not mutate snapshot.
2. selectors must preserve type contracts across minor versions.
3. missing entities return `None`/empty collection rather than raising unless selector contract explicitly says otherwise.

## 17. Wait/Watch Specification

Waiting APIs:
1. `wait_until(predicate, timeout, health_policy)`.
2. `wait_for_selector(selector, predicate, timeout, health_policy)`.

Behavior:
1. event-driven wakeups from publication stream; no busy polling.
2. timeout raises `SelectorWaitError` (also catchable as `TimeoutError`).
3. cancellation propagates cleanly.
4. health gating:
- `LIVE_ONLY`: stale snapshots do not satisfy waits,
- `ALLOW_STALE`: stale snapshots may satisfy.

Watch APIs:
1. change-stream subscription yields `ChangeSet` and/or snapshots.
2. selector-watch emits only when selected value changes by equality contract.
3. per-subscriber overflow policy documented and deterministic.

## 18. Replay Trace Specification

Purpose:
1. deterministic reproduction for bugs/regressions.
2. verification of long event sequences.

Format:
1. bootstrap payload capture,
2. ordered event list (wire or normalized),
3. expected final snapshot assertions and optional intermediate checkpoints.

Replay contract:
1. same trace + same code => same final snapshot and diagnostics.
2. replay engine uses the same reducer path as live flow.

## 19. Test Specification

Required coverage:
1. model immutability and type contracts.
2. bootstrap normalization per response variant, including unknown/missing cases.
3. invariant checks (single and multi-violation).
4. per-event reducer behavior with deterministic domain/cause outputs.
5. unknown event policy outcomes (`STALE`, `FAIL`, `IGNORE`).
6. store lifecycle (`connect`, publish, close, stale transitions).
7. wait/watch behavior (timeout, cancel, health policies, overflow).
8. resync orchestration (manual + auto).
9. replay regression tests.
10. focused-vs-active multi-output correctness tests.

Fixture requirements:
1. test fixtures must construct real generated protocol models (`Output`, `Workspace`, `Window`, `WindowLayout`, `Timestamp`, etc.).
2. helpers must cover optional/null edge cases and replacement events.

## 20. Quality Gates and Tooling

For Python edits, required checks:
1. `devenv shell -- ruff check .`
2. `devenv shell -- ruff format --check .`
3. `devenv shell -- ty check .` when changing signatures/public contracts/typed models.
4. targeted tests for changed behavior; full suite for cross-cutting changes.

Repository command constraints:
1. environment-dependent commands must run via `devenv shell -- ...`.
2. before first test run in session: `devenv shell -- uv sync --extra dev`.

## 21. Definition of Done

`niri-state` implementation is done when:
1. all required modules and public API surface exist and are documented.
2. bootstrap-to-live flow is coherent and race-closed.
3. reducers handle required event surface, including metadata-bearing events.
4. unknown/invariant/desync behaviors match configured policies.
5. selectors/waits/watches are stable and tested.
6. resync behavior is implemented and policy-compliant.
7. replay traces are supported for deterministic regression.
8. quality gates and tests pass cleanly.
9. documentation matches actual dependency contracts from `niri-pypc`.
