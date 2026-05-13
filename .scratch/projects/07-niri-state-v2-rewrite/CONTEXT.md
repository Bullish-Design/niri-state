# CONTEXT

Working branch: `v2-rewrite`

Step 4 complete:
- `refresh()` now accepts cause (`REFRESH` vs `RESYNC`) and preserves resync counters
- refresh flow now uses a fresh bundle bootstrap attempt, restores old state on failure, and keeps restart sequencing explicit
- desync diagnostic callsite fixed (`reason=`)
- integration tests for refresh, auto-resync, and close lifecycle are implemented and passing

Next final step:
- complete remaining replay/integration scaffolding and remove legacy `_core`/`_runtime` architecture paths
- run full repo Python quality gates (`ruff check`, `ruff format --check`, `ty check`, broader pytest) and ship final step commit
