# PROGRESS

## Status
Completed

## Completed
- Created project directory and tracking template files.
- Drafted step-by-step implementation guide.
- Phase 0: Baseline quality checks passed.
- Phase 1: Created api/, core/, adapters/, observability/ package directories.
- Phase 2: Moved protocol.py to adapters/protocol.py, logging.py to observability/logging.py with shims.
- Phase 3: Moved core modules (diagnostics, engine_state, invariants, reconcile, reducers, broadcaster, bootstrap, resync) with shims.
- Phase 4: Moved API modules (state, config, snapshot, changes, errors, health, waiters, selectors) with shims.
- Phase 5: Canonicalized __init__ import surface to use new paths.
- Phase 6: Added architecture tests to enforce dependency directions.
- Phase 7: Documentation and deprecation notes in shims.

## New Structure
```
src/niri_state/
  __init__.py
  _version.py
  api/
    __init__.py
    state.py (was store.py)
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

## Deprecation
All moved modules have shims at their original locations with deprecation notes. Users should migrate to new import paths. Shim removal is scheduled for a future release.
