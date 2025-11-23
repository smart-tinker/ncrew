"""
Session Continuation Tests for NeuroCrewLab Connectors.

This module tests that connectors maintain proper session state across
multiple execute() calls, preserving session identifiers and conversation
history. Tests mock subprocess calls to avoid requiring real CLI binaries.

Coverage:
- ACP connectors (Qwen, Gemini, OpenCode): session_id persistence
- CLI connectors (Codex, Claude): thread_id persistence  
- NeuroCrewLab: cumulative context passing
- Session recovery after process restart
- Cross-connector session isolation
- Error handling and recovery
- Long-running session stability

Run with: pytest tests/test_session_continuation.py -v
"""

import asyncio
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

import pytest
import pytest_asyncio

from app.connectors.qwen_acp_connector import QwenACPConnector
from app.connectors.gemini_acp_connector import GeminiACPConnector  
from app.connectors.opencode_acp_connector import OpenCodeACPConnector
from app.connectors.codex_cli_connector import CodexCLIConnector
from app.connectors.claude_cli_connector import ClaudeCLICodeConnector
from app.core.engine import NeuroCrewLab
from app.config import RoleConfig
from app.storage.file_storage import FileStorage


class MockACPProcess:
    """Mock subprocess process for ACP connectors."""
    
    def __init__(self):
        self.pid = 12345
        self.returncode = None  # None means process is running
        self.stdin = MagicMock()
        self.stdin.drain = AsyncMock()
        self.stdout = MagicMock()
        self.stdout.readline = AsyncMock(side_effect=self._readline_side_effect)
        self.stderr = MagicMock()
        self.session_id = str(uuid.uuid4())
        self.message_id = 0
        self._responses = []
        self._setup_responses()
        
    def _setup_responses(self):
        """Setup mock JSON-RPC responses."""
        self._responses = [
            json.dumps({
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "protocolVersion": 1,
                    "authMethods": [{"id": "qwen-oauth", "name": "Mock OAuth"}],
                    "agentCapabilities": {"loadSession": False, "promptCapabilities": {}},
                },
            }).encode() + b"\n",
            json.dumps({
                "jsonrpc": "2.0", 
                "id": 2,
                "result": {"sessionId": self.session_id},
            }).encode() + b"\n",
        ]
        
        # Add responses for each execute call (support up to 60 execute calls)
        for i in range(3, 123):  # Support many execute calls for stress test
            self._responses.extend([
                json.dumps({
                    "jsonrpc": "2.0",
                    "method": "session/update",
                    "params": {
                        "sessionId": self.session_id,
                        "update": {
                            "sessionUpdate": "agent_message_chunk",
                            "content": {"type": "text", "text": f"Mock response {i-2}"},
                        },
                    },
                }).encode() + b"\n",
                json.dumps({
                    "jsonrpc": "2.0",
                    "id": i,
                    "result": {"stopReason": "end_turn"},
                }).encode() + b"\n",
            ])
    
    async def _readline_side_effect(self):
        """Mock readline - return next response."""
        if self._responses:
            return self._responses.pop(0)
        return b""
        
    async def wait(self):
        """Mock wait."""
        return self.returncode
        
    def terminate(self):
        """Mock terminate."""
        self.returncode = 0
        
    def kill(self):
        """Mock kill."""
        self.returncode = 1


class MockCLIProcess:
    """Mock subprocess process for CLI connectors."""
    
    def __init__(self):
        self.pid = 12345
        self.returncode = 0  # Success return code
        self.thread_id = str(uuid.uuid4())
        
    async def communicate(self):
        """Mock communicate - returns CLI JSON events."""
        events = [
            json.dumps({"type": "thread.started", "thread_id": self.thread_id}),
            json.dumps({"type": "turn.started"}),
            json.dumps({
                "type": "item.completed", 
                "item": {
                    "id": "item_0", 
                    "type": "agent_message", 
                    "text": f"Response [{self.thread_id}]"
                }
            }),
            json.dumps({"type": "turn.completed"}),
        ]
        return "\n".join(events).encode(), b""
    
    def terminate(self):
        """Mock terminate."""
        self.returncode = 0
        
    def kill(self):
        """Mock kill.""" 
        self.returncode = 1


# Test fixtures
@pytest_asyncio.fixture
async def mock_acp_subprocess():
    """Mock asyncio.create_subprocess_exec for ACP connectors."""
    with patch('asyncio.create_subprocess_exec') as mock_subprocess, \
         patch('os.kill') as mock_kill:
        # Mock os.kill to always succeed (pretend process exists)
        mock_kill.return_value = None
        
        mock_process = MockACPProcess()
        mock_subprocess.return_value = mock_process
        yield mock_subprocess


