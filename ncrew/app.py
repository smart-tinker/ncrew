"""High-level entrypoint for launching the TUI application."""

from __future__ import annotations

from pathlib import Path

from .coordinator import SessionCoordinator
from .tui import run_tui


def run(settings_path: Path | None = None) -> None:
    """Launch the ncrew Textual application."""

    coordinator = SessionCoordinator(settings_path)
    run_tui(coordinator)


__all__ = ["run"]
