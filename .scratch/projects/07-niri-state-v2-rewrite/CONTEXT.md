# CONTEXT

Working branch: `v2-rewrite`

Step 3 complete:
- `run_bootstrap()` now starts event buffering before queries, replays buffered events into engine state, then freezes revision `1`
- test seams for fake bundle/client/runtime were added in `tests/conftest.py` and `tests/factories/bundle.py`
- integration tests now validate bootstrap replay and runtime mutation loop revision advancement

Next:
- Step 4: harden `refresh()`/resync lifecycle contract (atomic bundle replacement, carry-forward diagnostics counters, close ordering on failure)
- then Step 5: finish remaining integration/replay coverage and remove legacy architecture paths
