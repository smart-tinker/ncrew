#!/usr/bin/env python3
"""
NeuroCrew Lab - Main Entry Point

AI agent orchestration platform with role-based architecture.
Handles application initialization, graceful shutdown, and Telegram bot startup.
"""

import asyncio
import logging
import signal
import sys
from urllib.request import urlopen
from urllib.error import URLError

from config import Config
from utils.logger import setup_logger

# Initialize logger
logger = setup_logger("main", Config.LOG_LEVEL)


def main():
    """Main entry point for the application."""
    try:
        # Basic configuration
        logger.info("🚀 Starting NeuroCrew Lab...")
        logger.info(f"Version: 1.0.0")
        logger.info(f"Python: {sys.version}")

        # Setup directories (handled by FileStorage initialization)

        # Log configuration summary
        logger.info(f"Log level: {Config.LOG_LEVEL}")
        logger.info(f"Max conversation length: {Config.MAX_CONVERSATION_LENGTH}")
        logger.info(f"Agent timeout: {Config.AGENT_TIMEOUT}s")

        # Check Telegram connectivity
        try:
            urlopen("https://api.telegram.org", timeout=3)
        except URLError:
            logger.error("Cannot reach api.telegram.org. Check network connectivity.")
            return

        # Log role-based configuration
        logger.info("=== ROLE-BASED ARCHITECTURE INITIALIZED ===")
        if Config.is_role_based_enabled():
            available_roles = Config.get_available_roles()
            logger.info(f"Total roles loaded: {len(available_roles)}")
            logger.info(f"Available roles: {[role.role_name for role in available_roles]}")

            # Log role details
            logger.info("Role configuration details:")
            for role in available_roles:
                logger.info(f"  • {role.role_name} ({role.display_name})")
                logger.info(f"    Agent: {role.agent_type} | Command: {role.cli_command}")
                logger.info(f"    Bot: {role.telegram_bot_name} | Token: {'✓' if role.get_bot_token() else '⚠'}")
        else:
            logger.warning("Role-based configuration not enabled")
            return

        # Run the application with async main
        asyncio.run(async_main())

    except Exception as e:
        print(f"Failed to start application: {e}")
        sys.exit(1)


async def async_main():
    """Async main function that handles the complete application lifecycle."""
    # Import and create bot instance
    from telegram_bot import TelegramBot

    # Create global bot reference for signal handling
    global bot_instance
    bot_instance = TelegramBot()

    # Initialize NeuroCrewLab immediately to trigger role filtering
    logger.info("Initializing NeuroCrewLab instance...")
    await bot_instance._ensure_ncrew_initialized()
    logger.info("NeuroCrewLab initialization completed")

    # Graceful shutdown function with timeout
    async def graceful_shutdown():
        """Perform graceful shutdown of all components with timeout."""
        logger.info("Initiating graceful shutdown...")

        try:
            if hasattr(bot_instance, 'shutdown'):
                # Add timeout to prevent hanging during shutdown
                await asyncio.wait_for(bot_instance.shutdown(), timeout=15.0)
            logger.info("Graceful shutdown completed")
        except asyncio.TimeoutError:
            logger.warning("Graceful shutdown timed out, forcing exit")
        except Exception as e:
            logger.error(f"Error during graceful shutdown: {e}")

    # Add graceful_shutdown to bot for internal access
    bot_instance.graceful_shutdown = graceful_shutdown

    try:
        logger.info("Starting NeuroCrew Lab Telegram bot...")
        # Use the proper async lifecycle management
        await bot_instance.application.initialize()
        await bot_instance.application.start()
        await bot_instance.application.updater.start_polling(drop_pending_updates=True)

        # Keep the bot running
        try:
            # Run indefinitely until interrupted
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info("Bot operation cancelled")

        # Graceful shutdown
        await bot_instance.application.updater.stop()
        await bot_instance.application.stop()
        await bot_instance.application.shutdown()

    except KeyboardInterrupt:
        logger.info("Application stopped by user (Ctrl+C)")
        await graceful_shutdown()
    except Exception as e:
        logger.error(f"Unexpected error during bot operation: {e}")
        await graceful_shutdown()
        raise


if __name__ == '__main__':
    main()