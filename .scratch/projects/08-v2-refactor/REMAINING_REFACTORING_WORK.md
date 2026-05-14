# REMAINING_REFACTORING_WORK

## Purpose
This document lists the **remaining refactoring work** from `.scratch/projects/08-v2-refactor/Deep Review of niri-state and niri-pypc.md`, based on the current `niri-state` codebase state.

It excludes items already completed, except where noted in the completion audit section for traceability.

## Completion Audit (Already Done)
The following deep-review items are already implemented and are not part of remaining work:

1. `connect()` bootstrap-failure cleanup is implemented.
- Evidence: local bundle variable + `except Exception: await bundle.close(); raise` in `connect()`.
- Source: `src/niri_state/store.py`

2. `refresh()` now restores engine/loop on failure even when opening a new bundle fails.
- Evidence: `new_bundle` guarded `try/except`, restoration of `self._bundle`/`self._engine`, and `_start_mutation_loop()` in exception path.
- Source: `src/niri_state/store.py`

3. Manual refresh publishes `REFRESH` cause correctly.
- Evidence: `refresh_changeset(...)` used when cause is not `RESYNC`.
- Source: `src/niri_state/store.py`, `src/niri_state/changes.py`

4. `NiriState.open(...)` async classmethod exists.
- Source: `src/niri_state/store.py`

5. Bootstrap compatibility metadata includes schema version.
- Evidence: imports `UPSTREAM_VERSION` and populates `Compatibility.schema_version`.
- Source: `src/niri_state/bootstrap.py`

6. Bootstrap replay checks reducer desync markers.
- Evidence: replay loop checks `result.marked_desync` and sets stale health.
- Source: `src/niri_state/bootstrap.py`

7. `RESYNCING` is now entered during refresh flows.
- Source: `src/niri_state/store.py`

## Remaining Work (Prioritized)

## P0: Public API and Documentation Contract Corrections

1. Fix README quick-start to match real API.
- Current mismatch:
  - README uses `await NiriState.start(NiriStateConfig())` (classmethod style).
  - README unpacks `async for snapshot, changeset in state.subscribe()`.
- Actual API:
  - `start()` is instance method.
  - `subscribe()` yields `PublishedState`.
- Required changes:
  - Use `await NiriState.open(...)` or `await NiriState(...).start()`.
  - Show `PublishedState` usage (`published.snapshot`, `published.changes`).
  - Update lifecycle notes accordingly.
- Sources: `README.md`, `src/niri_state/store.py`, `src/niri_state/broadcaster.py`
- Acceptance criteria:
  - README example runs without modification against current API.
  - No tuple-unpack subscription examples remain.

2. Resolve `watch()` initial-duplicate contract ambiguity.
- Current behavior:
  - `watch()` yields `state.snapshot`, then iterates `state.subscribe()`.
  - `NiriState.subscribe()` also yields current snapshot first, causing duplicate initial snapshot.
- Required decision (pick one and document):
  - Option A: keep `watch()` behavior, change `NiriState.subscribe()` semantics.
  - Option B: keep `subscribe()` semantics, change `watch()` to avoid duplicate initial snapshot for `NiriState`.
- Sources: `src/niri_state/waiters.py`, `src/niri_state/store.py`
- Acceptance criteria:
  - Behavior is deterministic and explicitly documented.
  - Add regression test for chosen contract.

## P0: Stabilize niri-pypc Boundary

3. Remove deep imports from `niri_pypc.types.generated.*` / `niri_pypc.types.base` in `protocol.py`.
- Current state:
  - `src/niri_state/protocol.py` imports deep generated modules directly.
- Required changes:
  - Route imports through stable `niri_pypc.types` public surface where possible.
  - Minimize dependency on non-public internals.
- Source: `src/niri_state/protocol.py`
- Acceptance criteria:
  - No direct imports from `niri_pypc.types.generated.*` or `.types.base` remain in `niri-state` (except explicitly justified metadata import).

## P0: Make Resync Contract Real (or Remove Dead Surface)

4. Implement `resync_max_attempts` and `resync_backoff_base` in `ResyncCoordinator`, or remove/deprecate these config fields.
- Current state:
  - Fields exist in config but are unused.
  - Resync loop retries indefinitely with immediate retry behavior.
- Required changes:
  - Either implement bounded retries + backoff + diagnostics/logging + terminal behavior, or remove these fields and docs.
