"""
Tests for the OpenAISDKConnector.
"""

import pytest
import os
from unittest.mock import AsyncMock, MagicMock, patch

from connectors.openai_sdk_connector import OpenAISDKConnector


@pytest.fixture
def mock_env_vars(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test_api_key")


@pytest.mark.asyncio
async def test_openai_sdk_connector_e2e(mock_env_vars):
    """
    End-to-end test for the OpenAISDKConnector using a mocked API client.
    """
    connector = OpenAISDKConnector()

    # Mock the AsyncOpenAI client's chat.completions.create method
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message = MagicMock()
    mock_response.choices[0].message.content = "Mocked OpenAI response."

    with patch.object(connector.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
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

        assert response == "Mocked OpenAI response."
        assert connector.get_session_history() == [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
            {"role": "assistant", "content": "Mocked OpenAI response."},
        ]

        # Verify the API was called correctly
        mock_create.assert_called_once()
        call_args = mock_create.call_args.kwargs
        assert call_args["model"] == connector.model
        assert call_args["messages"] == [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        # 3. Follow-up prompt
        follow_up_prompt = "How are you?"
        mock_response.choices[0].message.content = "I am a mock, thank you."
        response = await connector.follow_up(follow_up_prompt)

        assert response == "I am a mock, thank you."
        assert mock_create.call_count == 2

        # 4. Shutdown
        await connector.shutdown()
        assert connector.get_session_history() == []
        assert connector.system_prompt == ""
