from __future__ import annotations

from niri_state.protocol import Overview
from niri_state.snapshot import Snapshot


def get_overview(snapshot: Snapshot) -> Overview:
    return snapshot.overview


def is_overview_open(snapshot: Snapshot) -> bool:
    return snapshot.overview.is_open
