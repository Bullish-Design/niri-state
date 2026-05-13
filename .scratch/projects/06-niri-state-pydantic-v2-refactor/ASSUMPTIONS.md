# ASSUMPTIONS

## Project Context

- niri-state is a Python library for deriving and querying compositor state for the Niri Wayland compositor
- It depends on niri-pypc as a lower-level protocol client
- niri-pypc was recently refactored to use pydantic v2+ patterns more effectively
- niri-state needs to be refactored to align with these new patterns

## Key Patterns from niri-pypc Refactor

1. **ProtocolModel Base Class**: Uses `ConfigDict(frozen=True, extra="forbid", strict=False, populate_by_name=True)`
2. **StrEnum**: Uses `StrEnum` from Python's stdlib for string enumerations
3. **Error Metadata**: All errors include `operation`, `retryable`, `cause` fields
4. **ExternallyTaggedEnum**: Uses RootModel pattern for enum types
5. **ProtocolVariant**: Uses class variables for wire name and variant kind

## Technical Constraints

- Maintain frozen=True for immutable snapshots
- Preserve extra="forbid" to catch unexpected fields
- Keep backward compatibility with existing API
- Ensure all tests pass after refactoring

## Scope

This is a library-internal refactoring - no public API changes. The goal is to:
- Use more idiomatic pydantic v2+ patterns
- Align with niri-pypc's approach
- Enable better type checking and IDE support