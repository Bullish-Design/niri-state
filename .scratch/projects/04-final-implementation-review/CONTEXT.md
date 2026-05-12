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

Validation results:
- `devenv shell -- ruff check .` passes.
- `devenv shell -- ruff format --check .` passes.
- `devenv shell -- pytest -q` passes.
- `devenv shell -- ty check .` still fails with 43 diagnostics, primarily pre-existing test typing debt (constructor/dynamic-dict typing and strict overload issues across many test modules).

Next step if required:
- Dedicated follow-up project to normalize test typing helpers/models and eliminate remaining `ty` diagnostics.
