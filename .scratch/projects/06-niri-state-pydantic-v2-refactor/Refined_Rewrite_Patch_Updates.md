Here is the full delta I would apply to the refined skeleton to make it the final code skeleton.

These are the required changes, not just nice-to-haves. The refined draft is a strong base, but it still leaves some upstream-shape issues unresolved and a few runtime semantics unfinished. It also already acknowledges that exact model fields, reducer field names, and `query_version()` still need tightening before implementation.  

## 1. Add the missing files and skeleton seams

Add these to the package tree:

* `src/niri_state/_version.py` if you want to preserve `__version__`
* `tests/conftest.py`
* `tests/factories/events.py`
* `tests/factories/bundle.py` or `tests/factories/runtime.py`
* `tests/replay/traces/` with at least one typed trace fixture
* optionally `tests/factories/models.py` if you want to split protocol model factories from event factories

Add these private seams in `store.py`:

* `_open_bundle()` should stay
* `_install_bootstrap_outcome()` should be added
* `_start_mutation_loop()` / `_stop_mutation_loop()` helpers should be added so `connect()`, `refresh()`, and `close()` all use one lifecycle path
* `_publish_snapshot()` helper should be added so invariant handling, revision bumping, and broadcaster calls are not duplicated

The refined tree already includes the flattened runtime/core layout and the `_open_bundle()` seam, but it still lacks the fixture and replay scaffolding needed to make the tests real.  

## 2. Lock down the public API now

The refined skeleton changes the public API in several places. Before coding, pick one shape and make the skeleton consistent.

Required decisions:

* `NiriState.start`: either keep the current classmethod constructor style, or keep the refined instance method. Do not leave both the docs and tests assuming different styles.
* `snapshot`: either make it a property everywhere, or a method everywhere. The refined waiters assume a method; the current library uses a property.
* `watch`: either keep the current selector-stream semantics, or make it a raw snapshot stream and add a separate `watch_selector`.
* `__init__.py`: either preserve `__version__`, selector re-exports, `CorrectnessMode`, and `normalize_config`, or explicitly remove them and add migration notes.

My recommendation for the final skeleton is:

* keep `snapshot` as a property
* keep `start` as a classmethod constructor or add a compatibility classmethod wrapper
* keep selector module re-exports
* add a short compatibility note for any deliberate v2 breaks

## 3. Fix `protocol.py` so tests and reducers can use real upstream types

The refined `protocol.py` is fine as a central import surface, but the final skeleton should also re-export the generated helper types the factories and reducer tests need.

Add these exports:

* `Timestamp`
* `WindowLayout`
* `LogicalOutput`
* `Mode`

Optionally export:

* `Event`
* `Response`

That lets the test factories use exact upstream shapes instead of anonymous dict guesses.

## 4. Correct upstream model assumptions in the factories

This is the biggest compile-time blocker.

The refined factory defaults are not aligned to the actual generated `niri-pypc` models. The final skeleton must replace the placeholder payloads with exact upstream shapes.

Required additions:

* add `make_timestamp()`
* add `make_window_layout()`
* add `make_mode()`
* add `make_logical_output()`

Required corrections:

* `make_output()` must use upstream `Output` fields, not the placeholder shape
* `make_window()` must supply a real `WindowLayout`, because `layout` is not nullable upstream
* `make_workspace()` should allow `output=None`, because upstream `Workspace.output` is optional
* `make_overview()` and `make_keyboard_layouts()` are already close

So `tests/factories/protocol.py` needs to stop using the current approximate `Output` payload and stop using `layout=None` for `Window`. The refined document explicitly leaves these upstream-shape fixes for later; they need to be pulled into the final skeleton now.  

## 5. Add real event factories

`tests/unit/test_reducers.py` cannot stay on stub event classes if the point of the rewrite is exact alignment with generated upstream events.

Add `tests/factories/events.py` with helpers for:

