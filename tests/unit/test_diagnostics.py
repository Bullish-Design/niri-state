from __future__ import annotations

from niri_state.diagnostics import Diagnostics, InvariantViolation, with_desync, with_invariant_violations


def test_with_desync_marks_diagnostic() -> None:
    diag = with_desync(Diagnostics(), event_type="UnknownEvent", reason="unknown event")
    assert diag.desynced is True
    assert diag.last_event_type == "UnknownEvent"
    assert diag.last_error == "unknown event"


def test_with_invariant_violations_stores_tuple() -> None:
    violations = (
        InvariantViolation(code="x", message="y"),
    )
    diag = with_invariant_violations(Diagnostics(), violations=violations)
    assert diag.invariant_violations == violations
