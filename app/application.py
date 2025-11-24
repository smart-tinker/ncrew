"""
NeuroCrew Application - Interface-Agnostic Multi-Interface Architecture

MVP Implementation - Simple wrapper around existing components.
No legacy compatibility, no performance optimization, just core functionality.
"""

import asyncio
import logging
from typing import Dict, Optional, List, Any
from enum import Enum

from app.config.manager import Config
from app.core.engine import NeuroCrewLab
from app.utils.logger import get_logger

# Import interfaces (existing classes)
from app.interfaces.telegram.telegram_bot import TelegramBot
from app.interfaces.web.web_server import app as web_app


class OperationMode(Enum):
    """Application operation modes."""
    HEADLESS = "headless"           # No interfaces
    TELEGRAM_ONLY = "telegram"     # Only Telegram
    WEB_ONLY = "web"              # Only Web
    MULTI_INTERFACE = "multi"      # Multiple interfaces


class NeuroCrewApplication:
    """
    Interface-agnostic application wrapper for NeuroCrew.

    MVP Implementation:
    - Manages multiple interfaces without complex logic
    - Simple lifecycle management
    - Basic error handling
    - No backward compatibility
    """

    def __init__(self):
        """Initialize application."""
        self.logger = get_logger("NeuroCrewApplication")
        self.ncrew_lab: Optional[NeuroCrewLab] = None
        self.telegram_bot: Optional[TelegramBot] = None
        self.operation_mode = OperationMode.HEADLESS
        self.is_running = False
        self.interfaces_status = {}

    async def initialize(self) -> bool:
        """
        Initialize core application without interfaces.

        Returns:
            bool: True if initialization successful
        """
        try:
            self.logger.info("🚀 Initializing NeuroCrew Application...")

            # Initialize core NeuroCrew engine
            self.logger.info("🧠 Initializing NeuroCrew Lab engine...")
            self.ncrew_lab = NeuroCrewLab()
            await self.ncrew_lab.initialize()

            # Determine operation mode based on configuration
            self.operation_mode = self._detect_operation_mode()
            self.logger.info(f"📋 Operation mode: {self.operation_mode.value}")

            self.logger.info("✅ NeuroCrew Application initialized successfully")
            return True

        except Exception as e:
            self.logger.error(f"❌ Failed to initialize NeuroCrew Application: {e}")
            return False

    def _detect_operation_mode(self) -> OperationMode:
        """Detect operation mode from available configuration."""
        telegram_available = bool(Config.MAIN_BOT_TOKEN and Config.TARGET_CHAT_ID)

        # For MVP: web interface is always available, so we need explicit check
        if not telegram_available:
            return OperationMode.HEADLESS
        else:
            return OperationMode.MULTI_INTERFACE

    async def start(self) -> bool:
        """
        Start application and initialize interfaces.

        Returns:
            bool: True if startup successful
        """
        try:
            if self.is_running:
                self.logger.warning("⚠️ Application is already running")
                return True

            self.logger.info("🎬 Starting NeuroCrew Application...")

            # Start interfaces based on operation mode
            success = await self._start_interfaces()

            if success:
                self.is_running = True
                self.logger.info("✅ NeuroCrew Application started successfully")
                return True
            else:
                self.logger.error("❌ Failed to start application interfaces")
                return False

        except Exception as e:
            self.logger.error(f"❌ Failed to start NeuroCrew Application: {e}")
            return False

    async def _start_interfaces(self) -> bool:
        """Start interfaces based on operation mode."""
        try:
            if self.operation_mode == OperationMode.HEADLESS:
                self.logger.info("🔧 Running in headless mode (no interfaces)")
                return True

            # Start Telegram interface if available
            if self.operation_mode in [OperationMode.TELEGRAM_ONLY, OperationMode.MULTI_INTERFACE]:
                if not await self._start_telegram_interface():
                    if self.operation_mode == OperationMode.TELEGRAM_ONLY:
                        return False
                    self.logger.warning("⚠️ Telegram interface failed, continuing with Web only")
                    self.operation_mode = OperationMode.WEB_ONLY

            # Start Web interface if available
            if self.operation_mode in [OperationMode.WEB_ONLY, OperationMode.MULTI_INTERFACE]:
                if not await self._start_web_interface():
                    if self.operation_mode == OperationMode.WEB_ONLY:
                        return False
                    self.logger.warning("⚠️ Web interface failed, continuing with Telegram only")
                    if self.telegram_bot:
                        self.operation_mode = OperationMode.TELEGRAM_ONLY
                    else:
                        self.operation_mode = OperationMode.HEADLESS

            return True

        except Exception as e:
            self.logger.error(f"❌ Failed to start interfaces: {e}")
            return False

    async def _start_telegram_interface(self) -> bool:
        """Start Telegram interface."""
        try:
            self.logger.info("📱 Starting Telegram interface...")
            self.telegram_bot = TelegramBot()
            self.interfaces_status["telegram"] = "starting"

            # Telegram bot starts automatically in constructor
            # Just verify it's properly initialized
            if self.telegram_bot and self.telegram_bot.application:
                self.interfaces_status["telegram"] = "active"
                self.logger.info("✅ Telegram interface started successfully")
                return True
            else:
                self.interfaces_status["telegram"] = "failed"
                return False

        except Exception as e:
            self.interfaces_status["telegram"] = "failed"
            self.logger.error(f"❌ Failed to start Telegram interface: {e}")
            return False

    async def _start_web_interface(self) -> bool:
        """Start Web interface."""
        try:
            self.logger.info("🌐 Starting Web interface...")

            # Web interface is managed by Flask app
            # We'll start it in a separate thread later
            self.interfaces_status["web"] = "active"
            self.logger.info("✅ Web interface ready")
            return True

        except Exception as e:
            self.interfaces_status["web"] = "failed"
            self.logger.error(f"❌ Failed to start Web interface: {e}")
            return False

    async def stop(self) -> bool:
        """
        Stop application and all interfaces.

        Returns:
            bool: True if shutdown successful
        """
        try:
            if not self.is_running:
                self.logger.warning("⚠️ Application is not running")
                return True

            self.logger.info("🛑 Stopping NeuroCrew Application...")

            # Stop interfaces
            await self._stop_interfaces()

            # Stop NeuroCrew engine
            if self.ncrew_lab:
                # Clean shutdown if method exists
                if hasattr(self.ncrew_lab, 'shutdown'):
                    await self.ncrew_lab.shutdown()
                self.ncrew_lab = None

            self.is_running = False
            self.logger.info("✅ NeuroCrew Application stopped successfully")
            return True

        except Exception as e:
            self.logger.error(f"❌ Failed to stop NeuroCrew Application: {e}")
            return False

    async def _stop_interfaces(self) -> None:
        """Stop all interfaces."""
        try:
            # Stop Telegram interface
            if self.telegram_bot:
                self.logger.info("📱 Stopping Telegram interface...")
                if hasattr(self.telegram_bot, 'shutdown'):
                    await self.telegram_bot.shutdown()
                self.telegram_bot = None
                self.interfaces_status["telegram"] = "stopped"

            # Stop Web interface
            if self.interfaces_status.get("web") == "active":
                self.logger.info("🌐 Stopping Web interface...")
                # Web interface cleanup would go here
                self.interfaces_status["web"] = "stopped"

        except Exception as e:
            self.logger.error(f"❌ Error stopping interfaces: {e}")

    async def process_message(self, source_interface: str, chat_id: int, user_text: str) -> bool:
        """
        Process message from any interface.

        Args:
            source_interface: Interface that sent the message
            chat_id: Chat ID from the interface
            user_text: User message content

        Returns:
            bool: True if message processed successfully
        """
        try:
            if not self.is_running or not self.ncrew_lab:
                self.logger.warning("⚠️ Application not ready to process messages")
                return False

            self.logger.debug(f"📨 Processing message from {source_interface}: {user_text[:50]}...")

            # Process message through NeuroCrew engine
            response_count = 0
            async for role_config, raw_response in self.ncrew_lab.handle_message(chat_id, user_text):
                if role_config and raw_response:
                    # Route response back to source interface
                    success = await self._send_response_to_interface(
                        source_interface, chat_id, role_config, raw_response
                    )
                    if success:
                        response_count += 1
                    else:
                        self.logger.warning(f"⚠️ Failed to send response to {source_interface}")

            self.logger.debug(f"✅ Processed {response_count} responses for {source_interface} message")
            return response_count > 0

        except Exception as e:
            self.logger.error(f"❌ Failed to process message from {source_interface}: {e}")
            return False

    async def _send_response_to_interface(self, interface_type: str, chat_id: int,
                                       role_config, response: str) -> bool:
        """Send response to specific interface."""
        try:
            if interface_type == "telegram" and self.telegram_bot:
                # Send via Telegram bot
                from app.utils.formatters import format_agent_response, format_telegram_message, split_long_message

                formatted_response = format_agent_response(role_config.display_name, response)
                messages = split_long_message(formatted_response, Config.TELEGRAM_MAX_MESSAGE_LENGTH)

                for message_chunk in messages:
                    await self.telegram_bot.application.bot.send_message(
                        chat_id=chat_id,
                        text=message_chunk,
                        parse_mode="MarkdownV2"
                    )
                return True

            elif interface_type == "web":
                # Web interface would handle this differently
                # For now, just log it
                self.logger.info(f"🌐 Web response: {role_config.display_name}: {response[:100]}...")
                return True

            return False

        except Exception as e:
            self.logger.error(f"❌ Failed to send response to {interface_type}: {e}")
            return False

    def get_status(self) -> Dict[str, Any]:
        """
        Get current application status.

        Returns:
            Dict with application status information
        """
        return {
            "application": {
                "running": self.is_running,
                "operation_mode": self.operation_mode.value,
                "ncrew_engine_initialized": self.ncrew_lab is not None
            },
            "interfaces": self.interfaces_status.copy(),
            "roles": {
                "total_loaded": len(Config.get_available_roles()),
                "active": len([r for r in Config.get_available_roles() if r.get_bot_token()])
            }
        }

    async def handle_interface_failure(self, interface_type: str, error: Exception) -> None:
        """
        Handle interface failure gracefully.

        Args:
            interface_type: Type of interface that failed
            error: The error that occurred
        """
        self.logger.error(f"❌ Interface {interface_type} failed: {error}")
        self.interfaces_status[interface_type] = "error"

        # Check if we still have any working interfaces
        active_interfaces = [
            iface for iface, status in self.interfaces_status.items()
            if status == "active"
        ]

        if not active_interfaces:
            self.logger.warning("⚠️ All interfaces failed, continuing in headless mode")
            self.operation_mode = OperationMode.HEADLESS
        else:
            self.logger.info(f"✅ Still have {len(active_interfaces)} active interfaces")


# Global application instance (singleton pattern)
_application_instance: Optional[NeuroCrewApplication] = None


def get_application() -> NeuroCrewApplication:
    """Get the global application instance."""
    global _application_instance
    if _application_instance is None:
        _application_instance = NeuroCrewApplication()
    return _application_instance