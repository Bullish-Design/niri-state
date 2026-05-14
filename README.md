# niri-state

State modeling and selector helpers for the Niri compositor.

## Quick start

```python
import asyncio

from niri_state import NiriState, NiriStateConfig


async def main() -> None:
    state = await NiriState.open(NiriStateConfig())
    try:
        print(state.snapshot)

        async for published in state.subscribe():
            print(
                published.snapshot.revision,
                published.snapshot.health,
                published.changes,
            )
            break
    finally:
        await state.close()


asyncio.run(main())
```

## Lifecycle notes

- `NiriState.open(config)` constructs and connects in one call.
- `NiriState(config).start()` is the instance-style alternative.
- `subscribe()` yields `PublishedState` values (`snapshot` + `changes`).
- `subscribe()` yields the current snapshot first, then future publications.
- `watch()` yields snapshots and suppresses duplicate initial publication revisions.
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

## Resync behavior

When `resync_policy=ResyncPolicy.AUTO`, desync-triggered resync attempts use:

- `resync_max_attempts`: maximum refresh attempts per resync request
- `resync_backoff_base`: exponential backoff base in seconds (`base * 2^attempt_index`)
