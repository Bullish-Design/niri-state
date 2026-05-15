# Event Batching — Detailed Concept & Implementation Plan

**Project**: `12-event-batching`
**Date**: 2026-05-15
**Branch**: `v2-rewrite` (build on top of completed v2 refactor)
**Source**: STATUS_SUMMARY.md § "Deferred Improvements" — Event batching

---

## 1. Problem Statement

When niri sends rapid event bursts (e.g. workspace switch triggers `WorkspaceActivated` + `WindowFocusChanged` + `WindowsChanged` within microseconds), the current mutation loop creates **one snapshot per event**. Each snapshot involves:

1. `reconcile(engine)` — O(workspaces + windows)
2. `engine.freeze()` — full-state copy into immutable `Snapshot` with `MappingProxyType` wrapping
3. `collect_invariant_violations()` — O(workspaces + windows + outputs)
4. `broadcaster.publish()` — enqueue to N subscriber queues

For a burst of 10 events, that's 10 reconciliations, 10 snapshot allocations, 10 invariant checks, and 10 publishes — when the subscriber only cares about the **final state** after the burst settles.

### Concrete Waste Scenarios

| User Action | Typical Event Burst | Events | Intermediate Snapshots Wasted |
|---|---|---|---|
| Switch workspace | `WorkspaceActivated` × 2 + `WindowFocusChanged` + `WindowsChanged` | 4 | 3 |
| Close window | `WindowsChanged` + `WindowFocusChanged` (+ possible `WorkspaceActivated`) | 2–3 | 1–2 |
| Open app | `WindowOpenedOrChanged` + `WindowsChanged` + `WindowFocusChanged` | 3 | 2 |
| Keyboard layout switch | `KeyboardLayoutsChanged` + `KeyboardLayoutSwitched` | 2 | 1 |
| Multi-monitor rearrange | N × `OutputsChanged` + workspace moves | N+M | N+M−1 |

### Goals

1. **Reduce snapshot allocations** during event bursts
2. **Reduce reconciliation/invariant passes** during bursts
3. **Preserve correctness** — subscribers must never see stale or inconsistent state
4. **Preserve event ordering** — reducers must run in arrival order
5. **Minimal latency impact** — isolated events should publish with near-zero added delay
6. **Backward compatible** — default config behaves identically to current per-event behavior

---

## 2. Design: Drain-Based Micro-Batching

### Core Idea

Instead of processing one event then publishing, **drain all immediately-available events** from the async iterator before creating a snapshot. This is a **zero-timeout drain** — no timer, no delay. It batches events that have already arrived but haven't been processed yet.

This works because:
- `async for event in bundle.events` yields one event, then we check if more are ready
- In a burst, niri-pypc's internal `asyncio.Queue` will have multiple events buffered
- Between bursts, the queue is empty and we publish immediately after the single event

### Why Not Time-Based Batching?

A timer-based approach (e.g. "collect events for 10ms then publish") adds **unconditional latency** to every event, even isolated ones. The drain approach adds zero latency — it only batches events that are already queued.

Time-based batching could be added later as an optional enhancement on top of drain-based batching, but the drain approach alone captures the vast majority of burst scenarios because niri sends correlated events within the same compositor frame (sub-millisecond).

---

## 3. Architecture

### 3.1 New: `EventBatchPolicy` Enum

```python
# api/config.py

class EventBatchPolicy(StrEnum):
    NONE = "none"        # Current behavior: one event → one snapshot (default)
    DRAIN = "drain"      # Drain all ready events before publishing
```

Default is `NONE` to preserve backward compatibility.

### 3.2 New Config Fields

```python
# api/config.py — added to NiriStateConfig

event_batch_policy: EventBatchPolicy = EventBatchPolicy.NONE
event_batch_max_size: PositiveInt = 64
```

- `event_batch_policy`: Controls batching behavior
- `event_batch_max_size`: Safety cap on batch size to prevent unbounded accumulation (e.g. during a flood of events). Once the cap is reached, the batch is flushed immediately.

### 3.3 Modified: `_mutation_loop()` in `api/state.py`

The mutation loop is restructured into two strategies based on policy:

```
NONE policy (current):
  for each event:
    reduce → reconcile → freeze → check invariants → publish

DRAIN policy:
  receive first event (blocking await)
  drain remaining ready events (non-blocking)
  for each event in batch:
    reduce (mutate engine, accumulate domains)
    if desync: flush immediately
  reconcile once
  freeze once → single snapshot
  check invariants once
  publish once with merged domains
```

