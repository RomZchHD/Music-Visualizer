"""Audio playback and real-time analysis engine."""

from __future__ import annotations

from collections import deque
import io
import shutil
import subprocess
import threading
from time import perf_counter
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

from app.config import AppConfig, DEFAULT_CONFIG
from app.dsp import AudioAnalyzer
from app.models import (
    AnalysisFrame,
    AudioMetadata,
    PlaybackSnapshot,
    TransportState,
    make_empty_analysis_frame,
)
from app.utils import clamp, display_title


class AudioEngine:
    """Manage file-backed playback and analysis for the UI."""

    def __init__(self, config: AppConfig = DEFAULT_CONFIG) -> None:
        self.config = config
        self._lock = threading.RLock()
        self._data: np.ndarray | None = None
        self._metadata: AudioMetadata | None = None
        self._analysis = make_empty_analysis_frame(
            sample_rate=48_000,
            waveform_points=self.config.waveform_points,
            spectrum_points=self.config.fft_size // 2 + 1,
        )
        self._analyzer: AudioAnalyzer | None = None
        self._stream: sd.OutputStream | None = None
        self._state = TransportState.STOPPED
        self._current_frame = 0
        self._volume = 1.0
        self._error_message: str | None = None
        self._scheduled_analysis: deque[tuple[float, AnalysisFrame]] = deque()
        self._analysis_window_frames = max(
            self.config.fft_size,
            self.config.waveform_window_frames,
        )

    def load_file(self, path: str | Path) -> AudioMetadata:
        """Load an audio file into memory and prepare analysis state."""

        resolved_path = Path(path).expanduser().resolve(strict=True)
        self._close_stream()

        try:
            audio_data, sample_rate = self._read_audio_file(resolved_path)
        except Exception as exc:  # pragma: no cover - depends on codecs/environment
            raise RuntimeError(f"Could not read audio file: {exc}") from exc

        if audio_data.size == 0:
            raise RuntimeError("The selected audio file does not contain any samples.")

        prepared_data = self._prepare_channels(audio_data)
        metadata = AudioMetadata(
            path=resolved_path,
            title=display_title(resolved_path),
            sample_rate=int(sample_rate),
            channels=int(prepared_data.shape[1]),
            frames=int(prepared_data.shape[0]),
            duration=float(prepared_data.shape[0] / float(sample_rate)),
        )

        analyzer = AudioAnalyzer(sample_rate=metadata.sample_rate, config=self.config)

        with self._lock:
            self._data = prepared_data
            self._metadata = metadata
            self._analyzer = analyzer
            self._current_frame = 0
            self._state = TransportState.STOPPED
            self._error_message = None
            self._scheduled_analysis.clear()
            self._prime_analysis_locked()

        return metadata

    def play(self) -> None:
        """Start or resume playback."""

        with self._lock:
            if self._data is None or self._metadata is None:
                raise RuntimeError("Open an audio file before pressing play.")
            if self._current_frame >= self._metadata.frames:
                self._current_frame = 0
                self._prime_analysis_locked()
            recreate_stream = self._stream is not None and not self._stream.active
            stream_is_active = self._stream is not None and self._stream.active
            self._state = TransportState.PLAYING
            self._error_message = None

        if recreate_stream:
            self._close_stream()

        if stream_is_active:
            return

        try:
            self._ensure_stream()
            if self._stream is not None and not self._stream.active:
                self._stream.start()
        except Exception as exc:  # pragma: no cover - device dependent
            with self._lock:
                self._state = TransportState.STOPPED
                self._error_message = f"Unable to start audio output: {exc}"
            raise RuntimeError(self._error_message) from exc

    def pause(self) -> None:
        """Pause playback while keeping the stream warm."""

        with self._lock:
            if self._state == TransportState.PLAYING:
                self._state = TransportState.PAUSED

    def stop(self) -> None:
        """Stop playback and reset the playhead."""

        self._stop_stream_if_needed()
        with self._lock:
            self._state = TransportState.STOPPED
            self._current_frame = 0
            self._scheduled_analysis.clear()
            if self._data is not None and self._analyzer is not None:
                self._prime_analysis_locked()
            else:
                self._analysis = make_empty_analysis_frame(
                    sample_rate=48_000,
                    waveform_points=self.config.waveform_points,
                    spectrum_points=self.config.fft_size // 2 + 1,
                )

    def toggle_play_pause(self) -> None:
        """Toggle between play and pause states."""

        with self._lock:
            current_state = self._state

        if current_state == TransportState.PLAYING:
            self.pause()
        else:
            self.play()

    def set_volume(self, volume: float) -> None:
        """Set playback volume as a linear multiplier."""

        with self._lock:
            self._volume = clamp(volume, 0.0, self.config.max_volume)

    def get_snapshot(self) -> PlaybackSnapshot:
        """Return a transport snapshot for the UI."""

        with self._lock:
            metadata = self._metadata
            duration = metadata.duration if metadata is not None else 0.0
            position = (
                self._current_frame / float(metadata.sample_rate)
                if metadata is not None and metadata.sample_rate > 0
                else 0.0
            )
            return PlaybackSnapshot(
                state=self._state,
                metadata=metadata,
                position=position,
                duration=duration,
                volume=self._volume,
                stream_active=bool(self._stream is not None and self._stream.active),
                error_message=self._error_message,
            )

    def get_analysis(self) -> AnalysisFrame:
        """Return the latest analysis frame."""

        with self._lock:
            now = perf_counter()
            while self._scheduled_analysis and self._scheduled_analysis[0][0] <= now:
                _, self._analysis = self._scheduled_analysis.popleft()
            return self._analysis

    def close(self) -> None:
        """Release audio resources."""

        self._close_stream()

    def _ensure_stream(self) -> None:
        with self._lock:
            if self._stream is not None or self._metadata is None:
                return
            metadata = self._metadata

        stream = sd.OutputStream(
            samplerate=metadata.sample_rate,
            channels=metadata.channels,
            dtype="float32",
            blocksize=self.config.audio_block_size,
            latency="low",
            callback=self._audio_callback,
        )

        with self._lock:
            if self._stream is None:
                self._stream = stream
                return

        stream.close()

    def _prepare_channels(self, samples: np.ndarray) -> np.ndarray:
        prepared = np.asarray(samples, dtype=np.float32)
        if prepared.ndim != 2:
            raise RuntimeError("Expected decoded audio to be a 2D array.")
        if prepared.shape[1] <= 2:
            return prepared
        return prepared[:, :2].astype(np.float32, copy=False)

    def _read_audio_file(self, path: Path) -> tuple[np.ndarray, int]:
        try:
            return sf.read(path, dtype="float32", always_2d=True)
        except Exception as soundfile_error:
            return self._decode_with_ffmpeg(path, soundfile_error)

    def _decode_with_ffmpeg(
        self,
        path: Path,
        original_error: Exception,
    ) -> tuple[np.ndarray, int]:
        ffmpeg_binary = shutil.which("ffmpeg")
        if ffmpeg_binary is None:
            raise RuntimeError(
                "soundfile could not decode this file and ffmpeg was not found on PATH. "
                "Install ffmpeg for AAC/Opus fallback support."
            ) from original_error

        command = [
            ffmpeg_binary,
            "-v",
            "error",
            "-vn",
            "-i",
            str(path),
            "-f",
            "wav",
            "-acodec",
            "pcm_f32le",
            "pipe:1",
        ]
        process = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if process.returncode != 0:
            ffmpeg_message = process.stderr.decode("utf-8", errors="replace").strip()
            if not ffmpeg_message:
                ffmpeg_message = "ffmpeg could not decode the selected file."
            raise RuntimeError(ffmpeg_message) from original_error

        try:
            return sf.read(io.BytesIO(process.stdout), dtype="float32", always_2d=True)
        except Exception as ffmpeg_decode_error:
            raise RuntimeError(
                "ffmpeg produced audio data, but the WAV fallback stream could not be parsed."
            ) from ffmpeg_decode_error

    def _prime_analysis_locked(self) -> None:
        if self._data is None or self._analyzer is None:
            return
        self._analysis = self._analyzer.analyze(
            self._data[: self._analysis_window_frames],
            timestamp=0.0,
        )

    def _audio_callback(
        self,
        outdata: np.ndarray,
        frames: int,
        time_info: object,
        status: sd.CallbackFlags,
    ) -> None:
        analysis_input: np.ndarray | None = None
        waveform_input: np.ndarray | None = None
        analyzer: AudioAnalyzer | None = None
        timestamp = 0.0
        display_at = 0.0
        reached_end = False

        with self._lock:
            if status:
                self._error_message = str(status)

            if self._data is None or self._metadata is None or self._state != TransportState.PLAYING:
                outdata.fill(0.0)
                return

            start = self._current_frame
            end = min(start + frames, self._metadata.frames)
            chunk = self._data[start:end]

            outdata.fill(0.0)
            if chunk.size:
                outdata[: chunk.shape[0], : chunk.shape[1]] = chunk * self._volume
                self._current_frame = end
                chunk_frames = chunk.shape[0]
                analysis_center = min(
                    self._metadata.frames,
                    start + max(1, chunk_frames // 2),
                )
                window_start = max(0, analysis_center - self._analysis_window_frames)
                analysis_input = self._data[window_start:analysis_center].copy()
                waveform_input = chunk.copy()
                analyzer = self._analyzer
                timestamp = analysis_center / float(self._metadata.sample_rate)
                latency_seconds = self._estimate_output_latency_seconds(time_info)
                display_at = perf_counter() + latency_seconds

            reached_end = end >= self._metadata.frames
            if reached_end:
                self._state = TransportState.STOPPED

        if analysis_input is not None and waveform_input is not None and analyzer is not None:
            analysis = analyzer.analyze(
                analysis_input,
                timestamp=timestamp,
                waveform_samples=waveform_input,
            )
            with self._lock:
                self._scheduled_analysis.append((display_at, analysis))
                while len(self._scheduled_analysis) > 24:
                    self._scheduled_analysis.popleft()

        if reached_end:
            raise sd.CallbackStop()

    def _estimate_output_latency_seconds(self, time_info: object) -> float:
        """Estimate seconds until the queued output buffer reaches the DAC."""

        output_time = float(getattr(time_info, "outputBufferDacTime", 0.0) or 0.0)
        current_time = float(getattr(time_info, "currentTime", 0.0) or 0.0)
        return max(0.0, output_time - current_time)

    def _stop_stream_if_needed(self) -> None:
        with self._lock:
            stream = self._stream

        if stream is None:
            return

        try:
            if stream.active:
                stream.stop()
        except Exception:
            pass

    def _close_stream(self) -> None:
        with self._lock:
            stream = self._stream
            self._stream = None

        if stream is None:
            return

        try:
            if stream.active:
                stream.stop()
        except Exception:
            pass

        try:
            stream.close()
        except Exception:
            pass
