# CONTEXT

Working branch: `v2-rewrite`

Step 4 complete:
- `refresh()` now accepts cause (`REFRESH` vs `RESYNC`) and preserves resync counters
- refresh flow now uses a fresh bundle bootstrap attempt, restores old state on failure, and keeps restart sequencing explicit
- desync diagnostic callsite fixed (`reason=`)
- integration tests for refresh, auto-resync, and close lifecycle are implemented and passing

Step 5 implementation complete:
- replay placeholder replaced by a real convergence test in `tests/replay/test_replay_traces.py`
- refresh integration test now asserts revision advancement and non-decreasing diagnostics resync counters
- v1 legacy `_core`/`_runtime` source paths and old test trees were removed by the user as directed

Remaining:
- run full repo Python quality gates (`ruff check`, `ruff format --check`, `ty check`, `pytest -q`)
- commit and push final step changes