### 3.4 Changed Domain Merging

When batching, domains from all events in the batch are unioned:

```python
# Event 1: WindowsChanged → {WINDOWS, FOCUS}
# Event 2: WorkspaceActivated → {WORKSPACES, FOCUS}
# Event 3: KeyboardLayoutSwitched → {KEYBOARD}
# Merged: {WINDOWS, FOCUS, WORKSPACES, KEYBOARD}
```

The `ChangeSet` published to subscribers reflects the **union of all changed domains** in the batch.

### 3.5 New: `ChangeCause.EVENT_BATCH`

```python
# api/changes.py

class ChangeCause(StrEnum):
    BOOTSTRAP = "bootstrap"
    EVENT = "event"
    EVENT_BATCH = "event_batch"  # NEW
    REFRESH = "refresh"
    RESYNC = "resync"
    CLOSE = "close"
    HEALTH = "health"
```

With a corresponding builder:

```python
def event_batch_changeset(
    *,
    revision: int,
    domains: frozenset[ChangedDomain],
    batch_size: int,
) -> ChangeSet:
    return ChangeSet(
        revision=revision,
        cause=ChangeCause.EVENT_BATCH,
        domains=domains,
    )
```

This lets subscribers distinguish between single-event updates and batched updates. Subscribers that don't care can treat `EVENT_BATCH` the same as `EVENT`.

### 3.6 Revision Semantics

With batching, the revision increment changes:

- **Current**: revision increments by 1 per event
- **With DRAIN**: revision increments by 1 per *published snapshot* (i.e. per batch)

This is consistent — revision tracks published snapshots, not raw events. The `diagnostics.event_count` still tracks every event processed.

### 3.7 Diagnostics Additions

```python
# core/diagnostics.py — added to Diagnostics model

last_batch_size: int = 1              # Size of most recent batch
total_batches_published: int = 0      # Number of batched publishes
total_events_batched: int = 0         # Events processed in batches (batch_size > 1)
```

These provide observability into batching behavior without affecting existing diagnostics.

---

## 4. Detailed Implementation

### 4.1 Event Draining Helper

New private method on `NiriState`:

```python
async def _drain_ready_events(
    self,
    first_event: EventValue,
    max_size: int,
) -> list[EventValue]:
    """Collect the first event plus any immediately-available events.

    Returns a list of 1..max_size events. The first event is always
    included. Additional events are collected non-blockingly from
    the bundle's event stream.
    """
    batch = [first_event]
    if max_size <= 1:
        return batch

    # Access the underlying queue from niri-pypc's event stream
    # to check for ready events without awaiting
    queue = self._bundle.event_queue  # Need to verify niri-pypc API

    while len(batch) < max_size:
        try:
            event = queue.get_nowait()
            batch.append(event)
        except asyncio.QueueEmpty:
            break

    return batch
```

**Important**: This requires access to niri-pypc's underlying event queue for non-blocking reads. We need to verify the niri-pypc API. If `bundle.events` is a pure `AsyncIterator` without queue access, we have two options:

1. **Preferred**: Add a `drain_ready()` method to niri-pypc that returns all immediately-available events
2. **Fallback**: Use `asyncio.wait_for(anext(event_iter), timeout=0)` — but this is fragile with async iterators

### 4.2 Restructured Mutation Loop

```python
async def _mutation_loop(self) -> None:
    assert self._bundle is not None
    assert self._engine is not None

    if self._config.event_batch_policy is EventBatchPolicy.NONE:
        await self._mutation_loop_unbatched()
    else:
        await self._mutation_loop_batched()
```

**Unbatched loop** — identical to current code (no behavior change).

**Batched loop**:

