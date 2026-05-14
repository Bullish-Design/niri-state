# Compatibility Shims - REMOVED

## Status: COMPLETE

All 25 compatibility shims have been removed from the `niri_state` package.

## Removed Shims

The following shim files were deleted:

| File | New Location |
|------|--------------|
| `niri_state/store.py` | `niri_state.api.state` |
| `niri_state/selectors/__init__.py` | `niri_state.api.selectors` |
| `niri_state/selectors/workspaces.py` | `niri_state.api.selectors.workspaces` |
| `niri_state/selectors/windows.py` | `niri_state.api.selectors.windows` |
| `niri_state/selectors/overview.py` | `niri_state.api.selectors.overview` |
| `niri_state/selectors/outputs.py` | `niri_state.api.selectors.outputs` |
| `niri_state/selectors/keyboard.py` | `niri_state.api.selectors.keyboard` |
| `niri_state/selectors/focus.py` | `niri_state.api.selectors.focus` |
| `niri_state/selectors/aggregates.py` | `niri_state.api.selectors.aggregates` |
| `niri_state/health.py` | `niri_state.api.health` |
| `niri_state/waiters.py` | `niri_state.api.waiters` |
| `niri_state/errors.py` | `niri_state.api.errors` |
| `niri_state/changes.py` | `niri_state.api.changes` |
| `niri_state/snapshot.py` | `niri_state.api.snapshot` |
| `niri_state/config.py` | `niri_state.api.config` |
| `niri_state/resync.py` | `niri_state.core.resync` |
| `niri_state/bootstrap.py` | `niri_state.core.bootstrap` |
| `niri_state/broadcaster.py` | `niri_state.core.broadcaster` |
| `niri_state/reducers.py` | `niri_state.core.reducers` |
| `niri_state/reconcile.py` | `niri_state.core.reconcile` |
| `niri_state/invariants.py` | `niri_state.core.invariants` |
| `niri_state/diagnostics.py` | `niri_state.core.diagnostics` |
| `niri_state/engine_state.py` | `niri_state.core.engine_state` |
| `niri_state/logging.py` | `niri_state.observability.logging` |
| `niri_state/protocol.py` | `niri_state.adapters.protocol` |

## Migration Completed

All imports in the library (source and tests) have been updated to use the new canonical paths:
- Public API → `niri_state.api.*`
- Core internals → `niri_state.core.*`
- Observability → `niri_state.observability.*`
- Adapters → `niri_state.adapters.*`

## Verification

- All 44 tests pass
- Architecture test confirms no internal imports use shim paths
- Lint and format checks pass