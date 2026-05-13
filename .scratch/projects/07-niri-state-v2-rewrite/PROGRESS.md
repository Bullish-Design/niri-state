# PROGRESS

## Task: Full rewrite to v2 architecture aligned to updated niri-pypc

### Completed
- [x] Read rewrite skeleton and project rules
- [x] Step 1: Landed v2 scaffolding files from skeleton across `src/niri_state` and `tests/`
- [x] Step 1: Aligned protocol surface and typed factories to generated `niri_pypc` types
- [x] Step 1: Added missing typed factory helpers (`make_timestamp`, `make_window_layout`, `make_mode`, `make_logical_output`)
- [x] Step 1: Added event and fake bundle factory scaffolding for upcoming reducer/runtime/integration tests

### Pending
- [ ] Step 2: Reducer field semantics + reconcile/invariant completion
- [ ] Step 3: Bootstrap buffering and store lifecycle seam completion
- [ ] Step 4: Refresh/resync safety path + diagnostics carry-forward behavior
- [ ] Step 5: Integration/replay coverage completion and final cleanup
