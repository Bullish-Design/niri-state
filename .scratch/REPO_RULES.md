# REPO RULES — niri-state

## ABSOLUTE RULES — READ FIRST

1. **NO SUBAGENTS** — NEVER use the Task tool. Do ALL work directly.
2. **KEEP TRACKING CURRENT** — Maintain `.scratch/projects/<num>-<name>/` files while working.

---

Repo-specific standards and conventions. Loaded after `CRITICAL_RULES.md`.

## Project Scope

This repository builds `niri-state`, a Python library for deriving and querying compositor state for Niri.

Current priority:
- keep package/tooling setup coherent and reproducible
- enforce linting with Ruff and type checking with Ty
- keep config/docs aligned with `niri-state` naming and paths

## Environment and Tooling (MANDATORY)

Use `devenv shell --` for commands that execute project code or tooling.
You do not need it for read-only inspection commands (`ls`, `cat`, `rg`, `git show`, etc.).

Before the first test run in every session:
```bash
devenv shell -- uv sync --extra dev
```

Never use `uv pip install` in this repo.

Preferred quality commands:
```bash
devenv shell -- ruff check .
devenv shell -- ruff check --fix .
devenv shell -- ruff format .
devenv shell -- ruff format --check .
devenv shell -- ty check .
devenv shell -- pytest -q
```

## Architecture Rules

- Keep `niri-state` focused on snapshot models, reducers, selectors, and wait/observe APIs.
- Treat `niri-pypc` as the lower-level dependency for typed protocol/runtime concerns.
- Preserve deterministic reduction behavior and explicit state-health transitions.
- Avoid leaking transport concerns into public state APIs.

## Testing Expectations

- Add or update tests with every behavior change.
- Prioritize reducer, selector, snapshot, and wait/observe behavior tests.
- Include integration coverage for bootstrap + event-application flows where feasible.

## Key Reference Files

| Document | Path |
|----------|------|
| Concept review | `.scratch/projects/00-niri-state-brainstorming/NIRI_STATE_CONCEPT.md` |
| Agent operating instructions | `AGENTS.md` |
