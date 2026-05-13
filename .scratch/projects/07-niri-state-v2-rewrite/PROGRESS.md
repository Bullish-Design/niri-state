# PROGRESS

## Task: Full rewrite to v2 architecture aligned to updated niri-pypc

### Completed
- [x] Read rewrite skeleton and project rules
- [x] Step 1: Landed v2 scaffolding files from skeleton + typed factory baseline
- [x] Step 2: Corrected reducer contracts (`urgent` fields, layout `changes`, workspace activation `focused` handling)
- [x] Step 2: Implemented reconcile passes for keyboard index tolerance and stale `active_window_id` cleanup
- [x] Step 2: Extended invariants and deterministic derived-index checks
- [x] Step 2: Added unit tests for reducer/reconcile/invariant/determinism contracts

### Pending
- [ ] Step 3: Bootstrap buffering and store lifecycle seam completion
- [ ] Step 4: Refresh/resync safety path + diagnostics carry-forward behavior
- [ ] Step 5: Integration/replay coverage completion and final cleanup
