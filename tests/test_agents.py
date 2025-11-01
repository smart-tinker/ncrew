import sys

import pytest

from ncrew.agents import AgentInvocationError, AgentProfile, invoke_agent


def test_build_command_with_placeholder():
    profile = AgentProfile(id="echo", name="Echo", command="echo {message}")

    command = profile.build_command("hello world")

    assert command == ["echo", "hello world"]


def test_build_command_appends_message():
    profile = AgentProfile(id="echo", name="Echo", command="echo")

    command = profile.build_command("hello")

    assert command == ["echo", "hello"]


def test_invoke_agent_returns_stdout(tmp_path):
    script = tmp_path / "agent.py"
    script.write_text(
        "import sys\nmessage = sys.argv[1]\nprint(f'Reply:{message}')\n",
        encoding="utf-8",
    )

    profile = AgentProfile(
        id="script",
        name="Script Agent",
        command=f"{sys.executable} {script} {{message}}",
    )

    output = invoke_agent(profile, "test message")

    assert output == "Reply:test message"


def test_invoke_agent_raises_on_failure(tmp_path):
    script = tmp_path / "agent_fail.py"
    script.write_text("import sys\nsys.exit(2)\n", encoding="utf-8")

    profile = AgentProfile(
        id="script",
        name="Script Agent",
        command=f"{sys.executable} {script}",
    )

    with pytest.raises(AgentInvocationError) as excinfo:
        invoke_agent(profile, "ignored")

    assert "exited with code" in str(excinfo.value)
