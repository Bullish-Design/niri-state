# ASSUMPTIONS

- Public imports from `niri_state` must remain stable during migration.
- Internal module moves are acceptable if compatibility shims are present.
- Refactor should be split into small, verifiable commits.
- Lint/type/test gates must pass at each migration phase.
