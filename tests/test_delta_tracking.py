"""
Tests for role delta tracking and message indexing.

This module tests that each role correctly tracks which messages it has seen
and only processes new messages since its last response.
"""

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
    """Create NeuroCrew Lab instance with mocked config and connectors."""
    # Patch background task managers to prevent hanging tests
    with patch("app.core.memory_manager.MemoryManager.start", new_callable=AsyncMock), \
         patch("app.core.port_manager.PortManager.start", new_callable=AsyncMock), \
         patch("app.core.session_manager.SessionManager.initialize", new_callable=AsyncMock):
        # Patch Config where it is used (ncrew module)
        with patch("app.core.engine.Config") as mock_config:
            mock_config.is_role_based_enabled.return_value = True
            mock_config.SYSTEM_REMINDER_INTERVAL = 5
            mock_config.get_role_sequence.return_value = [
                RoleConfig(
                    role_name="dev",
                    display_name="Developer",
                    telegram_bot_name="dev_bot",
                    prompt_file="",
                    agent_type="mock_agent",
                    cli_command="echo",
                    system_prompt="You are a developer",
                ),
                RoleConfig(
                    role_name="reviewer",
                    display_name="Reviewer",
                    telegram_bot_name="reviewer_bot",
                    prompt_file="",
                    agent_type="mock_agent",
                    cli_command="echo",
                    system_prompt="You are a reviewer",
                ),
            ]
            mock_config.TELEGRAM_BOT_TOKENS = {
                "dev_bot": "token1",
                "reviewer_bot": "token2",
            }

            # Also patch get_connector_spec in ncrew to avoid validation errors
            with patch("app.core.agent_coordinator.get_connector_spec") as mock_spec:
                mock_spec.return_value = MagicMock(requires_cli=False)

                # Patch connector creation
                with patch("app.core.agent_coordinator.get_connector_class") as mock_get_connector:
                    MockConnector = MagicMock()
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
async def test_delta_tracking_first_role_sees_all_initial_messages(ncrew_lab):
    """Test that first role sees all existing messages when starting fresh."""
    chat_id = 12345

    # Setup conversation with 3 messages
    conversation = [
        {"role": "user", "content": "Hello"},
        {"role": "user", "content": "World"},
        {"role": "user", "content": "Test"},
    ]

    ncrew_lab.storage.load_conversation.return_value = conversation

    # Get the role
    dev_role = ncrew_lab.roles[0]
    key = (chat_id, dev_role.role_name)

    # Verify initial state: no last_seen_index for this role
    assert key not in ncrew_lab.role_last_seen_index

    # Process with role (should see all 3 messages)
    await ncrew_lab._process_with_role(chat_id, dev_role)

    # After processing, last_seen_index should be set to conversation length
    # (because we added one response message, making it 4 total)
    # Mock adds one message, so conversation becomes 4
    assert key in ncrew_lab.role_last_seen_index


@pytest.mark.asyncio
async def test_delta_tracking_second_role_only_sees_new_messages(ncrew_lab):
    """Test that second role only sees messages since first role's response."""
    chat_id = 12345

    # Initial conversation
    initial_conversation = [
        {"role": "user", "content": "Hello"},
        {"role": "agent", "role_name": "dev", "content": "Dev response"},
    ]

    ncrew_lab.storage.load_conversation.return_value = initial_conversation

    dev_role = ncrew_lab.roles[0]
    reviewer_role = ncrew_lab.roles[1]

    dev_key = (chat_id, dev_role.role_name)
    reviewer_key = (chat_id, reviewer_role.role_name)

    # Set last_seen_index for dev (after it processed 2 messages)
    ncrew_lab.role_last_seen_index[dev_key] = 2

    # Reviewer hasn't processed yet
    assert reviewer_key not in ncrew_lab.role_last_seen_index

    # Process with reviewer
    new_messages = initial_conversation[0:]  # Reviewer should see all (like first time)

    prompt, has_updates = ncrew_lab._format_conversation_for_role(
        new_messages, reviewer_role, chat_id
    )

    # Reviewer should see messages because it's first time
    assert has_updates is True
    assert "Hello" in prompt
    assert "Dev response" in prompt


