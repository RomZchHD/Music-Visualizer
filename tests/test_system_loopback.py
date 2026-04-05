"""Tests for Windows loopback helpers and source lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
import time
import warnings

import numpy as np

from app.audio_sources.system_loopback import (
    SystemLoopbackSource,
    _patch_soundcard_numpy_compat,
    match_channel_count,
    normalize_loopback_chunk,
    prepare_loopback_waveform_samples,
    split_capture_blocks,
)
from app.config import AppConfig
from app.models import AudioDeviceInfo, TransportState


def make_config() -> AppConfig:
    """Create a test-friendly loopback config."""

    return AppConfig(
        audio_block_size=8,
        fft_size=32,
        waveform_points=16,
        waveform_window_frames=16,
    )


def test_normalize_loopback_chunk_promotes_to_float32_2d() -> None:
    mono = np.array([0.25, -0.25, 0.5], dtype=np.float64)

    normalized = normalize_loopback_chunk(mono)

    assert normalized.dtype == np.float32
    assert normalized.shape == (3, 1)


def test_match_channel_count_repeats_single_channel() -> None:
    mono = np.array([[0.2], [0.4]], dtype=np.float32)

    matched = match_channel_count(mono, channel_count=2)

    np.testing.assert_allclose(matched, np.array([[0.2, 0.2], [0.4, 0.4]], dtype=np.float32))


def test_split_capture_blocks_rechunks_pending_audio() -> None:
    pending = np.arange(20, dtype=np.float32).reshape(10, 2)

    blocks, remainder = split_capture_blocks(pending, block_frames=4)

    assert len(blocks) == 2
    assert blocks[0].shape == (4, 2)
    assert blocks[1].shape == (4, 2)
    assert remainder.shape == (2, 2)


def test_prepare_loopback_waveform_samples_boosts_quiet_audio_for_display() -> None:
    chunk = np.full((8, 2), 0.08, dtype=np.float32)

    boosted = prepare_loopback_waveform_samples(chunk)

    assert boosted.shape == chunk.shape
    assert boosted.dtype == np.float32
    assert float(np.max(np.abs(boosted))) > float(np.max(np.abs(chunk)))
    assert float(np.max(np.abs(boosted))) <= 1.0


@dataclass
class FakeRecorder:
    """Recorder that yields prepared chunks for loopback tests."""

    chunks: list[np.ndarray]

    def record(self, numframes: int) -> np.ndarray:
        del numframes
        if self.chunks:
            return self.chunks.pop(0)
        time.sleep(0.01)
        return np.zeros((8, 2), dtype=np.float32)


class FakeRecorderContext:
    """Context manager wrapper for the fake recorder."""

    def __init__(self, backend: "FakeLoopbackBackend") -> None:
        self._backend = backend
        self._recorder = FakeRecorder(self._backend.chunks)

    def __enter__(self) -> FakeRecorder:
        self._backend.open_count += 1
        return self._recorder

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        del exc_type, exc, tb
        self._backend.close_count += 1


class FakeLoopbackBackend:
    """Hardware-free backend for loopback-source tests."""

    def __init__(self, fail_48k: bool = False) -> None:
        self.fail_48k = fail_48k
        self.open_count = 0
        self.close_count = 0
        self.chunks = [
            np.full((8, 2), 0.25, dtype=np.float32),
            np.full((8, 2), 0.5, dtype=np.float32),
        ]

    def availability_error(self) -> str | None:
        return None

    def list_output_devices(self) -> list[AudioDeviceInfo]:
        return [
            AudioDeviceInfo(identifier="default", name="Speakers", is_default=True),
            AudioDeviceInfo(identifier="usb", name="USB DAC"),
        ]

    def open_recorder(self, device_id: str, samplerate: int, blocksize: int) -> FakeRecorderContext:
        del device_id, blocksize
        if self.fail_48k and samplerate == 48_000:
            raise RuntimeError("unsupported rate")
        return FakeRecorderContext(self)


def test_system_loopback_source_stop_cleans_up_thread() -> None:
    source = SystemLoopbackSource(make_config(), backend=FakeLoopbackBackend())

    source.start()
    time.sleep(0.05)
    source.stop()

    snapshot = source.get_snapshot()
    assert snapshot.state == TransportState.STOPPED
    assert snapshot.stream_active is False
    assert snapshot.stop_enabled is False


def test_system_loopback_source_falls_back_to_44100() -> None:
    source = SystemLoopbackSource(make_config(), backend=FakeLoopbackBackend(fail_48k=True))

    source.start()
    time.sleep(0.05)
    analysis = source.get_analysis()
    source.stop()

    assert analysis.sample_rate == 44_100


def test_select_output_device_restarts_active_capture() -> None:
    source = SystemLoopbackSource(make_config(), backend=FakeLoopbackBackend())
    calls: list[str] = []

    source._state = TransportState.PLAYING
    source._thread = None
    source._stop_event = None
    source._selected_device_id = "default"
    source._selected_device_name = "Speakers"
    source._available_devices = source.list_output_devices()
    source.stop = lambda: calls.append("stop")  # type: ignore[method-assign]
    source.start = lambda: calls.append("start")  # type: ignore[method-assign]

    source.select_output_device("usb")

    assert calls == ["stop", "start"]


def test_soundcard_numpy2_compat_patch_uses_frombuffer_copy() -> None:
    release_calls: list[int] = []

    class FakeRecorderClass:
        def __init__(self) -> None:
            self.channelmap = [0, 1]
            self.samplerate = 48_000
            self._idle_start_time = None
            self._is_first_frame = False
            self.deviceperiod = (0.01, 0.005)

        def _capture_available_frames(self) -> int:
            return 1

        def _capture_buffer(self) -> tuple[bytes, int, int]:
            return (
                np.array([0.25, -0.25, 0.5, -0.5], dtype=np.float32).tobytes(),
                2,
                0,
            )

        def _capture_release(self, numframes: int) -> None:
            release_calls.append(numframes)

    fake_module = SimpleNamespace(
        __name__="soundcard.mediafoundation",
        _Recorder=FakeRecorderClass,
        _ffi=SimpleNamespace(
            NULL=None,
            buffer=lambda data, size: memoryview(data)[:size],
        ),
        _ole32=SimpleNamespace(
            AUDCLNT_BUFFERFLAGS_SILENT=0x2,
            AUDCLNT_BUFFERFLAGS_DATA_DISCONTINUITY=0x1,
        ),
        time=time,
        warnings=warnings,
        SoundcardRuntimeWarning=RuntimeWarning,
    )

    _patch_soundcard_numpy_compat(fake_module)
    recorder = FakeRecorderClass()

    chunk = recorder._record_chunk()

    np.testing.assert_allclose(chunk, np.array([0.25, -0.25, 0.5, -0.5], dtype=np.float32))
    assert release_calls == [2]
