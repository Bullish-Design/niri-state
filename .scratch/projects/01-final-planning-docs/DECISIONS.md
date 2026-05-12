# DECISIONS

## D-001: Dependency truth over prior draft text
- Decision: Final concept/spec align to actual attached `niri-pypc` implementation/tests when prior docs disagree.
- Why: `niri-state` is downstream and must encode real contracts, not aspirational ones.

## D-002: Preserve separate final concept and final spec artifacts
- Decision: Keep `CONCEPT.md` as architecture baseline and `SPEC.md` as implementation contract.
- Why: User requested comprehensive final spec after studying both planning docs and dependency code.

## D-003: Include corrected treatment of drifted event and payload contracts
- Decision: Final `SPEC.md` explicitly incorporates `ConfigLoadedEvent`, `WindowLayoutsChangedEvent`, `WindowFocusTimestampChangedEvent`, and true payload nullability for Overview/Version.
- Why: These were key misalignments and materially affect reducer and bootstrap correctness.

## D-004: Add a separate greenfield redesign concept artifact
- Decision: Create `CONCEPT_RETHINK.md` distinct from finalized concept/spec docs.
- Why: User requested explicit brainstorming unconstrained by backward compatibility; keeping it separate avoids mixing normative spec contracts with exploratory redesign direction.
