"""Tests for waveform-visualizer shaping behavior."""

from __future__ import annotations

import numpy as np

from app.config import AppConfig
from app.visualizers.waveform import WaveformVisualizer


def test_waveform_intensity_changes_envelope_strength() -> None:
    config = AppConfig()
    visualizer = WaveformVisualizer(config)
    waveform = np.full(256, 0.14, dtype=np.float32)

    visualizer.set_intensity(config.min_visualizer_intensity)
    low = visualizer._build_envelope(waveform, segment_count=32)

    visualizer.set_intensity(config.max_visualizer_intensity)
    high = visualizer._build_envelope(waveform, segment_count=32)

    assert float(high.max()) > float(low.max())
