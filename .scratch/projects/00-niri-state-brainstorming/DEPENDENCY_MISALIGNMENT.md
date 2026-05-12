# DEPENDENCY_MISALIGNMENT.md

Analysis of alignment issues between the `niri-state` documentation and the actual `niri-pypc` (v0.1.0, upstream `niri-ipc 25.11`) dependency.

---

## 1. `KeyboardLayouts` Field Has No Default for `current_idx`

**niri-pypc source:** `src/niri_pypc/types/generated/models.py`, lines 683–687
```python
class KeyboardLayouts(BaseModel):
    model_config = ConfigDict(populate_by_name=True, strict=False)
    current_idx: int      # NOT optional, no default
    names: list[str]       # NOT optional, no default
```

**Spec (NIRI_STATE_SPEC.md, lines 683–687):**
The spec's `KeyboardLayoutsState` model shows:
```python
class KeyboardLayoutsState(FrozenModel):
    raw: KeyboardLayouts
    current_idx: int | None = None  # nullable with default
    current_name: str | None = None
```

**Overview (Step 5, lines 116–120):**
The overview shows `current_idx: int | None = None` and `current_name: str | None = None`.

**Detail Guide (lines 434–437):**
```python
class KeyboardLayoutsState(FrozenModel):
    raw: KeyboardLayouts
    current_idx: int | None = None
    current_name: str | None = None
```

**Problem:** The underlying `niri_pypc.types.KeyboardLayouts` model has `current_idx: int` with **no default** and **not nullable**. The wrapper `KeyboardLayoutsState` can be nullable, but `raw.current_idx` is always an `int`. Any code that assumes `raw.current_idx` can be `None` (or that `KeyboardLayouts` has defaults) is incorrect.

**Recommendation:** In the `build_initial_snapshot` function and keyboard reducers, assume `raw.current_idx` is always present as an `int`. If the upstream sends no keyboard layouts, the entire `KeyboardLayouts` object may be absent (nullable wrapper), but if present, `current_idx` is always valid. Do not guard with `if raw.current_idx is not None`.

---

## 2. `ConfigLoadedEvent` Has a `failed: bool` Field That Affects State

**niri-pypc source:** `src/niri_pypc/types/generated/event.py`, lines 19–21
```python
class ConfigLoadedEvent(BaseModel):
    failed: bool
```

**Overview (Step 10f, lines 314–319):**
> Handle:
> - `ConfigLoadedEvent`
> 
> This should probably not mutate entity state, but it should produce `ChangeDomain.METADATA` and update diagnostics/summary so consumers can observe successful or failed config loads.

**Problem:** The overview says to handle `ConfigLoadedEvent` but does not mention the `failed` field. The detail guide's root reducer does not handle `ConfigLoadedEvent` at all. More critically, the `failed: bool` field means there are two meaningful states:
- `ConfigLoadedEvent(failed=False)`: config loaded successfully
- `ConfigLoadedEvent(failed=True)`: config load failed

This is not a pure no-op—it has semantic content. Whether it should affect health diagnostics depends on policy, but the field should not be ignored.

**Recommendation:** 
- Add `ConfigLoadedEvent` handling to the root reducer in the detail guide
- The handler should produce `ChangeDomain.METADATA` and optionally update diagnostics with `last_refresh_reason` when `failed=True`
- Either add this to the spec's required event coverage or explicitly document it as a metadata-only no-op

---

## 3. `WindowLayoutsChangedEvent` Uses `tuple[int, WindowLayout]` Not a `Tile` Variant

**niri-pypc source:** `src/niri_pypc/types/generated/event.py`, lines 44–46
```python
class WindowLayoutsChangedEvent(BaseModel):
    changes: list[tuple[int, WindowLayout]]
```

**Detail Guide (conftest.py fixture, line 588):**
```python
layout={"Tile": {}},  # replace with real WindowLayout helper if needed
```

**Problem:** The fixture comment says "replace with real WindowLayout helper if needed" but the conftest uses a dict that would not be a valid `WindowLayout` Pydantic instance. More critically, the event's `changes` field is `list[tuple[int, WindowLayout]]`, meaning each change is a 2-tuple of `(window_id: int, WindowLayout)`.

The overview (lines 279–280) says:
> * `WindowLayoutsChangedEvent`: explicit no-op or raw layout update, but document the decision

But neither document shows the actual type of `changes`.

**Recommendation:**
- Update conftest.py to create proper `WindowLayout` instances:
```python
def make_window_layout(
    tile_size: list[int] = [800, 600],
    window_size: list[int] = [800, 600],
) -> WindowLayout:
    return WindowLayout(
        tile_size=tile_size,
        window_size=window_size,
        window_offset_in_tile=[0, 0],
    )
```
- In `WindowLayoutsChangedEvent` handling, the `changes` is `list[tuple[int, WindowLayout]]` where `tuple[0]` is the window id
- Document that `WindowLayout` fields include: `tile_pos_in_scrolling_layout`, `tile_size`, `window_offset_in_tile`, `window_size`

---

## 4. `WindowFocusTimestampChangedEvent` Carries a `Timestamp` Object

