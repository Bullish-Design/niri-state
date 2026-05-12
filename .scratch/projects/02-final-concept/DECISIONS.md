# DECISIONS

1. Build the final concept as a full rewrite rather than incremental edits to avoid carrying legacy structure drift.
2. Keep architecture contract clarity while adopting pragmatic recommendations from `FINAL_CONCEPT_ANALYSIS.md` (single package with internal core/runtime boundary, no event-sourced log, explicit FSM, predicate wait/watch API).
3. Rewrite `SPEC` as a new final implementation specification to exactly mirror `FINAL_CONCEPT.md` boundaries and terminology, replacing legacy layout/contracts that no longer match the finalized concept.