```python
async def _mutation_loop_batched(self) -> None:
    async for first_event in self._bundle.events:
        if self._closed:
            return

        try:
            batch = await self._drain_ready_events(
                first_event,
                max_size=self._config.event_batch_max_size,
            )
            await self._process_event_batch(batch)

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

### 4.3 Batch Processing

```python
async def _process_event_batch(self, batch: list[EventValue]) -> None:
    accumulated_domains: frozenset[ChangedDomain] = frozenset()
    any_applied = False

    for event in batch:
        result = reduce_event(
            self._engine,
            event,
            config=self._config,
            revision=self._revision,
        )

        if not result.applied:
            continue

        any_applied = True
        accumulated_domains = accumulated_domains | result.domains

        if result.marked_desync:
            # Desync is urgent — flush what we have immediately
            await self._transition_health(HealthState.STALE)
            # Don't break — remaining events in batch should still reduce
            # (they may contain recovery information)

    if not any_applied:
        return

    # Single reconciliation pass for the entire batch
    reconcile(self._engine)

    self._revision += 1
    snapshot = self._engine.freeze(revision=self._revision)

    violations = collect_invariant_violations(snapshot)
    if violations:
        snapshot = self._handle_invariant_violations(snapshot, violations)

    previous = self._snapshot
    self._snapshot = snapshot

    if previous is not None and previous.health != snapshot.health:
        accumulated_domains = accumulated_domains | frozenset(
            {ChangedDomain.HEALTH, ChangedDomain.DIAGNOSTICS}
        )

    # Choose changeset type based on batch size
    batch_size = len(batch)
    if batch_size == 1:
        changes = event_changeset(
            revision=snapshot.revision,
            domains=accumulated_domains,
        )
    else:
        changes = event_batch_changeset(
            revision=snapshot.revision,
            domains=accumulated_domains,
            batch_size=batch_size,
        )

    await self._broadcaster.publish(
        PublishedState(snapshot=snapshot, changes=changes)
    )

    # Update diagnostics
    self._engine.diagnostics = self._engine.diagnostics.model_copy(
        update={
            "last_batch_size": batch_size,
            "total_batches_published": self._engine.diagnostics.total_batches_published + 1,
            "total_events_batched": (
                self._engine.diagnostics.total_events_batched + batch_size
                if batch_size > 1 else
                self._engine.diagnostics.total_events_batched
            ),
        }
    )
```

### 4.4 Key Design Decision: Reconcile Once vs. Per-Event

The plan calls for **reconciling once after the entire batch**, not after each event. This is safe because:

1. **Reconciliation is idempotent** — running it once at the end produces the same engine state as running it after every event. Each reconcile pass only reads and corrects engine state; it doesn't depend on snapshot history.

2. **Reducers don't depend on reconciled state** — reducers read/write `engine.windows`, `engine.workspaces`, etc. directly. They don't read derived fields that reconciliation fixes (like `focused_workspace_id` inferred from window focus). The only potential issue is if a reducer reads `engine.focused_workspace_id` after a previous event in the batch changed the focused window — but reconciliation only *infers* focus from window data, and the reducer would get the stale focus ID. However, this is the same stale ID it would get if the events arrived in separate loop iterations with reconciliation in between, because reconciliation runs *after* the reducer, not before it.

3. **The bootstrap already does this** — `run_bootstrap()` in `core/bootstrap.py` processes buffered events with `reconcile()` after each one, but this is conservative. The events are applied to the same engine sequentially. Skipping intermediate reconciliations is equivalent.

**Caveat**: If a future reducer is added that reads reconciled state (e.g. reads `engine.focused_workspace_id` expecting it to reflect the previous event's focus change), this assumption breaks. The plan includes a comment in the code documenting this invariant.

**Alternative (conservative)**: Reconcile after each event but only freeze/publish once. This adds O(batch_size) reconciliation cost but is strictly safer:

```python
for event in batch:
    result = reduce_event(...)
    if result.applied:
        reconcile(self._engine)  # per-event
        accumulated_domains |= result.domains

# Single freeze + publish
snapshot = self._engine.freeze(...)
```

**Recommendation**: Start with the conservative approach (reconcile per-event, freeze/publish once). This captures the main performance win (snapshot allocation + invariant checks + publish fan-out) while avoiding any correctness risk. Optimize to single-reconcile later if profiling shows it matters.

---

## 5. niri-pypc Integration

### 5.1 Required API

The drain approach requires non-blocking access to ready events. Current niri-pypc exposes `bundle.events` as an `AsyncIterator`. We need one of:

**Option A — Expose the internal queue** (simplest):
```python
# In niri-pypc's NiriConnectionBundle
@property
def event_queue(self) -> asyncio.Queue[EventValue]:
    return self._event_queue
```

**Option B — Add a `drain_ready()` method** (cleaner API):
```python
# In niri-pypc's NiriConnectionBundle
def drain_ready_events(self, max_count: int = -1) -> list[EventValue]:
    """Return all immediately-available events without blocking."""
    events = []
    while max_count < 0 or len(events) < max_count:
        try:
            events.append(self._event_queue.get_nowait())
        except asyncio.QueueEmpty:
            break
    return events
