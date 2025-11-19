import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from app.core.engine import NeuroCrewLab
from app.config import RoleConfig


@pytest.fixture
def mock_storage():
    storage = MagicMock()
    storage.add_message = AsyncMock(return_value=True)
    storage.load_conversation = AsyncMock(return_value=[])
    return storage


@pytest.fixture
def ncrew_lab(mock_storage):
    # Patch Config where it is used (ncrew module)
    with patch("app.core.engine.Config") as mock_config:
        mock_config.is_role_based_enabled.return_value = True
        mock_config.get_role_sequence.return_value = [
            RoleConfig(
                role_name="dev",
                display_name="Developer",
                telegram_bot_name="dev_bot",
                system_prompt_file="",
                agent_type="mock_agent",
                cli_command="echo",
            ),
            RoleConfig(
                role_name="reviewer",
                display_name="Reviewer",
                telegram_bot_name="reviewer_bot",
                system_prompt_file="",
                agent_type="mock_agent",
                cli_command="echo",
            ),
        ]
        mock_config.TELEGRAM_BOT_TOKENS = {
            "dev_bot": "token1",
            "reviewer_bot": "token2",
        }

        # Also patch get_connector_spec in ncrew to avoid validation errors
        with patch("app.core.engine.get_connector_spec") as mock_spec:
            mock_spec.return_value = MagicMock(requires_cli=False)

            # Patch connector creation
            with patch("app.core.engine.get_connector_class") as mock_get_connector:
                MockConnector = MagicMock()
                # Setup mock connector instance
                mock_instance = MagicMock()
                mock_instance.check_availability.return_value = True
                mock_instance.is_alive.return_value = True
                mock_instance.launch = AsyncMock()
                mock_instance.execute = AsyncMock(return_value="Mock response")
                mock_instance.shutdown = AsyncMock()

                MockConnector.return_value = mock_instance
                mock_get_connector.return_value = MockConnector

                lab = NeuroCrewLab(storage=mock_storage)
                yield lab


@pytest.mark.asyncio
async def test_autonomous_cycle_termination(ncrew_lab):
    """Test that the cycle terminates when agents return '.....'."""
    chat_id = 12345
    user_text = "Hello world"

    # Setup mock responses to simulate conversation then termination
    # Dev responds once, then dots. Reviewer responds once, then dots.
    # We need to control the connector.execute return values

    # Get the mock connector instance created during init (it's shared because we mocked the class return)
    # Wait, _create_connector_for_role creates NEW instances.
    # We need to mock _create_connector_for_role or the class it uses.

    # Let's mock _process_with_role to have finer control over the flow without dealing with connector internals
    with patch.object(
        ncrew_lab,
        "_process_with_role",
        side_effect=[
            "Dev response 1",  # Cycle 1, Role 1
            "Reviewer response 1",  # Cycle 1, Role 2
            ".....",  # Cycle 2, Role 1 (starts termination sequence)
            ".....",  # Cycle 2, Role 2 (completes termination sequence)
        ],
    ) as mock_process:
        results = []
        async for role, response in ncrew_lab.handle_message(chat_id, user_text):
            if role:
                results.append((role.role_name, response))
            else:
                # System message
                results.append(("system", response))

        # Verify results
        # We expect 2 messages (Dev 1, Reviewer 1).
        # The system completion message is handled by the caller (telegram_bot), not yielded by handle_message.
        assert len(results) == 2
        assert results[0][0] == "dev"
        assert results[0][1] == "Dev response 1"
        assert results[1][0] == "reviewer"
        assert results[1][1] == "Reviewer response 1"

        assert mock_process.call_count == 4


@pytest.mark.asyncio
async def test_single_agent_cycle(ncrew_lab):
    """Test cycle with error handling."""
    chat_id = 12345

    with patch.object(
        ncrew_lab,
        "_process_with_role",
        side_effect=[
            "Response 1",
            "❌ Error: Something failed",  # Error should be yielded but continue
            ".....",
            ".....",
        ],
    ):
        results = []
        async for role, response in ncrew_lab.handle_message(chat_id, "Hi"):
            if role:
                results.append(response)

        assert "Response 1" in results
        assert "❌ Error: Something failed" in results
        assert len(results) == 2
