from __future__ import annotations

from niri_state.selectors import overview
from tests._typing_helpers import make_minimal_snapshot


class TestOverviewSelectors:
    def test_is_overview_open_false(self) -> None:
        snap = make_minimal_snapshot()
        result = overview.is_overview_open(snap)
        assert result is False

    def test_is_overview_open_true(self) -> None:
        from niri_state._core.models.entities import OverviewState

        snap = make_minimal_snapshot(overview=OverviewState(is_open=True))
        result = overview.is_overview_open(snap)
        assert result is True

    def test_get_overview_state(self) -> None:
        snap = make_minimal_snapshot()
        result = overview.get_overview_state(snap)
        assert result is snap.overview
