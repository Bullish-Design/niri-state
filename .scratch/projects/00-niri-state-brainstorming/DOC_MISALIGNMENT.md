# DOC_MISALIGNMENT.md

Analysis of alignment issues between the four core `niri-state` documents:
- `NIRI_STATE_SPEC.md` (authoritative specification)
- `NIRI_STATE_CONCEPT.md` (high-level concept)
- `NIRI_STATE_IMPLEMENTATION_GUIDE_OVERVIEW.md` (implementation overview)
- `NIRI_STATE_IMPLEMENTATION_GUIDE_DETAIL.md` (detailed implementation guide)

---

## 1. Correctness Mode Backpressure Logic is Inverted in Detail Guide

**Location:** `NIRI_STATE_IMPLEMENTATION_GUIDE_DETAIL.md`, lines 285–298 (section 4, `effective_pypc_config`)

**Spec Rule (NIRI_STATE_SPEC.md, section 8, Config Semantics, rule 2):**
> `correctness_mode=STRICT` requires upstream event backpressure to be fail-fast.

**Detail Guide Implementation:**
```python
def effective_pypc_config(config: NiriStateConfig) -> NiriConfig:
    pypc = config.pypc
    if config.correctness_mode is CorrectnessMode.BEST_EFFORT:
        return pypc

    if pypc.backpressure_mode is BackpressureMode.FAIL_FAST:
        return pypc

    try:
        return replace(pypc, backpressure_mode=BackpressureMode.FAIL_FAST)
    except Exception as exc:
        raise StateConfigError(
            "Strict correctness mode requires FAIL_FAST upstream backpressure",
        ) from exc
```

**Problem:** The early-return logic checks for `BEST_EFFORT` first, then assumes `STRICT` requires fail-fast. This matches the spec intent, but the condition check is slightly awkward. More critically, if `correctness_mode` is `STRICT` and `pypc.backpressure_mode` is `DROP_OLDEST`, the code correctly forces fail-fast. However, the condition sequence implies the default non-BEST_EFFORT path is always `STRICT`, which is correct, but the logic is not defensive enough if an unknown mode is added later.

**Recommendation:** The logic is actually correct per spec, but the style is confusing. Add an explicit else branch or restructure to be clearer:

```python
def effective_pypc_config(config: NiriStateConfig) -> NiriConfig:
    pypc = config.pypc
    if config.correctness_mode is CorrectnessMode.STRICT:
        if pypc.backpressure_mode is not BackpressureMode.FAIL_FAST:
            try:
                return replace(pypc, backpressure_mode=BackpressureMode.FAIL_FAST)
            except Exception as exc:
                raise StateConfigError(
                    "Strict correctness mode requires FAIL_FAST upstream backpressure",
                ) from exc
    return pypc
```

---

## 2. Unknown Event Handling Does Not Set `ChangeCause.STALE_TRANSITION`

**Location:** `NIRI_STATE_IMPLEMENTATION_GUIDE_DETAIL.md`, lines 1356–1384 (`apply_event` root reducer)

**Spec Rule (NIRI_STATE_SPEC.md, section 11, Unknown / Unsupported Event Handling):**
> Default behavior with `unknown_event_policy=STALE`:
> - publish a new snapshot with:
>   - incremented revision,
>   - unchanged entity state,
>   - `health=STALE`,
>   - diagnostics recording the event,
>   - **`ChangeCause.STALE_TRANSITION`**,  <-- MISSING
>   - `ChangeDomain.HEALTH` and `ChangeDomain.METADATA`.

**Detail Guide Implementation:**
The root reducer sets `health=StoreHealth.STALE` and records diagnostics, but does not set `ChangeCause.STALE_TRANSITION` on the returned `ReductionResult`. The returned `ReductionResult` has no explicit `cause` field set—it only sets `snapshot`, `domains`, `event_type`, `applied=True`, and `summary`.

**Problem:** The `ReductionResult` class in the detail guide (lines 937–944) does not have a `cause` field, but the spec's `ChangeSet` model (lines 585–602) requires `cause: ChangeCause`. The spec's `ReductionResult` in section 11 (lines 920–927) also does not include `cause`. However, the `ChangeSet` constructed at publication time must include the correct `cause`. The detail guide's implementation appears to omit this from the reducer result, implying it must be injected at the publication layer.

