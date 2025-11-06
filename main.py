"""
Main entry point for NeuroCrew Lab.

This module handles application initialization and startup.
"""

import asyncio
import logging
import sys
import socket
import os
import subprocess
from pathlib import Path
from urllib.request import urlopen
from urllib.error import URLError
from dotenv import load_dotenv

from config import Config
from utils.logger import setup_logger


def main():
    """Main application entry point."""
    logger = None
    try:
        # Load environment variables from .env file
        load_dotenv()

        # Prevent multiple instances
        try:
            existing = subprocess.check_output(["pgrep", "-f", "python main.py"]).decode().strip().splitlines()
        except subprocess.CalledProcessError:
            existing = []

        current_pid = os.getpid()
        other_pids = []
        for line in existing:
            parts = line.strip().split()
            if not parts:
                continue
            pid = int(parts[0])
            cmd = " ".join(parts[1:])
            if pid != current_pid and "python main.py" in cmd:
                other_pids.append(pid)

        if other_pids:
            print("Another instance of NeuroCrew is running. Please stop it before launching.")
            return

        # Kill stale qwen processes
        subprocess.run(
            ["pkill", "-f", "qwen --experimental-acp"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Validate configuration
        Config.validate()

        # Setup logging
        log_file = Config.get_data_dir() / 'logs' / 'ncrew.log'
        logger = setup_logger('ncrew', Config.LOG_LEVEL, log_file)
        logger.info("Starting NeuroCrew Lab...")

        # Ensure all directories exist
        Config.ensure_directories()
        logger.info(f"Data directory: {Config.DATA_DIR}")

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

        # Initialize and start Telegram bot
        logger.info("NeuroCrew Lab initialized successfully")
        logger.info("Starting Telegram bot...")

        # Import and start bot
        from telegram_bot import TelegramBot
        bot = TelegramBot()
        try:
            bot.run()
        except KeyboardInterrupt:
            logger.info("Application stopped by user")
        finally:
            # Graceful shutdown
            if hasattr(bot, 'shutdown'):
                import asyncio
                asyncio.run(bot.shutdown())
    except Exception as e:
        print(f"Failed to start application: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
