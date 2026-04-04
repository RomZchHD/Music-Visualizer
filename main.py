"""Compatibility wrapper for launching the application directly."""

from __future__ import annotations

from app.main import main


if __name__ == "__main__":
    raise SystemExit(main())
