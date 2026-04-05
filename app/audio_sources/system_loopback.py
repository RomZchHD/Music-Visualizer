"""Windows-only system-audio loopback capture source."""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
import importlib
import platform
from time import perf_counter
import threading
from typing import Protocol

import numpy as np

from app.audio_sources.base import BaseAudioSource
from app.config import AppConfig, DEFAULT_CONFIG
from app.dsp import AudioAnalyzer
from app.models import (
    AnalysisFrame,
    AudioDeviceInfo,
    AudioSourceMode,
    PlaybackSnapshot,
    TransportState,
    make_empty_analysis_frame,
)

try:  # pragma: no cover - optional dependency
    import soundcard as sc
except ImportError:  # pragma: no cover - optional dependency
    sc = None


FloatChunk = np.ndarray


class RecorderProtocol(Protocol):
    """Protocol for loopback recorder objects returned by the backend."""

    def record(self, numframes: int) -> FloatChunk:
        """Return captured audio frames."""


class RecorderContextProtocol(AbstractContextManager[RecorderProtocol], Protocol):
    """Protocol for backend recorder context managers."""


class LoopbackBackendProtocol(Protocol):
    """Adapter boundary around the hardware-dependent soundcard package."""

    def availability_error(self) -> str | None:
        """Return a user-facing availability error when loopback is unavailable."""

    def list_output_devices(self) -> list[AudioDeviceInfo]:
        """Return selectable Windows output devices."""

    def open_recorder(
        self,
        device_id: str,
        samplerate: int,
        blocksize: int,
    ) -> RecorderContextProtocol:
        """Open a WASAPI loopback recorder for the selected device."""


def normalize_loopback_chunk(chunk: FloatChunk) -> FloatChunk:
    """Normalize loopback capture chunks to a 2D float32 array."""

    array = np.asarray(chunk, dtype=np.float32)
    if array.ndim == 0 or array.size == 0:
        return np.zeros((0, 1), dtype=np.float32)
    if array.ndim == 1:
        return array[:, np.newaxis]
    if array.ndim != 2:
        raise ValueError("Expected loopback chunks to be 1D or 2D arrays.")
    return np.ascontiguousarray(array, dtype=np.float32)


def match_channel_count(chunk: FloatChunk, channel_count: int) -> FloatChunk:
    """Coerce loopback chunks to a stable channel count for analysis."""

    if channel_count <= 0:
        raise ValueError("channel_count must be positive.")

    normalized = normalize_loopback_chunk(chunk)
    if normalized.shape[1] == channel_count:
        return normalized
    if normalized.shape[1] > channel_count:
        return normalized[:, :channel_count]
    if normalized.shape[1] == 1:
        return np.repeat(normalized, channel_count, axis=1)

    padding = np.repeat(normalized[:, -1:], channel_count - normalized.shape[1], axis=1)
    return np.concatenate([normalized, padding], axis=1)


