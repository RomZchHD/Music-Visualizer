"""Small UI-adjacent tests that do not require showing a window."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl

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
