from __future__ import annotations

from niri_state._core.models.snapshot import NiriSnapshot


def get_keyboard_state(snapshot: NiriSnapshot) -> object:
    """Get the keyboard state."""
    return snapshot.keyboard


def get_current_layout_name(snapshot: NiriSnapshot) -> str | None:
    """Get the current keyboard layout name."""
    return snapshot.keyboard.current_name