**Recommendation:** Clarify in the spec whether `ReductionResult` should carry `cause`, or confirm that the store's publication layer is responsible for setting `ChangeCause.STALE_TRANSITION` when publishing an unknown-event stale transition. If the latter, document this responsibility explicitly in the `NiriState` publication logic section.

---

## 3. `ConfigLoadedEvent` is Mentioned but Not Handled

**Location:** `NIRI_STATE_IMPLEMENTATION_GUIDE_OVERVIEW.md`, lines 314–319; not in `NIRI_STATE_SPEC.md` required events

**Overview Text:**
> #### 10f. metadata/config handling
> 
> Handle:
> - `ConfigLoadedEvent`
> 
> This should probably not mutate entity state, but it should produce `ChangeDomain.METADATA` and update diagnostics/summary so consumers can observe successful or failed config loads.

**Problems:**

1. **Spec does not list `ConfigLoadedEvent` as a required event reducer.** The spec's "Required Event Reducer Coverage" (lines 976–992) includes window, workspace, focus, keyboard, overview events—but not `ConfigLoadedEvent`. The spec does not mention it in the invariant, selector, or bootstrap sections either.

2. **The overview says "handle it" but the detail guide does not implement it.** Looking at the detail guide's `reducers/root.py` imports (lines 1329–1347), `ConfigLoadedEvent` is not imported or handled. The `apply_event` function raises `DesyncError` for unhandled events.

3. **Contradiction:** If `ConfigLoadedEvent` reaches `apply_event` without being handled, the root reducer raises `DesyncError("Unhandled known event type ...")` per lines 1415–1421, which contradicts the overview's guidance that it should produce `ChangeDomain.METADATA` and update diagnostics.

**Recommendation:** Either:
- Add `ConfigLoadedEvent` to the spec's required event reducer coverage (if it's a real event in the current `niri-pypc` surface), OR
- Remove the overview's mention of `ConfigLoadedEvent` handling, OR
- Clarify that it should be an explicit no-op in the root reducer alongside `ScreenshotCapturedEvent` etc.

---

## 4. Window Urgency Events: Listed in Spec but Not in Overview

**Location:** 
- `NIRI_STATE_SPEC.md`, lines 982–983 (required events)
- `NIRI_STATE_IMPLEMENTATION_GUIDE_OVERVIEW.md`, section 10a (only lists `WindowOpenedOrChangedEvent`, `WindowClosedEvent`, `WindowsChangedEvent`)

**Spec Required Events (lines 976–992):**
> - window opened/changed,
> - window closed,
> - windows changed,
> - **window focus changed,**
> - **window urgency changed,**  <-- in spec
> - workspace activated,
> - ...

**Overview Section 10a (lines 228–249):**
> Handle:
> - `WindowOpenedOrChangedEvent`
> - `WindowClosedEvent`
> - `WindowsChangedEvent`
> - **`WindowUrgencyChangedEvent`**  <-- MISSING from overview's list

The overview lists four window events but omits `WindowUrgencyChangedEvent`, while the spec includes it. The detail guide also does not show urgency handling in its starter snippet.

**Recommendation:** Add `WindowUrgencyChangedEvent` to the overview's window reducer events list, and ensure the detail guide's window reducer includes `apply_window_urgency_changed`.

---

## 5. Workspace Urgency Events: Same Issue

**Location:**
- `NIRI_STATE_SPEC.md`, lines 986–987
- `NIRI_STATE_IMPLEMENTATION_GUIDE_OVERVIEW.md`, section 10b

**Spec (lines 986–987):**
> - workspace urgency changed,

**Overview Section 10b (lines 251–268):**
> Handle:
> - `WorkspaceActivatedEvent`
> - `WorkspaceActiveWindowChangedEvent`
> - `WorkspaceUrgencyChangedEvent`  <-- Listed correctly
> - `WorkspacesChangedEvent`

This one is actually present in the overview. No discrepancy here.

---

## 6. `KeyboardLayoutsState` Model Default Mismatch

**Location:**
- `NIRI_STATE_SPEC.md`, lines 311–330
- `NIRI_STATE_IMPLEMENTATION_GUIDE_DETAIL.md`, lines 434–437

