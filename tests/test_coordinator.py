import json
import sys

import pytest

from ncrew.coordinator import AgentUnavailableError, SessionCoordinator


def write_settings(tmp_path, agents, ui=None):
    payload = {
        "agents": agents,
        "ui": ui or {"history_limit": 10, "show_timestamps": False},
    }
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def make_agent_script(tmp_path):
    script = tmp_path / "agent.py"
    script.write_text(
        """
import sys
agent = sys.argv[1]
message = sys.argv[2]
print(f"{agent}:{message}")
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return script


def test_broadcast_prompt_returns_responses_in_order(tmp_path):
    script = make_agent_script(tmp_path)
    settings_path = write_settings(
        tmp_path,
        [
            {
                "id": "codex",
                "name": "Codex",
                "command": f"{sys.executable} {script} codex {{message}}",
            },
            {
                "id": "qwen",
                "name": "Qwen",
                "command": f"{sys.executable} {script} qwen {{message}}",
            },
        ],
    )

    coordinator = SessionCoordinator(settings_path)

    user_msg = coordinator.record_user_message("hello world")
    assert user_msg.role == "user"
    assert coordinator.get_history()[-1] is user_msg

    responses = list(coordinator.broadcast_prompt("hello world"))

    assert [message.agent_id for message in responses] == ["codex", "qwen"]
    assert [message.content for message in responses] == [
        "codex:hello world",
        "qwen:hello world",
    ]


def test_reload_settings_updates_agent_list(tmp_path):
    script = make_agent_script(tmp_path)
    settings_path = write_settings(
        tmp_path,
        [
            {
                "id": "codex",
                "name": "Codex",
                "command": f"{sys.executable} {script} codex {{message}}",
            }
        ],
    )

    coordinator = SessionCoordinator(settings_path)
    assert coordinator.agent_order == ["codex"]

    settings_path.write_text(
        json.dumps(
            {
                "agents": [
                    {
                        "id": "qwen",
                        "name": "Qwen",
                        "command": f"{sys.executable} {script} qwen {{message}}",
                    }
                ],
                "ui": {"history_limit": 5, "show_timestamps": True},
            }
        ),
        encoding="utf-8",
    )

    assert coordinator.reload_settings() is True
    assert coordinator.agent_order == ["qwen"]
    assert coordinator.ui_settings.show_timestamps is True
    assert coordinator.ui_settings.history_limit == 5


def test_record_user_message_without_agents_raises(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("{}", encoding="utf-8")

    coordinator = SessionCoordinator(settings_path)
    assert coordinator.agent_order == []
    assert "Settings error" in coordinator.status_message

    with pytest.raises(AgentUnavailableError):
        coordinator.record_user_message("hello")
