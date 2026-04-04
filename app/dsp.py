"""Signal-processing helpers for the visualizer."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from app.config import AppConfig, DEFAULT_CONFIG
from app.models import AnalysisFrame, BandEnergy


FloatArray = NDArray[np.float32]


def to_mono(samples: FloatArray) -> FloatArray:
    """Convert mono or multi-channel samples into a mono float32 array."""

    array = np.asarray(samples, dtype=np.float32)
    if array.ndim == 1:
        return array
    if array.ndim != 2:
        raise ValueError("Expected 1D or 2D audio samples.")
    return array.mean(axis=1, dtype=np.float32)


def resample_for_display(samples: FloatArray, target_size: int) -> FloatArray:
    """Resample audio samples to a fixed-size array for drawing."""

    if target_size <= 0:
        raise ValueError("target_size must be positive.")

    array = np.asarray(samples, dtype=np.float32)
    if array.size == 0:
        return np.zeros(target_size, dtype=np.float32)
    if array.size == target_size:
        return array.astype(np.float32, copy=True)
    if array.size == 1:
        return np.full(target_size, float(array[0]), dtype=np.float32)

    source_positions = np.linspace(0.0, 1.0, num=array.size, dtype=np.float32)
    target_positions = np.linspace(0.0, 1.0, num=target_size, dtype=np.float32)
    return np.interp(target_positions, source_positions, array).astype(np.float32)


def compute_rms(samples: FloatArray) -> float:
    """Compute RMS level for a mono or multi-channel block."""

    array = np.asarray(samples, dtype=np.float32)
    if array.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(array), dtype=np.float32)))


def exponential_smoothing(
    previous: float | FloatArray | None,
    current: float | FloatArray,
    factor: float,
) -> float | FloatArray:
    """Blend values using exponential smoothing."""

    smoothing = float(np.clip(factor, 0.0, 0.9999))
    if previous is None:
        if isinstance(current, np.ndarray):
            return current.astype(np.float32, copy=True)
        return float(current)
    return previous * smoothing + current * (1.0 - smoothing)


def compute_band_energies(
    spectrum: FloatArray,
    frequencies: FloatArray,
    bass_cutoff_hz: float,
    treble_cutoff_hz: float,
) -> BandEnergy:
    """Aggregate broad bass, mids, and treble energy values."""

    if spectrum.size == 0 or frequencies.size == 0:
        return BandEnergy(bass=0.0, mids=0.0, treble=0.0)

    bass_mask = frequencies <= bass_cutoff_hz
    mid_mask = (frequencies > bass_cutoff_hz) & (frequencies <= treble_cutoff_hz)
    treble_mask = frequencies > treble_cutoff_hz

    def band_value(mask: NDArray[np.bool_]) -> float:
        if not np.any(mask):
            return 0.0
        return float(np.mean(spectrum[mask], dtype=np.float32))

    return BandEnergy(
        bass=band_value(bass_mask),
        mids=band_value(mid_mask),
        treble=band_value(treble_mask),
    )


def spectrum_to_bars(
    spectrum: FloatArray,
    sample_rate: int,
    bar_count: int,
    min_frequency_hz: float = 30.0,
) -> FloatArray:
    """Convert a spectrum into log-spaced bar magnitudes."""

    if bar_count <= 0:
        raise ValueError("bar_count must be positive.")

    array = np.asarray(spectrum, dtype=np.float32)
    if array.size <= 1 or sample_rate <= 0:
        return np.zeros(bar_count, dtype=np.float32)

    frequencies = np.linspace(0.0, sample_rate / 2.0, num=array.size, dtype=np.float32)
    start_index = int(np.searchsorted(frequencies, min_frequency_hz, side="left"))
    start_index = min(max(start_index, 1), array.size - 1)

    start_frequency = float(frequencies[start_index])
    end_frequency = float(frequencies[-1])
    if start_frequency >= end_frequency:
        return np.zeros(bar_count, dtype=np.float32)

    edges = np.geomspace(start_frequency, end_frequency, num=bar_count + 1)
    bars = np.zeros(bar_count, dtype=np.float32)

    for index in range(bar_count):
        left = int(np.searchsorted(frequencies, edges[index], side="left"))
        right = int(np.searchsorted(frequencies, edges[index + 1], side="right"))
        right = max(right, left + 1)
        region = array[left:right]
        if region.size == 0:
            continue
        bars[index] = float(region.max() * 0.85 + region.mean(dtype=np.float32) * 0.15)

    return np.power(np.clip(bars, 0.0, 1.0), 0.85).astype(np.float32)


@dataclass
class AudioAnalyzer:
    """Compute smoothed waveform and spectrum data from recent audio blocks."""

    sample_rate: int
    config: AppConfig = DEFAULT_CONFIG

    def __post_init__(self) -> None:
        self._window = np.hanning(self.config.fft_size).astype(np.float32)
        self._frequencies = np.fft.rfftfreq(
            self.config.fft_size,
            d=1.0 / float(self.sample_rate),
        ).astype(np.float32)
        self._previous_spectrum = np.zeros(self.config.fft_size // 2 + 1, dtype=np.float32)
        self._previous_bands = BandEnergy(bass=0.0, mids=0.0, treble=0.0)
        self._reference_db: float | None = None

    def analyze(self, samples: FloatArray, timestamp: float = 0.0) -> AnalysisFrame:
        """Analyze a recent block of audio and return display-ready values."""

        mono = to_mono(samples)
        waveform_source = mono[-self.config.waveform_window_frames :]
        if waveform_source.size == 0:
            waveform_source = mono

        waveform = resample_for_display(waveform_source, self.config.waveform_points)
        peak = float(np.max(np.abs(waveform_source))) if waveform_source.size else 0.0
        rms = compute_rms(waveform_source)

        fft_input = np.zeros(self.config.fft_size, dtype=np.float32)
        tail = mono[-self.config.fft_size :]
        if tail.size:
            fft_input[-tail.size :] = tail

        magnitude = np.abs(np.fft.rfft(fft_input * self._window)).astype(np.float32)
        spectrum = self._normalize_spectrum(magnitude)
        spectrum = exponential_smoothing(
            self._previous_spectrum,
            spectrum,
            self.config.spectrum_smoothing,
        )
        self._previous_spectrum = np.asarray(spectrum, dtype=np.float32)

        band_energies = compute_band_energies(
            self._previous_spectrum,
            self._frequencies,
            self.config.bass_cutoff_hz,
            self.config.treble_cutoff_hz,
        )
        smoothed_bands = BandEnergy(
            bass=float(
                exponential_smoothing(
                    self._previous_bands.bass,
                    band_energies.bass,
                    self.config.band_smoothing,
                )
            ),
            mids=float(
                exponential_smoothing(
                    self._previous_bands.mids,
                    band_energies.mids,
                    self.config.band_smoothing,
                )
            ),
            treble=float(
                exponential_smoothing(
                    self._previous_bands.treble,
                    band_energies.treble,
                    self.config.band_smoothing,
                )
            ),
        )
        self._previous_bands = smoothed_bands

        return AnalysisFrame(
            waveform=waveform,
            spectrum=self._previous_spectrum.copy(),
            bands=smoothed_bands,
            peak=peak,
            rms=rms,
            sample_rate=self.sample_rate,
            timestamp=timestamp,
        )

    def _normalize_spectrum(self, magnitude: FloatArray) -> FloatArray:
        safe_magnitude = np.maximum(np.asarray(magnitude, dtype=np.float32), 1e-10)
        decibels = 20.0 * np.log10(safe_magnitude)
        frame_reference_db = float(np.percentile(decibels, 96.0))
        frame_reference_db = max(frame_reference_db, self.config.adaptive_floor_db)
        self._reference_db = float(
            exponential_smoothing(
                self._reference_db,
                frame_reference_db,
                self.config.reference_smoothing,
            )
        )

        floor_db = self._reference_db - self.config.dynamic_range_db
        normalized = (decibels - floor_db) / self.config.dynamic_range_db
        return np.clip(normalized, 0.0, 1.0).astype(np.float32)
