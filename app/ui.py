"""Qt user interface for the music visualizer."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt, QTimer, QUrl, QSignalBlocker
from PySide6.QtGui import (
    QColor,
    QCloseEvent,
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QFont,
    QKeySequence,
    QLinearGradient,
    QPainter,
    QPaintEvent,
    QShortcut,
)
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
from app.models import (
    AnalysisFrame,
    AudioSourceMode,
    PlaybackSnapshot,
    TransportState,
    make_empty_analysis_frame,
)
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
        self._intensity = config.default_visualizer_intensity
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
        self.set_visualizer_intensity(self._intensity)

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

    def set_visualizer_intensity(self, intensity: float) -> None:
        """Update the shared intensity multiplier for every visualizer."""

        self._intensity = intensity
        for visualizer in self._visualizers.values():
            visualizer.set_intensity(intensity)
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
        if self._snapshot.source_mode == AudioSourceMode.FILE and self._snapshot.metadata is None:
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
        if self._snapshot.source_mode == AudioSourceMode.SYSTEM:
            title = "Start system audio capture to visualize Windows output"
            subtitle = "Loopback capture uses your selected speaker device and never records the microphone."
        else:
            title = "Open an audio file to start visualizing"
            subtitle = "Modes: spectrum bars, waveform, radial spectrum. Shortcuts: Space, 1/2/3, F."

        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, title)

        painter.setPen(QColor(theme.text_secondary))
        subtitle_rect = rect.adjusted(0.0, 48.0, 0.0, 0.0)
        painter.setFont(QFont("Segoe UI", 11))
        painter.drawText(
            subtitle_rect,
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            subtitle,
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
            self._snapshot.status_text.upper(),
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
        self.source_label = QLabel("No file loaded")
        self.state_label = QLabel(TransportState.STOPPED.value)
        self.detail_label = QLabel("00:00 / 00:00")
        self.source_caption = QLabel("Source")
        self.detail_caption = QLabel("Position")
        self.open_button = QPushButton("Open File")
        self.play_pause_button = QPushButton("Play")
        self.stop_button = QPushButton("Stop")
        self.source_combo = QComboBox()
        self.device_label = QLabel("Output")
        self.device_combo = QComboBox()
        self.refresh_devices_button = QPushButton("↺")
        self.mode_combo = QComboBox()
        self.volume_caption = QLabel("Volume")
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.intensity_slider = QSlider(Qt.Orientation.Horizontal)

        self._setup_ui()
        self._setup_shortcuts()
        self._setup_timer()
        self._refresh_from_engine()
        self.setAcceptDrops(True)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.engine.close()
        super().closeEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._extract_first_local_file(event.mimeData().urls()) is not None:
            event.acceptProposedAction()
            self.statusBar().showMessage("Drop to open audio file", 1500)
            return
        event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if self._extract_first_local_file(event.mimeData().urls()) is not None:
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        path = self._extract_first_local_file(event.mimeData().urls())
        if path is None:
            event.ignore()
            return

        event.acceptProposedAction()
        self._load_file(path)

    def open_file_dialog(self) -> None:
        """Show an audio picker and load the selected file."""

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Audio File",
            str(Path.home()),
            "Audio Files (*.wav *.flac *.ogg *.opus *.aac *.aiff *.aif *.mp3);;All Files (*.*)",
        )
        if not file_path:
            return

        self._load_file(file_path)

    def toggle_play_pause(self) -> None:
        """Toggle playback from the current transport state."""

        snapshot = self.engine.get_snapshot()
        if snapshot.source_mode == AudioSourceMode.FILE and snapshot.metadata is None:
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

        self.source_caption.setObjectName("caption")
        state_caption = QLabel("State")
        state_caption.setObjectName("caption")
        self.detail_caption.setObjectName("caption")

        file_stack = QVBoxLayout()
        file_stack.setSpacing(4)
        file_stack.addWidget(self.source_caption)
        file_stack.addWidget(self.source_label)

        state_stack = QVBoxLayout()
        state_stack.setSpacing(4)
        state_stack.addWidget(state_caption)
        state_stack.addWidget(self.state_label)

        position_stack = QVBoxLayout()
        position_stack.setSpacing(4)
        position_stack.addWidget(self.detail_caption)
        position_stack.addWidget(self.detail_label)

        info_layout.addLayout(file_stack, 1)
        info_layout.addLayout(state_stack)
        info_layout.addLayout(position_stack)

        controls_panel = QFrame(self)
        controls_panel.setObjectName("controlPanel")
        controls_layout = QHBoxLayout(controls_panel)
        controls_layout.setContentsMargins(18, 12, 18, 12)
        controls_layout.setSpacing(14)

        source_label = QLabel("Source")
        source_label.setObjectName("caption")
        self.device_label.setObjectName("caption")
        self.refresh_devices_button.setObjectName("iconButton")
        self.refresh_devices_button.setToolTip("Refresh output devices")
        self.refresh_devices_button.setMinimumWidth(36)
        self.refresh_devices_button.setMaximumWidth(36)
        for visualizer in self.visualizers:
            self.mode_combo.addItem(visualizer.display_name, visualizer.mode_id)
        for mode, display_name, enabled in self.engine.source_modes():
            if enabled:
                self.source_combo.addItem(display_name, mode)

        self.volume_slider.setRange(0, int(self.config.max_volume * 100))
        self.volume_slider.setValue(100)
        self.intensity_slider.setRange(
            int(self.config.min_visualizer_intensity * 100),
            int(self.config.max_visualizer_intensity * 100),
        )
        self.intensity_slider.setValue(int(self.config.default_visualizer_intensity * 100))

        mode_label = QLabel("Mode")
        mode_label.setObjectName("caption")
        self.volume_caption.setObjectName("caption")
        intensity_label = QLabel("Intensity")
        intensity_label.setObjectName("caption")

        controls_layout.addWidget(source_label)
        controls_layout.addWidget(self.source_combo)
        controls_layout.addWidget(self.open_button)
        controls_layout.addWidget(self.play_pause_button)
        controls_layout.addWidget(self.stop_button)
        controls_layout.addWidget(self.device_label)
        controls_layout.addWidget(self.device_combo)
        controls_layout.addWidget(self.refresh_devices_button)
        controls_layout.addSpacing(8)
        controls_layout.addWidget(mode_label)
        controls_layout.addWidget(self.mode_combo)
        controls_layout.addSpacing(8)
        controls_layout.addWidget(self.volume_caption)
        controls_layout.addWidget(self.volume_slider, 1)
        controls_layout.addSpacing(8)
        controls_layout.addWidget(intensity_label)
        controls_layout.addWidget(self.intensity_slider, 1)

        root_layout.addWidget(self.canvas, 1)
        root_layout.addWidget(info_panel)
        root_layout.addWidget(controls_panel)
        self.setCentralWidget(central)
        self.statusBar().showMessage("Ready")

        self.open_button.clicked.connect(self.open_file_dialog)
        self.play_pause_button.clicked.connect(self.toggle_play_pause)
        self.stop_button.clicked.connect(self.stop_playback)
        self.source_combo.currentIndexChanged.connect(self._on_source_changed)
        self.device_combo.currentIndexChanged.connect(self._on_device_changed)
        self.refresh_devices_button.clicked.connect(self._refresh_output_devices)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        self.intensity_slider.valueChanged.connect(self._on_intensity_changed)

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
            QPushButton#iconButton {{
                min-width: 36px;
                max-width: 36px;
                padding: 8px 0;
                font-size: 18px;
                font-weight: 600;
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
            if self.engine.get_source_mode() != AudioSourceMode.FILE:
                self.engine.set_source_mode(AudioSourceMode.FILE)
                self._sync_source_combo()
            metadata = self.engine.load_file(path)
        except RuntimeError as exc:
            self._show_error("Open File Failed", str(exc))
            return

        self.statusBar().showMessage(f"Loaded {metadata.title}", 5000)
        self.source_label.setToolTip(str(metadata.path))
        self._refresh_from_engine()

    def _refresh_from_engine(self) -> None:
        snapshot = self.engine.get_snapshot()
        analysis = self.engine.get_analysis()
        self.canvas.set_frame(analysis, snapshot)

        if snapshot.source_mode == AudioSourceMode.FILE:
            self.source_caption.setText("Track")
            self.detail_caption.setText("Position")
            if snapshot.metadata is None:
                self.source_label.setText("No file loaded")
                self.source_label.setToolTip("")
            else:
                self.source_label.setText(snapshot.metadata.title)
                self.source_label.setToolTip(str(snapshot.metadata.path))
        else:
            self.source_caption.setText("Source")
            self.detail_caption.setText("Device")
            self.source_label.setText(snapshot.source_name)
            self.source_label.setToolTip(snapshot.detail_text)

        self.state_label.setText(snapshot.status_text)
        self.detail_label.setText(snapshot.detail_text)
        self.play_pause_button.setText(snapshot.primary_action_label)
        self.play_pause_button.setEnabled(snapshot.primary_action_enabled)
        self.open_button.setEnabled(snapshot.open_file_enabled)
        self.stop_button.setEnabled(snapshot.stop_enabled)
        self.volume_slider.setEnabled(snapshot.volume_enabled)
        self._sync_output_controls(snapshot.source_mode)
        self._sync_source_combo()
        if snapshot.source_mode == AudioSourceMode.SYSTEM:
            self._sync_device_combo()

        if snapshot.error_message and snapshot.error_message != self._last_error_message:
            self.statusBar().showMessage(snapshot.error_message, 6000)
        self._last_error_message = snapshot.error_message

    def _on_source_changed(self, index: int) -> None:
        mode = self._coerce_source_mode(self.source_combo.itemData(index))
        if mode is None:
            return

        try:
            self.engine.set_source_mode(mode)
        except RuntimeError as exc:
            self._show_error("Source Switch Failed", str(exc))
            self._sync_source_combo()
            return

        if mode == AudioSourceMode.SYSTEM:
            try:
                self._refresh_output_devices(show_message=False)
                self.engine.play()
            except RuntimeError as exc:
                self._show_error("System Audio Capture Failed", str(exc))
        self._refresh_from_engine()

    def _on_device_changed(self, index: int) -> None:
        if self.engine.get_source_mode() != AudioSourceMode.SYSTEM:
            return

        device_id = self.device_combo.itemData(index)
        if not isinstance(device_id, str) or not device_id:
            return

        try:
            self.engine.select_output_device(device_id)
            snapshot = self.engine.get_snapshot()
            if not snapshot.stream_active:
                self.engine.play()
        except RuntimeError as exc:
            self._show_error("Device Switch Failed", str(exc))
            self._refresh_output_devices(show_message=False)
            return

        self.statusBar().showMessage("System audio device updated", 2500)
        self._refresh_from_engine()

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

    def _on_intensity_changed(self, value: int) -> None:
        intensity = value / 100.0
        self.canvas.set_visualizer_intensity(intensity)
        self.statusBar().showMessage(f"Visualizer intensity {value}%", 1500)

    def _show_error(self, title: str, message: str) -> None:
        QMessageBox.critical(self, title, message)
        self.statusBar().showMessage(message, 7000)

    def _refresh_output_devices(self, show_message: bool = True) -> None:
        devices = self.engine.refresh_output_devices()
        self._sync_device_combo()
        if show_message:
            if devices:
                self.statusBar().showMessage("Output device list refreshed", 2500)
            else:
                availability = self.engine.system_audio_availability_error()
                if availability:
                    self.statusBar().showMessage(availability, 4000)

    def _sync_source_combo(self) -> None:
        mode = self.engine.get_source_mode()
        blocker = QSignalBlocker(self.source_combo)
        for index in range(self.source_combo.count()):
            combo_mode = self._coerce_source_mode(self.source_combo.itemData(index))
            if combo_mode == mode:
                self.source_combo.setCurrentIndex(index)
                break
        del blocker

    def _sync_device_combo(self) -> None:
        devices = self.engine.list_output_devices()
        selected_device_id = self.engine.selected_output_device_id()
        blocker = QSignalBlocker(self.device_combo)
        self.device_combo.clear()
        selected_index = -1
        for index, device in enumerate(devices):
            label = f"{device.name} (Default)" if device.is_default else device.name
            self.device_combo.addItem(label, device.identifier)
            if device.identifier == selected_device_id:
                selected_index = index
        if selected_index >= 0:
            self.device_combo.setCurrentIndex(selected_index)
        del blocker

    def _sync_output_controls(self, source_mode: AudioSourceMode) -> None:
        is_system = source_mode == AudioSourceMode.SYSTEM
        show_file_controls = not is_system
        self.open_button.setVisible(show_file_controls)
        self.play_pause_button.setVisible(show_file_controls)
        self.stop_button.setVisible(show_file_controls)
        self.volume_caption.setVisible(show_file_controls)
        self.volume_slider.setVisible(show_file_controls)
        self.device_label.setVisible(is_system)
        self.device_combo.setVisible(is_system)
        self.refresh_devices_button.setVisible(is_system)

    @staticmethod
    def _coerce_source_mode(value: object) -> AudioSourceMode | None:
        if isinstance(value, AudioSourceMode):
            return value
        if isinstance(value, str):
            try:
                return AudioSourceMode(value)
            except ValueError:
                return None
        return None

    @staticmethod
    def _extract_first_local_file(urls: list[QUrl]) -> str | None:
        for url in urls:
            if url.isLocalFile():
                local_path = url.toLocalFile()
                if local_path:
                    return local_path
        return None
