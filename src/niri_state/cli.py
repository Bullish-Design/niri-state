from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Protocol, TextIO, cast

import typer

from niri_state.api.changes import ChangeCause, ChangedDomain
from niri_state.api.config import NiriStateConfig
from niri_state.api.state import NiriState
from niri_state.core.broadcaster import PublishedState

app = typer.Typer(add_completion=False, no_args_is_help=True)


class SupportsStreamState(Protocol):
    def subscribe(self) -> AsyncIterator[PublishedState]: ...

    async def close(self) -> None: ...


class OutputFormat(StrEnum):
    TEXT = "text"
    JSON = "json"


class DetailLevel(StrEnum):
    SUMMARY = "summary"
    FOCUS = "focus"
    DELTA = "delta"
    SNAPSHOT = "snapshot"


@app.callback()
def cli() -> None:
    """niri-state CLI commands."""


@app.command()
def stream(
    fmt: Annotated[
        OutputFormat,
        typer.Option("--format", help="Output format: text or json."),
    ] = OutputFormat.TEXT,
    detail: Annotated[
        DetailLevel,
        typer.Option("--detail", help="Detail level: summary, focus, delta, or snapshot."),
    ] = DetailLevel.SUMMARY,
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
    asyncio.run(
        _stream_loop(
            fmt=fmt,
            detail=detail,
            include_initial=include_initial,
            show_changes=show_changes,
            flush=flush,
            max_events=max_events,
            output=sys.stdout,
        )
    )


async def _stream_loop(
    *,
    fmt: OutputFormat,
    detail: DetailLevel,
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

            if fmt is OutputFormat.JSON:
                line = _format_json_line(published, detail=detail)
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


def _format_json_line(published: PublishedState, *, detail: DetailLevel) -> str:
    payload: dict[str, Any] = {
        "revision": published.snapshot.revision,
        "health": published.snapshot.health.value,
        "cause": published.changes.cause.value,
        "domains": sorted(domain.value for domain in published.changes.domains),
        "timestamp": datetime.now(UTC).isoformat(),
    }

    if detail is DetailLevel.FOCUS:
        payload.update(_focus_payload(published.snapshot))
    elif detail is DetailLevel.DELTA:
        payload["delta"] = _delta_payload(published)
    elif detail is DetailLevel.SNAPSHOT:
        payload["snapshot"] = _snapshot_payload(published.snapshot)

    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _focus_payload(snapshot: Any) -> dict[str, Any]:
    return {
        "focused_window_id": getattr(snapshot, "focused_window_id", None),
        "focused_workspace_id": getattr(snapshot, "focused_workspace_id", None),
        "focused_output_name": getattr(snapshot, "focused_output_name", None),
        "keyboard_current_name": getattr(snapshot, "keyboard_current_name", None),
        "overview_open": bool(getattr(getattr(snapshot, "overview", None), "is_open", False)),
    }


def _delta_payload(published: PublishedState) -> dict[str, Any]:
    snapshot = published.snapshot
    domains = published.changes.domains
    payload: dict[str, Any] = {}

    if ChangedDomain.OUTPUTS in domains:
        payload["outputs"] = _mapping_projection(getattr(snapshot, "outputs", {}))
    if ChangedDomain.WORKSPACES in domains:
        payload["workspaces"] = _mapping_projection(getattr(snapshot, "workspaces", {}))
    if ChangedDomain.WINDOWS in domains:
        payload["windows"] = _mapping_projection(getattr(snapshot, "windows", {}))
    if ChangedDomain.FOCUS in domains:
        payload["focus"] = {
            "focused_window_id": getattr(snapshot, "focused_window_id", None),
            "focused_workspace_id": getattr(snapshot, "focused_workspace_id", None),
            "focused_output_name": getattr(snapshot, "focused_output_name", None),
        }
    if ChangedDomain.KEYBOARD in domains:
        payload["keyboard"] = _jsonable(getattr(snapshot, "keyboard_layouts", None))
    if ChangedDomain.OVERVIEW in domains:
        payload["overview"] = _jsonable(getattr(snapshot, "overview", None))
    if ChangedDomain.HEALTH in domains:
        payload["health"] = _health_value(snapshot)
    if ChangedDomain.DIAGNOSTICS in domains:
        payload["diagnostics"] = _jsonable(getattr(snapshot, "diagnostics", None))

    return payload


def _snapshot_payload(snapshot: Any) -> dict[str, Any]:
    return {
        "revision": getattr(snapshot, "revision", None),
        "timestamp": getattr(snapshot, "timestamp", None),
        "health": _health_value(snapshot),
        "focused_window_id": getattr(snapshot, "focused_window_id", None),
        "focused_workspace_id": getattr(snapshot, "focused_workspace_id", None),
        "focused_output_name": getattr(snapshot, "focused_output_name", None),
        "keyboard_current_name": getattr(snapshot, "keyboard_current_name", None),
        "outputs": _mapping_projection(getattr(snapshot, "outputs", {})),
        "workspaces": _mapping_projection(getattr(snapshot, "workspaces", {})),
        "windows": _mapping_projection(getattr(snapshot, "windows", {})),
        "keyboard_layouts": _jsonable(getattr(snapshot, "keyboard_layouts", None)),
        "overview": _jsonable(getattr(snapshot, "overview", None)),
        "diagnostics": _jsonable(getattr(snapshot, "diagnostics", None)),
        "compatibility": _jsonable(getattr(snapshot, "compatibility", None)),
    }


def _mapping_projection(mapping: Mapping[Any, Any] | object) -> dict[str, Any]:
    if not isinstance(mapping, Mapping):
        return {}
    return {str(key): _jsonable(value) for key, value in mapping.items()}


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, Mapping):
        return {str(key): _jsonable(inner) for key, inner in value.items()}

    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]

    if isinstance(value, StrEnum):
        return value.value

    model_dump = getattr(value, "model_dump", None)
    if model_dump is not None:
        model_dump_fn = cast(Callable[..., Any], model_dump)
        return _jsonable(model_dump_fn(mode="json"))

    if hasattr(value, "__dict__"):
        return {str(key): _jsonable(inner) for key, inner in vars(value).items()}

    return str(value)


def _health_value(snapshot: Any) -> str | None:
    health = getattr(snapshot, "health", None)
    value = getattr(health, "value", None)
    return value if isinstance(value, str) else None


def main() -> None:
    app()


if __name__ == "__main__":
    main()
