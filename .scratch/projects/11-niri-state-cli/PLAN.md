# PLAN

1. Define CLI scope and UX
- Specify command shape, default behavior, and output contract for continuous streaming.
- Acceptance: clear command examples and option list documented.

2. Add CLI module and entrypoint
- Implement a dedicated CLI module under `src/niri_state/`.
- Register console script in `pyproject.toml`.
- Acceptance: command can be invoked in dev environment and package install context.

3. Implement stream loop and shutdown handling
- Wire `NiriState.open(...)` + `subscribe()` into an interrupt-safe loop.
- Ensure graceful close on Ctrl+C and task cancellation.
- Acceptance: long-running stream starts, prints updates, exits cleanly.

4. Add output modes
- Provide at least JSON-lines output for machine use and concise text output for humans.
- Acceptance: stable per-line schema in JSON mode and readable default text mode.

5. Add configuration flags
- Add minimal high-value flags (format, include-initial snapshot, flush behavior, optional field filtering).
- Acceptance: flags are validated and reflected in behavior.

6. Testing
- Add focused tests for argument parsing, formatter output, and loop/publication handling.
- Acceptance: targeted tests pass and cover happy path + interruption/close behavior.

7. Documentation
- Update `README.md` with CLI quickstart and examples for continuous pass-through usage.
- Acceptance: user can run one documented command and immediately see streaming output.

8. Quality gate
- Run required lint/format/type/test commands before finalization.
- Acceptance: all required checks pass.
