from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, TypeVar, cast

from niri_pypc import NiriConnectionBundle
from niri_pypc.types.generated.models import KeyboardLayouts, Output, Overview, Window
from niri_pypc.types.generated.reply import (
    FocusedOutputResponse,
    FocusedWindowResponse,
    KeyboardLayoutsResponse,
    OutputsResponse,
    OverviewStateResponse,
    Response,
    VersionResponse,
    WindowsResponse,
    WorkspacesResponse,
)
from niri_pypc.types.generated.request import (
    FocusedOutputRequest,
    FocusedWindowRequest,
    KeyboardLayoutsRequest,
    OutputsRequest,
    OverviewStateRequest,
    VersionRequest,
    WindowsRequest,
    WorkspacesRequest,
)

from niri_state._core.invariants import assert_invariants
from niri_state._core.models.bootstrap_payload import BootstrapPayload
from niri_state._core.models.changes import ChangeCause, ChangedDomain, ChangeSet
from niri_state._core.models.draft import DraftState
from niri_state._core.models.health import HealthState
from niri_state._core.models.snapshot import NiriSnapshot
from niri_state._core.reducers.root import reduce_event
from niri_state._core.snapshot_builder import build_initial_draft
from niri_state.config import NiriStateConfig, UnknownEventPolicy, normalize_config
from niri_state.errors import BootstrapError, DesyncError


@dataclass(frozen=True, slots=True)
class BootstrapOutcome:
    bundle: NiriConnectionBundle
    initial_snapshot: NiriSnapshot
    initial_changeset: ChangeSet


async def run_bootstrap(config: NiriStateConfig) -> BootstrapOutcome:
    normalized = normalize_config(config)

    try:
        bundle = await NiriConnectionBundle.open(normalized.pypc)
    except Exception as exc:
        raise BootstrapError("Failed to open connection bundle", cause=exc) from exc

    buffered_events: list[object] = []
    reader_errors: list[Exception] = []
    query_done = asyncio.Event()
    reader_task: asyncio.Task[None] | None = None

    def _start_reader() -> None:
        nonlocal reader_task
        reader_task = asyncio.create_task(_read_events_loop(bundle, buffered_events, query_done, reader_errors))

    _start_reader()

    try:
        payload = await _execute_bootstrap_queries(bundle)
        query_done.set()
        if reader_task is not None:
            try:
                await asyncio.wait_for(reader_task, timeout=5.0)
            except TimeoutError:
                reader_task.cancel()
                try:
                    await reader_task
                except asyncio.CancelledError:
                    pass
    except Exception as exc:
        query_done.set()
        if reader_task is not None:
            reader_task.cancel()
            try:
                await reader_task
            except asyncio.CancelledError:
                pass
        try:
            await bundle.close()
        except Exception:
            pass
        raise BootstrapError("Bootstrap query phase failed", cause=exc) from exc
    if reader_errors:
        try:
            await bundle.close()
        except Exception:
            pass
        raise BootstrapError("Event stream failed during bootstrap", cause=reader_errors[0])

    draft = build_initial_draft(payload)

    _assert_invariants(draft.freeze(revision=0))

    for event in buffered_events:
        _apply_event(draft, event, normalized)

    if draft.health is HealthState.BOOTSTRAPPING:
        draft.health = HealthState.LIVE
    published_snapshot = draft.freeze(revision=1)
    _assert_invariants(published_snapshot)

    changeset = ChangeSet(
        revision=1,
        timestamp=published_snapshot.timestamp,
        cause=ChangeCause.BOOTSTRAP,
        changed_domains=frozenset(
            {
                ChangedDomain.OUTPUTS,
                ChangedDomain.WORKSPACES,
                ChangedDomain.WINDOWS,
                ChangedDomain.FOCUS,
                ChangedDomain.KEYBOARD,
                ChangedDomain.OVERVIEW,
                ChangedDomain.HEALTH,
            }
        ),
        event_type=None,
        event_summary="bootstrap",
    )

    return BootstrapOutcome(bundle=bundle, initial_snapshot=published_snapshot, initial_changeset=changeset)


async def _read_events_loop(
    bundle: NiriConnectionBundle,
    buffer: list[object],
    query_done: asyncio.Event,
    errors: list[Exception],
) -> None:
    try:
        while not query_done.is_set():
            try:
                event = await asyncio.wait_for(bundle.events.next(timeout=0.1), timeout=1.0)
                buffer.append(event)
            except TimeoutError:
                continue
            except Exception as exc:
                errors.append(exc)
                break
    except asyncio.CancelledError:
        pass


T = TypeVar("T")


def _extract_payload(
    value: object,
    response_type: type[object],
    query: str,
    expected_type: type[object] | tuple[type[object], ...],
) -> T:
    payload: object = value

    if isinstance(value, Response):
        variant = value.variant
        if not isinstance(variant, response_type):
            raise BootstrapError(f"{query} request returned unexpected variant {type(variant).__name__}", query=query)
        payload = cast(Any, variant).payload

    if not isinstance(payload, expected_type):
        raise BootstrapError(f"{query} request returned {type(payload).__name__}", query=query)

    return cast(T, payload)


async def _execute_bootstrap_queries(bundle: NiriConnectionBundle) -> BootstrapPayload:
    client = bundle.client

    outputs_typed = _extract_payload(
        await client.request(OutputsRequest()),
        OutputsResponse,
        "outputs",
        dict,
    )
    workspaces_typed = _extract_payload(
        await client.request(WorkspacesRequest()),
        WorkspacesResponse,
        "workspaces",
        list,
    )
    windows_typed = _extract_payload(
        await client.request(WindowsRequest()),
        WindowsResponse,
        "windows",
        list,
    )
    focused_output = _extract_payload(
        await client.request(FocusedOutputRequest()),
        FocusedOutputResponse,
        "focused_output",
        (Output, type(None)),
    )
    focused_window = _extract_payload(
        await client.request(FocusedWindowRequest()),
        FocusedWindowResponse,
        "focused_window",
        (Window, type(None)),
    )
    keyboard_layouts = _extract_payload(
        await client.request(KeyboardLayoutsRequest()),
        KeyboardLayoutsResponse,
        "keyboard_layouts",
        KeyboardLayouts,
    )
    overview = _extract_payload(
        await client.request(OverviewStateRequest()),
        OverviewStateResponse,
        "overview",
        Overview,
    )

    compositor_version: str | None = None
    try:
        version_resp = await client.request(VersionRequest())
        compositor_version = _extract_payload(version_resp, VersionResponse, "version", str)
    except Exception:
        compositor_version = None

    return BootstrapPayload(
        outputs=outputs_typed,
        workspaces=workspaces_typed,
        windows=windows_typed,
        focused_output=focused_output,
        focused_window=focused_window,
        keyboard_layouts=keyboard_layouts,
        overview=overview,
        compositor_version=compositor_version,
    )


def _apply_event(draft: DraftState, event: object, config: NiriStateConfig) -> None:
    result = reduce_event(draft, event, config.unknown_event_policy)
    if not result.applied and config.unknown_event_policy is UnknownEventPolicy.FAIL:
        raise DesyncError(f"Unhandled event type: {type(event).__name__}", event_type=type(event).__name__)


def _assert_invariants(snapshot: NiriSnapshot) -> None:
    try:
        assert_invariants(snapshot)
    except Exception as exc:
        raise BootstrapError(f"Invariant check failed at revision {snapshot.revision}: {exc}", cause=exc) from exc
