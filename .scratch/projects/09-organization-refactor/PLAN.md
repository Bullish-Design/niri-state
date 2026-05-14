# PLAN

## Objective
Design and execute a compatibility-first architectural organization refactor for `niri_state` by introducing subdirectories and preserving stable public APIs.

## Steps
- [ ] Define module boundaries and dependency direction rules.
- [ ] Create new package directories and placeholders.
- [ ] Move low-risk modules first with shims.
- [ ] Move core orchestration modules with shims.
- [ ] Update imports, exports, and documentation.
- [ ] Validate via lint/type/tests and finalize deprecation/removal plan.

## Deliverable
A migrated package layout with backward-compatible shims and an explicit removal timeline.
