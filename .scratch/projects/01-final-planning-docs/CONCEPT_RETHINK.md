# CONCEPT_RETHINK

Greenfield redesign exploration for `niri-state` with no backward-compatibility constraints.

## Table of Contents

1. Rethink Goals and Design Posture
2. Product Split: Core vs Runtime
3. Event-Sourced-First Architecture
4. Typed Lifecycle State Machine
5. Freshness as a Type-Level Contract
6. Protocol Ingress Normalization Boundary
7. Incremental Selector and Index Engine
8. Declarative Conditions and Subscription Runtime
9. Checkpointing and Fast Recovery
10. Unknown Event Evolution Strategy
11. Test Architecture as a Product Feature
12. Public API Direction (Greenfield)
13. End-to-End Example Flow
14. Tradeoff Summary Matrix
15. Recommended Phased Path to a v2
16. Open Questions to Resolve Early

## 1. Rethink Goals and Design Posture

This document assumes complete freedom to redesign `niri-state` as a new product line.

Primary goals:
1. Maximize correctness clarity.
2. Minimize accidental complexity at call sites.
3. Make recovery and schema evolution first-class.
4. Keep deterministic replay as a hard invariant.

Design posture:
1. Prefer explicit contracts over convenience magic.
2. Prefer separation of responsibilities over “all-in-one” objects.
3. Prefer architecture that makes failures diagnosable and recoverable.

Example framing:
- Old posture: “maintain a coherent latest snapshot and stream updates.”
- New posture: “maintain an authoritative event log and derive coherent snapshots as views.”

Pros:
- Cleaner long-term evolution.
- Better operational debugging.

Cons:
- Higher upfront design cost.
- More concepts for beginners.

Implications:
- Docs and examples must be significantly better than typical library docs.

Opportunities:
- Position the library as a state platform, not a helper wrapper.

## 2. Product Split: Core vs Runtime

Recommendation:
1. `niri-state-core` (pure domain engine).
2. `niri-state-runtime` (async tasks, sockets via `niri-pypc`, buffering, policy execution).

`niri-state-core` responsibilities:
1. Domain events.
2. Reducers.
3. Invariants.
4. Snapshot materialization.
5. Replay engine.

`niri-state-runtime` responsibilities:
1. Bootstrap orchestration.
2. Event ingestion.
3. Stream health and recovery.
4. Subscription/wait APIs.

Example package usage:
```python
# Pure replay test
from niri_state_core import Engine, ReplayTrace

engine = Engine.new()
final = engine.replay(ReplayTrace.load("trace.json"))
assert final.health == "live"
```

```python
# Live runtime usage
from niri_state_runtime import Runtime

rt = await Runtime.connect()
snap = rt.snapshot()
```

Pros:
- Testability improves drastically.
- Runtime complexity no longer contaminates domain core.

Cons:
- Two-package release and versioning management.

Implications:
- Need strong cross-package compatibility policy.

Opportunities:
- External teams can embed `core` in custom runtimes.

## 3. Event-Sourced-First Architecture

Recommendation:
- Keep append-only internal domain event log as source of truth.
- Materialize snapshots from event stream + checkpoints.

Internal flow:
1. Ingress receives protocol event/reply.
2. Normalize to domain event.
3. Append to log with monotonic sequence.
4. Reduce into state projection(s).
5. Publish projection deltas.

Example domain event:
```python
DomainEvent(
    seq=10231,
    kind="window.focus.changed",
    payload={"window_id": 42},
    source="event_stream",
    observed_at_ns=...
)
```

Pros:
- Reproducibility and auditability.
- Natural foundation for replay and debugging.

Cons:
- Additional storage/retention concerns.

Implications:
- Need clear retention/compaction policy.

Opportunities:
- Time-travel debugging and “what changed?” tooling.

## 4. Typed Lifecycle State Machine

Recommendation:
- Replace loose health flags with explicit state machine and legal transitions.

Proposed states:
1. `cold`
2. `bootstrapping`
3. `live`
4. `degraded`
5. `recovering`
6. `failed`
7. `closed`

Example transition rule:
- `live -> degraded` on unknown impactful event.
- `degraded -> recovering` if auto-recovery enabled.
- `recovering -> live` only after successful bootstrap+replay.