def split_capture_blocks(
    pending: FloatChunk,
    block_frames: int,
) -> tuple[list[FloatChunk], FloatChunk]:
    """Split buffered capture data into fixed analysis blocks."""

    normalized = normalize_loopback_chunk(pending)
    if block_frames <= 0:
        raise ValueError("block_frames must be positive.")

    total_frames = normalized.shape[0]
    complete_frames = (total_frames // block_frames) * block_frames
    if complete_frames == 0:
        return [], normalized

    blocks = [
        normalized[index : index + block_frames]
        for index in range(0, complete_frames, block_frames)
    ]
    remainder = normalized[complete_frames:]
    return blocks, remainder


def prepare_loopback_waveform_samples(
    chunk: FloatChunk,
    *,
    target_peak: float = 0.55,
    max_gain: float = 4.0,
) -> FloatChunk:
    """Boost loopback waveform display samples without changing spectrum analysis."""

    normalized = normalize_loopback_chunk(chunk)
    if normalized.size == 0:
        return normalized

    peak = float(np.max(np.abs(normalized)))
    if peak <= 1e-4:
        return normalized.copy()

    desired_gain = target_peak / peak
    gain = float(np.clip(desired_gain, 1.0, max_gain))
    return np.tanh(normalized * gain).astype(np.float32)


@dataclass(frozen=True)
class _CaptureSettings:
    """Derived capture settings for a loopback session."""

    device_id: str
    device_name: str
    sample_rate: int


class SoundcardLoopbackBackend:
    """Adapter around the optional soundcard dependency."""

    def __init__(self, soundcard_module: object | None = None) -> None:
        self._soundcard = soundcard_module if soundcard_module is not None else sc
        _patch_soundcard_numpy_compat(self._soundcard)

    def availability_error(self) -> str | None:
        if platform.system() != "Windows":
            return "System Audio (Windows) is only available on Windows 10."
        if self._soundcard is None:
            return "Install the optional 'soundcard' package to enable system audio capture."
        return None

    def list_output_devices(self) -> list[AudioDeviceInfo]:
        error = self.availability_error()
        if error is not None:
            return []

        speakers = list(self._soundcard.all_speakers())
        default_speaker = self._safe_default_speaker()
        default_id = _device_identifier(default_speaker)

        devices = [
            AudioDeviceInfo(
                identifier=_device_identifier(speaker),
                name=_device_name(speaker),
                is_default=_device_identifier(speaker) == default_id,
            )
            for speaker in speakers
        ]
        devices.sort(key=lambda device: (not device.is_default, device.name.lower()))
        return devices

    def open_recorder(
        self,
        device_id: str,
        samplerate: int,
        blocksize: int,
    ) -> RecorderContextProtocol:
        speaker = self._find_speaker(device_id)
        microphone = self._resolve_loopback_microphone(speaker)
        return microphone.recorder(samplerate=samplerate, blocksize=blocksize)

    def _safe_default_speaker(self) -> object | None:
        try:
            return self._soundcard.default_speaker()
        except Exception:
            return None

    def _find_speaker(self, device_id: str) -> object:
        for speaker in self._soundcard.all_speakers():
            if _device_identifier(speaker) == device_id:
                return speaker
        raise RuntimeError("The selected Windows output device is no longer available.")

    def _resolve_loopback_microphone(self, speaker: object) -> object:
        speaker_id = _device_identifier(speaker)
        speaker_name = _device_name(speaker).casefold()

        get_microphone = getattr(self._soundcard, "get_microphone", None)
        if callable(get_microphone):
            try:
                loopback = get_microphone(speaker_id, include_loopback=True)
            except Exception:
                loopback = None
            if loopback is not None and getattr(loopback, "isloopback", False):
                return loopback

        microphones = self._soundcard.all_microphones(include_loopback=True)
        loopbacks = [microphone for microphone in microphones if getattr(microphone, "isloopback", False)]
        for microphone in loopbacks:
            if _device_identifier(microphone) == speaker_id:
                return microphone
        for microphone in loopbacks:
            if speaker_name and speaker_name in _device_name(microphone).casefold():
                return microphone

        raise RuntimeError(
            "Could not map the selected speaker to a WASAPI loopback endpoint."
        )


def _device_identifier(device: object | None) -> str:
    if device is None:
        return ""
    for attribute in ("id", "identifier", "name"):
        value = getattr(device, attribute, None)
        if value:
            return str(value)
    return str(device)


def _device_name(device: object | None) -> str:
    if device is None:
        return ""
    value = getattr(device, "name", None)
    if value:
        return str(value)
    return str(device)


class SystemLoopbackSource(BaseAudioSource):
    """Capture Windows output audio through WASAPI loopback without playback."""

    SAMPLE_RATE_CANDIDATES = (48_000, 44_100)

    def __init__(
        self,
        config: AppConfig = DEFAULT_CONFIG,
        backend: LoopbackBackendProtocol | None = None,
    ) -> None:
        self.config = config
        self._backend = backend if backend is not None else SoundcardLoopbackBackend()
        self._lock = threading.RLock()
        self._analysis = make_empty_analysis_frame(
            sample_rate=self.SAMPLE_RATE_CANDIDATES[0],
            waveform_points=self.config.waveform_points,
            spectrum_points=self.config.fft_size // 2 + 1,
        )
        self._state = TransportState.STOPPED
        self._error_message: str | None = None
        self._thread: threading.Thread | None = None
        self._stop_event: threading.Event | None = None
        self._selected_device_id: str | None = None
        self._selected_device_name = "No device selected"
        self._available_devices: list[AudioDeviceInfo] = []
        self._analysis_window_frames = max(
            self.config.fft_size,
            self.config.waveform_window_frames,
        )
        self.refresh_devices()

    def availability_error(self) -> str | None:
        """Return a user-facing reason when loopback capture is unavailable."""

        return self._backend.availability_error()

    def list_output_devices(self) -> list[AudioDeviceInfo]:
        """Return the currently known output devices."""

        with self._lock:
            return list(self._available_devices)

    def selected_output_device_id(self) -> str | None:
        """Return the currently selected output-device identifier."""

        with self._lock:
            return self._selected_device_id

    def refresh_devices(self) -> list[AudioDeviceInfo]:
        """Refresh the list of Windows output devices and preserve selection when possible."""

        devices = self._backend.list_output_devices()
        with self._lock:
            previous_id = self._selected_device_id
            self._available_devices = devices
            if not devices:
                self._selected_device_id = None
                self._selected_device_name = "No output devices found"
            elif previous_id and any(device.identifier == previous_id for device in devices):
                selected = next(device for device in devices if device.identifier == previous_id)
                self._selected_device_id = selected.identifier
                self._selected_device_name = selected.name
            else:
                selected = next((device for device in devices if device.is_default), devices[0])
                self._selected_device_id = selected.identifier
                self._selected_device_name = selected.name
        return devices

    def select_output_device(self, device_id: str) -> None:
        """Select the output device used for loopback capture."""

        with self._lock:
            match = next(
                (device for device in self._available_devices if device.identifier == device_id),
                None,
            )
            if match is None:
                raise RuntimeError("The selected output device is no longer available.")

            was_running = self._state == TransportState.PLAYING
            if match.identifier == self._selected_device_id and not was_running:
                self._selected_device_name = match.name
                return

            self._selected_device_id = match.identifier
            self._selected_device_name = match.name

        if was_running:
            self.stop()
            self.start()

    def start(self) -> None:
        """Start loopback capture from the selected output device."""

        availability_error = self.availability_error()
        if availability_error is not None:
            raise RuntimeError(availability_error)

        self.refresh_devices()
        with self._lock:
            if self._state == TransportState.PLAYING:
                return
            if self._selected_device_id is None:
                raise RuntimeError("No Windows output devices were found.")

            self._state = TransportState.PLAYING
            self._error_message = None
            self._stop_event = threading.Event()
            thread = threading.Thread(
                target=self._capture_loop,
                name="PulseCanvasLoopbackCapture",
                daemon=True,
            )
            self._thread = thread

        thread.start()

    def stop(self) -> None:
        """Stop loopback capture and clear active resources."""

        with self._lock:
            stop_event = self._stop_event
            thread = self._thread
            self._stop_event = None

        if stop_event is not None:
            stop_event.set()
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.5)

        with self._lock:
            self._thread = None
            self._state = TransportState.STOPPED
            self._analysis = make_empty_analysis_frame(
                sample_rate=self._analysis.sample_rate,
                waveform_points=self.config.waveform_points,
                spectrum_points=self.config.fft_size // 2 + 1,
            )

    def close(self) -> None:
        """Release capture resources."""

        self.stop()

    def get_snapshot(self) -> PlaybackSnapshot:
        """Return a UI-facing snapshot for the live system-audio source."""

        with self._lock:
            availability_error = self.availability_error()
            if availability_error is not None:
                error_message = availability_error
            else:
                error_message = self._error_message

            active = bool(self._thread is not None and self._thread.is_alive())
            can_start = availability_error is None and self._selected_device_id is not None and not active
            detail_text = self._selected_device_name
            if availability_error is not None:
                detail_text = availability_error

            return PlaybackSnapshot(
                state=self._state,
                metadata=None,
                position=0.0,
                duration=0.0,
                volume=1.0,
                stream_active=active,
                source_mode=AudioSourceMode.SYSTEM,
                source_name="System Audio",
                detail_text=detail_text,
                status_text="Capturing" if active else "Stopped",
                primary_action_label="Start Capture",
                primary_action_enabled=can_start,
                open_file_enabled=False,
                stop_enabled=active,
                volume_enabled=False,
                error_message=error_message,
            )

    def get_analysis(self) -> AnalysisFrame:
        """Return the latest captured analysis frame."""

        with self._lock:
            return self._analysis

    def _capture_loop(self) -> None:
        settings: _CaptureSettings | None = None
        analyzer: AudioAnalyzer | None = None
        history: FloatChunk | None = None
        pending: FloatChunk | None = None
        channel_count: int | None = None

        try:
            settings = self._open_capture_settings()
            analyzer = AudioAnalyzer(sample_rate=settings.sample_rate, config=self.config)
            history = np.zeros((0, 1), dtype=np.float32)
            pending = np.zeros((0, 1), dtype=np.float32)

            with self._backend.open_recorder(
                settings.device_id,
                samplerate=settings.sample_rate,
                blocksize=self.config.audio_block_size,
            ) as recorder:
                while True:
                    with self._lock:
                        stop_event = self._stop_event
                    if stop_event is None or stop_event.is_set():
                        break

                    raw_chunk = recorder.record(numframes=self.config.audio_block_size)
                    chunk = normalize_loopback_chunk(raw_chunk)
                    if chunk.shape[0] == 0:
                        continue
                    if channel_count is None:
                        channel_count = max(1, chunk.shape[1])
                        history = np.zeros((0, channel_count), dtype=np.float32)
                        pending = np.zeros((0, channel_count), dtype=np.float32)
                    chunk = match_channel_count(chunk, channel_count)
                    pending = np.concatenate([pending, chunk], axis=0)
                    blocks, pending = split_capture_blocks(pending, self.config.audio_block_size)
                    for block in blocks:
                        history = np.concatenate([history, block], axis=0)
                        history = history[-self._analysis_window_frames :]
                        waveform_block = prepare_loopback_waveform_samples(block)
                        analysis = analyzer.analyze(
                            history,
                            timestamp=perf_counter(),
                            waveform_samples=waveform_block,
                        )
                        with self._lock:
                            self._analysis = analysis
                            self._error_message = None
        except Exception as exc:  # pragma: no cover - hardware dependent
            with self._lock:
                self._analysis = make_empty_analysis_frame(
                    sample_rate=settings.sample_rate if settings is not None else self.SAMPLE_RATE_CANDIDATES[0],
                    waveform_points=self.config.waveform_points,
                    spectrum_points=self.config.fft_size // 2 + 1,
                )
                self._error_message = str(exc)
        finally:
            with self._lock:
                self._thread = None
                self._stop_event = None
                self._state = TransportState.STOPPED

    def _open_capture_settings(self) -> _CaptureSettings:
        with self._lock:
            device_id = self._selected_device_id
            device_name = self._selected_device_name

        if device_id is None:
            raise RuntimeError("No Windows output device is selected for system-audio capture.")

        last_error: Exception | None = None
        for sample_rate in self.SAMPLE_RATE_CANDIDATES:
            try:
                with self._backend.open_recorder(
                    device_id,
                    samplerate=sample_rate,
                    blocksize=self.config.audio_block_size,
                ):
                    return _CaptureSettings(
                        device_id=device_id,
                        device_name=device_name,
                        sample_rate=sample_rate,
                    )
            except Exception as exc:  # pragma: no cover - hardware dependent
                last_error = exc

        if last_error is None:
            raise RuntimeError("Unable to open system audio capture.")
        raise RuntimeError(
            f"Could not start WASAPI loopback capture on '{device_name}': {last_error}"
        ) from last_error


