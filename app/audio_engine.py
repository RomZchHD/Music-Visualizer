"""Source-aware audio controller used by the UI."""

from __future__ import annotations

from pathlib import Path

from app.audio_sources import FilePlaybackSource, SystemLoopbackSource
from app.config import AppConfig, DEFAULT_CONFIG
from app.models import AnalysisFrame, AudioDeviceInfo, AudioMetadata, AudioSourceMode, PlaybackSnapshot


class AudioEngine:
    """Coordinate the active audio source while preserving a single UI-facing API."""

    def __init__(self, config: AppConfig = DEFAULT_CONFIG) -> None:
        self.config = config
        self._file_source = FilePlaybackSource(config)
        self._system_source = SystemLoopbackSource(config)
        self._mode = AudioSourceMode.FILE

    def set_source_mode(self, mode: AudioSourceMode) -> None:
        """Switch the active source mode and stop any currently active source."""

        if mode == self._mode:
            return

        if mode == AudioSourceMode.SYSTEM:
            availability_error = self._system_source.availability_error()
            if availability_error is not None:
                raise RuntimeError(availability_error)
            self._system_source.refresh_devices()

        self._active_source().stop()
        self._mode = mode

    def get_source_mode(self) -> AudioSourceMode:
        """Return the currently selected source mode."""

        return self._mode

    def source_modes(self) -> list[tuple[AudioSourceMode, str, bool]]:
        """Return the source-mode options shown in the UI."""

        system_error = self._system_source.availability_error()
        return [
            (AudioSourceMode.FILE, "File", True),
            (
                AudioSourceMode.SYSTEM,
                "System Audio (Windows)",
                system_error is None,
            ),
        ]

    def system_audio_availability_error(self) -> str | None:
        """Return the availability message for Windows loopback capture."""

        return self._system_source.availability_error()

    def list_output_devices(self) -> list[AudioDeviceInfo]:
        """Return system-audio output devices."""

        return self._system_source.list_output_devices()

    def refresh_output_devices(self) -> list[AudioDeviceInfo]:
        """Refresh and return system-audio output devices."""

        return self._system_source.refresh_devices()

    def select_output_device(self, device_id: str) -> None:
        """Select the output device used for Windows loopback capture."""

        self._system_source.select_output_device(device_id)

    def selected_output_device_id(self) -> str | None:
        """Return the currently selected system-audio output device."""

        return self._system_source.selected_output_device_id()

    def load_file(self, path: str | Path) -> AudioMetadata:
        """Load a file into the file-playback source and switch to file mode."""

        if self._mode != AudioSourceMode.FILE:
            self._active_source().stop()
            self._mode = AudioSourceMode.FILE
        return self._file_source.load_file(path)

    def play(self) -> None:
        """Start the active source."""

        self._active_source().start()

    def pause(self) -> None:
        """Pause the active source when supported."""

        self._active_source().pause()

    def stop(self) -> None:
        """Stop the active source."""

        self._active_source().stop()

    def toggle_play_pause(self) -> None:
        """Toggle playback in file mode or start capture in system mode."""

        active_source = self._active_source()
        if self._mode == AudioSourceMode.SYSTEM:
            active_source.start()
            return
        active_source.toggle_play_pause()

    def set_volume(self, volume: float) -> None:
        """Set playback volume on the file source."""

        self._file_source.set_volume(volume)

    def get_snapshot(self) -> PlaybackSnapshot:
        """Return the snapshot of the active source."""

        return self._active_source().get_snapshot()

    def get_analysis(self) -> AnalysisFrame:
        """Return the analysis frame of the active source."""

        return self._active_source().get_analysis()

    def close(self) -> None:
        """Release source resources."""

        self._file_source.close()
        self._system_source.close()

    def _active_source(self) -> FilePlaybackSource | SystemLoopbackSource:
        if self._mode == AudioSourceMode.SYSTEM:
            return self._system_source
        return self._file_source