Pros:
- Eliminates ambiguous intermediate behavior.
- Easier operational introspection.

Cons:
- More code around transition guards.

Implications:
- All APIs should define behavior per lifecycle state.

Opportunities:
- Export structured lifecycle telemetry for observability.

## 5. Freshness as a Type-Level Contract

Recommendation:
- Represent freshness quality in types to prevent misuse.

Example concept types:
```python
class Live[T]: ...
class RefreshBacked[T]: ...
class QueryOnly[T]: ...
```

API example:
```python
def focused_window(snapshot) -> Live[WindowRef | None]: ...
def outputs(snapshot) -> RefreshBacked[tuple[OutputState, ...]]: ...
```

Pros:
- Consumers cannot accidentally treat stale-capable domains as live-certainty.

Cons:
- More advanced typing patterns can feel heavy.

Implications:
- Need excellent helper APIs (`.value`, `.freshness`, coercion rules).

Opportunities:
- Best-in-class correctness ergonomics for downstream automation.

## 6. Protocol Ingress Normalization Boundary

Recommendation:
- `niri-pypc` models terminate at ingress adapter.
- Internal reducers only consume stable internal domain events.

Example mapping:
- `WindowFocusChangedEvent(id=42)` -> `window.focus.changed(window_id=42)`
- `WindowFocusChangedEvent(id=None)` -> `window.focus.cleared()`

Pros:
- Internal engine insulated from protocol churn.

Cons:
- Mapping layer must be rigorously maintained.

Implications:
- Schema/version adapters become critical infrastructure.

Opportunities:
- Support multiple protocol versions with the same core.

## 7. Incremental Selector and Index Engine

Recommendation:
- Maintain secondary indexes during reduction so selectors are cheap.

Index examples:
1. `windows_by_workspace: dict[WorkspaceId, tuple[WindowId, ...]]`
2. `workspace_by_output: dict[OutputName, tuple[WorkspaceId, ...]]`
3. `focused_refs` compact struct.

Pros:
- Predictable selector performance.
- Reduces repeated scans on high-frequency reads.

Cons:
- More reducer complexity and invariant surface.

Implications:
- Index correctness tests become mandatory.

Opportunities:
- Enable richer query APIs without performance cliffs.

## 8. Declarative Conditions and Subscription Runtime

Recommendation:
- Replace ad-hoc wait loops with declarative condition plans.

Concept:
1. User defines a condition object.
2. Runtime compiles to selector + predicate plan.
3. Plan runs on each publication.
4. Multi-subscriber sharing avoids duplicated evaluation work.

Example:
```python
cond = Condition.window_exists(window_id=42) & Condition.health_is("live")
await runtime.wait(cond, timeout=5.0)
```

Pros:
- Better composability and clearer semantics.
- Centralized timeout/cancellation/health policy behavior.

Cons:
- Requires DSL/API design discipline.

Implications:
- Need explicit truth-table semantics for composed conditions.

Opportunities:
- Add “explain why condition is unmet” diagnostics.

## 9. Checkpointing and Fast Recovery

Recommendation:
- Add periodic compacted checkpoints plus event offset markers.

Recovery flow:
1. Load latest checkpoint.
2. Reapply events since checkpoint offset.
3. Validate invariants.
4. Publish recovered snapshot.

Pros:
- Faster startup and resync.
- Lower bootstrap pressure on compositor.

Cons:
- Checkpoint storage lifecycle management needed.

Implications:
- Need checkpoint format versioning and migration strategy.

Opportunities:
- Optional durable local cache for near-instant warm starts.

## 10. Unknown Event Evolution Strategy

Recommendation:
- Treat unknown events as schema evolution input, not binary failure only.

Policy ladder:
1. `strict`: degrade/fail immediately.
2. `compat`: attempt adapter mapping.
3. `observe`: record and continue with bounded risk labeling.

Example:
- Unknown variant arrives with payload shape matching known semantic category.
- Adapter maps it to `workspace.meta.changed` with `compat_note`.

Pros:
- Better forward-compatibility posture.

Cons:
- Adapter logic can become error-prone if unchecked.

Implications:
- Compatibility behavior must be visibly surfaced in diagnostics.

Opportunities:
- Build a compatibility marketplace of adapters.

