"""Package entrypoint for the desktop music visualizer."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from app.config import DEFAULT_CONFIG
from app.ui import MainWindow


def main() -> int:
    """Launch the Qt application."""

    app = QApplication(sys.argv)
    app.setApplicationName(DEFAULT_CONFIG.app_name)
    app.setApplicationDisplayName(DEFAULT_CONFIG.window_title)

    window = MainWindow(DEFAULT_CONFIG)
    window.show()
    return app.exec()

