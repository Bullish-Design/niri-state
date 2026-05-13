# PROGRESS

## Task: niri-state Pydantic v2+ Refactoring

### Completed

- [x] Study niri-pypc library patterns in depth
  - Read all niri_pypc modules: __init__.py, config.py, errors.py
  - Read types: base.py, codec.py, generated/event.py, generated/models.py
  - Read runtime: lifecycle.py
- [x] Study niri-state library in depth
  - Read all core models: types.py, entities.py, snapshot.py, changes.py, health.py, draft.py, bootstrap_payload.py
  - Read reducers: root.py, windows.py, workspaces.py, keyboard.py, overview.py
  - Read runtime: store.py
  - Read selectors: windows.py, overview.py
  - Read config.py and errors.py
- [x] Create project directory structure
- [x] Create PLAN.md
- [x] Create ASSUMPTIONS.md
- [x] Create NIRI_STATE_REFACTORING_OVERVIEW.md with complete analysis
- [x] Update `REFINED_V2_REWRITE_CODE_SKELETON.md` from `Refined_Rewrite_Patch_Updates.md`
  - Added missing tree entries and runtime seams
  - Locked API direction (`snapshot` property path)
  - Added protocol helper type re-exports and resync changeset helper
  - Added mandatory implementation-contract appendix

### Pending

- [ ] Phase 1: Refactor config.py (convert from dataclass to BaseModel)
- [ ] Phase 1: Refactor bootstrap_payload.py (convert from dataclass to ProtocolModel)
- [ ] Phase 2: Refactor entities.py (add strict=False, populate_by_name=True)
- [ ] Phase 2: Refactor snapshot.py (add strict=False, populate_by_name=True)
- [ ] Phase 2: Refactor changes.py (add strict=False, consider StrEnum)
- [ ] Phase 3: Refactor errors.py (add structured metadata)
- [ ] Phase 4: Refactor health.py (convert to StrEnum)
- [ ] Run all quality checks after each phase
- [ ] Run test suite to verify no regressions

### Notes

The NIRI_STATE_REFACTORING_OVERVIEW.md document provides:
- Detailed analysis of niri-pypc patterns
- File-by-file change recommendations
- Migration priority and order
- Testing strategy
- Additional pydantic v2+ enhancement opportunities