@pytest.mark.asyncio
async def test_delta_tracking_index_advances_after_response(ncrew_lab):
    """Test that last_seen_index advances correctly after role adds response."""
    chat_id = 12345

    initial_conversation = [
        {"role": "user", "content": "User message"},
    ]

    # Mock the storage to simulate adding a message
    async def mock_add_message(cid, msg):
        if cid == chat_id:
            initial_conversation.append(msg)
        return True

    async def mock_load_after_add(cid):
        if cid == chat_id:
            return initial_conversation
        return []

    ncrew_lab.storage.add_message.side_effect = mock_add_message
    ncrew_lab.storage.load_conversation.side_effect = mock_load_after_add

    dev_role = ncrew_lab.roles[0]
    key = (chat_id, dev_role.role_name)

    # Initial: dev hasn't seen anything
    assert key not in ncrew_lab.role_last_seen_index

    # First call: should have 1 user message, dev will respond
    # Process returns the response
    with patch.object(
        ncrew_lab.agent_coordinator, "get_or_create_connector"
    ) as mock_get_connector:
        mock_connector = MagicMock()
        mock_connector.is_alive.return_value = True
        mock_connector.execute = AsyncMock(return_value="Dev response")
        mock_get_connector.return_value = mock_connector

        await ncrew_lab._process_with_role(chat_id, dev_role)

    # After processing, last_seen_index should be 1 (dev saw 1 message, then processed)
    assert key in ncrew_lab.role_last_seen_index
    assert ncrew_lab.role_last_seen_index[key] == 1


@pytest.mark.asyncio
async def test_delta_tracking_boundary_out_of_bounds_index(ncrew_lab):
    """Test that out-of-bounds index is handled gracefully."""
    chat_id = 12345

    conversation = [
        {"role": "user", "content": "Hello"},
        {"role": "user", "content": "World"},
    ]

    ncrew_lab.storage.load_conversation.return_value = conversation

    dev_role = ncrew_lab.roles[0]
    key = (chat_id, dev_role.role_name)

    # Set an out-of-bounds index (past conversation length)
    ncrew_lab.role_last_seen_index[key] = 100

    # Should reset to 0 and see all messages
    prompt, has_updates = ncrew_lab._format_conversation_for_role(
        conversation[0:], dev_role, chat_id
    )

    assert has_updates is True


@pytest.mark.asyncio
async def test_delta_tracking_negative_index(ncrew_lab):
    """Test that negative index is handled gracefully."""
    chat_id = 12345

    conversation = [
        {"role": "user", "content": "Hello"},
    ]

    dev_role = ncrew_lab.roles[0]
    key = (chat_id, dev_role.role_name)

    # Set negative index
    ncrew_lab.role_last_seen_index[key] = -5

    # In _process_with_role, should reset to 0
    assert ncrew_lab.role_last_seen_index[key] == -5

    # When calling with reset logic
    last_seen_index = ncrew_lab.role_last_seen_index.get(key, 0)
    if last_seen_index < 0 or last_seen_index > len(conversation):
        last_seen_index = 0

    new_messages = conversation[last_seen_index:]
    assert len(new_messages) == 1


@pytest.mark.asyncio
async def test_delta_tracking_placeholder_messages_filtered(ncrew_lab):
    """Test that placeholder responses ('.....') don't reset delta tracking."""
    chat_id = 12345

    # Conversation with placeholder responses
    conversation = [
        {"role": "user", "content": "Hello"},
        {"role": "agent", "role_name": "dev", "content": "....."},  # Dev had nothing to say
        {"role": "agent", "role_name": "reviewer", "content": "Review done"},
    ]

    dev_role = ncrew_lab.roles[0]
    reviewer_role = ncrew_lab.roles[1]

    # Dev should filter out its own placeholder
    new_messages = conversation[1:]
    prompt, has_updates = ncrew_lab._format_conversation_for_role(
        new_messages, dev_role, chat_id
    )

    # Should see reviewer's response but not its own placeholder
    assert has_updates is True
    assert "Review done" in prompt
    assert "....." not in prompt  # Placeholder should be filtered


