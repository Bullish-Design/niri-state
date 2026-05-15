from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from typing import Annotated, Protocol, TextIO

import typer

from niri_state.api.changes import ChangeCause
from niri_state.api.config import NiriStateConfig
from niri_state.api.state import NiriState
from niri_state.core.broadcaster import PublishedState

app = typer.Typer(add_completion=False, no_args_is_help=True)


class SupportsStreamState(Protocol):
    def subscribe(self) -> AsyncIterator[PublishedState]: ...

    async def close(self) -> None: ...


@app.command()
def stream(
    fmt: Annotated[
        str,
        typer.Option("--format", help="Output format: text or json."),
    ] = "text",
    include_initial: Annotated[
        bool,
        typer.Option("--include-initial/--no-include-initial", help="Include initial bootstrap publication."),
    ] = True,
    show_changes: Annotated[
        bool,
        typer.Option("--show-changes/--no-show-changes", help="Include change details in text mode."),
    ] = True,
    flush: Annotated[
        bool,
        typer.Option("--flush/--no-flush", help="Flush stdout after each event."),
    ] = True,
    max_events: Annotated[
        int | None,
        typer.Option(min=1, help="Stop after emitting this many events."),
    ] = None,
) -> None:
    """Continuously stream niri-state publications."""
    if fmt not in {"text", "json"}:
        raise typer.BadParameter("must be one of: text, json", param_hint="--format")

    asyncio.run(
        _stream_loop(
            fmt=fmt,
            include_initial=include_initial,
            show_changes=show_changes,
            flush=flush,
            max_events=max_events,
            output=sys.stdout,
        )
    )


async def _stream_loop(
    *,
    fmt: str,
    include_initial: bool,
    show_changes: bool,
    flush: bool,
    max_events: int | None,
    output: TextIO,
    state_factory: Callable[[], Awaitable[SupportsStreamState]] | None = None,
) -> None:
    if state_factory is None:
        state = await NiriState.open(NiriStateConfig())
    else:
        state = await state_factory()

    emitted = 0
    try:
        async for published in state.subscribe():
            if not include_initial and published.changes.cause is ChangeCause.BOOTSTRAP:
                continue

            if fmt == "json":
                line = _format_json_line(published)
            else:
                line = _format_text_line(published, show_changes=show_changes)

            print(line, file=output, flush=flush)
            emitted += 1

            if max_events is not None and emitted >= max_events:
                return
    except KeyboardInterrupt:
        return
    finally:
        await state.close()


def _format_text_line(published: PublishedState, *, show_changes: bool) -> str:
    snapshot = published.snapshot
    base = f"rev={snapshot.revision} health={snapshot.health.value}"
    if not show_changes:
        return base

    changes = published.changes
    domains = ",".join(sorted(domain.value for domain in changes.domains))
    return f"{base} cause={changes.cause.value} domains={domains}"


def _format_json_line(published: PublishedState) -> str:
    payload = {
        "revision": published.snapshot.revision,
        "health": published.snapshot.health.value,
        "cause": published.changes.cause.value,
        "domains": sorted(domain.value for domain in published.changes.domains),
        "timestamp": datetime.now(UTC).isoformat(),
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
