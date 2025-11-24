"""
Test for /start command issue in Telegram bot.

This test reproduces the problem where the /start command fails
and provides a way to verify the fix.
"""

import os
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from telegram import Update, Message, User, Chat
from telegram.ext import CallbackContext

from app.interfaces.telegram.telegram_bot import TelegramBot
from app.config import Config


@pytest.fixture
def mock_update():
    """Create a mock Telegram update."""
    update = MagicMock(spec=Update)
    update.effective_chat.id = 12345
    update.effective_user.id = 67890
    update.effective_user.first_name = "TestUser"
    update.message.reply_text = AsyncMock()
    return update


@pytest.fixture
def mock_context():
    """Create a mock Telegram context."""
    return MagicMock(spec=CallbackContext)


@pytest.fixture
def telegram_bot():
    """Create a TelegramBot instance for testing."""
    with patch("app.interfaces.telegram.telegram_bot.Config") as mock_config:
        # Mock configuration
        mock_config.MAIN_BOT_TOKEN = "test_token"
        mock_config.TARGET_CHAT_ID = 12345
        mock_config.LOG_LEVEL = "INFO"
        mock_config.is_role_based_enabled.return_value = True
        mock_config.get_available_roles.return_value = []

        with patch("app.interfaces.telegram.telegram_bot.Application.builder") as mock_app_builder:
            mock_app = MagicMock()
            mock_app_builder.return_value.build.return_value = mock_app
            bot = TelegramBot()
            return bot


@pytest.mark.asyncio
async def test_start_command_success(telegram_bot, mock_update, mock_context):
    """Test successful /start command execution."""
    # Mock the _ensure_ncrew_initialized method
    telegram_bot._ensure_ncrew_initialized = AsyncMock()

    # Mock the _is_target_chat method to return True
    telegram_bot._is_target_chat = MagicMock(return_value=True)

    # Execute the command
    await telegram_bot.cmd_start(mock_update, mock_context)

    # Verify that initialization was called
    telegram_bot._ensure_ncrew_initialized.assert_called_once()

    # Verify that a reply was sent
    mock_update.message.reply_text.assert_called_once()

    # Get the message that was sent
    call_args = mock_update.message.reply_text.call_args
    message = call_args[0][0]  # First positional argument

    # Verify the welcome message content
    assert "Welcome to NeuroCrew Lab" in message
    assert "Available commands" in message or "commands" in message
    assert "/help" in message
    assert "/reset" in message


@pytest.mark.asyncio
async def test_start_command_wrong_chat(telegram_bot, mock_update, mock_context):
    """Test /start command from non-target chat."""
    # Mock the _is_target_chat method to return False
    telegram_bot._is_target_chat = MagicMock(return_value=False)

    # Execute the command
    await telegram_bot.cmd_start(mock_update, mock_context)

    # Verify that no reply was sent (message from wrong chat)
    mock_update.message.reply_text.assert_not_called()


@pytest.mark.asyncio
async def test_start_command_initialization_error(
    telegram_bot, mock_update, mock_context
):
    """Test /start command when NeuroCrew initialization fails."""
    # Mock the _ensure_ncrew_initialized method to raise an exception
    telegram_bot._ensure_ncrew_initialized = AsyncMock(
        side_effect=Exception("Initialization failed")
    )

    # Mock the _is_target_chat method to return True
    telegram_bot._is_target_chat = MagicMock(return_value=True)

    # Execute the command
    await telegram_bot.cmd_start(mock_update, mock_context)

    # Verify that an error message was sent
    mock_update.message.reply_text.assert_called_once()

    # Get the error message
    call_args = mock_update.message.reply_text.call_args
    message = call_args[0][0]

    assert "❌ Sorry, an error occurred" in message


@pytest.mark.asyncio
async def test_start_command_with_real_config():
    """Test /start command with more realistic configuration."""
    # This test uses the actual config but mocks external dependencies

    with patch("app.interfaces.telegram_bot.Config") as mock_config:
        # Setup realistic configuration
        mock_config.MAIN_BOT_TOKEN = "test_main_bot_token"
        mock_config.TARGET_CHAT_ID = 12345
        mock_config.LOG_LEVEL = "INFO"
        mock_config.is_role_based_enabled.return_value = True
        mock_config.get_available_roles.return_value = []

        # Mock the application builder
        with patch("app.interfaces.telegram_bot.Application.builder") as mock_app_builder:
            mock_app = MagicMock()
            mock_app_builder.return_value.build.return_value = mock_app

            # Create bot instance
            bot = TelegramBot()

            # Mock update and context
            mock_update = MagicMock(spec=Update)
            mock_update.effective_chat.id = 12345
            mock_update.effective_user.id = 67890
            mock_update.effective_user.first_name = "TestUser"
            mock_update.message.reply_text = AsyncMock()

            mock_context = MagicMock(spec=CallbackContext)

            # Mock methods
            bot._ensure_ncrew_initialized = AsyncMock()
            bot._is_target_chat = MagicMock(return_value=True)

            # Execute the command
            await bot.cmd_start(mock_update, mock_context)

            # Verify results
            bot._ensure_ncrew_initialized.assert_called_once()
            mock_update.message.reply_text.assert_called_once()

            # Check message content
            call_args = mock_update.message.reply_text.call_args
            message = call_args[0][0]
            assert "Welcome to NeuroCrew Lab" in message


if __name__ == "__main__":
    # Run specific test
    pytest.main([__file__, "-v"])