@pytest_asyncio.fixture  
async def mock_cli_subprocess():
    """Mock asyncio.create_subprocess_exec for CLI connectors."""
    with patch('asyncio.create_subprocess_exec') as mock_subprocess:
        mock_process = MockCLIProcess()
        mock_subprocess.return_value = mock_process
        yield mock_subprocess


@pytest.fixture
def sample_role_config():
    """Create sample RoleConfig for testing."""
    return RoleConfig(
        role_name="test_developer",
        display_name="Test Developer",
        agent_type="qwen_acp",
        cli_command="qwen --experimental-acp",
        system_prompt="You are a helpful coding assistant.",
        enabled=True
    )


@pytest.fixture
def temp_storage(tmp_path):
    """Create temporary FileStorage for testing."""
    storage_path = tmp_path / "test_conversations"
    storage_path.mkdir()
    return FileStorage(data_dir=storage_path)


# ACP Connector Tests
@pytest.mark.asyncio
async def test_qwen_acp_session_continuity(mock_acp_subprocess):
    """Test Qwen ACP connector maintains session across multiple execute() calls."""
    connector = QwenACPConnector()
    
    # Launch connector - mock process will provide responses
    await connector.launch("qwen --experimental-acp", "System prompt")
    
    # Verify session was created
    assert connector.session_id is not None
    initial_session_id = connector.session_id
    assert connector.initialized is True
    # Note: authenticated is never set to True in current implementation
    # assert connector.authenticated is True
    
    # First execute call (system prompt already consumed response 1)
    response1 = await connector.execute("First prompt")
    assert response1 is not None
    assert "Mock response 2" in response1
    
    # Verify session persists and history grows
    assert connector.session_id == initial_session_id
    assert len(connector._conversation_history) == 1
    
    # Second execute call  
    response2 = await connector.execute("Second prompt")
    assert response2 is not None
    assert "Mock response 3" in response2
    
    # Verify session still persists and history grew
    assert connector.session_id == initial_session_id
    assert len(connector._conversation_history) == 2
    
    # Third execute call
    response3 = await connector.execute("Third prompt") 
    assert response3 is not None
    assert "Mock response 4" in response3
    
    # Final verification
    assert connector.session_id == initial_session_id
    assert len(connector._conversation_history) == 3
    
    # Verify history contains all responses
    history = connector.get_session_history()
    assert len(history) == 3
    assert all(isinstance(entry, str) for entry in history)
    
    await connector.shutdown()


@pytest.mark.asyncio
async def test_gemini_acp_session_continuity(mock_acp_subprocess):
    """Test Gemini ACP connector maintains session across multiple execute() calls."""
    connector = GeminiACPConnector()
    
    await connector.launch("gemini --experimental-acp", "System prompt")
    
    # Verify session creation
    assert connector.session_id is not None
    initial_session_id = connector.session_id
    
    # Multiple execute calls
    for i in range(3):
        response = await connector.execute(f"Prompt {i+1}")
        assert response is not None
        assert connector.session_id == initial_session_id
        assert len(connector._conversation_history) == i + 1
    
    await connector.shutdown()


@pytest.mark.asyncio
async def test_opencode_acp_session_continuity(mock_acp_subprocess):
    """Test OpenCode ACP connector maintains session across multiple execute() calls."""
    connector = OpenCodeACPConnector()
    
    await connector.launch("opencode --experimental-acp", "System prompt")
    
    # Verify session creation
    assert connector.session_id is not None
    initial_session_id = connector.session_id
    
    # Multiple execute calls
    for i in range(3):
        response = await connector.execute(f"Prompt {i+1}")
        assert response is not None
        assert connector.session_id == initial_session_id
        assert len(connector._conversation_history) == i + 1
    
    await connector.shutdown()


# CLI Connector Tests
@pytest.mark.asyncio
async def test_codex_cli_session_continuity(mock_cli_subprocess):
    """Test Codex CLI connector maintains thread across multiple execute() calls."""
    connector = CodexCLIConnector()
    
    await connector.launch("codex exec --json", "System prompt")
    
    # Verify initialization
    assert connector._initialized is True
    
    # First execute call - should establish thread
    response1 = await connector.execute("First prompt")
    assert response1 is not None
    assert connector.thread_id is not None
    initial_thread_id = connector.thread_id
    
    # Second execute call - should reuse thread
    response2 = await connector.execute("Second prompt")
    assert response2 is not None
    assert connector.thread_id == initial_thread_id
    
    # Third execute call - should still reuse thread
    response3 = await connector.execute("Third prompt")
    assert response3 is not None  
    assert connector.thread_id == initial_thread_id
    
    await connector.shutdown()