**niri-pypc source:** `src/niri_pypc/types/generated/event.py`, lines 40–43
```python
class WindowFocusTimestampChangedEvent(BaseModel):
    id: int
    focus_timestamp: Timestamp | None = None
```

**Overview (lines 277–280):**
> * `WindowFocusTimestampChangedEvent`: explicit no-op or raw field update, but document the decision

**Problem:** The event carries a full `Timestamp` object (`nanos: int, secs: int`) not just a raw value. Neither document shows the `Timestamp` structure. If the reducer chooses to update `raw.focus_timestamp` on `WindowState`, it needs to know how to construct or match a `Timestamp`.

**Recommendation:**
- Add to conftest.py:
```python
def make_timestamp(secs: int = 0, nanos: int = 0) -> Timestamp:
    return Timestamp(secs=secs, nanos=nanos)
```
- In the root reducer, if handling `WindowFocusTimestampChangedEvent`, update `WindowState.raw.focus_timestamp` using `event.focus_timestamp` (which is `Timestamp | None`)

---

## 5. `OverviewStateResponse.payload` is `Overview` (Not Nullable)

**niri-pypc source:** `src/niri_pypc/types/generated/reply.py`, lines 88–89
```python
class OverviewStateResponse(BaseModel):
    payload: Overview      # NOT Overview | None
```

**Detail Guide (lines 634–636, 710–711):**
```python
overview: Overview | None = None
...
overview=responses.overview.payload,  # This could raise if Overview has no default
```

**Overview Bootstrap (lines 168–170):**
> * `OverviewStateResponse.payload` is `Overview | None`, so derive `focused_output_name` from `payload.name`

**Problem:** The overview incorrectly says `OverviewStateResponse.payload` is `Overview | None`. The actual niri-pypc type is `payload: Overview` (non-nullable). However, `Overview` itself is not a unit struct—it has `is_open: bool`. If the protocol sends an empty or malformed `Overview`, Pydantic validation may fail rather than defaulting to None.

**Also:** The detail guide's `normalize_bootstrap_responses` checks `if responses.overview is None` but does not check if `responses.overview.payload` is valid. The `Overview` model has `is_open: bool` (no default), so if the compositor sends an incomplete Overview object, `Overview.model_validate()` will raise.

**Recommendation:**
- Fix the overview: `OverviewStateResponse.payload` is `Overview`, not `Overview | None`
- In `normalize_bootstrap_responses`, wrap the payload extraction in a try/except or validate the Overview before using it
- The `Overview` model requires `is_open: bool` with no default, so always expect a valid boolean

---

## 6. `VersionResponse.payload` is `str` (Not `str | None`)

**niri-pypc source:** `src/niri_pypc/types/generated/reply.py`, lines 97–98
```python
class VersionResponse(BaseModel):
    payload: str       # NOT str | None
```

**Detail Guide (does not show VersionResponse payload type):**

The detail guide mentions `VersionRequest` but doesn't show how to handle `VersionResponse.payload`.

**Problem:** The version payload is a non-nullable `str`. The implementation should not guard against `None`.

---

## 7. `KeyboardLayouts` Has No `current_name` Field in Protocol

**niri-pypc source:** `src/niri_pypc/types/generated/models.py`, lines 683–687
```python
class KeyboardLayouts(BaseModel):
    model_config = ConfigDict(populate_by_name=True, strict=False)
    current_idx: int
    names: list[str]
```

**Spec (lines 328–330):**
> 3. `current_name` is derived only when `current_idx` and the names/list payload permit it.

**Detail Guide (lines 832–838):**
```python
keyboard_layouts=(
    KeyboardLayoutsState(
        raw=payload.keyboard_layouts,
        current_idx=payload.keyboard_layouts.current_idx,
        current_name=_keyboard_name(
            payload.keyboard_layouts,
            payload.keyboard_layouts.current_idx,
        ),
    )
    ...
)
```

**Problem:** The spec and detail guide are correct: `KeyboardLayouts` does NOT have a `current_name` field. The name must be derived by indexing into `names` with `current_idx`. This is handled correctly in the detail guide's `_keyboard_name` function (lines 733–738), but the spec and overview don't show this distinction explicitly.

**Status:** Correct in all documents. No change needed—this is noted for completeness.

---

## 8. `Output` Model Has No Direct Change Event in niri-pypc 25.11

**niri-pypc source:** `src/niri_pypc/types/generated/event.py` (all events)

The event surface does not include any `OutputConfigChanged` event variant. The only `Output`-related response is `OutputConfigChangedResponse` which is a reply to an `OutputRequest` action, not a spontaneous event.

**Spec (lines 468, 1079):**
The spec correctly classifies outputs as refresh-backed and says "no dedicated direct output-change event in current event surface."

**Problem:** This is correct—no misalignment. Noted for completeness.

---

## 9. `NiriClient.connect()` is NOT Async

**niri-pypc source:** `src/niri_pypc/api/client.py`, lines 28–37
```python
@classmethod
def connect(
    cls,
    config: NiriConfig | None = None,
) -> NiriClient:        # NOT async def
    """Create a client. Validates config but does not open a socket yet."""
    if config is None:
        config = NiriConfig()
    config.resolve_socket_path()
    return cls(config)
```

