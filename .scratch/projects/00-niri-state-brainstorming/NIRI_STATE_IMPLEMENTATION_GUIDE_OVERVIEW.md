I reviewed the attached [spec](sandbox:/mnt/data/NIRI_STATE_SPEC.md), [concept](sandbox:/mnt/data/NIRI_STATE_CONCEPT.md), and the attached [niri-pypc export](sandbox:/mnt/data/niri-pypc.zip).

The core takeaway is that `niri-state` is not a protocol client and not a policy layer. It is a deterministic state engine that sits strictly downstream of `niri-pypc`: `niri-pypc` owns typed requests/replies/events, decoding, sockets, and bundle lifecycle; `niri-state` owns bootstrap, normalization, reducers, immutable snapshots, selectors, waits/watchers, health, desync detection, and resync. It must model observed truth only, preserve atomic snapshots, and make correctness boundaries explicit rather than guessing after drift.  

From direct inspection of the attached `niri-pypc` zip, the implementation reality the intern must code against is:

* `niri_pypc` is version `0.1.0`, with generated protocol types pinned to upstream `niri-ipc 25.11`.
* `NiriClient` is **one connection per request**, not a long-lived command socket.
* `NiriEventStream` is the long-lived stream, backed by a bounded `asyncio.Queue`; in `DROP_OLDEST` it silently drops oldest events and logs, while in `FAIL_FAST` it terminates with a protocol error.
* `NiriConnectionBundle` is just `client + events`.
* `client.request()` returns an unwrapped **typed `Response` variant**, not a naked payload.
* unknown event variants decode to `UnknownEvent` sentinels.
* the current event surface includes the window/workspace/focus/keyboard/overview events the spec expects, plus `ScreenshotCaptured`, `WindowFocusTimestampChanged`, `WindowLayoutsChanged`, and `ConfigLoaded`.

That matches the spec’s requirement that `niri-state` adapt to the actual `niri-pypc` implementation, not older design assumptions. 

The most important design rules to preserve are:

1. Only event-backed domains get “live” guarantees.
2. Outputs are refresh-backed, not fully live.
3. Layers are query-only/unsupported in v1.
4. Focused and active are not the same thing; active workspaces are tracked per output, not as one singular global active workspace.
5. `connect()` must not return until the first coherent live snapshot exists.
6. Strict mode must force upstream fail-fast backpressure.    

## Implementation guide for the intern

### Step 1 — Create the repository skeleton exactly around the spec

Implement the package/module layout from the spec first, before writing logic. Keep the dependency direction strict: store → sync/reducers/selectors/models/errors/config → `niri-pypc`, and never the reverse. The public boundary is `NiriState`, public models, public selectors, and public errors. 

Create:

* `src/niri_state/__init__.py`, `_version.py`
* `config.py`, `errors.py`
* `models/{common,health,entities,snapshot,change_set}.py`
* `reducers/{common,bootstrap,root,windows,workspaces,focus,keyboard,overview,invariants}.py`
* `selectors/{outputs,workspaces,windows,focus,aggregates}.py`
* `sync/{bootstrap,resync,policies}.py`
* `store/{live_state,broadcaster,waiters}.py`
* `tests/...` matching the test tree in the spec. 

Validate:

* package imports cleanly
* `from niri_state import NiriState, NiriStateConfig, selectors` works
* no module imports any downstream app code
* no reducer or selector imports transport code directly

### Step 2 — Lock in project/runtime constraints

Set Python to 3.13, `asyncio` only, Pydantic v2 models, and PEP 8 naming. All public models must be frozen. This should be enforced immediately so later work does not accumulate mutable state leaks. 

Implement:

* `FrozenModel` in `models/common.py`
* public identifier aliases:

  * `OutputName = str`
  * `WorkspaceId = int`
  * `WindowId = int`
  * `Revision = int`

Validate:

* mutation of any public model raises
* mypy/ty-style type checks on public function signatures pass
* public collections that should be immutable are tuples, not lists

### Step 3 — Implement `config.py` before anything stateful

Create the exact enum/config surface from the spec: `CorrectnessMode`, `ResyncPolicy`, `StoreOverflowMode`, `UnknownEventPolicy`, `InvariantFailurePolicy`, `WaitHealthPolicy`, and `NiriStateConfig`. This config drives almost every later decision. 

Critical implementation detail: because `niri_pypc.NiriConfig` is a frozen dataclass and currently defaults to `BackpressureMode.DROP_OLDEST`, `NiriState.connect()` must normalize it in strict mode by building a replacement config with `FAIL_FAST`. Do not mutate in place. 

