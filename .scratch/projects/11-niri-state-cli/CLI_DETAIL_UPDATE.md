# CLI_DETAIL_UPDATE

## Objective

Expand `niri-state` CLI output detail beyond high-level `domains` metadata so users can inspect richer state in real time while preserving a lightweight default mode.

Primary user problem:
- Current JSON output is concise (`revision`, `health`, `cause`, `domains`, `timestamp`) but insufficient for deep debugging and live introspection.

Primary outcome:
- Add explicit detail-level controls so users can choose between low-overhead summaries and rich state payloads.

---

## Current State (As of 2026-05-15)

Current command:
- `niri-state stream --format json`

Current JSON payload keys:
- `revision`
- `health`
- `cause`
- `domains`
- `timestamp`

Current constraints:
- No structured focus info.
- No changed-object payloads.
- No full snapshot serialization in stream output.

---

## Proposed UX

## New CLI option

Add a new option to `stream`:
- `--detail [summary|focus|delta|snapshot]`

Default:
- `summary`

Behavior by format:
- In `--format json`, `--detail` controls emitted object depth.
- In `--format text`, keep concise output by default; optionally append detail-specific suffixes only where practical.

### Detail levels

1. `summary`
- Existing behavior (backward-compatible schema).
- Best for low-bandwidth streaming and simple monitoring.

2. `focus`
- Include focused entities and other high-signal fields.
- Intended for interactive workflows where users primarily care about what is active right now.

3. `delta`
- Include domain-scoped changed data derived from each event publication.
- Provides medium payload size with event-local detail.

4. `snapshot`
- Include a full snapshot projection every event.
- Maximum observability and easiest jq exploration.

---

## JSON Schema Additions (Per Detail Level)

Base keys (always present):
- `revision: int`
- `health: str`
- `cause: str`
- `domains: list[str]`
- `timestamp: str` (ISO-8601)

### `summary`
- Base keys only.

### `focus`
Add keys:
- `focused_window_id: int | null`
- `focused_workspace_id: int | null`
- `focused_output_name: str | null`
- `keyboard_current_name: str | null`
- `overview_open: bool`

### `delta`
Add key:
- `delta: object`

`delta` object shape (domain-gated, keys optional):
- `outputs`: map of output name -> projected output fields
- `workspaces`: map of workspace id -> projected workspace fields
- `windows`: map of window id -> projected window fields
- `focus`: focus-specific projection
- `keyboard`: keyboard projection
- `overview`: overview projection
- `health`: health transition metadata (optional)
- `diagnostics`: diagnostics projection (optional)

Initial simplification recommendation:
- Implement `delta` as a filtered projection from the current snapshot based on `domains`.
- Do not attempt true previous-vs-current structural diff in first pass.

### `snapshot`
Add key:
- `snapshot: object`

`snapshot` projection should include:
- `revision`
- `health`
- `focused_window_id`
- `focused_workspace_id`
- `focused_output_name`
- `keyboard_layouts` (current index and names)
- `overview`
- `outputs`
- `workspaces`
- `windows`
- `diagnostics` (as a safe, serializable projection)
- `compatibility` (serializable projection)

---

## Serialization Strategy

Problem:
- Internal snapshot object contains rich types and mappings; not all objects are guaranteed JSON-serializable as-is.

Strategy:
1. Introduce explicit projection helpers (no blind `model_dump()` on arbitrary nested objects).
2. For each domain model, expose JSON-safe dict projection functions.
3. Keep stable key ordering and predictable field names.
4. Ensure nullability is explicit for missing focus values.

Proposed helper structure:
- `src/niri_state/cli.py` (small helpers if scope remains small)
- or split to `src/niri_state/cli_formatters.py` when complexity grows

Projection helper set (proposed):
- `_base_payload(published)`
- `_focus_payload(snapshot)`
- `_delta_payload(published)`
- `_snapshot_payload(snapshot)`
- `_project_output(output)`
- `_project_workspace(workspace)`
- `_project_window(window)`
- `_project_diagnostics(diagnostics)`
- `_project_compatibility(compatibility)`

---

## Backward Compatibility

Compatibility objective:
- Existing command without `--detail` behaves exactly as current `summary` mode.

Guarantees:
- Default remains concise.
- Existing scripts reading current keys continue to work.
- Additional keys are opt-in through `--detail`.

---

## Performance Considerations

