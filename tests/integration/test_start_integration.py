"""
Integration test for /start command to identify the real issue.
"""

import os
import sys
import asyncio
from unittest.mock import patch, MagicMock

# Add the project root to Python path
sys.path.insert(0, "/home/dadgo/code/ncrew")


import pytest


@pytest.mark.asyncio
async def test_start_command_integration():
    """Test the /start command with more realistic setup."""

    # Set up minimal environment
    os.environ["MAIN_BOT_TOKEN"] = "test_main_bot_token"
    os.environ["TARGET_CHAT_ID"] = "12345"
    os.environ["LOG_LEVEL"] = "INFO"

    # Mock the config loading to avoid dependency on actual .env
    with patch("app.config.Config.load_roles") as mock_load_roles:
        with patch("app.config.Config._load_telegram_bot_tokens") as mock_load_tokens:
            with patch("app.interfaces.telegram_bot.Application.builder") as mock_app_builder:
                # Setup mocks
                mock_load_roles.return_value = True
                mock_load_tokens.return_value = None

                mock_config = MagicMock()
                mock_config.MAIN_BOT_TOKEN = "test_main_bot_token"
                mock_config.TARGET_CHAT_ID = 12345
                mock_config.LOG_LEVEL = "INFO"
                mock_config.is_role_based_enabled.return_value = True
                mock_config.get_available_roles.return_value = []
                mock_config.TELEGRAM_BOT_TOKENS = {}

                mock_app = MagicMock()
                mock_app_builder.return_value.build.return_value = mock_app

                # Import after patching
                from app.interfaces.telegram_bot import TelegramBot

                # Create bot
                bot = TelegramBot()

                # Mock the ncrew initialization to avoid external dependencies
                bot.ncrew = MagicMock()

                async def mock_ensure_initialized():
                    pass

                bot._ensure_ncrew_initialized = mock_ensure_initialized

                # Create mock update and context
                mock_update = MagicMock()
                mock_update.effective_chat.id = 12345
                mock_update.effective_user.id = 67890
                mock_update.effective_user.first_name = "TestUser"

                # Make reply_text an async function
                async def mock_reply_text(text, **kwargs):
                    print(f"Reply text called with: {text}")
                    return MagicMock()

                mock_update.message.reply_text = mock_reply_text

                mock_context = MagicMock()

                # Mock _is_target_chat
                bot._is_target_chat = MagicMock(return_value=True)

                try:
                    # Test the start command
                    await bot.cmd_start(mock_update, mock_context)
                    print("SUCCESS: /start command executed without errors")
                    return True
                except Exception as e:
                    print(f"ERROR: /start command failed: {e}")
                    import traceback

                    traceback.print_exc()
                    return False


if __name__ == "__main__":
    success = asyncio.run(test_start_command_integration())
    if success:
        print("Test passed!")
    else:
        print("Test failed!")
