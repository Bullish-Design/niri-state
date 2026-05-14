# V2 Refactor Implementation Guide

**Source**: `V2_REFACTOR_CODE_REVIEW.md`
**Target branch**: `v2-rewrite`
**Prerequisite**: `devenv shell -- uv sync --extra dev`

This guide walks you through every fix, refactor, and improvement identified in the code review, organized so that each step builds on the previous one. Complete each step fully (edit + test + lint) before moving to the next.

**Quality gate after every step**:
```bash
devenv shell -- ruff check .
devenv shell -- ruff format --check .
devenv shell -- pytest -x
```

If you change type signatures or public API surface, also run:
```bash
devenv shell -- ty check .
```

---

## Table of Contents

- [Phase 1: Bug Fixes (Medium-severity correctness issues)](#phase-1-bug-fixes)
  - [Step 1: Fix duplicate notes memory leak in reconcile](#step-1-fix-duplicate-notes-memory-leak-in-reconcile)
  - [Step 2: Isolate subscriber failures in broadcaster publish](#step-2-isolate-subscriber-failures-in-broadcaster-publish)
  - [Step 3: Make close() cleanup resilient with try/finally](#step-3-make-close-cleanup-resilient-with-tryfinally)
- [Phase 2: API Improvements (Medium-severity usability)](#phase-2-api-improvements)
  - [Step 4: Add async context manager to NiriState](#step-4-add-async-context-manager-to-niristate)
  - [Step 5: Add bundle_factory dependency injection to NiriState](#step-5-add-bundle_factory-dependency-injection-to-niristate)
  - [Step 6: Re-export PublishedState from public API](#step-6-re-export-publishedstate-from-public-api)
- [Phase 3: Architectural Cleanup (Low-severity layering)](#phase-3-architectural-cleanup)
  - [Step 7: Move InvariantViolation to api layer](#step-7-move-invariantviolation-to-api-layer)
  - [Step 8: Add architecture test for api importing core data types](#step-8-add-architecture-test-for-api-importing-core-data-types)
  - [Step 9: Fix subscribe() initial changeset semantics](#step-9-fix-subscribe-initial-changeset-semantics)
- [Phase 4: Type Safety Improvements (Low-severity types)](#phase-4-type-safety-improvements)
  - [Step 10: Fix Reducer typedef to be properly typed](#step-10-fix-reducer-typedef-to-be-properly-typed)
  - [Step 11: Fix dict[int, object] type annotation in reduce_workspace_activated](#step-11-fix-dictint-object-type-annotation-in-reduce_workspace_activated)
- [Phase 5: Resilience Improvements (Low-medium severity)](#phase-5-resilience-improvements)
  - [Step 12: Add terminal health detection to wait_until](#step-12-add-terminal-health-detection-to-wait_until)
  - [Step 13: Fix strict_config to respect explicit overrides](#step-13-fix-strict_config-to-respect-explicit-overrides)
  - [Step 14: Cache selector result in wait_for_selector](#step-14-cache-selector-result-in-wait_for_selector)
  - [Step 15: Wrap old_bundle.close() in refresh() with try/except](#step-15-wrap-old_bundleclose-in-refresh-with-tryexcept)
- [Phase 6: Performance Improvements](#phase-6-performance-improvements)
  - [Step 16: Parallelize bootstrap queries with asyncio.gather](#step-16-parallelize-bootstrap-queries-with-asynciogather)
- [Phase 7: Test Coverage Expansion](#phase-7-test-coverage-expansion)
  - [Step 17: Fix DummyState.subscribe to yield PublishedState](#step-17-fix-dummystatesubscribe-to-yield-publishedstate)
  - [Step 18: Add unit tests for all 14 reducers](#step-18-add-unit-tests-for-all-14-reducers)
  - [Step 19: Add broadcaster publish tests](#step-19-add-broadcaster-publish-tests)
  - [Step 20: Add invariant coverage tests](#step-20-add-invariant-coverage-tests)
  - [Step 21: Add NiriState lifecycle error path tests](#step-21-add-niristate-lifecycle-error-path-tests)
  - [Step 22: Add mutation loop error path tests](#step-22-add-mutation-loop-error-path-tests)
  - [Step 23: Add close-during-subscription test](#step-23-add-close-during-subscription-test)
  - [Step 24: Add edge case tests](#step-24-add-edge-case-tests)

---

## Phase 1: Bug Fixes

### Step 1: Fix duplicate notes memory leak in reconcile

**Issue**: C2 (Medium). `_reconcile_diagnostics` in `core/reconcile.py:71-75` appends the note `"health is stale without explicit desync marker"` on every call to `reconcile()` when health is STALE without a desync marker. Since `reconcile()` runs after every event, this creates unbounded tuple growth.

**File**: `src/niri_state/core/reconcile.py`

**Current code** (lines 67-75):
```python
def _reconcile_diagnostics(engine: EngineState) -> None:
    if engine.health is HealthState.LIVE and engine.diagnostics.desynced:
        update = cast(Mapping[str, Any], {"desynced": False})
        engine.diagnostics = engine.diagnostics.model_copy(update=update)
    if engine.health is HealthState.STALE and not engine.diagnostics.desynced:
        engine.diagnostics = with_note(
            engine.diagnostics,
            note="health is stale without explicit desync marker",
        )
```

**Change**: Add a guard to check if the note already exists before appending:

```python
def _reconcile_diagnostics(engine: EngineState) -> None:
    if engine.health is HealthState.LIVE and engine.diagnostics.desynced:
        update = cast(Mapping[str, Any], {"desynced": False})
        engine.diagnostics = engine.diagnostics.model_copy(update=update)
    if engine.health is HealthState.STALE and not engine.diagnostics.desynced:
        note = "health is stale without explicit desync marker"
        if note not in engine.diagnostics.notes:
            engine.diagnostics = with_note(engine.diagnostics, note=note)
```

**Test**: Add to `tests/unit/test_reconcile.py`:

```python
def test_reconcile_does_not_duplicate_stale_note() -> None:
    engine = EngineState.empty()
    engine.keyboard_layouts = make_keyboard_layouts()
    engine.overview = make_overview()
    engine.health = HealthState.STALE

    reconcile(engine)
    reconcile(engine)
    reconcile(engine)

    stale_notes = [n for n in engine.diagnostics.notes if "stale without" in n]
    assert len(stale_notes) == 1
```

Add the import `from niri_state.api.health import HealthState` if not already present.

**Verify**: `devenv shell -- pytest tests/unit/test_reconcile.py -x`

---

### Step 2: Isolate subscriber failures in broadcaster publish

**Issue**: BR1 (Medium). In `core/broadcaster.py`, the `publish()` method raises on the first subscriber overflow, preventing remaining subscribers from receiving the published item.

**File**: `src/niri_state/core/broadcaster.py`

**Current code** (lines 42-76):
```python
async def publish(self, item: PublishedState) -> None:
    if self._closed:
        return

    dead: list[_Subscriber] = []
    for subscriber in self._subscribers:
        try:
            subscriber.queue.put_nowait(item)
        except asyncio.QueueFull:
            policy = self._config.subscriber_overflow_policy
            if policy is SubscriberOverflowPolicy.DROP_OLDEST:
                _LOGGER.warning("subscriber queue full; dropping oldest item")
                try:
                    _ = subscriber.queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    subscriber.queue.put_nowait(item)
                except asyncio.QueueFull as exc:
                    dead.append(subscriber)
                    raise SubscriptionOverflowError(
                        "subscriber queue remained full after dropping oldest item",
                        operation="broadcaster_publish",
                        cause=exc,
                    ) from exc
            else:
                _LOGGER.error("subscriber queue overflowed with fail-fast policy")
                dead.append(subscriber)
                raise SubscriptionOverflowError(
                    "subscriber queue overflowed",
                    operation="broadcaster_publish",
                ) from None

    for subscriber in dead:
        self._subscribers.discard(subscriber)
```

**Change**: Collect errors per-subscriber, deliver to all, then raise the first error if any:

```python
async def publish(self, item: PublishedState) -> None:
    if self._closed:
        return

    dead: list[_Subscriber] = []
    first_error: SubscriptionOverflowError | None = None

    for subscriber in self._subscribers:
        try:
            subscriber.queue.put_nowait(item)
        except asyncio.QueueFull:
            policy = self._config.subscriber_overflow_policy
            if policy is SubscriberOverflowPolicy.DROP_OLDEST:
                _LOGGER.warning("subscriber queue full; dropping oldest item")
                try:
                    _ = subscriber.queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    subscriber.queue.put_nowait(item)
                except asyncio.QueueFull as exc:
                    dead.append(subscriber)
                    if first_error is None:
                        first_error = SubscriptionOverflowError(
                            "subscriber queue remained full after dropping oldest item",
                            operation="broadcaster_publish",
                            cause=exc,
                        )
            else:
                _LOGGER.error("subscriber queue overflowed with fail-fast policy")
                dead.append(subscriber)
                if first_error is None:
                    first_error = SubscriptionOverflowError(
                        "subscriber queue overflowed",
                        operation="broadcaster_publish",
                    )

    for subscriber in dead:
        self._subscribers.discard(subscriber)

    if first_error is not None:
        raise first_error
```

**Test**: Add to `tests/unit/test_broadcaster.py`:

```python
import asyncio

import pytest

from niri_state.api.config import NiriStateConfig, SubscriberOverflowPolicy
from niri_state.api.changes import ChangeCause, ChangeSet, ChangedDomain
from niri_state.api.errors import SubscriptionOverflowError
from niri_state.api.health import HealthState
from niri_state.api.snapshot import Snapshot
from niri_state.core.broadcaster import Broadcaster, PublishedState
from niri_state.core.diagnostics import Compatibility, Diagnostics
from tests.factories.protocol import make_keyboard_layouts, make_output, make_overview


def _make_published(revision: int = 1) -> PublishedState:
    snapshot = Snapshot(
        revision=revision,
        timestamp=0.0,
        health=HealthState.LIVE,
        outputs={"HDMI-A-1": make_output()},
        workspaces={},
        windows={},
        focused_workspace_id=None,
        focused_window_id=None,
        keyboard_layouts=make_keyboard_layouts(),
        overview=make_overview(),
        diagnostics=Diagnostics(),
        compatibility=Compatibility(),
    )
    return PublishedState(
        snapshot=snapshot,
        changes=ChangeSet(revision=revision, cause=ChangeCause.EVENT, domains=frozenset()),
    )


@pytest.mark.asyncio
async def test_publish_delivers_to_all_subscribers() -> None:
    config = NiriStateConfig(subscriber_queue_size=8)
    broadcaster = Broadcaster(config)
    sub1 = broadcaster.subscribe()
    sub2 = broadcaster.subscribe()

    item = _make_published()
    await broadcaster.publish(item)
    await broadcaster.close()

    items1 = [x async for x in sub1]
    items2 = [x async for x in sub2]
    assert len(items1) == 1
    assert len(items2) == 1


@pytest.mark.asyncio
async def test_publish_overflow_still_delivers_to_healthy_subscribers() -> None:
    config = NiriStateConfig(
        subscriber_queue_size=1,
        subscriber_overflow_policy=SubscriberOverflowPolicy.FAIL_FAST,
    )
    broadcaster = Broadcaster(config)
    slow_sub = broadcaster.subscribe()
    fast_sub = broadcaster.subscribe()

    # Fill slow_sub's queue
    await broadcaster.publish(_make_published(revision=1))

    # Second publish should overflow slow_sub but still deliver to fast_sub
    with pytest.raises(SubscriptionOverflowError):
        await broadcaster.publish(_make_published(revision=2))

    await broadcaster.close()

    # fast_sub should have received both items
    fast_items = [x async for x in fast_sub]
    assert len(fast_items) == 2
```

**Verify**: `devenv shell -- pytest tests/unit/test_broadcaster.py -x`

---

### Step 3: Make close() cleanup resilient with try/finally

**Issue**: Shutdown ordering in `api/state.py:388-393` — if `self._bundle.close()` raises, `self._resync.close()` and `self._broadcaster.close()` are skipped.

**File**: `src/niri_state/api/state.py`

**Current code** (lines 388-393):
```python
            if self._bundle is not None:
                await self._bundle.close()

            await self._resync.close()
            await self._broadcaster.close()
            _LOGGER.info("close completed")
```

**Change**: Wrap in nested try/finally to guarantee all cleanup runs:

```python
            try:
                if self._bundle is not None:
                    await self._bundle.close()
            finally:
                try:
                    await self._resync.close()
                finally:
                    await self._broadcaster.close()
            _LOGGER.info("close completed")
```

**Test**: Existing close tests should still pass. No new test needed (the old bundle close failure is an edge case of the niri-pypc transport layer).

**Verify**: `devenv shell -- pytest tests/integration/test_close_lifecycle.py -x`

---

## Phase 2: API Improvements

### Step 4: Add async context manager to NiriState

**Issue**: S5 (Medium). `NiriState` doesn't implement `__aenter__`/`__aexit__`, requiring manual `close()` calls and risking resource leaks.

**File**: `src/niri_state/api/state.py`

**Change**: Add these two methods to the `NiriState` class, after the `start()` method (around line 159):

```python
    async def __aenter__(self) -> NiriState:
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        await self.close()
```

**Test**: Add to `tests/integration/test_close_lifecycle.py`:

```python
@pytest.mark.asyncio
async def test_context_manager_opens_and_closes(fake_runtime_bundle) -> None:
    state = NiriState()

    async def _open_bundle():
        return fake_runtime_bundle

    state._open_bundle = _open_bundle  # type: ignore[method-assign]

    async with state:
        assert state.snapshot is not None
        assert state.health() in {HealthState.LIVE, HealthState.STALE}

    assert state.snapshot.health is HealthState.CLOSED
```

**Verify**: `devenv shell -- pytest tests/integration/test_close_lifecycle.py -x`

---

### Step 5: Add bundle_factory dependency injection to NiriState

**Issue**: Every integration test monkey-patches `state._open_bundle = ...` with `# type: ignore[method-assign]`. This is a code smell indicating missing DI.

**File**: `src/niri_state/api/state.py`

**Change 1**: Update `__init__` to accept an optional factory (line 60):

```python
    def __init__(
        self,
        config: NiriStateConfig | None = None,
        *,
        bundle_factory: Callable[[], Awaitable[NiriConnectionBundle]] | None = None,
    ) -> None:
        self._config = config or NiriStateConfig()
        self._lock = asyncio.Lock()
        self._started = False
        self._closed = False

        self._bundle: NiriConnectionBundle | None = None
        self._engine: EngineState | None = None
        self._snapshot: Snapshot | None = None
        self._revision = 0

        self._mutation_task: asyncio.Task[None] | None = None
        self._broadcaster = Broadcaster(self._config)
        self._resync = ResyncCoordinator(self, self._config)

        if bundle_factory is not None:
            self._open_bundle = bundle_factory  # type: ignore[assignment]
```

Add the necessary imports at the top of the file:
```python
from collections.abc import AsyncIterator, Awaitable, Callable
```

(Replace the existing `from collections.abc import AsyncIterator` line.)

**Change 2**: Update `open()` classmethod to accept and pass through the factory:

```python
    @classmethod
    async def open(
        cls,
        config: NiriStateConfig | None = None,
        *,
        bundle_factory: Callable[[], Awaitable[NiriConnectionBundle]] | None = None,
    ) -> NiriState:
        state = cls(config, bundle_factory=bundle_factory)
        await state.connect()
        return state
```

**Change 3**: Migrate integration tests. In each test file that does `state._open_bundle = ...`, change to use the constructor parameter instead. For example, in `tests/integration/test_runtime_mutation_loop.py`:

**Before**:
```python
    state = NiriState()

    async def _open_bundle() -> FakeBundle:
        return fake_runtime_bundle

    state._open_bundle = _open_bundle  # type: ignore[method-assign]
```

**After**:
```python
    async def _open_bundle() -> FakeBundle:
        return fake_runtime_bundle

    state = NiriState(bundle_factory=_open_bundle)
```

Apply this pattern to all integration test files:
- `tests/integration/test_runtime_mutation_loop.py`
- `tests/integration/test_close_lifecycle.py`
- `tests/integration/test_desync_and_auto_resync.py`
- `tests/integration/test_refresh.py`
- `tests/integration/test_store_regressions.py`

**Important**: Some tests use a list of bundles and `bundles.pop(0)` — the pattern is the same, just pass the lambda/function as `bundle_factory=`.

**Verify**: `devenv shell -- pytest tests/ -x`

---

### Step 6: Re-export PublishedState from public API

**Issue**: Users must import `PublishedState` from `niri_state.core.broadcaster`, which is an internal module. It should be part of the public API surface.

**File 1**: `src/niri_state/api/__init__.py` — add the re-export:

```python
from niri_state.core.broadcaster import PublishedState

__all__ = ["PublishedState"]
```

(Or just add `PublishedState` to the existing `__all__` if one exists.)

**File 2**: `src/niri_state/__init__.py` — add to imports and `__all__`:

Add this import after the existing imports:
```python
from niri_state.core.broadcaster import PublishedState
```

Add `"PublishedState"` to the `__all__` list (maintaining alphabetical order — insert between `"NiriStateError"` and `"ReductionError"`).

**Verify**: `devenv shell -- python -c "from niri_state import PublishedState; print(PublishedState)"`

---

## Phase 3: Architectural Cleanup

### Step 7: Move InvariantViolation to api layer

**Issue**: `InvariantViolation` is defined in `core/diagnostics.py` but used in `api/errors.py` (in the `InvariantError` class). This is a cross-layer import where api imports a core data model that leaks into the public API.

This is a multi-file refactor. The goal is to define `InvariantViolation` in `api/` and have `core/` import it from there.

**Step 7a**: Create `InvariantViolation` in `api/errors.py` (or a new `api/types.py` — `api/errors.py` is simpler since that's where it's consumed).

Move the class from `core/diagnostics.py` to `api/errors.py`. Add it before the `NiriStateError` class definition:

```python
from pydantic import BaseModel, ConfigDict

class InvariantViolation(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    path: tuple[str | int, ...] = ()
    severity: str = "error"
```

Add the necessary pydantic imports to `api/errors.py` (they may not be there yet).

Remove the `from niri_state.core.diagnostics import InvariantViolation` import from `api/errors.py` (line 5).

**Step 7b**: In `core/diagnostics.py`, remove the `InvariantViolation` class definition and instead import it:

```python
from niri_state.api.errors import InvariantViolation
```

**Wait** — this creates a circular import: `api/errors.py` would be imported by `core/diagnostics.py`, but `api/state.py` imports from both. Check if this is an issue.

Actually, the better approach: put `InvariantViolation` in its own small module to avoid circular imports.

**Alternative approach — create `api/types.py`**:

Create `src/niri_state/api/types.py`:
```python
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class InvariantViolation(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    path: tuple[str | int, ...] = ()
    severity: str = "error"
```

Then update imports everywhere:

1. `api/errors.py` line 5: change `from niri_state.core.diagnostics import InvariantViolation` to `from niri_state.api.types import InvariantViolation`

2. `core/diagnostics.py`: remove the `InvariantViolation` class definition (lines 9-15). Add: `from niri_state.api.types import InvariantViolation`

3. `core/invariants.py`: if it imports `InvariantViolation` from `core/diagnostics`, update to `from niri_state.api.types import InvariantViolation`

4. `api/state.py` line 24: if it imports `InvariantViolation` from `core/diagnostics`, update to `from niri_state.api.types import InvariantViolation`

5. `core/bootstrap.py` line 31: if it imports `with_invariant_violations` from `core/diagnostics`, that's fine — `with_invariant_violations` stays in `core/diagnostics`. But ensure `core/diagnostics` still has `InvariantViolation` available (via its own import from `api/types`).

6. Re-export from `__init__.py` if desired: add `from niri_state.api.types import InvariantViolation` and add `"InvariantViolation"` to `__all__`.

**Verify**: `devenv shell -- pytest -x && devenv shell -- ruff check .`

---

### Step 8: Add architecture test for api importing core data types

**Issue**: The architecture tests don't catch api modules importing core data types that leak into the public API.

**File**: `tests/unit/test_architecture.py`

**Change**: Update the `TestArchitecture` class. The existing tests check `adapters -> core` and `observability -> api/core`. Add a more nuanced check: `api/errors.py` should not import from `niri_state.core.*`:

```python
    def test_api_errors_should_not_import_from_core(self) -> None:
        """api/errors.py should not import data types from core (they leak into public API)."""
        errors_file = Path("src/niri_state/api/errors.py")
        if not errors_file.exists():
            return

        imports = get_imports(errors_file)
        core_imports = {i for i in imports if i.startswith("niri_state.core")}
        assert not core_imports, f"api/errors.py imports from core: {core_imports}"
```

**Note**: This test will fail if Step 7 hasn't been completed yet. Implement Step 7 first.

**Verify**: `devenv shell -- pytest tests/unit/test_architecture.py -x`

---

### Step 9: Fix subscribe() initial changeset semantics

**Issue**: S3 (Low). `subscribe()` yields the initial snapshot with `health_changeset` (only HEALTH + DIAGNOSTICS domains), but for a new subscriber everything is new. This is misleading.

**File**: `src/niri_state/api/state.py`

**Current code** (lines 92-99):
```python
    async def subscribe(self) -> AsyncIterator[PublishedState]:
        if self._snapshot is not None:
            yield PublishedState(
                snapshot=self._snapshot,
                changes=health_changeset(revision=self._snapshot.revision),
            )
        async for published in self._broadcaster.subscribe():
            yield published
```

**Change**: Use `bootstrap_changeset` instead of `health_changeset` for the initial yield, since all domains are "new" for the subscriber:

```python
    async def subscribe(self) -> AsyncIterator[PublishedState]:
        if self._snapshot is not None:
            yield PublishedState(
                snapshot=self._snapshot,
                changes=bootstrap_changeset(revision=self._snapshot.revision),
            )
        async for published in self._broadcaster.subscribe():
            yield published
```

`bootstrap_changeset` is already imported (line 11 of the imports). It includes ALL domains, which is semantically correct for a first-time subscriber.

**Verify**: `devenv shell -- pytest -x`

---

## Phase 4: Type Safety Improvements

### Step 10: Fix Reducer typedef to be properly typed

**Issue**: R1 (Low). The `Reducer` typedef uses `object` for the event parameter, losing type information.

**File**: `src/niri_state/core/reducers.py`

This is a challenging fix because Python's type system doesn't easily support a heterogeneous dispatch registry with per-key typing. The pragmatic improvement is to use `Any` instead of `object` (which is slightly more honest about intent) and document the contract:

**Current** (line 40):
```python
Reducer = Callable[[EngineState, object], frozenset[ChangedDomain]]
```

**Change** to:
```python
# Each reducer function accepts a specific event subtype, but the registry
# stores them uniformly. Type safety is enforced by the @register decorator
# pairing each function with its corresponding event type at registration time.
Reducer = Callable[[EngineState, Any], frozenset[ChangedDomain]]
```

Add `Any` to the typing imports at line 5 if not already there (it is: `from typing import Any, cast`).

**Verify**: `devenv shell -- ruff check . && devenv shell -- pytest -x`

---

### Step 11: Fix dict[int, object] type annotation in reduce_workspace_activated

**Issue**: R2 (Low). The `updated` dict is typed as `dict[int, object]` instead of the correct `dict[int, Workspace]`.

**File**: `src/niri_state/core/reducers.py`

**Current** (line 206):
```python
    updated: dict[int, object] = {}
```

**Change**: Import `Workspace` and use the correct type. Add `Workspace` to the imports from `niri_state.adapters.protocol`:

Check if `Workspace` is already imported — look at the imports at the top of the file. It isn't currently imported. Add it:

```python
from niri_state.adapters.protocol import (
    ...
    Workspace,
    ...
)
```

Wait — actually the `model_copy` return type is already correctly typed by Pydantic (it returns `Self`), so the issue is just the annotation. The simpler fix is:

```python
    updated: dict[int, object] = {}
```
to:
```python
    updated: dict[int, Workspace] = {}
```

But we need `Workspace` imported. However, the reducers file doesn't import protocol model types — only event types. Adding `Workspace` import just for this annotation might not be worth it. An alternative:

```python
    updated = dict[int, type(workspace)]()
```

No, that's worse. The cleanest approach: just import `Workspace` from the adapters.

Add to the imports block:
```python
from niri_state.adapters.protocol import (
    ConfigLoadedEvent,
    EventValue,
    ...
    WorkspaceUrgencyChangedEvent,
)
```

Actually, `Workspace` is not an event type. Add a separate import or add it to the existing one. Looking at the current import (lines 7-25), it only imports event types. Add `Workspace` to that import list.

After adding the import, change line 206:
```python
    updated: dict[int, Workspace] = {}
```

And update the `engine.workspaces.update(updated)` call — `engine.workspaces` is `dict[int, Workspace]`, so this should now type-check cleanly.

**Verify**: `devenv shell -- ruff check . && devenv shell -- pytest tests/unit/test_reducers.py -x`

---

## Phase 5: Resilience Improvements

### Step 12: Add terminal health detection to wait_until

**Issue**: W1 (Low-Medium). When health transitions to CLOSED or FAILED during `wait_until`, the function `continue`s silently instead of raising an error. The eventual error message is misleading.

**File**: `src/niri_state/api/waiters.py`

**Change**: Add terminal health detection in the wait loop. After the `_health_allows_wait` check, check for terminal states:

```python
async def _wait() -> Snapshot:
    async for snapshot in _subscription_iter(state):
        if snapshot.health in {HealthState.CLOSED, HealthState.FAILED}:
            raise StateLifecycleError(
                f"state transitioned to {snapshot.health.value} while waiting for predicate",
                current_state=snapshot.health,
                operation="wait_until",
            )
        if not _health_allows_wait(snapshot=snapshot, config=config):
            continue
        if predicate(snapshot):
            return snapshot
    raise WaitTimeoutError(
        "state subscription closed before predicate matched",
        timeout=timeout or 0.0,
        operation="wait_until",
    )
```

Add the import:
```python
from niri_state.api.errors import StateLifecycleError, WaitTimeoutError
```

(Update the existing `from niri_state.api.errors import WaitTimeoutError` line.)

**Test**: Add to `tests/unit/test_waiters.py`:

```python
@pytest.mark.asyncio
async def test_wait_until_raises_on_closed_health() -> None:
    class _ClosingState:
        @property
        def snapshot(self) -> Snapshot:
            return Snapshot(
                revision=1,
                timestamp=0.0,
                health=HealthState.LIVE,
                outputs={"HDMI-A-1": make_output()},
                workspaces={1: make_workspace(id=1)},
                windows={},
                focused_workspace_id=1,
                focused_window_id=None,
                keyboard_layouts=make_keyboard_layouts(),
                overview=make_overview(),
                diagnostics=Diagnostics(),
                compatibility=Compatibility(),
            )

        async def subscribe(self) -> AsyncIterator[PublishedState]:
            yield PublishedState(
                snapshot=Snapshot(
                    revision=2,
                    timestamp=1.0,
                    health=HealthState.CLOSED,
                    outputs={},
                    workspaces={},
                    windows={},
                    focused_workspace_id=None,
                    focused_window_id=None,
                    keyboard_layouts=make_keyboard_layouts(),
                    overview=make_overview(),
                    diagnostics=Diagnostics(),
                    compatibility=Compatibility(),
                ),
                changes=empty_changeset(2),
            )

    from niri_state.api.errors import StateLifecycleError

    with pytest.raises(StateLifecycleError, match="CLOSED"):
        await wait_until(
            _ClosingState(),
            lambda s: False,  # never matches
            config=NiriStateConfig(),
            timeout=1.0,
        )
```

**Verify**: `devenv shell -- pytest tests/unit/test_waiters.py -x`

---

### Step 13: Fix strict_config to respect explicit overrides

**Issue**: CF1 (Low). `strict_config(unknown_event_policy=IGNORE)` silently overwrites IGNORE with FAIL.

**File**: `src/niri_state/api/config.py`

**Current code** (lines 53-65):
```python
def strict_config(**overrides: object) -> NiriStateConfig:
    base = NiriStateConfig(**overrides)
    pypc_update = cast(Mapping[str, Any], {"backpressure_mode": BackpressureMode.FAIL_FAST})
    state_update = cast(
        Mapping[str, Any],
        {
            "pypc": base.pypc.model_copy(update=pypc_update),
            "unknown_event_policy": UnknownEventPolicy.FAIL,
            "invariant_failure_policy": InvariantFailurePolicy.FAIL,
            "subscriber_overflow_policy": SubscriberOverflowPolicy.FAIL_FAST,
        },
    )
    return base.model_copy(update=state_update)
```

**Change**: Build the strict defaults first, then apply user overrides on top:

```python
def strict_config(**overrides: object) -> NiriStateConfig:
    strict_defaults: dict[str, object] = {
        "unknown_event_policy": UnknownEventPolicy.FAIL,
        "invariant_failure_policy": InvariantFailurePolicy.FAIL,
        "subscriber_overflow_policy": SubscriberOverflowPolicy.FAIL_FAST,
    }
    # User overrides take precedence over strict defaults
    merged = {**strict_defaults, **overrides}
    base = NiriStateConfig(**merged)
    pypc_update = cast(Mapping[str, Any], {"backpressure_mode": BackpressureMode.FAIL_FAST})
    pypc_merged = cast(Mapping[str, Any], {"pypc": base.pypc.model_copy(update=pypc_update)})
    return base.model_copy(update=pypc_merged)
```

**Test**: Add to `tests/unit/test_config.py`:

```python
def test_strict_config_respects_explicit_overrides() -> None:
    config = strict_config(unknown_event_policy=UnknownEventPolicy.IGNORE)
    assert config.unknown_event_policy is UnknownEventPolicy.IGNORE
    # Other strict defaults should still apply
    assert config.invariant_failure_policy is InvariantFailurePolicy.FAIL
    assert config.subscriber_overflow_policy is SubscriberOverflowPolicy.FAIL_FAST
```

**Verify**: `devenv shell -- pytest tests/unit/test_config.py -x`

---

### Step 14: Cache selector result in wait_for_selector

**Issue**: W2 (Very low). `wait_for_selector` calls the selector twice — once inside the predicate and once on the matched snapshot.

**File**: `src/niri_state/api/waiters.py`

**Current code** (lines 83-103):
```python
async def wait_for_selector[T](
    state: WaitableState,
    selector: Callable[[Snapshot], T],
    *,
    predicate: Callable[[T], bool] | None = None,
    config: NiriStateConfig,
    timeout: float | None = None,
) -> T:
    def _wrapped(snapshot: Snapshot) -> bool:
        value = selector(snapshot)
        if predicate is None:
            return bool(value)
        return predicate(value)

    snapshot = await wait_until(
        state,
        _wrapped,
        config=config,
        timeout=timeout,
    )
    return selector(snapshot)
```

**Change**: Cache the last computed value in a mutable container:

```python
async def wait_for_selector[T](
    state: WaitableState,
    selector: Callable[[Snapshot], T],
    *,
    predicate: Callable[[T], bool] | None = None,
    config: NiriStateConfig,
    timeout: float | None = None,
) -> T:
    last_value: list[T] = []

    def _wrapped(snapshot: Snapshot) -> bool:
        value = selector(snapshot)
        last_value.clear()
        last_value.append(value)
        if predicate is None:
            return bool(value)
        return predicate(value)

    await wait_until(
        state,
        _wrapped,
        config=config,
        timeout=timeout,
    )
    return last_value[0]
```

**Verify**: `devenv shell -- pytest tests/unit/test_waiters.py -x`

---

### Step 15: Wrap old_bundle.close() in refresh() with try/except

**Issue**: S4 (Low). In `refresh()`, `old_bundle.close()` is called after the new mutation loop starts. If it raises, the caller gets an error but the state is functional.

**File**: `src/niri_state/api/state.py`

**Current** (lines 361-362):
```python
            self._start_mutation_loop()
            await old_bundle.close()
```

**Change**: Swallow the error with logging since the new connection is already working:

```python
            self._start_mutation_loop()
            try:
                await old_bundle.close()
            except Exception:
                _LOGGER.warning("failed to close old bundle during refresh; new connection is active", exc_info=True)
```

**Verify**: `devenv shell -- pytest tests/integration/test_refresh.py -x`

---

## Phase 6: Performance Improvements

### Step 16: Parallelize bootstrap queries with asyncio.gather

**Issue**: B1 (Low/Medium). 8 sequential IPC round-trips during bootstrap.

**File**: `src/niri_state/core/bootstrap.py`

**Current code** (lines 92-100):
```python
async def build_initial_engine_state(client: NiriClient) -> EngineState:
    outputs = await query_outputs(client)
    workspaces = await query_workspaces(client)
    windows = await query_windows(client)
    focused_output = await query_focused_output(client)
    focused_window = await query_focused_window(client)
    keyboard_layouts = await query_keyboard_layouts(client)
    overview = await query_overview(client)
    version = await query_version(client)
```

**Change**: Use `asyncio.gather()`:

```python
async def build_initial_engine_state(client: NiriClient) -> EngineState:
    (
        outputs,
        workspaces,
        windows,
        focused_output,
        focused_window,
        keyboard_layouts,
        overview,
        version,
    ) = await asyncio.gather(
        query_outputs(client),
        query_workspaces(client),
        query_windows(client),
        query_focused_output(client),
        query_focused_window(client),
        query_keyboard_layouts(client),
        query_overview(client),
        query_version(client),
    )
```

The rest of the function remains the same. `asyncio` is already imported.

**Important note**: This works because `NiriClient.request()` creates a new socket connection per request — there's no shared connection state between concurrent calls.

**Test**: Existing bootstrap tests should still pass:

**Verify**: `devenv shell -- pytest tests/integration/test_bootstrap.py tests/replay/test_replay_traces.py -x`

---

## Phase 7: Test Coverage Expansion

### Step 17: Fix DummyState.subscribe to yield PublishedState

**Issue**: `DummyState.subscribe()` in `tests/conftest.py` yields `object` not `PublishedState`, making it incompatible with `WaitableState` protocol.

**File**: `tests/conftest.py`

**Current code** (lines 53-55):
```python
    async def subscribe(self) -> AsyncIterator[object]:
        if False:
            yield None
```

**Change**:
```python
    async def subscribe(self) -> AsyncIterator[PublishedState]:
        if False:
            yield  # type: ignore[misc]  # pragma: no cover
```

Add import at the top:
```python
from niri_state.core.broadcaster import PublishedState
```

**Verify**: `devenv shell -- pytest -x`

---

### Step 18: Add unit tests for all 14 reducers

**Issue**: Only 4 of 14 reducers have unit tests. Add parametrized tests for the remaining 10.

**File**: `tests/unit/test_reducers.py`

Add these test functions. Each tests the reducer in isolation by constructing an `EngineState`, applying the reducer, and asserting the expected outcome.

```python
import pytest

from niri_state.adapters.protocol import UnknownEvent
from niri_state.api.changes import ChangedDomain
from niri_state.api.config import NiriStateConfig, UnknownEventPolicy
from niri_state.api.errors import DesyncError
from niri_state.core.engine_state import EngineState
from niri_state.core.reducers import (
    reduce_event,
    reduce_keyboard_layout_switched,
    reduce_keyboard_layouts_changed,
    reduce_overview_opened_or_closed,
    reduce_window_closed,
    reduce_window_focus_changed,
    reduce_window_focus_timestamp_changed,
    reduce_window_opened_or_changed,
    reduce_window_layouts_changed,
    reduce_window_urgency_changed,
    reduce_windows_changed,
    reduce_workspace_activated,
    reduce_workspace_active_window_changed,
    reduce_workspace_urgency_changed,
    reduce_workspaces_changed,
)
from tests.factories.events import (
    make_config_loaded_event,
    make_keyboard_layout_switched_event,
    make_keyboard_layouts_changed_event,
    make_overview_opened_or_closed_event,
    make_window_closed_event,
    make_window_focus_changed_event,
    make_window_focus_timestamp_changed_event,
    make_window_layouts_changed_event,
    make_window_opened_or_changed_event,
    make_window_urgency_changed_event,
    make_windows_changed_event,
    make_workspace_activated_event,
    make_workspace_active_window_changed_event,
    make_workspace_urgency_changed_event,
    make_workspaces_changed_event,
)
from tests.factories.protocol import (
    make_keyboard_layouts,
    make_overview,
    make_timestamp,
    make_window,
    make_window_layout,
    make_workspace,
)


def _engine_with_defaults() -> EngineState:
    """Create an engine with minimal valid state."""
    engine = EngineState.empty()
    engine.keyboard_layouts = make_keyboard_layouts()
    engine.overview = make_overview()
    engine.workspaces = {1: make_workspace(id=1, output="HDMI-A-1")}
    engine.windows = {100: make_window(id=100, workspace_id=1)}
    return engine


def test_reduce_window_opened_or_changed_adds_new_window() -> None:
    engine = _engine_with_defaults()
    event = make_window_opened_or_changed_event(window=make_window(id=200, workspace_id=1))
    domains = reduce_window_opened_or_changed(engine, event)

    assert 200 in engine.windows
    assert ChangedDomain.WINDOWS in domains


def test_reduce_window_opened_or_changed_updates_focus_when_focused() -> None:
    engine = _engine_with_defaults()
    event = make_window_opened_or_changed_event(
        window=make_window(id=200, workspace_id=1, is_focused=True),
    )
    domains = reduce_window_opened_or_changed(engine, event)

    assert engine.focused_window_id == 200
    assert ChangedDomain.FOCUS in domains


def test_reduce_window_closed_removes_window() -> None:
    engine = _engine_with_defaults()
    event = make_window_closed_event(id=100)
    domains = reduce_window_closed(engine, event)

    assert 100 not in engine.windows
    assert ChangedDomain.WINDOWS in domains


def test_reduce_window_closed_clears_focus_if_focused() -> None:
    engine = _engine_with_defaults()
    engine.focused_window_id = 100
    event = make_window_closed_event(id=100)
    domains = reduce_window_closed(engine, event)

    assert engine.focused_window_id is None
    assert ChangedDomain.FOCUS in domains


def test_reduce_window_focus_changed_sets_focus() -> None:
    engine = _engine_with_defaults()
    event = make_window_focus_changed_event(id=100)
    domains = reduce_window_focus_changed(engine, event)

    assert engine.focused_window_id == 100
    assert domains == frozenset({ChangedDomain.FOCUS})


def test_reduce_window_focus_timestamp_changed_updates_timestamp() -> None:
    engine = _engine_with_defaults()
    new_ts = make_timestamp(secs=42)
    event = make_window_focus_timestamp_changed_event(id=100, focus_timestamp=new_ts)
    domains = reduce_window_focus_timestamp_changed(engine, event)

    assert engine.windows[100].focus_timestamp.secs == 42
    assert ChangedDomain.FOCUS in domains


def test_reduce_window_focus_timestamp_changed_raises_on_unknown_window() -> None:
    engine = _engine_with_defaults()
    event = make_window_focus_timestamp_changed_event(id=999)
    with pytest.raises(DesyncError):
        reduce_window_focus_timestamp_changed(engine, event)


def test_reduce_workspaces_changed_replaces_all() -> None:
    engine = _engine_with_defaults()
    new_ws = [make_workspace(id=5, output="DP-1"), make_workspace(id=6, output="DP-1")]
    event = make_workspaces_changed_event(workspaces=new_ws)
    domains = reduce_workspaces_changed(engine, event)

    assert set(engine.workspaces) == {5, 6}
    assert ChangedDomain.WORKSPACES in domains


def test_reduce_workspace_active_window_changed_updates_workspace() -> None:
    engine = _engine_with_defaults()
    event = make_workspace_active_window_changed_event(workspace_id=1, active_window_id=100)
    domains = reduce_workspace_active_window_changed(engine, event)

    assert engine.workspaces[1].active_window_id == 100
    assert ChangedDomain.WORKSPACES in domains


def test_reduce_workspace_active_window_changed_raises_on_unknown() -> None:
    engine = _engine_with_defaults()
    event = make_workspace_active_window_changed_event(workspace_id=999, active_window_id=100)
    with pytest.raises(DesyncError):
        reduce_workspace_active_window_changed(engine, event)


def test_reduce_workspace_urgency_changed_sets_urgent() -> None:
    engine = _engine_with_defaults()
    event = make_workspace_urgency_changed_event(id=1, urgent=True)
    domains = reduce_workspace_urgency_changed(engine, event)

    assert engine.workspaces[1].is_urgent is True
    assert ChangedDomain.WORKSPACES in domains


def test_reduce_workspace_urgency_changed_raises_on_unknown() -> None:
    engine = _engine_with_defaults()
    event = make_workspace_urgency_changed_event(id=999, urgent=True)
    with pytest.raises(DesyncError):
        reduce_workspace_urgency_changed(engine, event)


def test_reduce_keyboard_layouts_changed_replaces_layouts() -> None:
    engine = _engine_with_defaults()
    new_layouts = make_keyboard_layouts(names=["FR", "ES"], current_idx=1)
    event = make_keyboard_layouts_changed_event(keyboard_layouts=new_layouts)
    domains = reduce_keyboard_layouts_changed(engine, event)

    assert engine.keyboard_layouts is not None
    assert engine.keyboard_layouts.names == ["FR", "ES"]
    assert domains == frozenset({ChangedDomain.KEYBOARD})


def test_reduce_keyboard_layout_switched_updates_index() -> None:
    engine = _engine_with_defaults()
    event = make_keyboard_layout_switched_event(idx=1)
    domains = reduce_keyboard_layout_switched(engine, event)

    assert engine.keyboard_layouts is not None
    assert engine.keyboard_layouts.current_idx == 1
    assert domains == frozenset({ChangedDomain.KEYBOARD})


def test_reduce_keyboard_layout_switched_raises_when_uninitialized() -> None:
    engine = EngineState.empty()
    engine.overview = make_overview()
    # keyboard_layouts is None
    event = make_keyboard_layout_switched_event(idx=0)
    with pytest.raises(DesyncError):
        reduce_keyboard_layout_switched(engine, event)


def test_reduce_overview_opened_or_closed_updates_state() -> None:
    engine = _engine_with_defaults()
    event = make_overview_opened_or_closed_event(is_open=True)
    domains = reduce_overview_opened_or_closed(engine, event)

    assert engine.overview is not None
    assert engine.overview.is_open is True
    assert domains == frozenset({ChangedDomain.OVERVIEW})


def test_reduce_overview_raises_when_uninitialized() -> None:
    engine = EngineState.empty()
    engine.keyboard_layouts = make_keyboard_layouts()
    # overview is None
    event = make_overview_opened_or_closed_event(is_open=True)
    with pytest.raises(DesyncError):
        reduce_overview_opened_or_closed(engine, event)


def test_reduce_config_loaded_is_noop() -> None:
    engine = _engine_with_defaults()
    from niri_state.core.reducers import reduce_config_loaded

    event = make_config_loaded_event()
    domains = reduce_config_loaded(engine, event)
    assert domains == frozenset()


def test_reduce_event_handles_unknown_with_stale_policy() -> None:
    engine = _engine_with_defaults()
    engine.health = HealthState.LIVE
    event = UnknownEvent(variant_name="FutureEvent", raw_payload={})
    config = NiriStateConfig(unknown_event_policy=UnknownEventPolicy.STALE)

    result = reduce_event(engine, event, config=config, revision=1)

    assert result.marked_desync is True
    assert engine.diagnostics.desynced is True


def test_reduce_event_ignores_unknown_with_ignore_policy() -> None:
    engine = _engine_with_defaults()
    event = UnknownEvent(variant_name="FutureEvent", raw_payload={})
    config = NiriStateConfig(unknown_event_policy=UnknownEventPolicy.IGNORE)

    result = reduce_event(engine, event, config=config, revision=1)

    assert result.applied is False
```

Add this import at top of file if not already present:
```python
from niri_state.api.health import HealthState
```

**Verify**: `devenv shell -- pytest tests/unit/test_reducers.py -x -v`

---

### Step 19: Add broadcaster publish tests

Already covered in Step 2's test additions. The `test_publish_delivers_to_all_subscribers` and `test_publish_overflow_still_delivers_to_healthy_subscribers` tests provide basic broadcaster publish coverage.

Add one more test for the DROP_OLDEST behavior:

**File**: `tests/unit/test_broadcaster.py`

```python
@pytest.mark.asyncio
async def test_publish_drop_oldest_on_full_queue() -> None:
    config = NiriStateConfig(
        subscriber_queue_size=1,
        subscriber_overflow_policy=SubscriberOverflowPolicy.DROP_OLDEST,
    )
    broadcaster = Broadcaster(config)
    sub = broadcaster.subscribe()

    # Fill the queue
    await broadcaster.publish(_make_published(revision=1))
    # This should drop revision=1 and insert revision=2
    await broadcaster.publish(_make_published(revision=2))
    await broadcaster.close()

    items = [x async for x in sub]
    assert len(items) == 1
    assert items[0].snapshot.revision == 2
```

Add to imports: `from niri_state.api.config import SubscriberOverflowPolicy`

**Verify**: `devenv shell -- pytest tests/unit/test_broadcaster.py -x`

---

### Step 20: Add invariant coverage tests

**Issue**: Only 2 of 7 invariant checks have tests.

**File**: `tests/unit/test_invariants.py`

Add these tests:

```python
def test_collects_missing_focused_window() -> None:
    snapshot = Snapshot(
        revision=1,
        timestamp=0.0,
        health=HealthState.LIVE,
        outputs={},
        workspaces={},
        windows={},
        focused_workspace_id=None,
        focused_window_id=999,  # doesn't exist
        keyboard_layouts=make_keyboard_layouts(),
        overview=make_overview(),
        diagnostics=Diagnostics(),
        compatibility=Compatibility(),
    )

    violations = collect_invariant_violations(snapshot)
    assert any(v.code == "focused_window_missing" for v in violations)


def test_collects_missing_focused_workspace() -> None:
    snapshot = Snapshot(
        revision=1,
        timestamp=0.0,
        health=HealthState.LIVE,
        outputs={},
        workspaces={},
        windows={},
        focused_workspace_id=999,  # doesn't exist
        focused_window_id=None,
        keyboard_layouts=make_keyboard_layouts(),
        overview=make_overview(),
        diagnostics=Diagnostics(),
        compatibility=Compatibility(),
    )

    violations = collect_invariant_violations(snapshot)
    assert any(v.code == "focused_workspace_missing" for v in violations)


def test_collects_missing_output_for_workspace() -> None:
    snapshot = Snapshot(
        revision=1,
        timestamp=0.0,
        health=HealthState.LIVE,
        outputs={},
        workspaces={1: make_workspace(id=1, output="MISSING-OUTPUT")},
        windows={},
        focused_workspace_id=None,
        focused_window_id=None,
        keyboard_layouts=make_keyboard_layouts(),
        overview=make_overview(),
        diagnostics=Diagnostics(),
        compatibility=Compatibility(),
    )

    violations = collect_invariant_violations(snapshot)
    assert any(v.code == "workspace_output_missing" for v in violations)


def test_no_violations_for_valid_snapshot() -> None:
    snapshot = Snapshot(
        revision=1,
        timestamp=0.0,
        health=HealthState.LIVE,
        outputs={"HDMI-A-1": make_output()},
        workspaces={1: make_workspace(id=1, output="HDMI-A-1")},
        windows={100: make_window(id=100, workspace_id=1)},
        focused_workspace_id=1,
        focused_window_id=100,
        keyboard_layouts=make_keyboard_layouts(),
        overview=make_overview(),
        diagnostics=Diagnostics(),
        compatibility=Compatibility(),
    )

    violations = collect_invariant_violations(snapshot)
    assert violations == ()
```

**Note**: Check the actual violation code strings by reading `core/invariants.py`. The codes used above (`focused_window_missing`, `focused_workspace_missing`, `workspace_output_missing`) should match what `collect_invariant_violations` produces. Adjust if needed.

**Verify**: `devenv shell -- pytest tests/unit/test_invariants.py -x -v`

---

### Step 21: Add NiriState lifecycle error path tests

**File**: `tests/integration/test_close_lifecycle.py` (or a new `tests/integration/test_lifecycle_errors.py`)

```python
import pytest

from niri_state.api.errors import StateLifecycleError
from niri_state.api.state import NiriState
from tests.factories.bundle import FakeBundle


@pytest.mark.asyncio
async def test_connect_when_already_started_raises() -> None:
    bundle = FakeBundle()
    state = NiriState(bundle_factory=lambda: bundle)
    await state.connect()

    with pytest.raises(StateLifecycleError, match="already started"):
        await state.connect()

    await state.close()


@pytest.mark.asyncio
async def test_connect_when_already_closed_raises() -> None:
    bundle = FakeBundle()
    state = NiriState(bundle_factory=lambda: bundle)
    await state.connect()
    await state.close()

    with pytest.raises(StateLifecycleError, match="already closed"):
        await state.connect()


@pytest.mark.asyncio
async def test_refresh_when_not_connected_raises() -> None:
    state = NiriState()

    with pytest.raises(StateLifecycleError, match="not connected"):
        await state.refresh()
```

**Note**: If Step 5 (bundle_factory DI) hasn't been done yet, use the monkey-patching pattern instead.

**Verify**: `devenv shell -- pytest tests/integration/ -x`

---

### Step 22: Add mutation loop error path tests

**File**: `tests/integration/test_runtime_mutation_loop.py`

```python
import asyncio

import pytest

from niri_state.api.health import HealthState
from niri_state.api.state import NiriState
from tests.factories.bundle import FakeBundle
from tests.factories.events import make_window_urgency_changed_event


@pytest.mark.asyncio
async def test_mutation_loop_marks_stale_on_desync() -> None:
    """When a reducer raises DesyncError, the mutation loop should mark state as STALE."""
    # Send urgency change for a window ID that doesn't exist (id=999) — this triggers DesyncError
    event = make_window_urgency_changed_event(id=999, urgent=True)
    bundle = FakeBundle(events=(event,), event_delay_s=0.01)
    state = NiriState(bundle_factory=lambda: bundle)
    await state.connect()

    # Wait for the event to be processed
    for _ in range(20):
        if state.snapshot.health is HealthState.STALE:
            break
        await asyncio.sleep(0.02)

    assert state.snapshot.health is HealthState.STALE
    assert state.snapshot.diagnostics.desynced is True
    await state.close()
```

**Verify**: `devenv shell -- pytest tests/integration/test_runtime_mutation_loop.py -x`

---

### Step 23: Add close-during-subscription test

**File**: `tests/integration/test_close_lifecycle.py`

```python
@pytest.mark.asyncio
async def test_subscriber_receives_closed_on_close(fake_runtime_bundle) -> None:
    state = NiriState(bundle_factory=lambda: fake_runtime_bundle)
    await state.connect()

    received = []
    sub = state.subscribe()

    # Get the initial snapshot
    initial = await sub.__anext__()
    received.append(initial)

    # Close the state — this should deliver a CLOSED snapshot then terminate
    await state.close()

    async for item in sub:
        received.append(item)

    assert any(p.snapshot.health is HealthState.CLOSED for p in received)
```

**Verify**: `devenv shell -- pytest tests/integration/test_close_lifecycle.py -x`

---

### Step 24: Add edge case tests

**File**: `tests/unit/test_snapshot.py` or a new `tests/unit/test_edge_cases.py`

```python
def test_snapshot_empty_state() -> None:
    """Snapshot with no outputs, workspaces, or windows is valid."""
    snapshot = Snapshot(
        revision=1,
        timestamp=0.0,
        health=HealthState.LIVE,
        outputs={},
        workspaces={},
        windows={},
        focused_workspace_id=None,
        focused_window_id=None,
        keyboard_layouts=make_keyboard_layouts(),
        overview=make_overview(),
        diagnostics=Diagnostics(),
        compatibility=Compatibility(),
    )

    assert snapshot.focused_output_name is None
    assert dict(snapshot.workspaces_by_output) == {}
    assert dict(snapshot.windows_by_workspace) == {}
    assert dict(snapshot.active_workspace_by_output) == {}


def test_snapshot_multiple_outputs() -> None:
    """Snapshot with multiple outputs indexes correctly."""
    snapshot = Snapshot(
        revision=1,
        timestamp=0.0,
        health=HealthState.LIVE,
        outputs={
            "HDMI-A-1": make_output(name="HDMI-A-1"),
            "DP-1": make_output(name="DP-1"),
        },
        workspaces={
            1: make_workspace(id=1, idx=1, output="HDMI-A-1", is_active=True, is_focused=True),
            2: make_workspace(id=2, idx=1, output="DP-1", is_active=True, is_focused=False),
        },
        windows={
            100: make_window(id=100, workspace_id=1),
            200: make_window(id=200, workspace_id=2),
        },
        focused_workspace_id=1,
        focused_window_id=100,
        keyboard_layouts=make_keyboard_layouts(),
        overview=make_overview(),
        diagnostics=Diagnostics(),
        compatibility=Compatibility(),
    )

    assert snapshot.workspaces_by_output["HDMI-A-1"] == (1,)
    assert snapshot.workspaces_by_output["DP-1"] == (2,)
    assert snapshot.windows_by_workspace[1] == (100,)
    assert snapshot.windows_by_workspace[2] == (200,)
    assert snapshot.focused_output_name == "HDMI-A-1"


def test_snapshot_keyboard_empty_names() -> None:
    """Keyboard with empty names list doesn't crash derived properties."""
    snapshot = Snapshot(
        revision=1,
        timestamp=0.0,
        health=HealthState.LIVE,
        outputs={},
        workspaces={},
        windows={},
        focused_workspace_id=None,
        focused_window_id=None,
        keyboard_layouts=make_keyboard_layouts(names=[], current_idx=0),
        overview=make_overview(),
        diagnostics=Diagnostics(),
        compatibility=Compatibility(),
    )

    assert snapshot.keyboard_current_name is None
```

**Verify**: `devenv shell -- pytest tests/unit/test_snapshot.py -x`

---

## Final Verification

After completing all steps, run the full quality gate:

```bash
devenv shell -- ruff check .
devenv shell -- ruff format --check .
devenv shell -- ty check .
devenv shell -- pytest --cov=niri_state --cov-report=term-missing
```

Verify:
1. All tests pass
2. No lint errors
3. No type errors
4. Coverage has improved from the baseline

---

## Summary of Changes by File

| File | Steps | Changes |
|------|-------|---------|
| `core/reconcile.py` | 1 | Deduplicate stale note |
| `core/broadcaster.py` | 2 | Isolate per-subscriber errors in publish |
| `api/state.py` | 3, 4, 5, 9, 15 | try/finally close, context manager, DI, changeset fix, old_bundle safety |
| `api/config.py` | 13 | Fix strict_config override semantics |
| `api/waiters.py` | 12, 14 | Terminal health detection, cache selector |
| `api/types.py` (new) | 7 | InvariantViolation model |
| `api/errors.py` | 7 | Import from api/types instead of core |
| `core/diagnostics.py` | 7 | Import InvariantViolation from api/types |
| `core/reducers.py` | 10, 11 | Fix Reducer typedef, Workspace type annotation |
| `core/bootstrap.py` | 16 | asyncio.gather for parallel queries |
| `__init__.py` | 6, 7 | Re-export PublishedState, InvariantViolation |
| `api/__init__.py` | 6 | Re-export PublishedState |
| `tests/conftest.py` | 17 | Fix DummyState.subscribe return type |
| `tests/unit/test_reconcile.py` | 1 | Duplicate note test |
| `tests/unit/test_broadcaster.py` | 2, 19 | Publish delivery and overflow tests |
| `tests/unit/test_reducers.py` | 18 | Full reducer coverage |
| `tests/unit/test_invariants.py` | 20 | Invariant violation coverage |
| `tests/unit/test_waiters.py` | 12 | Terminal health test |
| `tests/unit/test_config.py` | 13 | strict_config override test |
| `tests/unit/test_architecture.py` | 8 | api/errors core import check |
| `tests/unit/test_snapshot.py` | 24 | Edge case tests |
| `tests/integration/test_close_lifecycle.py` | 4, 21, 23 | Context manager, lifecycle errors, subscription close |
| `tests/integration/test_runtime_mutation_loop.py` | 22 | Desync error path |
| `tests/integration/*.py` | 5 | Migrate to bundle_factory DI |
