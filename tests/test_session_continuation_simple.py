"""
Simple Session Continuation Tests for NeuroCrewLab Connectors.

This module provides focused tests for session continuity without complex
NeuroCrewLab integration issues.

Run with: pytest tests/test_session_continuation_simple.py -v
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
        
        # Add responses for each execute call (support up to 10 execute calls)
        for i in range(3, 23):  # Support many execute calls
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
    num_calls = 10
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
    print("Run session continuation tests with: pytest tests/test_session_continuation_simple.py -v")
    print("\nTest coverage:")
    print("- ACP connectors (Qwen, Gemini, OpenCode): session_id persistence")
    print("- CLI connectors (Codex, Claude): thread_id persistence")  
    print("- Error handling and recovery")
    print("- Long-running session stability")
    print("\nThese tests use mocks instead of real CLI binaries for CI compatibility.")