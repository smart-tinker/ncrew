"""
Tests for the AnthropicSDKConnector.
"""

import pytest
import os
from unittest.mock import AsyncMock, MagicMock, patch

from connectors.anthropic_sdk_connector import AnthropicSDKConnector


@pytest.fixture
def mock_env_vars(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test_api_key")


@pytest.mark.asyncio
async def test_anthropic_sdk_connector_e2e(mock_env_vars):
    """
    End-to-end test for the AnthropicSDKConnector using a mocked API client.
    """
    connector = AnthropicSDKConnector()

    # Mock the AsyncAnthropic client's messages.create method
    mock_response = MagicMock()
    mock_response.content = [MagicMock()]
    mock_response.content[0].text = "Mocked Anthropic response."

    with patch.object(connector.client.messages, 'create', new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_response

        # 1. Launch and set system prompt
        system_prompt = "You are a helpful assistant."
        await connector.launch(command="", system_prompt=system_prompt)

        assert connector.system_prompt == system_prompt
        assert connector.get_session_history() == [
            {"role": "system", "content": system_prompt}
        ]
        assert connector.is_alive() is True

        # 2. Execute a user prompt
        user_prompt = "Hello, world!"
        response = await connector.execute(user_prompt)

        assert response == "Mocked Anthropic response."
        assert connector.get_session_history() == [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
            {"role": "assistant", "content": "Mocked Anthropic response."},
        ]

        # Verify the API was called correctly
        mock_create.assert_called_once()
        call_args = mock_create.call_args[1]
        assert call_args["model"] == connector.model
        assert call_args["system"] == system_prompt
        assert call_args["messages"] == [
            {"role": "user", "content": user_prompt},
        ]

        # 3. Follow-up prompt
        follow_up_prompt = "How are you?"
        mock_response.content[0].text = "I am a mock, thank you."
        response = await connector.follow_up(follow_up_prompt)

        assert response == "I am a mock, thank you."
        assert mock_create.call_count == 2

        # 4. Shutdown
        await connector.shutdown()
        assert connector.get_session_history() == []
        assert connector.system_prompt == ""
