"""Qt user interface for the music visualizer."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QCloseEvent, QFont, QKeySequence, QLinearGradient, QPainter, QPaintEvent, QShortcut
from PySide6.QtWidgets import (
    QFileDialog,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from app.audio_engine import AudioEngine
from app.config import AppConfig, DEFAULT_CONFIG
from app.models import AnalysisFrame, PlaybackSnapshot, TransportState, make_empty_analysis_frame
from app.utils import format_seconds
from app.visualizers import build_visualizers
from app.visualizers.base import BaseVisualizer


class VisualizerCanvas(QWidget):
    """Paint the active visualizer onto the central canvas."""

    def __init__(self, config: AppConfig, visualizers: list[BaseVisualizer], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self._visualizers = {visualizer.mode_id: visualizer for visualizer in visualizers}
        self._mode_id = visualizers[0].mode_id
        self._analysis: AnalysisFrame = make_empty_analysis_frame(
            sample_rate=48_000,
            waveform_points=config.waveform_points,
            spectrum_points=config.fft_size // 2 + 1,
        )
        self._snapshot = PlaybackSnapshot(
            state=TransportState.STOPPED,
            metadata=None,
            position=0.0,
            duration=0.0,
            volume=1.0,
            stream_active=False,
            error_message=None,
        )
        self.setMinimumHeight(420)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)

    def set_mode(self, mode_id: str) -> None:
        """Switch the active visualizer."""

        if mode_id in self._visualizers:
            self._mode_id = mode_id
            self.update()

    def set_frame(self, analysis: AnalysisFrame, snapshot: PlaybackSnapshot) -> None:
        """Update the canvas with the latest playback and analysis state."""

        self._analysis = analysis
        self._snapshot = snapshot
        self.update()

    def active_mode_name(self) -> str:
        """Return the display name of the current visualizer."""

        return self._visualizers[self._mode_id].display_name

    def paintEvent(self, event: QPaintEvent) -> None:
        del event

        theme = self.config.theme
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        gradient = QLinearGradient(0.0, 0.0, 0.0, float(self.height()))
        gradient.setColorAt(0.0, QColor(theme.background_top))
        gradient.setColorAt(1.0, QColor(theme.background_bottom))
        painter.fillRect(self.rect(), gradient)

        pulse_strength = min(1.0, self._analysis.bands.bass * 1.5 + self._analysis.rms * 0.7)

        pulse_color = QColor(theme.accent_primary)
        pulse_color.setAlpha(int(28 + pulse_strength * 45))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(pulse_color)
        painter.drawEllipse(
            QRectF(
                self.width() * 0.12,
                self.height() * 0.08,
                self.width() * 0.36,
                self.width() * 0.36,
            )
        )

        warm_color = QColor(theme.accent_warm)
        warm_color.setAlpha(int(16 + self._analysis.bands.treble * 55))
        painter.setBrush(warm_color)
        painter.drawEllipse(
            QRectF(
                self.width() * 0.6,
                self.height() * 0.18,
                self.width() * 0.28,
                self.width() * 0.28,
            )
        )

        content_rect = QRectF(self.rect()).adjusted(28.0, 28.0, -28.0, -28.0)
        if self._snapshot.metadata is None:
            self._draw_empty_state(painter, content_rect)
            return

        self._visualizers[self._mode_id].render(painter, content_rect, self._analysis)
        self._draw_overlay(painter, content_rect)

    def _draw_empty_state(self, painter: QPainter, rect: QRectF) -> None:
        theme = self.config.theme
        painter.setPen(QColor(theme.text_primary))
        title_font = QFont("Segoe UI", 20)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Open an audio file to start visualizing")

        painter.setPen(QColor(theme.text_secondary))
        subtitle_rect = rect.adjusted(0.0, 48.0, 0.0, 0.0)
        painter.setFont(QFont("Segoe UI", 11))
        painter.drawText(
            subtitle_rect,
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            "Modes: spectrum bars, waveform, radial spectrum. Shortcuts: Space, 1/2/3, F.",
        )

    def _draw_overlay(self, painter: QPainter, rect: QRectF) -> None:
        theme = self.config.theme
        overlay_font = QFont("Segoe UI", 9)
        overlay_font.setBold(True)
        painter.setFont(overlay_font)

        painter.setPen(QColor(theme.text_secondary))
        painter.drawText(
            rect.adjusted(8.0, 4.0, -8.0, -4.0),
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
            self.active_mode_name().upper(),
        )

        painter.setPen(QColor(theme.text_primary))
        painter.drawText(
            rect.adjusted(8.0, 4.0, -8.0, -4.0),
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight,
            self._snapshot.state.value.upper(),
        )


class MainWindow(QMainWindow):
    """Main application window and playback controls."""

    def __init__(self, config: AppConfig = DEFAULT_CONFIG) -> None:
        super().__init__()
        self.config = config
        self.engine = AudioEngine(config)
        self.visualizers = build_visualizers(config)
        self._last_error_message: str | None = None

        self.setWindowTitle(config.window_title)
        self.setMinimumSize(config.min_width, config.min_height)

        self.canvas = VisualizerCanvas(config, self.visualizers, self)
        self.file_label = QLabel("No file loaded")
        self.state_label = QLabel(TransportState.STOPPED.value)
        self.position_label = QLabel("00:00 / 00:00")
        self.open_button = QPushButton("Open File")
        self.play_pause_button = QPushButton("Play")
        self.stop_button = QPushButton("Stop")
        self.mode_combo = QComboBox()
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)

        self._setup_ui()
        self._setup_shortcuts()
        self._setup_timer()
        self._refresh_from_engine()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.engine.close()
        super().closeEvent(event)

    def open_file_dialog(self) -> None:
        """Show an audio picker and load the selected file."""

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Audio File",
            str(Path.home()),
            "Audio Files (*.wav *.flac *.ogg *.aiff *.aif *.mp3);;All Files (*.*)",
        )
        if not file_path:
            return

        self._load_file(file_path)

    def toggle_play_pause(self) -> None:
        """Toggle playback from the current transport state."""

        snapshot = self.engine.get_snapshot()
        if snapshot.metadata is None:
            self.open_file_dialog()
            return

        try:
            self.engine.toggle_play_pause()
        except RuntimeError as exc:
            self._show_error("Playback Error", str(exc))
        finally:
            self._refresh_from_engine()

    def stop_playback(self) -> None:
        """Stop playback and reset the playhead."""

        self.engine.stop()
        self._refresh_from_engine()

    def toggle_fullscreen(self) -> None:
        """Toggle fullscreen mode."""

        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _setup_ui(self) -> None:
        theme = self.config.theme
        central = QWidget(self)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(14, 14, 14, 14)
        root_layout.setSpacing(14)

        info_panel = QFrame(self)
        info_panel.setObjectName("controlPanel")
        info_layout = QHBoxLayout(info_panel)
        info_layout.setContentsMargins(18, 14, 18, 14)
        info_layout.setSpacing(18)

        file_caption = QLabel("Track")
        file_caption.setObjectName("caption")
        state_caption = QLabel("State")
        state_caption.setObjectName("caption")
        position_caption = QLabel("Position")
        position_caption.setObjectName("caption")

        file_stack = QVBoxLayout()
        file_stack.setSpacing(4)
        file_stack.addWidget(file_caption)
        file_stack.addWidget(self.file_label)

        state_stack = QVBoxLayout()
        state_stack.setSpacing(4)
        state_stack.addWidget(state_caption)
        state_stack.addWidget(self.state_label)

        position_stack = QVBoxLayout()
        position_stack.setSpacing(4)
        position_stack.addWidget(position_caption)
        position_stack.addWidget(self.position_label)

        info_layout.addLayout(file_stack, 1)
        info_layout.addLayout(state_stack)
        info_layout.addLayout(position_stack)

        controls_panel = QFrame(self)
        controls_panel.setObjectName("controlPanel")
        controls_layout = QHBoxLayout(controls_panel)
        controls_layout.setContentsMargins(18, 12, 18, 12)
        controls_layout.setSpacing(14)

        for visualizer in self.visualizers:
            self.mode_combo.addItem(visualizer.display_name, visualizer.mode_id)

        self.volume_slider.setRange(0, int(self.config.max_volume * 100))
        self.volume_slider.setValue(100)

        mode_label = QLabel("Mode")
        mode_label.setObjectName("caption")
        volume_label = QLabel("Volume")
        volume_label.setObjectName("caption")

        controls_layout.addWidget(self.open_button)
        controls_layout.addWidget(self.play_pause_button)
        controls_layout.addWidget(self.stop_button)
        controls_layout.addSpacing(8)
        controls_layout.addWidget(mode_label)
        controls_layout.addWidget(self.mode_combo)
        controls_layout.addSpacing(8)
        controls_layout.addWidget(volume_label)
        controls_layout.addWidget(self.volume_slider, 1)

        root_layout.addWidget(self.canvas, 1)
        root_layout.addWidget(info_panel)
        root_layout.addWidget(controls_panel)
        self.setCentralWidget(central)
        self.statusBar().showMessage("Ready")

        self.open_button.clicked.connect(self.open_file_dialog)
        self.play_pause_button.clicked.connect(self.toggle_play_pause)
        self.stop_button.clicked.connect(self.stop_playback)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self.volume_slider.valueChanged.connect(self._on_volume_changed)

        self.setStyleSheet(
            f"""
            QMainWindow {{
                background-color: {theme.background_bottom};
            }}
            QFrame#controlPanel {{
                background-color: {theme.panel_background};
                border: 1px solid {theme.panel_border};
                border-radius: 16px;
            }}
            QLabel {{
                color: {theme.text_primary};
                font-size: 13px;
            }}
            QLabel#caption {{
                color: {theme.text_secondary};
                font-size: 11px;
            }}
            QPushButton {{
                background-color: {theme.panel_border};
                color: {theme.text_primary};
                border: 1px solid {theme.panel_border};
                border-radius: 10px;
                padding: 8px 14px;
                min-width: 88px;
            }}
            QPushButton:hover {{
                background-color: {theme.accent_secondary};
                border-color: {theme.accent_secondary};
            }}
            QPushButton:pressed {{
                background-color: {theme.accent_primary};
                border-color: {theme.accent_primary};
                color: {theme.background_bottom};
            }}
            QComboBox {{
                background-color: {theme.background_top};
                color: {theme.text_primary};
                border: 1px solid {theme.panel_border};
                border-radius: 10px;
                padding: 7px 12px;
                min-width: 170px;
            }}
            QSlider::groove:horizontal {{
                background: {theme.background_top};
                height: 6px;
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: {theme.accent_primary};
                width: 16px;
                margin: -6px 0;
                border-radius: 8px;
            }}
            QStatusBar {{
                color: {theme.text_secondary};
            }}
            """
        )

    def _setup_shortcuts(self) -> None:
        QShortcut(QKeySequence("Space"), self, activated=self.toggle_play_pause)
        QShortcut(QKeySequence("1"), self, activated=lambda: self._set_mode_by_index(0))
        QShortcut(QKeySequence("2"), self, activated=lambda: self._set_mode_by_index(1))
        QShortcut(QKeySequence("3"), self, activated=lambda: self._set_mode_by_index(2))
        QShortcut(QKeySequence("F"), self, activated=self.toggle_fullscreen)

    def _setup_timer(self) -> None:
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_from_engine)
        self._timer.start(max(8, int(1000 / self.config.ui_fps)))

    def _load_file(self, path: str) -> None:
        try:
            metadata = self.engine.load_file(path)
        except RuntimeError as exc:
            self._show_error("Open File Failed", str(exc))
            return

        self.statusBar().showMessage(f"Loaded {metadata.title}", 5000)
        self.file_label.setToolTip(str(metadata.path))
        self._refresh_from_engine()

    def _refresh_from_engine(self) -> None:
        snapshot = self.engine.get_snapshot()
        analysis = self.engine.get_analysis()
        self.canvas.set_frame(analysis, snapshot)

        if snapshot.metadata is None:
            self.file_label.setText("No file loaded")
        else:
            self.file_label.setText(snapshot.metadata.title)

        self.state_label.setText(snapshot.state.value)
        self.position_label.setText(
            f"{format_seconds(snapshot.position)} / {format_seconds(snapshot.duration)}"
        )
        self.play_pause_button.setText(
            "Pause" if snapshot.state == TransportState.PLAYING else "Play"
        )
        self.stop_button.setEnabled(snapshot.metadata is not None)

        if snapshot.error_message and snapshot.error_message != self._last_error_message:
            self.statusBar().showMessage(snapshot.error_message, 6000)
        self._last_error_message = snapshot.error_message

    def _on_mode_changed(self, index: int) -> None:
        mode_id = self.mode_combo.itemData(index)
        if isinstance(mode_id, str):
            self.canvas.set_mode(mode_id)

    def _set_mode_by_index(self, index: int) -> None:
        if 0 <= index < self.mode_combo.count():
            self.mode_combo.setCurrentIndex(index)

    def _on_volume_changed(self, value: int) -> None:
        self.engine.set_volume(value / 100.0)
        self.statusBar().showMessage(f"Volume {value}%", 1500)

    def _show_error(self, title: str, message: str) -> None:
        QMessageBox.critical(self, title, message)
        self.statusBar().showMessage(message, 7000)
