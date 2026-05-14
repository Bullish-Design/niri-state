# CONTEXT

Task completed: produced a detailed remaining-refactor work document based on the deep review + current codebase state.

Output file:
- `.scratch/projects/08-v2-refactor/REMAINING_REFACTORING_WORK.md`

Key result:
- The document distinguishes already completed deep-review work from still-open work.
- Remaining work is prioritized into P0/P1/P2 with concrete acceptance criteria and execution order.

Notable completed items already in code (excluded from remaining list):
- `connect()` cleanup on bootstrap failure.
- `refresh()` failure recovery and refresh-cause fix.
- `NiriState.open(...)` classmethod.
- Bootstrap schema metadata population.
- Bootstrap desync marker handling.
- `RESYNCING` transition usage during refresh.
