"""Audio source implementations used by the engine."""

from app.audio_sources.base import BaseAudioSource
from app.audio_sources.file_playback import FilePlaybackSource
from app.audio_sources.system_loopback import (
    SoundcardLoopbackBackend,
    SystemLoopbackSource,
    match_channel_count,
    normalize_loopback_chunk,
    prepare_loopback_waveform_samples,
    split_capture_blocks,
)

__all__ = [
    "BaseAudioSource",
    "FilePlaybackSource",
    "SoundcardLoopbackBackend",
    "SystemLoopbackSource",
    "match_channel_count",
    "normalize_loopback_chunk",
    "prepare_loopback_waveform_samples",
    "split_capture_blocks",
]
