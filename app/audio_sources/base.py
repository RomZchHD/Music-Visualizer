"""Common audio-source abstractions shared by playback and capture modes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from app.models import AnalysisFrame, AudioMetadata, PlaybackSnapshot, TransportState


class BaseAudioSource(ABC):
    """Shared interface for file playback and system-audio capture sources."""

    @abstractmethod
    def start(self) -> None:
        """Start playback or capture."""

    @abstractmethod
    def stop(self) -> None:
        """Stop playback or capture and reset any active stream state."""

    def pause(self) -> None:
        """Pause the source when supported."""

    def toggle_play_pause(self) -> None:
        """Toggle between active and paused states when supported."""

        snapshot = self.get_snapshot()
        if snapshot.state == TransportState.PLAYING:
            self.pause()
            return
        self.start()

    @abstractmethod
    def close(self) -> None:
        """Release any owned resources."""

    @abstractmethod
    def get_snapshot(self) -> PlaybackSnapshot:
        """Return the latest UI-facing source snapshot."""

    @abstractmethod
    def get_analysis(self) -> AnalysisFrame:
        """Return the latest analysis frame for the renderer."""

    def load_file(self, path: str | Path) -> AudioMetadata:
        """Load an audio file when the source supports it."""

        raise RuntimeError("This source does not support loading files.")

    def set_volume(self, volume: float) -> None:
        """Adjust playback volume when the source supports it."""
