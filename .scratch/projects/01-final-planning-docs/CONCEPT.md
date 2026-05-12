# CONCEPT

Final concept baseline for `niri-state`, reconciled across:
- brainstorming concept/spec/implementation guides,
- doc/dependency misalignment analyses,
- and the attached `.context/niri-pypc` implementation and test contracts.

## Table of Contents

1. Authority, Intent, and Scope
- Defines what this concept governs and what sources are canonical.

2. Project Identity and Layering
- Names, package boundary, and one-way dependency direction.

3. Core Goals
- Non-negotiable outcomes for correctness, determinism, and ergonomics.

4. Non-Goals
- Responsibilities explicitly excluded from `niri-state`.

5. Dependency Reality: `niri-pypc` Contracts
- Concrete behavior `niri-state` must design around.

6. State Truth Model
- What “observed truth” means; domain freshness classes and guarantees.

7. High-Level Architecture
- Bootstrap, reducers, snapshots, selectors, store, waits/watchers, and resync ownership.

8. Snapshot and Health Semantics
- Immutable revisioned snapshots, health states, and correctness boundaries.

9. Bootstrap and Race-Closure Contract
- Required sync sequence and response normalization responsibilities.

10. Reduction Contract
- Event handling, unknown/unsupported behavior, invariant enforcement, and deterministic transitions.

11. Desync, Stale, and Resync Contract
- Trigger conditions, policy modes, and publish semantics.

12. Public API Concept
- Intended high-level interface and behavioral promises to consumers.

13. Compatibility and Versioning
- Dependency/version coupling and runtime metadata expectations.

14. Testing and Verification Principles
- What must be testable to trust correctness claims.

15. Corrected Misalignment Decisions
- Explicit reconciliations made against prior document drift.

16. Implementation Phasing Intent
- Recommended order for moving from concept to implementation.

17. Final Invariants
- Architectural rules that must remain true as the project evolves.

## 1. Authority, Intent, and Scope

`CONCEPT.md` is the top-level architecture contract for `niri-state`.

Canonical truth order for this final concept:
1. Attached `niri-pypc` dependency code and tests in `.context/niri-pypc`.
2. Refined `niri-state` spec/concept/implementation documents.
3. Misalignment analysis documents where they resolve drift toward dependency reality.

If future planning text conflicts with actual `niri-pypc` behavior, `niri-state` planning must be updated.

## 2. Project Identity and Layering

- Project/package: `niri-state` (`niri_state`).
- Role: downstream state engine over `niri-pypc`.
- Dependency direction: `niri-state -> niri-pypc` only.

`niri-pypc` owns protocol and runtime substrate.
`niri-state` owns observed compositor state derivation and publication.

## 3. Core Goals

1. Deterministic state reduction from bootstrap payload + ordered event stream.
2. Atomic immutable snapshot publication for each revision.
3. Explicit health/freshness semantics (no silent correctness drift).
4. Query ergonomics via typed selectors and wait/watch helpers.
5. Dependency-faithful design aligned with current `niri-pypc` contracts.
6. Replayable behavior suitable for regression trace testing.

## 4. Non-Goals

1. Reimplementing transport/framing/socket lifecycle.
2. Reimplementing request/reply/event codec logic.
3. Owning protocol schema generation or pin management.
4. Policy/planning/orchestration logic above raw state.
5. Pretending query-only domains are event-live.

## 5. Dependency Reality: `niri-pypc` Contracts

`niri-state` must design around these confirmed behaviors:

1. `NiriClient` is one-connection-per-request; `request()` opens, exchanges one frame, and closes.
2. `NiriEventStream` is long-lived, buffered by bounded `asyncio.Queue`.
3. Backpressure modes are `DROP_OLDEST` and `FAIL_FAST`; strict correctness requires fail-fast semantics.
4. `NiriConnectionBundle.open()` is async and returns `client + events`; it closes the client if event stream setup fails.
5. `client.request()` returns unwrapped typed `Response` variant payloads and raises `RemoteError` for `Err` replies.
6. Unknown wire event variants become typed `UnknownEvent`; unknown reply variants flow through decode paths as decode failures/unknown sentinels.
7. Event surface includes workspace/window/focus/keyboard/overview plus `ConfigLoaded`, `ScreenshotCaptured`, `WindowFocusTimestampChanged`, and `WindowLayoutsChanged`.
8. Key payload shapes: outputs are `dict[str, Output]`, windows/workspaces are lists, focused output/window are nullable payloads, overview/version payloads are non-nullable (`Overview`, `str`).

## 6. State Truth Model

`niri-state` models observed compositor truth only.

Domain classes:
1. Event-reduced live: windows, workspaces, focus pointers, keyboard layouts, overview state.
2. Refresh-backed: output configuration/details.
3. Query-only/optional: layers and similar surfaces lacking live event coverage.

