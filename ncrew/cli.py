"""Command-line interface for launching the ncrew application."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence


def build_parser() -> argparse.ArgumentParser:
    """Return an argument parser for the ncrew CLI."""

    parser = argparse.ArgumentParser(
        prog="ncrew",
        description="Запуск текстового интерфейса ncrew.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        metavar="PATH",
        help="Путь к альтернативному файлу настроек (по умолчанию ~/.ncrew/settings.json).",
    )
    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments from *argv*."""

    parser = build_parser()
    return parser.parse_args(argv)


def launch(settings_path: Path | None) -> None:
    """Lazy wrapper around :func:`ncrew.app.run` for testability."""

    from .app import run as app_run

    app_run(settings_path=settings_path)


def main(argv: Sequence[str] | None = None) -> None:
    """Parse arguments and launch the application."""

    args = parse_args(argv)
    launch(args.config)


__all__ = ["build_parser", "launch", "main", "parse_args"]

