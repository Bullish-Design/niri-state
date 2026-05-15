from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from io import StringIO
from types import SimpleNamespace
from typing import Any

from typer.testing import CliRunner

from niri_state.api.changes import ChangeCause, ChangedDomain, ChangeSet
from niri_state.api.health import HealthState
from niri_state.cli import DetailLevel, OutputFormat, _format_json_line, _format_text_line, _stream_loop, app
from niri_state.core.broadcaster import PublishedState


@dataclass(frozen=True)
class _SnapshotStub:
    revision: int
    health: HealthState


class _FakeState:
    def __init__(self, items: list[PublishedState]) -> None:
        self._items = items
        self.closed = False

    async def subscribe(self) -> AsyncIterator[PublishedState]:
        for item in self._items:
            yield item

    async def close(self) -> None:
        self.closed = True


class _Dumpable:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def model_dump(self, *, mode: str) -> dict[str, Any]:
        assert mode == "json"
        return self.payload


def _published(
    *,
    revision: int,
    health: HealthState = HealthState.LIVE,
    cause: ChangeCause = ChangeCause.EVENT,
    domains: frozenset[ChangedDomain] | None = None,
) -> PublishedState:
    return PublishedState(
        snapshot=_SnapshotStub(revision=revision, health=health),  # type: ignore[arg-type]
        changes=ChangeSet(
            revision=revision,
            cause=cause,
            domains=domains or frozenset({ChangedDomain.WINDOWS}),
        ),
    )


def _rich_published(*, domains: frozenset[ChangedDomain]) -> PublishedState:
    snapshot = SimpleNamespace(
        revision=11,
        timestamp=123.4,
        health=HealthState.LIVE,
        focused_window_id=101,
        focused_workspace_id=2,
        focused_output_name="HDMI-A-1",
        keyboard_current_name="US",
        outputs={"HDMI-A-1": _Dumpable({"name": "HDMI-A-1"})},
        workspaces={2: _Dumpable({"id": 2, "output": "HDMI-A-1"})},
        windows={101: _Dumpable({"id": 101, "title": "Terminal"})},
        keyboard_layouts=_Dumpable({"names": ["US", "DE"], "current_idx": 0}),
        overview=_Dumpable({"is_open": False}),
        diagnostics=_Dumpable({"desynced": False, "event_count": 42}),
        compatibility=_Dumpable({"niri_version": "x", "schema_version": "y", "warnings": []}),
    )
    return PublishedState(
        snapshot=snapshot,  # type: ignore[arg-type]
        changes=ChangeSet(revision=11, cause=ChangeCause.EVENT, domains=domains),
    )


def test_format_text_line_with_changes() -> None:
    line = _format_text_line(_published(revision=7), show_changes=True)
    assert line == "rev=7 health=live cause=event domains=windows"


def test_format_text_line_without_changes() -> None:
    line = _format_text_line(_published(revision=8), show_changes=False)
    assert line == "rev=8 health=live"


def test_format_json_line_summary_has_base_fields() -> None:
    line = _format_json_line(_published(revision=9), detail=DetailLevel.SUMMARY)
    payload = json.loads(line)
    assert payload["revision"] == 9
    assert payload["health"] == "live"
    assert payload["cause"] == "event"
    assert payload["domains"] == ["windows"]
    assert isinstance(payload["timestamp"], str)
    assert "snapshot" not in payload
    assert "delta" not in payload


def test_format_json_line_focus_has_focus_fields() -> None:
    line = _format_json_line(_rich_published(domains=frozenset({ChangedDomain.FOCUS})), detail=DetailLevel.FOCUS)
    payload = json.loads(line)
    assert payload["focused_window_id"] == 101
    assert payload["focused_workspace_id"] == 2
    assert payload["focused_output_name"] == "HDMI-A-1"
    assert payload["keyboard_current_name"] == "US"
    assert payload["overview_open"] is False


def test_format_json_line_delta_has_domain_filtered_payload() -> None:
    line = _format_json_line(
        _rich_published(domains=frozenset({ChangedDomain.WINDOWS, ChangedDomain.KEYBOARD})),
        detail=DetailLevel.DELTA,
    )
    payload = json.loads(line)
    assert "delta" in payload
    assert sorted(payload["delta"].keys()) == ["keyboard", "windows"]
    assert payload["delta"]["windows"]["101"]["title"] == "Terminal"


def test_format_json_line_snapshot_has_full_snapshot_payload() -> None:
    line = _format_json_line(_rich_published(domains=frozenset({ChangedDomain.WINDOWS})), detail=DetailLevel.SNAPSHOT)
    payload = json.loads(line)
    snapshot = payload["snapshot"]
    assert snapshot["revision"] == 11
    assert snapshot["health"] == "live"
    assert snapshot["windows"]["101"]["id"] == 101
    assert snapshot["diagnostics"]["event_count"] == 42


def test_cli_rejects_invalid_format() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["stream", "--format", "yaml"])
    assert result.exit_code == 2


def test_cli_rejects_invalid_detail() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["stream", "--detail", "full"])
    assert result.exit_code == 2


def test_cli_requires_stream_subcommand() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--format", "json"])
    assert result.exit_code == 2


async def test_stream_loop_skips_initial_when_disabled() -> None:
    fake = _FakeState(
        [
            _published(revision=1, cause=ChangeCause.BOOTSTRAP),
            _published(revision=2, cause=ChangeCause.EVENT),
        ]
    )

    output = StringIO()
    await _stream_loop(
        fmt=OutputFormat.TEXT,
        detail=DetailLevel.SUMMARY,
        include_initial=False,
        show_changes=False,
        flush=True,
        max_events=1,
        output=output,
        state_factory=lambda: _open_fake_state(fake),
    )

    out = output.getvalue()
    assert "rev=2 health=live" in out
    assert "rev=1" not in out
    assert fake.closed is True


async def _open_fake_state(fake: _FakeState) -> _FakeState:
    return fake
