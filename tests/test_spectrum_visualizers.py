"""Tests for spectrum-based visualizer shaping."""

from __future__ import annotations

import numpy as np

from app.config import AppConfig
from app.visualizers.bars import BarsVisualizer


def test_bars_visualizer_intensity_changes_response_more_than_average_height() -> None:
    config = AppConfig(bar_count=16)
    raw_a = np.linspace(0.82, 0.18, config.bar_count, dtype=np.float32)
    raw_b = raw_a.copy()
    raw_b[:5] -= 0.18
    raw_b = np.clip(raw_b, 0.0, 1.0)

    low = BarsVisualizer(config)
    low.set_intensity(config.min_visualizer_intensity)
    low_target_a = low._prepare_levels(raw_a)
    low_display_a = low.animate_levels(None, low_target_a)
    low_target_b = low._prepare_levels(raw_b)
    low_levels = low.animate_levels(low_display_a, low_target_b)

    high = BarsVisualizer(config)
    high.set_intensity(config.max_visualizer_intensity)
    high_target_a = high._prepare_levels(raw_a)
    high_display_a = high.animate_levels(None, high_target_a)
    high_target_b = high._prepare_levels(raw_b)
    high_levels = high.animate_levels(high_display_a, high_target_b)

    assert float(low_levels.mean()) > float(high_levels.mean()) * 0.78
    assert float(np.mean(np.abs(high_levels[:5] - low_levels[:5]))) > 0.005


def test_bars_visualizer_bass_plateau_can_drop_after_sustained_peak() -> None:
    config = AppConfig(bar_count=16)
    visualizer = BarsVisualizer(config)
    visualizer.set_intensity(config.default_visualizer_intensity)

    sustained = np.concatenate(
        [
            np.full(5, 0.92, dtype=np.float32),
            np.linspace(0.72, 0.18, 11, dtype=np.float32),
        ]
    )
    dropped = sustained.copy()
    dropped[:5] -= 0.16

    first_target = visualizer._prepare_levels(sustained)
    first_display = visualizer.animate_levels(None, first_target)
    second_target = visualizer._prepare_levels(np.clip(dropped, 0.0, 1.0))
    second_display = visualizer.animate_levels(first_display, second_target)

    assert float(np.max(first_display[:4])) < 0.95
    assert float(np.mean(first_display[:4] - second_display[:4])) > 0.04
