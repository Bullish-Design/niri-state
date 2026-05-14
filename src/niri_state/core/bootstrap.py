from __future__ import annotations

import asyncio
import contextlib

from niri_pypc.types.generated._metadata import UPSTREAM_VERSION as PYPC_SCHEMA_VERSION
from pydantic import BaseModel, ConfigDict

from niri_state.adapters.protocol import (
    FocusedOutputRequest,
    FocusedWindowRequest,
    KeyboardLayouts,
    KeyboardLayoutsRequest,
    NiriClient,
    NiriConnectionBundle,
    Output,
    OutputsRequest,
    Overview,
    OverviewStateRequest,
    VersionRequest,
    Window,
    WindowsRequest,
    Workspace,
    WorkspacesRequest,
)
from niri_state.api.changes import ChangeSet, bootstrap_changeset
from niri_state.api.config import InvariantFailurePolicy, NiriStateConfig
from niri_state.api.errors import BootstrapError, InvariantError
from niri_state.api.health import HealthState
from niri_state.api.snapshot import Snapshot
from niri_state.core.diagnostics import Compatibility, Diagnostics, with_invariant_violations, with_note
from niri_state.core.engine_state import EngineState
from niri_state.core.invariants import collect_invariant_violations
from niri_state.core.reconcile import reconcile
from niri_state.core.reducers import reduce_event
from niri_state.observability.logging import get_logger

_LOGGER = get_logger(__name__)


class BootstrapOutcome(BaseModel, frozen=True):
    model_config = ConfigDict(
        extra="forbid",
        arbitrary_types_allowed=True,
    )

    engine: EngineState
    initial_snapshot: Snapshot
    initial_changeset: ChangeSet


async def query_outputs(client: NiriClient) -> dict[str, Output]:
    response = await client.request(OutputsRequest())
    return response.payload


async def query_workspaces(client: NiriClient) -> list[Workspace]:
    response = await client.request(WorkspacesRequest())
    return response.payload


async def query_windows(client: NiriClient) -> list[Window]:
    response = await client.request(WindowsRequest())
    return response.payload


async def query_focused_output(client: NiriClient) -> Output | None:
    response = await client.request(FocusedOutputRequest())
    return response.payload


async def query_focused_window(client: NiriClient) -> Window | None:
    response = await client.request(FocusedWindowRequest())
    return response.payload


async def query_keyboard_layouts(client: NiriClient) -> KeyboardLayouts:
    response = await client.request(KeyboardLayoutsRequest())
    return response.payload


async def query_overview(client: NiriClient) -> Overview:
    response = await client.request(OverviewStateRequest())
    return response.payload


async def query_version(client: NiriClient) -> str | None:
    response = await client.request(VersionRequest())
    return response.payload


async def build_initial_engine_state(client: NiriClient) -> EngineState:
    (
        outputs,
        workspaces,
        windows,
        focused_output,
        focused_window,
        keyboard_layouts,
        overview,
        version,
    ) = await asyncio.gather(
        query_outputs(client),
        query_workspaces(client),
        query_windows(client),
        query_focused_output(client),
        query_focused_window(client),
        query_keyboard_layouts(client),
        query_overview(client),
        query_version(client),
    )

    engine = EngineState.empty()
    engine.outputs = dict(outputs)
    engine.workspaces = {workspace.id: workspace for workspace in workspaces}
    engine.windows = {window.id: window for window in windows}
    engine.keyboard_layouts = keyboard_layouts
    engine.overview = overview
    engine.health = HealthState.BOOTSTRAPPING
    engine.diagnostics = Diagnostics()
    engine.compatibility = Compatibility(
        niri_version=version,
        schema_version=PYPC_SCHEMA_VERSION,
        warnings=()
        if version in {None, PYPC_SCHEMA_VERSION}
        else (f"runtime niri version {version} differs from schema version {PYPC_SCHEMA_VERSION}",),
    )

    if focused_window is not None:
        engine.focused_window_id = focused_window.id
        engine.focused_workspace_id = focused_window.workspace_id

    if focused_output is not None and engine.focused_workspace_id is not None:
        workspace = engine.workspaces.get(engine.focused_workspace_id)
        if workspace is not None and workspace.output != focused_output.name:
            engine.diagnostics = with_note(
                engine.diagnostics,
                note="focused_output query disagreed with focused workspace output",
            )

    reconcile(engine)
    return engine


def _apply_bootstrap_invariant_policy(
    engine: EngineState,
    *,
    snapshot: Snapshot,
    config: NiriStateConfig,
) -> Snapshot:
    violations = collect_invariant_violations(snapshot)
    if not violations:
        return snapshot

    if config.invariant_failure_policy is InvariantFailurePolicy.FAIL:
        raise InvariantError(
            "bootstrap snapshot invariants violated",
            violations=violations,
            revision=snapshot.revision,
            operation="bootstrap",
        )

    engine.diagnostics = with_invariant_violations(
        engine.diagnostics,
        violations=violations,
    )
    engine.health = HealthState.STALE
    reconcile(engine)
    return engine.freeze(revision=snapshot.revision, timestamp=snapshot.timestamp)


async def run_bootstrap(
    bundle: NiriConnectionBundle,
    *,
    config: NiriStateConfig,
) -> BootstrapOutcome:
    try:
        _LOGGER.info("bootstrap started")
        buffered_events: list[object] = []

        async def _buffer_events() -> None:
            async for event in bundle.events:
                buffered_events.append(event)

        buffer_task = asyncio.create_task(_buffer_events())
        await asyncio.sleep(0)
        try:
            engine = await build_initial_engine_state(bundle.client)
        finally:
            buffer_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await buffer_task

        for event in buffered_events:
            result = reduce_event(engine, event, config=config, revision=0)
            if result.marked_desync:
                _LOGGER.warning("bootstrap replay marked state as desynced")
                engine.health = HealthState.STALE
            reconcile(engine)

        if engine.health is HealthState.BOOTSTRAPPING:
            engine.health = HealthState.LIVE

        snapshot = engine.freeze(revision=1)
        snapshot = _apply_bootstrap_invariant_policy(
            engine,
            snapshot=snapshot,
            config=config,
        )

        return BootstrapOutcome(
            engine=engine,
            initial_snapshot=snapshot,
            initial_changeset=bootstrap_changeset(revision=snapshot.revision),
        )
    except InvariantError:
        _LOGGER.exception("bootstrap invariant validation failed")
        raise
    except Exception as exc:
        _LOGGER.exception("bootstrap failed")
        raise BootstrapError(
            "failed to bootstrap initial niri state",
            operation="bootstrap",
            retryable=True,
            cause=exc,
        ) from exc
    finally:
        _LOGGER.info("bootstrap finished")