**Spec:**
```python
class KeyboardLayoutsState(FrozenModel):
    raw: KeyboardLayouts
    current_idx: int | None = None
    current_name: str | None = None
```
All fields have explicit defaults.

**Detail Guide:**
```python
class KeyboardLayoutsState(FrozenModel):
    raw: KeyboardLayouts
    current_idx: int | None = None
    current_name: str | None = None
```
Same structure.

**Minor note:** The spec shows all three fields with defaults. The detail guide matches. No real discrepancy—just verify `current_idx` and `current_name` have defaults in the final implementation.

---

## 7. `OverviewState` Field Defaults

**Location:**
- `NIRI_STATE_SPEC.md`, lines 332–348
- `NIRI_STATE_IMPLEMENTATION_GUIDE_DETAIL.md`, lines 440–442

**Spec:**
```python
class OverviewState(FrozenModel):
    raw: Overview | None = None
    is_open: bool | None = None
```

**Detail Guide:**
```python
class OverviewState(FrozenModel):
    raw: Overview | None = None
    is_open: bool | None = None
```
Matches exactly.

---

## 8. Missing Explicit Enumeration of Selector Functions in Detail Guide

**Location:** `NIRI_STATE_IMPLEMENTATION_GUIDE_DETAIL.md` (no explicit selector section with function names)

**Problem:** The spec (section 13, lines 1086–1175) provides an explicit list of required selector functions:
- Output selectors: `output_by_name`, `outputs`, `focused_output`, `workspaces_on_output`, `output_config_is_live_current`
- Workspace selectors: `workspace_by_id`, `workspaces`, `focused_workspace`, `active_workspaces_on_output`, `windows_on_workspace`
- Window selectors: `window_by_id`, `windows`, `focused_window`, `workspace_for_window`
- Focus selectors: `focused_window_id`, `focused_workspace_id`, `focused_output_name`
- Keyboard/Overview selectors: `keyboard_layouts`, `current_keyboard_layout_name`, `current_keyboard_layout_index`, `overview_is_open`
- Aggregate selectors: `window_count`, `workspace_count`, `output_count`, `has_window`, `is_live`, `is_stale`

The overview (Step 17) mentions the required families but does not enumerate them. The detail guide does not mention selectors at all in its build order.

**Recommendation:** Add a section to the detail guide (after step 11 or in step 17) that explicitly lists all required selector functions as starter code, matching the spec's enumeration. This ensures the intern doesn't have to cross-reference the spec for every selector name.

---

## 9. `OverviewState` Rule 3 Clarification

**Location:** `NIRI_STATE_SPEC.md`, line 347; `NIRI_STATE_IMPLEMENTATION_GUIDE_DETAIL.md`, lines 440–442

**Spec Rule 3:**
> 3. `None` means unknown, not closed.

**Problem:** This is a semantic clarification but it's not reflected in any starter code comment or validation test in the detail guide. The `is_open: bool | None` field is self-documenting but the "unknown vs closed" distinction is subtle.

**Recommendation:** Add a code comment in the detail guide's `OverviewState` starter:
```python
class OverviewState(FrozenModel):
    raw: Overview | None = None  # None until first overview query/bootstrap
    is_open: bool | None = None  # None means unknown, not closed
```

---

## 10. Layers as Query-Only Domain is Implicit, Not Explicit in Detail Guide

**Location:** `NIRI_STATE_SPEC.md`, lines 468–469, 581; `NIRI_STATE_IMPLEMENTATION_GUIDE_DETAIL.md`, lines 656–671

**Spec (domain classification table, line 469):**
> | layers | query-only or unsupported | Queryable, but not event-reduced live in current event surface. |

**Spec (ChangeDomain rules, line 581):**
> `LAYERS` is intentionally omitted from the default domain enum because layers are not event-reduced live in the current `niri-pypc` surface.

**Detail Guide (`layers_raw` in BootstrapPayload, line 656):**
```python
layers_raw: object | None = None
```

The detail guide supports `layers_raw` in the bootstrap payload but does not document that it's query-only and intentionally excluded from the `ChangeDomain` enum.