Design corrections preserved:
- Focused and active are different concepts.
- Active workspace relationships are per output, not singular global truth.

## 7. High-Level Architecture

1. Sync/bootstrap layer: open bundle, buffer events, execute query plan, normalize replies, build base snapshot, replay buffer.
2. Reducer layer: pure deterministic event application + invariant checks.
3. Model layer: immutable normalized snapshots with revision + diagnostics.
4. Selector layer: pure read/query helpers over snapshot.
5. Store layer: publication, watchers, waits, health transitions, lifecycle.
6. Resync coordinator: stale-to-live recovery orchestration.

## 8. Snapshot and Health Semantics

Snapshot rules:
1. Public snapshots are immutable.
2. Revision increments on each published state transition.
3. No partial reducer state is observable.
4. `last_good_revision` tracks last coherent live revision.

Health states:
- `bootstrapping`, `live`, `stale`, `resyncing`, `closed`, `failed`.

`live` guarantees only apply to event-reduced domains.

## 9. Bootstrap and Race-Closure Contract

Required sequence:
1. Normalize config and enforce correctness mode requirements.
2. Open `NiriConnectionBundle`.
3. Start event consumption/buffering immediately.
4. Execute explicit initial query suite.
5. Normalize typed response wrappers into bootstrap payload.
6. Build base snapshot.
7. Replay buffered events in order through normal reducer path.
8. Publish first live snapshot only after replay succeeds.

No live snapshot may be published before race closure.

## 10. Reduction Contract

Reducer requirements:
1. Pure functions only; no I/O and no command issuing.
2. Dispatch by concrete typed event variants.
3. Unknown/unsupported state-affecting events never silently ignored.
4. Invariants validated after applied transitions.
5. Deterministic same-input same-output behavior.

Known non-stateful events (for v1) must be explicitly documented as no-op or metadata-only behavior, not accidental fallthrough.

## 11. Desync, Stale, and Resync Contract

Desync triggers include:
1. Unknown/unsupported impactful event.
2. Invariant violation.
3. Transport/event-stream failure.
4. Upstream fail-fast overflow signal.
5. Manual refresh request.

Policy modes:
- Manual: transition stale and await explicit refresh.
- Auto: transition resyncing and attempt fresh bootstrap.

Resync publishes a new coherent snapshot on success; old snapshots remain immutable.

## 12. Public API Concept

Intended consumer surface:
1. Connect and current/snapshot retrieval.
2. Change stream subscription.
3. Selector watch subscription.
4. Wait helpers (`wait_until`, `wait_for_selector`).
5. Explicit refresh/resync entrypoint.
6. Predictable close semantics.

Behavioral promise: coherent snapshots with explicit health boundaries.

## 13. Compatibility and Versioning

1. `niri-state` declares compatible `niri-pypc` range and tests against it.
2. Snapshot compatibility metadata includes `niri-state`, `niri-pypc`, and upstream protocol pin context.
3. Optional runtime compositor version check may refine compatibility diagnostics.
4. Breaking public state/selectors semantics require semver-appropriate changes.

## 14. Testing and Verification Principles

1. Reducer and invariant tests are first-class.
2. Bootstrap/replay race closure must be integration-tested.
3. Unknown event and overflow/desync paths must be explicitly tested.
4. Wait/watch behavior must be event-driven and deterministic under timeout/cancel.
5. Replay traces should reproduce fixed bugs and long-sequence convergence.

## 15. Corrected Misalignment Decisions

Final concept explicitly resolves prior drift:
1. Strict correctness maps to fail-fast upstream backpressure expectations.
2. Overview/version payload nullability follows actual generated types.
3. `ConfigLoadedEvent(failed: bool)` is acknowledged as metadata-bearing, not ignored noise.
4. `WindowLayoutsChanged` and `WindowFocusTimestampChanged` typed payloads are recognized in reduction planning.
5. Layers remain query-only unless event coverage changes upstream.
6. Workspace/window/output model shapes follow generated types (including workspace `idx`, window `focus_timestamp`, layout model structure).

## 16. Implementation Phasing Intent

Recommended execution order:
1. Models/config/errors.
2. Bootstrap normalization + invariants.
3. Domain reducers + root reducer.
4. Store publication + broadcaster/waiters.
5. Bootstrap coordinator.
6. Resync coordination.
7. Selector layer.
8. Replay/integration/live hardening.
9. Documentation/packaging alignment.

## 17. Final Invariants

These must remain true:
1. `niri-state` never claims stronger freshness than its event coverage supports.
2. Unknown/unsupported impactful inputs cannot silently preserve `live` correctness claims.
3. Snapshot publication remains atomic and immutable.
4. Reducers and selectors remain pure.
5. Dependency direction remains one-way: `niri-state -> niri-pypc`.
6. Behavior is testable through deterministic replay and integration flows.