Validate:

* strict mode with upstream drop-oldest either copies config to fail-fast or raises `StateConfigError`
* best-effort mode preserves drop-oldest if user asked for it
* effective upstream backpressure mode gets recorded into diagnostics later

### Step 4 — Implement the error taxonomy with context fields

Create the full `NiriStateError` hierarchy exactly as specified, including revision/health/event/selector context and retryable flags. Preserve chaining from `niri-pypc` exceptions. `SelectorWaitError` must also be catchable as `TimeoutError`. 

Also write the mapping helpers now:

* bootstrap-time `ConfigError`, `TransportError`, `DecodeError`, `RemoteError`, `NiriTimeoutError` → mostly `BootstrapError`
* live stream failures → stale/desync/resync paths, not just raw passthrough
* invalid state transitions → `StateLifecycleError`

Validate:

* all custom exceptions stringify cleanly
* wrapped causes are preserved with `raise ... from exc`
* timeout tests can catch `SelectorWaitError` as `TimeoutError`

### Step 5 — Build the state model exactly once, and make it authoritative

Implement the public models next:

* `CompatibilityStatus`, `CompatibilityInfo`
* `StoreHealth`
* `SnapshotDiagnostics`
* `SnapshotIndexes`
* `OutputState`
* `WorkspaceState`
* `WindowState`
* `KeyboardLayoutsState`
* `OverviewState`
* `NiriSnapshot`
* `ChangeCause`, `ChangeDomain`, `ChangeSet`   

Key rules to enforce in model design:

* raw `niri_pypc.types` models stay embedded inside entity models
* outputs are keyed by name, workspaces/windows by protocol ids
* `active_workspace_ids_by_output` exists; do not add singular global `active_workspace_id`
* `last_good_revision` semantics must follow the spec exactly
* `revision` increments only on publication, not on internal draft objects  

Validate:

* constructors reject extra fields
* snapshot equality is stable
* order indexes are explicit and immutable
* focused/active semantics are represented separately

### Step 6 — Create a reusable test fixture layer for protocol models

Before reducers, create helper builders in `tests/conftest.py` that produce real `niri_pypc.types` models:

* `make_output(...)`
* `make_workspace(...)`
* `make_window(...)`
* `make_keyboard_layouts(...)`
* `make_overview(...)`
* wrapper helpers for `OutputsResponse`, `WorkspacesResponse`, etc.
* event helpers for every event variant

This will keep later tests readable and make reducer coverage dense without being noisy.

Validate:

* every helper returns a real generated Pydantic model
* helpers cover optional/null cases
* helpers support focused/active edge cases across multiple outputs

### Step 7 — Implement bootstrap response normalization

This is the first place where `niri-state` must adapt to `niri-pypc` reality. Because replies arrive as typed response wrappers, write an internal `BootstrapResponses` carrier and a `normalize_bootstrap_responses(...) -> BootstrapPayload` function. It should match concrete response classes and extract payloads explicitly.  

Base the default query plan on the actual request surface in the attached zip:

* `OutputsRequest`
* `WorkspacesRequest`
* `WindowsRequest`
* `FocusedOutputRequest`
* `FocusedWindowRequest`
* `KeyboardLayoutsRequest`
* `OverviewStateRequest`
  Optional:
* `LayersRequest`
* `VersionRequest`

Important normalization notes from the zip:

* `OutputsResponse.payload` is `dict[str, Output]`
* `WorkspacesResponse.payload` is `list[Workspace]`
* `WindowsResponse.payload` is `list[Window]`
* `FocusedOutputResponse.payload` is `Output | None`, so derive `focused_output_name` from `payload.name`
* `FocusedWindowResponse.payload` is `Window | None`, so derive `focused_window_id` from `payload.id`
* unknown reply sentinels during bootstrap should fail bootstrap by default

Validate:

* one unit test per response variant
* missing required response variants raise `BootstrapError`
* optional layers only included when configured
* version metadata is extracted from `niri_pypc.types.generated._metadata` and optional runtime version query

### Step 8 — Implement invariant checking before reducers publish anything

Write `InvariantViolation` and `check_snapshot_invariants(snapshot)`. Implement every invariant in the spec, not just the obvious ones. 

Pay special attention to:

* mapping key ↔ entity id/name agreement
* workspace.output_name existence
* window.workspace_id existence
* output.workspace_ids membership
* focused pointers
* exactly one focused window when `focused_window_id` is set
* focused workspace consistency
* active workspace membership per output
* index completeness/no duplicates