**Detail Guide (sync/bootstrap.py, step 14):**
The detail guide's `run_bootstrap` function doesn't show the exact `NiriConnectionBundle.open()` call, but the pattern should be consistent.

**Spec (lines 1208–1209):**
> 2. Open a `NiriConnectionBundle` using `niri-pypc`.

**Concept (lines 393–395):**
> 1. Open a `NiriConnectionBundle` via `niri-pypc`.

**Problem:** Neither the spec, concept, nor guides specify whether the bundle open is sync or async. `NiriConnectionBundle.open()` is `async`, but `NiriClient.connect()` is NOT async. This matters for how bootstrap code is structured.

**Recommendation:** In all docs and implementation guides, use `await NiriConnectionBundle.open(config)` not `NiriConnectionBundle.connect(config)`. The bundle's `open()` is the async entry point.

---

## 10. `NiriEventStream.next()` Timeout Raises `NiriTimeoutError`, Not `TimeoutError`

**niri-pypc source:** `src/niri_pypc/api/event_stream.py`, lines 196–236
```python
async def next(self, *, timeout: float | None = None) -> BaseModel:
    ...
    try:
        item = await asyncio.wait_for(self._queue.get(), timeout=read_timeout)
    except TimeoutError:
        raise NiriTimeoutError(
            "No event received within timeout",
            operation="next",
            retryable=True,
        ) from None
```

**Spec (lines 805–816, error mapping):**
> | `NiriTimeoutError` | live event loop | stale transition or `DesyncError` |

**Problem:** The spec correctly maps `NiriTimeoutError` on the live event loop to stale/desync paths. However, the docs don't explicitly show that `NiriEventStream.next()` raises `NiriTimeoutError` (not raw `TimeoutError`) on timeout. The `niri-state` error taxonomy uses `NiriTimeoutError` as a source error to be mapped.

**Recommendation:** Ensure the error mapping table in the spec (section 9, lines 806–816) is correctly understood by the implementation:
- `NiriTimeoutError` from `NiriEventStream.next()` in the live event loop → stale transition or `DesyncError` (NOT `SelectorWaitError`, which is for wait operations)
- `NiriTimeoutError` from `NiriClient.request()` during bootstrap → `BootstrapError`

---

## 11. `NiriClient.request()` Returns Unwrapped Payload (Not `Reply`)

**niri-pypc source:** `src/niri_pypc/api/client.py`, lines 39–71
```python
async def request(self, req: BaseModel, *, timeout: float | None = None) -> Any:
    ...
    reply = Reply.model_validate(decoded)
    return unwrap_reply(reply)     # Returns payload, not Reply
```

**niri-pypc `unwrap_reply` function:** `src/niri_pypc/types/codec.py`, lines 100–124
```python
def unwrap_reply(reply: BaseModel) -> Any:
    variant = getattr(reply, "variant", None)
    if isinstance(variant, OkReply):
        return getattr(variant, "payload", variant)  # Returns payload
    if isinstance(variant, ErrReply):
        raise RemoteError(...)  # Raises on error
```

**Detail Guide (lines 694–698):**
```python
focused_output_name = None
if responses.focused_output.payload is not None:
    focused_output_name = responses.focused_output.payload.name
```

**Problem:** The detail guide correctly accesses `.payload.name` on `FocusedOutputResponse.payload` (which is `Output | None`), but the concept and spec don't explicitly document that `client.request()` unwraps the reply envelope and raises `RemoteError` on error responses.

**Recommendation:** Add to the spec's bootstrap and sync sections:
- `client.request()` raises `RemoteError` if the compositor returns an error reply
- `client.request()` returns the raw payload (e.g., `dict[str, Output]`, `list[Window]`, `KeyboardLayouts`, etc.)
- Responses arrive as typed wrappers (e.g., `FocusedOutputResponse`) that must be matched by variant class and then have `.payload` extracted

---

## 12. `NiriEventStream` Drop-Oldest Behavior: Only One Event Dropped, Then Enqueued

**niri-pypc source:** `src/niri_pypc/api/event_stream.py`, lines 151–160
```python
if config.backpressure_mode == BackpressureMode.DROP_OLDEST:
    try:
        queue.put_nowait(item)
    except asyncio.QueueFull:
        logging.getLogger("niri_pypc.event_stream").warning("Event queue full, dropping oldest event")
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
        queue.put_nowait(item)
```

**Spec (lines 729–731):**
> For the upstream `niri-pypc` event queue:
> - fail-fast overflow is a desync trigger;
> - drop-oldest overflow is incompatible with strict correctness mode.

**Problem:** The spec says drop-oldest is "incompatible with strict correctness mode" and should be treated as a desync trigger in strict mode. However, the niri-pypc implementation logs a warning when it drops an event. This log message could be used by niri-state to detect that events were dropped. The docs don't mention the logging behavior or how to detect drop-oldest events.

