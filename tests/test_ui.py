"""Small UI-adjacent tests that do not require showing a window."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl

import app.ui as ui_module
from app.config import AppConfig
from app.models import AudioDeviceInfo, AudioSourceMode, PlaybackSnapshot, TransportState, make_empty_analysis_frame
from app.ui import MainWindow


def test_extract_first_local_file_prefers_local_urls() -> None:
    urls = [
        QUrl("https://example.com/file.mp3"),
        QUrl.fromLocalFile(r"D:\Music Visualizer\demo.wav"),
    ]

    assert Path(MainWindow._extract_first_local_file(urls) or "") == Path(
        r"D:\Music Visualizer\demo.wav"
    )


def test_extract_first_local_file_returns_none_for_non_local_urls() -> None:
    urls = [QUrl("https://example.com/file.mp3")]

    assert MainWindow._extract_first_local_file(urls) is None


class FakeEngine:
    """Tiny engine double used to test source-aware UI state."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._mode = AudioSourceMode.FILE
        self.play_calls = 0
        self._system_active = False

    def source_modes(self) -> list[tuple[AudioSourceMode, str, bool]]:
        return [
            (AudioSourceMode.FILE, "File", True),
            (AudioSourceMode.SYSTEM, "System Audio (Windows)", True),
        ]

    def get_source_mode(self) -> AudioSourceMode:
        return self._mode

    def set_source_mode(self, mode: AudioSourceMode) -> None:
        self._mode = mode

    def get_snapshot(self) -> PlaybackSnapshot:
        if self._mode == AudioSourceMode.SYSTEM:
            return PlaybackSnapshot(
                state=TransportState.PLAYING if self._system_active else TransportState.STOPPED,
                metadata=None,
                position=0.0,
                duration=0.0,
                volume=1.0,
                stream_active=self._system_active,
                source_mode=AudioSourceMode.SYSTEM,
                source_name="System Audio",
                detail_text="Speakers",
                status_text="Capturing" if self._system_active else "Stopped",
                primary_action_label="Start Capture",
                primary_action_enabled=not self._system_active,
                open_file_enabled=False,
                stop_enabled=self._system_active,
                volume_enabled=False,
            )

        return PlaybackSnapshot(
            state=TransportState.STOPPED,
            metadata=None,
            position=0.0,
            duration=0.0,
            volume=1.0,
            stream_active=False,
            source_mode=AudioSourceMode.FILE,
            source_name="No file loaded",
            detail_text="00:00 / 00:00",
            status_text="Stopped",
            primary_action_label="Play",
            primary_action_enabled=True,
            open_file_enabled=True,
            stop_enabled=False,
            volume_enabled=True,
        )

    def get_analysis(self):  # type: ignore[no-untyped-def]
        return make_empty_analysis_frame(
            sample_rate=48_000,
            waveform_points=self.config.waveform_points,
            spectrum_points=self.config.fft_size // 2 + 1,
        )

    def refresh_output_devices(self) -> list[AudioDeviceInfo]:
        return self.list_output_devices()

    def list_output_devices(self) -> list[AudioDeviceInfo]:
        return [AudioDeviceInfo(identifier="default", name="Speakers", is_default=True)]

    def selected_output_device_id(self) -> str | None:
        return "default"

    def system_audio_availability_error(self) -> str | None:
        return None

    def close(self) -> None:
        return None

    def stop(self) -> None:
        self._system_active = False

    def toggle_play_pause(self) -> None:
        return None

    def play(self) -> None:
        self.play_calls += 1
        if self._mode == AudioSourceMode.SYSTEM:
            self._system_active = True

    def set_volume(self, volume: float) -> None:
        del volume

    def select_output_device(self, device_id: str) -> None:
        del device_id

    def load_file(self, path: str):  # type: ignore[no-untyped-def]
        del path
        raise RuntimeError("not used in this test")


def test_main_window_toggles_controls_between_file_and_system_modes(
    qt_app,
    monkeypatch,
) -> None:
    del qt_app
    monkeypatch.setattr(ui_module, "AudioEngine", FakeEngine)

    window = MainWindow()
    window.show()

    assert window.source_label.isVisible() is False
    assert window.state_label.isVisible() is False
    assert window.detail_label.isVisible() is False
    assert window.open_button.isEnabled() is False
    assert window.volume_slider.isEnabled() is False
    assert window.open_button.isHidden() is True
    assert window.play_pause_button.isHidden() is True
    assert window.stop_button.isHidden() is True
    assert window.volume_slider.isHidden() is True
    assert window.device_combo.isVisible() is False
    assert window.refresh_devices_button.isVisible() is False
    assert window.visualizer_only_button.text() == "▼"
    assert window.engine.play_calls == 1

    window.source_combo.setCurrentIndex(0)
    window._refresh_from_engine()

    assert window.open_button.isEnabled() is True
    assert window.volume_slider.isEnabled() is True
    assert window.open_button.isHidden() is False
    assert window.play_pause_button.isHidden() is False
    assert window.stop_button.isHidden() is False
    assert window.volume_slider.isHidden() is False
    assert window.device_combo.isVisible() is False

    window.source_combo.setCurrentIndex(1)
    window._refresh_from_engine()

    assert window.open_button.isEnabled() is False
    assert window.volume_slider.isEnabled() is False
    assert window.open_button.isHidden() is True
    assert window.play_pause_button.isHidden() is True
    assert window.stop_button.isHidden() is True
    assert window.volume_slider.isHidden() is True
    assert window.device_combo.isVisible() is False
    assert window.engine.play_calls == 2

    window.close()


def test_main_window_visualizer_only_mode_moves_controls_offscreen(
    qt_app,
    monkeypatch,
) -> None:
    del qt_app
    monkeypatch.setattr(ui_module, "AudioEngine", FakeEngine)

    window = MainWindow()
    window.resize(1200, 800)
    window.show()

    visible_y = window.controls_panel.y()
    assert window.visualizer_only_button.isChecked() is False
    assert window.intensity_slider.maximumWidth() == 320

    window._set_visualizer_only_mode(True, animate=False)

    assert window.visualizer_only_button.isChecked() is True
    assert window.controls_panel.y() >= window.centralWidget().height()

    window._set_visualizer_only_mode(False, animate=False)

    assert window.visualizer_only_button.isChecked() is False
    assert window.controls_panel.y() == visible_y

    window.close()


def test_main_window_supports_topmost_and_borderless_toggles(
    qt_app,
    monkeypatch,
) -> None:
    del qt_app
    monkeypatch.setattr(ui_module, "AudioEngine", FakeEngine)

    window = MainWindow()
    window.show()

    assert window.minimumWidth() == 900
    assert window.minimumHeight() == 560
    assert bool(window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint) is False
    assert bool(window.windowFlags() & Qt.WindowType.FramelessWindowHint) is False

    window.toggle_always_on_top()
    assert bool(window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint) is True

    window.toggle_borderless_mode()
    assert bool(window.windowFlags() & Qt.WindowType.FramelessWindowHint) is True

    window.toggle_always_on_top()
    window.toggle_borderless_mode()
    assert bool(window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint) is False
    assert bool(window.windowFlags() & Qt.WindowType.FramelessWindowHint) is False

    window.close()
