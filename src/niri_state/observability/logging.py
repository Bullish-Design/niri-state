from __future__ import annotations

import logging
from typing import Final

_LOGGER_NAMESPACE: Final[str] = "niri_state"


def get_logger(module_name: str) -> logging.Logger:
    if module_name == _LOGGER_NAMESPACE or module_name.startswith(f"{_LOGGER_NAMESPACE}."):
        return logging.getLogger(module_name)
    return logging.getLogger(f"{_LOGGER_NAMESPACE}.{module_name}")