* `make_windows_changed_event()`
* `make_window_opened_or_changed_event()`
* `make_window_closed_event()`
* `make_window_focus_changed_event()`
* `make_window_urgency_changed_event()`
* `make_window_focus_timestamp_changed_event()`
* `make_window_layouts_changed_event()`
* `make_workspaces_changed_event()`
* `make_workspace_activated_event()`
* `make_workspace_active_window_changed_event()`
* `make_workspace_urgency_changed_event()`
* `make_keyboard_layouts_changed_event()`
* `make_keyboard_layout_switched_event()`
* `make_overview_opened_or_closed_event()`

That change removes all uncertainty around field names and catches drift against `niri-pypc` immediately.

## 6. Correct the reducer field names and event semantics

These are mandatory code corrections in `reducers.py`.

Replace these assumptions:

* `WindowUrgencyChangedEvent.is_urgent` → `urgent`
* `WorkspaceUrgencyChangedEvent.is_urgent` → `urgent`
* `WindowLayoutsChangedEvent.id + layout` → `changes: list[tuple[int, WindowLayout]]`
* `WorkspaceActivatedEvent` must honor `focused`
* `WindowFocusChangedEvent.id` is `int | None`, not always `int`

Concretely:

* `reduce_window_urgency_changed()` must patch `is_urgent` from `event.urgent`
* `reduce_workspace_urgency_changed()` must patch `is_urgent` from `event.urgent`
* `reduce_window_layouts_changed()` must iterate `for win_id, layout in event.changes`
* `reduce_workspace_activated()` must always set `is_active=True` for the target, but only set `is_focused=True` and `focused_workspace_id=event.id` when `event.focused` is true
* `reduce_window_focus_changed()` must handle `event.id is None` by clearing `focused_window_id`, and either also clear `focused_workspace_id` or let reconcile derive it correctly
* `reduce_window_opened_or_changed()` should set `focused_workspace_id` too when the window is focused and has a workspace
* `reduce_windows_changed()` and `reduce_workspaces_changed()` can stay full-replacement reducers, but they must rely on stronger reconcile/invariant passes afterward

The refined reducer layer still contains unresolved upstream placeholders in exactly these areas, so these should be treated as direct replacements.  

## 7. Make `bootstrap.py` race-safe

The refined bootstrap flow queries state from an already-open bundle, but it does not protect against events arriving while those queries are running.

The final skeleton needs bootstrap buffering:

* start a temporary event reader before issuing bootstrap queries
* buffer all events that arrive during the bootstrap query phase
* build the initial engine state from query responses
* apply the buffered events through the same reducer pipeline
* only then publish revision 1

Without that, the initial snapshot can already be stale before publication.

Also fix these details:

* `query_version()` should simply return `response.payload`; upstream `VersionResponse.payload` is already `str`
* keep `focused_output` as diagnostics-only, not canonical focus state
* optionally add a generic `_extract_payload()` helper if you want bootstrap to be type-strict against reply variants

The refined skeleton already recognizes that `query_version()` still needs tightening; bootstrap event buffering is the larger missing piece that should be elevated into the final skeleton.  

## 8. Rework `refresh()` and auto-resync so they are actually safe

The refined `refresh()` is not final-skeleton safe yet.

Required correction:

* do not bootstrap against a bundle while the live mutation loop is still consuming that same bundle

Final-skeleton refresh flow should be:

1. transition to `RESYNCING`
2. stop the live mutation loop
3. open a fresh bundle
4. run bootstrap on the fresh bundle
5. atomically install the new engine/snapshot
6. restart the mutation loop on the new bundle
7. close the old bundle
8. publish a refresh/resync changeset

Also:

* if refresh succeeds, preserve health from the bootstrap outcome; do not unconditionally force `LIVE`
* if refresh fails under auto-resync, honor `resync_max_attempts` and `resync_backoff_base`
* use `ChangeCause.RESYNC` for auto-recovery publications
* keep `ChangeCause.REFRESH` for explicit manual refreshes

