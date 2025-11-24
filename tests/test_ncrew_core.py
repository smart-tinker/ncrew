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
    # Patch background task managers to prevent hanging tests
    with patch("app.core.memory_manager.MemoryManager.start", new_callable=AsyncMock), \
         patch("app.core.port_manager.PortManager.start", new_callable=AsyncMock), \
         patch("app.core.session_manager.SessionManager.initialize", new_callable=AsyncMock):
        # Patch Config where it is used (ncrew module and agent coordinator)
        with patch("app.core.engine.Config") as mock_engine_config, \
             patch("app.core.agent_coordinator.Config") as mock_ac_config:
            roles = [
                RoleConfig(
                    role_name="software_developer",
                    display_name="Software Developer",
                    telegram_bot_name="software_developer_bot",
                    prompt_file="software_developer.md",
                    agent_type="mock_agent",
                    cli_command="echo",
                    telegram_bot_token="test_token_1",
                ),
                RoleConfig(
                    role_name="code_review",
                    display_name="Code Review",
                    telegram_bot_name="code_review_bot",
                    prompt_file="code_review.md",
                    agent_type="mock_agent",
                    cli_command="echo",
                    telegram_bot_token="test_token_2",
                ),
            ]

            for cfg in (mock_engine_config, mock_ac_config):
                cfg.is_role_based_enabled.return_value = True
                cfg.get_role_sequence.return_value = roles
                cfg.TELEGRAM_BOT_TOKENS = {
                    "software_developer_bot": "test_token_1",
                    "code_review_bot": "test_token_2",
                }
                cfg.ALLOW_DUMMY_TOKENS = True

            # Also patch get_connector_spec in ncrew to avoid validation errors
            with patch("app.core.agent_coordinator.get_connector_spec") as mock_spec:
                mock_spec.return_value = MagicMock(requires_cli=False)

                # Patch connector creation
                with patch("app.core.agent_coordinator.get_connector_class") as mock_get_connector:
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
    # Note: _process_with_role is now in DialogueOrchestrator, not NeuroCrewLab
    with patch.object(
        ncrew_lab.dialogue_orchestrator,
        "_process_with_role",
        new_callable=AsyncMock,
    ) as mock_process:
        mock_process.side_effect = [
            "Software Developer response 1",  # Cycle 1, software_developer
            "Code Review response 1",  # Cycle 1, code_review
            ".....",  # Cycle 2, software_developer
            ".....",  # Cycle 2, code_review (all agents finished)
        ]
        # Also need to mock get_or_create_connector to avoid blocking async calls
        with patch.object(
            ncrew_lab.agent_coordinator,
            "get_or_create_connector"
        ) as mock_get_connector:
            mock_connector = MagicMock()
            mock_connector.is_alive.return_value = True
            mock_get_connector.return_value = mock_connector

        results = []
        async for role, response in ncrew_lab.handle_message(chat_id, user_text):
            if role:
                results.append((role.role_name, response))
            else:
                # System message
                results.append(("system", response))

        # Verify results
        # We expect 2 messages (Software Developer 1, Code Review 1).
        # The system completion message is handled by the caller (telegram_bot), not yielded by handle_message.
        assert len(results) == 2
        assert results[0][0] == "software_developer"
        assert results[0][1] == "Software Developer response 1"
        assert results[1][0] == "code_review"
        assert results[1][1] == "Code Review response 1"

        assert mock_process.call_count == 4


@pytest.mark.asyncio
async def test_single_agent_cycle(ncrew_lab):
    """Test cycle with error handling."""
    chat_id = 12345

    with patch.object(
        ncrew_lab.dialogue_orchestrator,
        "_process_with_role",
        new_callable=AsyncMock,
    ) as mock_process:
        mock_process.side_effect = [
            "Software Developer Response 1",
            "❌ Error: Something failed",  # Error should be yielded but continue
            ".....",
            ".....",
            ".....",
            ".....",
        ]
        results = []
        async for role, response in ncrew_lab.handle_message(chat_id, "Hi"):
            if role:
                results.append(response)

        assert "Software Developer Response 1" in results
        assert "❌ Error: Something failed" in results
        assert len(results) == 2
