"""Spectrum bar visualizer."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QLineF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPen

from app.config import AppConfig
from app.dsp import spectrum_to_bars
from app.models import AnalysisFrame
from app.visualizers.base import BaseVisualizer


class BarsVisualizer(BaseVisualizer):
    """Draw a log-spaced spectrum analyzer."""

    mode_id = "bars"
    display_name = "Spectrum Bars"

    def __init__(self, config: AppConfig) -> None:
        super().__init__(config)
        self._display_bars: np.ndarray | None = None
        self._energy_floor: np.ndarray | None = None
        self._energy_peak: np.ndarray | None = None

    def render(self, painter: QPainter, rect: QRectF, frame: AnalysisFrame) -> None:
        raw_bars = spectrum_to_bars(
            frame.spectrum,
            sample_rate=frame.sample_rate,
            bar_count=self.config.bar_count,
            min_frequency_hz=self.config.min_display_frequency_hz,
        )
        if raw_bars.size == 0:
            return
        target_bars = self._prepare_levels(raw_bars)
        bars = self.animate_levels(self._display_bars, target_bars)
        self._display_bars = bars

        theme = self.config.theme
        padding_x = rect.width() * 0.06
        top = rect.top() + rect.height() * 0.12
        bottom = rect.bottom() - rect.height() * 0.07
        inner_width = rect.width() - padding_x * 2.0
        gap = max(3.0, inner_width * 0.004)
        bar_width = max(4.0, (inner_width - gap * (bars.size - 1)) / bars.size)
        max_height = bottom - top

        glow_height = rect.height() * 0.18 * max(frame.bands.bass * (0.9 + self.intensity_ratio() * 0.4), 0.06)
        painter.fillRect(
            QRectF(rect.left(), bottom - glow_height, rect.width(), glow_height),
            self.with_alpha(theme.accent_bass, 40),
        )

        painter.setPen(QPen(self.with_alpha(theme.panel_border, 80), 1.0))
        grid_lines = 4
        for index in range(grid_lines + 1):
            y = top + max_height * index / grid_lines
            painter.drawLine(QLineF(rect.left(), y, rect.right(), y))

        for index, value in enumerate(bars):
            amount = float(value)
            display_amount = min(1.0, pow(amount, 1.05) * 0.84)
            height = max(2.0, max_height * display_amount)
            x = rect.left() + padding_x + index * (bar_width + gap)
            y = bottom - height

            gradient = QLinearGradient(x, y, x, bottom)
            gradient.setColorAt(
                0.0,
                self.mix_colors(
                    theme.accent_secondary,
                    theme.accent_warm,
                    index / max(1, bars.size - 1),
                ),
            )
            gradient.setColorAt(
                1.0,
                self.mix_colors(
                    theme.accent_primary,
                    theme.accent_secondary,
                    index / max(1, bars.size - 1),
                ),
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(gradient))
            painter.drawRoundedRect(QRectF(x, y, bar_width, height), 5.0, 5.0)

            cap_y = max(top, y - 8.0)
            painter.setBrush(self.with_alpha(QColor(theme.text_primary), 140))
            painter.drawRoundedRect(QRectF(x, cap_y, bar_width, 3.0), 1.5, 1.5)

    def _prepare_levels(self, raw_bars: np.ndarray) -> np.ndarray:
        values = np.clip(np.asarray(raw_bars, dtype=np.float32), 0.0, 1.0)
        ratio = self.intensity_ratio()

        if values.size > 1:
            neighbor_support = values.copy()
            neighbor_support[0] = max(values[0], values[1] * 0.42)
            neighbor_support[-1] = max(values[-1], values[-2] * 0.42)
            if values.size > 2:
                neighbor_support[1:-1] = np.maximum(
                    values[1:-1],
                    (values[:-2] + values[2:]) * 0.42,
                )
            values = (values * 0.84 + neighbor_support * 0.16).astype(np.float32)

        if self._energy_floor is None or self._energy_floor.shape != values.shape:
            self._energy_floor = values * 0.52
        else:
            falling = values < self._energy_floor
            floor_drop = 0.34 - ratio * 0.08
            floor_rise = 0.982 - ratio * 0.03
            self._energy_floor = np.where(
                falling,
                self._energy_floor * floor_drop + values * (1.0 - floor_drop),
                self._energy_floor * floor_rise + values * (1.0 - floor_rise),
            ).astype(np.float32)

        if self._energy_peak is None or self._energy_peak.shape != values.shape:
            self._energy_peak = np.maximum(values, self._energy_floor + 0.22).astype(np.float32)
        else:
            rising = values > self._energy_peak
            peak_attack = 0.34 - ratio * 0.16
            peak_release = 0.86 - ratio * 0.16
            self._energy_peak = np.where(
                rising,
                self._energy_peak * peak_attack + values * (1.0 - peak_attack),
                self._energy_peak * peak_release + values * (1.0 - peak_release),
            ).astype(np.float32)
            self._energy_peak = np.maximum(
                self._energy_peak,
                self._energy_floor + 0.16,
            ).astype(np.float32)

        span = np.maximum(self._energy_peak - self._energy_floor, 0.16)
        motion = np.clip((values - self._energy_floor) / span, 0.0, 1.0)
        motion = np.power(motion, 0.96 - ratio * 0.22)

        local_lift_floor = np.minimum(self._energy_floor, values * (0.7 - ratio * 0.08))
        local_lift = np.clip(values - local_lift_floor, 0.0, 1.0)
        local_lift = np.power(local_lift, 0.78)

        body = np.power(values, 1.14 - ratio * 0.22)
        combined = np.clip(
            body * (0.22 + (1.0 - ratio) * 0.02)
            + motion * (0.62 + ratio * 0.12)
            + local_lift * (0.3 + ratio * 0.04),
            0.0,
            1.0,
        )
        combined = combined / (0.93 + combined * 0.07)
        contrast = 0.9 + ratio * 0.22
        combined = np.clip((combined - 0.5) * contrast + 0.5, 0.0, 1.0)
        combined = np.clip(combined * 0.9, 0.0, 1.0)
        return self.shape_levels(combined)
