# V2 Refactor — Status Summary

**Branch**: `v2-rewrite`
**Date**: 2026-05-14
**Source documents**: `V2_REFACTOR_CODE_REVIEW.md`, `V2_REFACTOR_REFACTOR_GUIDE.md`

---

## Current State

- **All 24 refactor steps: COMPLETE**
- Lint (`ruff check`): passing
- Format (`ruff format`): clean (61 files)
- Tests: **84 passed**, **85% coverage**
- 2 trivial uncommitted changes (import reorder + unused import removal in test files)

---

## Completed Work (24 Steps)

### Phase 1: Bug Fixes

| Step | Issue | File | What Changed |
|------|-------|------|--------------|
| 1 | C2 — Duplicate notes memory leak | `core/reconcile.py` | Added `if note not in engine.diagnostics.notes` guard before appending stale-health note. Prevents unbounded tuple growth when `reconcile()` runs repeatedly on STALE engine. |
| 2 | BR1 — Publish raises on first overflow, skipping remaining subscribers | `core/broadcaster.py` | Refactored `publish()` to collect errors per-subscriber via `first_error` pattern. All subscribers now receive items even if one overflows. First error is raised after full iteration. |
| 3 | Shutdown cleanup not resilient | `api/state.py` | Wrapped `bundle.close()`, `resync.close()`, `broadcaster.close()` in nested `try/finally` so all cleanup runs even if an earlier step raises. |

### Phase 2: API Improvements

| Step | Issue | File | What Changed |
|------|-------|------|--------------|
| 4 | S5 — No async context manager | `api/state.py` | Added `__aenter__` (calls `connect()`) and `__aexit__` (calls `close()`). `NiriState` now supports `async with`. |
| 5 | `_open_bundle` monkey-patching | `api/state.py` + all integration tests | Added `bundle_factory` parameter to `__init__()` and `open()`. Migrated all integration tests from `state._open_bundle = ...  # type: ignore` to constructor injection. |
| 6 | `PublishedState` not in public API | `__init__.py`, `api/__init__.py` | Re-exported `PublishedState` from both top-level and `api` packages. |

### Phase 3: Architectural Cleanup

| Step | Issue | File | What Changed |
|------|-------|------|--------------|
| 7 | `InvariantViolation` in core leaks into public API | New `api/types.py` | Moved `InvariantViolation` model to `api/types.py`. Updated imports in `api/errors.py`, `core/diagnostics.py`, `core/invariants.py`, `api/state.py`. |
| 8 | Architecture tests miss api->core data type imports | `tests/unit/test_architecture.py` | Added `test_api_errors_should_not_import_from_core` to verify `api/errors.py` doesn't import from `niri_state.core`. |
| 9 | S3 — `subscribe()` initial changeset misleading | `api/state.py` | Changed initial yield from `health_changeset` to `bootstrap_changeset` (all domains marked changed, semantically correct for new subscribers). |

### Phase 4: Type Safety

| Step | Issue | File | What Changed |
|------|-------|------|--------------|
| 10 | R1 — `Reducer` typedef uses `object` | `core/reducers.py` | Changed `Reducer = Callable[[EngineState, object], ...]` to `Callable[[EngineState, Any], ...]` with documenting comment. |
| 11 | R2 — `dict[int, object]` annotation | `core/reducers.py` | Changed `updated: dict[int, object]` to `dict[int, Workspace]` in `reduce_workspace_activated`. Added `Workspace` import. |

### Phase 5: Resilience

| Step | Issue | File | What Changed |
|------|-------|------|--------------|
| 12 | W1 — `wait_until` silent on terminal health | `api/waiters.py` | Added check for `HealthState.CLOSED`/`FAILED` that raises `StateLifecycleError` immediately instead of continuing silently until subscription closes. |
| 13 | CF1 — `strict_config` ignores explicit overrides | `api/config.py` | Changed to `merged = {**strict_defaults, **overrides}` so user-provided policy overrides take precedence over strict defaults. |
| 14 | W2 — `wait_for_selector` calls selector twice | `api/waiters.py` | Cached selector result in `last_value` list closure. Selector now runs once per snapshot instead of twice on match. |
| 15 | S4 — `refresh()` old bundle close can propagate | `api/state.py` | Wrapped `old_bundle.close()` in `try/except` with warning log. New connection is already active, so old close failure is non-fatal. |

### Phase 6: Performance

| Step | Issue | File | What Changed |
|------|-------|------|--------------|
| 16 | B1 — Sequential bootstrap queries | `core/bootstrap.py` | Replaced 8 sequential `await query_*()` calls with `asyncio.gather()`. Bootstrap now makes all IPC queries in parallel. |

