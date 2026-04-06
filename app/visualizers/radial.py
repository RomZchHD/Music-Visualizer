"""Circular spectrum visualizer."""

from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QPainter, QPen, QRadialGradient

from app.config import AppConfig
from app.dsp import spectrum_to_bars
from app.models import AnalysisFrame
from app.visualizers.base import BaseVisualizer


class RadialVisualizer(BaseVisualizer):
    """Draw a radial spectrum made from outward strokes."""

    mode_id = "radial"
    display_name = "Radial Spectrum"

    def __init__(self, config: AppConfig) -> None:
        super().__init__(config)
        self._display_bars: np.ndarray | None = None
        self._energy_floor: np.ndarray | None = None
        self._energy_peak: np.ndarray | None = None

    def render(self, painter: QPainter, rect: QRectF, frame: AnalysisFrame) -> None:
        raw_bars = spectrum_to_bars(
            frame.spectrum,
            sample_rate=frame.sample_rate,
            bar_count=self.config.radial_bar_count,
            min_frequency_hz=self.config.min_display_frequency_hz,
        )
        if raw_bars.size == 0:
            return
        target_bars = self._prepare_levels(raw_bars)
        bars = self.animate_levels(self._display_bars, target_bars)
        self._display_bars = bars

        theme = self.config.theme
        center = rect.center()
        size = min(rect.width(), rect.height())
        inner_radius = size * 0.18
        stroke_extent = size * 0.18

        orb_gradient = QRadialGradient(center, inner_radius * 1.5)
        orb_gradient.setColorAt(0.0, self.with_alpha(theme.accent_primary, 120))
        orb_gradient.setColorAt(0.5, self.with_alpha(theme.accent_secondary, 70))
        orb_gradient.setColorAt(1.0, self.with_alpha(theme.background_bottom, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(orb_gradient))
        painter.drawEllipse(center, inner_radius * 1.1, inner_radius * 1.1)

        ring_pen = QPen(self.with_alpha(theme.panel_border, 140), 2.0)
        painter.setPen(ring_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(center, inner_radius, inner_radius)

        for index, value in enumerate(bars):
            angle = (index / bars.size) * math.tau - math.pi / 2.0
            direction_x = math.cos(angle)
            direction_y = math.sin(angle)
            start = QPointF(
                center.x() + direction_x * inner_radius,
                center.y() + direction_y * inner_radius,
            )
            end = QPointF(
                center.x() + direction_x * (inner_radius + stroke_extent * (0.15 + float(value))),
                center.y() + direction_y * (inner_radius + stroke_extent * (0.15 + float(value))),
            )
            color = self.mix_colors(
                theme.accent_secondary,
                theme.accent_warm,
                index / max(1, bars.size - 1),
            )
            pen = QPen(color, 2.4)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(start, end)

    def _prepare_levels(self, raw_bars: np.ndarray) -> np.ndarray:
        levels, self._energy_floor, self._energy_peak = self.normalize_spectrum_motion(
            raw_bars,
            self._energy_floor,
            self._energy_peak,
        )
        return levels
