"""
SDK-based connector for OpenAI models.
"""

import os
from typing import Any, Dict

from openai import AsyncOpenAI
from config import Config
from .base_sdk_connector import BaseSDKConnector


class OpenAISDKConnector(BaseSDKConnector):
    """
    Connector for OpenAI models using the official Python SDK.
    """

    DEFAULT_MODEL = "gpt-4-turbo"

    def __init__(self):
        super().__init__()
        # The OpenAI SDK automatically picks up the API key from the
        # OPENAI_API_KEY environment variable.
        self.client = AsyncOpenAI()
        self.model = getattr(Config, "OPENAI_MODEL", self.DEFAULT_MODEL)
        self.timeout = float(getattr(Config, "AGENT_TIMEOUT", 120))

    def get_info(self) -> Dict[str, Any]:
        return {
            "name": "OpenAI SDK Connector",
            "type": "openai_sdk",
            "model": self.model,
            "status": "active",
        }

    async def _get_api_response(self) -> str:
        """
        Makes a request to the OpenAI API and returns the text of the response.
        """
        try:
            self.logger.debug(
                "Sending request to OpenAI API with %d messages.",
                len(self._conversation_history),
            )
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=list(self._conversation_history),
                temperature=0.7,
                stream=False,  # For simplicity, not streaming for now
                timeout=self.timeout,
            )
            self.logger.debug("Received response from OpenAI API.")
            content = response.choices[0].message.content
            return content.strip() if content else ""
        except Exception as e:
            self.logger.error("Error calling OpenAI API: %s", e)
            return f"Error: Could not get a response from OpenAI. Details: {e}"
