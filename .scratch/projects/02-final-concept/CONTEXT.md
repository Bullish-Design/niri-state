# CONTEXT

Project `02-final-concept` implementation of `niri-state` is ~60% complete.

## What's Done

Steps 0-7 of the implementation guide are complete:
- Step 0: Package structure, stub files, pyproject.toml (DONE)
- Step 1: Config (policy enums, NiriStateConfig frozen dataclass, normalize_config) and errors (full hierarchy) (DONE)
- Step 2: Core immutable models — types, entities, health, snapshot (with MappingProxyType), changes, draft, bootstrap_payload (DONE)
- Step 3: Lifecycle FSM with transition validation (DONE)
- Step 4: Snapshot builder (build_initial_draft from BootstrapPayload) (DONE)
- Step 5: Invariant engine (collect_invariant_violations, assert_invariants, 10 checks) (DONE)
- Step 6: Domain reducers — windows (7 events), workspaces (4 events), keyboard (2 events), overview (1 event) (DONE)
- Step 7: Root reducer with match/case dispatch, ReduceResult model, unknown event policy (STALE/FAIL/IGNORE) (DONE)

Core models, reducers, and invariants are all implemented and well-tested.

## What's Left

Steps 8-14 need full implementation:
- Step 8: Bootstrap pipeline in _runtime/bootstrap.py — connect, query, buffer events, replay, publish LIVE
- Step 9: Store + broadcaster — NiriState class, single-owner mutation loop, subscriber management, overflow policies
- Step 10: Wait/watch APIs in _runtime/waiters.py
- Step 11: Resync coordinator in _runtime/resync.py — manual and auto policies
- Step 12: Selector modules (outputs, workspaces, windows, focus, keyboard, overview, aggregates)
- Step 13: Integration tests and replay harness
- Step 14: API polish, public exports, packaging checks

All remaining steps require full implementation + tests + validation.

## Current Working Directory

All implementation lives in /home/andrew/Documents/Projects/niri-state/

## Session Plan

1. Sync dependencies first (uv sync --extra dev)
2. Implement Step 8: Bootstrap pipeline
3. Implement Step 9: Store and broadcaster
4. Implement Step 10: Wait/watch
5. Implement Step 11: Resync
6. Implement Step 12: Selectors
7. Implement Step 13: Integration tests
8. Final validation: all steps, full suite

After each step: commit + push, update PROGRESS.md.