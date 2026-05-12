from __future__ import annotations

from niri_state._core.models.entities import OverviewState
from niri_state._core.models.snapshot import NiriSnapshot


def is_overview_open(snapshot: NiriSnapshot) -> bool:
    """Check if overview is open."""
    return snapshot.overview.is_open


def get_overview_state(snapshot: NiriSnapshot) -> OverviewState:
    """Get the overview state."""
    return snapshot.overview
