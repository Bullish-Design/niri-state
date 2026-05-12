from __future__ import annotations

import asyncio
from dataclasses import dataclass

from niri_pypc import NiriConnectionBundle
from niri_pypc.types.generated.models import (
    KeyboardLayouts,
    Output,
    Overview,
    Window,
    Workspace,
)
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
from niri_state.config import NiriStateConfig, normalize_config
from niri_state.errors import BootstrapError


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
    query_done = asyncio.Event()
    reader_task: asyncio.Task[None] | None = None

    def _start_reader() -> None:
        nonlocal reader_task
        reader_task = asyncio.create_task(_read_events_loop(bundle, buffered_events, query_done))

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

    draft = build_initial_draft(payload)

    _assert_invariants(draft.freeze(revision=0))

    for event in buffered_events:
        _apply_event(draft, event, normalized.unknown_event_policy.value)

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

    return BootstrapOutcome(
        bundle=bundle,
        initial_snapshot=published_snapshot,
        initial_changeset=changeset,
    )


async def _read_events_loop(
    bundle: NiriConnectionBundle,
    buffer: list[object],
    query_done: asyncio.Event,
) -> None:
    try:
        while not query_done.is_set():
            try:
                event = await asyncio.wait_for(
                    bundle.events.next(timeout=0.1),
                    timeout=1.0,
                )
                buffer.append(event)
            except TimeoutError:
                continue
            except Exception:
                break
    except asyncio.CancelledError:
        pass


async def _execute_bootstrap_queries(bundle: NiriConnectionBundle) -> BootstrapPayload:
    client = bundle.client

    outputs_resp = await client.request(OutputsRequest())
    if not isinstance(outputs_resp, Response) or not isinstance(outputs_resp.variant, OutputsResponse):
        raise BootstrapError(
            f"Outputs request returned {type(outputs_resp).__name__}",
            query="outputs",
        )
    outputs_typed: dict[str, Output] = outputs_resp.variant.payload

    workspaces_resp = await client.request(WorkspacesRequest())
    if not isinstance(workspaces_resp, Response) or not isinstance(workspaces_resp.variant, WorkspacesResponse):
        raise BootstrapError(
            f"Workspaces request returned {type(workspaces_resp).__name__}",
            query="workspaces",
        )
    workspaces_typed: list[Workspace] = workspaces_resp.variant.payload

    windows_resp = await client.request(WindowsRequest())
    if not isinstance(windows_resp, Response) or not isinstance(windows_resp.variant, WindowsResponse):
        raise BootstrapError(f"Windows request returned {type(windows_resp).__name__}", query="windows")
    windows_typed: list[Window] = windows_resp.variant.payload

    focused_output_resp = await client.request(FocusedOutputRequest())
    if not isinstance(focused_output_resp, Response) or not isinstance(
        focused_output_resp.variant, FocusedOutputResponse
    ):
        raise BootstrapError(
            f"FocusedOutput request returned {type(focused_output_resp).__name__}",
            query="focused_output",
        )
    focused_output: Output | None = focused_output_resp.variant.payload

    focused_window_resp = await client.request(FocusedWindowRequest())
    if not isinstance(focused_window_resp, Response) or not isinstance(
        focused_window_resp.variant, FocusedWindowResponse
    ):
        raise BootstrapError(
            f"FocusedWindow request returned {type(focused_window_resp).__name__}",
            query="focused_window",
        )
    focused_window: Window | None = focused_window_resp.variant.payload

    keyboard_resp = await client.request(KeyboardLayoutsRequest())
    if not isinstance(keyboard_resp, Response) or not isinstance(keyboard_resp.variant, KeyboardLayoutsResponse):
        raise BootstrapError(
            f"KeyboardLayouts request returned {type(keyboard_resp).__name__}",
            query="keyboard_layouts",
        )
    keyboard_layouts: KeyboardLayouts = keyboard_resp.variant.payload

    overview_resp = await client.request(OverviewStateRequest())
    if not isinstance(overview_resp, Response) or not isinstance(overview_resp.variant, OverviewStateResponse):
        raise BootstrapError(
            f"OverviewState request returned {type(overview_resp).__name__}",
            query="overview",
        )
    overview: Overview = overview_resp.variant.payload

    compositor_version: str | None = None
    try:
        version_resp = await client.request(VersionRequest())
        if isinstance(version_resp, Response) and isinstance(version_resp.variant, VersionResponse):
            compositor_version = version_resp.variant.payload
    except Exception:
        pass

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


def _apply_event(draft: DraftState, event: object, unknown_event_policy: str) -> None:
    result = reduce_event(draft, event, unknown_event_policy)
    if not result.applied and unknown_event_policy == "fail":
        from niri_state.errors import DesyncError

        raise DesyncError(
            f"Unhandled event type: {type(event).__name__}",
            event_type=type(event).__name__,
        )


def _assert_invariants(snapshot: NiriSnapshot) -> None:
    try:
        assert_invariants(snapshot)
    except Exception as exc:
        raise BootstrapError(
            f"Invariant check failed at revision {snapshot.revision}: {exc}",
            cause=exc,
        ) from exc
