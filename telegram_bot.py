"""
Telegram bot interface for NeuroCrew Lab.

This module provides the Telegram bot interface for user interaction
with the NeuroCrew Lab system.
"""

import asyncio
import logging
import os
from typing import List, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
from telegram.ext import CallbackQueryHandler

from config import Config
from ncrew import NeuroCrewLab
from utils.logger import setup_logger
from utils.formatters import format_welcome_message, format_help_message, format_status_message, format_agent_response, split_long_message
from utils.security import validate_input, sanitize_for_logging


class ProxyManager:
    """Context manager to temporarily disable proxy settings."""

    def __init__(self):
        self.original_proxies = {}
        self.proxy_vars = ['HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy']

    def __enter__(self):
        # Save and remove proxy variables
        for var in self.proxy_vars:
            if var in os.environ:
                self.original_proxies[var] = os.environ[var]
                del os.environ[var]
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Restore proxy variables
        for var, value in self.original_proxies.items():
            os.environ[var] = value


class TelegramBot:
    """
    Telegram bot interface for NeuroCrew Lab.

    Handles user interactions through Telegram commands and messages.
    """

    def __init__(self):
        """Initialize the Telegram bot."""
        self.logger = setup_logger(f"{self.__class__.__name__}", Config.LOG_LEVEL)
        self.ncrew = None  # Will be initialized asynchronously

        try:
            # Initialize application with main listener bot token
            bot_token = Config.MAIN_BOT_TOKEN or Config.TELEGRAM_BOT_TOKEN

            # Disable proxy for telegram bot (SOCKS proxy not supported)
            with ProxyManager():
                self.application = Application.builder().token(bot_token).build()

            self.logger.info("Telegram application created successfully with main listener bot (proxy disabled)")

            # Set up handlers
            self._setup_handlers()
            self.application.post_shutdown = self._handle_application_shutdown

            self.logger.info("Telegram bot initialized successfully")

        except Exception as e:
            self.logger.error(f"Failed to initialize Telegram bot: {e}")
            raise

    async def _ensure_ncrew_initialized(self):
        """Ensure NeuroCrew Lab is initialized."""
        if self.ncrew is None:
            self.logger.info("Initializing NeuroCrew Lab...")
            print("DEBUG: Creating NeuroCrewLab instance...")
            self.ncrew = NeuroCrewLab()
            print(f"DEBUG: NeuroCrewLab created, roles count = {len(self.ncrew.roles)}")
            await self.ncrew.initialize()
            self.logger.info("NeuroCrew Lab initialized successfully")

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
                self.logger.warning(f"Message from non-target chat {update.effective_chat.id} ignored")
                return

            await self._ensure_ncrew_initialized()

            welcome_msg = format_welcome_message()
            await update.message.reply_text(welcome_msg, parse_mode='Markdown')

            self.logger.info(f"User {update.effective_user.id} started the bot")

        except Exception as e:
            self.logger.error(f"Error in /start command: {e}")
            await update.message.reply_text("❌ Sorry, an error occurred. Please try again.")

    async def cmd_help(self, update: Update, context: CallbackContext):
        """
        Handle /help command.

        Args:
            update: Telegram update
            context: Callback context
        """
        try:
            help_msg = format_help_message()
            await update.message.reply_text(help_msg, parse_mode='Markdown')

            self.logger.info(f"User {update.effective_user.id} requested help")

        except Exception as e:
            self.logger.error(f"Error in /help command: {e}")
            await update.message.reply_text("❌ Sorry, an error occurred. Please try again.")

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
                self.logger.warning(f"Message from non-target chat {update.effective_chat.id} ignored")
                return

            await self._ensure_ncrew_initialized()

            chat_id = update.effective_chat.id
            result = await self.ncrew.reset_conversation(chat_id)

            await update.message.reply_text(result)

            self.logger.info(f"User {update.effective_user.id} reset conversation")

        except Exception as e:
            self.logger.error(f"Error in /reset command: {e}")
            await update.message.reply_text("❌ Sorry, an error occurred while resetting conversation.")

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

            await update.message.reply_text(status_msg, parse_mode='Markdown')

            self.logger.info(f"User {update.effective_user.id} requested status")

        except Exception as e:
            self.logger.error(f"Error in /status command: {e}")
            await update.message.reply_text("❌ Sorry, an error occurred while getting status.")

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