def _patch_soundcard_numpy_compat(soundcard_module: object | None) -> None:
    """Patch old soundcard Windows recorders to work with NumPy 2.x."""

    mediafoundation = _get_soundcard_mediafoundation_module(soundcard_module)
    if mediafoundation is None:
        return

    recorder_class = getattr(mediafoundation, "_Recorder", None)
    if recorder_class is None or getattr(recorder_class, "_pulsecanvas_numpy2_compat", False):
        return

    def _record_chunk(self: object) -> FloatChunk:
        while self._capture_available_frames() == 0:
            if self._idle_start_time is None:
                self._idle_start_time = mediafoundation.time.perf_counter_ns()

            default_block_length, minimum_block_length = self.deviceperiod
            mediafoundation.time.sleep(minimum_block_length / 4)
            elapsed_time_ns = mediafoundation.time.perf_counter_ns() - self._idle_start_time
            if elapsed_time_ns / 1_000_000_000 > default_block_length * 4:
                num_frames = int(self.samplerate * elapsed_time_ns / 1_000_000_000)
                num_channels = len(set(self.channelmap))
                self._idle_start_time += elapsed_time_ns
                return np.zeros([num_frames * num_channels], dtype="float32")

        self._idle_start_time = None
        data_ptr, nframes, flags = self._capture_buffer()
        if data_ptr == mediafoundation._ffi.NULL:
            raise RuntimeError("Could not create capture buffer")

        channel_count = len(set(self.channelmap))
        raw_buffer = mediafoundation._ffi.buffer(data_ptr, nframes * 4 * channel_count)
        chunk = np.frombuffer(raw_buffer, dtype="float32").copy()
        if flags & mediafoundation._ole32.AUDCLNT_BUFFERFLAGS_SILENT:
            chunk[:] = 0
        if self._is_first_frame:
            flags &= ~mediafoundation._ole32.AUDCLNT_BUFFERFLAGS_DATA_DISCONTINUITY
            self._is_first_frame = False
        # Shared-mode WASAPI loopback can report discontinuities during normal
        # device scheduling changes. They are noisy in terminals and not actionable here.
        if nframes > 0:
            self._capture_release(nframes)
            return chunk
        return np.zeros([0], dtype="float32")

    recorder_class._record_chunk = _record_chunk
    recorder_class._pulsecanvas_numpy2_compat = True


def _get_soundcard_mediafoundation_module(soundcard_module: object | None) -> object | None:
    """Return soundcard's Windows backend module when available."""

    if soundcard_module is None or platform.system() != "Windows":
        return None

    module_name = getattr(soundcard_module, "__name__", "")
    try:
        if module_name == "soundcard.mediafoundation":
            return soundcard_module
        return importlib.import_module("soundcard.mediafoundation")
    except Exception:
        return None
