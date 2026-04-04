"""Waveform oscilloscope visualizer."""

from __future__ import annotations

from app.dsp import resample_for_display
from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

from app.models import AnalysisFrame
from app.visualizers.base import BaseVisualizer


class WaveformVisualizer(BaseVisualizer):
    """Draw a smoothed oscilloscope-style waveform."""

    mode_id = "waveform"
    display_name = "Waveform"

    def render(self, painter: QPainter, rect: QRectF, frame: AnalysisFrame) -> None:
        waveform = frame.waveform
        if waveform.size == 0:
            return
        target_points = max(96, min(waveform.size, int(rect.width())))
        if target_points != waveform.size:
            waveform = resample_for_display(waveform, target_points)

        theme = self.config.theme
        left = rect.left() + rect.width() * 0.05
        right = rect.right() - rect.width() * 0.05
        top = rect.top() + rect.height() * 0.18
        bottom = rect.bottom() - rect.height() * 0.18
        center_y = (top + bottom) / 2.0
        amplitude = (bottom - top) / 2.0

        adaptive_gain = min(6.0, 1.0 / max(frame.peak, 0.12)) * self.intensity
        normalized = waveform * adaptive_gain

        painter.setPen(QPen(self.with_alpha(theme.panel_border, 90), 1.0))
        painter.drawLine(QLineF(left, center_y, right, center_y))

        for index in range(1, 4):
            ratio = index / 4.0
            offset = amplitude * ratio
            painter.drawLine(QLineF(left, center_y - offset, right, center_y - offset))
            painter.drawLine(QLineF(left, center_y + offset, right, center_y + offset))

        path = QPainterPath(QPointF(left, center_y - float(normalized[0]) * amplitude))
        x_step = (right - left) / max(1, waveform.size - 1)
        for index, value in enumerate(normalized[1:], start=1):
            x = left + index * x_step
            y = center_y - float(max(-1.0, min(1.0, value))) * amplitude
            path.lineTo(x, y)

        glow_pen = QPen(self.with_alpha(theme.accent_secondary, 70), 8.0)
        glow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        glow_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(glow_pen)
        painter.drawPath(path)

        line_pen = QPen(QColor(theme.accent_primary), 2.6)
        line_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        line_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(line_pen)
        painter.drawPath(path)
