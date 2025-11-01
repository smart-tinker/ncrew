"""Loading and validation of ncrew configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


class SettingsError(Exception):
    """Raised when the settings file is missing or invalid."""


SETTINGS_DIR = Path.home() / ".ncrew"
SETTINGS_PATH = SETTINGS_DIR / "settings.json"


@dataclass(slots=True)
class AgentSettings:
    """Configuration for an external CLI agent."""

    id: str
    name: str
    command: str


@dataclass(slots=True)
class UISettings:
    """UI-related configuration flags."""

    theme: str = "default"
    history_limit: int = 200
    show_timestamps: bool = True


@dataclass(slots=True)
class Settings:
    """Full configuration model for the application."""

    agents: List[AgentSettings]
    ui: UISettings

    @property
    def agent_ids(self) -> List[str]:
        """Return the configured agent identifiers in order."""

        return [agent.id for agent in self.agents]


def _load_json(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SettingsError(
            f"Settings file not found at {path}. Create it using the template from the documentation."
        ) from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise SettingsError(f"Settings file contains invalid JSON: {exc.msg} (line {exc.lineno}).") from exc


def load_settings(path: Optional[Path] = None) -> Settings:
    """Load settings from *path* or the default location."""

    target = (path or SETTINGS_PATH).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    data = _load_json(target)

    agents_data = data.get("agents")
    if not isinstance(agents_data, list) or not agents_data:
        raise SettingsError("The 'agents' list must be provided and contain at least one agent entry.")

    agents: List[AgentSettings] = []
    seen_ids: set[str] = set()
    for entry in agents_data:
        if not isinstance(entry, dict):
            raise SettingsError("Agent entries must be JSON objects.")
        try:
            agent_id = str(entry["id"]).strip()
            name = str(entry["name"]).strip()
            command = str(entry["command"]).strip()
        except KeyError as exc:
            raise SettingsError(f"Missing required agent field: {exc.args[0]}") from exc
        if not agent_id:
            raise SettingsError("Agent 'id' must be a non-empty string.")
        if agent_id in seen_ids:
            raise SettingsError(f"Agent id '{agent_id}' is duplicated.")
        if not name:
            raise SettingsError("Agent 'name' must be a non-empty string.")
        if not command:
            raise SettingsError("Agent 'command' must be a non-empty string.")
        seen_ids.add(agent_id)
        agents.append(AgentSettings(id=agent_id, name=name, command=command))

    ui_data = data.get("ui", {})
    if not isinstance(ui_data, dict):
        raise SettingsError("The 'ui' field must be an object if provided.")

    theme = str(ui_data.get("theme", "default")).strip() or "default"
    history_limit_raw = ui_data.get("history_limit", 200)
    if not isinstance(history_limit_raw, int) or history_limit_raw <= 0:
        raise SettingsError("'ui.history_limit' must be a positive integer.")
    show_timestamps = ui_data.get("show_timestamps", True)
    if not isinstance(show_timestamps, bool):
        raise SettingsError("'ui.show_timestamps' must be a boolean value.")

    ui_settings = UISettings(
        theme=theme,
        history_limit=history_limit_raw,
        show_timestamps=show_timestamps,
    )

    return Settings(agents=agents, ui=ui_settings)


__all__ = [
    "AgentSettings",
    "Settings",
    "SettingsError",
    "UISettings",
    "load_settings",
    "SETTINGS_PATH",
]
