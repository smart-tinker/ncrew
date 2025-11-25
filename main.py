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
import os
from typing import Optional
import httpx

# --- PROXY CONFIGURATION ---
# Sanitize proxy environment variables immediately at startup.
# This is the SINGLE source of truth for proxy adjustment.
# httpx requires 'socks5://' but some environments provide 'socks://'
for var in [
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
]:
    value = os.environ.get(var)
    if value and value.startswith("socks://"):
        new_value = "socks5://" + value[8:]
        os.environ[var] = new_value
        print(f"MAIN: Adjusted {var} from socks:// to {new_value} for compatibility")

from app.config import Config
from app.utils.logger import setup_logger

# Initialize logger
logger = setup_logger(
    "main",
    Config.LOG_LEVEL,
    log_file=Config.DATA_DIR / "logs" / "ncrew.log",
)

# Configure other key loggers to write to the same file
setup_logger(
    "TelegramBot",
    Config.LOG_LEVEL,
    log_file=Config.DATA_DIR / "logs" / "ncrew.log",
)
# ncrew.NeuroCrewLab gets its logger via get_logger("NeuroCrewLab"), which returns "ncrew.NeuroCrewLab"
setup_logger(
    "ncrew.NeuroCrewLab",
    Config.LOG_LEVEL,
    log_file=Config.DATA_DIR / "logs" / "ncrew.log",
)


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
            # Use httpx for connectivity check as it supports SOCKS proxies (with socksio)
            # and aligns with what the bot uses.
            httpx.get("https://api.telegram.org", timeout=5.0)
        except Exception as e:
            logger.error(f"Cannot reach api.telegram.org: {e}")
            logger.error("Check network connectivity and proxy settings.")
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
from app.interfaces.web.server import run_web_server, app


async def async_main():
    """Async main function that handles the complete application lifecycle."""
    # Import and create bot instance
    from app.interfaces.telegram.bot import TelegramBot

    # Start web server in a separate thread with better error handling
    def start_web_server():
        """Start web server with retry logic and better error reporting."""
        import time
        import sys

        retries = 3
        port = 8080

        while retries > 0:
            try:
                logger.info(f"🌐 Attempting to start web server on port {port}...")
                app.run(host="0.0.0.0", port=port, use_reloader=False, debug=False)
                logger.info("✅ Web server stopped successfully")
                break
            except OSError as e:
                if "Address already in use" in str(e):
                    logger.warning(f"⚠️ Port {port} is busy, checking if process is ours...")
                    # Check if our process is already using the port
                    try:
                        import socket
                        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        result = sock.connect_ex(('localhost', port))
                        sock.close()
                        if result == 0:
                            logger.info("🔄 Port is in use by our process")
                            break
                    except:
                        pass

                    if retries > 1:
                        logger.warning(f"🔄 Retrying in 2 seconds... ({retries-1} retries left)")
                        time.sleep(2.0)
                        retries -= 1
                        port += 1  # Try next port
                    else:
                        logger.error(f"❌ Failed to start web server after 3 attempts")
                        break
                else:
                    logger.error(f"❌ Error starting web server: {e}")
                    break
            except Exception as e:
                logger.error(f"❌ Unexpected error in web server: {e}")
                break

    web_thread = threading.Thread(target=start_web_server, name="web_server", daemon=True)
    web_thread.start()
    logger.info(f"🚀 Web server thread started, listening on port 8080")

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

        # Keep the bot running with hot-reload capability
        try:
            while not shutdown_event.is_set():
                # Configuration is now hot-reloaded automatically via Config.reload_configuration()
                # No need for manual restart or flag detection - instant updates!
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