Cost profile by mode:
- `summary`: minimal CPU + minimal I/O
- `focus`: minimal-to-low CPU + low I/O
- `delta`: medium CPU + medium I/O (projection + larger payload)
- `snapshot`: highest CPU/I/O due to full object projection every publication

Mitigations:
- Keep `summary` default.
- Retain `--flush` control.
- Encourage users to combine with `jq` select/filter to reduce downstream load.
- Document that `snapshot` is for debugging and may be verbose.

---

## CLI Help and Examples

Add examples to README and `--help` docs:

1. Summary (default)
```bash
niri-state stream --format json | jq .
```

2. Focus detail
```bash
niri-state stream --format json --detail focus | jq '{revision, focused_window_id, focused_workspace_id, focused_output_name}'
```

3. Snapshot detail
```bash
niri-state stream --format json --detail snapshot | jq '.snapshot.windows'
```

4. Delta detail
```bash
niri-state stream --format json --detail delta | jq '.delta'
```

---

## Implementation Plan

1. Extend CLI option parsing
- Add `--detail` enum-like option validation.
- Allowed values: `summary`, `focus`, `delta`, `snapshot`.

2. Refactor formatter pipeline
- Keep existing base formatter path.
- Introduce detail-specific enrichment functions.

3. Implement `focus` mode
- Use direct snapshot scalar properties.
- Minimal risk and quick value.

4. Implement `snapshot` mode
- Add robust projections for nested structures.
- Validate JSON serialization on representative events.

5. Implement `delta` mode
- Domain-filtered projection from current snapshot.
- Avoid full diff algorithm in v1.

6. Preserve text mode ergonomics
- Maintain current concise output.
- Optionally append `focus` details in text mode only for `--detail focus`.

7. Update docs
- README section with detail-level examples.

8. Add tests
- Unit tests for each detail mode output shape.
- Validate keys and key types.
- Validate detail gating and backward compatibility.

---

## Test Plan

### Unit tests

1. `summary` mode JSON
- Assert existing key set.
- Assert no extra detail keys.

2. `focus` mode JSON
- Assert focus keys exist and are typed correctly.

3. `delta` mode JSON
- Assert `delta` key exists.
- Assert only domain-appropriate subkeys appear for given `domains`.

4. `snapshot` mode JSON
- Assert `snapshot` key exists.
- Assert required nested sections exist.
- Assert payload serializes and `json.loads` round-trips.

5. Invalid detail value
- CLI returns exit code 2 and help usage message.

6. Backward compatibility
- No `--detail` remains equivalent to `--detail summary`.

### Optional integration test

- Run stream loop with fake publications and verify output mode-specific payload growth.

---

## Risks and Mitigations

Risk: Overly large JSON payload in `snapshot` mode
- Mitigation: keep opt-in, document usage, and preserve summary default.

Risk: Non-serializable nested types
- Mitigation: explicit projection helpers for each nested model.

Risk: `delta` semantics confusion (diff vs filtered projection)
- Mitigation: document `delta` as domain-filtered current-state projection in v1.

Risk: CLI complexity growth in one file
- Mitigation: move to `cli_formatters.py` when formatter logic exceeds reasonable size.

---

## Acceptance Criteria

- `niri-state stream --format json --detail summary` outputs current schema.
- `niri-state stream --format json --detail focus` includes focus-centric fields.
- `niri-state stream --format json --detail delta` includes `delta` object keyed by changed domains.
- `niri-state stream --format json --detail snapshot` includes full projected snapshot object.
- Existing behavior without `--detail` remains backward-compatible.
- README documents all detail levels with runnable examples.
- Tests cover all detail modes and invalid inputs.
- Repo quality checks pass for edited Python files.

---

## Recommended Phased Delivery

Phase 1 (fastest value):
- Ship `focus` + `snapshot`
- Keep `delta` behind follow-up if needed

Phase 2:
- Ship `delta` (domain-filtered projection)

Phase 3 (optional advanced):
- Add true structural diffs or domain-specific compact diff schema

---

## Operator Notes

When users ask for “more detail”:
- Recommend `--detail focus` first for readability.
- Use `--detail snapshot` for deep forensics.
- Use `--detail delta` to monitor only domain-related sections per event.

Expected practical workflow:
```bash
niri-state stream --format json --detail snapshot | jq '.snapshot | {focused_window_id, focused_workspace_id, windows}'
```
