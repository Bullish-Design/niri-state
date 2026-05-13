# CONTEXT

## Current focus

Align `REFINED_V2_REWRITE_CODE_SKELETON.md` with `Refined_Rewrite_Patch_Updates.md` so the refined skeleton is the canonical final skeleton.

## What was done in this session

- Updated package tree to include missing seams and test scaffolding paths:
  - `src/niri_state/_version.py`
  - `tests/conftest.py`
  - `tests/factories/events.py`
  - `tests/factories/bundle.py`
  - `tests/replay/traces/`
- Updated protocol export surface to include generated helper types used by reducers/factories:
  - `Timestamp`, `WindowLayout`, `LogicalOutput`, `Mode`
- Updated `WaitTimeoutError` skeleton to inherit `TimeoutError`.
- Added `resync_changeset()` in `changes.py` skeleton.
- Updated runtime skeleton snippets for:
  - resync coordinator explicit `start()` lifecycle
  - `snapshot` property style
  - subscribe-first-current semantics
  - private runtime seams (`_install_bootstrap_outcome`, `_start_mutation_loop`, `_stop_mutation_loop`)
  - `_mark_desynced()` using `with_desync(...)`
  - refresh flow scaffolding to stop loop and replace bundle
- Updated waiter protocol to use `snapshot` property shape.
- Replaced the prior “cleanup pass” section with a mandatory implementation-contract appendix that codifies:
  - API compatibility decisions
  - reducer/event field contracts
  - bootstrap buffering requirement
  - refresh/resync lifecycle contract
  - reconcile/invariant/test coverage expectations
  - deterministic ordering guarantees

## Remaining work

- Some deeper per-function skeleton code blocks (especially reducers/reconcile/invariants/bootstrap internals) still need full line-by-line replacement during implementation.
- If requested, next step is to do a second pass that rewrites those specific code blocks directly in the skeleton file.
