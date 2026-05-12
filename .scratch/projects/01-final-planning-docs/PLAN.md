# PLAN

**NO SUBAGENTS RULE:** This project must be executed directly without subagents.

## Objective
Create final planning artifacts that consolidate the brainstorming concept/spec/guides/misalignment analysis and actual `niri-pypc` dependency behavior into corrected final docs for `niri-state`.

## Steps
1. Read and extract key contracts from brainstorming docs.
2. Read and extract runtime and type contracts from `.context/niri-pypc`.
3. Reconcile conflicts and freeze architectural boundaries.
4. Write `CONCEPT.md` in this project directory as the final concept baseline.
5. Write comprehensive `SPEC.md` in this project directory as the final implementation contract.
6. Update project tracking files.

## Acceptance Criteria
- `CONCEPT.md` clearly defines scope, goals, non-goals, boundaries, and behavior guarantees.
- `SPEC.md` is comprehensive and aligned to actual attached `niri-pypc` implementation and tests.
- Misalignments from prior docs are explicitly corrected in final artifacts.

**NO SUBAGENTS RULE (REPEATED):** All work in this project is completed directly with no subagent usage.
