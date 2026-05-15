# CONTEXT

User requested richer CLI stream output detail after trying jq with minimal payload output.

Implemented in this step:
- Added `--detail` option to CLI stream command with levels:
  - `summary` (default)
  - `focus`
  - `delta`
  - `snapshot`
- Added explicit JSON projection helpers in `src/niri_state/cli.py`:
  - focus payload projection
  - domain-filtered delta projection
  - full snapshot projection
  - generic JSON-safe conversion helper
- Kept backward compatibility by preserving existing summary schema when `--detail` is not provided.
- Updated README with `--detail` usage examples.
- Expanded `tests/unit/test_cli.py` to cover:
  - summary/focus/delta/snapshot JSON payloads
  - invalid `--detail` value rejection
  - existing stream-loop behavior

Validation run:
- `devenv shell -- ruff check .`
- `devenv shell -- ruff format --check .`
- `devenv shell -- ty check .` (warnings in pre-existing files outside this change)
- `devenv shell -- pytest -q tests/unit/test_cli.py`

Notes:
- Ty warnings that remain are pre-existing and unrelated to this change set.

Likely next step:
- Manual runtime smoke check with live Niri and jq for each detail level.
