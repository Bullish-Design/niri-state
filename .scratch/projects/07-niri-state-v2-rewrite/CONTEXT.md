# CONTEXT

The intro of `REFINED_V2_REWRITE_CODE_SKELETON.md` was upgraded to serve as a complete pre-implementation briefing.

It now explicitly covers:
- rewrite scope boundaries
- API compatibility decisions to preserve
- bootstrap/refresh/resync runtime correctness contracts
- determinism + invariants expectations
- unit/integration/replay testing strategy
- ordered implementation sequence
- repo-specific quality gates (`devenv shell -- ruff/ty/pytest`)

Next step is to start implementation using the skeleton sections in order.