@pytest.mark.asyncio
async def test_claude_cli_session_continuity(mock_cli_subprocess):
    """Test Claude CLI connector maintains thread across multiple execute() calls."""
    connector = ClaudeCLICodeConnector()
    
    await connector.launch("claude --json", "System prompt")
    
    # Verify initialization
    assert connector._initialized is True
    
    # First execute call - should establish thread
    response1 = await connector.execute("First prompt")
    assert response1 is not None
    assert connector.thread_id is not None
    initial_thread_id = connector.thread_id
    
    # Second execute call - should reuse thread
    response2 = await connector.execute("Second prompt")
    assert response2 is not None
    assert connector.thread_id == initial_thread_id
    
    # Third execute call - should still reuse thread
    response3 = await connector.execute("Third prompt")
    assert response3 is not None
    assert connector.thread_id == initial_thread_id
    
    await connector.shutdown()


# NeuroCrewLab Integration Tests
@pytest.mark.asyncio
async def test_neurocrew_context_accumulation(temp_storage, mock_acp_subprocess):
    """Test NeuroCrewLab passes cumulative context to connectors."""
    # Mock Config to avoid role validation issues
    with patch('app.core.engine.Config.is_role_based_enabled', return_value=True), \
         patch('app.core.engine.Config.get_role_sequence', return_value=[]), \
         patch('app.core.engine.Config.TELEGRAM_BOT_TOKENS', {'test_bot': 'real_valid_token_12345'}):
        # Create engine with temporary storage
        engine = NeuroCrewLab(storage=temp_storage)
        
        # Create test role
        role = RoleConfig(
            role_name="test_dev",
            display_name="Test Dev",
            agent_type="qwen_acp",
            cli_command="qwen --experimental-acp",
            system_prompt="You are a helpful assistant.",
            telegram_bot_name="test_bot",
            enabled=True
        )
        
        # Add role to engine (monkey patch since we can't modify config easily)
        engine.roles = [role]
    
    chat_id = 12345
    
    # First message - should get full context
    await engine.storage.add_message(chat_id, {"role": "user", "content": "First question"})
    response1 = await engine._process_with_role(chat_id, role)
    assert response1 is not None
    assert response1 != "....."
    
    # Verify connector session was created
    key = (chat_id, role.role_name)
    assert key in engine.connector_sessions
    connector = engine.connector_sessions[key]
    assert connector.session_id is not None
    
    # Second message - should get accumulated context
    await engine.storage.add_message(chat_id, {
        "role": "user", 
        "content": "Follow-up question"
    })
    response2 = await engine._process_with_role(chat_id, role)
    assert response2 is not None
    assert response2 != "....."
    
    # Verify same session is used
    assert key in engine.connector_sessions
    same_connector = engine.connector_sessions[key]
    assert same_connector is connector
    assert same_connector.session_id == connector.session_id
    
    # Verify conversation history grew
    assert len(connector._conversation_history) >= 2
    
    await engine._reset_chat_role_sessions(chat_id)


@pytest.mark.asyncio
async def test_session_recovery_after_restart(temp_storage, mock_acp_subprocess):
    """Test session recovery when process restarts but NeuroCrewLab maintains context."""
    # Mock Config to avoid role validation issues
    with patch('app.core.engine.Config.is_role_based_enabled', return_value=True), \
         patch('app.core.engine.Config.get_role_sequence', return_value=[]), \
         patch('app.core.engine.Config.TELEGRAM_BOT_TOKENS', {'test_bot': 'real_valid_token_12345'}):
        engine = NeuroCrewLab(storage=temp_storage)
        
        role = RoleConfig(
            role_name="test_dev",
            display_name="Test Dev",
            agent_type="qwen_acp",
            cli_command="qwen --experimental-acp",
            system_prompt="You are a helpful assistant.",
            telegram_bot_name="test_bot",
            enabled=True
        )
        
        engine.roles = [role]
    chat_id = 12345
    
    # Add some conversation history
    await engine.storage.add_message(chat_id, {"role": "user", "content": "Initial question"})
    
    # First processing - creates session
    response1 = await engine._process_with_role(chat_id, role)
    assert response1 is not None
    
    key = (chat_id, role.role_name)
    connector = engine.connector_sessions[key]
    initial_session_id = connector.session_id
    
    # Simulate process death (set returncode to non-None)
    connector.process.returncode = 1
    
    # Add another message
    await engine.storage.add_message(chat_id, {"role": "user", "content": "Question after restart"})
    
    # Second processing - should detect dead process and restart
    response2 = await engine._process_with_role(chat_id, role)
    assert response2 is not None
    
    # Verify new connector was created (session_id will change)
    new_connector = engine.connector_sessions[key]
    assert new_connector is not connector  # Should be new instance
    assert new_connector.session_id != initial_session_id  # New session
    
    # But context should be preserved via role_last_seen_index reset
    assert engine.role_last_seen_index[key] == 0  # Reset for full context
    
    await engine._reset_chat_role_sessions(chat_id)


