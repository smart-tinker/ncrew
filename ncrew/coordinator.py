"""Session coordinator managing agents, history, and settings."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Deque, Iterable, List, Optional

from .agents import AgentInvocationError, AgentProfile, invoke_agent
from .settings import Settings, SettingsError, UISettings, load_settings, SETTINGS_PATH


@dataclass(slots=True)
class Message:
    """A chat message stored in history."""

    role: str
    agent_id: str | None
    content: str
    timestamp: datetime


class AgentUnavailableError(RuntimeError):
    """Raised when no active agent is available for interaction."""


class SessionCoordinator:
    """Coordinates message flow between the UI and CLI agents."""

    def __init__(self, settings_path: Path | None = None) -> None:
        self.settings_path = (settings_path or SETTINGS_PATH).expanduser()
        self.settings: Optional[Settings] = None
        self.agent_order: List[str] = []
        self.ui_settings: UISettings = UISettings()
        self._agents: dict[str, AgentProfile] = {}
        self.history: Deque[Message] = deque()
        self.status_message: str = ""

        self.reload_settings()

    # ------------------------------------------------------------------
    # Settings management
    # ------------------------------------------------------------------
    def reload_settings(self) -> bool:
        """Reload settings from disk, returning ``True`` on success."""

        try:
            settings = load_settings(self.settings_path)
        except SettingsError as exc:
            self.status_message = f"Settings error: {exc}"
            return False

        self.settings = settings
        self.ui_settings = settings.ui
        self._agents = {cfg.id: AgentProfile(cfg.id, cfg.name, cfg.command) for cfg in settings.agents}
        self.agent_order = list(settings.agent_ids)
        self._trim_history()

        if not self.agent_order:
            self.status_message = "No agents configured."
        else:
            self.status_message = f"Loaded {len(self.agent_order)} agent(s)."
        return True

    # ------------------------------------------------------------------
    # Agent helpers
    # ------------------------------------------------------------------
    @property
    def agents(self) -> Iterable[AgentProfile]:
        for agent_id in self.agent_order:
            profile = self._agents.get(agent_id)
            if profile is not None:
                yield profile

    def get_agent(self, agent_id: str) -> AgentProfile:
        try:
            return self._agents[agent_id]
        except KeyError as exc:
            raise AgentUnavailableError(f"Agent '{agent_id}' is not registered.") from exc

    def get_agent_name(self, agent_id: str | None) -> str:
        if agent_id is None:
            return ""
        try:
            return self._agents[agent_id].name
        except KeyError:
            return agent_id

    # ------------------------------------------------------------------
    # Messaging
    # ------------------------------------------------------------------
    def record_user_message(self, content: str) -> Message:
        """Record a user's message in history."""

        if not self.agent_order:
            raise AgentUnavailableError("No agents are configured.")
        message = Message(
            role="user",
            agent_id=None,
            content=content,
            timestamp=datetime.now(),
        )
        self._append_message(message)
        return message

    def invoke_agent(self, agent_id: str, prompt: str) -> Message:
        """Send *prompt* to a specific agent and record the response."""

        agent = self.get_agent(agent_id)
        try:
            response = invoke_agent(agent, prompt)
        except AgentInvocationError as exc:
            message = Message(
                role="error",
                agent_id=agent.id,
                content=str(exc),
                timestamp=datetime.now(),
            )
            self.status_message = str(exc)
            self._append_message(message)
            return message

        message = Message(
            role="agent",
            agent_id=agent.id,
            content=response,
            timestamp=datetime.now(),
        )
        self._append_message(message)
        self.status_message = f"Received response from {agent.name}."
        return message

    def broadcast_prompt(self, prompt: str) -> Iterable[Message]:
        """Send *prompt* to all configured agents in order."""

        if not self.agent_order:
            raise AgentUnavailableError("No agents are configured.")

        for agent_id in self.agent_order:
            yield self.invoke_agent(agent_id, prompt)

    # ------------------------------------------------------------------
    # History utilities
    # ------------------------------------------------------------------
    def get_history(self) -> List[Message]:
        return list(self.history)

    def clear_history(self) -> None:
        self.history.clear()

    def _append_message(self, message: Message) -> None:
        history_limit = max(1, self.ui_settings.history_limit)
        self.history.append(message)
        while len(self.history) > history_limit:
            self.history.popleft()

    def _trim_history(self) -> None:
        history_limit = max(1, self.ui_settings.history_limit)
        while len(self.history) > history_limit:
            self.history.popleft()


__all__ = [
    "AgentUnavailableError",
    "Message",
    "SessionCoordinator",
]
