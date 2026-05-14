from __future__ import annotations

from niri_state.observability.logging import get_logger


def test_get_logger_preserves_niri_state_namespace() -> None:
    logger = get_logger("niri_state.store")
    assert logger.name == "niri_state.store"


def test_get_logger_prefixes_non_namespaced_modules() -> None:
    logger = get_logger("custom.module")
    assert logger.name == "niri_state.custom.module"
