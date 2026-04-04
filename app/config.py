"""Application-wide configuration."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ThemeConfig:
    """Color palette used throughout the application."""

    background_top: str = "#08131e"
    background_bottom: str = "#030812"
    panel_background: str = "#0d1724"
    panel_border: str = "#1f3143"
    text_primary: str = "#f5f7fb"
    text_secondary: str = "#9cb1c8"
    accent_primary: str = "#2ee6c5"
    accent_secondary: str = "#58a6ff"
    accent_warm: str = "#ff9566"
    accent_bass: str = "#13c4a3"
    accent_mid: str = "#58a6ff"
    accent_treble: str = "#ff7f6a"
    warning: str = "#ffb454"
    danger: str = "#ff6b6b"


@dataclass(frozen=True)
class AppConfig:
    """Runtime and visual tuning values for the application."""

    app_name: str = "PulseCanvas"
    window_title: str = "PulseCanvas Music Visualizer"
    min_width: int = 1024
    min_height: int = 680
    ui_fps: int = 60
    audio_block_size: int = 512
    fft_size: int = 2048
    waveform_points: int = 640
    waveform_window_frames: int = 512
    bar_count: int = 64
    radial_bar_count: int = 96
    default_visualizer_intensity: float = 0.65
    min_visualizer_intensity: float = 0.25
    max_visualizer_intensity: float = 1.2
    spectrum_smoothing: float = 0.72
    band_smoothing: float = 0.82
    reference_smoothing: float = 0.92
    adaptive_floor_db: float = -36.0
    dynamic_range_db: float = 72.0
    bass_cutoff_hz: float = 250.0
    treble_cutoff_hz: float = 4000.0
    min_display_frequency_hz: float = 30.0
    max_volume: float = 1.5
    theme: ThemeConfig = field(default_factory=ThemeConfig)


DEFAULT_CONFIG = AppConfig()
