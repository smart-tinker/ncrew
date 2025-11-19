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
from typing import Optional
from urllib.request import urlopen
from urllib.error import URLError

from app.config import Config
from app.utils.logger import setup_logger

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
            logger.info(
                f"Available roles: {[role.role_name for role in available_roles]}"
            )

            # Log role details
            logger.info("Role configuration details:")
            for role in available_roles:
                logger.info(f"  • {role.role_name} ({role.display_name})")
                logger.info(
                    f"    Agent: {role.agent_type} | Command: {role.cli_command}"
                )
                logger.info(
                    f"    Bot: {role.telegram_bot_name} | Token: {'✓' if role.get_bot_token() else '⚠'}"
                )
        else:
            logger.warning("Role-based configuration not enabled")
            return

        # Run the application with async main
        asyncio.run(async_main())

    except Exception as e:
        print(f"Failed to start application: {e}")
        sys.exit(1)


import os
import threading
from app.interfaces.web_server import run_web_server


async def async_main():
    """Async main function that handles the complete application lifecycle."""
    # Import and create bot instance
    from app.interfaces.telegram_bot import TelegramBot

    # Start web server in a separate thread
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    logger.info("🚀 Web server started in a background thread")

    # Create global bot reference for signal handling
    global bot_instance
    bot_instance = TelegramBot()

    # Initialize NeuroCrewLab immediately to trigger role filtering
    logger.info("Initializing NeuroCrewLab instance...")
    await bot_instance._ensure_ncrew_initialized()
    logger.info("NeuroCrewLab initialization completed")

    # Perform startup introductions
    logger.info("Performing startup agent introductions...")
    await bot_instance.run_startup_introductions()
    logger.info("Startup agent introductions completed")

    shutdown_event = asyncio.Event()
    shutdown_task: Optional[asyncio.Task] = None

    # Graceful shutdown function with timeout
    async def graceful_shutdown():
        """Perform graceful shutdown of all components with timeout."""
        logger.info("Initiating graceful shutdown...")

        try:
            if hasattr(bot_instance, "shutdown"):
                # Add timeout to prevent hanging during shutdown
                await asyncio.wait_for(bot_instance.shutdown(), timeout=15.0)
            logger.info("Graceful shutdown completed")
        except asyncio.TimeoutError:
            logger.warning("Graceful shutdown timed out, forcing exit")
        except Exception as e:
            logger.error(f"Error during graceful shutdown: {e}")

    async def ensure_shutdown(reason: str):
        nonlocal shutdown_task
        if shutdown_event.is_set():
            return shutdown_task

        shutdown_event.set()
        logger.info("Shutdown requested (%s)", reason)

        shutdown_task = asyncio.create_task(graceful_shutdown())
        await shutdown_task
        return shutdown_task

    # Add graceful_shutdown to bot for internal access
    bot_instance.graceful_shutdown = graceful_shutdown

    loop = asyncio.get_running_loop()

    def handle_sigint():
        if shutdown_event.is_set():
            logger.warning("Second SIGINT received, forcing immediate exit")
            loop.stop()
            return
        logger.info("SIGINT received. Initiating shutdown...")
        loop.call_soon_threadsafe(
            lambda: asyncio.create_task(ensure_shutdown("SIGINT"))
        )

    try:
        if hasattr(loop, "add_signal_handler"):
            loop.add_signal_handler(signal.SIGINT, handle_sigint)
        else:
            signal.signal(
                signal.SIGINT,
                lambda *_: loop.call_soon_threadsafe(
                    lambda: asyncio.create_task(ensure_shutdown("SIGINT"))
                ),
            )

        logger.info("Starting NeuroCrew Lab Telegram bot...")
        # Use the proper async lifecycle management
        await bot_instance.application.initialize()
        await bot_instance.application.start()
        await bot_instance.application.updater.start_polling(drop_pending_updates=True)

        # Keep the bot running and check for reload flag
        try:
            while not shutdown_event.is_set():
                if os.path.exists(".reload"):
                    logger.info("Reload flag detected. Restarting application...")
                    await bot_instance.application.bot.send_message(
                        chat_id=Config.TARGET_CHAT_ID,
                        text="Configuration updated. Restarting and starting a new conversation...",
                    )
                    await ensure_shutdown("configuration reload")
                    os.remove(".reload")
                    os.execv(sys.executable, ["python"] + sys.argv)
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info("Bot operation cancelled")

        if not shutdown_event.is_set():
            await ensure_shutdown("loop completed")

    except KeyboardInterrupt:
        logger.info("Application stopped by user (Ctrl+C)")
        await ensure_shutdown("KeyboardInterrupt")
    except Exception as e:
        logger.error(f"Unexpected error during bot operation: {e}")
        await ensure_shutdown("Unhandled exception")
        raise
    finally:
        if hasattr(loop, "remove_signal_handler"):
            loop.remove_signal_handler(signal.SIGINT)


if __name__ == "__main__":
    main()
