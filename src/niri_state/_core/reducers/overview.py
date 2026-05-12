from __future__ import annotations

from niri_pypc.types.generated.event import OverviewOpenedOrClosedEvent

from niri_state._core.models.draft import DraftState


def apply_overview_opened_or_closed(draft: DraftState, event: OverviewOpenedOrClosedEvent) -> bool:
    """Set overview.is_open."""
    if draft.overview.is_open == event.is_open:
        return False
    draft.overview = draft.overview.model_copy(
        update={"is_open": event.is_open}  # type: ignore[arg-type]
    )
    return True
