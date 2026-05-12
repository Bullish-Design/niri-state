# FINAL_IMPLEMENTATION_REVIEW

## Scope
This review audits the current `niri-state` implementation against:
- `.scratch/projects/02-final-concept/FINAL_IMPLEMENTATION_GUIDE.md`
- General correctness, architecture quality, typing quality, and test rigor.

## Executive Summary
Implementation is **partially complete** and includes many core building blocks (config, error hierarchy, immutable snapshot model, draft model, reducer skeletons, bootstrap orchestration skeleton, selector modules, and broad test inventory).

However, the library is **not final-ready** per the guide. There are several **high-severity contract violations** in runtime behavior and dependency integration assumptions, plus missing/under-implemented modules and significant type-quality failures. The implementation does not yet satisfy completion checklist criteria in the guide.

## Validation Evidence
Commands run in this session:
1. `devenv shell -- uv sync --extra dev` (pass)
2. `devenv shell -- ruff check .` (pass)
3. `devenv shell -- ruff format --check .` (pass)
4. `devenv shell -- ty check .` (fail, 44 diagnostics)
5. `devenv shell -- pytest -q` and `devenv shell -- pytest -vv -x` (execution hangs in runtime waiter tests; see findings)

Notable hard evidence:
- `ty check` reports broad typing failures across tests and type-contract drift with runtime interfaces.
- `pytest -vv -x` stalls at `tests/runtime/test_waiters.py::TestWaitUntil::test_timeout_raises`, consistent with a missing timeout implementation path in waiter code.

## Guide Conformance Matrix

### Step 0-2 (Structure, Config, Errors, Core Models)
- **Pass / Mostly Pass**
- Present and generally aligned:
  - Core module layout exists.
  - `NiriStateConfig` is frozen dataclass.
  - Config normalization exists.
  - Error names include `WaitTimeoutError` and `SubscriptionOverflowError`.
  - `DraftState`, `BootstrapPayload`, and immutable snapshot models are present.
- Notes:
  - Guide-expected tests `tests/core/models/test_types.py`, `test_entities.py`, `test_changes.py`, reducer-domain test files, and runtime broadcaster tests are absent.

### Step 3 (Lifecycle FSM)
- **Pass**
- Health state enum and legal transition validation are implemented.

### Step 4-7 (Builder, Invariants, Domain Reducers, Root Reducer)
- **Partial**
- Implemented with decent baseline coverage, but correctness issues remain:
  - Replace-all reducers detect change by count only, not content equality.
  - Window upsert reducer always reports unchanged for updates due post-write comparison logic.
  - Root reducer uses `unknown_event_policy: str` instead of enum type; policy handling is string-based.

### Step 8 (Bootstrap Pipeline)
- **Fail (major integration mismatch risk)**
- Guide requires honoring `niri-pypc` reality where `client.request()` returns payload directly.
- Current code assumes wrapped `Response` variants and validates against `Response` subclasses.
- This is a critical contract mismatch likely to break with real upstream behavior.

### Step 9 (Store and Subscription Runtime)
- **Fail (major architecture/behavior gaps)**
- Broadcaster module exists as file but has no implementation.
- Store owns subscriber queue logic directly and introduces a local `SubscriberOverflowError` class conflicting with public errors.
- Mutation loop currently requires `_current_draft` to be pre-initialized and can raise runtime error on first event.
- `refresh()` replaces bundle/snapshot but does not restart mutation loop for the new bundle.
- `close()` clears bundle before attempting lifecycle transition to `CLOSED`, so closure health transition is effectively skipped.

### Step 10 (Wait/Watch APIs)
- **Fail (behavioral correctness)**
- `wait_until()` accepts `timeout` but never enforces it (no `asyncio.wait_for` or deadline logic).
- This directly explains hang in timeout-related tests.
- Health gating policy behavior from guide (`LIVE_ONLY` vs `ALLOW_STALE`) is not implemented.

### Step 11 (Resync/Recovery)
- **Fail / Stub-level**
- `_trigger_stale_transition()` is unimplemented (`pass`).
- Resync coordinator mutates store internals directly and does not publish lifecycle transitions/changesets.
- AUTO policy transitions and failure terminal behavior are incomplete vs guide.
- `refresh()` semantics in AUTO mode are not implemented through this coordinator contract.

### Step 12 (Selectors and Public Exports)
- **Partial**
- Selector modules exist and are pure.
- Return types are overly generic (`object`/`list[object]`) rather than stable typed contracts.
- Public exports from top-level package do not include selector namespace symbols as guide requested.

### Step 13-14 (Integration, Replay, API polish)
- **Partial**
- Integration/replay tests exist and many pass.
- Missing comprehensive policy-mode runtime behavior validation and missing full-quality gate completion (`ty`/full pytest).

## Findings (Ordered by Severity)

