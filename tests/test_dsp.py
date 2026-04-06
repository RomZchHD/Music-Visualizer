"""Tests for pure DSP helpers."""

from __future__ import annotations

import math

import numpy as np

from app.config import AppConfig
from app.dsp import AudioAnalyzer, resample_for_display, spectrum_to_bars, to_mono


def make_config() -> AppConfig:
    """Create a test-friendly configuration."""

    return AppConfig(
        fft_size=2048,
        waveform_points=256,
        waveform_window_frames=128,
        bar_count=32,
        radial_bar_count=48,
    )


def sine_wave(frequency: float, sample_rate: int, frames: int) -> np.ndarray:
    """Generate a mono float32 sine wave."""

    timeline = np.arange(frames, dtype=np.float32) / float(sample_rate)
    return np.sin(2.0 * math.pi * frequency * timeline).astype(np.float32)


def test_to_mono_averages_channels() -> None:
    stereo = np.array([[1.0, -1.0], [0.5, 0.25]], dtype=np.float32)
    mono = to_mono(stereo)
    np.testing.assert_allclose(mono, np.array([0.0, 0.375], dtype=np.float32))


def test_resample_for_display_returns_requested_size() -> None:
    source = np.array([0.0, 1.0, 0.0, -1.0], dtype=np.float32)
    result = resample_for_display(source, 11)
    assert result.shape == (11,)
    assert result.dtype == np.float32


def test_analyzer_emphasizes_bass_band_for_low_sine() -> None:
    sample_rate = 48_000
    config = make_config()
    analyzer = AudioAnalyzer(sample_rate=sample_rate, config=config)
    signal = sine_wave(80.0, sample_rate, config.fft_size * 2)

    frame = analyzer.analyze(signal, timestamp=0.1)

    assert frame.bands.bass > frame.bands.mids
    assert frame.bands.bass > frame.bands.treble
    assert frame.spectrum.shape == (config.fft_size // 2 + 1,)


def test_spectrum_to_bars_matches_requested_count() -> None:
    spectrum = np.linspace(0.0, 1.0, 1025, dtype=np.float32)
    bars = spectrum_to_bars(spectrum, sample_rate=48_000, bar_count=48)
    assert bars.shape == (48,)
    assert np.all(bars >= 0.0)
    assert np.all(bars <= 1.0)


def test_spectrum_to_bars_preserves_high_frequency_activity() -> None:
    sample_rate = 48_000
    spectrum = np.zeros(1025, dtype=np.float32)
    frequencies = np.linspace(0.0, sample_rate / 2.0, num=spectrum.size, dtype=np.float32)
    high_index = int(np.argmin(np.abs(frequencies - 8_000.0)))
    spectrum[high_index] = 1.0

    bars = spectrum_to_bars(spectrum, sample_rate=sample_rate, bar_count=32)

    assert float(bars.max()) > 0.3


def test_spectrum_to_bars_does_not_flatten_broad_bass_plateau() -> None:
    sample_rate = 48_000
    spectrum = np.zeros(1025, dtype=np.float32)
    frequencies = np.linspace(0.0, sample_rate / 2.0, num=spectrum.size, dtype=np.float32)
    spectrum[(frequencies >= 50.0) & (frequencies < 160.0)] = 0.95
    spectrum[(frequencies >= 160.0) & (frequencies < 260.0)] = 0.55

    bars = spectrum_to_bars(spectrum, sample_rate=sample_rate, bar_count=32)

    assert float(np.ptp(bars[:6])) > 0.03
    assert float(np.max(bars[:4])) < 0.98


def test_analyzer_waveform_prefers_recent_window() -> None:
    config = AppConfig(
        fft_size=128,
        waveform_points=32,
        waveform_window_frames=32,
    )
    analyzer = AudioAnalyzer(sample_rate=48_000, config=config)
    signal = np.concatenate(
        [
            np.ones(128, dtype=np.float32),
            np.zeros(32, dtype=np.float32),
        ]
    )

    frame = analyzer.analyze(signal)

    assert frame.waveform.shape == (32,)
    assert float(np.max(np.abs(frame.waveform))) < 0.01


def test_analyzer_can_use_dedicated_waveform_samples() -> None:
    config = AppConfig(
        fft_size=128,
        waveform_points=16,
        waveform_window_frames=16,
    )
    analyzer = AudioAnalyzer(sample_rate=48_000, config=config)
    spectrum_signal = np.zeros(128, dtype=np.float32)
    waveform_signal = np.linspace(-1.0, 1.0, 16, dtype=np.float32)

    frame = analyzer.analyze(spectrum_signal, waveform_samples=waveform_signal)

    np.testing.assert_allclose(frame.waveform, waveform_signal, atol=1e-5)