```

**Option C — Pure asyncio approach** (no niri-pypc changes):
```python
# Use asyncio.Queue wrapping in niri-state
# Buffer events into our own queue, then drain from there
```

**Recommendation**: Option B is cleanest. If niri-pypc changes are undesirable, Option C works but adds a buffering layer.

### 5.2 Fallback: Internal Queue Wrapper

If we can't modify niri-pypc, we wrap the event stream in our own drainable queue:

```python
class DrainableEventStream:
    """Wraps an AsyncIterator into a drainable queue."""

    def __init__(self, events: AsyncIterator[EventValue], maxsize: int = 0) -> None:
        self._queue: asyncio.Queue[EventValue | None] = asyncio.Queue(maxsize=maxsize)
        self._pump_task: asyncio.Task[None] | None = None
        self._events = events

    async def start(self) -> None:
        self._pump_task = asyncio.create_task(self._pump())

    async def _pump(self) -> None:
        async for event in self._events:
            await self._queue.put(event)
        await self._queue.put(None)  # sentinel

    async def get(self) -> EventValue | None:
        """Blocking get — returns None when stream ends."""
        return await self._queue.get()

    def drain_ready(self, max_count: int) -> list[EventValue]:
        """Non-blocking drain of all ready events."""
        events: list[EventValue] = []
        while len(events) < max_count:
            try:
                event = self._queue.get_nowait()
                if event is None:
                    break
                events.append(event)
            except asyncio.QueueEmpty:
                break
        return events

    async def close(self) -> None:
        if self._pump_task:
            self._pump_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._pump_task
