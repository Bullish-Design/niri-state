# CONTEXT

The user approved proceeding with implementation and requested Typer for the CLI.

Implemented:
- Added Typer CLI module at `src/niri_state/cli.py`.
- Added `stream` command with options:
  - `--format` (`text`/`json`)
  - `--include-initial/--no-include-initial`
  - `--show-changes/--no-show-changes`
  - `--flush/--no-flush`
  - `--max-events`
- Added packaging entrypoint in `pyproject.toml`:
  - `[project.scripts] niri-state = "niri_state.cli:main"`
- Added dependency `typer>=0.12`.
- Added CLI tests in `tests/unit/test_cli.py`.
- Updated `README.md` with CLI usage.

Validation run:
- `devenv shell -- uv sync --extra dev`
- `devenv shell -- ruff check .`
- `devenv shell -- ruff format --check .`
- `devenv shell -- ty check .` (non-blocking warnings in pre-existing files)
- `devenv shell -- pytest -q tests/unit/test_cli.py`

Notes:
- A prior parallel pytest execution produced a coverage tempfile race; sequential run passed.
- `ty check .` reports existing warnings unrelated to this change set.

Likely next step:
- Optional manual smoke run against live Niri (`devenv shell -- niri-state stream`).
