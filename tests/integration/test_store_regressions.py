from __future__ import annotations

import pytest

from niri_state.adapters.protocol import UnknownEvent
from niri_state.api.changes import ChangeCause
from niri_state.api.config import NiriStateConfig, UnknownEventPolicy
from niri_state.api.health import HealthState
from niri_state.api.state import NiriState
from tests.factories.bundle import FakeBundle, FakeClient
from tests.factories.protocol import make_window


class _TrackedCloseBundle(FakeBundle):
    def __init__(self, *, client: FakeClient | None = None) -> None:
        super().__init__(client=client)
        self.closed = False

    async def close(self) -> None:
        self.closed = True
        await super().close()


@pytest.mark.asyncio
async def test_connect_closes_bundle_when_bootstrap_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = _TrackedCloseBundle()

    async def _open_bundle() -> _TrackedCloseBundle:
        return bundle

    async def _failing_bootstrap(*_args, **_kwargs):
        raise RuntimeError("bootstrap failed")

    state = NiriState(bundle_factory=_open_bundle)
    monkeypatch.setattr("niri_state.api.state.run_bootstrap", _failing_bootstrap)

    with pytest.raises(RuntimeError, match="bootstrap failed"):
        await state.connect()

    assert bundle.closed is True


@pytest.mark.asyncio
async def test_refresh_open_failure_restores_mutation_loop() -> None:
    first = FakeBundle(client=FakeClient(windows=[make_window(id=100)]))

    async def _open_bundle() -> FakeBundle:
        return first

    state = NiriState(bundle_factory=_open_bundle)
    await state.connect()

    original_task = state._mutation_task
    assert original_task is not None

    async def _failing_open_bundle():
        raise RuntimeError("open failed")

    state._open_bundle = _failing_open_bundle  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="open failed"):
        await state.refresh()

    mutation_task = state._mutation_task
    assert mutation_task is not None
    assert not mutation_task.done()
    await state.close()


@pytest.mark.asyncio
async def test_refresh_publishes_refresh_change_cause() -> None:
    first = FakeBundle(client=FakeClient(windows=[make_window(id=100)]))
    second = FakeBundle(client=FakeClient(windows=[make_window(id=200)]))
    bundles = [first, second]

    async def _open_bundle() -> FakeBundle:
        return bundles.pop(0)

    state = NiriState(bundle_factory=_open_bundle)
    await state.connect()

    published_items = []
    original_publish = state._broadcaster.publish

    async def _capture_publish(published):
        published_items.append(published)
        await original_publish(published)

    state._broadcaster.publish = _capture_publish  # type: ignore[method-assign]

    await state.refresh(cause=ChangeCause.REFRESH)

    assert published_items
    assert published_items[-1].changes.cause is ChangeCause.REFRESH
    await state.close()


@pytest.mark.asyncio
async def test_bootstrap_marks_stale_on_unknown_event_replay() -> None:
    event = UnknownEvent(variant_name="FutureEvent", raw_payload={"k": "v"})
    bundle = FakeBundle(events=(event,))

    async def _open_bundle() -> FakeBundle:
        return bundle

    state = NiriState(
        config=NiriStateConfig(unknown_event_policy=UnknownEventPolicy.STALE), bundle_factory=_open_bundle
    )
    await state.connect()

    assert state.snapshot.health is HealthState.STALE
    assert state.snapshot.diagnostics.desynced is True
    await state.close()
