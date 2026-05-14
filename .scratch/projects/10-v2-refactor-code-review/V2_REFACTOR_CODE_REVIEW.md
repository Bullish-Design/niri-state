# V2 Refactor Code Review — niri-state

**Reviewer**: Claude Opus 4.6
**Date**: 2026-05-13
**Branch**: `v2-rewrite` @ `fe2aae3`
**Scope**: Full library (`src/niri_state/`) + dependency (`niri-pypc 0.3.1`) + test suite

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Architecture Review](#2-architecture-review)
3. [Module-by-Module Analysis](#3-module-by-module-analysis)
4. [Concurrency & Lifecycle Review](#4-concurrency--lifecycle-review)
5. [Error Handling & Resilience](#5-error-handling--resilience)
6. [Type Safety & API Contracts](#6-type-safety--api-contracts)
7. [Test Suite Assessment](#7-test-suite-assessment)
8. [niri-pypc Dependency Analysis](#8-niri-pypc-dependency-analysis)
9. [Performance Considerations](#9-performance-considerations)
10. [Issues by Severity](#10-issues-by-severity)
11. [Recommendations](#11-recommendations)

---

## 1. Executive Summary

niri-state is a well-architected async state management library for the Niri Wayland compositor. The v2 rewrite demonstrates strong software engineering: strict layered architecture (enforced by AST-based tests), immutable snapshots from mutable engine state, a reducer pattern for event processing, and policy-driven error handling. The code is clean, type-safe (strict mypy), and well-organized.

**Overall Quality**: High. The architecture is sound, the patterns are well-chosen, and the implementation is careful. The issues identified are primarily edge cases, missing coverage, and minor design refinements — not fundamental flaws.

**Key Strengths**:
- Clean separation between mutable engine state and immutable snapshots
- Policy-driven behavior (unknown events, invariant failures, overflow, resync)
- Rigorous layering with AST-enforced dependency rules
- Forward-compatible event handling via `UnknownEvent`
- Comprehensive reconciliation and invariant checking

**Key Concerns**:
- Race conditions in bootstrap event buffering
- `_open_bundle` monkey-patching in tests suggests missing dependency injection
- Several untested error paths
- Sequential bootstrap queries where parallelism is possible
- Broadcaster error propagation can terminate the mutation loop

---

## 2. Architecture Review

### 2.1 Layering

```
api/          ← Public surface: NiriState, Snapshot, Config, Selectors, Waiters
core/         ← Internal: Bootstrap, Engine, Reducers, Reconcile, Invariants, Broadcaster, Resync
adapters/     ← Protocol re-exports from niri-pypc
observability/ ← Logging
```

**Verdict**: Excellent. Dependency directions are clean and AST-enforced. The adapter layer properly isolates niri-pypc types, making future protocol changes containable.

**One concern**: `api/errors.py` imports from `core/diagnostics.py` (`InvariantViolation`). This is a cross-layer coupling that could become problematic:

```python
# api/errors.py:5
from niri_state.core.diagnostics import InvariantViolation
```

`InvariantViolation` is a data model used in public-facing error objects (`InvariantError.violations`). It should arguably live in `api/` or a shared `types/` module, not `core/`. The architecture tests don't catch this because they only check that adapters don't import core and observability doesn't import api/core — they don't check that api doesn't import core *data types* that leak into the public API.

### 2.2 State Flow

```
Events → reduce_event() → reconcile() → freeze() → Snapshot → Broadcaster → Subscribers
```

This is a textbook unidirectional data flow. Each step is well-isolated and independently testable. The reducer pattern maps cleanly to the event-driven nature of the compositor IPC.

### 2.3 Dependency Injection

The library uses a mix of constructor injection (config) and monkey-patching (`_open_bundle`). Every integration test does:

```python
state._open_bundle = _open_bundle  # type: ignore[method-assign]
```

This works but is a code smell. `_open_bundle` should be an injectable factory or the class should accept a `bundle_factory` parameter. The `# type: ignore` annotations confirm that mypy objects to this pattern.

---

## 3. Module-by-Module Analysis

### 3.1 `api/state.py` — NiriState

**The central orchestrator.** 394 lines managing connection, bootstrap, mutation loop, refresh, and close.

#### Issue S1: Bootstrap event buffering has a race window

```python
# bootstrap.py:170-181
async def _buffer_events() -> None:
    async for event in bundle.events:
        buffered_events.append(event)

buffer_task = asyncio.create_task(_buffer_events())
await asyncio.sleep(0)       # ← Single yield to event loop
try:
    engine = await build_initial_engine_state(bundle.client)
finally:
    buffer_task.cancel()
```

The `await asyncio.sleep(0)` gives the buffer task exactly one chance to start. If the event stream hasn't yielded its first event yet (which is likely since the niri socket just opened), buffering begins. But there's a subtler issue: between `buffer_task.cancel()` and the event replay loop, any events that arrived in the event stream's internal asyncio queue but weren't yet consumed by `_buffer_events` are lost. The `NiriEventStream` from niri-pypc uses an internal `asyncio.Queue`, and cancelling the reader doesn't drain that queue.

**Severity**: Medium. In practice, the window is small because bootstrap queries are sequential and slow relative to event delivery. But under heavy compositor activity during connect, events could be dropped.

#### Issue S2: `_mutation_loop` swallows `SubscriptionOverflowError`

```python
# state.py:209-217
except DesyncError as exc:
    _LOGGER.warning("desync detected in mutation loop: %s", exc)
    await self._mark_desynced(exc)
except asyncio.CancelledError:
    raise
except Exception as exc:
    _LOGGER.exception("mutation loop failed")
    await self._fail(exc)
    raise
```

The `self._broadcaster.publish()` call at line 199 can raise `SubscriptionOverflowError` (when policy is FAIL_FAST). This is caught by the generic `Exception` handler at line 214, which calls `self._fail(exc)` and transitions to FAILED. This is arguably the correct behavior, but it means a single slow subscriber can kill the entire state manager. There's no way to isolate a misbehaving subscriber without also killing the mutation loop.

**Severity**: Medium. The default policy is DROP_OLDEST which avoids this, but FAIL_FAST users get an aggressive failure mode.

#### Issue S3: `subscribe()` yields initial snapshot with HEALTH changeset

```python
# state.py:92-99
async def subscribe(self) -> AsyncIterator[PublishedState]:
    if self._snapshot is not None:
        yield PublishedState(
            snapshot=self._snapshot,
            changes=health_changeset(revision=self._snapshot.revision),
        )
    async for published in self._broadcaster.subscribe():
        yield published
```

Using `health_changeset` for the initial yield is semantically misleading. The subscriber receives a changeset claiming only HEALTH and DIAGNOSTICS changed, when in reality this is their first snapshot and everything is "new." This will cause subscribers that filter on `ChangedDomain` to miss initial state unless they special-case `ChangeCause.HEALTH`. The `watch()` waiter handles this by always yielding the initial snapshot, but direct `subscribe()` users may be confused.

**Severity**: Low. Documented behavior, but semantically surprising.

#### Issue S4: `refresh()` closes old bundle after starting mutation loop

```python
# state.py:361-362
self._start_mutation_loop()
await old_bundle.close()
```

The old bundle is closed after the new mutation loop starts. This ordering is intentional (don't block the new loop), but if `old_bundle.close()` raises, the exception propagates up from `refresh()` while the new mutation loop is already running. The caller gets an error but the state is actually functional. This could lead to confusion.

**Severity**: Low. niri-pypc's `close()` is designed to be safe, but the asymmetry is worth noting.

#### Issue S5: No `__aenter__`/`__aexit__` context manager protocol

`NiriState` doesn't implement async context manager, requiring users to manually call `close()`. This is a common source of resource leaks, especially when exceptions occur. Given that the underlying `NiriConnectionBundle` supports `async with`, it's surprising that `NiriState` doesn't.

**Severity**: Medium. Usability issue. Every integration test manually calls `await state.close()`.

### 3.2 `core/bootstrap.py` — Bootstrap

#### Issue B1: Sequential queries are unnecessarily slow

```python
# bootstrap.py:92-100
outputs = await query_outputs(client)
workspaces = await query_workspaces(client)
windows = await query_windows(client)
focused_output = await query_focused_output(client)
focused_window = await query_focused_window(client)
keyboard_layouts = await query_keyboard_layouts(client)
overview = await query_overview(client)
version = await query_version(client)
```

8 sequential IPC round-trips. Each creates a new Unix socket connection (per niri-pypc's NiriClient design). These could be parallelized with `asyncio.gather()`:

```python
outputs, workspaces, windows, focused_output, focused_window, keyboard_layouts, overview, version = await asyncio.gather(
    query_outputs(client),
    query_workspaces(client),
    ...
)
```

**Severity**: Low (correctness), Medium (performance). Bootstrap time is 8x the single-query latency. On a typical system with ~1ms per IPC call, this is ~8ms vs ~1ms. Not critical but wasteful.

#### Issue B2: `_apply_bootstrap_invariant_policy` mutates engine then re-freezes

```python
# bootstrap.py:152-158
engine.diagnostics = with_invariant_violations(...)
engine.health = HealthState.STALE
reconcile(engine)
return engine.freeze(revision=snapshot.revision, timestamp=snapshot.timestamp)
```

This creates a second snapshot at the same revision and timestamp as the first. The first snapshot (which had violations) is discarded. This is correct behavior, but the function takes the original `snapshot` as a parameter only to extract `revision` and `timestamp` — it would be clearer to pass those directly.

### 3.3 `core/reducers.py` — Event Reducers

#### Issue R1: Type annotation looseness in Reducer typedef

```python
Reducer = Callable[[EngineState, object], frozenset[ChangedDomain]]
```

The second parameter is `object`, not the specific event type. This means the reducer functions' type signatures (e.g., `event: WindowsChangedEvent`) are lies from mypy's perspective. The `@register` decorator and dispatch mechanism work correctly at runtime, but the type system doesn't enforce that a registered reducer actually accepts the event type it's registered for.

A better approach would be a generic protocol:

```python
class Reducer(Protocol[E]):
    def __call__(self, engine: EngineState, event: E) -> frozenset[ChangedDomain]: ...
```

**Severity**: Low. Runtime behavior is correct; this is a type-system perfectionism issue.

#### Issue R2: `reduce_workspace_activated` has a subtle dict mutation pattern

```python
# reducers.py:206-213
updated: dict[int, object] = {}
for workspace_id, existing in engine.workspaces.items():
    if existing.output != workspace.output:
        continue
    if existing.is_active or existing.is_focused:
        updated[workspace_id] = existing.model_copy(update={"is_active": False, "is_focused": False})

engine.workspaces.update(updated)
```

The `updated` dict has type `dict[int, object]`, losing the `Workspace` type. This is because `model_copy` returns the same type but the dict annotation doesn't reflect it. Using `dict[int, Workspace]` would be more precise.

#### Issue R3: `reduce_event` calls `with_event_applied` even for unknown events

```python
# reducers.py:59-60
event_type = type(event).__name__
engine.diagnostics = with_event_applied(engine.diagnostics, event_type=event_type)
```

This increments `event_count` and sets `last_event_type` before checking if the event is known. So `diagnostics.event_count` includes unknown events, but `diagnostics.last_event_type` might be "UnknownEvent" even if the event was ignored. This is actually reasonable behavior (you want to know unknown events happened), but it's undocumented.

### 3.4 `core/reconcile.py` — Reconciliation

Well-implemented. Each reconciliation function is idempotent and handles its specific concern cleanly.

#### Issue C1: `_reconcile_focused_workspace` iterates all workspaces to find focused

```python
# reconcile.py:39-42
for workspace_id, ws in engine.workspaces.items():
    if ws.is_focused:
        engine.focused_workspace_id = workspace_id
        return
```

If multiple workspaces have `is_focused=True` (which can happen transiently during event processing), this picks the first one in dict iteration order. Dict iteration order in Python 3.7+ is insertion order, which for workspace IDs is typically chronological. This is fine but arbitrary — it might be better to pick the one from the focused output.

**Severity**: Very low. The compositor should never send conflicting focus states, and if it does, any choice is a best-effort guess.

#### Issue C2: `_reconcile_diagnostics` appends notes unconditionally

```python
# reconcile.py:71-75
if engine.health is HealthState.STALE and not engine.diagnostics.desynced:
    engine.diagnostics = with_note(
        engine.diagnostics,
        note="health is stale without explicit desync marker",
    )
```

Since `reconcile()` is called after every event, this note gets appended repeatedly if the engine stays in STALE health without a desync marker. The `with_note` function appends to a tuple:

```python
def with_note(diag, *, note):
    return diag.model_copy(update={"notes": diag.notes + (note,)})
```

So `diagnostics.notes` will accumulate duplicate entries: `("health is stale without explicit desync marker", "health is stale without explicit desync marker", ...)`.

**Severity**: Medium. This is a memory leak (notes tuple grows unboundedly) and diagnostic noise. Should either deduplicate or check if the note already exists.

### 3.5 `core/broadcaster.py` — Pub/Sub

#### Issue BR1: `publish()` raises on first overflow, skipping remaining subscribers

```python
# broadcaster.py:62-66
raise SubscriptionOverflowError(
    "subscriber queue remained full after dropping oldest item",
    operation="broadcaster_publish",
    cause=exc,
) from exc
```

If one subscriber's queue overflows with FAIL_FAST (or the DROP_OLDEST fallback fails), the exception propagates immediately. Any subsequent subscribers in the iteration don't receive the published item. The `dead` list cleanup at lines 75-76 only runs if no exception was raised.

**Severity**: Medium. Multiple subscribers are a supported use case, and one misbehaving subscriber shouldn't prevent others from receiving updates.

#### Issue BR2: `close()` swallows queue-full errors silently

```python
# broadcaster.py:86-89
except asyncio.QueueFull:
    with contextlib.suppress(asyncio.QueueFull):
        _ = subscriber.queue.get_nowait()
        subscriber.queue.put_nowait(None)
```

If the queue is full, it drops one item and tries to put `None`. If that also fails (which shouldn't happen since we just removed an item), it silently gives up. The subscriber will never receive the termination signal and will hang on `await subscriber.queue.get()` forever.

**Severity**: Low. The `get_nowait()` + `put_nowait(None)` sequence should always succeed (we just freed a slot). But defensive code that silently swallows failures can mask bugs.

### 3.6 `api/snapshot.py` — Snapshot

Clean implementation. Frozen Pydantic model with `cached_property` for derived indexes.

#### Issue SN1: `cached_property` on frozen Pydantic model has a subtle interaction

Pydantic's `frozen=True` prevents attribute mutation via `__setattr__`. However, `functools.cached_property` works by setting the attribute on the instance after first access. This works because Pydantic models store cached properties in `__dict__` which bypasses `__setattr__` validation for cached properties specifically (Pydantic v2 handles this).

**Severity**: None currently. But this relies on Pydantic v2's internal behavior with cached properties. If Pydantic changes this in a future version, cached properties would break. Worth documenting as an assumption.

#### Issue SN2: `_freeze_mapping` creates a defensive copy

```python
if isinstance(value, dict):
    return MappingProxyType(dict(value))  # dict(value) = shallow copy
```

The shallow copy means the `MappingProxyType` wraps a new dict, but the values (Output, Workspace, Window objects) are shared references. Since those are frozen Pydantic models, this is safe. But it's an extra allocation for every snapshot creation.

**Severity**: None. Correctness is fine; performance impact is negligible.

### 3.7 `api/waiters.py` — Wait Utilities

#### Issue W1: `wait_until` doesn't handle health transitions during wait

```python
# waiters.py:59-63
async for snapshot in _subscription_iter(state):
    if not _health_allows_wait(snapshot=snapshot, config=config):
        continue  # ← Skips, doesn't error
    if predicate(snapshot):
        return snapshot
```

If health transitions to CLOSED or FAILED, `_health_allows_wait` returns False and the loop `continue`s. The loop will only exit when the subscription iterator ends (broadcaster closes), at which point it raises `WaitTimeoutError` with "state subscription closed before predicate matched." This is correct but the error message doesn't mention that health was the reason.

A CLOSED/FAILED health state should arguably raise a `StateLifecycleError` immediately rather than waiting for the subscription to close.

**Severity**: Low-Medium. The user gets an error eventually, but the error message is misleading about the root cause.

#### Issue W2: `wait_for_selector` calls `selector` twice

```python
# waiters.py:91-103
def _wrapped(snapshot: Snapshot) -> bool:
    value = selector(snapshot)    # First call
    ...

snapshot = await wait_until(state, _wrapped, ...)
return selector(snapshot)         # Second call (same snapshot)
```

The selector is called once inside the predicate and again on the matched snapshot. If selectors have side effects or are expensive, this is wasteful. Since selectors are pure functions on frozen snapshots, this is harmless in practice.

**Severity**: Very low. Could cache the result in a closure variable.

### 3.8 `api/config.py` — Configuration

#### Issue CF1: `strict_config` overwrites user-provided policy overrides

```python
def strict_config(**overrides: object) -> NiriStateConfig:
    base = NiriStateConfig(**overrides)
    state_update = cast(Mapping[str, Any], {
        "unknown_event_policy": UnknownEventPolicy.FAIL,      # Always overwritten
        "invariant_failure_policy": InvariantFailurePolicy.FAIL,
        "subscriber_overflow_policy": SubscriberOverflowPolicy.FAIL_FAST,
    })
    return base.model_copy(update=state_update)
```

If a user calls `strict_config(unknown_event_policy=UnknownEventPolicy.IGNORE)`, the IGNORE is silently overwritten with FAIL. The function name implies "strict defaults" but the behavior is "force strict regardless of what you asked for."

**Severity**: Low. This is a testing utility, and its behavior is reasonable for its purpose. But the semantics are surprising.

### 3.9 `api/selectors/` — Selector Functions

Clean, thin functions. Each takes a Snapshot and returns a typed result. No issues identified.

One observation: `outputs.py` has `get_workspaces_on_output` and `get_active_workspace_for_output`, while `workspaces.py` has `list_workspaces_on_output` and `get_active_workspace`. These are near-duplicates with slightly different names:

| outputs.py | workspaces.py |
|---|---|
| `get_workspaces_on_output(snap, name)` | `list_workspaces_on_output(snap, name)` |
| `get_active_workspace_for_output(snap, name)` | `get_active_workspace(snap, name)` |

Both call the same underlying cached properties. This is arguably a feature (find things from the perspective of the entity you have), but worth documenting.

### 3.10 `core/diagnostics.py` — Diagnostic Models

#### Issue D1: All `with_*` functions use `cast(Mapping[str, Any], ...)`

This pattern appears 8 times across diagnostics.py and reconcile.py:

```python
update = cast(Mapping[str, Any], {"key": value})
return diag.model_copy(update=update)
```

The `cast` is needed because `model_copy(update=...)` expects `Mapping[str, Any]` but dict literals are inferred as `dict[str, <specific_type>]`. This is a Pydantic v2 typing ergonomics issue. It's correct but verbose.

**Severity**: None (correctness). Style issue — could use a helper or `# type: ignore[arg-type]`.

### 3.11 `adapters/protocol.py` — Protocol Adapter

Clean re-export module. 48 types re-exported from niri-pypc. The `__all__` is comprehensive and sorted.

One observation: `ScreenshotCapturedEvent` is imported but never appears in reducers as doing anything meaningful (the reducer returns `frozenset()`). Same for `ConfigLoadedEvent`. These are correctly handled as no-ops, but could optionally trigger diagnostics or logging.

---

## 4. Concurrency & Lifecycle Review

### 4.1 Lock Usage

`NiriState._lock` protects `connect()`, `refresh()`, and `close()`. The mutation loop runs outside the lock (it's a fire-and-forget task). This means:

- `connect()` and `close()` are serialized: good
- `refresh()` holds the lock while doing I/O (opening bundle, running bootstrap): the lock blocks `close()` during refresh
- The mutation loop can process events while `refresh()` is setting up: this is handled by stopping the mutation loop before refresh begins

**Potential issue**: If `_transition_health()` is called from both the mutation loop (via `_mark_desynced`) and `refresh()` (via the lock-holder), there's no lock protecting `_engine.health`. The mutation loop does `await self._transition_health(HealthState.STALE)` without holding `_lock`. If `refresh()` concurrently sets health to RESYNCING, the transitions could conflict.

In practice, `refresh()` stops the mutation loop before transitioning health, so they shouldn't run concurrently. But the code doesn't structurally prevent it — it relies on temporal ordering.

**Severity**: Low. The stop-before-transition ordering is correct; this is a defensive-coding observation.

### 4.2 Task Lifecycle

- `_mutation_task`: Created by `_start_mutation_loop()`, cancelled by `_stop_mutation_loop()`. Clean lifecycle.
- `_resync._task`: Created by `start()`, cancelled by `close()`. Clean lifecycle.
- Bootstrap `buffer_task`: Created and cancelled within `run_bootstrap()`. Local lifecycle.

All tasks properly handle `CancelledError`. Good.

### 4.3 Shutdown Ordering

```python
# state.py:366-393 (close)
await self._stop_mutation_loop()       # 1. Stop processing events
await self._transition_health(CLOSED)  # 2. Mark closed
self._snapshot = ...freeze()           # 3. Create final snapshot
await self._broadcaster.publish(...)   # 4. Notify subscribers
await self._bundle.close()             # 5. Close connection
await self._resync.close()             # 6. Stop resync
await self._broadcaster.close()        # 7. Close broadcaster
```

This is well-ordered. Subscribers get the CLOSED notification before the broadcaster shuts down. The connection is closed after the final publish. Good.

**Minor concern**: If `self._bundle.close()` raises, `self._resync.close()` and `self._broadcaster.close()` are skipped. These should ideally use `try/finally` or `contextlib.AsyncExitStack`.

---

## 5. Error Handling & Resilience

### 5.1 Error Hierarchy

```
NiriStateError
├── StateConfigError
├── StateLifecycleError (current_state, target_state)
├── BootstrapError (query, retryable=True)
├── ReductionError (event_type, revision, retryable=False)
├── InvariantError (violations, revision)
├── DesyncError (event_type, revision, retryable=True)
├── ResyncError
├── SubscriptionOverflowError
└── WaitTimeoutError (timeout) ← also inherits TimeoutError
```

**Verdict**: Well-designed. The `retryable` flag is a good pattern. The double inheritance of `WaitTimeoutError` (both `TimeoutError` and `NiriStateError`) enables catching with either `except TimeoutError` or `except NiriStateError`.

### 5.2 Policy-Driven Error Behavior

Five policies control error behavior. The defaults are all "graceful degradation" (STALE, DROP_OLDEST, MANUAL), with `strict_config()` available for testing. This is a strong pattern for a library — it lets users choose their failure mode.

### 5.3 Unhandled Edge Cases

1. **Bootstrap fails after partial state**: If `query_overview()` fails but previous queries succeeded, the bootstrap error wraps the original exception. But the partial engine state is discarded — good.

2. **Resync exhaustion**: When auto-resync exhausts all attempts, it logs a warning and returns silently. The state remains STALE/RESYNCING. There's no callback or event to notify the user that auto-recovery failed.

3. **Double-close**: `close()` is idempotent (early return if `_closed`). Good.

4. **Connect after close**: Raises `StateLifecycleError`. Good.

5. **Refresh while not connected**: Raises `StateLifecycleError`. Good.

---

## 6. Type Safety & API Contracts

### 6.1 Strict mypy Configuration

```toml
[tool.mypy]
strict = true
```

With all the strict flags enabled. Good.

### 6.2 Type Annotations Quality

- All functions have return type annotations
- All parameters have type annotations
- `from __future__ import annotations` used consistently (deferred evaluation)
- Generic type variable in `wait_for_selector[T]` (PEP 695 syntax)
- Protocols used for dependency inversion (`WaitableState`, `_Refreshable`)

### 6.3 Type Holes

1. **`object` in Reducer typedef** (discussed in R1)
2. **`cast(Mapping[str, Any], ...)` pattern** (discussed in D1)
3. **`FakeClient.request` returns `object`** in tests — loses type safety
4. **`FakeBundle` inherits from `NiriConnectionBundle`** — the fake passes arbitrary objects that might not match the real types exactly

### 6.4 Public API Surface

The `__init__.py` exports are well-curated. The `__all__` list is sorted and comprehensive. Notable exclusions from the public API:

- `PublishedState` — only accessible through `subscribe()`
- `EngineState` — correctly internal
- All `core/` modules — correctly hidden
- Selectors are accessible via `niri_state.api.selectors.*` but not re-exported at package level

**Observation**: Users need to import selectors from `niri_state.api.selectors.windows` etc., but `PublishedState` from `niri_state.core.broadcaster`. This is inconsistent — `PublishedState` should be re-exported from `api/` or `__init__.py`.

---

## 7. Test Suite Assessment

### 7.1 Coverage Summary

| Area | Unit Tests | Integration Tests | Coverage |
|------|-----------|-------------------|----------|
| Snapshot | test_snapshot.py (3 tests) | — | Derived properties only |
| Config | test_config.py | — | Unknown (not read) |
| Health | test_health.py | — | State transitions |
| Reducers | test_reducers.py (4 tests) | — | 4 of 14 reducers |
| Reconcile | test_reconcile.py (4 tests) | — | All 5 reconcile functions |
| Invariants | test_invariants.py (2 tests) | — | 2 of 7 invariant checks |
| Broadcaster | test_broadcaster.py (1 test) | — | Subscribe only; no publish tests |
| Selectors | test_selectors.py | — | Unknown coverage |
| Waiters | test_waiters.py (2 tests) | — | wait_until + watch |
| Diagnostics | test_diagnostics.py | — | Unknown |
| Resync | test_resync.py | — | Unknown |
| Bootstrap | — | test_bootstrap.py (2 tests) | Happy path + buffered replay |
| Mutation loop | — | test_runtime_mutation_loop.py (1 test) | Event processing |
| Close | — | test_close_lifecycle.py (1 test) | Basic close |
| Desync/Resync | — | test_desync_and_auto_resync.py (1 test) | Auto-resync |
| Refresh | — | test_refresh.py (1 test) | Snapshot replacement |
| Regressions | — | test_store_regressions.py (4 tests) | Edge cases |
| Replay | — | test_replay_traces.py (1 test) | Event sequence convergence |
| Architecture | test_architecture.py (3 tests) | — | Dependency rules |

### 7.2 Gaps

#### Critical gaps:
1. **Broadcaster publish with overflow** — No test for DROP_OLDEST behavior or FAIL_FAST error propagation
2. **Multiple subscribers** — No test that multiple concurrent subscribers work correctly
3. **Mutation loop error paths** — No test for `DesyncError` handling in the mutation loop, no test for the `_fail()` path
4. **Reducer coverage** — Only 4 of 14 reducers have direct unit tests. Missing: `reduce_window_opened_or_changed`, `reduce_window_closed`, `reduce_window_focus_changed`, `reduce_window_focus_timestamp_changed`, `reduce_workspaces_changed`, `reduce_workspace_active_window_changed`, `reduce_workspace_urgency_changed`, `reduce_keyboard_layouts_changed`, `reduce_keyboard_layout_switched`, `reduce_overview_opened_or_closed`
5. **Invariant coverage** — Only 2 of 7 invariant checks tested directly
6. **Close during active subscription** — No test for what happens to subscribers when state is closed

#### Missing error path tests:
- `connect()` when already started
- `connect()` when already closed
- `refresh()` when not connected
- `refresh()` failure recovery (bundle open fails mid-refresh)
- `_handle_invariant_violations` with FAIL policy
- `_transition_health` with invalid transition

#### Missing edge case tests:
- Empty state (no windows, no workspaces, no outputs)
- Multiple outputs with workspaces
- Window with `workspace_id=None` (floating window)
- Keyboard with empty `names` list
- Overview state changes

### 7.3 Test Infrastructure

**Strengths**:
- Factory pattern with `make_*` functions is excellent
- `FakeBundle`/`FakeClient`/`FakeEventStream` provide clean test doubles
- TypeAdapter-based factories ensure protocol compliance
- Architecture tests are creative and valuable

**Weaknesses**:
- `_open_bundle` monkey-patching is brittle (discussed above)
- No pytest parametrize usage for testing multiple reducer types
- No property-based testing (hypothesis) for invariant checking
- `DummyState.subscribe()` yields `object` not `PublishedState`, making it useless for testing subscription flows

### 7.4 Test Quality

The existing tests are well-written: focused, deterministic, and testing the right things. The gap is in *quantity*, not *quality*. The test suite feels like a foundation that hasn't been fully built out yet.

---

## 8. niri-pypc Dependency Analysis

### 8.1 Architecture

niri-pypc is a well-structured async IPC client with four layers:
- **API**: `NiriClient` (request-response), `NiriEventStream` (event streaming), `NiriConnectionBundle` (convenience wrapper)
- **Transport**: `UnixConnection` for raw socket I/O
- **Runtime**: `LifecycleManager` state machine
- **Types**: Pydantic models generated from niri-ipc spec v25.11

### 8.2 Integration Points

niri-state uses niri-pypc through the adapter layer:
1. **Connection**: `NiriConnectionBundle.open()` for connecting
2. **Requests**: `NiriClient.request()` for bootstrap queries (8 request types)
3. **Events**: `NiriEventStream.__aiter__()` for the mutation loop (16 event types)
4. **Types**: All protocol models (Output, Window, Workspace, etc.)

### 8.3 Version Coupling

```toml
dependencies = ["niri-pypc>=0.3.1,<0.4"]
```

Tight coupling to niri-pypc 0.3.x. The `Compatibility` model in diagnostics checks runtime niri version against schema version:

```python
warnings=() if version in {None, PYPC_SCHEMA_VERSION}
    else (f"runtime niri version {version} differs from schema version {PYPC_SCHEMA_VERSION}",)
```

This is good forward-compatibility awareness.

### 8.4 niri-pypc Quality Assessment

niri-pypc is high quality:
- Clean layered architecture
- Rich error hierarchy with context
- Lifecycle state machine for event streams
- Forward-compatible event handling (UnknownEvent)
- Overloaded request methods for type safety
- Generated types from upstream spec

**One concern**: niri-pypc's `NiriClient` creates a new Unix socket connection per request. This means bootstrap's 8 sequential queries create 8 separate connections. Connection pooling is not available.

---

## 9. Performance Considerations

### 9.1 Snapshot Creation

Every event creates a new `Snapshot` via `engine.freeze()`. This involves:
1. `require_initialized()` — two None checks
2. `Snapshot(...)` — Pydantic model construction
3. `_freeze_mapping` validator — creates `MappingProxyType(dict(value))` for outputs, workspaces, windows (3 shallow copies)
4. Cached properties are lazy — only computed on first access

For a typical system with ~10 windows, ~5 workspaces, ~2 outputs, this is fast. But under heavy event load (e.g., rapidly resizing windows which triggers `WindowLayoutsChanged` events), the allocation rate could be noticeable.

### 9.2 Reducer Allocations

Reducers that update individual items use `model_copy(update={...})`:

```python
engine.windows[event.id] = window.model_copy(update={"is_urgent": event.urgent})
```

This creates a new Window object for each change. With frozen Pydantic models, this is the correct approach, but it means every window urgency change allocates a new Window, a new dict entry, and eventually a new Snapshot.

### 9.3 Reconciliation Cost

`reconcile()` is called after every event and iterates through workspaces (for relationship checking) and diagnostics. For typical workspace counts (<10), this is negligible.

### 9.4 Invariant Checking Cost

`collect_invariant_violations()` accesses cached properties `active_workspace_by_output`, `workspaces_by_output`, and `windows_by_workspace`. These involve sorting. For typical sizes, this is negligible. But invariant checking creates temporary lists and performs sorting on every event — it could be made conditional (only check after significant changes).

---

## 10. Issues by Severity

### High
*(None identified — no correctness bugs found)*

### Medium
| ID | Issue | Location |
|----|-------|----------|
| S1 | Bootstrap event buffering race window | `core/bootstrap.py:170-181` |
| S2 | `SubscriptionOverflowError` terminates mutation loop | `api/state.py:214` |
| S5 | No async context manager protocol | `api/state.py` |
| C2 | Reconcile diagnostics appends duplicate notes | `core/reconcile.py:71-75` |
| BR1 | Publish raises on first overflow, skipping remaining subscribers | `core/broadcaster.py:62-66` |
| — | Test coverage gaps (reducers, broadcaster, error paths) | `tests/` |

### Low
| ID | Issue | Location |
|----|-------|----------|
| S3 | `subscribe()` initial yield uses misleading changeset cause | `api/state.py:94-97` |
| S4 | `refresh()` closes old bundle after starting new loop | `api/state.py:361-362` |
| B1 | Sequential bootstrap queries (performance) | `core/bootstrap.py:92-100` |
| R1 | `Reducer` typedef uses `object` instead of specific event type | `core/reducers.py:40` |
| R2 | `updated` dict typed as `dict[int, object]` | `core/reducers.py:206` |
| W1 | `wait_until` doesn't error on terminal health states | `api/waiters.py:59-63` |
| CF1 | `strict_config` silently overwrites user overrides | `api/config.py:53-65` |
| — | `InvariantViolation` lives in core but leaks into public API | `core/diagnostics.py` / `api/errors.py` |
| — | `PublishedState` not re-exported from public API | `core/broadcaster.py` |
| — | Duplicate selector functions across outputs.py/workspaces.py | `api/selectors/` |
| — | Shutdown doesn't use try/finally for cleanup ordering | `api/state.py:388-393` |

### Informational
| ID | Issue | Location |
|----|-------|----------|
| R3 | `event_count` includes unknown events | `core/reducers.py:59-60` |
| SN1 | `cached_property` relies on Pydantic v2 frozen model behavior | `api/snapshot.py` |
| SN2 | `_freeze_mapping` creates defensive shallow copy | `api/snapshot.py:43` |
| W2 | `wait_for_selector` calls selector twice | `api/waiters.py:91-103` |
| D1 | Verbose `cast(Mapping[str, Any], ...)` pattern | Multiple files |
| — | `_open_bundle` monkey-patching in tests | `tests/integration/` |

---

## 11. Recommendations

### Immediate (before 1.0)

1. **Add `__aenter__`/`__aexit__` to `NiriState`**
   ```python
   async def __aenter__(self) -> NiriState:
       await self.connect()
       return self
   async def __aexit__(self, *exc) -> None:
       await self.close()
   ```

2. **Fix duplicate notes in `_reconcile_diagnostics`**
   ```python
   note = "health is stale without explicit desync marker"
   if note not in engine.diagnostics.notes:
       engine.diagnostics = with_note(engine.diagnostics, note=note)
   ```

3. **Make `close()` cleanup use try/finally**
   ```python
   try:
       await self._bundle.close()
   finally:
       try:
           await self._resync.close()
       finally:
           await self._broadcaster.close()
   ```

4. **Re-export `PublishedState` from `__init__.py`** — it's part of the public subscription API.

5. **Move `InvariantViolation` to `api/` or a shared module** — it's part of the public error surface.

6. **Add a `bundle_factory` parameter to `NiriState`** — replace monkey-patching with proper DI:
   ```python
   def __init__(self, config=None, *, bundle_factory=None):
       self._bundle_factory = bundle_factory or self._default_open_bundle
   ```

### Soon (before 1.0 or shortly after)

7. **Parallelize bootstrap queries** with `asyncio.gather()` — 8x speedup for connect time.

8. **Isolate subscriber failures in `publish()`** — catch per-subscriber errors without aborting the loop:
   ```python
   for subscriber in self._subscribers:
       try:
           subscriber.queue.put_nowait(item)
       except asyncio.QueueFull:
           # handle per subscriber, don't raise
   ```

9. **Fill test coverage gaps** — prioritize:
   - All 14 reducers (parametrized)
   - Broadcaster publish with multiple subscribers
   - Mutation loop desync and failure paths
   - Close-during-subscription behavior

10. **Add `wait_until` terminal health detection** — raise `StateLifecycleError` immediately when health is CLOSED/FAILED instead of waiting for subscription to close.

### Later (nice-to-have)

11. **Consider event batching** — if niri sends rapid bursts of events, creating a snapshot per event is wasteful. A debounce/batch mechanism could reduce allocations.

12. **Property-based testing with Hypothesis** — generate random event sequences and verify invariants always hold.

13. **Metrics/observability hooks** — callback or event for monitoring (events processed, snapshot latency, queue depths).

14. **Generic `Reducer` protocol** — for type-safety purists, a properly-typed reducer registry.

---

## Appendix A: File Inventory

| File | Lines | Purpose |
|------|-------|---------|
| `__init__.py` | 53 | Public API exports |
| `_version.py` | 1 | Version string |
| `api/__init__.py` | 7 | Module marker |
| `api/state.py` | 394 | Main orchestrator |
| `api/snapshot.py` | 93 | Immutable state snapshot |
| `api/config.py` | 66 | Configuration and policies |
| `api/errors.py` | 151 | Error hierarchy |
| `api/health.py` | 67 | Health state machine |
| `api/changes.py` | 105 | Change tracking |
| `api/waiters.py` | 104 | Subscription utilities |
| `api/selectors/__init__.py` | 20 | Selector module exports |
| `api/selectors/windows.py` | 22 | Window queries |
| `api/selectors/workspaces.py` | 25 | Workspace queries |
| `api/selectors/outputs.py` | 25 | Output queries |
| `api/selectors/focus.py` | 29 | Focus queries |
| `api/selectors/keyboard.py` | 12 | Keyboard queries |
| `api/selectors/overview.py` | 13 | Overview queries |
| `api/selectors/aggregates.py` | 62 | Composite queries |
| `core/__init__.py` | 5 | Module marker |
| `core/bootstrap.py` | 218 | Initial state building |
| `core/engine_state.py` | 54 | Mutable state container |
| `core/reducers.py` | 347 | Event processing |
| `core/reconcile.py` | 76 | State consistency |
| `core/invariants.py` | 110 | Snapshot validation |
| `core/broadcaster.py` | 107 | Pub/sub mechanism |
| `core/resync.py` | 83 | Auto-resync coordination |
| `core/diagnostics.py` | 85 | Diagnostic models |
| `adapters/__init__.py` | 5 | Module marker |
| `adapters/protocol.py` | 97 | niri-pypc re-exports |
| `observability/__init__.py` | 5 | Module marker |
| `observability/logging.py` | 13 | Logger factory |
| **Total** | **~2500** | |

## Appendix B: Dependency Graph

```
niri_state.__init__
  └─ api.state ← api.changes, api.config, api.errors, api.health, api.snapshot
       └─ core.bootstrap ← core.engine_state, core.reducers, core.reconcile, core.invariants, core.diagnostics
       └─ core.broadcaster ← api.snapshot, api.changes, api.config, api.errors
       └─ core.resync ← api.changes, api.config
       └─ adapters.protocol ← niri_pypc
       └─ observability.logging ← stdlib logging
```
