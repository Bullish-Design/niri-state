"""Compatibility shim - module moved to niri_state.api.state.

This module is deprecated. Please import from niri_state.api.state instead.
"""

from niri_state.api.state import NiriState, run_bootstrap  # noqa: F401

__all__ = ["NiriState", "run_bootstrap"]