## 11. Test Architecture as a Product Feature

Recommendation:
- Treat replay and property tests as first-class product surface.

Testing layers:
1. Golden trace suites.
2. Reducer property tests (determinism, invariants).
3. Chaos tests for runtime failure/recovery.
4. Protocol adapter differential tests across version pins.

Example property:
- For a valid event stream, reducing twice from same initial checkpoint yields equal snapshot and indexes.

Pros:
- Regressions are found earlier with higher confidence.

Cons:
- Larger maintenance burden for test assets.

Implications:
- CI cost increases; must parallelize intelligently.

Opportunities:
- Public “conformance harness” for plugin/integration authors.

## 12. Public API Direction (Greenfield)

Recommendation:
- Expose a small set of strongly-typed entry points.

Proposed surface:
1. `Runtime.connect(config) -> RuntimeHandle`
2. `RuntimeHandle.snapshot() -> SnapshotView`
3. `RuntimeHandle.query(Query[T]) -> T`
4. `RuntimeHandle.subscribe(SubscriptionSpec) -> AsyncIterator[Event]`
5. `RuntimeHandle.wait(Condition, timeout) -> WaitResult`
6. `RuntimeHandle.recover(policy_override=None)`

Example query object:
```python
q = Query.windows_on_output("DP-1").focused_first().include_urgent(True)
windows = runtime.query(q)
```

Pros:
- API becomes more discoverable and composable.

Cons:
- Query abstraction adds an indirection layer.

Implications:
- Must avoid building an overengineered mini-language.

Opportunities:
- Future server/client remote query protocol reuse.

## 13. End-to-End Example Flow

Scenario:
1. Runtime boots, queries initial state, starts stream.
2. Ingress maps protocol responses/events into domain events.
3. Domain log appends events with sequence IDs.
4. Reducers update base state and indexes.
5. Snapshot publication emits:
- revision,
- lifecycle state,
- change cause/domains,
- derived diagnostics.
6. Condition plans evaluate; matching waiters resolve.
7. Unknown impactful event arrives:
- lifecycle `live -> degraded`,
- diagnostics emit compatibility detail,
- auto-recovery policy triggers `degraded -> recovering -> live` on success.

Pros:
- Operational behavior is explicit and explainable.

Cons:
- More moving parts than a minimal snapshot-only design.

Implications:
- Requires strong runtime introspection APIs.

Opportunities:
- Build UI tooling that visualizes lifecycle, event log, and selector outputs.

## 14. Tradeoff Summary Matrix

1. Core/runtime split
- Upside: modularity, testability.
- Downside: version coordination complexity.

2. Event-sourced core
- Upside: replayability, auditability.
- Downside: retention/compaction overhead.

3. Typed freshness
- Upside: compile-time misuse prevention.
- Downside: higher typing complexity.

4. Ingress normalization
- Upside: protocol decoupling.
- Downside: adapter maintenance burden.

5. Incremental indexes
- Upside: selector performance.
- Downside: more invariant surface.

6. Declarative conditions
- Upside: better wait/watch ergonomics.
- Downside: DSL/API complexity risk.

## 15. Recommended Phased Path to a v2

Phase 1: Extract pure core.
1. Introduce internal domain events and replayable reducer engine.
2. Add invariant framework and deterministic trace runner.

Phase 2: Runtime rewrite on top of core.
1. Add ingress adapter and lifecycle FSM.
2. Add condition engine and subscription runtime.

Phase 3: Performance and recovery.
1. Add incremental indexes.
2. Add checkpointing and fast recovery.

Phase 4: Compatibility hardening.
1. Add schema evolution adapters.
2. Build cross-version differential tests.

Phase 5: Public stabilization.
1. Freeze v2 API contracts.
2. Publish conformance fixtures and operator docs.

## 16. Open Questions to Resolve Early

1. Should event log be memory-only by default or durable by default?
2. What durability guarantees should checkpointing provide?
3. How strict should typed freshness be in Python ergonomics?
4. Which unknown-event modes are safe as defaults?
5. Do we need pluggable storage backends in v2 or defer?
6. What observability surface is mandatory (metrics, traces, debug endpoints)?
7. How much query abstraction is enough before it becomes a burden?