🔄 **Agent Calls:** {metrics['total_agent_calls']}
⏱️ **Total Response Time:** {metrics['total_response_time']:.2f}s
📈 **Average Response Time:** {metrics['average_response_time']:.2f}s
💬 **Conversations Processed:** {metrics['conversations_processed']}
📝 **Messages Processed:** {metrics['messages_processed']}"""

            await update.message.reply_text(metrics_msg, parse_mode='Markdown')

            self.logger.info(f"User {update.effective_user.id} requested metrics")

        except Exception as e:
            self.logger.error(f"Error in /metrics command: {e}")
            await update.message.reply_text("❌ Sorry, an error occurred while getting metrics.")

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
                "*Currently in MVP development phase*"
            )

            await update.message.reply_text(about_msg, parse_mode='Markdown')

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
            lines.append(f"🔄 Position: {agent_info.get('agent_index', 0) + 1}/{agent_info.get('total_agents', 0)}")
            lines.append("")

            lines.append("**Next Agents:**")
            for i, agent in enumerate(agent_info.get('next_agents', [])[:3]):
                emoji = "✅" if agent['available'] else "❌"
                arrow = "→" if i == 0 else "⤷️"
                status = "Available" if agent['available'] else "Unavailable"
                lines.append(f"{emoji} {arrow} {agent['name']} ({status})")

            msg = "\n".join(lines)
            await update.message.reply_text(msg, parse_mode='Markdown')

            self.logger.info(f"User {update.effective_user.id} requested agent information")

        except Exception as e:
            self.logger.error(f"Error in /agents command: {e}")
            await update.message.reply_text("❌ Sorry, an error occurred while getting agent information.")

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

                await update.message.reply_text(msg, parse_mode='Markdown')
                self.logger.info(f"User {update.effective_user.id} switched to agent: {next_agent}")
            else:
                await update.message.reply_text("❌ No agents available to switch to.")

        except Exception as e:
            self.logger.error(f"Error in /next command: {e}")
            await update.message.reply_text("❌ Sorry, an error occurred while switching agents.")

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
                self.logger.warning(f"Message from non-target chat {update.effective_chat.id} ignored")
                return

            await self._ensure_ncrew_initialized()

            chat_id = update.effective_chat.id
            user_text = update.message.text
            user_name = update.effective_user.first_name or update.effective_user.username

            # Security validation of input
            is_valid, error_msg = validate_input(user_text, "message")
            if not is_valid:
                self.logger.warning(f"Security check failed for message from {user_name} ({chat_id}): {error_msg}")
                await update.message.reply_text("❌ Your message contains potentially dangerous content and was rejected for security reasons.")
                return

            # Sanitize message for logging
            sanitized_message = sanitize_for_logging(user_text)
            self.logger.info(f"Message from {user_name} ({chat_id}): {sanitized_message[:100]}...")

            processing_msg = None

            try:
                # Process message through NeuroCrew autonomous dialogue cycle
                # Iterate over async generator to get responses from all roles
                role_responses_sent = 0

                async for role_config, raw_response in self.ncrew.handle_message(chat_id, user_text):
                    # Delete initial processing message on first response
                    if role_config and raw_response:
                        # Успешный ответ от роли
                        # Get bot token from role config
                        bot_lookup_name = role_config.telegram_bot_name
                        agent_token = Config.TELEGRAM_BOT_TOKENS.get(bot_lookup_name)
                        self.logger.info(f"Token lookup: bot_lookup_name={bot_lookup_name}, agent_token_found={bool(agent_token)}")

                        display_name = role_config.display_name
                        formatted_response = format_agent_response(display_name, raw_response)
                        messages_to_send = split_long_message(formatted_response, max_length=Config.TELEGRAM_MAX_MESSAGE_LENGTH)

                        if agent_token:
                            with ProxyManager():
                                actor_bot = Bot(token=agent_token)
                                for msg in messages_to_send:
                                    try:
                                        await actor_bot.send_message(
                                            chat_id=Config.TARGET_CHAT_ID,
                                            text=msg,
                                            parse_mode='Markdown'
                                        )
                                        self.logger.info(f"Sent response from {display_name} ({bot_lookup_name}) via actor bot")
                                    except Exception as send_error:
                                        self.logger.error(f"Error sending message via actor bot {display_name} ({bot_lookup_name}): {send_error}")
                                        try:
                                            await actor_bot.send_message(chat_id=Config.TARGET_CHAT_ID, text=msg)
                                        except Exception as fallback_error:
                                            self.logger.error(f"Critical error sending via actor bot: {fallback_error}")
                                            await update.message.reply_text(f"❌ Error sending from {display_name} bot. Response:\n{raw_response}")
                                            break
                        else:
                            for chunk in messages_to_send:
                                await update.message.reply_text(chunk, parse_mode='Markdown')
                            self.logger.warning(f"No actor token for role {role_config.role_name}, sent response via listener bot.")

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
                    await update.message.reply_text("💬 Команда завершила свою работу. Жду ваших дальнейших указаний.")
                    self.logger.info(f"Autonomous dialogue cycle completed for chat {chat_id} with {role_responses_sent} role responses")
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
                await update.message.reply_text("❌ Sorry, an unexpected error occurred.")
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
            status_lines.append(f"📊 Total chats: {system_status.get('total_chats', 0)}")
            status_lines.append(f"💬 Total messages: {system_status.get('total_messages', 0)}")
            status_lines.append(f"💾 Storage size: {system_status.get('storage_size_mb', 0)} MB")
            status_lines.append(f"🤖 Available agents: {system_status.get('available_agents', 0)}/{system_status.get('configured_agents', 0)}")

            status_msg = "\n".join(status_lines)

            await self.application.bot.send_message(chat_id, status_msg, parse_mode='Markdown')

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
        """Gracefully shut down the bot and any associated resources."""
        self.logger.info("Initiating graceful shutdown...")
        try:
            if self.ncrew:
                # Shutdown all role sessions (connectors)
                await self.ncrew.shutdown_role_sessions()
                self.logger.info("All role sessions shut down")
        except Exception as e:
            self.logger.error(f"Error during graceful shutdown: {e}")
        finally:
            self.logger.info("Graceful shutdown completed")


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


if __name__ == '__main__':
    import sys
    sys.exit(main())