- Sources: `src/niri_state/config.py`, `src/niri_state/resync.py`, `README.md`
- Acceptance criteria:
  - Config surface matches runtime behavior.
  - Tests cover retry budget/backoff behavior if implemented.

## P1: Versioning and Packaging Coherence

5. Resolve package version inconsistency and expose runtime version cleanly.
- Current mismatch:
  - `pyproject.toml` version is `0.1.2`.
  - `src/niri_state/_version.py` is `0.1.0` and not exported.
- Required changes:
  - Single source of truth for version.
  - Expose `__version__` from package entrypoint.
- Sources: `pyproject.toml`, `src/niri_state/_version.py`, `src/niri_state/__init__.py`
- Acceptance criteria:
  - Imported runtime version matches package metadata version.
  - Add metadata test.

6. Tighten `niri-pypc` dependency range.
- Current state: `niri-pypc>=0.3.0`.
- Required change: constrain to reviewed compatible minor range (for example `>=0.3.1,<0.4`).
- Source: `pyproject.toml`
- Acceptance criteria:
  - Dependency range reflects tested compatibility policy.

7. Add typed-distribution metadata if typed consumption is intended.
- Required changes:
  - Add `py.typed` marker in package.
  - Ensure build includes marker.
  - Add package metadata tests.
- Source: `src/niri_state/`, `pyproject.toml`, `tests/`
- Acceptance criteria:
  - Wheel contains `py.typed`.
  - Metadata test validates marker and version.

## P1: Test and Quality Coverage Gaps

8. Add missing lifecycle/regression tests called out in deep review.
- Still missing/insufficiently explicit:
  - `connect()` bootstrap-failure closes bundle test.
  - `refresh()` open-bundle failure restores old mutation loop test.
  - `refresh(cause=REFRESH)` publishes `ChangeCause.REFRESH` test.
  - bootstrap unknown-event/desync behavior test for chosen policy.
  - `watch()` non-duplication (or intentional duplication) contract test.
- Sources: `tests/integration/`, `tests/unit/`, `src/niri_state/store.py`, `src/niri_state/bootstrap.py`, `src/niri_state/waiters.py`
- Acceptance criteria:
  - New tests fail before fix (or encode explicit intended current behavior) and pass after.

9. Enforce repo quality-gate commands for Python changes.
- For actual implementation PR(s), run:
  - `devenv shell -- uv sync --extra dev` (before first test run in session)
  - `devenv shell -- ruff check .`
  - `devenv shell -- ruff format --check .`
  - `devenv shell -- ty check .` (when interfaces/types change)
  - relevant tests / full suite as scope requires
- Source: `AGENTS.md`

## P2: Cleanup / Design Improvements

10. Simplify `query_version()` to strict current `VersionResponse.payload: str` contract unless legacy compatibility is explicitly required.
- Current state includes legacy fallback paths (`hasattr(payload, "version")`, `str(payload)`).
- Source: `src/niri_state/bootstrap.py`
- Acceptance criteria:
  - Chosen compatibility policy documented and tested.

11. Correct mypy configuration target declaration.
- Current state: `packages = ["src/niri_state"]` (path-shaped entry).
- Required change: use package-shaped config (`packages = ["niri_state"]`) or `files = [...]`.
- Source: `pyproject.toml`
- Acceptance criteria:
  - Type checker target selection is unambiguous and valid.

12. Add structured logging in key lifecycle paths.
- Minimum events:
  - bootstrap start/success/failure
  - mutation loop start/stop
  - desync detection
  - auto-resync requested/start/fail/success
  - subscriber overflow handling
- Sources: `src/niri_state/store.py`, `src/niri_state/resync.py`, `src/niri_state/broadcaster.py`
- Acceptance criteria:
  - Logs provide actionable production diagnostics without noisy duplication.

## Suggested Execution Order
1. P0 API/docs correctness (`README`, `watch()/subscribe()` semantics).
2. P0 boundary hardening (`protocol.py` import surface).
3. P0 resync contract completion/removal.
4. P1 packaging/version/dependency coherence.
5. P1 targeted regression tests + quality gates.
6. P2 cleanup items (version-query strictness, mypy config, logging).

## Out of Scope for This Repo Task
These were mentioned in deep review but are not `niri-state` refactoring tasks in this workspace:
- Cleaning stale build artifacts in `niri-pypc` repository.
- `niri-pypc` CI/internal repo hygiene work.