**Recommendation:** Add a comment in the detail guide's `layers_raw` field:
```python
layers_raw: object | None = None  # query-only; not event-reduced live, not in ChangeDomain
```

---

## 11. No `visible_windows()` Selector Agreed, But Should Be Documented

**Location:**
- `NIRI_STATE_SPEC.md`, lines 1139–1140
- `NIRI_STATE_IMPLEMENTATION_GUIDE_OVERVIEW.md`, line 496

**Both documents agree:** `visible_windows()` is not part of the required v1 selector surface unless visibility is precisely defined.

**Problem:** Neither document explicitly states this as a negative requirement that must be actively resisted. The overview says "no visible_windows() in v1 unless fully defined and tested" which is strong, but the detail guide does not mention it at all.

**Recommendation:** Add to step 17 in the overview (or create a new step 17 in the detail guide):
> **Negative requirements for selectors:**
> - Do not implement `visible_windows()` in v1 unless a precise, tested visibility derivation rule is documented.
> - Do not implement a singular global `active_workspace()` unless its semantics are explicitly documented.

---

## 12. Bootstrap Event Buffer Overflow Handling

**Location:** `NIRI_STATE_IMPLEMENTATION_GUIDE_OVERVIEW.md`, lines 410–413; `NIRI_STATE_SPEC.md`, lines 1223–1225

**Both documents agree:** Local bootstrap event buffer overflow causes bootstrap failure.

**However, the overview says:**
> - local bootstrap buffer overflow is always bootstrap failure

But the spec's detail in "Queue Overflow Rules" (lines 723–725) says:
> For the local bootstrap event buffer:
> - overflow is always a bootstrap failure, because the race window can no longer be proven closed.

**Problem:** The detail guide does not have a corresponding section defining this rule. It's only implied in the `run_bootstrap` step descriptions (step 4 in overview's step 14).

**Recommendation:** Add explicit overflow handling rules to the detail guide's `sync/bootstrap.py` section, or reference the spec's "Queue Overflow Rules" section explicitly.

---

## 13. `ReducerContext` Imports Across Documents