**Recommendation:** Add to the spec and implementation guides:
- In strict mode, the upstream event queue must be `FAIL_FAST`. If configured as `DROP_OLDEST` with strict mode, either raise `StateConfigError` or log a warning and downgrade the correctness claim.
- `niri-pypc` logs `"Event queue full, dropping oldest event"` when drop-oldest is active. This can be used for diagnostics/logging but does not prevent the state engine from detecting the correctness issue.
- In strict mode, any drop-oldest activity should be treated as a desync signal (stale transition).

---

## 13. `UnknownEvent` is a Valid Variant in the `Event` Model; `UnknownReply` is Not in the `Reply` Model's Variant Union

**niri-pypc source:** `src/niri_pypc/types/generated/event.py`, lines 118–132
```python
class Event(BaseModel):
    variant: ConfigLoadedEvent | KeyboardLayoutSwitchedEvent | ... | UnknownEvent  # UnknownEvent IS in union

    @model_validator(mode="before")
    @classmethod
    def _decode_external_tag(cls, data: Any) -> dict[str, Any]:
        return {"variant": decode_externally_tagged(
            data, _EVENT_VARIANTS,
            unknown_sentinel=UnknownEvent,  # Uses UnknownEvent sentinel
        )}
```

**niri-pypc source:** `src/niri_pypc/types/generated/reply.py`, lines 46–60
```python
class Reply(BaseModel):
    variant: ErrReply | OkReply | UnknownReply  # UnknownReply IS in union

    @model_validator(mode="before")
    @classmethod
    def _decode_external_tag(cls, data: Any) -> dict[str, Any]:
        return {"variant": decode_externally_tagged(
            data, _REPLY_VARIANTS,
            unknown_sentinel=UnknownReply,  # Uses UnknownReply sentinel
        )}
```

**Spec (lines 862–865):**
> 5. Preserve raw query-only layer payloads only if `include_query_only_layers=True`.
> 6. Unknown reply sentinels during bootstrap are bootstrap failures by default.

**Concept (lines 410–417):**
> Therefore bootstrap must include an explicit normalization stage that:
> - matches each response variant,
> - extracts payload fields,
> - and converts those into a reducer-friendly bootstrap payload.

**Problem:** The spec says "Unknown reply sentinels during bootstrap are bootstrap failures by default." This is correct—the `Reply` model uses `UnknownReply` as the sentinel for unknown reply variants. However, the implementation guide doesn't show how to handle `UnknownReply` during bootstrap.

**Detail Guide (lines 680–693):**
```python
if responses.outputs is None:
    raise BootstrapError("Missing OutputsResponse during bootstrap")
...
if responses.focused_output is None:
    raise BootstrapError("Missing FocusedOutputResponse during bootstrap")
```

**Problem:** The detail guide checks for `None` but doesn't handle the case where the response is an `UnknownReply` sentinel. The `NiriClient.request()` calls `unwrap_reply()` which raises `RemoteError` for `ErrReply` variants, but `UnknownReply` would be returned as a raw `UnknownReply` instance by `unwrap_reply()`. Actually, looking at `unwrap_reply()` more carefully:

```python
def unwrap_reply(reply: BaseModel) -> Any:
    variant = getattr(reply, "variant", None)
    if isinstance(variant, OkReply):
        return getattr(variant, "payload", variant)
    if isinstance(variant, ErrReply):
        raise RemoteError(...)
    raise DecodeError(
        f"Unexpected reply variant: {type(variant).__name__}",
        operation="unwrap_reply",
    )
```

If `variant` is `UnknownReply`, neither `OkReply` nor `ErrReply` matches, and it raises `DecodeError`.

**Recommendation:** Update the error mapping table:
- `DecodeError` from `unwrap_reply()` (including `UnknownReply` cases) → `BootstrapError` during bootstrap
- `RemoteError` from `unwrap_reply()` → `BootstrapError` during bootstrap query

---

## 14. `Workspace` Model Has an `idx` Field Not Mentioned in Spec

**niri-pypc source:** `src/niri_pypc/types/generated/models.py`, lines 764–773
```python
class Workspace(BaseModel):
    active_window_id: int | None = None
    id: int
    idx: int              # NOT mentioned in spec
    is_active: bool
    is_focused: bool
    is_urgent: bool
    name: str | None = None
    output: str | None = None
```

**Spec (lines 267–279):**
```python
class WorkspaceState(FrozenModel):
    id: WorkspaceId
    raw: Workspace
    output_name: OutputName | None = None
    active_window_id: WindowId | None = None
    is_active: bool = False
    is_focused: bool = False
```

**Problem:** The spec doesn't mention `idx` from the protocol `Workspace` model. While `id` is the workspace identifier used for keying, `idx` may be a separate protocol field (e.g., workspace index/position). The detail guide's `build_initial_snapshot` uses `ws.id` and `ws.output`, but doesn't use `idx`.

**Recommendation:** In the spec, note that `Workspace` protocol model includes `idx` which may be used for ordering indexes if protocol ordering is insufficient. In the implementation, preserve `raw.idx` but don't expose it as a separate field unless needed.

---

## 15. `Window` Model Has `focus_timestamp: Timestamp | None` Not in Spec

