from __future__ import annotations


def make_event_frame(payload: str) -> bytes:
    return payload.encode("utf-8")
