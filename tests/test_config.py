from __future__ import annotations

import pytest
from niri_pypc import BackpressureMode, NiriConfig

from niri_state.config import (
    CorrectnessMode,
    NiriStateConfig,
    normalize_config,
)


class TestNormalizeConfig:
    def test_strict_rewrites_backpressure_to_fail_fast(self) -> None:
        config = NiriStateConfig(
            pypc=NiriConfig(backpressure_mode=BackpressureMode.DROP_OLDEST),
            correctness_mode=CorrectnessMode.STRICT,
        )
        result = normalize_config(config)
        assert result.pypc.backpressure_mode is BackpressureMode.FAIL_FAST

    def test_strict_preserves_already_fail_fast(self) -> None:
        config = NiriStateConfig(
            pypc=NiriConfig(backpressure_mode=BackpressureMode.FAIL_FAST),
            correctness_mode=CorrectnessMode.STRICT,
        )
        result = normalize_config(config)
        assert result.pypc.backpressure_mode is BackpressureMode.FAIL_FAST

    def test_best_effort_leaves_backpressure_unchanged(self) -> None:
        config = NiriStateConfig(
            pypc=NiriConfig(backpressure_mode=BackpressureMode.DROP_OLDEST),
            correctness_mode=CorrectnessMode.BEST_EFFORT,
        )
        result = normalize_config(config)
        assert result.pypc.backpressure_mode is BackpressureMode.DROP_OLDEST

    def test_config_is_frozen(self) -> None:
        config = NiriStateConfig()
        with pytest.raises(AttributeError):
            config.correctness_mode = CorrectnessMode.STRICT
