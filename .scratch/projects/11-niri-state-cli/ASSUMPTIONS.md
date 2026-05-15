# ASSUMPTIONS

- The goal is to add a first-party CLI to this repository, not an external helper script.
- Primary user need is a continuous "pass-through" mode that streams Niri-derived state updates without custom app code.
- CLI should be usable during development via `devenv shell -- ...` and after package install via a console script.
- Existing Python package architecture (`niri_state` API, snapshot/publish models, health transitions) should remain authoritative; CLI is a thin adapter.
- Initial CLI scope should prioritize reliability and clarity over broad feature surface.
- The repo’s quality gate (ruff, ty, targeted tests) applies to CLI additions.
