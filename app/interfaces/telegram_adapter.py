"""
Telegram interface adapter for NeuroCrew.

This module provides the Telegram adapter that implements the BaseInterface
contract for Telegram bot interactions, refactored from the original telegram_bot.py
to use the new interface abstraction layer.
"""

import asyncio
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackContext,
)
from telegram.ext import CallbackQueryHandler

from app.interfaces.base import (
    BaseInterface,
    MessageCapabilities,
    UserIdentity,
    ChatContext,
    Message,
    FormattedMessage,
    MessageType,
    InterfaceType,
    MessageFormatter,
    InterfaceEventHandler,
)
from app.config import Config, RoleConfig
from app.utils.formatters import (
    format_welcome_message,
    format_help_message,
    format_status_message,
    format_agent_response,
    split_long_message,
    format_telegram_message,
)
from app.utils.errors import (
    TelegramError,
    ConfigurationError,
    handle_errors,
    safe_execute
)
from app.utils.security import validate_input, sanitize_for_logging


class TelegramMessageFormatter(MessageFormatter):
    """Message formatter for Telegram interface."""

    async def format_text(self, content: str, **kwargs) -> FormattedMessage:
        """Format plain text for Telegram."""
        # Escape special characters for Telegram MarkdownV2
        escaped_content = format_telegram_message(content)

        return FormattedMessage(
            content=escaped_content,
            message_type=MessageType.TEXT,
            capabilities_used=self.capabilities,
            formatting_options={'parse_mode': 'MarkdownV2'}
        )

    async def format_markdown(self, content: str, **kwargs) -> FormattedMessage:
        """Format markdown for Telegram."""
        # Telegram supports MarkdownV2 format
        escaped_content = format_telegram_message(content)

        return FormattedMessage(
            content=escaped_content,
            message_type=MessageType.MARKDOWN,
            capabilities_used=self.capabilities,
            formatting_options={'parse_mode': 'MarkdownV2'}
        )

    async def format_html(self, content: str, **kwargs) -> FormattedMessage:
        """Format HTML for Telegram (converts to markdown)."""
        # Telegram prefers markdown over HTML, so convert
        escaped_content = format_telegram_message(content)

        return FormattedMessage(
            content=escaped_content,
            message_type=MessageType.TEXT,
            capabilities_used=self.capabilities,
            formatting_options={'parse_mode': 'MarkdownV2'}
        )

    async def format_agent_response(self, agent_name: str, content: str, **kwargs) -> List[FormattedMessage]:
        """Format agent response for Telegram with proper markdown."""
        # Use existing formatter for consistency
        safe_response = format_telegram_message(content)
        formatted_response = format_agent_response(agent_name, safe_response)

        # Split into multiple messages if needed
        messages = split_long_message(
            formatted_response,
            max_length=self.capabilities.max_message_length
        )

        formatted_messages = []
        for msg in messages:
            formatted_messages.append(FormattedMessage(
                content=msg,
                message_type=MessageType.MARKDOWN,
                capabilities_used=self.capabilities,
                formatting_options={'parse_mode': 'MarkdownV2'}
            ))

        return formatted_messages

    async def format_system_status(self, status_data: Dict[str, Any]) -> FormattedMessage:
        """Format system status for Telegram."""
        # Format status data into a readable message
        lines = ["🔍 **System Status**"]

        if 'total_chats' in status_data:
            lines.append(f"📊 Total chats: {status_data['total_chats']}")
        if 'total_messages' in status_data:
            lines.append(f"💬 Total messages: {status_data['total_messages']}")
        if 'storage_size_mb' in status_data:
            lines.append(f"💾 Storage size: {status_data['storage_size_mb']} MB")
        if 'available_agents' in status_data and 'configured_agents' in status_data:
            lines.append(f"🤖 Available agents: {status_data['available_agents']}/{status_data['configured_agents']}")

        content = "\n".join(lines)
        escaped_content = format_telegram_message(content)

        return FormattedMessage(
            content=escaped_content,
            message_type=MessageType.MARKDOWN,
            capabilities_used=self.capabilities,
            formatting_options={'parse_mode': 'MarkdownV2'}
        )


