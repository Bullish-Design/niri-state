"""Public API module for niri_state.

This module contains the public-facing interfaces that external consumers
interact with. It may depend on core modules through stable interfaces.
"""

from niri_state.core.broadcaster import PublishedState

__all__ = ["PublishedState"]
