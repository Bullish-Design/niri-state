# PROGRESS

## Task: Full rewrite to v2 architecture aligned to updated niri-pypc

### Completed
- [x] Read rewrite skeleton and project rules
- [x] Step 1: Landed v2 scaffolding files from skeleton + typed factory baseline
- [x] Step 2: Corrected reducer/reconcile/invariant contracts and tests
- [x] Step 3: Implemented bootstrap query-phase event buffering/replay before publishing revision `1`
- [x] Step 3: Added runtime seam fixtures (`FakeBundle`, `FakeClient`, test fixtures) and integration tests for bootstrap replay + mutation loop

### Pending
- [ ] Step 4: Refresh/resync safety path + diagnostics carry-forward behavior
- [ ] Step 5: Integration/replay coverage completion and final cleanup