**niri-pypc source:** `src/niri_pypc/types/generated/models.py`, lines 743–755
```python
class Window(BaseModel):
    app_id: str | None = None
    focus_timestamp: Timestamp | None = None  # NOT in spec
    id: int
    is_floating: bool
    is_focused: bool
    is_urgent: bool
    layout: WindowLayout
    pid: int | None = None
    title: str | None = None
    workspace_id: int | None = None
```

**Spec (lines 290–309):**
```python
class WindowState(FrozenModel):
    id: WindowId
    raw: Window
    workspace_id: WorkspaceId | None = None
    is_focused: bool = False
```

**Problem:** The spec's `WindowState` model does not show `focus_timestamp` from the raw model. The `Window` model includes `focus_timestamp: Timestamp | None` and `title: str | None` (both missing from the spec's explicit enumeration).

**Recommendation:** Add `focus_timestamp` and `title` to the spec's `WindowState` rules:
> Rule 6. `raw.focus_timestamp` carries the last focus timestamp (`Timestamp` with `secs` and `nanos`) if available.
> Rule 7. `raw.title` carries the window title string if available.

---

## 16. `LayerSurface` Has 4 Fields: `namespace`, `output`, `layer`, `keyboard_interactivity`

**niri-pypc source:** `src/niri_pypc/types/generated/models.py`, lines 688–694
```python
class LayerSurface(BaseModel):
    keyboard_interactivity: LayerSurfaceKeyboardInteractivity
    layer: Layer
    namespace: str
    output: str
```

**Spec (lines 880–881):**
> Optional:
> - `LayersRequest`, only when `include_query_only_layers=True`

**Problem:** The spec doesn't enumerate the `LayerSurface` fields. The detail guide's `layers_raw: object | None = None` doesn't specify the actual type.

**Recommendation:** Change `layers_raw: object | None = None` to `layers_raw: list[LayerSurface] | None = None` (matching the `LayersResponse.payload` type from `niri_pypc.types`).

---

## 17. `NiriConfig.event_read_timeout` Defaults to `None` (No Read Timeout)

**niri-pypc source:** `src/niri_pypc/config.py`, lines 18–28
```python
@dataclass(frozen=True, slots=True)
class NiriConfig:
    socket_path: Path | None = None
    connect_timeout: float = 5.0
    request_timeout: float = 10.0
    event_read_timeout: float | None = None   # None = no timeout
    max_frame_size: int = 4 * 1024 * 1024
    event_queue_capacity: int = 256
    backpressure_mode: BackpressureMode = BackpressureMode.DROP_OLDEST
```

**Spec (lines 691–692):**
> 1. `pypc` contains transport/socket/timeouts/event queue settings owned by `niri-pypc`.

**Problem:** The spec doesn't mention `event_read_timeout` specifically. It defaults to `None` meaning the event stream `next()` call has no timeout by default. This is a design decision that affects how niri-state handles the event loop.

**Recommendation:** Document in the spec's config section:
> `event_read_timeout: float | None` - timeout for reading the next event from the stream via `next()`. `None` means block indefinitely. Default in `NiriConfig` is `None`.

---

## 18. `NiriEventStream` Accessible via `bundle.events.next()` (Not `bundle.events.get()`)

**niri-pypc source:** `src/niri_pypc/api/event_stream.py`, line 196
```python
async def next(self, *, timeout: float | None = None) -> BaseModel:
```

**niri-pypc source:** `src/niri_pypc/api/bundle.py`, line 43
```python
@property
def events(self) -> NiriEventStream:
    return self._events
```

**Spec (lines 1425–1429):**
> ```python
> while not closed:
>     event = await bundle.events.next()  # Correct
>     result = apply_event(current_snapshot, event, next_revision=..., context=...)
>     publish(result)
> ```

**Problem:** The spec uses the correct method name `next()`. However, the detail guide's bootstrap section (which I haven't fully seen in the offset read) likely uses this correctly. No real misalignment here—confirmed correct.

---

## 19. Upstream Metadata Accessible from `niri_pypc.types.generated._metadata`

**niri-pypc source:** `src/niri_pypc/types/generated/_metadata.py`, lines 6–16
```python
UPSTREAM_CRATE: str = "niri-ipc"
UPSTREAM_VERSION: str = "25.11"
GENERATOR_VERSION: str = "1"
IR_VERSION: str = "1"
IR_HASH: str = "sha256:..."
SCHEMA_HASHES: dict[str, str] = {
    "request": "sha256:...",
    "reply": "sha256:...",
    "event": "sha256:...",
    "action": "sha256:...",
}
```

**Spec (lines 220–224):**
> 3. `upstream_version` may be read from `niri_pypc.types.generated._metadata` if available.
> 4. `compositor_version` is populated only if a runtime version query succeeds.

**Spec (lines 351–360, `SnapshotDiagnostics`):**
```python
class SnapshotDiagnostics(FrozenModel):
    ...
    upstream_backpressure_mode: str | None = None
    correctness_mode: str | None = None
```

**Problem:** The spec mentions `_metadata` but doesn't enumerate its fields. The `SCHEMA_HASHES` dict is available and could be useful for compatibility checking.

