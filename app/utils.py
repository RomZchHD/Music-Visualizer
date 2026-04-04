"""Small utility helpers used by the UI layer."""

from __future__ import annotations

from pathlib import Path


def clamp(value: float, minimum: float, maximum: float) -> float:
    """Clamp a numeric value to a closed interval."""

    return max(minimum, min(value, maximum))


def format_seconds(seconds: float) -> str:
    """Format seconds as ``MM:SS``."""

    safe_seconds = max(0, int(seconds))
    minutes, remainder = divmod(safe_seconds, 60)
    return f"{minutes:02d}:{remainder:02d}"


def display_title(path: str | Path) -> str:
    """Return a friendly display title for a media path."""

    return Path(path).stem

