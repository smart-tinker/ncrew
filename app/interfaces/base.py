"""
Interface abstraction layer for NeuroCrew.

This module provides the abstract base interface and related abstractions
for supporting multiple interaction channels (Telegram, Web, etc.) with
clean separation of concerns and pluggable architecture.
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Union, AsyncGenerator
from dataclasses import dataclass
from enum import Enum
import logging

from app.config import RoleConfig


class InterfaceType(Enum):
    """Enumeration of supported interface types."""
    TELEGRAM = "telegram"
    WEB = "web"


class MessageType(Enum):
    """Enumeration of message types supported by interfaces."""
    TEXT = "text"
    MARKDOWN = "markdown"
    HTML = "html"
    FILE = "file"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    SYSTEM = "system"


@dataclass
class MessageCapabilities:
    """Describes the capabilities of an interface for message formatting."""
    supports_markdown: bool = False
    supports_html: bool = False
    max_message_length: int = 4096
    supports_files: bool = False
    supports_images: bool = False
    supports_audio: bool = False
    supports_video: bool = False
    supports_inline_buttons: bool = False
    supports_typing_indicators: bool = False


@dataclass
class UserIdentity:
    """Represents a user identity across different interfaces."""
    user_id: str
    username: Optional[str] = None
    display_name: Optional[str] = None
    interface_type: Optional[InterfaceType] = None
    chat_id: Optional[str] = None


@dataclass
class ChatContext:
    """Represents a conversation context for routing messages."""
    chat_id: str
    interface_type: InterfaceType
    user_identity: UserIdentity
    metadata: Dict[str, Any] = None


@dataclass
class Message:
    """Represents a message flowing through the interface abstraction layer."""
    content: str
    message_type: MessageType
    sender: UserIdentity
    chat_context: ChatContext
    timestamp: str
    metadata: Dict[str, Any] = None


@dataclass
class FormattedMessage:
    """Represents a formatted message ready for delivery to a specific interface."""
    content: str
    message_type: MessageType
    capabilities_used: MessageCapabilities
    formatting_options: Dict[str, Any] = None
    metadata: Dict[str, Any] = None


class InterfaceEventHandler(ABC):
    """Abstract event handler for interface events."""

    @abstractmethod
    async def on_message_received(self, message: Message) -> None:
        """Handle incoming message from interface."""
        pass

    @abstractmethod
    async def on_interface_ready(self, interface_type: InterfaceType) -> None:
        """Handle interface ready event."""
        pass

    @abstractmethod
    async def on_interface_error(self, interface_type: InterfaceType, error: Exception) -> None:
        """Handle interface error event."""
        pass

    @abstractmethod
    async def on_interface_shutdown(self, interface_type: InterfaceType) -> None:
        """Handle interface shutdown event."""
        pass


class BaseInterface(ABC):
    """
    Abstract base interface for all interaction channels.

    This defines the common contract that all interfaces must implement
    to plug into the NeuroCrew system. Interfaces are independent,
    pluggable, and interface-agnostic.
    """

    def __init__(self, interface_type: InterfaceType):
        """
        Initialize the base interface.

        Args:
            interface_type: The type of this interface
        """
        self.interface_type = interface_type
        self.logger = logging.getLogger(f"{self.__class__.__name__}")
        self.event_handler: Optional[InterfaceEventHandler] = None
        self.is_running = False
        self._capabilities: Optional[MessageCapabilities] = None

    @property
    @abstractmethod
    def capabilities(self) -> MessageCapabilities:
        """Get the message capabilities of this interface."""
        pass

    @abstractmethod
    async def initialize(self) -> bool:
        """
        Initialize the interface.

        Returns:
            bool: True if initialization successful
        """
        pass

    @abstractmethod
    async def start(self) -> bool:
        """
        Start the interface and begin listening for messages.

        Returns:
            bool: True if start successful
        """
        pass

    @abstractmethod
    async def stop(self) -> bool:
        """
        Stop the interface gracefully.

        Returns:
            bool: True if stop successful
        """
        pass

    @abstractmethod
    async def send_message(self, chat_context: ChatContext, message: FormattedMessage) -> bool:
        """
        Send a message through this interface.

        Args:
            chat_context: The chat context for routing
            message: The formatted message to send

        Returns:
            bool: True if message sent successfully
        """
        pass

    @abstractmethod
    async def send_typing_indicator(self, chat_context: ChatContext, is_typing: bool) -> bool:
        """
        Send or stop typing indicator.

        Args:
            chat_context: The chat context
            is_typing: Whether to start or stop typing indicator

        Returns:
            bool: True if action successful
        """
        pass

    async def send_system_message(self, chat_context: ChatContext, content: str) -> bool:
        """
        Send a system message (convenience method).

        Args:
            chat_context: The chat context
            content: The system message content

        Returns:
            bool: True if message sent successfully
        """
        message = FormattedMessage(
            content=content,
            message_type=MessageType.SYSTEM,
            capabilities_used=self.capabilities
        )
        return await self.send_message(chat_context, message)

    def set_event_handler(self, handler: InterfaceEventHandler) -> None:
        """
        Set the event handler for interface events.

        Args:
            handler: The event handler instance
        """
        self.event_handler = handler

    async def _emit_message_received(self, message: Message) -> None:
        """Emit message received event to handler."""
        if self.event_handler:
            try:
                await self.event_handler.on_message_received(message)
            except Exception as e:
                self.logger.error(f"Error in event handler for message received: {e}")

    async def _emit_interface_ready(self) -> None:
        """Emit interface ready event to handler."""
        if self.event_handler:
            try:
                await self.event_handler.on_interface_ready(self.interface_type)
            except Exception as e:
                self.logger.error(f"Error in event handler for interface ready: {e}")

    async def _emit_interface_error(self, error: Exception) -> None:
        """Emit interface error event to handler."""
        if self.event_handler:
            try:
                await self.event_handler.on_interface_error(self.interface_type, error)
            except Exception as e:
                self.logger.error(f"Error in event handler for interface error: {e}")

    async def _emit_interface_shutdown(self) -> None:
        """Emit interface shutdown event to handler."""
        if self.event_handler:
            try:
                await self.event_handler.on_interface_shutdown(self.interface_type)
            except Exception as e:
                self.logger.error(f"Error in event handler for interface shutdown: {e}")


class MessageFormatter(ABC):
    """
    Abstract message formatter for different interface capabilities.

    Each interface implementation should provide a concrete formatter
    that handles the specific formatting requirements of that interface.
    """

    def __init__(self, capabilities: MessageCapabilities):
        """
        Initialize the formatter.

        Args:
            capabilities: The interface capabilities
        """
        self.capabilities = capabilities

    @abstractmethod
    async def format_text(self, content: str, **kwargs) -> FormattedMessage:
        """
        Format plain text content.

        Args:
            content: The text content to format
            **kwargs: Additional formatting options

        Returns:
            FormattedMessage: The formatted message
        """
        pass

    @abstractmethod
    async def format_markdown(self, content: str, **kwargs) -> FormattedMessage:
        """
        Format markdown content.

        Args:
            content: The markdown content to format
            **kwargs: Additional formatting options

        Returns:
            FormattedMessage: The formatted message
        """
        pass

    @abstractmethod
    async def format_html(self, content: str, **kwargs) -> FormattedMessage:
        """
        Format HTML content.

        Args:
            content: The HTML content to format
            **kwargs: Additional formatting options

        Returns:
            FormattedMessage: The formatted message
        """
        pass

    @abstractmethod
    async def format_agent_response(self, agent_name: str, content: str, **kwargs) -> List[FormattedMessage]:
        """
        Format an agent response for delivery.

        Args:
            agent_name: The name of the agent
            content: The agent response content
            **kwargs: Additional formatting options

        Returns:
            List[FormattedMessage]: List of formatted messages (may be split for length limits)
        """
        pass

    @abstractmethod
    async def format_system_status(self, status_data: Dict[str, Any]) -> FormattedMessage:
        """
        Format system status information.

        Args:
            status_data: System status data

        Returns:
            FormattedMessage: The formatted status message
        """
        pass


class InterfaceRegistry:
    """
    Registry for managing available interface types and their implementations.
    """

    def __init__(self):
        """Initialize the registry."""
        self.interfaces: Dict[InterfaceType, type] = {}
        self.logger = logging.getLogger(f"{self.__class__.__name__}")

    def register_interface(self, interface_type: InterfaceType, interface_class: type) -> None:
        """
        Register an interface implementation.

        Args:
            interface_type: The interface type
            interface_class: The interface implementation class
        """
        if not issubclass(interface_class, BaseInterface):
            raise ValueError(f"Interface class must inherit from BaseInterface")

        self.interfaces[interface_type] = interface_class
        self.logger.info(f"Registered interface {interface_type.value}: {interface_class.__name__}")

    def get_interface_class(self, interface_type: InterfaceType) -> Optional[type]:
        """
        Get the interface class for a type.

        Args:
            interface_type: The interface type

        Returns:
            Optional[type]: The interface class or None if not registered
        """
        return self.interfaces.get(interface_type)

    def list_registered_interfaces(self) -> List[InterfaceType]:
        """
        List all registered interface types.

        Returns:
            List[InterfaceType]: List of registered interface types
        """
        return list(self.interfaces.keys())

    def create_interface(self, interface_type: InterfaceType, **kwargs) -> Optional[BaseInterface]:
        """
        Create an interface instance.

        Args:
            interface_type: The interface type to create
            **kwargs: Additional arguments for interface constructor

        Returns:
            Optional[BaseInterface]: The interface instance or None if type not registered
        """
        interface_class = self.get_interface_class(interface_type)
        if not interface_class:
            return None

        try:
            return interface_class(interface_type, **kwargs)
        except Exception as e:
            self.logger.error(f"Failed to create interface {interface_type.value}: {e}")
            return None


# Global registry instance
interface_registry = InterfaceRegistry()