**Recommendation:** Add to the spec's compatibility metadata section:
```python
from niri_pypc.types.generated import (
    UPSTREAM_CRATE,      # "niri-ipc"
    UPSTREAM_VERSION,    # "25.11"
    IR_HASH,             # full IR hash for content-addressed pinning
    SCHEMA_HASHES,       # dict of schema-version hashes per category
)
```

---

## 20. `NiriConnectionBundle.open()` Creates Both Connections Before Returning

**niri-pypc source:** `src/niri_pypc/api/bundle.py`, lines 20–36
```python
@classmethod
async def open(
    cls,
    config: NiriConfig | None = None,
) -> NiriConnectionBundle:
    if config is None:
        config = NiriConfig()

    client = NiriClient.connect(config)
    try:
        events = await NiriEventStream.connect(config)  # Can raise
    except Exception:
        await client.close()  # Cleanup on failure
        raise

    return cls(client, events)
```

**Spec (lines 1207–1218):**
> 1. Normalize config and enforce correctness-mode constraints.
> 2. Open a `NiriConnectionBundle` using `niri-pypc`.
> 3. Confirm the event stream is connected.

**Concept (lines 182–189):**
> Responsibilities:
> - open a coordinated command + event bundle through `niri-pypc`,

**Problem:** The spec and concept don't mention the error isolation behavior in `NiriConnectionBundle.open()`. If the event stream connection fails after the client is created, the client is closed before raising. The spec should note this for bootstrap error handling.

**Recommendation:** Add to the spec's bootstrap sequence:
> Step 2b: If event stream connection fails after client creation, the client is automatically closed by `NiriConnectionBundle.open()` before raising.

---

## 21. `NiriEventStream` Uses `LifecycleManager` with States: INIT → CONNECTING → READY → CLOSING → CLOSED

**niri-pypc source:** `src/niri_pypc/runtime/lifecycle.py`, lines 11–26
```python
class LifecycleState(enum.Enum):
    INIT = "init"
    CONNECTING = "connecting"
    READY = "ready"
    CLOSING = "closing"
    CLOSED = "closed"

_VALID_TRANSITIONS = {
    LifecycleState.INIT: {LifecycleState.CONNECTING},
    LifecycleState.CONNECTING: {LifecycleState.READY, LifecycleState.CLOSED},
    LifecycleState.READY: {LifecycleState.CLOSING},
    LifecycleState.CLOSING: {LifecycleState.CLOSED},
    LifecycleState.CLOSED: set(),  # No transitions from CLOSED
}
```

**Spec (lines 496–502, health semantics):**
> - `CLOSED`: the store was intentionally closed.

**Problem:** The niri-pypc `LifecycleManager` has `is_usable` property (only true at READY) and `is_terminal` property (only true at CLOSED). This is not mentioned in the docs. The event stream uses these internally but they're not exposed as part of the public API.

**Status:** Internal detail. Not a misalignment—just noting it exists.

---

## 22. `BackpressureMode` is `enum.Enum` Not `enum.StrEnum`

**niri-pypc source:** `src/niri_pypc/config.py`, lines 13–15
```python
class BackpressureMode(enum.Enum):  # NOT enum.StrEnum
    DROP_OLDEST = "drop_oldest"
    FAIL_FAST = "fail_fast"
```

**Spec (lines 638–641):**
```python
class StoreOverflowMode(enum.StrEnum):
    DROP_OLDEST = "drop_oldest"
    FAIL_FAST = "fail_fast"
```

**Detail Guide (lines 233–236):**
```python
class StoreOverflowMode(enum.StrEnum):
    DROP_OLDEST = "drop_oldest"
    FAIL_FAST = "fail_fast"
```

