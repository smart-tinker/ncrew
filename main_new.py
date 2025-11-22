#!/usr/bin/env python3
"""
NeuroCrew Lab - New Interface-Agnostic Main Entry Point

This is the new main entry point that uses the interface abstraction layer.
The application can now run and function independently of specific interfaces.
"""

import asyncio
import logging
import sys
import os
from typing import Optional

# --- PROXY CONFIGURATION ---
# Sanitize proxy environment variables immediately at startup.
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
from app.core.application import ApplicationFactory


def main():
    """Main entry point for the interface-agnostic NeuroCrew application."""
    try:
        # Basic configuration
        logger = setup_logger(
            "main",
            Config.LOG_LEVEL,
            log_file=Config.DATA_DIR / "logs" / "ncrew.log",
        )

        logger.info("🚀 Starting NeuroCrew Lab (Interface-Agnostic)...")
        logger.info(f"Version: 2.0.0")
        logger.info(f"Python: {sys.version}")

        # Log configuration summary
        logger.info(f"Log level: {Config.LOG_LEVEL}")
        logger.info(f"Max conversation length: {Config.MAX_CONVERSATION_LENGTH}")
        logger.info(f"Agent timeout: {Config.AGENT_TIMEOUT}s")

        # Check role-based configuration
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

        # Check interface configurations
        logger.info("=== INTERFACE CONFIGURATION ===")
        configured_interfaces = []

        if Config.MAIN_BOT_TOKEN:
            configured_interfaces.append("Telegram")
            logger.info("✅ Telegram interface configured")
        else:
            logger.info("⚠️  Telegram interface not configured (no MAIN_BOT_TOKEN)")

        # Web interface is always available
        configured_interfaces.append("Web")
        logger.info("✅ Web interface configured")

        if configured_interfaces:
            logger.info(f"Configured interfaces: {', '.join(configured_interfaces)}")
        else:
            logger.warning("⚠️  No interfaces configured - application will run in headless mode")

        # Run the application
        asyncio.run(ApplicationFactory.create_and_run())

    except KeyboardInterrupt:
        logger.info("Application stopped by user")
    except Exception as e:
        logging.error(f"Failed to start application: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()