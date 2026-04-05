"""Waveform oscilloscope visualizer."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen

from app.config import AppConfig
from app.models import AnalysisFrame
from app.visualizers.base import BaseVisualizer


class WaveformVisualizer(BaseVisualizer):
    """Draw a smoothed oscilloscope-style waveform."""

    mode_id = "waveform"
    display_name = "Waveform"

    def __init__(self, config: AppConfig) -> None:
        super().__init__(config)
        self._display_envelope: np.ndarray | None = None

    def render(self, painter: QPainter, rect: QRectF, frame: AnalysisFrame) -> None:
        waveform = frame.waveform
        if waveform.size == 0:
            return

        theme = self.config.theme
        left = rect.left() + rect.width() * 0.05
        right = rect.right() - rect.width() * 0.05
        top = rect.top() + rect.height() * 0.22
        bottom = rect.bottom() - rect.height() * 0.22
        center_y = (top + bottom) / 2.0
        amplitude = (bottom - top) / 2.0

        envelope = self._build_envelope(waveform, segment_count=max(48, min(120, int(rect.width() / 14.0))))
        display_envelope = self._animate_envelope(envelope)

        painter.setPen(QPen(self.with_alpha(theme.panel_border, 90), 1.0))
        painter.drawLine(QLineF(left, center_y, right, center_y))

        for index in range(1, 3):
            ratio = index / 3.0
            offset = amplitude * ratio
            painter.drawLine(QLineF(left, center_y - offset, right, center_y - offset))
            painter.drawLine(QLineF(left, center_y + offset, right, center_y + offset))

        x_step = (right - left) / max(1, display_envelope.size - 1)
        upper_points: list[QPointF] = []
        lower_points: list[QPointF] = []
        for index, value in enumerate(display_envelope):
            x = left + index * x_step
            offset = float(np.clip(value, 0.0, 1.0)) * amplitude
            upper_points.append(QPointF(x, center_y - offset))
            lower_points.append(QPointF(x, center_y + offset))

        fill_path = QPainterPath(upper_points[0])
        for point in upper_points[1:]:
            fill_path.lineTo(point)
        for point in reversed(lower_points):
            fill_path.lineTo(point)
        fill_path.closeSubpath()

        fill_gradient = QLinearGradient(left, top, left, bottom)
        fill_gradient.setColorAt(0.0, self.with_alpha(theme.accent_secondary, 72))
        fill_gradient.setColorAt(0.5, self.with_alpha(theme.accent_primary, 110))
        fill_gradient.setColorAt(1.0, self.with_alpha(theme.accent_secondary, 72))
        painter.fillPath(fill_path, QBrush(fill_gradient))

        upper_path = QPainterPath(upper_points[0])
        lower_path = QPainterPath(lower_points[0])
        for point in upper_points[1:]:
            upper_path.lineTo(point)
        for point in lower_points[1:]:
            lower_path.lineTo(point)

        glow_pen = QPen(self.with_alpha(theme.accent_secondary, 55), 5.0)
        glow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        glow_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(glow_pen)
        painter.drawPath(upper_path)
        painter.drawPath(lower_path)

        line_pen = QPen(QColor(theme.accent_primary), 1.8)
        line_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        line_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(line_pen)
        painter.drawPath(upper_path)
        painter.drawPath(lower_path)

    def _build_envelope(self, waveform: np.ndarray, segment_count: int) -> np.ndarray:
        absolute = np.abs(waveform).astype(np.float32, copy=False)
        segments = np.array_split(absolute, segment_count)
        values = np.array(
            [
                float(np.sqrt(np.mean(np.square(segment), dtype=np.float32))) if segment.size else 0.0
                for segment in segments
            ],
            dtype=np.float32,
        )
        values = 1.0 - np.exp(-values * 3.6)
        kernel = np.array([1.0, 2.0, 3.0, 2.0, 1.0], dtype=np.float32)
        kernel /= kernel.sum()
        padded = np.pad(values, (2, 2), mode="edge")
        smoothed = np.convolve(padded, kernel, mode="valid")
        return np.clip(smoothed, 0.0, 1.0).astype(np.float32)

    def _animate_envelope(self, envelope: np.ndarray) -> np.ndarray:
        ratio = self.intensity_ratio()
        if self._display_envelope is None or self._display_envelope.shape != envelope.shape:
            self._display_envelope = envelope.copy()
            return self._display_envelope

        attack = 0.52 - ratio * 0.12
        release = 0.86 - ratio * 0.08
        rising = envelope >= self._display_envelope
        self._display_envelope = np.where(
            rising,
            self._display_envelope * attack + envelope * (1.0 - attack),
            self._display_envelope * release + envelope * (1.0 - release),
        ).astype(np.float32)
        return self._display_envelope
