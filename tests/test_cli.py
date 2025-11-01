"""Tests for the ncrew command-line interface."""

from __future__ import annotations

from pathlib import Path

import pytest

from ncrew import cli


@pytest.mark.parametrize("argv,expected", [([], None), (["--config", "/tmp/settings.json"], Path("/tmp/settings.json"))])
def test_main_passes_config_to_launch(monkeypatch, argv, expected):
    called = {}

    def fake_launch(settings_path):
        called["settings_path"] = settings_path

    monkeypatch.setattr(cli, "launch", fake_launch)

    cli.main(argv)

    assert called["settings_path"] == expected


def test_parse_args_rejects_unknown_flags():
    with pytest.raises(SystemExit):
        cli.parse_args(["--unknown"])