### Phase 7: Test Coverage

| Step | What | File |
|------|------|------|
| 17 | Fixed `DummyState.subscribe` return type to `AsyncIterator[PublishedState]` | `tests/conftest.py` |
| 18 | Added unit tests for all 14 reducers (24 test functions) | `tests/unit/test_reducers.py` |
| 19 | Added broadcaster publish tests (multi-subscriber, overflow, DROP_OLDEST) | `tests/unit/test_broadcaster.py` |
| 20 | Added invariant coverage tests (missing window/workspace/output, valid snapshot) | `tests/unit/test_invariants.py` |
| 21 | Added lifecycle error path tests (double connect, connect-after-close, refresh-when-disconnected) | `tests/integration/test_close_lifecycle.py` |
| 22 | Added mutation loop desync test (unknown window -> STALE + desynced) | `tests/integration/test_runtime_mutation_loop.py` |
| 23 | Added close-during-subscription test (subscriber receives CLOSED snapshot) | `tests/integration/test_close_lifecycle.py` |
| 24 | Added edge case tests (empty state, multi-output, empty keyboard names) | `tests/unit/test_snapshot.py` |

---

## Remaining Items (Not in Refactor Guide)

These are items from the code review that were categorized as informational, by-design, or deferred. None are blocking.

### Low-Priority / Nice-to-Have

| ID | Issue | Severity | Notes |
|----|-------|----------|-------|
| S1 | Bootstrap event buffering race window | Medium | Between `buffer_task.cancel()` and event replay, events in niri-pypc's internal `asyncio.Queue` could theoretically be lost. Window is small in practice (bootstrap queries are slow relative to event delivery). Would need niri-pypc changes to fully fix. |
| S2 | `SubscriptionOverflowError` terminates mutation loop | Medium | Step 2 fixed subscriber isolation, but with `FAIL_FAST` policy a single slow subscriber still kills the mutation loop via the generic `Exception` handler. Default `DROP_OLDEST` avoids this. Could add specific `SubscriptionOverflowError` handling in the mutation loop to degrade gracefully. |
| C1 | `_reconcile_focused_workspace` picks arbitrary workspace if multiple focused | Very low | Dict iteration order (insertion). Compositor should never send conflicting focus; any choice is best-effort. |
| R3 | `event_count` includes unknown events | Informational | `diagnostics.event_count` increments before unknown-event check. Reasonable behavior but undocumented. |
| SN1 | `cached_property` on frozen Pydantic model | Informational | Works via Pydantic v2's `__dict__` bypass. If Pydantic changes this, cached properties would break. Worth noting as an assumption. |
| D1 | Verbose `cast(Mapping[str, Any], ...)` pattern | Style | Appears ~8 times. Needed because `model_copy(update=...)` expects `Mapping[str, Any]`. Could use a helper or `# type: ignore`. |

### Deferred Improvements (from Review Section 11: "Later")

| Item | Description | Effort |
|------|-------------|--------|
| Event batching | If niri sends rapid event bursts, snapshot-per-event is wasteful. A debounce/batch mechanism could reduce allocations. | Medium |
| Property-based testing | Use Hypothesis to generate random event sequences and verify invariants always hold. | Medium |
| Metrics/observability hooks | Callback or event for monitoring (events processed, snapshot latency, queue depths). | Low-Medium |
| Generic `Reducer` protocol | Properly typed reducer registry using `Protocol[E]` for type-safety purists. | Low |

### Coverage Gaps (Not Critical)

Current coverage is 85%. Lower-coverage areas:

| Module | Coverage | Notes |
|--------|----------|-------|
| `api/selectors/aggregates.py` | 47% | Composite queries not exercised by tests |
| `api/selectors/outputs.py` | 47% | Output-centric queries untested |
| `api/selectors/workspaces.py` | 47% | Workspace-centric queries untested |
| `api/selectors/focus.py` | 59% | Focus queries partially tested |
| `api/selectors/windows.py` | 58% | Window queries partially tested |
| `api/waiters.py` | 68% | `wait_for_selector` and timeout paths |
| `api/errors.py` | 77% | Some error class `__init__` paths |
| `core/invariants.py` | 79% | 3 of 7 invariant checks still untested |

### Uncommitted Changes

Two trivial diffs in test files (import reordering in `test_close_lifecycle.py`, unused import removal in `test_reducers.py`). These are linter-clean already — just haven't been committed.
