from __future__ import annotations

from niri_state.adapters.protocol import KeyboardLayouts
from niri_state.api.snapshot import Snapshot


def get_keyboard_layouts(snapshot: Snapshot) -> KeyboardLayouts:
    return snapshot.keyboard_layouts


def get_keyboard_current_name(snapshot: Snapshot) -> str | None:
    return snapshot.keyboard_current_name