class TelegramAdapter(BaseInterface):
    """
    Telegram interface adapter implementing BaseInterface contract.

    This adapter handles Telegram-specific functionality while exposing
    a clean interface-agnostic API to the NeuroCrew system.
    """

    def __init__(self, interface_type: InterfaceType = InterfaceType.TELEGRAM):
        """Initialize the Telegram adapter."""
        super().__init__(interface_type)

        self.application: Optional[Application] = None
        self.bot_token: Optional[str] = None
        self._capabilities: Optional[MessageCapabilities] = None
        self.formatter: Optional[TelegramMessageFormatter] = None
        self.ncrew = None  # Will be injected by InterfaceManager

    @property
    def capabilities(self) -> MessageCapabilities:
        """Get Telegram interface capabilities."""
        if self._capabilities is None:
            self._capabilities = MessageCapabilities(
                supports_markdown=True,
                supports_html=False,  # Limited HTML support
                max_message_length=Config.TELEGRAM_MAX_MESSAGE_LENGTH,
                supports_files=True,
                supports_images=True,
                supports_audio=True,
                supports_video=True,
                supports_inline_buttons=True,
                supports_typing_indicators=True
            )
        return self._capabilities

    async def initialize(self) -> bool:
        """
        Initialize the Telegram adapter.

        Returns:
            bool: True if initialization successful
        """
        try:
            # Get bot token from configuration
            self.bot_token = safe_execute(
                lambda: Config.MAIN_BOT_TOKEN,
                logger=self.logger,
                context="telegram_initialization",
                error_message="❌ Не удалось получить токен Telegram бота"
            )

            if not self.bot_token:
                raise ConfigurationError("MAIN_BOT_TOKEN not configured")

            # Create Telegram application
            self.application = safe_execute(
                lambda: Application.builder().token(self.bot_token).build(),
                logger=self.logger,
                context="telegram_application_creation",
                error_message="❌ Не удалось создать Telegram приложение"
            )

            if not self.application:
                raise ConfigurationError("Failed to create Telegram application")

            # Initialize formatter
            self.formatter = TelegramMessageFormatter(self.capabilities)

            # Set up handlers
            await self._setup_handlers()
            self.application.post_shutdown = self._handle_application_shutdown

            self.logger.info("Telegram adapter initialized successfully")
            return True

        except Exception as e:
            self.logger.error(f"Failed to initialize Telegram adapter: {e}")
            await self._emit_interface_error(e)
            return False

    async def start(self) -> bool:
        """
        Start the Telegram adapter.

        Returns:
            bool: True if start successful
        """
        try:
            if not self.application:
                await self.initialize()

            # Start the Telegram application
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling(drop_pending_updates=True)

            self.is_running = True
            await self._emit_interface_ready()
            self.logger.info("Telegram adapter started successfully")
            return True

        except Exception as e:
            self.logger.error(f"Failed to start Telegram adapter: {e}")
            await self._emit_interface_error(e)
            return False

    async def stop(self) -> bool:
        """
        Stop the Telegram adapter gracefully.

        Returns:
            bool: True if stop successful
        """
        try:
            self.is_running = False

            if self.application:
                # Stop the application gracefully
                await self.application.updater.stop()
                await self.application.stop()
                await self.application.shutdown()

            await self._emit_interface_shutdown()
            self.logger.info("Telegram adapter stopped successfully")
            return True

        except Exception as e:
            self.logger.error(f"Error stopping Telegram adapter: {e}")
            return False

    async def send_message(self, chat_context: ChatContext, message: FormattedMessage) -> bool:
        """
        Send a message through Telegram interface.

        Args:
            chat_context: The chat context for routing
            message: The formatted message to send

        Returns:
            bool: True if message sent successfully
        """
        try:
            if not self.application or not self.is_running:
                self.logger.warning("Telegram adapter not running, cannot send message")
                return False

            # Extract chat_id from context
            chat_id = int(chat_context.chat_id)

            # Get formatting options
            formatting_options = message.formatting_options or {}
            parse_mode = formatting_options.get('parse_mode', 'MarkdownV2')

            # Send message through Telegram
            await self.application.bot.send_message(
                chat_id=chat_id,
                text=message.content,
                parse_mode=parse_mode
            )

            return True

        except Exception as e:
            self.logger.error(f"Failed to send Telegram message: {e}")
            return False

    async def send_typing_indicator(self, chat_context: ChatContext, is_typing: bool) -> bool:
        """
        Send or stop typing indicator in Telegram.

        Args:
            chat_context: The chat context
            is_typing: Whether to start or stop typing indicator

        Returns:
            bool: True if action successful
        """
        if not is_typing:
            # Telegram doesn't support "stop typing" - it times out automatically
            return True

        try:
            if not self.application or not self.is_running:
                return False

            chat_id = int(chat_context.chat_id)

            # Send typing action
            await self.application.bot.send_chat_action(
                chat_id=chat_id,
                action="typing"
            )
            return True

        except Exception as e:
            self.logger.error(f"Failed to send typing indicator: {e}")
            return False

    async def send_role_messages_via_actor(
        self, role_config: RoleConfig, messages: List[str], chat_id: str
    ) -> bool:
        """
        Attempt to send prepared messages via the role-specific Telegram bot.

        Args:
            role_config: Role configuration for which to send the message.
            messages: Pre-formatted messages ready for delivery.
            chat_id: Target chat ID.

        Returns:
            bool: True if delivery through the actor bot succeeded, False otherwise.
        """
        bot_lookup_name = role_config.telegram_bot_name
        agent_token = Config.TELEGRAM_BOT_TOKENS.get(bot_lookup_name)

        if not agent_token:
            return False

        actor_bot = Bot(token=agent_token)
        try:
            for msg in messages:
                await actor_bot.send_message(
                    chat_id=int(chat_id), text=msg, parse_mode="MarkdownV2"
                )
            return True
        except Exception as e:
            self.logger.error(f"Error sending via actor bot {bot_lookup_name}: {e}")
            return False

    def set_ncrew_instance(self, ncrew_instance) -> None:
        """
        Set the NeuroCrew instance for this adapter.

        Args:
            ncrew_instance: The NeuroCrew instance
        """
        self.ncrew = ncrew_instance

    async def _setup_handlers(self) -> None:
        """Set up Telegram command and message handlers."""
        if not self.application:
            return

        # Command handlers
        self.application.add_handler(CommandHandler("start", self._cmd_start))
        self.application.add_handler(CommandHandler("help", self._cmd_help))
        self.application.add_handler(CommandHandler("reset", self._cmd_reset))
        self.application.add_handler(CommandHandler("status", self._cmd_status))
        self.application.add_handler(CommandHandler("metrics", self._cmd_metrics))
        self.application.add_handler(CommandHandler("about", self._cmd_about))
        self.application.add_handler(CommandHandler("agents", self._cmd_agents))
        self.application.add_handler(CommandHandler("next", self._cmd_next_agent))

        # Message handlers
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message)
        )

        # Error handler
        self.application.add_error_handler(self._error_handler)

    def _is_target_chat(self, chat_id: int) -> bool:
        """Check if message is from the target chat."""
        if Config.TARGET_CHAT_ID == 0:
            return True
        return chat_id == Config.TARGET_CHAT_ID

    async def _cmd_start(self, update: Update, context: CallbackContext) -> None:
        """Handle /start command."""
        try:
            if not self._is_target_chat(update.effective_chat.id):
                return

            chat_context = self._create_chat_context(update)
            welcome_msg = format_welcome_message()
            formatted_message = await self.formatter.format_text(welcome_msg)
            await self.send_message(chat_context, formatted_message)

        except Exception as e:
            self.logger.error(f"Error in /start command: {e}")

    async def _cmd_help(self, update: Update, context: CallbackContext) -> None:
        """Handle /help command."""
        try:
            chat_context = self._create_chat_context(update)
            help_msg = format_help_message()
            formatted_message = await self.formatter.format_markdown(help_msg)
            await self.send_message(chat_context, formatted_message)

        except Exception as e:
            self.logger.error(f"Error in /help command: {e}")

    async def _cmd_reset(self, update: Update, context: CallbackContext) -> None:
        """Handle /reset command."""
        try:
            if not self._is_target_chat(update.effective_chat.id):
                return

            if not self.ncrew:
                return

            chat_context = self._create_chat_context(update)
            result = await self.ncrew.reset_conversation(chat_context.chat_id)
            formatted_message = await self.formatter.format_text(result)
            await self.send_message(chat_context, formatted_message)

        except Exception as e:
            self.logger.error(f"Error in /reset command: {e}")

    async def _cmd_status(self, update: Update, context: CallbackContext) -> None:
        """Handle /status command."""
        try:
            if not self.ncrew:
                return

            chat_context = self._create_chat_context(update)
            agent_status = await self.ncrew.get_agent_status()
            status_msg = format_status_message(agent_status)
            formatted_message = await self.formatter.format_markdown(status_msg)
            await self.send_message(chat_context, formatted_message)

        except Exception as e:
            self.logger.error(f"Error in /status command: {e}")

    async def _cmd_metrics(self, update: Update, context: CallbackContext) -> None:
        """Handle /metrics command."""
        try:
            if not self.ncrew:
                return

            chat_context = self._create_chat_context(update)
            metrics = self.ncrew.get_metrics()
            metrics_msg = f"""📊 **Performance Metrics**

🔄 **Agent Calls:** {metrics["total_agent_calls"]}
⏱️ **Total Response Time:** {metrics["total_response_time"]:.2f}s
📈 **Average Response Time:** {metrics["average_response_time"]:.2f}s
💬 **Conversations Processed:** {metrics["conversations_processed"]}
📝 **Messages Processed:** {metrics["messages_processed"]}"""

            formatted_message = await self.formatter.format_markdown(metrics_msg)
            await self.send_message(chat_context, formatted_message)

        except Exception as e:
            self.logger.error(f"Error in /metrics command: {e}")

    async def _cmd_about(self, update: Update, context: CallbackContext) -> None:
        """Handle /about command."""
        try:
            chat_context = self._create_chat_context(update)
            about_msg = (
                "🤖 **NeuroCrew Lab v0.1.0 MVP**\n\n"
                "A Telegram-based orchestration platform for multiple AI coding agents.\n\n"
                "**Features:**\n"
                "• Multi-agent orchestration\n"
                "• Context-aware conversations\n"
                "• File-based storage\n"
                "• Error handling\n\n"
                "**Supported Agents:**\n"
                "• Qwen Code ✅\n"
                "• Gemini CLI 🚧\n"
                "• Claude-Code 🚧\n\n"
                "_Currently in MVP development phase_"
            )
            formatted_message = await self.formatter.format_markdown(about_msg)
            await self.send_message(chat_context, formatted_message)

        except Exception as e:
            self.logger.error(f"Error in /about command: {e}")

    async def _cmd_agents(self, update: Update, context: CallbackContext) -> None:
        """Handle /agents command."""
        try:
            if not self.ncrew:
                return

            chat_context = self._create_chat_context(update)
            agent_info = await self.ncrew.get_chat_agent_info(chat_context.chat_id)

            if not agent_info:
                await self.send_message(chat_context, await self.formatter.format_text("❌ Unable to get agent information."))
                return

            # Format agent information
            lines = [f"🤖 **Agent Sequence for Your Chat**"]
            lines.append(f"📍 Current: {agent_info.get('current_agent', 'Unknown')}")
            lines.append(f"🔄 Position: {agent_info.get('agent_index', 0) + 1}/{agent_info.get('total_agents', 0)}")
            lines.append("")

            lines.append("**Next Agents:**")
            for i, agent in enumerate(agent_info.get("next_agents", [])[:3]):
                emoji = "✅" if agent["available"] else "❌"
                arrow = "→" if i == 0 else "⤷️"
                status = "Available" if agent["available"] else "Unavailable"
                lines.append(f"{emoji} {arrow} {agent['name']} ({status})")

            msg = "\n".join(lines)
            formatted_message = await self.formatter.format_markdown(msg)
            await self.send_message(chat_context, formatted_message)

        except Exception as e:
            self.logger.error(f"Error in /agents command: {e}")

    async def _cmd_next_agent(self, update: Update, context: CallbackContext) -> None:
        """Handle /next command to skip to next agent."""
        try:
            if not self.ncrew:
                return

            chat_context = self._create_chat_context(update)
            next_agent = await self.ncrew.skip_to_next_agent(chat_context.chat_id)

            if next_agent:
                agent_info = await self.ncrew.get_chat_agent_info(chat_context.chat_id)
                msg = f"🔄 **Switched to next agent:** {next_agent}"

                if agent_info:
                    msg += f"\n📍 **Sequence position:** {agent_info.get('agent_index', 0) + 1}/{agent_info.get('total_agents', 0)}"

                formatted_message = await self.formatter.format_markdown(msg)
                await self.send_message(chat_context, formatted_message)
            else:
                await self.send_message(chat_context, await self.formatter.format_text("❌ No agents available to switch to."))

        except Exception as e:
            self.logger.error(f"Error in /next command: {e}")

    async def _handle_message(self, update: Update, context: CallbackContext) -> None:
        """
        Handle incoming Telegram messages and route through interface abstraction.
        """
        try:
            # Check if this is from target chat
            if not self._is_target_chat(update.effective_chat.id):
                return

            # Create message objects for interface abstraction
            chat_context = self._create_chat_context(update)
            user_message = self._create_message(update, chat_context)

            # Validate input
            is_valid, error_msg = validate_input(user_message.content, "message")
            if not is_valid:
                self.logger.warning(f"Security check failed for message: {error_msg}")
                await self.send_message(chat_context, await self.formatter.format_text(
                    "❌ Your message contains potentially dangerous content and was rejected for security reasons."
                ))
                return

            # Log sanitized message
            sanitized_message = sanitize_for_logging(user_message.content)
            self.logger.info(f"Message from {user_message.sender.display_name}: {sanitized_message[:100]}...")

            # Emit message to event handler (InterfaceManager will route to NeuroCrew)
            await self._emit_message_received(user_message)

        except Exception as e:
            self.logger.error(f"Error handling message: {e}")

    def _create_chat_context(self, update: Update) -> ChatContext:
        """Create ChatContext from Telegram update."""
        user_identity = UserIdentity(
            user_id=str(update.effective_user.id),
            username=update.effective_user.username,
            display_name=update.effective_user.first_name or update.effective_user.username,
            interface_type=InterfaceType.TELEGRAM,
            chat_id=str(update.effective_chat.id)
        )

        return ChatContext(
            chat_id=str(update.effective_chat.id),
            interface_type=InterfaceType.TELEGRAM,
            user_identity=user_identity,
            metadata={
                'message_id': update.message.message_id if update.message else None,
                'chat_type': update.effective_chat.type if update.effective_chat else None
            }
        )

    def _create_message(self, update: Update, chat_context: ChatContext) -> Message:
        """Create Message from Telegram update."""
        return Message(
            content=update.message.text,
            message_type=MessageType.TEXT,
            sender=chat_context.user_identity,
            chat_context=chat_context,
            timestamp=datetime.now().isoformat(),
            metadata={
                'update_id': update.update_id,
                'message_id': update.message.message_id
            }
        )

    async def _error_handler(self, update: Optional[Update], context: CallbackContext) -> None:
        """Handle errors in the Telegram bot."""
        self.logger.error(f"Telegram bot error: {context.error}")

        try:
            if update and update.effective_chat:
                chat_context = self._create_chat_context(update)
                error_message = await self.formatter.format_text(
                    "❌ Sorry, an unexpected error occurred. Please try again later."
                )
                await self.send_message(chat_context, error_message)
        except Exception as e:
            self.logger.error(f"Error sending error message: {e}")

    async def _handle_application_shutdown(self, application: Application) -> None:
        """Telegram Application post-shutdown hook."""
        await self.stop()


# Register the Telegram adapter
from app.interfaces.base import interface_registry
interface_registry.register_interface(InterfaceType.TELEGRAM, TelegramAdapter)