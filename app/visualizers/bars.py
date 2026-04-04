"""Spectrum bar visualizer."""

from __future__ import annotations

from PySide6.QtCore import QLineF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPen

from app.dsp import spectrum_to_bars
from app.models import AnalysisFrame
from app.visualizers.base import BaseVisualizer


class BarsVisualizer(BaseVisualizer):
    """Draw a log-spaced spectrum analyzer."""

    mode_id = "bars"
    display_name = "Spectrum Bars"

    def render(self, painter: QPainter, rect: QRectF, frame: AnalysisFrame) -> None:
        bars = spectrum_to_bars(
            frame.spectrum,
            sample_rate=frame.sample_rate,
            bar_count=self.config.bar_count,
            min_frequency_hz=self.config.min_display_frequency_hz,
        )
        if bars.size == 0:
            return

        theme = self.config.theme
        padding_x = rect.width() * 0.06
        top = rect.top() + rect.height() * 0.12
        bottom = rect.bottom() - rect.height() * 0.07
        inner_width = rect.width() - padding_x * 2.0
        gap = max(3.0, inner_width * 0.004)
        bar_width = max(4.0, (inner_width - gap * (bars.size - 1)) / bars.size)
        max_height = bottom - top

        glow_height = rect.height() * 0.18 * max(frame.bands.bass, 0.06)
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
            height = max(2.0, max_height * amount)
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
