import json
from pathlib import Path

import pytest

from ncrew.settings import Settings, SettingsError, UISettings, load_settings


def write_settings(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_load_settings_success(tmp_path):
    path = write_settings(
        tmp_path,
        {
            "agents": [
                {"id": "codex", "name": "Codex", "command": "echo {message}"},
                {"id": "qwen", "name": "Qwen", "command": "echo"},
            ],
            "ui": {"theme": "dark", "history_limit": 42, "show_timestamps": False},
        },
    )

    settings = load_settings(path)

    assert isinstance(settings, Settings)
    assert settings.agent_ids == ["codex", "qwen"]
    assert settings.ui == UISettings(theme="dark", history_limit=42, show_timestamps=False)
    assert [agent.name for agent in settings.agents] == ["Codex", "Qwen"]


def test_load_settings_rejects_invalid_agents(tmp_path):
    path = write_settings(
        tmp_path,
        {
            "agents": [
                {"id": "dup", "name": "Dup", "command": "echo"},
                {"id": "dup", "name": "Dup 2", "command": "echo"},
            ]
        },
    )

    with pytest.raises(SettingsError):
        load_settings(path)