**Problem:** `StoreOverflowMode` in niri-state is `enum.StrEnum` (correct for niri-state's own enums), but `BackpressureMode` from niri-pypc is `enum.Enum` (not a StrEnum). The value comparison `config.pypc.backpressure_mode is BackpressureMode.FAIL_FAST` works correctly because `Enum` instances are singletons. However, `BackpressureMode.DROP_OLDEST.value == "drop_oldest"` should also work.

**Status:** No real misalignment. The comparison works. Noted for completeness.

---

## 23. `NiriError` Uses `operation`, `socket_path`, `cause` Fields; `NiriStateError` Uses Different Fields

**niri-pypc source:** `src/niri_pypc/errors.py`, lines 8–24
```python
class NiriError(Exception):
    def __init__(
        self,
        message: str,
        *,
        operation: str | None = None,
        socket_path: str | None = None,
        retryable: bool = False,
        cause: Exception | None = None,
    ) -> None:
```

**Spec (lines 739–752):**
```python
class NiriStateError(Exception):
    def __init__(
        self,
        message: str,
        *,
        revision: Revision | None = None,
        last_good_revision: Revision | None = None,
        health: str | None = None,
        event_type: str | None = None,
        selector_name: str | None = None,
        retryable: bool = False,
    ) -> None:
```

**Spec Error Mapping Table (lines 804–816):**
Maps niri-pypc errors to niri-state errors, but doesn't show the field mapping.

**Problem:** The spec's error mapping table (lines 806–816) doesn't show how to extract context from `niri-pypc` errors when wrapping them. For example:
- `TransportError` has `operation`, `socket_path`, `retryable`, `cause`
- `BootstrapError` from `niri-state` has `revision`, `health`, `event_type`

When mapping `TransportError` to `BootstrapError`, which fields from `TransportError` should be preserved? The spec says "Wrapped `niri-pypc` exceptions must use Python exception chaining" (rule 4), but doesn't specify field translation.

**Recommendation:** Add to the spec's error mapping:
```python
# TransportError (niri-pypc) → BootstrapError (niri-state)
# Fields: operation -> event_type or selector_name; socket_path -> not mapped;
# retryable -> retryable; cause -> cause (chaining)

# NiriTimeoutError (niri-pypc) → BootstrapError (niri-state) [during bootstrap]
# Fields: operation -> event_type; retryable -> retryable; cause -> cause (chaining)

# NiriTimeoutError (niri-pypc) → SelectorWaitError (niri-state) [during wait]
# Fields: operation -> selector_name; retryable -> retryable; cause -> cause (chaining)

# RemoteError (niri-pypc) → BootstrapError (niri-state)
# Fields: operation -> event_type; remote_message -> stored in details;
# retryable -> retryable; cause -> cause (chaining)

# DecodeError (niri-pypc) → BootstrapError (niri-state)
# Fields: operation -> event_type; raw_payload -> stored in details;
# retryable -> False; cause -> cause (chaining)
```

---

## 24. Version Pin Mismatch: `ty>=0.0.1a12` vs `ty>=0.0.1a11`

**niri-pypc pyproject.toml (line 23):**
```
"ty>=0.0.1a11",
```

**Detail Guide (line 66):**
```
"ty>=0.0.1a12",
```

**Overview (line 66):**
```
"ty>=0.1.0",   # NOT aligned with detail or actual dependency
```

**Problem:** The three documents have three different `ty` version specs:
- Spec/Detail Guide: `ty>=0.0.1a12`
- Overview: `ty>=0.1.0`
- Actual niri-pypc: `ty>=0.0.1a11`

**Recommendation:** Use the actual niri-pypc constraint: `ty>=0.0.1a11`. Update the overview to match.

---

## 25. Missing `OutputsResponse.payload` Type: `dict[str, Output]` vs `list[Output]`

**niri-pypc source:** `src/niri_pypc/types/generated/reply.py`, lines 85–86
```python
class OutputsResponse(BaseModel):
    payload: dict[str, Output]   # dict, not list
```

**Detail Guide (line 704):**
```python
outputs=tuple(responses.outputs.payload.values()),
```

**Overview (lines 167–168):**
> * `OutputsResponse.payload` is `dict[str, Output]`

**Spec (line 869):**
The spec doesn't show the payload type but says "preserves protocol identifiers as keys."

**Problem:** The overview and detail guide both correctly show `dict[str, Output]`. However, the overview's statement "preserve protocol identifiers as keys" means the dict keys are output names. The detail guide correctly uses `.values()` to get all outputs.

**Status:** Correctly aligned. Noted for completeness.

---

## 26. `WindowsResponse.payload` is `list[Window]` Not `dict[str, Window]`

**niri-pypc source:** `src/niri_pypc/types/generated/reply.py`, lines 100–101
```python
class WindowsResponse(BaseModel):
    payload: list[Window]   # list, not dict
```

**Overview (line 170):**
> * `WindowsResponse.payload` is `list[Window]`

**Detail Guide (line 706):**
```python
windows=tuple(responses.windows.payload),
```

**Status:** Correctly aligned. Noted for completeness.

---

## 27. `LayersResponse.payload` is `list[LayerSurface]` Not `tuple[LayerSurface, ...]`

**niri-pypc source:** `src/niri_pypc/types/generated/reply.py`, lines 79–80
```python
class LayersResponse(BaseModel):
    payload: list[LayerSurface]   # list, not tuple
```

**Detail Guide (lines 656, 711):**
```python
layers_raw: object | None = None
...
layers_raw=responses.layers.payload if include_query_only_layers and responses.layers else None,
```

**Problem:** The detail guide uses `object | None` for `layers_raw` which is too vague. It should be `list[LayerSurface] | None`. The actual payload is a `list`, not a `tuple` or `object`.

**Recommendation:** Update the detail guide's `layers_raw` type:
```python
layers_raw: list[LayerSurface] | None = None
```

---

## 28. `OutputConfigChangedResponse` Exists but No Corresponding Event

**niri-pypc source:** `src/niri_pypc/types/generated/reply.py`, lines 82–83
```python
class OutputConfigChangedResponse(BaseModel):
    payload: OutputConfigChanged
```

**niri-pypc source:** `src/niri_pypc/types/generated/request.py`, lines 36–38
```python
class OutputRequest(BaseModel):
    action: OutputAction
    output: str
```

**Problem:** `OutputConfigChangedResponse` is a reply to an `OutputRequest` (an action request), not a spontaneous event. The spec's domain classification correctly excludes `OutputConfigChanged` from the event surface, but the type exists in `niri-pypc` and could confuse implementers.

**Status:** Not a misalignment—just a note that `OutputConfigChangedResponse` is a reply type, not an event type.

---

## 29. `PickWindowRequest`, `PickColorRequest` Exist But Are Unused in Bootstrap

**niri-pypc source:** `src/niri_pypc/types/generated/request.py`, lines 46–53
```python
class PickColorRequest(BaseModel):
    pass

class PickWindowRequest(BaseModel):
    pass
```

**Detail Guide (default query plan, lines 155–161):**
The detail guide only lists: OutputsRequest, WorkspacesRequest, WindowsRequest, FocusedOutputRequest, FocusedWindowRequest, KeyboardLayoutsRequest, OverviewStateRequest.

**Problem:** `PickWindowRequest` and `PickColorRequest` are valid requests in niri-pypc but are not part of the niri-state bootstrap query plan. They are interactive/screenshot features, not state queries.

**Status:** Correctly omitted from bootstrap. No action needed—this is a design decision, not a misalignment.

---

## 30. `ReturnErrorRequest` is a Debug/Test Request

**niri-pypc source:** `src/niri_pypc/types/generated/request.py`, lines 52–53
```python
class ReturnErrorRequest(BaseModel):
    pass
```

**Problem:** This is a debug/testing request. The docs correctly don't mention it.

---

## Summary of Findings

| # | Issue | Severity | Documents |
|---|-------|----------|-----------|
| 1 | `KeyboardLayouts.current_idx` has no default, is non-nullable | High | All docs |
| 2 | `ConfigLoadedEvent.failed` field not documented | Medium | Overview, Spec |
| 3 | `WindowLayoutsChangedEvent.changes` type not shown | Medium | Overview, Detail |
| 4 | `WindowFocusTimestampChangedEvent.focus_timestamp: Timestamp` not documented | Medium | Overview |
| 5 | `OverviewStateResponse.payload` is non-nullable `Overview` | Medium | Overview |
| 6 | `VersionResponse.payload` is `str` (not nullable) | Low | Detail |
| 7 | `KeyboardLayouts` has no `current_name` (correct, just noted) | None | Already aligned |
| 8 | `Output` has no direct change event (correct, just noted) | None | Already aligned |
| 9 | `NiriClient.connect()` is NOT async; `NiriConnectionBundle.open()` IS | Medium | Spec, Concept, Detail |
| 10 | `NiriEventStream.next()` raises `NiriTimeoutError` not `TimeoutError` | Low | Spec, Concept |
| 11 | `NiriClient.request()` raises `RemoteError` on error replies, returns payload on OK | Medium | Spec, Concept |
| 12 | Drop-oldest logs warning; no explicit overflow detection API | Low | Spec |
| 13 | `UnknownReply` in `Reply` model; `UnknownEvent` in `Event` model | Medium | Spec, Detail |
| 14 | `Workspace.idx` field in protocol model not in spec | Low | Spec |
| 15 | `Window.focus_timestamp: Timestamp` and `Window.title` not in spec | Low | Spec |
| 16 | `layers_raw` type too vague (`object` vs `list[LayerSurface]`) | Low | Detail |
| 17 | `event_read_timeout` defaults to `None` (no timeout) not documented | Low | Spec |
| 18 | `bundle.events.next()` correct (noted for verification) | None | Already aligned |
| 19 | Upstream metadata fields (`SCHEMA_HASHES`, `IR_HASH`) not enumerated | Low | Spec |
| 20 | `NiriConnectionBundle.open()` error isolation behavior not documented | Low | Spec |
| 21 | `LifecycleManager` states not mentioned (internal) | None | Internal only |
| 22 | `BackpressureMode` is `Enum` not `StrEnum` (works correctly) | None | No action |
| 23 | Error field translation between `NiriError` and `NiriStateError` not shown | Medium | Spec |
| 24 | `ty` version: three different values across docs | Medium | All docs |
| 25 | `OutputsResponse.payload` is `dict[str, Output]` (correctly aligned) | None | Already aligned |
| 26 | `WindowsResponse.payload` is `list[Window]` (correctly aligned) | None | Already aligned |
| 27 | `layers_raw` should be `list[LayerSurface]` not `object` | Low | Detail |
| 28 | `OutputConfigChangedResponse` exists but no event (noted) | None | No action |
| 29 | `PickWindowRequest`/`PickColorRequest` unused (correctly omitted) | None | Already aligned |
| 30 | `ReturnErrorRequest` exists (debug, correctly omitted) | None | Already aligned |

**Priority:** Issues #1, #9, #11, #13, #23, #24 are the most likely to cause incorrect implementations.

---

*Generated from deep analysis of `niri-pypc` (v0.1.0, upstream `niri-ipc 25.11`) source code and cross-reference with `NIRI_STATE_SPEC.md`, `NIRI_STATE_CONCEPT.md`, `NIRI_STATE_IMPLEMENTATION_GUIDE_OVERVIEW.md`, and `NIRI_STATE_IMPLEMENTATION_GUIDE_DETAIL.md`.*