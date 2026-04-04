"""Visualizer registry."""

from __future__ import annotations

from app.config import AppConfig
from app.visualizers.bars import BarsVisualizer
from app.visualizers.radial import RadialVisualizer
from app.visualizers.waveform import WaveformVisualizer


def build_visualizers(config: AppConfig) -> list:
    """Construct the default visualizer instances."""

    return [
        BarsVisualizer(config),
        WaveformVisualizer(config),
        RadialVisualizer(config),
    ]

