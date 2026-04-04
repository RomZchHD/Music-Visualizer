"""Base interfaces and helpers for visualizer renderers."""

from __future__ import annotations

from abc import ABC, abstractmethod

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QPainter

from app.config import AppConfig
from app.models import AnalysisFrame
from app.utils import clamp


class BaseVisualizer(ABC):
    """Base class for pluggable visualizer renderers."""

    mode_id = "base"
    display_name = "Base"

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    @abstractmethod
    def render(self, painter: QPainter, rect: QRectF, frame: AnalysisFrame) -> None:
        """Draw the latest analysis frame into the provided rectangle."""

    def with_alpha(self, color: str | QColor, alpha: int) -> QColor:
        """Return a color with the requested alpha channel."""

        qcolor = QColor(color)
        qcolor.setAlpha(int(clamp(alpha, 0, 255)))
        return qcolor

    def mix_colors(self, start: str | QColor, end: str | QColor, amount: float) -> QColor:
        """Blend two colors together."""

        start_color = QColor(start)
        end_color = QColor(end)
        t = clamp(amount, 0.0, 1.0)
        return QColor(
            int(start_color.red() + (end_color.red() - start_color.red()) * t),
            int(start_color.green() + (end_color.green() - start_color.green()) * t),
            int(start_color.blue() + (end_color.blue() - start_color.blue()) * t),
            int(start_color.alpha() + (end_color.alpha() - start_color.alpha()) * t),
        )

