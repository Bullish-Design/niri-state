from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from io import StringIO

from typer.testing import CliRunner

from niri_state.api.changes import ChangeCause, ChangedDomain, ChangeSet
from niri_state.api.health import HealthState
from niri_state.cli import _format_json_line, _format_text_line, _stream_loop, app
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


def test_format_text_line_with_changes() -> None:
    line = _format_text_line(_published(revision=7), show_changes=True)
    assert line == "rev=7 health=live cause=event domains=windows"


def test_format_text_line_without_changes() -> None:
    line = _format_text_line(_published(revision=8), show_changes=False)
    assert line == "rev=8 health=live"


def test_format_json_line_has_expected_fields() -> None:
    line = _format_json_line(_published(revision=9))
    payload = json.loads(line)
    assert payload["revision"] == 9
    assert payload["health"] == "live"
    assert payload["cause"] == "event"
    assert payload["domains"] == ["windows"]
    assert isinstance(payload["timestamp"], str)


def test_cli_rejects_invalid_format() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["stream", "--format", "yaml"])
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
        fmt="text",
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
