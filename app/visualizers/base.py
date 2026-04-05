"""Base interfaces and helpers for visualizer renderers."""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np
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
        self.intensity = config.default_visualizer_intensity

    @abstractmethod
    def render(self, painter: QPainter, rect: QRectF, frame: AnalysisFrame) -> None:
        """Draw the latest analysis frame into the provided rectangle."""

    def set_intensity(self, intensity: float) -> None:
        """Set the current visualizer intensity multiplier."""

        self.intensity = clamp(
            intensity,
            self.config.min_visualizer_intensity,
            self.config.max_visualizer_intensity,
        )

    def intensity_ratio(self) -> float:
        """Return intensity normalized to a 0..1 range."""

        span = self.config.max_visualizer_intensity - self.config.min_visualizer_intensity
        if span <= 0.0:
            return 0.5
        return clamp(
            (self.intensity - self.config.min_visualizer_intensity) / span,
            0.0,
            1.0,
        )

    def shape_levels(self, values: np.ndarray) -> np.ndarray:
        """Shape normalized levels without adding an artificial floor."""

        ratio = self.intensity_ratio()
        exponent = 1.18 - ratio * 0.46
        clipped = np.clip(values, 0.0, 1.0)
        return np.power(clipped, exponent).astype(np.float32)

    def animate_levels(
        self,
        previous: np.ndarray | None,
        target: np.ndarray,
    ) -> np.ndarray:
        """Animate levels with fast attack and slower release."""

        target_array = np.asarray(target, dtype=np.float32)
        if previous is None or previous.shape != target_array.shape:
            return target_array.copy()

        ratio = self.intensity_ratio()
        attack = 0.24 - ratio * 0.12
        release = 0.84 - ratio * 0.2
        rising = target_array >= previous
        animated = np.where(
            rising,
            previous * attack + target_array * (1.0 - attack),
            previous * release + target_array * (1.0 - release),
        )
        return animated.astype(np.float32)

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
