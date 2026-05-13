# NIRI_STATE_REFACTORING_OVERVIEW

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Pydantic v2+ Patterns Used in niri-pypc](#2-pydantic-v2-patterns-used-in-niri-pypc)
3. [Current niri-state Analysis](#3-current-niri-state-analysis)
4. [Required Changes by File](#4-required-changes-by-file)
   - [4.1 config.py](#41-configpy)
   - [4.2 bootstrap_payload.py](#42-bootstrap_payloadpy)
   - [4.3 entities.py](#43-entitiespy)
   - [4.4 snapshot.py](#44-snapshotpy)
   - [4.5 changes.py](#45-changespy)
   - [4.6 errors.py](#46-errorspy)
   - [4.7 health.py](#47-healthpy)
5. [Pydantic v2+ Enhancements for niri-state](#5-pydantic-v2-enhancements-for-niri-state)
6. [Migration Priority and Order](#6-migration-priority-and-order)
7. [Testing Strategy](#7-testing-strategy)

---

## 1. Executive Summary

The niri-pypc library has been fully refactored to leverage pydantic v2+ functionality, introducing several key patterns that niri-state should adopt:

- **ProtocolModel base class** with consistent ConfigDict settings
- **StrEnum** for string enumerations (replacing enum.Enum)
- **Structured error metadata** with operation, retryable, and cause fields
- **RootModel-based ExternallyTaggedEnum** for externally-tagged variants
- **model_validator and model_serializer** for custom serialization logic

This document outlines all changes required to refactor niri-state to align with these patterns while maintaining backward compatibility.

---

## 2. Pydantic v2+ Patterns Used in niri-pypc

### 2.1 ProtocolModel Base Class

All generated protocol models inherit from a base class that sets consistent configuration:

```python
class ProtocolModel(BaseModel):
    """Base for all generated protocol models."""

    model_config = ConfigDict(
        frozen=True,
        strict=False,
        extra="forbid",
        populate_by_name=True,
    )
```

**Key observations:**
- `frozen=True`: Immutable instances (important for snapshots)
- `strict=False`: Allow coercion from JSON types (e.g., int to str enum)
- `extra="forbid"`: Catch unexpected fields early
- `populate_by_name=True`: Allow both field name and alias for deserialization

### 2.2 StrEnum Usage

String enumerations use Python's stdlib `StrEnum` instead of `pydantic.Constant` or `enum.Enum`:

```python
class ColumnDisplay(StrEnum):
    NORMAL = "Normal"
    TABBED = "Tabbed"
```

**Benefits:**
- Native type support in Python 3.11+
- Better serialization/deserialization
- Cleaner syntax

### 2.3 ProtocolVariant for Externally-Tagged Enums

Variants use class variables for metadata:

```python
class IndexLayoutSwitchTarget(ProtocolVariant):
    __niri_wire_name__ = "Index"
    __niri_variant_kind__ = "newtype"
    payload: int
```

### 2.4 ExternallyTaggedEnum via RootModel

Complex enum types use RootModel pattern with custom validators/serializers:

```python
class LayoutSwitchTarget(ExternallyTaggedEnum[LayoutSwitchTargetValue]):
    __niri_variants__ = (
        IndexLayoutSwitchTarget,
        NextLayoutSwitchTarget,
        PrevLayoutSwitchTarget,
    )
```

### 2.5 Structured Error Taxonomy

All errors include structured metadata:

```python
class NiriError(Exception):
    def __init__(
        self,
        message: str,
        *,
        operation: str | None = None,
        socket_path: str | None = None,
        retryable: bool = False,
        cause: Exception | None = None,
    ) -> None:
        self.operation = operation
        self.socket_path = socket_path
        self.retryable = retryable
        self.cause = cause
        super().__init__(message)
```

---

## 3. Current niri-state Analysis

### Files to Refactor

| File | Current Pattern | New Pattern Needed |
|------|-----------------|---------------------|
| `config.py` | `@dataclass(frozen=True, slots=True)` | `BaseModel` with `ConfigDict` |
| `bootstrap_payload.py` | `@dataclass(frozen=True, slots=True)` | `ProtocolModel` |
| `entities.py` | `BaseModel` with basic `ConfigDict` | Consistent `ConfigDict` with `strict=False` |
| `snapshot.py` | `BaseModel` with `field_validator` | Add `strict=False` and validate patterns |
| `changes.py` | `BaseModel` with basic `ConfigDict` | Add `strict=False` |
| `errors.py` | Basic `Exception` subclasses | Add structured metadata |
| `health.py` | `enum.Enum` | Consider `StrEnum` |

---

## 4. Required Changes by File

### 4.1 config.py

**Current:**
```python
from dataclasses import dataclass, replace

@dataclass(frozen=True, slots=True)
class NiriStateConfig:
    pypc: NiriConfig = NiriConfig()
    # ... other fields
```

**Change to:**
```python
from pydantic import BaseModel, ConfigDict

class NiriStateConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=False)

    pypc: NiriConfig = NiriConfig()
    # ... other fields
```

**Benefits:**
- Consistent with niri-pypc `NiriConfig`
- Enables pydantic validation on config construction
- Better error messages for invalid config

**Note:** The `normalize_config` function uses `dataclasses.replace` - this needs updating to use pydantic `.model_copy()` instead:

```python
# Before
normalized_pypc = replace(config.pypc, backpressure_mode=BackpressureMode.FAIL_FAST)
return replace(config, pypc=normalized_pypc)

# After
normalized_pypc = config.pypc.model_copy(update={"backpressure_mode": BackpressureMode.FAIL_FAST})
return config.model_copy(update={"pypc": normalized_pypc})
```

### 4.2 bootstrap_payload.py

**Current:**
```python
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class BootstrapPayload:
    outputs: dict[str, Output]
    # ... other fields
```

**Change to:**
```python
from niri_pypc.types.base import ProtocolModel

class BootstrapPayload(ProtocolModel):
    outputs: dict[str, Output]
    # ... other fields
```

**Benefits:**
- Consistent with niri-pypc models
- Better serialization/deserialization
- Enables validation at construction

### 4.3 entities.py

**Current:**
```python
class OutputState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    output_name: str
    protocol: Output
```

**Change to:**
```python
class OutputState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=False, populate_by_name=True)
    output_name: str
    protocol: Output
```

**Apply to all entity classes:**
- `OutputState`
- `WorkspaceState`
- `WindowState`
- `KeyboardState`
- `OverviewState`

**Benefits:**
- Consistent with niri-pypc ProtocolModel
- Better handling of protocol coercion

### 4.4 snapshot.py

**Current:**
```python
class NiriSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    # Uses field_validator for MappingProxyType wrapping
    @field_validator(
        "outputs",
        "workspaces",
        # ... others
        mode="before",
    )
    @classmethod
    def _wrap_in_mapping_proxy(cls, v: dict | MappingProxyType) -> MappingProxyType:
```

**Change to:**
```python
class NiriSnapshot(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        arbitrary_types_allowed=True,
        strict=False,
        populate_by_name=True,
    )
```

**Note:** The `field_validator` pattern is fine and can remain. Consider if `mode="plain"` (pydantic v2.1+) is preferred for new validators.

### 4.5 changes.py

**Current:**
```python
class ChangeSet(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    revision: Revision
    # ... fields
```

**Change to:**
```python
class ChangeSet(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=False)

    revision: Revision
    # ... fields
```

**Also consider:** Converting enum classes to `StrEnum`:
```python
# Before
class ChangeCause(enum.Enum):
    BOOTSTRAP = "bootstrap"
    EVENT = "event"
    # ...

# After
class ChangeCause(StrEnum):
    BOOTSTRAP = "bootstrap"
    EVENT = "event"
    # ...
```

### 4.6 errors.py

**Current:** Basic exception classes with limited metadata.

**Change to:** Add structured metadata consistent with niri-pypc pattern:

```python
class NiriStateError(Exception):
    def __init__(
        self,
        message: str,
        *,
        operation: str | None = None,
        retryable: bool = False,
        cause: Exception | None = None,
    ) -> None:
        self.operation = operation
        self.retryable = retryable
        self.cause = cause
        super().__init__(message)
```

**Apply to all error classes:**
- `StateConfigError` - Add operation, cause
- `StateLifecycleError` - Add operation, cause (has current_state, target_state)
- `BootstrapError` - Add operation, cause (has query)
- `ReductionError` - Add operation, cause (has event_type, revision)
- `InvariantError` - Add operation, cause (has violations, revision)
- `DesyncError` - Add operation, cause (has event_type, revision)
- `ResyncError` - Add operation, cause
- `SubscriptionOverflowError` - Add operation, cause
- `WaitTimeoutError` - Add operation, cause (has timeout)

**Note:** Some errors have existing structured fields that should be preserved. The pattern should extend, not replace.

### 4.7 health.py

**Current:**
```python
class HealthState(enum.Enum):
    BOOTSTRAPPING = "bootstrapping"
    LIVE = "live"
    # ...
```

**Option 1 (Keep as-is):** The health state is used more like a state machine than a string enum in protocol serialization. The current `enum.Enum` pattern is acceptable for internal state.

**Option 2 (StrEnum):** If consistency with niri-pypc is preferred:
```python
from enum import StrEnum

class HealthState(StrEnum):
    BOOTSTRAPPING = "bootstrapping"
    LIVE = "live"
    STALE = "stale"
    RESYNCING = "resyncing"
    CLOSED = "closed"
    FAILED = "failed"
```

**Recommendation:** Option 2 for full consistency. The health state values are already string-like and serializing as strings is more consistent.

---

## 5. Pydantic v2+ Enhancements for niri-state

Beyond aligning with niri-pypc patterns, there are opportunities for niri-state to leverage additional pydantic v2+ features:

### 5.1 Field Validation with model_validator

Replace `field_validator` with `model_validator` where cross-field validation is needed:

```python
# Current
@field_validator("outputs", mode="before")
@classmethod
def _wrap_in_mapping_proxy(cls, v):
    # ...

# Consider for new validators
@model_validator(mode="before")
def _validate_and_transform(cls, data):
    # Handle complex validation/transformation
    return data
```

### 5.2 Computed Fields

Use `computed_field` for derived data that doesn't need storage:

```python
from pydantic import computed_field

class Snapshot(BaseModel):
    # ... fields ...

    @computed_field
    @property
    def is_healthy(self) -> bool:
        return self.health == HealthState.LIVE
```

### 5.3 JSON Schema Generation

With consistent `ConfigDict`, the library can generate better JSON schemas for external consumers.

### 5.4 Deprecated Fields

Use `PydanticDeprecated` for any fields being phased out:

```python
from pydantic import PydanticDeprecated

class Config(BaseModel):
    old_field: str | None = PydanticDeprecated("Use new_field instead")
    new_field: str | None = None
```

### 5.5 Type Narrowing with BeforeValidator

For complex type transformations at deserialization:

```python
from pydantic import BeforeValidator

type OutputMap = Annotated[dict[str, Output], BeforeValidator(normalize_outputs)]
```

---

## 6. Migration Priority and Order

### Phase 1: Core Infrastructure (High Priority)

1. **config.py** - Most visible change, affects initialization
2. **bootstrap_payload.py** - Foundation for snapshot building

### Phase 2: Model Alignment (Medium Priority)

3. **entities.py** - Fundamental data types
4. **snapshot.py** - Core snapshot model
5. **changes.py** - Change tracking

### Phase 3: Error Handling (Medium Priority)

6. **errors.py** - Improved debugging and logging

### Phase 4: Enhancements (Low Priority)

7. **health.py** - StrEnum conversion
8. Add computed fields where beneficial
9. Add model validators for complex validation

---

## 7. Testing Strategy

### Before Each Phase

1. Run full test suite to establish baseline
2. Run ruff and ty checks

### After Each Change

1. Run related unit tests
2. Run ruff check
3. Run ruff format --check
4. Run ty check

### Critical Tests to Verify

- `tests/core/models/test_snapshot.py` - Snapshot creation and validation
- `tests/core/models/test_draft.py` - Draft state operations
- `tests/runtime/test_store.py` - Full state lifecycle
- `tests/runtime/test_bootstrap.py` - Bootstrap flow
- `tests/integration/test_bootstrap_convergence.py` - End-to-end integration

### Backward Compatibility

- Public API signatures should remain unchanged
- Internal implementation details may change
- Test that existing code using niri-state continues to work

---

## Summary

This refactoring will:

1. **Align niri-state with niri-pypc patterns** - Consistent ConfigDict settings, StrEnum usage
2. **Improve error handling** - Structured metadata on all exceptions
3. **Leverage pydantic v2+ features** - Better validation, computed fields, schema generation
4. **Maintain backward compatibility** - No public API changes

The changes are primarily internal implementation details that improve consistency, type safety, and maintainability while keeping the public API stable.