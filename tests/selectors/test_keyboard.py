from __future__ import annotations

from niri_state.selectors import keyboard
from tests._typing_helpers import make_minimal_snapshot


class TestKeyboardSelectors:
    def test_get_keyboard_state(self) -> None:
        snap = make_minimal_snapshot()
        result = keyboard.get_keyboard_state(snap)
        assert result is snap.keyboard

    def test_get_current_layout_name(self) -> None:
        snap = make_minimal_snapshot()
        result = keyboard.get_current_layout_name(snap)
        assert result == "us"
