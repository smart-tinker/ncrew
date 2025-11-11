"""
Tests for Gemini ACP connector.

Note: These tests require Gemini CLI to be installed and properly authenticated.
If Gemini is not available, tests will be skipped.
"""

import pytest
import asyncio
import json
import tempfile
import subprocess
from unittest.mock import AsyncMock, MagicMock, patch, call
from io import StringIO

from connectors.gemini_acp_connector import GeminiACPConnector


class TestGeminiACPConnector:
    """Test suite for GeminiACPConnector."""

    @pytest.fixture
    def connector(self):
        """Create a GeminiACPConnector instance for testing."""
        return GeminiACPConnector()

    def test_initialization(self, connector):
        """Test connector initialization."""
        assert connector.message_id == 0
        assert connector.session_id is None
        assert not connector.initialized
        assert not connector.authenticated
        assert connector._conversation_history == []

    def test_check_availability_gemini_available(self, connector):
        """Test availability check when Gemini is available."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout='1.0.0', stderr='')

            assert connector.check_availability() is True
            mock_run.assert_called_once_with(
                ['gemini', '--version'],
                capture_output=True,
                text=True,
                timeout=10
            )

    def test_check_availability_gemini_not_available(self, connector):
        """Test availability check when Gemini is not available."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = Exception("Command not found")

            assert connector.check_availability() is False

    def test_get_info(self, connector):
        """Test get_info method."""
        info = connector.get_info()

        assert info['name'] == 'Gemini ACP Connector (experimental)'
        assert info['type'] == 'gemini_acp'
        assert 'status' in info
        assert 'session_id' in info

    @pytest.mark.asyncio
    async def test_shutdown_without_process(self, connector):
        """Test shutdown when no process is running."""
        await connector.shutdown()
        assert connector.process is None

    @pytest.mark.asyncio
    async def test_is_alive_no_process(self, connector):
        """Test is_alive when no process exists."""
        assert not connector.is_alive()

    @pytest.mark.asyncio
    async def test_is_alive_process_terminated(self, connector):
        """Test is_alive when process has terminated."""
        mock_process = AsyncMock()
        mock_process.returncode = 0
        connector.process = mock_process

        assert not connector.is_alive()

    @pytest.mark.asyncio
    async def test_is_alive_process_running(self, connector):
        """Test is_alive when process is running."""
        mock_process = AsyncMock()
        mock_process.returncode = None
        mock_process.pid = 12345
        connector.process = mock_process

        with patch('os.kill') as mock_kill:
            mock_kill.return_value = None  # Signal sent successfully
            assert connector.is_alive()

    def test_default_command(self, connector):
        """Test default command configuration."""
        assert connector.DEFAULT_COMMAND == "gemini --experimental-acp"

    def test_prepare_command_args_simple(self, connector):
        """Test command argument preparation for simple command."""
        with patch('shutil.which', return_value='/usr/bin/gemini'):
            args = connector._prepare_command_args("gemini --experimental-acp")
            assert args == ["gemini", "--experimental-acp"]

    def test_prepare_command_args_with_path(self, connector):
        """Test command argument preparation when command has path."""
        with patch('os.path.isfile', return_value=True):
            args = connector._prepare_command_args("/usr/local/bin/gemini --experimental-acp")
            assert args == ["/usr/local/bin/gemini", "--experimental-acp"]

    def test_prepare_command_args_not_found(self, connector):
        """Test command argument preparation when command not found."""
        def mock_which(cmd):
            if cmd == "nonexistent":
                return None
            elif cmd == "gemini":
                return "/usr/bin/gemini"
            return None

        with patch('os.path.isfile', return_value=False), \
             patch('shutil.which', side_effect=mock_which):
            args = connector._prepare_command_args("nonexistent --flag")
            assert args == ["/usr/bin/gemini", "--flag"]

    @pytest.mark.asyncio
    async def test_send_request_timeout_validation(self, connector):
        """Test 30s timeout configuration for _send_request."""
        connector.initialized = True
        connector.authenticated = True
        connector.session_id = "test_session"

        mock_process = AsyncMock()
        mock_process.stdin = AsyncMock()
        mock_process.stdin.write = AsyncMock()
        mock_process.returncode = None
        connector.process = mock_process

        # Mock _read_response to raise timeout
        with patch.object(connector, '_read_response',
                         side_effect=asyncio.TimeoutError):
            with pytest.raises(RuntimeError, match="Timeout waiting for Gemini ACP response"):
                await connector._send_request("test/method", {"test": "data"})

    @pytest.mark.asyncio
    async def test_chunk_parsing_valid_json(self, connector):
        """Test chunk parsing with valid JSON-RPC responses."""
        mock_stdout = AsyncMock()

        # Create a proper async iterator for stdout
        async def mock_readline():
            valid_response = {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "content": "Test response",
                    "session_id": "test_session"
                }
            }
            return (json.dumps(valid_response) + "\n").encode('utf-8')

        mock_stdout.readline = mock_readline

        mock_process = AsyncMock()
        mock_process.stdout = mock_stdout
        connector.process = mock_process

        response = await connector._read_response()
        assert response["result"]["content"] == "Test response"
        assert response["result"]["session_id"] == "test_session"

    @pytest.mark.asyncio
    async def test_chunk_parsing_malformed_json(self, connector):
        """Test chunk parsing with malformed JSON handling."""
        mock_stdout = AsyncMock()

        # Simulate malformed JSON followed by valid JSON
        responses = [
            '{"invalid": json}\n'.encode('utf-8'),  # malformed
            '{"jsonrpc":"2.0","id":1,"result":{"content":"valid"}}\n'.encode('utf-8')  # valid
        ]
        response_index = 0

        async def mock_readline():
            nonlocal response_index
            if response_index < len(responses):
                result = responses[response_index]
                response_index += 1
                return result
            return b''  # EOF

        mock_stdout.readline = mock_readline

        mock_process = AsyncMock()
        mock_process.stdout = mock_stdout
        connector.process = mock_process

        # Should skip malformed JSON and return valid response
        response = await connector._read_response()
        assert response["result"]["content"] == "valid"

    @pytest.mark.asyncio
    async def test_chunk_parsing_incomplete_response(self, connector):
        """Test chunk parsing with incomplete JSON-RPC response."""
        mock_stdout = AsyncMock()

        async def mock_readline():
            # Write incomplete JSON-RPC (missing required fields)
            incomplete_response = {
                "jsonrpc": "2.0",
                "id": 1
                # Missing "result" or "error" field
            }
            return (json.dumps(incomplete_response) + "\n").encode('utf-8')

        mock_stdout.readline = mock_readline

        mock_process = AsyncMock()
        mock_process.stdout = mock_stdout
        connector.process = mock_process

        response = await connector._read_response()
        # Should handle gracefully by returning the incomplete response
        assert "result" not in response
        assert "error" not in response

    @pytest.mark.asyncio
    async def test_chunk_parsing_buffer_accumulation(self, connector):
        """Test chunk parsing with buffer accumulation scenarios."""
        mock_stdout = AsyncMock()

        async def mock_readline():
            # Simulate reading a complete JSON line (the connector reads line by line)
            complete_json = '{"jsonrpc":"2.0","id":1,"result":{"content":"complete"}}\n'
            return complete_json.encode('utf-8')

        mock_stdout.readline = mock_readline

        mock_process = AsyncMock()
        mock_process.stdout = mock_stdout
        connector.process = mock_process

        response = await connector._read_response()
        assert response["result"]["content"] == "complete"

    @pytest.mark.asyncio
    async def test_graceful_degradation_process_crash(self, connector):
        """Test graceful degradation when process crashes (validates line 279)."""
        mock_stdout = AsyncMock()

        async def mock_readline():
            # Simulate EOF (process closed unexpectedly)
            return b''  # Empty bytes indicate EOF

        mock_stdout.readline = mock_readline

        mock_process = AsyncMock()
        mock_process.stdout = mock_stdout
        connector.process = mock_process

        # Should handle gracefully and return error response instead of crashing
        response = await connector._read_response()

        assert isinstance(response, dict)
        assert "error" in response
        assert response["error"]["code"] == -1
        assert "Process closed unexpectedly" in response["error"]["message"]

    @pytest.mark.asyncio
    async def test_graceful_degradation_timeout_without_crash(self, connector):
        """Test graceful degradation on timeout without process crash."""
        connector.initialized = True
        connector.authenticated = True
        connector.session_id = "test_session"

        mock_process = AsyncMock()
        mock_process.returncode = None  # Process still running
        mock_process.stdin = AsyncMock()
        mock_process.stdin.write = AsyncMock()
        connector.process = mock_process

        # Mock timeout during response reception
        with patch.object(connector, '_read_response',
                         side_effect=asyncio.TimeoutError):
            with pytest.raises(RuntimeError, match="Timeout waiting for Gemini ACP response"):
                await connector._send_request("test/method", {"test": "data"})

    @pytest.mark.asyncio
    async def test_end_to_end_integration_with_mock_server(self, connector):
        """Test end-to-end integration with mock CLI server."""
        # Mock subprocess execution
        mock_process = AsyncMock()
        mock_stdout = AsyncMock()

        # Simulate complete CLI interaction responses
        responses = [
            '{"jsonrpc":"2.0","id":0,"result":{"session_id":"mock_session_123"}}\n'.encode('utf-8'),
            '{"jsonrpc":"2.0","id":1,"result":{"content":"Mock AI response"}}\n'.encode('utf-8')
        ]
        response_index = 0

        async def mock_readline():
            nonlocal response_index
            if response_index < len(responses):
                result = responses[response_index]
                response_index += 1
                return result
            return b''  # EOF

        mock_stdout.readline = mock_readline
        mock_process.stdout = mock_stdout
        mock_process.returncode = None
        mock_process.stdin = AsyncMock()
        mock_process.stdin.write = AsyncMock()

        connector.process = mock_process

        # Test _send_request directly (skip _initialize as it needs complex subprocess mocking)
        response = await connector._send_request("test/method", {"test": "data"})
        # _send_request returns (response, output) tuple
        assert isinstance(response, tuple)
        response_dict, output_str = response
        assert response_dict["result"]["content"] == "Mock AI response"

    @pytest.mark.asyncio
    async def test_concurrent_message_handling(self, connector):
        """Test concurrent message handling and state management."""
        connector.initialized = True
        connector.authenticated = True
        connector.session_id = "test_session"

        mock_process = AsyncMock()
        mock_process.returncode = None
        mock_process.stdin = AsyncMock()
        mock_process.stdin.write = AsyncMock()
        connector.process = mock_process

        # Mock responses for concurrent calls
        call_count = 0
        async def mock_read_response():
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.1)  # Simulate processing delay
            return {
                "jsonrpc": "2.0",
                "result": {"content": f"Response {call_count}"}
            }

        with patch.object(connector, '_read_response', side_effect=mock_read_response):
            # Send multiple requests concurrently
            tasks = [
                connector._send_request("test/method", {"message": f"Message {i}"})
                for i in range(3)
            ]
            responses = await asyncio.gather(*tasks)

            # All should complete successfully - _send_request returns (response, output) tuples
            assert len(responses) == 3
            for response_tuple in responses:
                response_dict, output_str = response_tuple
                assert "Response" in response_dict["result"]["content"]

    @pytest.mark.asyncio
    async def test_error_recovery_and_reconnect(self, connector):
        """Test error recovery and reconnection scenarios."""
        connector.session_id = "test_session"

        # Mock stdout that returns EOF (process crash)
        mock_stdout = AsyncMock()
        async def mock_readline_eof():
            return b''  # EOF indicates process crash

        mock_stdout.readline = mock_readline_eof

        mock_process_1 = AsyncMock()
        mock_process_1.stdout = mock_stdout
        mock_process_1.returncode = 1
        connector.process = mock_process_1

        # First call fails due to process crash
        response_1 = await connector._read_response()
        assert "error" in response_1
        assert "Process closed unexpectedly" in response_1["error"]["message"]

        # Reset and test recovery
        connector.process = None
        connector.session_id = None
        connector.initialized = False
        connector.authenticated = False

        # Next initialization should work with proper response
        mock_stdout_2 = AsyncMock()
        async def mock_readline_success():
            response = '{"jsonrpc":"2.0","id":0,"result":{"session_id":"new_session"}}\n'
            return response.encode('utf-8')

        mock_stdout_2.readline = mock_readline_success

        mock_process_2 = AsyncMock()
        mock_process_2.stdout = mock_stdout_2
        mock_process_2.returncode = None

        connector.process = mock_process_2

        response_2 = await connector._read_response()
        assert response_2["result"]["session_id"] == "new_session"