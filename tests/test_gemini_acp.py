"""
Tests for Gemini ACP connector.

Note: These tests require Gemini CLI to be installed and properly authenticated.
If Gemini is not available, tests will be skipped.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

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