Validate:

* one test per invariant family
* multi-violation cases return all violations, not just first
* stale-on-invariant and fail-on-invariant policy conversion behaves exactly as configured 

### Step 9 — Implement `build_initial_snapshot()`

Now build the base coherent snapshot from normalized bootstrap payload. This reducer is pure and should not know anything about sockets or bundles. It should:

* normalize outputs/workspaces/windows into entity maps
* build explicit indexes
* derive `focused_output_name`, `focused_workspace_id`, `focused_window_id`
* derive `active_workspace_ids_by_output`
* populate keyboard/overview state
* mark outputs as `is_live_config_current=False`
* stamp `bootstrapped=True`, `health=LIVE`, `last_good_revision=revision` only after invariants pass  

Validate:

* bootstrap snapshot from minimal payload
* bootstrap snapshot from multi-output/multi-workspace payload
* focused workspace derived from focused window when possible
* output freshness flag is false
* ordering uses protocol order when available and deterministic fallback otherwise

### Step 10 — Implement domain reducers, one module at a time

Do not start with a giant root reducer. Implement domain reducers first.

#### 10a. `reducers/windows.py`

Handle:

* `WindowOpenedOrChangedEvent`
* `WindowClosedEvent`
* `WindowsChangedEvent`
* `WindowUrgencyChangedEvent`

Likely behavior:

* opened/changed: upsert by id, keep raw model current, sync `workspace_id`
* closed: remove window; clear focused/window pointers and any workspace `active_window_id` referencing it
* windows changed: authoritative replace of window domain
* urgency changed: `raw = raw.model_copy(update={"is_urgent": urgent})`

Validate:

* add/update/remove flow
* replace-all flow
* workspace dangling pointers get cleaned up
* no-op path when an update doesn’t change effective state

#### 10b. `reducers/workspaces.py`

Handle:

* `WorkspaceActivatedEvent`
* `WorkspaceActiveWindowChangedEvent`
* `WorkspaceUrgencyChangedEvent`
* `WorkspacesChangedEvent`

Important rule: do not collapse active vs focused. Updating one workspace on one output must not incorrectly clear activity on other outputs. 

Validate:

* activation on same output updates active workspace set correctly
* activation on another output preserves other outputs’ active workspaces
* focused flag propagation works
* authoritative replace works without breaking focused ids when still valid

#### 10c. `reducers/focus.py`

Handle:

* `WindowFocusChangedEvent`
  Optionally:
* derive focused workspace/output from the focused window’s relationships

Minimal compliant path for the remaining event-surface items from the zip:

* `WindowFocusTimestampChangedEvent`: explicit no-op or raw field update, but document the decision
* `WindowLayoutsChangedEvent`: explicit no-op or raw layout update, but document the decision
* `ScreenshotCapturedEvent`: explicit no-op

Validate:

* focus set, focus clear, focus change between windows
* exactly one focused window invariant holds
* derived focused workspace/output move with focused window when data allows

#### 10d. `reducers/keyboard.py`

Handle:

* `KeyboardLayoutSwitchedEvent`
* `KeyboardLayoutsChangedEvent`

Validate:

* current idx updates
* current name recomputes correctly
* changed event replaces raw domain and derived fields

#### 10e. `reducers/overview.py`

Handle:

* `OverviewOpenedOrClosedEvent`

Validate:

* `None -> True/False`
* preserving raw overview data where appropriate

#### 10f. metadata/config handling

Handle:

* `ConfigLoadedEvent`

This should probably not mutate entity state, but it should produce `ChangeDomain.METADATA` and update diagnostics/summary so consumers can observe successful or failed config loads. The concept explicitly calls out config-load/store diagnostics as part of the state engine’s responsibility. 

Validate:

* config loaded success and failure publish useful metadata
* no entity maps change

### Step 11 — Implement the root reducer and policy conversion

`reducers/root.py` should dispatch by **concrete event model type**, not strings. Required coverage includes the supported live domains, and any known-but-not-stateful current event variants must be explicitly no-op’d. Unknown sentinels must follow policy: stale transition or hard failure. 

Root reducer flow:

1. receive current snapshot + typed event
2. call the appropriate domain reducer
3. if reducer says `applied=False` and diagnostics/health unchanged, do not publish
4. run invariants after non-no-op result
5. convert invariant failures to stale or raise, per policy
6. return a `ReductionResult`

Validate:

* one test per event variant
* unknown event → stale or `DesyncError`
* unsupported known event path is explicit and tested
* domains in `ChangeSet` are deduped and stable-ordered

