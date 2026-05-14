# ORGANIZATION_REFACTOR

## Goal
Reorganize `src/niri_state` into explicit architectural subdirectories while preserving backward compatibility and keeping quality gates green after each step.

## Target Structure

```text
src/niri_state/
  __init__.py
  _version.py
  api/
    __init__.py
    state.py
    config.py
    snapshot.py
    changes.py
    errors.py
    health.py
    waiters.py
    selectors/
      __init__.py
      aggregates.py
      focus.py
      keyboard.py
      outputs.py
      overview.py
      windows.py
      workspaces.py
  core/
    __init__.py
    bootstrap.py
    broadcaster.py
    diagnostics.py
    engine_state.py
    invariants.py
    reconcile.py
    reducers.py
    resync.py
  adapters/
    __init__.py
    protocol.py
  observability/
    __init__.py
    logging.py
```

## Architectural Rules

1. Public API flows through `niri_state.__init__` and `niri_state.api.*`.
2. `api` may depend on `core` only through stable interfaces (not circularly).
3. `core` may depend on `adapters` and `observability`.
4. `adapters` cannot import `core`.
5. `observability` is dependency-light and import-safe.

## Migration Strategy

1. Use **small batches** and keep each batch independently valid.
2. For each moved module, leave a **top-level shim** in old location.
3. Update imports incrementally; avoid mixed old/new import styles in same area.
4. Run lint/type/tests after every batch.
5. Remove shims only after explicit deprecation window.

## Step-by-Step Implementation Plan

## Phase 0: Safety Baseline

1. Create a branch for this refactor.
2. Run full quality baseline:
   - `devenv shell -- uv sync --extra dev`
   - `devenv shell -- ruff check .`
   - `devenv shell -- ruff format --check .`
   - `devenv shell -- ty check .`
   - `devenv shell -- pytest -q`
3. Record baseline results in PR description.

## Phase 1: Create New Package Directories

1. Add directories with `__init__.py` files:
   - `api/`, `core/`, `adapters/`, `observability/`.
2. Do not move business logic yet.
3. Add short module-level comments in each `__init__.py` defining ownership.

Acceptance:
- Imports still unchanged.
- All checks pass.

## Phase 2: Move Leaf Modules First

Move low-risk modules with minimal inbound dependencies:
1. `protocol.py` -> `adapters/protocol.py`
2. `logging.py` -> `observability/logging.py`

For each move:
- Create new target file with full implementation.
- Replace old file with shim:
```python
from niri_state.adapters.protocol import *  # noqa: F401,F403
```
or
```python
from niri_state.observability.logging import *  # noqa: F401,F403
```
- Update direct internal imports to prefer new path.

Acceptance:
- `ruff`, `ty`, targeted tests for moved modules pass.

## Phase 3: Move Core Infrastructure Modules

Move modules that are internal and mostly non-public:
1. `diagnostics.py` -> `core/diagnostics.py`
2. `engine_state.py` -> `core/engine_state.py`
3. `invariants.py` -> `core/invariants.py`
4. `reconcile.py` -> `core/reconcile.py`
5. `reducers.py` -> `core/reducers.py`
6. `broadcaster.py` -> `core/broadcaster.py`
7. `bootstrap.py` -> `core/bootstrap.py`
8. `resync.py` -> `core/resync.py`

After each move:
- Leave shim module at old path.
- Update internal imports gradually toward `niri_state.core.*`.
- Run targeted tests (`test_reconcile`, `test_reducers`, `test_bootstrap`, `test_resync`, `test_store_regressions`).

Acceptance:
- No behavior changes.
- Regression tests and quality gates remain green.

## Phase 4: Move Public-Facing API Modules

Move public-ish modules into `api/`:
1. `store.py` -> `api/state.py`
2. `config.py` -> `api/config.py`
3. `snapshot.py` -> `api/snapshot.py`
4. `changes.py` -> `api/changes.py`
5. `errors.py` -> `api/errors.py`
6. `health.py` -> `api/health.py`
7. `waiters.py` -> `api/waiters.py`
8. `selectors/*` -> `api/selectors/*`

Keep top-level shims for all moved files during deprecation period.

Acceptance:
- `niri_state.__init__` exports unchanged.
- Existing user imports continue working.

## Phase 5: Canonicalize Import Surface

1. Update `niri_state.__init__` to import from new canonical paths.
2. Keep exported names exactly stable.
3. Add/adjust tests for public import compatibility:
   - `import niri_state`
   - old-path import still works (`from niri_state.store import NiriState`)
   - new-path import works (`from niri_state.api.state import NiriState`)

Acceptance:
- Backward compatibility verified by tests.

## Phase 6: Add Guardrails

1. Add a lightweight architecture test (or lint rule) that enforces dependency direction.
2. Example checks:
   - `adapters` cannot import `core`.
   - `observability` cannot import `api`/`core`.
   - `api` cannot import from top-level shims.

Acceptance:
- Fails when forbidden imports are introduced.

## Phase 7: Docs and Deprecation Policy

1. Update README with module layout summary.
2. Add migration note showing old -> new import paths.
3. Mark shims as deprecated in docstrings/changelog.
4. Define removal target release (e.g., next minor+1).

Acceptance:
- Users have a clear migration path.

## Phase 8: Shim Removal (Later Release)

1. Remove top-level shim modules only after deprecation window.
2. Remove compatibility tests for old imports and replace with hard-fail migration tests.
3. Bump version according to compatibility policy.

## Commit Plan (Recommended)

1. `chore(layout): add api/core/adapters/observability package scaffolding`
2. `refactor(adapters): move protocol module with compatibility shim`
3. `refactor(observability): move logging module with compatibility shim`
4. `refactor(core): move diagnostics/engine/invariants/reconcile`
5. `refactor(core): move reducers/broadcaster/bootstrap/resync`
6. `refactor(api): move state/config/snapshot/changes/errors/health/waiters`
7. `refactor(api): move selectors package`
8. `refactor(api): canonicalize __init__ import surface`
9. `test(architecture): enforce package dependency directions`
10. `docs(layout): publish module layout and migration guide`

## Quality Gate for Every Commit

- `devenv shell -- ruff check .`
- `devenv shell -- ruff format --check .`
- `devenv shell -- ty check .` (if import paths/types changed)
- `devenv shell -- pytest -q` (or targeted tests for narrow steps)

## Risk and Mitigation

1. Circular imports after move.
- Mitigation: move leaf modules first, keep shims thin, run tests per batch.

2. Hidden import consumers breaking.
- Mitigation: retain top-level shims and add compatibility import tests.

3. Large diffs becoming hard to review.
- Mitigation: one architectural slice per commit with explicit scope.

## Completion Criteria

- New directory architecture is in place and used internally.
- Public API remains stable.
- Compatibility shims exist with documented deprecation timeline.
- Quality gates pass.
- Documentation clearly describes old/new paths and migration sequence.
