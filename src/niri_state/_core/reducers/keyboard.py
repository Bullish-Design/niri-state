from __future__ import annotations

from niri_pypc.types.generated.event import (
    KeyboardLayoutsChangedEvent,
    KeyboardLayoutSwitchedEvent,
)
from niri_pypc.types.generated.models import KeyboardLayouts

from niri_state._core.models.draft import DraftState


def _derive_current_name(protocol: KeyboardLayouts) -> str | None:
    """Derive current keyboard layout name from protocol."""
    if protocol.current_idx < 0:
        return None
    if protocol.current_idx >= len(protocol.names):
        return None
    return protocol.names[protocol.current_idx]


def apply_keyboard_layouts_changed(draft: DraftState, event: KeyboardLayoutsChangedEvent) -> bool:
    """Replace protocol payload; recompute current_name with bounds checks."""
    old_protocol = draft.keyboard.protocol
    old_current = draft.keyboard.current_name

    new_protocol = event.keyboard_layouts
    new_current = _derive_current_name(new_protocol)

    if old_protocol != new_protocol or old_current != new_current:
        draft.keyboard = draft.keyboard.model_copy(update={"protocol": new_protocol, "current_name": new_current})
        return True
    return False


def apply_keyboard_layout_switched(draft: DraftState, event: KeyboardLayoutSwitchedEvent) -> bool:
    """Patch current_idx; recompute current_name."""
    updated_protocol = draft.keyboard.protocol.model_copy(update={"current_idx": event.idx})
    new_current = _derive_current_name(updated_protocol)

    if draft.keyboard.current_name != new_current:
        draft.keyboard = draft.keyboard.model_copy(update={"protocol": updated_protocol, "current_name": new_current})
        return True
    return False