```

This adds one extra hop (event → internal queue → drain) but the overhead is negligible compared to snapshot creation.

---

## 6. File Changes Summary

| File | Change | Scope |
|---|---|---|
| `api/config.py` | Add `EventBatchPolicy` enum, `event_batch_policy` and `event_batch_max_size` fields | Small |
| `api/changes.py` | Add `ChangeCause.EVENT_BATCH`, add `event_batch_changeset()` builder | Small |
| `api/state.py` | Split mutation loop, add `_drain_ready_events()`, add `_process_event_batch()` | Medium |
| `core/diagnostics.py` | Add `last_batch_size`, `total_batches_published`, `total_events_batched` fields | Small |
| `core/broadcaster.py` | No changes needed | None |
| `core/reconcile.py` | No changes needed | None |
| `core/engine_state.py` | No changes needed | None |
| `api/snapshot.py` | No changes needed (diagnostics changes flow through automatically) | None |
| `__init__.py` | Re-export `EventBatchPolicy` if needed | Trivial |

### New Files

| File | Purpose |
|---|---|
| `core/drain.py` | `DrainableEventStream` class (if niri-pypc doesn't add `drain_ready()`) |
| `tests/unit/test_drain.py` | Unit tests for drainable stream |
| `tests/unit/test_event_batching.py` | Unit tests for batch processing logic |
| `tests/integration/test_event_batching.py` | Integration tests with mock event bursts |

---

## 7. Implementation Steps

### Phase 1: Foundation (no behavior change)

1. **Add `EventBatchPolicy` enum and config fields** to `api/config.py`
2. **Add `ChangeCause.EVENT_BATCH`** and builder to `api/changes.py`
3. **Add diagnostics fields** to `core/diagnostics.py`
4. **Re-export** new types from `__init__.py` and `api/__init__.py`
5. **Split `_mutation_loop()`** into `_mutation_loop_unbatched()` (identical to current) and a dispatcher. All existing tests should still pass.

### Phase 2: Drain Infrastructure

6. **Implement `DrainableEventStream`** in `core/drain.py` (or verify niri-pypc API and use directly)
7. **Write unit tests for drain** — test non-blocking drain, max_count cap, empty queue, sentinel handling
8. **Wire `DrainableEventStream`** into `NiriState._connect()` when batch policy is `DRAIN`

### Phase 3: Batched Mutation Loop

9. **Implement `_mutation_loop_batched()`** using conservative approach (reconcile per-event, freeze/publish once per batch)
10. **Implement `_process_event_batch()`** with domain accumulation and changeset selection
11. **Update diagnostics** after each batch publish

### Phase 4: Testing

12. **Unit test: batch domain merging** — verify domains are unioned correctly across events
13. **Unit test: batch of 1** — verify single-event batch produces `EVENT` cause, not `EVENT_BATCH`
14. **Unit test: max_size cap** — verify batch doesn't exceed configured max
15. **Unit test: desync mid-batch** — verify health transition happens but remaining events still reduce
16. **Integration test: burst scenario** — mock 5 rapid events, verify single snapshot published
17. **Integration test: isolated events** — verify no added latency when events arrive with gaps
18. **Integration test: subscriber receives batched changeset** — verify subscriber sees merged domains
19. **Integration test: mixed batch/unbatch** — verify switching policy at config level works

### Phase 5: Documentation & Polish

20. **Docstrings** on new public API surface
21. **Update `strict_config()`** if batching should be off in strict mode (likely yes — strict wants per-event fidelity)
22. **Run full test suite** with `DRAIN` policy as default to verify no regressions

---

## 8. Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| niri-pypc doesn't expose queue for non-blocking reads | Blocks drain approach | `DrainableEventStream` wrapper (§5.2) |
| Reconcile-once-per-batch breaks a future reducer | Incorrect state in snapshot | Start conservative (reconcile per-event); document the invariant |
| Batch hides individual event changesets from subscribers | Subscriber can't react to specific events | Union of domains is strictly more information; subscribers already handle coarse domains. `EVENT_BATCH` cause distinguishes from `EVENT`. |
| `event_batch_max_size` set too high | Long stall before publish during flood | Default 64 is already the subscriber queue size; any higher and we'd overflow queues anyway |
| Revision gap confuses subscribers | Subscriber expects monotonic +1 revisions | Revision still increments by 1 per publish — just fewer publishes. Document this. |
| Diagnostics snapshot embedded in batched snapshot is stale | `last_batch_size` in snapshot N reflects batch N-1 | Update diagnostics *before* freeze, or accept one-behind. Minor issue. |

---

## 9. Performance Expectations

### Best Case (5-event burst)

| Metric | Before (per-event) | After (drain batch) | Savings |
|---|---|---|---|
| `reconcile()` calls | 5 | 5 (conservative) or 1 (optimized) | 0–80% |
| `freeze()` calls | 5 | 1 | 80% |
| `collect_invariant_violations()` calls | 5 | 1 | 80% |
| `broadcaster.publish()` calls | 5 | 1 | 80% |
| Snapshot allocations | 5 | 1 | 80% |
| `MappingProxyType` wraps | 15 (3 dicts × 5) | 3 (3 dicts × 1) | 80% |
| Subscriber queue usage | 5 items per burst | 1 item per burst | 80% |

### Isolated Events (no burst)

| Metric | Before | After | Overhead |
|---|---|---|---|
| Latency | ~0 | ~0 (drain is non-blocking check) | Negligible |
| CPU | baseline | baseline + one `QueueEmpty` exception | Negligible |

### Worst Case (sustained flood, max_size=64)

Events are processed in chunks of 64, each chunk producing one snapshot. This bounds memory usage and ensures subscribers aren't starved of updates during floods.

---

## 10. Future Extensions (Out of Scope)

These are **not** part of this implementation but are enabled by it:

1. **Time-based batching**: Add `event_batch_timeout_ms` that holds the batch open for N ms after the first event, catching events that arrive slightly later (e.g. niri sends events across two compositor frames). Requires `asyncio.wait_for()` on drain.

2. **Adaptive batching**: Dynamically adjust batch strategy based on event rate — drain-only when event rate is low, time-window when rate is high.

3. **Batch-aware selectors**: Selectors that can diff between pre-batch and post-batch snapshots efficiently, avoiding full recomputation.

4. **Event coalescing**: Collapse redundant events within a batch (e.g. two `WindowsChanged` events → keep only the last). This requires reducer-level awareness and is significantly more complex.

5. **Batch metadata in `ChangeSet`**: Add `batch_size`, `first_revision`, `event_types` fields to `ChangeSet` for richer subscriber introspection.

---

## 11. Decision Log

| Decision | Choice | Rationale |
|---|---|---|
| Batching strategy | Drain (zero-timeout) | No added latency; captures compositor-frame bursts naturally |
| Default policy | `NONE` | Backward compatible; opt-in |
| Reconciliation approach | Conservative (per-event) initially | Correctness over performance; optimize later |
| Revision semantics | Per-publish (not per-event) | Consistent with existing meaning; revision = snapshot version |
| New `ChangeCause` | `EVENT_BATCH` | Subscribers can distinguish; no breaking change |
| Diagnostics | Three new counters | Observable without overhead; Pydantic defaults to 0 |
| Max batch size default | 64 | Matches subscriber queue size; natural bound |
