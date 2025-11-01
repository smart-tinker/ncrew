"""ncrew package exposing the TUI application entry points."""

from __future__ import annotations

from typing import Any

__all__ = ["run"]


def run(*args: Any, **kwargs: Any) -> None:
    """Lazy wrapper around :func:`ncrew.app.run` to defer heavy imports."""

    from .app import run as _run

    _run(*args, **kwargs)
