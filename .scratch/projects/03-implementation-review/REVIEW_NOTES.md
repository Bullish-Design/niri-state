# Review Notes

## Type Error Summary

Total: 60 mypy errors

### By Category

1. **model_copy(update={}) pattern**: 18 errors
   - keyboard.py: 3
   - windows.py: 5
   - workspaces.py: 6
   - overview.py: 1
   - root.py: 1

2. **Test fixtures wrong types**: 30+ errors
   - Most tests use dict instead of MappingProxyType
   - Missing Pydantic model required fields

3. **config.py normalize_config**: 2 errors
   - dataclasses.replace on frozen dataclass

4. **waiters.py**: 1 error
   - state.snapshot type narrowing

5. **Various test issues**: ~10 errors
   - TemporaryDirectory() overloads
   - Missing arguments to Pydantic models

## Files Checked

### Source Files
- ✅ config.py - correct structure
- ✅ errors.py - correct error hierarchy with proper naming
- ✅ _core/models/types.py
- ✅ _core/models/entities.py  
- ✅ _core/models/health.py
- ✅ _core/models/snapshot.py - MappingProxyType enforced
- ✅ _core/models/draft.py
- ✅ _core/models/changes.py
- ✅ _core/models/bootstrap_payload.py - correctly in _core
- ✅ _core/invariants.py - 10 checks
- ✅ _core/reducers/root.py - match/case dispatch
- ✅ _core/reducers/windows.py - 7 handlers
- ✅ _core/reducers/workspaces.py - 4 handlers
- ✅ _core/reducers/keyboard.py - 2 handlers
- ✅ _core/reducers/overview.py - 1 handler
- ✅ _core/snapshot_builder.py
- ✅ _runtime/bootstrap.py
- ✅ _runtime/store.py
- ✅ _runtime/waiters.py
- ✅ _runtime/resync.py
- ✅ selectors/ - all modules present

## Test Results

Working test modules:
- test_config.py ✅
- test_errors.py ✅  
- core/models/ ✅ (30 tests)
- core/reducers/ ✅ (16 tests)
- core/test_invariants.py ✅
- core/test_snapshot_builder.py ✅
- selectors/ ✅ (22 tests)
- runtime/test_store.py ✅

## Next Steps

1. Fix type errors in model_copy() calls
2. Fix normalize_config type issues  
3. Add runtime module tests
4. Complete public API exports
5. Fix test helper functions