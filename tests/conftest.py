"""Shared pytest fixtures for Qt-based tests."""

from __future__ import annotations

import os

import pytest
from PySide6.QtWidgets import QApplication


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def qt_app() -> QApplication:
    """Provide a QApplication instance for UI tests."""

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app