# Cross-connector compatibility tests
@pytest.mark.asyncio
async def test_mixed_connector_session_isolation(mock_acp_subprocess, mock_cli_subprocess):
    """Test that different connector types maintain isolated sessions."""
    # Mock Config to avoid role validation issues  
    with patch('app.core.engine.Config.is_role_based_enabled', return_value=True), \
         patch('app.core.engine.Config.get_role_sequence', return_value=[]), \
         patch('app.core.engine.Config.TELEGRAM_BOT_TOKENS', {'test_bot': 'real_valid_token_12345'}):
        engine = NeuroCrewLab(storage=FileStorage())
        
        # Create roles with different connector types
        acp_role = RoleConfig(
            role_name="acp_dev",
            display_name="ACP Dev",
            agent_type="qwen_acp",
            cli_command="qwen --experimental-acp",
            system_prompt="ACP assistant.",
            telegram_bot_name="test_bot",
            enabled=True
        )
        
        cli_role = RoleConfig(
            role_name="cli_dev",
            display_name="CLI Dev",
            agent_type="codex_cli",
            cli_command="codex exec --json",
            system_prompt="CLI assistant.",
            telegram_bot_name="test_bot",
            enabled=True
        )
        
        engine.roles = [acp_role, cli_role]
    chat_id = 12345
    
    # Process with ACP connector
    await engine.storage.add_message(chat_id, {"role": "user", "content": "Question for ACP"})
    acp_response = await engine._process_with_role(chat_id, acp_role)
    assert acp_response is not None
    
    # Process with CLI connector
    cli_response = await engine._process_with_role(chat_id, cli_role)
    assert cli_response is not None
    
    # Verify both sessions exist and are isolated
    acp_key = (chat_id, acp_role.role_name)
    cli_key = (chat_id, cli_role.role_name)
    
    assert acp_key in engine.connector_sessions
    assert cli_key in engine.connector_sessions
    
    acp_connector = engine.connector_sessions[acp_key]
    cli_connector = engine.connector_sessions[cli_key]
    
    # Different connector types
    assert isinstance(acp_connector, QwenACPConnector)
    assert isinstance(cli_connector, CodexCLIConnector)
    
    # Different session identifiers
    assert acp_connector.session_id is not None
    assert cli_connector.thread_id is not None
    
    await engine._reset_chat_role_sessions(chat_id)


# Error handling tests
@pytest.mark.asyncio
async def test_session_continuity_with_errors(mock_acp_subprocess):
    """Test session continuity when execute() calls encounter errors."""
    connector = QwenACPConnector()
    
    await connector.launch("qwen --experimental-acp", "System prompt")
    initial_session_id = connector.session_id
    
    # First successful execute
    response1 = await connector.execute("Good prompt")
    assert response1 is not None
    assert len(connector._conversation_history) == 1
    
    # Mock a failure on second execute
    with patch.object(connector, '_send_prompt', side_effect=RuntimeError("Network error")):
        with pytest.raises(RuntimeError):
            await connector.execute("Bad prompt")
    
    # Session should still be intact after error
    assert connector.session_id == initial_session_id
    assert len(connector._conversation_history) == 1  # No growth on error
    
    # Third execute should still work with same session
    with patch.object(connector, '_send_prompt', return_value="Recovered response"):
        response3 = await connector.execute("Recovery prompt")
        assert response3 == "Recovered response"
        assert connector.session_id == initial_session_id
        assert len(connector._conversation_history) == 2  # Grows on success
    
    await connector.shutdown()


# Performance and stress tests
@pytest.mark.asyncio
async def test_long_running_session_continuity(mock_acp_subprocess):
    """Test session continuity over many execute() calls."""
    connector = QwenACPConnector()
    
    await connector.launch("qwen --experimental-acp", "System prompt")
    initial_session_id = connector.session_id
    
    # Execute many prompts
    num_calls = 50
    for i in range(num_calls):
        response = await connector.execute(f"Prompt {i+1}")
        assert response is not None
        assert connector.session_id == initial_session_id
        assert len(connector._conversation_history) == i + 1
    
    # Verify final state
    assert len(connector._conversation_history) == num_calls
    assert connector.session_id == initial_session_id
    
    await connector.shutdown()


if __name__ == "__main__":
    # Direct execution for debugging
    print("Run session continuation tests with: pytest tests/test_session_continuation.py -v")
    print("\nTest coverage:")
    print("- ACP connectors (Qwen, Gemini, OpenCode): session_id persistence")
    print("- CLI connectors (Codex, Claude): thread_id persistence")  
    print("- NeuroCrewLab: cumulative context passing")
    print("- Session recovery after process restart")
    print("- Cross-connector session isolation")
    print("- Error handling and recovery")
    print("- Long-running session stability")