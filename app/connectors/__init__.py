"""Connector utilities and registry for NeuroCrew Lab."""

from __future__ import annotations

from dataclasses import dataclass
import importlib
from typing import Dict, Optional, Type

from .base import BaseConnector


@dataclass(frozen=True)
class ConnectorSpec:
    """Metadata describing how to load a connector."""

    module: str
    class_name: str
    requires_cli: bool


CONNECTOR_SPECS: Dict[str, ConnectorSpec] = {
    "qwen_acp": ConnectorSpec(
        module="app.connectors.qwen_acp_connector",
        class_name="QwenACPConnector",
        requires_cli=True,
    ),
    "gemini_acp": ConnectorSpec(
        module="app.connectors.gemini_acp_connector",
        class_name="GeminiACPConnector",
        requires_cli=True,
    ),
    "opencode_acp": ConnectorSpec(
        module="app.connectors.opencode_acp_connector",
        class_name="OpenCodeACPConnector",
        requires_cli=True,
    ),
    "codex_cli": ConnectorSpec(
        module="app.connectors.codex_cli_connector",
        class_name="CodexCLIConnector",
        requires_cli=True,
    ),
    "claude_cli": ConnectorSpec(
        module="app.connectors.claude_cli_connector",
        class_name="ClaudeCLICodeConnector",
        requires_cli=True,
    ),
}


def get_connector_spec(agent_type: str) -> Optional[ConnectorSpec]:
    """Return connector metadata for provided agent type."""

    if not agent_type:
        return None
    return CONNECTOR_SPECS.get(agent_type.lower())


def get_connector_class(agent_type: str) -> Optional[Type[BaseConnector]]:
    """Dynamically import and return the connector class for the agent type."""

    spec = get_connector_spec(agent_type)
    if not spec:
        return None

    module = importlib.import_module(spec.module)
    return getattr(module, spec.class_name, None)


__all__ = [
    "BaseConnector",
    "ConnectorSpec",
    "CONNECTOR_SPECS",
    "get_connector_spec",
    "get_connector_class",
]
