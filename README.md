# niri-state

State modeling and selector helpers for the Niri compositor.

## Quick start

```python
import asyncio

from niri_state import NiriState, NiriStateConfig


async def main() -> None:
    state = await NiriState.start(NiriStateConfig())
    try:
        print(state.snapshot)

        async for snapshot, changeset in state.subscribe():
            print(snapshot.revision, snapshot.health, changeset)
            break
    finally:
        await state.close()


asyncio.run(main())
```

## Lifecycle notes

- `NiriState.start()` performs bootstrap and starts the mutation loop.
- `subscribe()` yields the current snapshot first, then future publications.
- `refresh()` preserves monotonic revisions and emits resync lifecycle changes.
- `close()` is idempotent and wakes blocked subscribers.

## Health states

`BOOTSTRAPPING -> LIVE -> (STALE | RESYNCING | CLOSED)`

Resync may transition back to `LIVE`, `STALE`, `FAILED`, or `CLOSED`.

## Unknown events

Behavior is controlled by `UnknownEventPolicy`:

- `STALE`: mark health stale and continue
- `FAIL`: raise desync error
- `IGNORE`: ignore and continue
