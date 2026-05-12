# Context

Implemented deep-research report fixes in `niri-state`:

- Runtime correctness:
  - `Broadcaster.close()` now wakes blocked subscribers and supports closed-state subscription behavior.
  - `NiriState.connect()` now publishes initial snapshot.
  - `NiriState.subscribe()` now yields current snapshot immediately.
  - `NiriState.refresh()` now cancels old mutation loop before replacing state, preserves monotonic revisions, and broadcasts rewritten bootstrap changeset with monotonic revision.
  - `HealthState` transition graph now allows `LIVE -> RESYNCING`.
  - `run_bootstrap()` now fails when event stream fails during bootstrap and preserves stale health set during replay.
  - `NiriState` now wires in `ResyncCoordinator` and uses it on event stream errors (activates AUTO policy behavior).
  - Added `NiriState.start()` classmethod for public bootstrap/start path.

- Typing/API/packaging:
  - Fixed nullable typing in `selectors.aggregates.FocusedContext`.
  - Pinned dependency range to `niri-pypc>=0.2.0,<0.3.0`.
  - Added `project.urls`, `LICENSE`, and expanded README usage/lifecycle docs.

- Tests updated/added:
  - health transition legality for `LIVE -> RESYNCING`
  - broadcaster close wakes waiting subscriber
  - store subscription initial snapshot behavior
  - store refresh monotonic revision
  - store start() bootstraps and connects
  - bootstrap stream failure during bootstrap raises
  - bootstrap preserves stale health from replay

Validation completed successfully:
- `devenv shell -- uv sync --extra dev`
- `devenv shell -- ruff check .`
- `devenv shell -- ruff format --check .`
- `devenv shell -- ty check .`
- `devenv shell -- pytest -q`