Right now the refined skeleton defines `RESYNCING`, `RESYNC`, and resync retry config, but does not fully use them in the runtime design. That needs to be completed. 

## 9. Move async task startup out of `ResyncCoordinator.__init__`

This is required.

If `NiriState(config=...)` is constructed outside a running loop and auto-resync is enabled, creating an asyncio task in `ResyncCoordinator.__init__` can fail.

Final-skeleton fix:

* `ResyncCoordinator.__init__` should be synchronous and side-effect free
* add `start()` and `close()` methods
* call `await self._resync.start()` from `connect()` after the store is live, or lazily create the loop task on first `request()`

## 10. Fix desync diagnostics in `_mark_desynced()`

This is a real logic bug in the refined runtime.

`_mark_desynced()` currently uses `with_error()` only. That means reducer-raised desyncs set `last_error`, but do not mark `diagnostics.desynced=True`.

Required fix:

* `_mark_desynced()` should use `with_desync(...)`, not just `with_error(...)`
* include `event_type` when available
* keep `last_error`
* then transition health to `STALE`

Unknown-event desync already does this through `_handle_unknown_event()`. Reducer-raised desyncs should behave the same way.

## 11. Add a real `resync_changeset()` helper

`ChangeCause.RESYNC` exists in the refined skeleton, but there is no helper for it.

Add:

* `resync_changeset(revision: int, domains: frozenset[ChangedDomain]) -> ChangeSet`

Then use it for successful auto-resync publications.

## 12. Strengthen `reconcile.py`

The three no-op helpers cannot remain no-ops in the final skeleton.

Required reconcile behavior:

* `_reconcile_focused_window`:

  * clear missing focused window
  * if focused window exists and has a workspace, derive `focused_workspace_id`
* `_reconcile_focused_workspace`:

  * clear missing focused workspace
  * if no focused workspace id is set, derive it from focused workspace flags
* `_reconcile_workspace_window_relationships`:

  * clear any workspace `active_window_id` that points to a missing window
  * clear any workspace `active_window_id` that points to a window on a different workspace
* `_reconcile_keyboard`:

  * optional clamp is fine, but at minimum leave it explicit that out-of-range `current_idx` is tolerated and only affects the derived current name
* `_reconcile_diagnostics`:

  * ensure diagnostics and health do not drift, at least for the `desynced` flag and invariant list lifecycle

You do not need to make reconcile overly magical, but you cannot leave those stubs empty in a final skeleton.

## 13. Strengthen `invariants.py`

The refined invariant set is too weak for a final skeleton.

Add checks for:

* mapping key/entity id mismatches:

  * `outputs[key].name == key`
  * `workspaces[key].id == key`
  * `windows[key].id == key`
* `focused_window_id` exists
* `focused_workspace_id` exists
* focused window’s `workspace_id` matches `focused_workspace_id`
* workspace `active_window_id` exists if set
* workspace `active_window_id` belongs to that same workspace if set
* workspace `output` exists in `outputs` when non-null
* `workspaces_by_output` only references real workspaces and matches each workspace’s `output`
* `windows_by_workspace` only references real windows and matches each window’s `workspace_id`
* `active_workspace_by_output` points to a real active workspace on that output
* no duplicate ids inside the derived index tuples
* optionally: no more than one active workspace per output
* optionally: no more than one focused workspace globally

The current refined invariant file only covers the base existence checks and one derived-index check. The final skeleton should include the full derived-index consistency pass. 

## 14. Define deterministic ordering for derived indexes and selectors

Right now the refined snapshot derives:

* `workspaces_by_output`
* `windows_by_workspace`
* `active_workspace_by_output`

but does not define ordering guarantees.

Add one explicit rule:

* `workspaces_by_output` should be ordered by `(idx, id)`
* `windows_by_workspace` should be ordered by a stable rule, at minimum by `id`, unless you intentionally want upstream insertion order

