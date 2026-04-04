"""Shared data models used by the application."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import numpy as np
from numpy.typing import NDArray


FloatArray = NDArray[np.float32]


class TransportState(str, Enum):
    """Playback transport state."""

    STOPPED = "Stopped"
    PLAYING = "Playing"
    PAUSED = "Paused"


@dataclass(frozen=True)
class BandEnergy:
    """Aggregated energy across broad frequency regions."""

    bass: float
    mids: float
    treble: float


@dataclass(frozen=True)
class AudioMetadata:
    """Loaded audio file metadata."""

    path: Path
    title: str
    sample_rate: int
    channels: int
    frames: int
    duration: float


@dataclass(frozen=True)
class AnalysisFrame:
    """Visual analysis values derived from a recent audio window."""

    waveform: FloatArray
    spectrum: FloatArray
    bands: BandEnergy
    peak: float
    rms: float
    sample_rate: int
    timestamp: float


@dataclass(frozen=True)
class PlaybackSnapshot:
    """UI-facing snapshot of current transport state."""

    state: TransportState
    metadata: AudioMetadata | None
    position: float
    duration: float
    volume: float
    stream_active: bool
    error_message: str | None = None


def make_empty_analysis_frame(
    sample_rate: int,
    waveform_points: int,
    spectrum_points: int,
) -> AnalysisFrame:
    """Create an empty analysis frame for startup and error states."""

    return AnalysisFrame(
        waveform=np.zeros(waveform_points, dtype=np.float32),
        spectrum=np.zeros(spectrum_points, dtype=np.float32),
        bands=BandEnergy(bass=0.0, mids=0.0, treble=0.0),
        peak=0.0,
        rms=0.0,
        sample_rate=sample_rate,
        timestamp=0.0,
    )

