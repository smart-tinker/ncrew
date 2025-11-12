"""
SDK-based connector for Anthropic models (Claude).
"""

import os
from typing import Any, Dict

from anthropic import AsyncAnthropic
from config import Config
from .base_sdk_connector import BaseSDKConnector


class AnthropicSDKConnector(BaseSDKConnector):
    """
    Connector for Anthropic models using the official Python SDK.
    """

    DEFAULT_MODEL = "claude-3-opus-20240229"

    def __init__(self):
        super().__init__()
        # The Anthropic SDK automatically picks up the API key from the
        # ANTHROPIC_API_KEY environment variable.
        self.client = AsyncAnthropic()
        self.model = getattr(Config, "ANTHROPIC_MODEL", self.DEFAULT_MODEL)
        self.timeout = float(getattr(Config, "AGENT_TIMEOUT", 120))

    def get_info(self) -> Dict[str, Any]:
        return {
            "name": "Anthropic SDK Connector",
            "type": "anthropic_sdk",
            "model": self.model,
            "status": "active",
        }

    async def _get_api_response(self) -> str:
        """
        Makes a request to the Anthropic API and returns the text of the response.
        """
        try:
            self.logger.debug(
                "Sending request to Anthropic API with %d messages.",
                len(self._conversation_history),
            )

            # Anthropic API requires the system prompt to be a top-level parameter,
            # not part of the messages list.
            system_prompt = self.system_prompt
            messages = [m for m in self._conversation_history if m["role"] != "system"]

            response = await self.client.messages.create(
                model=self.model,
                system=system_prompt,
                messages=messages,
                max_tokens=4096,  # Recommended default
                temperature=0.7,
                timeout=self.timeout,
            )
            self.logger.debug("Received response from Anthropic API.")
            content = response.content[0].text
            return content.strip() if content else ""
        except Exception as e:
            self.logger.error("Error calling Anthropic API: %s", e)
            return f"Error: Could not get a response from Anthropic. Details: {e}"
