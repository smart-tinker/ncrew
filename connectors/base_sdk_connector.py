"""
Base class for SDK-based connectors that interact directly with LLM APIs.

Unlike ACP connectors, SDK connectors do not manage a subprocess. Instead, they
are responsible for maintaining the conversation history and sending it with
each API request. This class provides a common structure for handling this
state management.
"""

from __future__ import annotations

from typing import Any, Dict, List

from .base import BaseConnector


class BaseSDKConnector(BaseConnector):
    """
    An abstract base class for connectors that use a direct SDK integration.
    """

    def __init__(self):
        super().__init__()
        self._conversation_history: List[Dict[str, Any]] = []
        self.system_prompt: str = ""

    async def launch(self, command: str, system_prompt: str):
        """
        Initializes the connector and sets the system prompt.

        For SDK connectors, this doesn't launch a process but prepares the
        conversation history.
        """
        self.system_prompt = system_prompt
        self._conversation_history = []
        if self.system_prompt:
            self._add_message("system", self.system_prompt)
        self.logger.info("%s initialized with system prompt.", self.__class__.__name__)

    async def execute(self, delta_prompt: str) -> str:
        """
        Adds the user's prompt to the history and gets the model's response.
        """
        self._add_message("user", delta_prompt)
        response_text = await self._get_api_response()
        if response_text:
            self._add_message("assistant", response_text)
        return response_text

    async def follow_up(self, delta_prompt: str) -> str:
        """
        For stateful SDK connectors, follow-up is the same as execute.
        """
        return await self.execute(delta_prompt)

    def get_session_history(self) -> List[Dict[str, Any]]:
        """
        Returns the entire conversation history.
        """
        return list(self._conversation_history)

    async def shutdown(self):
        """
        Resets the conversation history. No process to terminate.
        """
        self._conversation_history = []
        self.system_prompt = ""
        self.logger.info("%s session cleared.", self.__class__.__name__)
        # No actual process to shut down, so we call the base's shutdown
        # logic which is a no-op but good practice.
        await super().shutdown()

    def is_alive(self) -> bool:
        """
        SDK connectors are always "alive" as long as they are instantiated.
        """
        return True

    def check_availability(self) -> bool:
        """
        Checks if the connector is available. For SDK-based connectors, this
        is always True as there are no external dependencies to check.
        """
        return True

    def _add_message(self, role: str, content: str):
        """
        Adds a message to the conversation history in the format expected by most APIs.
        """
        self._conversation_history.append({"role": role, "content": content})

    async def _get_api_response(self) -> str:
        """
        This method must be implemented by subclasses to make the actual API call.
        """
        raise NotImplementedError("Subclasses must implement _get_api_response")