### Step 12 — Implement broadcaster primitives before the store

Write `store/broadcaster.py` to own per-subscriber queues for:

* `ChangeSet`
* selector results

It must support:

* queue creation per subscriber
* configurable capacity
* `DROP_OLDEST` and `FAIL_FAST`
* clean termination after final publication 

Validate:

* multiple subscribers receive same revision order
* one slow subscriber does not break others
* overflow mode behaves exactly as configured
* fail-fast overflow becomes `WatchOverflowError`

### Step 13 — Implement waiter primitives

Write `store/waiters.py` with:

* `wait_until`
* `wait_for_selector`

Rules:

* evaluate current snapshot first
* then subscribe to change publication
* event-driven only; no polling
* respect `WaitHealthPolicy`
* timeout raises `SelectorWaitError`  

Validate:

* immediate success path
* next-change success path
* timeout path
* cancellation path
* stale handling under `REQUIRE_LIVE` vs `ALLOW_STALE`
* selector predicate omitted means “next distinct value”

### Step 14 — Implement coordinated bootstrap in `sync/bootstrap.py`

This is the hardest part, and it must reflect the real `niri-pypc` bundle behavior. Since `NiriClient` uses one connection per request and `NiriEventStream` is separate, bootstrap must close the race by starting event consumption first and buffering typed event variants in FIFO order while running the query suite.  

Implement `run_bootstrap(bundle, config)`:

1. normalize config and verify strict-mode backpressure
2. verify event stream is ready
3. start a local FIFO bootstrap buffer
4. optionally query runtime version
5. issue initial requests through `bundle.client.request(...)`
6. normalize responses into `BootstrapPayload`
7. build base snapshot with `build_initial_snapshot`
8. replay buffered events through the same `apply_event`
9. stop buffering
10. return `BootstrapArtifacts`

Important:

* local bootstrap buffer overflow is always bootstrap failure
* upstream event queue overflow in fail-fast mode is also bootstrap failure
* do not publish first live snapshot until replay finishes successfully  

Validate:

* race-closing test where events arrive during query execution
* bootstrap buffer overflow failure
* upstream fail-fast overflow failure
* command error failure
* normalization failure
* timeout failure
* strict version mismatch failure

### Step 15 — Implement `ResyncCoordinator`

Resync is a first-class feature, not an afterthought. It serializes refreshes, uses a fresh bundle, and publishes `RESYNCING` before success/failure. The last readable snapshot remains available during resync.  

Implement:

* in-progress flag
* consecutive failure counter
* `run(state)` that:

  1. rejects concurrent resyncs
  2. publishes `RESYNCING`
  3. opens fresh bundle
  4. runs bootstrap
  5. swaps bundle/event task on success
  6. publishes `LIVE` on success
  7. publishes `STALE` or `FAILED` on failure

Validate:

* manual refresh success
* manual refresh failure from live state → stale
* auto-resync stops after configured failure threshold
* readable last-good snapshot remains available during resync

### Step 16 — Implement `NiriState` itself

Only now write `store/live_state.py`. The public class should mostly orchestrate the already-built pieces. The connect flow is fixed by the spec: normalize config, validate correctness mode, open initial bundle, run bootstrap, publish first live snapshot, start event-consumer task, return usable instance. No half-live object should leak out.  

Internals to own:

* current snapshot
* revision counter
* broadcaster
* bundle
* event-consumer task
* lifecycle locks
* resync coordinator

Event loop behavior:

* one serialized consumer task only
* `await bundle.events.next()`
* `apply_event(...)`
* publish resulting snapshot/change
* on stream exceptions, transition stale/fail/resync per policy

Validate:

* `connect()` returns only after first live snapshot exists
* `current()` returns latest snapshot immediately
* `snapshot(wait_for_live=True)` blocks through resync and resumes on live
* `close()` is idempotent
* `close()` publishes final `CLOSED` snapshot if store had become readable
* new subscriptions and refreshes are rejected once close starts

### Step 17 — Implement selectors after the snapshot model is stable

Write only the selectors the spec requires. Keep them pure and snapshot-only. Do not smuggle policy or refresh behavior into them.  

Required selector families:

* outputs
* workspaces
* windows
* focus
* keyboard
* overview
* aggregates

Important cautions:

* no `visible_windows()` in v1 unless fully defined and tested
* no singular global `active_workspace()` unless you intentionally define it as convenience over focused state and document that clearly

Validate:

* direct lookup tests
* relationship traversal tests
* aggregate tests
* empty-state tests
* selector stability across unchanged revisions
* watch dedupe uses normal equality