### Critical
1. **Bootstrap assumes wrong upstream `niri-pypc` response contract**
- Evidence: `src/niri_state/_runtime/bootstrap.py:160-223`
- Issue: code expects `Response` wrappers and variant classes. Guide explicitly requires handling direct payload returns from `client.request()`.
- Risk: production bootstrap likely fails type checks and raises `BootstrapError` despite valid upstream replies.

2. **Wait timeouts are not implemented, causing hangs**
- Evidence: `src/niri_state/_runtime/waiters.py:14-30`
- Issue: `timeout` parameter is unused; loop waits indefinitely on subscription stream.
- Risk: API contract violation; tests hang; callers can deadlock awaiting impossible predicates.

3. **Runtime resync path is incomplete and non-authoritative**
- Evidence: `src/niri_state/_runtime/resync.py:39-42`
- Issue: stale transition trigger is a no-op (`pass`), with no definitive state transition pipeline.
- Risk: stale detection and recovery policy cannot be trusted; AUTO/MANUAL semantics from guide are not met.

4. **Store refresh path can disconnect event processing**
- Evidence: `src/niri_state/_runtime/store.py:232-245`
- Issue: `refresh()` swaps bundle and snapshot but does not restart mutation loop against new bundle.
- Risk: state appears recovered but no further events are consumed.

### High
5. **Broadcaster module is missing implementation despite architecture requirement**
- Evidence: `src/niri_state/_runtime/broadcaster.py:1`
- Issue: empty file, while guide requires dedicated broadcaster with overflow policy semantics.
- Risk: architecture drift and reduced testability; overflow semantics fragmented in store.

6. **Store mutation loop has invalid initial draft guard**
- Evidence: `src/niri_state/_runtime/store.py:112-115`
- Issue: raises when `_current_draft is None`, then immediately recreates draft from snapshot.
- Risk: first runtime event can fail erroneously.

7. **Conflicting overflow exception type introduced in store**
- Evidence: `src/niri_state/_runtime/store.py:43-44`
- Issue: local `SubscriberOverflowError` shadows intended public `SubscriptionOverflowError`.
- Risk: inconsistent API/error handling; callers cannot rely on documented exceptions.

8. **`close()` lifecycle transition to CLOSED is effectively bypassed**
- Evidence: `src/niri_state/_runtime/store.py:265-272`
- Issue: `_bundle` and runtime internals are torn down before transition logic; transition method early-returns when snapshot state context is missing/invalid.
- Risk: closure observability and health-state correctness are degraded.

### Medium
9. **Reducer change-detection logic has correctness bugs**
- Evidence:
  - `src/niri_state/_core/reducers/windows.py:24-29` (upsert changed check done after overwrite)
  - `src/niri_state/_core/reducers/windows.py:17-21` and `src/niri_state/_core/reducers/workspaces.py:14-18` (replace-all checks count only)
- Risk: change notifications/domains can be wrong, impacting watchers and downstream logic.

10. **Selectors are weakly typed and leak generic `object` API surface**
- Evidence: `src/niri_state/selectors/windows.py:7-25` (similar pattern in other selector modules)
- Risk: poor IDE/static tooling support and avoidable contract ambiguity.

11. **Root reducer policy arg should be enum, not raw string**
- Evidence: `src/niri_state/_core/reducers/root.py:39-43` and `232-276`
- Risk: invalid runtime values accepted silently; weaker type safety.

### Low
12. **Type ignores and typing hygiene issues are substantial**
- Evidence: `devenv shell -- ty check .` output (44 diagnostics)
- Risk: lowers confidence in static safety and long-term maintainability.

## Test and Coverage Review
Strengths:
- Broad inventory with core/replay/runtime/selectors tests.
- Many reducer/invariant/snapshot paths covered.
- Replay determinism checks exist in integration.

Gaps vs guide:
- Missing dedicated reducer suite files (`test_root.py`, `test_windows.py`, `test_workspaces.py`, etc.).
- Missing runtime broadcaster tests (`tests/runtime/test_broadcaster.py`).
- Wait/watch tests include skipped watch cases and currently expose timeout hang.
- No robust verification of AUTO refresh semantics and legal transition traces across stale/resync/failed flows.

## Recommended Fix Sequence
1. Fix bootstrap request/response integration to match real `niri-pypc` return shapes.
2. Implement authoritative broadcaster module and wire store to it.
3. Repair store event loop lifecycle: draft initialization, refresh loop restart, close lifecycle publication.
4. Implement `wait_until` timeout and health-policy gating exactly per guide.
5. Complete resync coordinator transitions and AUTO/MANUAL behavior contract.
6. Correct reducer change-detection logic for replace-all and upsert paths.
7. Tighten selector typing and top-level exports.
8. Expand/align tests to missing guide-mandated files and scenarios.
9. Drive `ty check .` to zero diagnostics.
10. Re-run full quality matrix and record clean results.

## Final Verdict
The project is **not yet complete** relative to `FINAL_IMPLEMENTATION_GUIDE.md`. It has a solid foundation, but critical runtime and integration-contract gaps remain. The next iteration should prioritize runtime correctness and policy semantics before additional API expansion.
