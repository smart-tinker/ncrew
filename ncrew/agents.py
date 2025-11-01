"""Agent invocation helpers for running external CLI commands."""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from typing import List


class AgentInvocationError(Exception):
    """Raised when invoking an agent fails."""


@dataclass(slots=True)
class AgentProfile:
    """Metadata required to run an external agent."""

    id: str
    name: str
    command: str

    def build_command(self, message: str) -> List[str]:
        """Build the subprocess command for *message*.

        If the command string contains ``{message}``, the placeholder is replaced with a
        shell-quoted message before splitting. Otherwise the message is appended as the
        final argument.
        """

        template = self.command
        if "{message}" in template:
            substituted = template.replace("{message}", shlex.quote(message))
            return shlex.split(substituted)
        return [*shlex.split(template), message]

def invoke_agent(profile: AgentProfile, prompt: str, *, timeout: float | None = 120.0) -> str:
    """Execute the agent command and return its stdout.

    Raises :class:`AgentInvocationError` if the subprocess fails.
    """

    try:
        completed = subprocess.run(
            profile.build_command(prompt),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise AgentInvocationError(
            f"Executable for agent '{profile.name}' was not found: {exc.filename}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise AgentInvocationError(
            f"Agent '{profile.name}' timed out after {timeout} seconds."
        ) from exc

    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        stdout = completed.stdout.strip()
        details = stderr or stdout or "unknown error"
        raise AgentInvocationError(
            f"Agent '{profile.name}' exited with code {completed.returncode}: {details}"
        )

    output = completed.stdout.strip()
    if not output:
        output = completed.stderr.strip()
    return output or "(no output)"


__all__ = ["AgentInvocationError", "AgentProfile", "invoke_agent"]