### Step 18 — Implement replay support

Add replay traces only after reducers are stable. The replay engine should reuse the same bootstrap builder and root reducer used in live code. That keeps regressions honest. 

Implement:

* JSONL trace parser
* `bootstrap_payload` record loader
* externally-tagged event decoding via `niri_pypc.types`
* assertions for expected revision/health/selector outcomes

Validate:

* deterministic replay of same trace
* regression traces for previously fixed bugs
* long mixed event sequences converge identically across runs

### Step 19 — Add integration and live smoke coverage

Once the state engine works in isolation, verify end-to-end behavior with a controlled mock Niri-like session and then with optional live tests gated by `NIRI_SOCKET`. The spec’s integration/live split is correct; keep it. 

Integration coverage must include:

* bootstrap + live tracking
* unknown event → stale
* transport loss → stale/resync
* manual refresh
* monotonic gap-free revision publication
* overflow/desync paths

Live smoke:

* bootstrap against real compositor
* observe at least one real event-driven state change
* manual refresh smoke

### Step 20 — Finish packaging and docs last

Only after behavior is solid:

* fill `__init__.py` re-exports
* add README
* add bootstrap/resync guide
* add reducer/selectors authoring guide
* add examples for `current`, `changes`, `watch_selector`, `wait_until`
* clearly document live vs refresh-backed vs query-only domains, stale semantics, and dependency direction. 

## Testing and validation plan by milestone

### Milestone A — Foundation

Complete after Steps 1–5.

Must pass:

* model immutability tests
* config normalization tests
* error construction/chaining tests
* snapshot/change model shape tests

Exit criteria:

* package structure stable
* no mutable public state
* strict-vs-best-effort config policy encoded correctly

### Milestone B — Reducer correctness

Complete after Steps 6–11.

Must pass:

* `tests/reducers/test_bootstrap.py`
* `test_windows.py`
* `test_workspaces.py`
* `test_focus.py`
* `test_keyboard.py`
* `test_overview.py`
* `test_unknown_events.py`
* `test_invariants.py` 

Exit criteria:

* same bootstrap payload + same event sequence = same final snapshot and revisions
* unsupported/unknown inputs never silently drift
* invariants are enforced after every applied transition

### Milestone C — Sync correctness

Complete after Steps 12–15.

Must pass:

* response normalization tests
* bootstrap buffering tests
* strict backpressure contract tests
* resync tests
* compatibility tests 

Exit criteria:

* bootstrap race is closed
* strict mode truly uses fail-fast upstream queueing
* resync semantics match spec

### Milestone D — Public store behavior

Complete after Steps 16–17.

Must pass:

* `test_live_state.py`
* `test_changes.py`
* `test_watch_selector.py`
* `test_wait_until.py`
* `test_close_and_failure.py` 

Exit criteria:

* publication ordering is stable
* waits are event-driven
* watcher overflow behavior is correct
* close/failure semantics are predictable

### Milestone E — Hardening

Complete after Steps 18–20.

Must pass:

* replay suite
* integration suite
* optional live smoke suite
* lint/typecheck gates  

Exit criteria:

* regressions can be replayed
* end-to-end tracking converges
* docs match actual behavior

## A few implementation choices I would strongly recommend

1. Treat `WindowsChangedEvent` and `WorkspacesChangedEvent` as authoritative replace events for their domains. That keeps convergence simple and robust.
2. Use small pure helper functions for “derive focused workspace/output from focused window”.
3. Use `model_copy(update=...)` for updating raw generated Pydantic models.
4. Keep publication centralized in one method so revisions, `ChangeSet`, diagnostics, broadcaster fan-out, and waiter notifications cannot drift apart.
5. Explicitly document the handling of `ScreenshotCapturedEvent`, `WindowFocusTimestampChangedEvent`, and `WindowLayoutsChangedEvent` in the root reducer, since they exist in the current `niri-pypc` event surface but are outside the spec’s required v1 live-domain coverage.

## The shortest path to a successful implementation

Do it in this order:

1. models/config/errors
2. fixtures
3. normalization
4. invariants
5. bootstrap snapshot builder
6. reducers
7. broadcaster/waiters
8. bootstrap coordinator
9. store
10. resync
11. selectors
12. replay/integration/live/docs

That order matches the concept’s architecture and the spec’s definition of done, while also respecting the real behavior of the attached `niri-pypc` implementation.  

If it helps, I can turn this into an intern-facing checklist with concrete file-by-file tasks and test names.
