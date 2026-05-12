# CONTEXT

Implemented nearly all remediation items from `.scratch/projects/04-final-implementation-review/FINAL_IMPLEMENTATION_REVIEW.md`.

Completed implementation changes:
- Runtime/bootstrap contract updates to support direct payload responses (with compatibility for wrapped responses).
- Dedicated runtime broadcaster implemented and wired into store publication/subscription.
- Store lifecycle and mutation loop fixes: draft handling, refresh loop restart, close transition ordering, broadcaster shutdown.
- Wait API timeout enforcement and wait health policy gating (`LIVE_ONLY` vs `ALLOW_STALE`).
- Resync coordinator stale transition wiring and AUTO retry/terminal behavior.
- Reducer correctness fixes for replace-all and window upsert changed detection.
- Selector typing hardening and top-level selector exports.
- Added `tests/runtime/test_broadcaster.py` and expanded waiter/resync tests.

Validation results (updated May 12, 2026):
- `devenv shell -- ty check .` passes with zero diagnostics.
- `devenv shell -- ruff check .` passes.
- `devenv shell -- ruff format --check .` passes.

Typing remediation completed:
- Added `tests/_typing_helpers.py` with a typed `make_minimal_snapshot()` helper.
- Replaced dynamic `NiriSnapshot(**defaults)` test patterns with typed helper usage.
- Replaced several dynamic `Model(**dict)` construction paths in integration tests with `model_validate(...)`.
- Fixed window layout typing in tests by using `WindowLayout.model_validate(...)`.
- Removed `TemporaryDirectory()` usage that triggered strict overload diagnostics in `ty` and replaced with `mkdtemp()` + cleanup.
