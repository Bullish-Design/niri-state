# NIRI_STATE_CLI_PLAN

## 1. Goal

Add a first-party `niri-state` CLI that can continuously emit compositor-derived updates with zero custom Python scripting.

Primary success criterion:
- A user can run one command and keep receiving line-delimited updates until they interrupt the process.

## 2. User Stories

1. As a developer, I want a single command that streams state updates continuously so I can inspect compositor behavior in real time.
2. As a tool author, I want JSON-lines output so I can pipe updates into `jq`, log processors, or other automation.
3. As an operator, I want graceful shutdown on Ctrl+C so the process exits predictably without hanging.
4. As a debugger, I want optional inclusion/exclusion of initial snapshot emission and change metadata.

## 3. CLI Surface (Proposed)

Command:
- `niri-state stream [options]`

Initial option set:
- `--format {text,json}` (default: `text`)
- `--include-initial / --no-include-initial` (default: include initial)
- `--show-changes / --no-show-changes` (default: show in text mode)
- `--flush / --no-flush` (default: flush enabled for real-time pipes)
- `--max-events <int>` (optional, mainly for testing/debug sessions)

Future-safe but out-of-scope for first pass:
- Predicate filtering on fields
- Selector-targeted subcommands
- File sink rotation and buffering policies

## 4. Output Contracts

### Text mode (`--format text`)

One publication per line, compact and stable:
- `rev=<int> health=<state> changes=<summary>`

Design points:
- Keep output readable in terminal without wrapping where possible.
- Avoid volatile ordering of fields.

### JSON mode (`--format json`)

Emit one JSON object per line (JSONL):
- Required keys: `revision`, `health`, `changes`, `timestamp`
- Optional keys (future): selected snapshot fragments

Design points:
- Machine-parseable, no multi-line pretty printing.
- Consistent schema across events.

## 5. Architecture and File Changes

### New module

- `src/niri_state/cli.py`

Responsibilities:
- Parse args (`argparse` preferred to avoid extra deps)
- Dispatch to `stream` command
- Manage async runtime boundaries (`asyncio.run`)
- Format and write publications
- Handle interrupts and controlled shutdown

### Packaging changes

- `pyproject.toml`

Add console script entry:
- `[project.scripts]`
- `niri-state = "niri_state.cli:main"`

### Optional internal helper module (if complexity grows)

- `src/niri_state/cli_formatters.py`

Responsibilities:
- Keep formatting and schema logic testable and isolated.

## 6. Streaming Loop Design

Flow:
1. Parse CLI args.
2. Build `NiriStateConfig()` (initially defaults, extensible later).
3. `state = await NiriState.open(config)`.
4. Iterate `async for published in state.subscribe():`
5. Transform published event -> output record/text.
6. Write line with optional flush.
7. Respect `--max-events` and exit when reached.
8. On `KeyboardInterrupt` or cancellation, close state and exit with code 0.
9. On unrecoverable runtime errors, print concise error to stderr and exit non-zero.

Error-handling goals:
- No dangling tasks.
- Idempotent close path.
- Predictable exit codes for scripting.

## 7. Testing Strategy

Test layers:

1. Unit tests: argument parsing
- Valid options and defaults.
- Invalid combinations fail fast with usage output.

2. Unit tests: formatter behavior
- Text mode line shape.
- JSON mode key presence and value normalization.

3. Async behavior tests: streaming runner
- Emits lines for mocked publications.
- Honors `--max-events`.
- Closes state on interruption/cancellation.

4. Integration-style test (lightweight)
- Invoke CLI entrypoint with mocked state provider.
- Assert stable stdout/stderr and exit codes.

Candidate files:
- `tests/test_cli_args.py`
- `tests/test_cli_formatters.py`
- `tests/test_cli_stream.py`

## 8. Documentation Updates

Update `README.md` with a `CLI` section:
- Install/run note using `devenv shell -- niri-state stream`
- `text` and `json` examples
- Pipe example with `jq`
- Ctrl+C shutdown behavior

Example snippets to include:
- `devenv shell -- niri-state stream`
- `devenv shell -- niri-state stream --format json | jq .`

## 9. Quality Gates and Verification

Required commands for Python edits:
1. `devenv shell -- uv sync --extra dev` (before first test run in session)
2. `devenv shell -- ruff check .`
3. `devenv shell -- ruff format --check .`
4. `devenv shell -- ty check .` (if interfaces/types are touched, expected here)
5. Targeted tests for new CLI modules

Done criteria:
- CLI runs and streams continuously.
- JSON mode is valid JSONL and stable.
- Graceful interrupt confirmed.
- Docs updated with exact run commands.
- Quality commands pass.

## 10. Rollout Steps

1. Implement minimal `stream` command with text output only.
2. Add JSON mode and tests.
3. Register console script.
4. Update README.
5. Run quality gates.
6. Final manual smoke run:
   - `devenv shell -- niri-state stream`
   - verify continuous updates and clean Ctrl+C exit.

## 11. Risks and Mitigations

Risk: API event objects may be verbose or unstable for direct serialization.
- Mitigation: explicit JSON schema mapping in formatter layer.

Risk: Cancellation/shutdown edge cases leave dangling async tasks.
- Mitigation: centralize close logic with `try/finally` and interruption tests.

Risk: User expectation mismatch between “raw niri output” and reduced state publications.
- Mitigation: document clearly that CLI emits `niri-state` publications derived from Niri events.

## 12. Acceptance Checklist

- [ ] `niri-state stream` continuously prints updates.
- [ ] `--format json` emits one valid JSON object per line.
- [ ] Interrupt (`Ctrl+C`) exits cleanly and closes state.
- [ ] Console script registered in `pyproject.toml`.
- [ ] Tests added for args, formatting, and stream loop.
- [ ] README contains runnable CLI examples.
- [ ] Required lint/format/type/test checks pass.
