"""Compatibility shim - package moved to niri_state.api.selectors.

This module is deprecated. Please import from niri_state.api.selectors instead.
"""

from niri_state.api import selectors

__all__ = [
    "aggregates",
    "focus",
    "keyboard",
    "outputs",
    "overview",
    "windows",
    "workspaces",
]

aggregates = selectors.aggregates
focus = selectors.focus
keyboard = selectors.keyboard
outputs = selectors.outputs
overview = selectors.overview
windows = selectors.windows
workspaces = selectors.workspaces