That makes selectors deterministic and keeps tests stable.

## 15. Fix `WaitTimeoutError`

Required correction in `errors.py`:

* `WaitTimeoutError` should subclass `TimeoutError`

That keeps compatibility with timeout handling and matches expected asyncio semantics better.

The refined skeleton currently stores `timeout`, but it drops the `TimeoutError` inheritance. 

## 16. Make `subscribe()` yield the current snapshot immediately

This is the cleaner final-skeleton behavior, and it matches the current library’s runtime contract.

Required change in `store.py`:

* wrap broadcaster subscription so `subscribe()` first yields the current snapshot if one exists, then yields future publications

That makes subscribers and waiters consistent even if they attach after `connect()`.

Do this in `store.subscribe()`, not in `Broadcaster`.

## 17. Make waiters consistent with the chosen store API

The refined waiters assume:

* `state.snapshot()` is a method
* `watch()` yields snapshots

If the final skeleton keeps the current store-style property and current watch semantics, then update waiters accordingly.

Required final choice:

* either keep the refined design and update store/tests to match
* or keep the current design and change waiters to:

  * read `state.snapshot` as a property
  * provide `watch_selector(state, selector)` with dedup behavior
  * optionally keep `watch(state)` as the raw snapshot stream

Do not leave the store, waiters, and tests assuming different signatures.

## 18. Preserve cumulative diagnostics across refreshes

Right now the refined `refresh()` replaces the engine, then calls `with_resync()` on the fresh diagnostics object.

That loses historical counters unless you explicitly merge them.

Required improvement:

* carry forward cumulative diagnostic fields like `resync_count`
* optionally preserve notes and compatibility warnings
* clear only fields that are supposed to reset on successful resync, such as `desynced`, `last_error`, and invariant violations

## 19. Clean up `broadcaster.py` semantics

The refined subscriber identity fix is already applied, so keep that. 

Add one more explicit decision:

* decide whether `SubscriberOverflowPolicy.FAIL_FAST` should fail only the offending subscription or fail the whole store

For a final skeleton, I would document that policy in the skeleton itself. If you want safer behavior, cancel only that subscriber. If you want strict behavior, let the error propagate and test for it.

## 20. Expand the tests from placeholders to executable seams

These are the required additions to make the test tree real:

In `tests/conftest.py` add fixtures for:

* `dummy_state`
* `fake_client`
* `fake_event_stream`
* `fake_bundle`
* `fake_runtime_bundle`

Add an in-memory event stream helper that supports whatever the final runtime uses:

* async iterator style, or
* `.next(timeout=...)` style

Integration tests should then actually cover:

* bootstrap publishes revision 1
* mutation loop publishes revision bumps after events
* unknown event policy behavior
* desync → stale transition
* auto-resync retry/backoff path
* refresh replaces bundle and snapshot atomically
* close publishes a final closed snapshot
* subscriber overflow policy

Replay tests should cover:

* applying a saved trace converges to the expected final snapshot
* invariants hold after every replayed step

## 21. Add one short implementation-contract appendix to the skeleton

This is not code, but it is required for the final skeleton to stop being ambiguous.

Add a short appendix with:

* exact upstream model fields used by factories
* exact upstream event fields used by reducers
* lifecycle contract for `connect`, `refresh`, `close`, and auto-resync
* subscriber contract
* ordering guarantees for selectors
* which public v1 APIs are preserved vs intentionally broken

## 22. Optional but worth folding in now

These are not blockers, but I would still include them in the final skeleton:

* `EngineState.is_initialized()`
* `_install_bootstrap_outcome()`
* `resync_changeset()`
* `watch_selector()` if `watch()` becomes a raw snapshot stream
* compatibility shims for `__version__`, `CorrectnessMode`, and `normalize_config` if you want a smoother migration

If you want, I can turn this into a file-by-file patch plan with exact replacement snippets for each module.
