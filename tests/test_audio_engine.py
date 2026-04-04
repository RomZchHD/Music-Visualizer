"""Tests for audio engine behaviors that do not require live audio output."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

import app.audio_engine as audio_engine_module
from app.audio_engine import AudioEngine
from app.config import AppConfig


class FakeOutputStream:
    """Small fake stream used to test replay behavior."""

    instances: list["FakeOutputStream"] = []

    def __init__(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        self.active = False
        self.closed = False
        FakeOutputStream.instances.append(self)

    def start(self) -> None:
        self.active = True

    def stop(self) -> None:
        self.active = False

    def close(self) -> None:
        self.closed = True
        self.active = False


def make_engine_config() -> AppConfig:
    """Return a compact config for tests."""

    return AppConfig(
        audio_block_size=256,
        fft_size=1024,
        waveform_points=128,
        waveform_window_frames=256,
    )


def write_test_wave(path: Path, sample_rate: int = 48_000) -> None:
    """Write a short sine-wave file for integration checks."""

    timeline = np.arange(sample_rate // 8, dtype=np.float32) / float(sample_rate)
    signal = 0.25 * np.sin(2.0 * np.pi * 220.0 * timeline).astype(np.float32)
    sf.write(path, signal, sample_rate)


def test_play_after_end_recreates_stream(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source_path = tmp_path / "tone.wav"
    write_test_wave(source_path)
    engine = AudioEngine(make_engine_config())
    metadata = engine.load_file(source_path)

    monkeypatch.setattr(audio_engine_module.sd, "OutputStream", FakeOutputStream)
    exhausted_stream = FakeOutputStream()
    engine._stream = exhausted_stream
    engine._current_frame = metadata.frames

    engine.play()

    assert exhausted_stream.closed is True
    assert engine.get_snapshot().state.value == "Playing"
    assert engine._current_frame == 0
    assert engine._stream is not None
    assert engine._stream is not exhausted_stream
    assert engine._stream.active is True


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is required for codec fallback tests")
@pytest.mark.parametrize(
    ("extension", "codec"),
    [
        (".aac", "aac"),
        (".opus", "libopus"),
    ],
)
def test_load_file_with_ffmpeg_supported_formats(
    tmp_path: Path,
    extension: str,
    codec: str,
) -> None:
    source_path = tmp_path / "source.wav"
    output_path = tmp_path / f"encoded{extension}"
    write_test_wave(source_path)

    subprocess.run(
        [
            shutil.which("ffmpeg") or "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(source_path),
            "-c:a",
            codec,
            str(output_path),
        ],
        check=True,
    )

    engine = AudioEngine(make_engine_config())
    metadata = engine.load_file(output_path)

    assert metadata.path == output_path.resolve()
    assert metadata.frames > 0
    assert metadata.duration > 0
