# PLAN: niri-state Pydantic v2+ Refactoring

## Objective

Refactor niri-state library to align with the updated niri-pypc patterns that now fully utilize pydantic v2+ functionality.

## Steps

1. [ ] Create detailed NIRI_STATE_REFACTORING_OVERVIEW.md with complete change analysis
2. [ ] Refactor `config.py` - Convert NiriStateConfig from dataclass to BaseModel
3. [ ] Refactor `bootstrap_payload.py` - Convert BootstrapPayload from dataclass to ProtocolModel
4. [ ] Refactor entity models - Add ProtocolModel base class pattern where beneficial
5. [ ] Refactor error classes - Add structured metadata fields following niri-pypc pattern
6. [ ] Run ruff and ty checks after each major change
7. [ ] Run test suite to verify refactoring doesn't break functionality

## Dependencies

- Requires understanding of niri-pypc patterns (completed)
- Requires understanding of niri-state current implementation (completed)

## Acceptance Criteria

- All niri-state models use consistent pydantic v2+ patterns
- Config uses BaseModel with proper ConfigDict instead of dataclass
- BootstrapPayload uses ProtocolModel pattern
- Error classes include structured metadata (operation, retryable, cause)
- All tests pass
- ruff and ty checks pass