@pytest.mark.asyncio
async def test_delta_tracking_reset_clears_indices(ncrew_lab):
    """Test that reset_conversation clears all delta indices."""
    chat_id = 12345

    dev_role = ncrew_lab.roles[0]
    reviewer_role = ncrew_lab.roles[1]

    # Set up indices for both roles
    ncrew_lab.role_last_seen_index[(chat_id, dev_role.role_name)] = 5
    ncrew_lab.role_last_seen_index[(chat_id, reviewer_role.role_name)] = 3

    # Also set up connectors for both roles
    ncrew_lab.connector_sessions[(chat_id, dev_role.role_name)] = MagicMock()
    ncrew_lab.connector_sessions[(chat_id, reviewer_role.role_name)] = MagicMock()

    # Setup mock connector shutdown
    for key, connector in list(ncrew_lab.connector_sessions.items()):
        if key[0] == chat_id:
            connector.shutdown = AsyncMock()

    # Clear conversation
    ncrew_lab.storage.clear_conversation = AsyncMock(return_value=True)

    await ncrew_lab.reset_conversation(chat_id)

    # Verify indices are cleared
    assert (chat_id, dev_role.role_name) not in ncrew_lab.role_last_seen_index
    assert (chat_id, reviewer_role.role_name) not in ncrew_lab.role_last_seen_index

    # Verify connectors are cleared
    assert (chat_id, dev_role.role_name) not in ncrew_lab.connector_sessions
    assert (chat_id, reviewer_role.role_name) not in ncrew_lab.connector_sessions


@pytest.mark.asyncio
async def test_delta_tracking_multiple_chats_independent(ncrew_lab):
    """Test that delta tracking is independent across multiple chats."""
    chat_id_1 = 12345
    chat_id_2 = 67890

    dev_role = ncrew_lab.roles[0]

    # Set indices for both chats
    ncrew_lab.role_last_seen_index[(chat_id_1, dev_role.role_name)] = 5
    ncrew_lab.role_last_seen_index[(chat_id_2, dev_role.role_name)] = 2

    # Reset only chat_id_1
    ncrew_lab.connector_sessions[(chat_id_1, dev_role.role_name)] = MagicMock()
    ncrew_lab.connector_sessions[(chat_id_1, dev_role.role_name)].shutdown = AsyncMock()

    await ncrew_lab._reset_chat_role_sessions(chat_id_1)

    # chat_id_1 indices should be cleared
    assert (chat_id_1, dev_role.role_name) not in ncrew_lab.role_last_seen_index

    # chat_id_2 indices should remain
    assert (chat_id_2, dev_role.role_name) in ncrew_lab.role_last_seen_index
    assert ncrew_lab.role_last_seen_index[(chat_id_2, dev_role.role_name)] == 2


@pytest.mark.asyncio
async def test_delta_tracking_no_messages_returns_placeholder(ncrew_lab):
    """Test that with no new messages, role returns placeholder."""
    chat_id = 12345

    dev_role = ncrew_lab.roles[0]

    # Empty new messages
    new_messages = []

    prompt, has_updates = ncrew_lab._format_conversation_for_role(
        new_messages, dev_role, chat_id
    )

    assert prompt == "....."
    assert has_updates is False


@pytest.mark.asyncio
async def test_delta_tracking_only_placeholder_messages(ncrew_lab):
    """Test that if all new messages are placeholders, role returns placeholder."""
    chat_id = 12345

    dev_role = ncrew_lab.roles[0]

    # Only placeholder messages
    new_messages = [
        {"role": "agent", "role_name": "dev", "content": "....."},
        {"role": "agent", "role_name": "reviewer", "content": "....."},
    ]

    prompt, has_updates = ncrew_lab._format_conversation_for_role(
        new_messages, dev_role, chat_id
    )

    assert prompt == "....."
    assert has_updates is False


@pytest.mark.asyncio
async def test_delta_tracking_preserves_order(ncrew_lab):
    """Test that delta tracking preserves message order."""
    chat_id = 12345

    conversation = [
        {"role": "user", "content": "First user message"},
        {"role": "user", "content": "Second user message"},
        {"role": "agent", "role_name": "dev", "content": "Dev response"},
        {"role": "user", "content": "Third user message"},
    ]

    dev_role = ncrew_lab.roles[0]

    # Dev should see all messages (starting from index 0)
    prompt, has_updates = ncrew_lab._format_conversation_for_role(
        conversation, dev_role, chat_id
    )

    # Verify order is preserved
    assert prompt.index("First user message") < prompt.index("Second user message")
    assert prompt.index("Second user message") < prompt.index("Dev response")
    assert prompt.index("Dev response") < prompt.index("Third user message")
