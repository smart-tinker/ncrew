"""
Telegram bot interface for NeuroCrew Lab.

This module provides the Telegram bot interface for user interaction
with the NeuroCrew Lab system.
"""

import asyncio
import logging
from typing import List, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackContext,
)
from telegram.ext import CallbackQueryHandler

from app.config import Config, RoleConfig
from app.core.engine import NeuroCrewLab
from app.utils.logger import setup_logger
from app.utils.errors import (
    TelegramError,
    ConfigurationError,
    handle_errors,
    safe_execute
)
from app.utils.formatters import (
    format_welcome_message,
    format_help_message,
    format_status_message,
    format_agent_response,
    split_long_message,
    format_telegram_message,
)
from app.utils.security import validate_input, sanitize_for_logging


class TelegramBot:
    """
    Telegram bot interface for NeuroCrew Lab.

    Handles user interactions through Telegram commands and messages.
    """

    def __init__(self):
        """Initialize the Telegram bot."""
        self.logger = setup_logger(f"{self.__class__.__name__}", Config.LOG_LEVEL)
        self.ncrew = None  # Will be initialized asynchronously

        # Initialize application with main listener bot token
        bot_token = safe_execute(
            lambda: Config.MAIN_BOT_TOKEN,
            logger=self.logger,
            context="telegram_initialization",
            error_message="❌ Не удалось получить токен Telegram бота"
        )

        if not bot_token:
            raise ConfigurationError("MAIN_BOT_TOKEN not configured")

        # Create application directly using system settings
        self.application = safe_execute(
            lambda: Application.builder().token(bot_token).build(),
            logger=self.logger,
            context="telegram_application_creation",
            error_message="❌ Не удалось создать Telegram приложение"
        )

        if not self.application:
            raise ConfigurationError("Failed to create Telegram application")

        self.logger.info(
            "Telegram application created successfully with main listener bot"
        )

        # Set up handlers
        safe_execute(
            lambda: self._setup_handlers(),
            logger=self.logger,
            context="telegram_handlers_setup",
            error_message="❌ Не удалось настроить обработчики Telegram"
        )

        self.application.post_shutdown = self._handle_application_shutdown
        self.logger.info("Telegram bot initialized successfully")

    @handle_errors(
        logger=None,  # будет использоваться self.logger
        context="ncrew_initialization",
        return_on_error=None
    )
    async def _ensure_ncrew_initialized(self):
        """Ensure NeuroCrew Lab is initialized."""
        if self.ncrew is None:
            self.logger.info("Initializing NeuroCrew Lab...")
            self.ncrew = NeuroCrewLab()
            await self.ncrew.initialize()
            self.logger.info("NeuroCrew Lab initialized successfully")

    async def run_startup_introductions(self):
        """Triggers the agent introduction sequence at startup."""
        self.logger.debug("Starting agent introduction sequence")
        await self._ensure_ncrew_initialized()

        if Config.TARGET_CHAT_ID:
            self.logger.debug(f"Sending startup message to {Config.TARGET_CHAT_ID}")
            try:
                # Avoid bold/ellipsis to keep MarkdownV2 parsing simple
                startup_msg = (
                    "🚀 NeuroCrew Lab запускается — сбор команды и инициализация агентов."
                )
                formatted_startup = format_telegram_message(startup_msg)
                await self.application.bot.send_message(
                    chat_id=Config.TARGET_CHAT_ID,
                    text=formatted_startup,
                    parse_mode="MarkdownV2",
                )
                self.logger.debug("Startup message sent")
            except Exception as e:
                self.logger.error(f"Failed to send startup message: {e}")

        try:
            self.logger.debug("Starting streaming introductions loop")
            # Iterate over the async generator to stream introductions
            async for (
                role_config,
                intro_text,
            ) in self.ncrew.perform_startup_introductions():
                self.logger.debug(f"Got introduction from {role_config.role_name}")

                # Send "typing" action while processing
                if Config.TARGET_CHAT_ID:
                    try:
                        await self.application.bot.send_chat_action(
                            chat_id=Config.TARGET_CHAT_ID, action="typing"
                        )
                    except Exception as e:
                        self.logger.debug(f"Failed to send typing action: {e}")

                # Escape introduction text
                safe_intro = format_telegram_message(intro_text)
                formatted_intro = format_agent_response(
                    role_config.display_name, safe_intro
                )
                messages_to_send = split_long_message(
                    formatted_intro, max_length=Config.TELEGRAM_MAX_MESSAGE_LENGTH
                )

                self.logger.debug(f"Sending intro for {role_config.role_name}")
                sent_via_actor = await self._send_role_messages_via_actor(
                    role_config, messages_to_send
                )
                if not sent_via_actor:
                    self.logger.warning(
                        "Failed to send introduction via actor bot for role %s. Falling back to coordinator bot.",
                        role_config.role_name,
                    )
                    for chunk in messages_to_send:
                        # chunk is already formatted and escaped
                        await self.application.bot.send_message(
                            chat_id=Config.TARGET_CHAT_ID,
                            text=chunk,
                            parse_mode="MarkdownV2",
                        )
                self.logger.debug(f"Intro sent for {role_config.role_name}")

                await asyncio.sleep(1.0)  # Short pause between agents

        except Exception as intro_error:
            self.logger.error(f"Failed during startup introductions: {intro_error}")
            return

        self.logger.debug("Introductions loop finished")

        if Config.TARGET_CHAT_ID:
            try:
                ready_msg = "💬 Команда в сборе и готова к работе. Жду ваших указаний."
                formatted_ready = format_telegram_message(ready_msg)
                await self.application.bot.send_message(
                    chat_id=Config.TARGET_CHAT_ID,
                    text=formatted_ready,
                    parse_mode="MarkdownV2",
                )
                self.logger.info(
                    f"Sent 'ready' message to chat ID {Config.TARGET_CHAT_ID}."
                )
            except Exception as ready_error:
                self.logger.error(
                    f"Failed to send 'ready' message to Telegram: {ready_error}"
                )
        else:
            self.logger.warning(
                "No TARGET_CHAT_ID configured. Cannot send 'ready' message."
            )

    def _is_target_chat(self, chat_id: int) -> bool:
        """Check if message is from the target chat."""
        if Config.TARGET_CHAT_ID == 0:
            # If no target chat configured, allow all chats (backward compatibility)
            return True
        return chat_id == Config.TARGET_CHAT_ID

    def _setup_handlers(self):
        """Set up command and message handlers."""
        # Command handlers
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("help", self.cmd_help))
        self.application.add_handler(CommandHandler("reset", self.cmd_reset))
        self.application.add_handler(CommandHandler("status", self.cmd_status))
        self.application.add_handler(CommandHandler("metrics", self.cmd_metrics))
        self.application.add_handler(CommandHandler("about", self.cmd_about))
        self.application.add_handler(CommandHandler("agents", self.cmd_agents))
        self.application.add_handler(CommandHandler("next", self.cmd_next_agent))

        # Message handlers
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message)
        )

        # Error handler
        self.application.add_error_handler(self.error_handler)

        self.logger.debug("Telegram handlers set up successfully")

    async def _send_role_messages_via_actor(
        self, role_config: RoleConfig, messages: List[str]
    ) -> bool:
        """
        Attempt to send prepared messages via the role-specific Telegram bot.

        Args:
            role_config: Role configuration for which to send the message.
            messages: Pre-formatted messages ready for delivery.

        Returns:
            bool: True if delivery through the actor bot succeeded, False otherwise.
        """
        bot_lookup_name = role_config.telegram_bot_name
        agent_token = Config.TELEGRAM_BOT_TOKENS.get(bot_lookup_name)
        self.logger.info(
            "Actor bot lookup: role=%s, bot_name=%s, token_found=%s",
            role_config.role_name,
            bot_lookup_name,
            bool(agent_token),
        )

        if not agent_token:
            return False

        actor_bot = Bot(token=agent_token)
        for msg in messages:
            try:
                # msg is already formatted and escaped by caller
                await actor_bot.send_message(
                    chat_id=Config.TARGET_CHAT_ID, text=msg, parse_mode="MarkdownV2"
                )
                self.logger.info(
                    "Sent response from %s (%s) via actor bot",
                    role_config.display_name,
                    bot_lookup_name,
                )
            except Exception as send_error:
                self.logger.error(
                    "Error sending message via actor bot %s (%s): %s",
                    role_config.display_name,
                    bot_lookup_name,
                    send_error,
                )
                try:
                    await actor_bot.send_message(
                        chat_id=Config.TARGET_CHAT_ID, text=msg
                    )
                except Exception as fallback_error:
                    self.logger.error(
                        "Critical error sending via actor bot %s (%s): %s",
                        role_config.display_name,
                        bot_lookup_name,
                        fallback_error,
                    )
                    return False

        return True

    async def cmd_start(self, update: Update, context: CallbackContext):
        """
        Handle /start command.

        Args:
            update: Telegram update
            context: Callback context
        """
        try:
            # Check if this is from target chat
            if not self._is_target_chat(update.effective_chat.id):
                self.logger.warning(
                    f"Message from non-target chat {update.effective_chat.id} ignored"
                )
                return

            await self._ensure_ncrew_initialized()

            welcome_msg = format_welcome_message()
            formatted_msg = format_telegram_message(welcome_msg)
            await update.message.reply_text(formatted_msg, parse_mode="MarkdownV2")

            self.logger.info(f"User {update.effective_user.id} started the bot")

        except Exception as e:
            self.logger.error(f"Error in /start command: {e}")
            await update.message.reply_text(
                "❌ Sorry, an error occurred. Please try again."
            )

    async def cmd_help(self, update: Update, context: CallbackContext):
        """
        Handle /help command.

        Args:
            update: Telegram update
            context: Callback context
        """
        try:
            help_msg = format_help_message()
            formatted_msg = format_telegram_message(help_msg)
            await update.message.reply_text(formatted_msg, parse_mode="MarkdownV2")

            self.logger.info(f"User {update.effective_user.id} requested help")

        except Exception as e:
            self.logger.error(f"Error in /help command: {e}")
            await update.message.reply_text(
                "❌ Sorry, an error occurred. Please try again."
            )

    async def cmd_reset(self, update: Update, context: CallbackContext):
        """
        Handle /reset command.

        Args:
            update: Telegram update
            context: Callback context
        """
        try:
            # Check if this is from target chat
            if not self._is_target_chat(update.effective_chat.id):
                self.logger.warning(
                    f"Message from non-target chat {update.effective_chat.id} ignored"
                )
                return

            await self._ensure_ncrew_initialized()

            chat_id = update.effective_chat.id
            result = await self.ncrew.reset_conversation(chat_id)

            await update.message.reply_text(result)

            self.logger.info(f"User {update.effective_user.id} reset conversation")

        except Exception as e:
            self.logger.error(f"Error in /reset command: {e}")
            await update.message.reply_text(
                "❌ Sorry, an error occurred while resetting conversation."
            )

    async def cmd_status(self, update: Update, context: CallbackContext):
        """
        Handle /status command.

        Args:
            update: Telegram update
            context: Callback context
        """
        try:
            await self._ensure_ncrew_initialized()

            agent_status = await self.ncrew.get_agent_status()
            status_msg = format_status_message(agent_status)
            formatted_msg = format_telegram_message(status_msg)

            await update.message.reply_text(formatted_msg, parse_mode="MarkdownV2")

            self.logger.info(f"User {update.effective_user.id} requested status")

        except Exception as e:
            self.logger.error(f"Error in /status command: {e}")
            await update.message.reply_text(
                "❌ Sorry, an error occurred while getting status."
            )

    async def cmd_metrics(self, update: Update, context: CallbackContext):
        """
        Handle /metrics command.

        Args:
            update: Telegram update
            context: Callback context
        """
        try:
            await self._ensure_ncrew_initialized()

            metrics = self.ncrew.get_metrics()
            metrics_msg = f"""📊 **Performance Metrics**

🔄 **Agent Calls:** {metrics["total_agent_calls"]}
⏱️ **Total Response Time:** {metrics["total_response_time"]:.2f}s
📈 **Average Response Time:** {metrics["average_response_time"]:.2f}s
💬 **Conversations Processed:** {metrics["conversations_processed"]}
📝 **Messages Processed:** {metrics["messages_processed"]}"""

            formatted_msg = format_telegram_message(metrics_msg)
            await update.message.reply_text(formatted_msg, parse_mode="MarkdownV2")

            self.logger.info(f"User {update.effective_user.id} requested metrics")

        except Exception as e:
            self.logger.error(f"Error in /metrics command: {e}")
            await update.message.reply_text(
                "❌ Sorry, an error occurred while getting metrics."
            )

    async def cmd_about(self, update: Update, context: CallbackContext):
        """
        Handle /about command.

        Args:
            update: Telegram update
            context: Callback context
        """
        try:
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

            formatted_msg = format_telegram_message(about_msg)
            await update.message.reply_text(formatted_msg, parse_mode="MarkdownV2")

            self.logger.info(f"User {update.effective_user.id} requested about")

        except Exception as e:
            self.logger.error(f"Error in /about command: {e}")
            await update.message.reply_text("❌ Sorry, an error occurred.")

    async def cmd_agents(self, update: Update, context: CallbackContext):
        """
        Handle /agents command.

        Args:
            update: Telegram update
            context: Callback context
        """
        try:
            await self._ensure_ncrew_initialized()

            chat_id = update.effective_chat.id
            agent_info = await self.ncrew.get_chat_agent_info(chat_id)

            if not agent_info:
                await update.message.reply_text("❌ Unable to get agent information.")
                return

            # Format agent information
            lines = [f"🤖 **Agent Sequence for Your Chat**"]
            lines.append(f"📍 Current: {agent_info.get('current_agent', 'Unknown')}")
            lines.append(
                f"🔄 Position: {agent_info.get('agent_index', 0) + 1}/{agent_info.get('total_agents', 0)}"
            )
            lines.append("")

            lines.append("**Next Agents:**")
            for i, agent in enumerate(agent_info.get("next_agents", [])[:3]):
                emoji = "✅" if agent["available"] else "❌"
                arrow = "→" if i == 0 else "⤷️"
                status = "Available" if agent["available"] else "Unavailable"
                lines.append(f"{emoji} {arrow} {agent['name']} ({status})")

            msg = "\n".join(lines)
            formatted_msg = format_telegram_message(msg)
            await update.message.reply_text(formatted_msg, parse_mode="MarkdownV2")

            self.logger.info(
                f"User {update.effective_user.id} requested agent information"
            )

        except Exception as e:
            self.logger.error(f"Error in /agents command: {e}")
            await update.message.reply_text(
                "❌ Sorry, an error occurred while getting agent information."
            )

    async def cmd_next_agent(self, update: Update, context: CallbackContext):
        """
        Handle /next command to skip to next agent.

        Args:
            update: Telegram update
            context: Callback context
        """
        try:
            await self._ensure_ncrew_initialized()

            chat_id = update.effective_chat.id
            next_agent = await self.ncrew.skip_to_next_agent(chat_id)

            if next_agent:
                # Get updated agent info
                agent_info = await self.ncrew.get_chat_agent_info(chat_id)
                msg = f"🔄 **Switched to next agent:** {next_agent}"

                if agent_info:
                    msg += f"\n📍 **Sequence position:** {agent_info.get('agent_index', 0) + 1}/{agent_info.get('total_agents', 0)}"

                formatted_msg = format_telegram_message(msg)
                await update.message.reply_text(formatted_msg, parse_mode="MarkdownV2")
                self.logger.info(
                    f"User {update.effective_user.id} switched to agent: {next_agent}"
                )
            else:
                await update.message.reply_text("❌ No agents available to switch to.")

        except Exception as e:
            self.logger.error(f"Error in /next command: {e}")
            await update.message.reply_text(
                "❌ Sorry, an error occurred while switching agents."
            )

    async def handle_message(self, update: Update, context: CallbackContext):
        """
        Handle text messages from users using Puppet Master architecture.

        Args:
            update: Telegram update
            context: Callback context
        """
        try:
            # Check if this is from target chat
            if not self._is_target_chat(update.effective_chat.id):
                self.logger.warning(
                    f"Message from non-target chat {update.effective_chat.id} ignored"
                )
                return

            await self._ensure_ncrew_initialized()

            chat_id = update.effective_chat.id
            user_text = update.message.text
            user_name = (
                update.effective_user.first_name or update.effective_user.username
            )

            # Security validation of input
            is_valid, error_msg = validate_input(user_text, "message")
            if not is_valid:
                self.logger.warning(
                    f"Security check failed for message from {user_name} ({chat_id}): {error_msg}"
                )
                await update.message.reply_text(
                    "❌ Your message contains potentially dangerous content and was rejected for security reasons."
                )
                return

            # Sanitize message for logging
            sanitized_message = sanitize_for_logging(user_text)
            self.logger.info(
                f"Message from {user_name} ({chat_id}): {sanitized_message[:100]}..."
            )

            processing_msg = None

            try:
                # Process message through NeuroCrew autonomous dialogue cycle
                # Iterate over async generator to get responses from all roles
                role_responses_sent = 0

                async for role_config, raw_response in self.ncrew.handle_message(
                    chat_id, user_text
                ):
                    # Delete initial processing message on first response
                    if role_config and raw_response:
                        # Успешный ответ от роли
                        display_name = role_config.display_name
                        # Escape and format agent response before splitting
                        safe_response = format_telegram_message(raw_response)
                        formatted_response = format_agent_response(
                            display_name, safe_response
                        )
                        messages_to_send = split_long_message(
                            formatted_response,
                            max_length=Config.TELEGRAM_MAX_MESSAGE_LENGTH,
                        )

                        # 🔍 ОТЛАДОЧНОЕ ЛОГИРОВАНИЕ
                        self.logger.info(f"🔄 Processing role: {role_config.role_name}")
                        self.logger.info(f"📝 Raw response length: {len(raw_response)} chars")
                        self.logger.info(f"📨 Messages to send: {len(messages_to_send)}")
                        self.logger.info(f"📦 First message preview: {messages_to_send[0][:100] if messages_to_send else 'No messages'}")

                        sent_via_actor = await self._send_role_messages_via_actor(
                            role_config, messages_to_send
                        )
                        if not sent_via_actor:
                            for chunk in messages_to_send:
                                # chunk is already formatted and escaped
                                await update.message.reply_text(
                                    chunk, parse_mode="MarkdownV2"
                                )
                            self.logger.warning(
                                "Failed to deliver via actor bot for role %s, sent response via listener bot.",
                                role_config.role_name,
                            )

                        role_responses_sent += 1

                        # Добавляем небольшую паузу для имитации "живого" общения
                        await asyncio.sleep(1.5)

                    else:
                        # Если произошла ошибка внутри ncrew (role_config is None)
                        await update.message.reply_text(raw_response)
                        self.logger.warning(f"NeuroCrew returned error: {raw_response}")

                # Сообщение о завершении цикла
                try:
                    if processing_msg:
                        await processing_msg.delete()
                except Exception:
                    pass

                if role_responses_sent > 0:
                    await update.message.reply_text(
                        "💬 Команда завершила свою работу. Жду ваших дальнейших указаний."
                    )
                    self.logger.info(
                        f"Autonomous dialogue cycle completed for chat {chat_id} with {role_responses_sent} role responses"
                    )
                else:
                    self.logger.warning(f"No role responses sent for chat {chat_id}")

                self.logger.info(f"Successfully processed message for user {user_name}")

            except Exception as processing_error:
                # Delete processing message
                try:
                    await processing_msg.delete()
                except:
                    pass

                self.logger.error(f"Error processing message: {processing_error}")
                await update.message.reply_text(
                    "❌ Sorry, I encountered an error while processing your message. Please try again."
                )

        except asyncio.CancelledError:
            self.logger.info("Message handling cancelled")
            raise
        except Exception as e:
            self.logger.error(f"Error in handle_message: {e}")
            try:
                await update.message.reply_text(
                    "❌ Sorry, an unexpected error occurred."
                )
            except:
                pass

    async def error_handler(self, update: Optional[Update], context: CallbackContext):
        """
        Handle errors in the bot.

        Args:
            update: Telegram update (may be None)
            context: Callback context with error
        """
        self.logger.error(f"Telegram bot error: {context.error}")

        try:
            if update and update.effective_chat:
                await update.effective_chat.send_message(
                    "❌ Sorry, an unexpected error occurred. Please try again later."
                )
        except Exception as e:
            self.logger.error(f"Error sending error message: {e}")

    async def send_system_status(self, chat_id: int):
        """
        Send system status to a specific chat.

        Args:
            chat_id: Telegram chat ID
        """
        try:
            await self._ensure_ncrew_initialized()

            system_status = await self.ncrew.get_system_status()

            status_lines = ["🔍 **System Status**"]
            status_lines.append(
                f"📊 Total chats: {system_status.get('total_chats', 0)}"
            )
            status_lines.append(
                f"💬 Total messages: {system_status.get('total_messages', 0)}"
            )
            status_lines.append(
                f"💾 Storage size: {system_status.get('storage_size_mb', 0)} MB"
            )
            status_lines.append(
                f"🤖 Available agents: {system_status.get('available_agents', 0)}/{system_status.get('configured_agents', 0)}"
            )

            status_msg = "\n".join(status_lines)
            formatted_status = format_telegram_message(status_msg)

            await self.application.bot.send_message(
                chat_id, formatted_status, parse_mode="MarkdownV2"
            )

        except Exception as e:
            self.logger.error(f"Error sending system status: {e}")

    async def _handle_application_shutdown(self, application: Application):
        """
        Telegram Application post-shutdown hook.

        Ensures NeuroCrew resources are cleaned up before the event loop closes.
        """
        await self.shutdown()

    def run(self):
        """Run the Telegram bot."""
        try:
            self.logger.info("Starting NeuroCrew Lab Telegram bot...")
            self.application.run_polling(drop_pending_updates=True)

        except KeyboardInterrupt:
            self.logger.info("Bot stopped by user")
        except Exception as e:
            self.logger.error(f"Error running bot: {e}")
            raise
        finally:
            self.logger.info("Bot shutdown complete")

    async def shutdown(self):
        """Gracefully shut down the bot and any associated resources with reduced logging."""
        self.logger.info("Shutting down Telegram bot...")

        try:
            # Step 1: Shutdown all role sessions (connectors)
            if self.ncrew:
                try:
                    await self.ncrew.shutdown_role_sessions()
                except Exception as e:
                    self.logger.debug(f"Error shutting down role sessions: {e}")

            # Step 2: Stop the application
            try:
                if hasattr(self.application, "stop"):
                    await self.application.stop()
                elif hasattr(self.application, "stop_running"):
                    self.application.stop_running()
            except Exception as e:
                self.logger.debug(f"Error stopping application: {e}")

            # Step 3: Final cleanup
            try:
                self.ncrew = None
            except Exception as e:
                self.logger.debug(f"Error during final cleanup: {e}")

        except Exception as e:
            self.logger.error(f"Critical error during graceful shutdown: {e}")

        finally:
            self.logger.info("Telegram bot shutdown completed")


# For development and testing
def main():
    """Main function for running the bot independently."""
    try:
        Config.validate()
        bot = TelegramBot()
        bot.run()
    except Exception as e:
        logging.error(f"Failed to start bot: {e}")
        return 1
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
