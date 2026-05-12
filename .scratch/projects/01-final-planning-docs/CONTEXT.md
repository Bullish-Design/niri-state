# CONTEXT

Final state:
- Project `01-final-planning-docs` now contains:
  - `CONCEPT.md` (final architecture baseline),
  - `SPEC.md` (comprehensive implementation contract),
  - `CONCEPT_RETHINK.md` (greenfield redesign brainstorming document).

Latest work completed:
- Wrote `CONCEPT_RETHINK.md` with detailed redesign proposals for:
  - core/runtime split,
  - event-sourced-first architecture,
  - typed lifecycle FSM,
  - freshness type contracts,
  - ingress normalization boundary,
  - incremental selector/index engine,
  - declarative condition/subscription runtime,
  - checkpoint/recovery model,
  - unknown event evolution strategies,
  - test architecture as product feature,
  - greenfield API direction,
  - phased v2 migration path.
- Each section includes examples plus pros/cons/implications/opportunities.

Inputs incorporated:
- Prior finalized concept/spec work in this directory.
- Earlier reconciled constraints from `00` brainstorming docs and `.context/niri-pypc` dependency study.

Outcome:
- `CONCEPT_RETHINK.md` provides a structured brainstorming base for a no-compatibility redesign discussion.