**Location:** 
- `NIRI_STATE_SPEC.md`, lines 907–917 (spec's ReducerContext)
- `NIRI_STATE_IMPLEMENTATION_GUIDE_DETAIL.md`, lines 929–935 (guide's ReducerContext)

**Spec:**
```python
class ReducerContext(FrozenModel):
    cause: ChangeCause
    unknown_event_policy: UnknownEventPolicy
    invariant_failure_policy: InvariantFailurePolicy
    compatibility: CompatibilityInfo
    metadata: dict[str, Any] = Field(default_factory=dict)
```

**Detail Guide:**
```python
class ReducerContext(FrozenModel):
    cause: ChangeCause
    unknown_event_policy: UnknownEventPolicy
    invariant_failure_policy: InvariantFailurePolicy
    compatibility: CompatibilityInfo
    metadata: dict[str, Any] = Field(default_factory=dict)
```
Matches exactly.

---

## 14. `ReductionResult` Does Not Include `cause` Field

**Location:**
- `NIRI_STATE_SPEC.md`, lines 920–927 (spec's ReductionResult)
- `NIRI_STATE_IMPLEMENTATION_GUIDE_DETAIL.md`, lines 937–944 (guide's ReductionResult)

**Spec:**
```python
class ReductionResult(FrozenModel):
    snapshot: NiriSnapshot
    domains: tuple[ChangeDomain, ...] = ()
    event_type: str | None = None
    applied: bool = True
    summary: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
```

**Detail Guide:**
```python
class ReductionResult(FrozenModel):
    snapshot: NiriSnapshot
    domains: tuple[ChangeDomain, ...] = ()
    event_type: str | None = None
    applied: bool = True
    summary: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
```
Matches exactly.

**Note:** Neither includes a `cause` field, which aligns with the earlier finding that `ChangeCause.STALE_TRANSITION` must be injected at the publication layer. This is consistent but needs explicit documentation.

---

## 15. Package Structure Files: `common.py` Split

**Location:**
- `NIRI_STATE_SPEC.md`, lines 108–109 (model files list)
- `NIRI_STATE_IMPLEMENTATION_GUIDE_OVERVIEW.md`, lines 36–37
- `NIRI_STATE_IMPLEMENTATION_GUIDE_DETAIL.md`, section 2 (only `common.py` mentioned with identifier aliases)

**Spec and Overview:**
```
├─ models/
│  ├─ __init__.py
│  ├─ common.py         # FrozenModel, id aliases, helper types
│  ├─ health.py
│  ├─ entities.py
│  ├─ snapshot.py
│  └─ change_set.py
```

**Problem:** The spec and overview list five model files: `common.py`, `health.py`, `entities.py`, `snapshot.py`, `change_set.py`. The detail guide's section 2 only creates `models/common.py` with identifier aliases, and subsequent sections create `models/health.py`, `models/entities.py`, etc. This is correct, but the detail guide doesn't provide starter code for `models/snapshot.py` or `models/change_set.py` explicitly—it puts `NiriSnapshot`, `SnapshotIndexes`, `ChangeSet`, `ChangeCause`, and `ChangeDomain` in `models/entities.py` (lines 445–511).

**Alignment:** The spec says `snapshot.py` should contain `NiriSnapshot` and `SnapshotIndexes`, and `change_set.py` should contain `ChangeSet`, `ChangeDomain`, and `ChangeCause`. The detail guide consolidates these into `entities.py`.

**Recommendation:** Either:
- Keep consolidation (entities.py contains all entity/state models) and update the spec's module map, OR
- Split into separate files per spec and ensure the detail guide provides starter code for `snapshot.py` and `change_set.py`.

The spec's module map (lines 108–114) is authoritative. If the detail guide consolidates, it should note this as a deliberate deviation or the spec should be updated.

---

## 16. Empty Bootstrapping Snapshot Definition Location

**Location:** `NIRI_STATE_SPEC.md`, lines 426–441

**Problem:** The spec defines `EMPTY_BOOTSTRAPPING_SNAPSHOT` as an internal placeholder, but the detail guide does not include this constant or mention where it should live. The overview doesn't mention it either.

**Recommendation:** Add to the detail guide's `models/snapshot.py` (or whichever file contains `NiriSnapshot`):
```python
EMPTY_BOOTSTRAPPING_SNAPSHOT = NiriSnapshot(
    revision=0,
    health=StoreHealth.BOOTSTRAPPING,
    compatibility=CompatibilityInfo(
        niri_state_version="<version>",
        niri_pypc_version="<version>",
    ),
    bootstrapped=False,
    outputs_by_name={},
    workspaces_by_id={},
    windows_by_id={},
)
```

---

## 17. Devenv Scripts Order in Detail vs. Overview vs. Spec

**Location:**
- `NIRI_STATE_IMPLEMENTATION_GUIDE_OVERVIEW.md`, lines 241–250 (CI gate sequence)
- `NIRI_STATE_SPEC.md`, lines 241–256 (devenv scripts)
- `NIRI_STATE_IMPLEMENTATION_GUIDE_DETAIL.md`, line 77 (ruff check, line 93 for validation)

**Spec devenv scripts (lines 104–111):**
```nix
scripts = {
    test-reducers.exec = "pytest tests/reducers -q";
    test-selectors.exec = "pytest tests/selectors -q";
    test-store.exec = "pytest tests/store tests/sync tests/integration -q";
    test-all.exec = "pytest -q";
    lint.exec = "ruff check . && ruff format --check .";
    typecheck.exec = "ty check .";
};
```

**Overview CI Gate Sequence (lines 241–250):**
```bash
pytest tests/reducers -q
pytest tests/selectors -q
pytest tests/sync tests/store tests/integration -q
pytest tests/replay -q
ruff check .
ruff format --check .
ty check .
```

**Discrepancy:** The spec's devenv scripts combine `tests/store tests/sync tests/integration` under `test-store`, but the overview's CI gate sequence also includes `tests/replay` as a separate gate step. The spec does not list `tests/replay` in the devenv scripts.

**Recommendation:** Update the spec's devenv scripts to include `tests/replay` as a separate script or add it to `test-all`:
```nix
scripts = {
    test-reducers.exec = "pytest tests/reducers -q";
    test-selectors.exec = "pytest tests/selectors -q";
    test-sync-store.exec = "pytest tests/sync tests/store tests/integration -q";
    test-replay.exec = "pytest tests/replay -q";
    test-all.exec = "pytest -q";
    lint.exec = "ruff check . && ruff format --check .";
    typecheck.exec = "ty check .";
};
```

---

## 18. Domain Freshness Classification Table

**Location:** `NIRI_STATE_SPEC.md`, lines 461–478

**Problem:** The spec has a detailed domain freshness classification table, but the overview and detail guide do not reference or restate it. This is an important architectural point that should be reinforced in both implementation guides.

**Recommendation:** Add to the overview (after step 4) and detail guide (after config/error/models):
```
### Domain Freshness Summary

| Domain | Classification | Notes |
|---|---|---|
| windows | event-reduced live | Supported by window events. |
| workspaces | event-reduced live | Supported by workspace events. |
| focus | event-reduced live | Supported by focus events and queries. |
| keyboard layouts | event-reduced live | Bootstrap from query; update from keyboard events. |
| overview | event-reduced live | Bootstrap from query; update from overview events. |
| outputs | refresh-backed | No dedicated output-change event in current surface. |
| layers | query-only or unsupported | Queryable, but not event-reduced live. |
```

---

## 19. Resync Triggers List Incompleteness

**Location:** `NIRI_STATE_SPEC.md`, lines 1286–1294 (resync triggers); `NIRI_STATE_IMPLEMENTATION_GUIDE_OVERVIEW.md` does not list resync triggers; `NIRI_STATE_IMPLEMENTATION_GUIDE_DETAIL.md` step 15 does not list triggers.

**Problem:** The spec defines a comprehensive list of resync triggers, but the implementation guides do not restate or reference them. The detail guide's step 15 on resync says:
> Resync is a first-class feature, not an afterthought.

But it does not enumerate triggers.

**Recommendation:** Add to the detail guide's step 15:
```
Required resync triggers:
- explicit manual refresh/resync call
- transport loss in live event loop
- upstream fail-fast backpressure overflow
- unknown inbound event when stale-on-unknown policy is active
- unsupported known event when it may affect state
- invariant failure when stale-on-invariant policy is active
```

---

## 20. `broadcast_query_plan_name` Not in Detail Guide

**Location:** `NIRI_STATE_SPEC.md`, lines 682, 841, 858

**Spec Config (line 682):**
```
bootstrap_query_plan_name: str = "default"
```

**Spec BootstrapPayload (line 841):**
```
query_plan_name: str
```

**Spec Query Plan Rules (line 886):**
> 1. The query plan is explicit and named.

**Problem:** The detail guide's config section (lines 253–283) includes `bootstrap_query_plan_name: str = "default"`, and the bootstrap payload includes `query_plan_name`, but the detail guide doesn't provide a concrete list of available query plan names or what each plan includes.

**Recommendation:** Add a section in the detail guide defining the default query plan explicitly:
```python
DEFAULT_QUERY_PLAN = {
    "name": "default",
    "requests": [
        "OutputsRequest",
        "WorkspacesRequest",
        "WindowsRequest",
        "FocusedOutputRequest",
        "FocusedWindowRequest",
        "KeyboardLayoutsRequest",
        "OverviewStateRequest",
    ],
}
```

---

## 21. Test File Naming Convention: `conftest.py` vs `test_*.py`

**Location:** `NIRI_STATE_SPEC.md`, lines 122–164 (test structure); `NIRI_STATE_IMPLEMENTATION_GUIDE_DETAIL.md`, section 7 (only `conftest.py` mentioned)

**Spec Test Structure:** Uses `test_*.py` naming consistently (e.g., `test_bootstrap.py`, `test_windows.py`).

**Detail Guide Section 7:** Creates `conftest.py` with fixture builders, and references test files that should be created later (e.g., `tests/reducers/test_bootstrap.py`).

**Minor discrepancy:** The spec uses `conftest.py` for fixtures (line 122) but doesn't explicitly show the file creation guidance. The detail guide correctly separates fixture creation (section 7) from test file creation.

**Status:** Aligned. No action needed.

---

## 22. Invariant Enforcement Location Ambiguity

**Location:** `NIRI_STATE_SPEC.md`, lines 1076–1083 (enforcement policy); `NIRI_STATE_IMPLEMENTATION_GUIDE_DETAIL.md` distributes enforcement across steps 10–12

**Spec Policy:**
> After each non-no-op reducer result:
> 1. run `check_snapshot_invariants()`,
> 2. if violations are empty, continue,
> 3. if violations exist and `invariant_failure_policy=STALE`, convert the result into a stale snapshot publication,
> 4. if violations exist and `invariant_failure_policy=FAIL`, raise `InvariantError`.

**Detail Guide Approach:**
- Step 8: Implement `check_snapshot_invariants` in `invariants.py` (lines 956–1047)
- Step 11: Implement domain reducers with no explicit invariant enforcement
- Step 12: Implement root reducer without explicit invariant enforcement call
- The enforcement is implied but not explicitly shown in the root reducer code

**Problem:** The root reducer starter code (lines 1356–1422) does not call `check_snapshot_invariants`. The spec says enforcement should happen "after each non-no-op reducer result," implying it should be in the root reducer or a wrapper.

**Recommendation:** Add invariant enforcement to the root reducer in the detail guide:
```python
def apply_event(snapshot, event, *, next_revision: int, context: ReducerContext) -> ReductionResult:
    # ... event handling ...
    
    # Run invariants after applied event
    violations = check_snapshot_invariants(result.snapshot)
    if violations:
        if context.invariant_failure_policy is InvariantFailurePolicy.FAIL:
            raise InvariantError(
                f"Snapshot violated {len(violations)} invariant(s)",
                violations=violations,
            )
        # Convert to stale
        stale = result.snapshot.model_copy(
            update={"health": StoreHealth.STALE}
        )
        result = result.model_copy(update={"snapshot": stale})
    
    return result
```

---

## Summary of Findings

| # | Issue | Severity | Documents |
|---|-------|----------|-----------|
| 1 | Correctness mode logic style | Low | Detail vs Spec |
| 2 | `ChangeCause.STALE_TRANSITION` not set in reducer | High | Detail vs Spec |
| 3 | `ConfigLoadedEvent` mentioned but not handled | High | Overview vs Spec + Detail |
| 4 | `WindowUrgencyChangedEvent` missing from Overview | Medium | Overview vs Spec |
| 5 | `WorkspaceUrgencyChangedEvent` listed correctly | N/A | Already aligned |
| 6 | `KeyboardLayoutsState` defaults aligned | None | Already aligned |
| 7 | `OverviewState` defaults aligned | None | Already aligned |
| 8 | Selector functions not enumerated in Detail | Medium | Detail vs Spec |
| 9 | `OverviewState` "unknown not closed" not documented | Low | Detail lacks comment |
| 10 | Layers query-only not explicitly documented | Low | Detail lacks comment |
| 11 | `visible_windows()` negative requirement not in Detail | Low | Detail vs Spec + Overview |
| 12 | Bootstrap buffer overflow not explicitly documented | Medium | Detail vs Spec |
| 13 | `ReducerContext` aligned | None | Already aligned |
| 14 | `ReductionResult` no `cause` field (consistent) | Low | Both docs |
| 15 | Module split mismatch (snapshot.py vs entities.py) | Medium | Detail vs Spec |
| 16 | `EMPTY_BOOTSTRAPPING_SNAPSHOT` not in Detail | Low | Detail vs Spec |
| 17 | `tests/replay` missing from devenv scripts in Spec | Low | Spec vs Overview |
| 18 | Domain freshness table not in Overview/Detail | Medium | Missing from guides |
| 19 | Resync triggers not in Detail | Medium | Detail vs Spec |
| 20 | `bootstrap_query_plan_name` not detailed | Low | Detail lacks plan details |
| 21 | Test naming aligned | None | Already aligned |
| 22 | Invariant enforcement location ambiguous | High | Detail vs Spec |

**Priority:** Issues #2, #3, #15, #22 are the most critical as they affect core behavior correctness and could lead to incorrect implementations.

---

*Generated from cross-document analysis of `NIRI_STATE_SPEC.md`, `NIRI_STATE_CONCEPT.md`, `NIRI_STATE_IMPLEMENTATION_GUIDE_OVERVIEW.md`, and `NIRI_STATE_IMPLEMENTATION_GUIDE_DETAIL.md`.*