"""
Interface Manager for NeuroCrew.

This module provides the central coordination point for all interfaces,
handling message routing, lifecycle management, and interface-agnostic
operations.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Set, Any, Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from app.interfaces.base import (
    BaseInterface,
    InterfaceType,
    MessageCapabilities,
    UserIdentity,
    ChatContext,
    Message,
    FormattedMessage,
    MessageType,
    InterfaceEventHandler,
    interface_registry,
)
from app.config import Config, RoleConfig
from app.utils.logger import get_logger


class InterfaceStatus(Enum):
    """Enumeration of interface statuses."""
    INACTIVE = "inactive"
    INITIALIZING = "initializing"
    ACTIVE = "active"
    ERROR = "error"
    STOPPING = "stopping"


@dataclass
class InterfaceInfo:
    """Information about an interface instance."""
    interface: BaseInterface
    status: InterfaceStatus
    capabilities: MessageCapabilities
    last_activity: Optional[datetime] = None
    error_count: int = 0
    message_count: int = 0
    metadata: Dict[str, Any] = None


class InterfaceManager(InterfaceEventHandler):
    """
    Central manager for coordinating multiple interfaces.

    This class handles:
    - Interface lifecycle management
    - Message routing between interfaces and NeuroCrew
    - Interface health monitoring
    - Graceful startup and shutdown
    - Interface-agnostic operations
    """

    def __init__(self, ncrew_instance=None):
        """
        Initialize the InterfaceManager.

        Args:
            ncrew_instance: The NeuroCrew instance to connect to
        """
        self.logger = get_logger(f"{self.__class__.__name__}")
        self.ncrew = ncrew_instance

        # Interface management
        self.interfaces: Dict[InterfaceType, InterfaceInfo] = {}
        self.active_interfaces: Set[InterfaceType] = set()
        self.configured_interfaces: Set[InterfaceType] = set()

        # Message routing
        self.message_handlers: List[Callable] = []
        self.chat_contexts: Dict[str, ChatContext] = {}  # chat_id -> ChatContext

        # State management
        self.is_running = False
        self.startup_time: Optional[datetime] = None

        # Load configuration
        self._load_configuration()

        self.logger.info("InterfaceManager initialized")

    def _load_configuration(self) -> None:
        """Load interface configuration from Config."""
        try:
            # Determine which interfaces are configured
            if Config.MAIN_BOT_TOKEN:
                self.configured_interfaces.add(InterfaceType.TELEGRAM)
                self.logger.info("Telegram interface configured")

            # Web interface is always available if enabled
            if hasattr(Config, 'WEB_INTERFACE_ENABLED') and Config.WEB_INTERFACE_ENABLED:
                self.configured_interfaces.add(InterfaceType.WEB)
                self.logger.info("Web interface configured")

            self.logger.info(f"Configured interfaces: {[it.value for it in self.configured_interfaces]}")

        except Exception as e:
            self.logger.error(f"Error loading interface configuration: {e}")

    async def initialize(self) -> bool:
        """
        Initialize all configured interfaces.

        Returns:
            bool: True if initialization successful
        """
        try:
            self.logger.info("Initializing InterfaceManager...")
            self.startup_time = datetime.now()

            # Initialize each configured interface
            for interface_type in self.configured_interfaces:
                await self._initialize_interface(interface_type)

            # Inject NeuroCrew instance into interfaces
            if self.ncrew:
                await self._inject_ncrew_into_interfaces()

            self.logger.info(f"InterfaceManager initialized with {len(self.active_interfaces)} active interfaces")
            return True

        except Exception as e:
            self.logger.error(f"Failed to initialize InterfaceManager: {e}")
            return False

    async def start(self) -> bool:
        """
        Start all initialized interfaces.

        Returns:
            bool: True if start successful
        """
        try:
            self.logger.info("Starting InterfaceManager...")
            self.is_running = True

            # Start each interface
            startup_tasks = []
            for interface_type in list(self.active_interfaces):
                startup_tasks.append(self._start_interface(interface_type))

            # Wait for all interfaces to start
            if startup_tasks:
                results = await asyncio.gather(*startup_tasks, return_exceptions=True)
                successful_starts = sum(1 for r in results if r is True)
                self.logger.info(f"Started {successful_starts}/{len(startup_tasks)} interfaces")

            # Perform role introductions if any interface is active
            if self.active_interfaces and self.ncrew:
                await self._perform_startup_introductions()

            self.logger.info("InterfaceManager started successfully")
            return True

        except Exception as e:
            self.logger.error(f"Failed to start InterfaceManager: {e}")
            return False

    async def stop(self) -> bool:
        """
        Stop all interfaces gracefully.

        Returns:
            bool: True if stop successful
        """
        try:
            self.logger.info("Stopping InterfaceManager...")
            self.is_running = False

            # Stop each interface
            stop_tasks = []
            for interface_type in list(self.active_interfaces):
                stop_tasks.append(self._stop_interface(interface_type))

            # Wait for all interfaces to stop
            if stop_tasks:
                results = await asyncio.gather(*stop_tasks, return_exceptions=True)
                successful_stops = sum(1 for r in results if r is True)
                self.logger.info(f"Stopped {successful_stops}/{len(stop_tasks)} interfaces")

            self.active_interfaces.clear()
            self.logger.info("InterfaceManager stopped successfully")
            return True

        except Exception as e:
            self.logger.error(f"Error stopping InterfaceManager: {e}")
            return False

    async def add_interface(self, interface_type: InterfaceType, **kwargs) -> bool:
        """
        Add and initialize a new interface.

        Args:
            interface_type: The type of interface to add
            **kwargs: Additional arguments for interface creation

        Returns:
            bool: True if interface added successfully
        """
        try:
            if interface_type in self.interfaces:
                self.logger.warning(f"Interface {interface_type.value} already exists")
                return False

            # Create interface instance
            interface = interface_registry.create_interface(interface_type, **kwargs)
            if not interface:
                self.logger.error(f"Failed to create interface {interface_type.value}")
                return False

            # Initialize interface
            await self._initialize_interface_instance(interface_type, interface)

            self.logger.info(f"Added interface {interface_type.value}")
            return True

        except Exception as e:
            self.logger.error(f"Error adding interface {interface_type.value}: {e}")
            return False

    async def remove_interface(self, interface_type: InterfaceType) -> bool:
        """
        Remove and stop an interface.

        Args:
            interface_type: The type of interface to remove

        Returns:
            bool: True if interface removed successfully
        """
        try:
            if interface_type not in self.interfaces:
                self.logger.warning(f"Interface {interface_type.value} not found")
                return False

            # Stop interface
            await self._stop_interface(interface_type)

            # Remove from tracking
            del self.interfaces[interface_type]
            self.active_interfaces.discard(interface_type)
            self.configured_interfaces.discard(interface_type)

            self.logger.info(f"Removed interface {interface_type.value}")
            return True

        except Exception as e:
            self.logger.error(f"Error removing interface {interface_type.value}: {e}")
            return False

    async def send_message_to_all_interfaces(self, message: str, message_type: MessageType = MessageType.TEXT) -> bool:
        """
        Send a message to all active interfaces.

        Args:
            message: The message content to send
            message_type: The type of message

        Returns:
            bool: True if message sent to at least one interface
        """
        try:
            success_count = 0

            for interface_type, interface_info in self.interfaces.items():
                if interface_info.status != InterfaceStatus.ACTIVE:
                    continue

                # Create chat context (using default/system chat)
                chat_context = ChatContext(
                    chat_id="system",
                    interface_type=interface_type,
                    user_identity=UserIdentity(
                        user_id="system",
                        display_name="NeuroCrew System",
                        interface_type=interface_type
                    )
                )

                # Create formatted message
                formatted_message = FormattedMessage(
                    content=message,
                    message_type=message_type,
                    capabilities_used=interface_info.capabilities
                )

                # Send message
                if await interface_info.interface.send_message(chat_context, formatted_message):
                    success_count += 1
                    interface_info.message_count += 1
                    interface_info.last_activity = datetime.now()

            self.logger.info(f"Sent message to {success_count}/{len(self.active_interfaces)} interfaces")
            return success_count > 0

        except Exception as e:
            self.logger.error(f"Error sending message to all interfaces: {e}")
            return False

    async def send_typing_indicator(self, chat_id: str, is_typing: bool) -> None:
        """
        Send typing indicator to relevant interfaces for a chat.

        Args:
            chat_id: The chat ID
            is_typing: Whether to start or stop typing
        """
        try:
            for interface_type, interface_info in self.interfaces.items():
                if interface_info.status != InterfaceStatus.ACTIVE:
                    continue

                # Find chat context for this interface
                chat_context = self._find_chat_context_for_interface(chat_id, interface_type)
                if chat_context:
                    await interface_info.interface.send_typing_indicator(chat_context, is_typing)

        except Exception as e:
            self.logger.error(f"Error sending typing indicator: {e}")

    def get_interface_status(self) -> Dict[str, Dict[str, Any]]:
        """
        Get status information for all interfaces.

        Returns:
            Dict: Status information for each interface
        """
        status = {}
        for interface_type, interface_info in self.interfaces.items():
            status[interface_type.value] = {
                'status': interface_info.status.value,
                'capabilities': {
                    'supports_markdown': interface_info.capabilities.supports_markdown,
                    'supports_html': interface_info.capabilities.supports_html,
                    'max_message_length': interface_info.capabilities.max_message_length,
                    'supports_files': interface_info.capabilities.supports_files,
                    'supports_images': interface_info.capabilities.supports_images,
                    'supports_inline_buttons': interface_info.capabilities.supports_inline_buttons,
                    'supports_typing_indicators': interface_info.capabilities.supports_typing_indicators,
                },
                'last_activity': interface_info.last_activity.isoformat() if interface_info.last_activity else None,
                'error_count': interface_info.error_count,
                'message_count': interface_info.message_count,
                'uptime_seconds': (datetime.now() - self.startup_time).total_seconds() if self.startup_time else 0
            }

        return status

    async def restart_interface(self, interface_type: InterfaceType) -> bool:
        """
        Restart a specific interface.

        Args:
            interface_type: The interface type to restart

        Returns:
            bool: True if restart successful
        """
        try:
            self.logger.info(f"Restarting interface {interface_type.value}...")

            if interface_type not in self.interfaces:
                self.logger.error(f"Interface {interface_type.value} not found")
                return False

            # Stop interface
            await self._stop_interface(interface_type)

            # Wait a moment
            await asyncio.sleep(2)

            # Start interface
            success = await self._start_interface(interface_type)

            self.logger.info(f"Interface {interface_type.value} restart {'successful' if success else 'failed'}")
            return success

        except Exception as e:
            self.logger.error(f"Error restarting interface {interface_type.value}: {e}")
            return False

    # InterfaceEventHandler implementation

    async def on_message_received(self, message: Message) -> None:
        """Handle incoming message from any interface."""
        try:
            self.logger.debug(f"Received message from {message.chat_context.interface_type.value}: {message.content[:100]}...")

            # Update interface activity
            interface_type = message.chat_context.interface_type
            if interface_type in self.interfaces:
                self.interfaces[interface_type].last_activity = datetime.now()
                self.interfaces[interface_type].message_count += 1

            # Store chat context
            self.chat_contexts[message.chat_context.chat_id] = message.chat_context

            # Route message to NeuroCrew if available
            if self.ncrew:
                await self._route_message_to_ncrew(message)
            else:
                self.logger.warning("NeuroCrew instance not available, cannot process message")

        except Exception as e:
            self.logger.error(f"Error handling received message: {e}")

    async def on_interface_ready(self, interface_type: InterfaceType) -> None:
        """Handle interface ready event."""
        if interface_type in self.interfaces:
            self.interfaces[interface_type].status = InterfaceStatus.ACTIVE
            self.active_interfaces.add(interface_type)

        self.logger.info(f"Interface {interface_type.value} is ready")

    async def on_interface_error(self, interface_type: InterfaceType, error: Exception) -> None:
        """Handle interface error event."""
        if interface_type in self.interfaces:
            self.interfaces[interface_type].status = InterfaceStatus.ERROR
            self.interfaces[interface_type].error_count += 1

        self.logger.error(f"Interface {interface_type.value} error: {error}")

    async def on_interface_shutdown(self, interface_type: InterfaceType) -> None:
        """Handle interface shutdown event."""
        if interface_type in self.interfaces:
            self.interfaces[interface_type].status = InterfaceStatus.INACTIVE

        self.active_interfaces.discard(interface_type)
        self.logger.info(f"Interface {interface_type.value} shutdown")

    # Private methods

    async def _initialize_interface(self, interface_type: InterfaceType) -> bool:
        """Initialize a specific interface type."""
        try:
            # Create interface instance
            interface = interface_registry.create_interface(interface_type)
            if not interface:
                self.logger.error(f"Failed to create interface {interface_type.value}")
                return False

            return await self._initialize_interface_instance(interface_type, interface)

        except Exception as e:
            self.logger.error(f"Error initializing interface {interface_type.value}: {e}")
            return False

    async def _initialize_interface_instance(self, interface_type: InterfaceType, interface: BaseInterface) -> bool:
        """Initialize an interface instance."""
        try:
            # Set this manager as event handler
            interface.set_event_handler(self)

            # Initialize interface
            if not await interface.initialize():
                self.logger.error(f"Failed to initialize interface {interface_type.value}")
                return False

            # Track interface
            self.interfaces[interface_type] = InterfaceInfo(
                interface=interface,
                status=InterfaceStatus.INITIALIZING,
                capabilities=interface.capabilities,
                metadata={}
            )

            self.logger.info(f"Interface {interface_type.value} initialized")
            return True

        except Exception as e:
            self.logger.error(f"Error initializing interface instance {interface_type.value}: {e}")
            return False

    async def _inject_ncrew_into_interfaces(self) -> None:
        """Inject NeuroCrew instance into all interfaces that support it."""
        for interface_type, interface_info in self.interfaces.items():
            if hasattr(interface_info.interface, 'set_ncrew_instance'):
                interface_info.interface.set_ncrew_instance(self.ncrew)
                self.logger.debug(f"Injected NeuroCrew into {interface_type.value} interface")

    async def _start_interface(self, interface_type: InterfaceType) -> bool:
        """Start a specific interface."""
        try:
            if interface_type not in self.interfaces:
                self.logger.error(f"Interface {interface_type.value} not found")
                return False

            interface_info = self.interfaces[interface_type]
            interface_info.status = InterfaceStatus.INITIALIZING

            # Start interface
            if await interface_info.interface.start():
                interface_info.status = InterfaceStatus.ACTIVE
                self.active_interfaces.add(interface_type)
                self.logger.info(f"Interface {interface_type.value} started")
                return True
            else:
                interface_info.status = InterfaceStatus.ERROR
                self.logger.error(f"Failed to start interface {interface_type.value}")
                return False

        except Exception as e:
            self.logger.error(f"Error starting interface {interface_type.value}: {e}")
            if interface_type in self.interfaces:
                self.interfaces[interface_type].status = InterfaceStatus.ERROR
            return False

    async def _stop_interface(self, interface_type: InterfaceType) -> bool:
        """Stop a specific interface."""
        try:
            if interface_type not in self.interfaces:
                return True  # Interface doesn't exist, consider it stopped

            interface_info = self.interfaces[interface_type]
            interface_info.status = InterfaceStatus.STOPPING

            # Stop interface
            success = await interface_info.interface.stop()

            interface_info.status = InterfaceStatus.INACTIVE
            self.active_interfaces.discard(interface_type)

            self.logger.info(f"Interface {interface_type.value} stopped")
            return success

        except Exception as e:
            self.logger.error(f"Error stopping interface {interface_type.value}: {e}")
            return False

    async def _perform_startup_introductions(self) -> None:
        """Perform startup introductions through available interfaces."""
        try:
            self.logger.info("Performing startup introductions through interfaces...")

            if not self.ncrew:
                return

            # Send startup notification
            startup_msg = "🚀 NeuroCrew Lab запускается — сбор команды и инициализация агентов."
            await self.send_message_to_all_interfaces(startup_msg, MessageType.TEXT)

            # Stream introductions from NeuroCrew
            async for role_config, intro_text in self.ncrew.perform_startup_introductions():
                # Send typing indicator
                for interface_type in self.active_interfaces:
                    await self.send_typing_indicator(str(Config.TARGET_CHAT_ID), True)

                # Format and send introduction
                for interface_type, interface_info in self.interfaces.items():
                    if interface_info.status != InterfaceStatus.ACTIVE:
                        continue

                    try:
                        # Use interface's formatter
                        formatted_messages = await interface_info.interface.formatter.format_agent_response(
                            role_config.display_name, intro_text
                        )

                        chat_context = ChatContext(
                            chat_id=str(Config.TARGET_CHAT_ID),
                            interface_type=interface_type,
                            user_identity=UserIdentity(
                                user_id="system",
                                display_name="NeuroCrew System",
                                interface_type=interface_type
                            )
                        )

                        for formatted_msg in formatted_messages:
                            await interface_info.interface.send_message(chat_context, formatted_msg)

                    except Exception as e:
                        self.logger.error(f"Error sending introduction via {interface_type.value}: {e}")

                await asyncio.sleep(1.0)  # Pause between agents

            # Send ready message
            ready_msg = "💬 Команда в сборе и готова к работе. Жду ваших указаний."
            await self.send_message_to_all_interfaces(ready_msg, MessageType.TEXT)

            self.logger.info("Startup introductions completed")

        except Exception as e:
            self.logger.error(f"Error during startup introductions: {e}")

    async def _route_message_to_ncrew(self, message: Message) -> None:
        """Route message to NeuroCrew for processing."""
        try:
            chat_id = message.chat_context.chat_id
            user_text = message.content

            # Process message through NeuroCrew
            async for role_config, raw_response in self.ncrew.handle_message(chat_id, user_text):
                if role_config and raw_response:
                    # Send response to all active interfaces for this chat
                    await self._send_agent_response_to_interfaces(
                        role_config, raw_response, chat_id
                    )

                    # Pause between agents
                    await asyncio.sleep(1.5)

            # Send completion message
            completion_msg = "💬 Команда завершила свою работу. Жду ваших дальнейших указаний."
            await self.send_message_to_all_interfaces(completion_msg, MessageType.TEXT)

        except Exception as e:
            self.logger.error(f"Error routing message to NeuroCrew: {e}")

    async def _send_agent_response_to_interfaces(self, role_config: RoleConfig, response: str, chat_id: str) -> None:
        """Send agent response to all active interfaces."""
        for interface_type, interface_info in self.interfaces.items():
            if interface_info.status != InterfaceStatus.ACTIVE:
                continue

            try:
                # Use interface's formatter for agent responses
                formatted_messages = await interface_info.interface.formatter.format_agent_response(
                    role_config.display_name, response
                )

                chat_context = ChatContext(
                    chat_id=chat_id,
                    interface_type=interface_type,
                    user_identity=UserIdentity(
                        user_id="agent",
                        display_name=role_config.display_name,
                        interface_type=interface_type
                    )
                )

                for formatted_msg in formatted_messages:
                    await interface_info.interface.send_message(chat_context, formatted_msg)

            except Exception as e:
                self.logger.error(f"Error sending agent response via {interface_type.value}: {e}")

    def _find_chat_context_for_interface(self, chat_id: str, interface_type: InterfaceType) -> Optional[ChatContext]:
        """Find chat context for a specific interface and chat ID."""
        # Look for existing context
        key = f"{interface_type.value}:{chat_id}"
        if chat_id in self.chat_contexts:
            context = self.chat_contexts[chat_id]
            if context.interface_type == interface_type:
                return context

        # Create new context if needed
        return ChatContext(
            chat_id=chat_id,
            interface_type=interface_type,
            user_identity=UserIdentity(
                user_id="web_user",
                display_name="Web User",
                interface_type=interface_type,
                chat_id=chat_id
            )
        )