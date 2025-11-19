"""
NeuroCrew Lab - Core business logic for multi-agent orchestration.

This module contains the main NeuroCrewLab class that manages
agent orchestration, conversation handling, and state management.
"""

import asyncio
import logging
import subprocess
import time
from datetime import datetime
from typing import List, Dict, Optional, Any, Tuple, AsyncGenerator

from config import Config, RoleConfig
from storage.file_storage import FileStorage
from connectors import get_connector_class, get_connector_spec
from connectors.base import BaseConnector
from utils.logger import get_logger


class NeuroCrewLab:
    """
    Core business logic for NeuroCrew Lab.

    Manages multiple AI coding agents, conversation context,
    and orchestrates agent execution with role-based architecture.
    """

    def __init__(self, storage: Optional[FileStorage] = None):
        """
        Initialize NeuroCrew Lab.

        Args:
            storage: File storage instance. Creates default if None.
        """
        self.storage = storage or FileStorage()
        self.logger = get_logger(f"{self.__class__.__name__}")

        # Role-based configuration
        self.is_role_based = Config.is_role_based_enabled()
        self.roles = []

        # Role-based stateful session management ONLY
        self.connector_sessions: Dict[
            Tuple[int, str], BaseConnector
        ] = {}  # {(chat_id, role_name): connector}
        self.chat_role_pointers: Dict[int, int] = {}  # chat_id -> role_index
        self.role_last_seen_index: Dict[
            Tuple[int, str], int
        ] = {}  # {(chat_id, role_name): message_index}
        self.role_response_count: Dict[
            Tuple[int, str], int
        ] = {}  # {(chat_id, role_name): response_count}
        self.role_introductions: Dict[str, str] = {}  # {role_name: introduction_text}

        self._shutdown_in_progress: bool = False

        # Performance metrics
        self.metrics = {
            "total_agent_calls": 0,
            "total_response_time": 0.0,
            "average_response_time": 0.0,
            "conversations_processed": 0,
            "messages_processed": 0,
        }

        # Role-based mode is REQUIRED
        if not self.is_role_based:
            raise RuntimeError(
                "Role-based configuration is required. Please ensure roles/agents.yaml exists and is valid."
            )

        # Initialize role sequence with full chain validation
        self._initialize_and_validate_role_sequence()
        self.logger.info(
            f"NeuroCrew Lab initialized - Role-based: {self.is_role_based}"
        )
        self.logger.info(
            f"Validated role sequence: {[role.role_name for role in self.roles]}"
        )

    def _initialize_and_validate_role_sequence(self):
        """Initialize and validate role sequence with full chain validation."""
        try:
            # Load default role sequence
            all_roles = Config.get_role_sequence("default")

            # Validate complete chain for each role
            self.roles = []
            validation_summary = {
                "total": len(all_roles),
                "valid": 0,
                "invalid": 0,
                "issues": [],
            }

            self.logger.info("=== ROLE CHAIN VALIDATION ===")
            for role in all_roles:
                validation_result = self._validate_role_chain(role)

                if validation_result["valid"]:
                    self.roles.append(role)
                    validation_summary["valid"] += 1
                    self.logger.info(f"✅ {role.role_name} - VALID")
                else:
                    validation_summary["invalid"] += 1
                    validation_summary["issues"].extend(validation_result["issues"])
                    self.logger.warning(
                        f"❌ {role.role_name} - INVALID: {', '.join(validation_result['issues'])}"
                    )

            # Log summary
            self.logger.info(f"=== VALIDATION SUMMARY ===")
            self.logger.info(f"Total roles: {validation_summary['total']}")
            self.logger.info(f"Valid roles: {validation_summary['valid']}")
            self.logger.info(f"Invalid roles: {validation_summary['invalid']}")

            if validation_summary["valid"] == 0:
                raise RuntimeError(
                    "❌ CRITICAL: No valid roles found. System cannot start."
                )

            # Enforce resource availability (command + token)
            enabled_roles = []
            disabled_roles = []

            for role in self.roles:
                missing = []
                if not role.cli_command or not role.cli_command.strip():
                    missing.append("cli_command")
                bot_token = Config.TELEGRAM_BOT_TOKENS.get(role.telegram_bot_name)

                if not bot_token:
                    missing.append("bot_token")
                else:
                    # Check if token is a placeholder/invalid
                    placeholder_patterns = [
                        "your_",
                        "placeholder",
                        "token_here",
                        "bot_token",
                        "example",
                        "test_",
                        "none",
                        "null",
                        "undefined",
                    ]
                    token_lower = bot_token.lower()
                    if any(pattern in token_lower for pattern in placeholder_patterns):
                        missing.append("bot_token")

                if missing:
                    disabled_roles.append((role, missing))
                else:
                    enabled_roles.append(role)

            self.roles = enabled_roles

            for role, missing in disabled_roles:
                self.logger.warning(
                    f"Role {role.role_name} disabled (missing: {', '.join(missing)})"
                )

            if not self.roles:
                raise RuntimeError(
                    "❌ CRITICAL: No enabled roles after resource checks."
                )

            self.logger.info(
                f"🎯 Active roles in queue: {[role.role_name for role in self.roles]}"
            )
            self.logger.info(
                "Resource validation summary: enabled=%d disabled=%d",
                len(self.roles),
                len(disabled_roles),
            )

        except Exception as e:
            self.logger.error(f"Failed to initialize and validate role sequence: {e}")
            raise RuntimeError(f"Role validation failed: {e}")

    def _validate_role_chain(self, role):
        """
        Validate complete chain: Role + Connector + Command + Token

        Returns:
            dict: {'valid': bool, 'issues': list}
        """
        issues = []

        connector_spec = get_connector_spec(getattr(role, "agent_type", None))

        # 1. Validate role configuration
        if not hasattr(role, "role_name") or not role.role_name:
            issues.append("missing role_name")
        if not hasattr(role, "agent_type") or not role.agent_type:
            issues.append("missing agent_type")
        if not hasattr(role, "telegram_bot_name") or not role.telegram_bot_name:
            issues.append("missing telegram_bot_name")

        # 2. Validate connector availability
        if role.agent_type:
            connector_available = self._validate_connector(role.agent_type)
            if not connector_available:
                issues.append(f"no connector for {role.agent_type}")

        # 3. Validate CLI command when required
        requires_cli = connector_spec.requires_cli if connector_spec else True
        cli_command = getattr(role, "cli_command", "")

        if requires_cli:
            if not cli_command:
                issues.append("missing cli_command")
            else:
                command_valid = self._validate_cli_command(cli_command)
                if not command_valid:
                    issues.append(f"CLI command '{cli_command}' invalid")

        # 4. Validate Telegram bot token
        if role.telegram_bot_name:
            token_valid = self._validate_telegram_token(role.telegram_bot_name)
            if not token_valid:
                issues.append(f"no token for {role.telegram_bot_name}")

        return {"valid": len(issues) == 0, "issues": issues}

    def _validate_connector(self, agent_type):
        """Check if connector exists for agent type."""
        try:
            connector_class = get_connector_class(agent_type)
            return connector_class is not None
        except ImportError as e:
            self.logger.error(f"Connector import error: {e}")
            return False

    def _validate_cli_command(self, cli_command):
        """Validate CLI command is available."""
        try:
            import subprocess
            import shlex

            # Extract base command (remove arguments)
            parts = shlex.split(cli_command)
            base_command = parts[0] if parts else cli_command

            # Check if command exists in PATH
            result = subprocess.run(
                ["which", base_command], capture_output=True, text=True, timeout=5
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            return False

    def _validate_telegram_token(self, telegram_bot_name):
        """Validate Telegram bot token exists and is not empty."""
        try:
            if not hasattr(Config, "TELEGRAM_BOT_TOKENS"):
                return False

            token = Config.TELEGRAM_BOT_TOKENS.get(telegram_bot_name)
            return token is not None and len(token.strip()) > 0
        except Exception:
            return False

    def _filter_valid_roles(self) -> List[RoleConfig]:
        """
        Filter roles to only include those with valid CLI commands AND bot tokens.

        Returns:
            List[RoleConfig]: Filtered list of valid roles
        """
        if not self.is_role_based:
            return []

        valid_roles = []
        for role in self.roles:
            self.logger.debug(f"Validating role resources: {role.role_name}")
            # Check CLI command availability
            cli_command = role.cli_command
            if not cli_command:
                self.logger.warning(f"Role {role.role_name}: no CLI command configured")
                continue

            # Check bot token availability (new format only)
            bot_token = Config.TELEGRAM_BOT_TOKENS.get(role.telegram_bot_name)
            if not bot_token:
                self.logger.warning(
                    f"Role {role.role_name}: no bot token configured for {role.telegram_bot_name}"
                )
                continue

            # Check if token is a placeholder/invalid
            placeholder_patterns = [
                "your_",
                "placeholder",
                "token_here",
                "bot_token",
                "example",
                "test_",
                "none",
                "null",
                "undefined",
            ]
            token_lower = bot_token.lower()
            if any(pattern in token_lower for pattern in placeholder_patterns):
                self.logger.warning(
                    f"Role {role.role_name}: bot token appears to be placeholder for {role.telegram_bot_name}"
                )
                continue

            # Test CLI availability (quick check)
            try:
                import subprocess
                import os

                result = subprocess.run(
                    [cli_command, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    env=os.environ.copy(),
                )
                if result.returncode == 0:
                    valid_roles.append(role)
                    self.logger.info(
                        f"Role {role.role_name}: ✅ CLI available, ✅ Token configured"
                    )
                else:
                    self.logger.warning(f"Role {role.role_name}: CLI command failed")
            except Exception as e:
                self.logger.warning(f"Role {role.role_name}: CLI check failed: {e}")

        return valid_roles

    async def initialize(self):
        """
        Asynchronous initialization that requires await.
        Call this after creating the instance.
        """
        # Load system prompts for all roles (roles already validated in constructor)
        if self.is_role_based:
            # Load system prompts for each validated role
            for role in self.roles:
                if (
                    not role.system_prompt
                    and hasattr(role, "system_prompt_file")
                    and role.system_prompt_file
                ):
                    try:
                        with open(role.system_prompt_file, "r", encoding="utf-8") as f:
                            role.system_prompt = f.read().strip()
                    except Exception as e:
                        self.logger.error(
                            f"Failed to load system prompt for {role.role_name}: {e}"
                        )
                        role.system_prompt = f"You are a {role.display_name} helping with programming tasks."
                elif not role.system_prompt:
                    role.system_prompt = (
                        f"You are a {role.display_name} helping with programming tasks."
                    )

            self.logger.info(
                f"Initialized {len(self.roles)} validated roles ready for stateful execution"
            )

    # Legacy _filter_valid_agents method removed - we use role-based stateful connectors only

    # Legacy initialize_connectors method removed - we use stateful role sessions instead

    async def handle_message(
        self, chat_id: int, user_text: str
    ) -> AsyncGenerator[Tuple[Optional[RoleConfig], str], None]:
        """
        Handle a user message and process it through continuous autonomous role dialogue cycle.

        Args:
            chat_id: Telegram chat ID
            user_text: User's message text

        Yields:
            Tuple[RoleConfig, str]: (role_config, raw_response) for each role in the cycle
        """
        self.logger.info(
            f"Starting continuous autonomous dialogue cycle for chat {chat_id}: {user_text[:100]}..."
        )

        try:
            # Add user message to conversation
            user_message = {
                "role": "user",
                "content": user_text,
                "timestamp": datetime.now().isoformat(),
            }

            success = await self.storage.add_message(chat_id, user_message)
            if not success:
                self.logger.error("Failed to save user message")
                yield (None, "❌ Error: Could not save your message")
                return

            # Update conversation metrics
            self.metrics["conversations_processed"] += 1
            self.metrics["messages_processed"] += 1

            # --- НАЧАЛО НЕПРЕРЫВНОГО АВТОНОМНОГО ЦИКЛА ---
            # Continue cycling through roles indefinitely, building conversation context
            # Stop only when ALL agents have nothing to say (respond with ".....")

            self.logger.info(
                f"Starting continuous cycle with {len(self.roles)} validated roles"
            )
            cycle_count = 0
            consecutive_empty_responses = 0  # Считаем последовательные ответы "....."
            consecutive_error_responses = 0
            MAX_CYCLES = 20

            while cycle_count < MAX_CYCLES:  # Цикл с ограничением итераций
                self.logger.debug(
                    "Chat %s: top of loop, roles=%s, pointer=%s",
                    chat_id,
                    [r.role_name for r in self.roles],
                    self.chat_role_pointers.get(chat_id, 0),
                )

                if self._shutdown_in_progress:
                    self.logger.info(
                        f"Shutdown requested, stopping dialogue cycle for chat {chat_id}"
                    )
                    break

                cycle_count += 1
                self.logger.info(f"--- Cycle {cycle_count} ---")

                # Get next role using round-robin pointer
                current_role_index = self.chat_role_pointers.get(chat_id, 0)
                role_config = self.roles[current_role_index]

                self.logger.info(
                    f"Активация роли {cycle_count}: {role_config.role_name}"
                )

                # Check availability and launch if needed
                connector = self._get_or_create_role_connector(chat_id, role_config)
                if not connector.is_alive():
                    try:
                        await connector.launch(
                            role_config.cli_command, role_config.system_prompt
                        )
                        self.logger.info(
                            f"Launched role process: {role_config.role_name}"
                        )
                    except Exception as e:
                        self.logger.error(
                            f"Не удалось запустить роль {role_config.role_name}: {e}"
                        )
                        # Move to next role and continue
                        self.chat_role_pointers[chat_id] = (
                            current_role_index + 1
                        ) % len(self.roles)
                        continue

                # Process with current role
                self.logger.debug(
                    f"Chat {chat_id}: invoking _process_with_role for {role_config.role_name}"
                )
                raw_response = await self._process_with_role(chat_id, role_config)
                self.logger.debug(
                    f"Chat {chat_id}: role {role_config.role_name} produced "
                    f"{len(raw_response)} chars"
                )

                # Update pointer for next cycle
                self.chat_role_pointers[chat_id] = (current_role_index + 1) % len(
                    self.roles
                )

                # Check for termination condition: ровно 5 точек
                if raw_response.strip() == ".....":
                    consecutive_empty_responses += 1
                    consecutive_error_responses = 0
                    self.logger.info(
                        f"Роль {role_config.role_name} не имеет ничего добавить ({consecutive_empty_responses}/{len(self.roles)})."
                    )

                    # Если ВСЕ агенты подряд ответили "....." - завершаем диалог
                    if consecutive_empty_responses >= len(self.roles):
                        self.logger.info(
                            f"Все {len(self.roles)} агентов завершили диалог. Цикл остановлен."
                        )
                        yield (None, "Ожидаем новое сообщение от пользователя.")
                        break
                    else:
                        # Продолжаем цикл, но не отправляем response в Telegram
                        continue

                # Reset counter when we get meaningful response
                consecutive_empty_responses = 0

                # Check for error responses - they don't count towards termination
                if (
                    raw_response.startswith("❌ Error:")
                    or raw_response == "I'm sorry, I don't have a response for that."
                ):
                    self.logger.warning(
                        f"Role {role_config.role_name} returned error response "
                        f"(length={len(raw_response)}). Continuing to next role."
                    )
                    consecutive_error_responses += 1
                    yield (role_config, raw_response)

                    if consecutive_error_responses >= len(self.roles):
                        self.logger.error(
                            "All roles returned error responses in this cycle. Stopping dialogue."
                        )
                        break
                    continue
                else:
                    consecutive_error_responses = 0

                # Yield the response for Telegram sending (только meaningful responses)
                yield (role_config, raw_response)

            self.logger.info(
                f"Continuous autonomous cycle completed after {cycle_count} iterations for chat {chat_id}"
            )

        except Exception as e:
            error_msg = f"Error in continuous autonomous dialogue cycle: {e}"
            self.logger.error(error_msg)
            yield (
                None,
                f"❌ Error: Something went wrong during the autonomous dialogue cycle",
            )

    async def _get_next_role(self, chat_id: int) -> Optional[RoleConfig]:
        """
        Get the next role using role-based selection.

        Cycles through available roles in sequence for each chat.

        Args:
            chat_id: Telegram chat ID

        Returns:
            Optional[RoleConfig]: Role configuration or None if no roles available
        """
        try:
            # Get current pointer or initialize to 0
            current_pointer = self.chat_role_pointers.get(chat_id, 0)
            roles_tried = 0
            max_attempts = len(self.roles)

            # Try roles starting from current pointer
            while roles_tried < max_attempts:
                role_index = (current_pointer + roles_tried) % len(self.roles)
                role = self.roles[role_index]

                # Get stateful connector for this role
                try:
                    connector = self._get_or_create_role_connector(chat_id, role)
                    if connector.check_availability():
                        # Update pointer for next time
                        self.chat_role_pointers[chat_id] = (role_index + 1) % len(
                            self.roles
                        )
                        self.logger.debug(
                            f"Selected role: {role.role_name} -> {role.agent_type} (pointer: {self.chat_role_pointers[chat_id]})"
                        )
                        return role
                    else:
                        self.logger.warning(
                            f"Role {role.role_name}: agent not available"
                        )
                except Exception as e:
                    self.logger.warning(
                        f"Role {role.role_name}: connector creation failed: {e}"
                    )

                roles_tried += 1

                self.logger.error("No roles are available")
                self.logger.debug(
                    "Role validation state: %s",
                    {
                        "roles": [r.role_name for r in self.roles],
                        "pointer": self.chat_role_pointers.get(chat_id),
                    },
                )
                return None

        except Exception as e:
            self.logger.error(f"Error selecting role: {e}")
            return None

    async def _process_with_role(self, chat_id: int, role: RoleConfig) -> str:
        """
        Process message through a specific role using pure stateful connectors.

        Args:
            chat_id: Telegram chat ID
            role: RoleConfig for the role to process with

        Returns:
            str: Role's raw response (without formatting)
        """
        try:
            self.logger.info(f"Processing with role: {role.role_name}")

            self.logger.debug(
                f"Chat {chat_id}: loading conversation history for role {role.role_name}"
            )
            # Get full conversation history for context
            conversation = await self.storage.load_conversation(chat_id)
            self.logger.debug(
                f"Chat {chat_id}: history contains {len(conversation)} messages"
            )

            key = (chat_id, role.role_name)
            last_seen_index = self.role_last_seen_index.get(key, 0)
            if last_seen_index < 0 or last_seen_index > len(conversation):
                last_seen_index = max(len(conversation) - 6, 0)

            new_messages = conversation[last_seen_index:]
            role_prompt, has_updates = self._format_conversation_for_role(
                new_messages, role, chat_id
            )

            if has_updates:
                # Get or create stateful connector for role
                role_connector = self._get_or_create_role_connector(chat_id, role)

                # Launch role process if not already running
                if not role_connector.is_alive():
                    await role_connector.launch(role.cli_command, role.system_prompt)
                    self.logger.debug(f"Launched role process: {role.role_name}")

                self.logger.debug(
                    f"Chat {chat_id}: formatted prompt for {role.role_name} "
                    f"({len(role_prompt)} chars, updates={len(new_messages)})"
                )

                # Execute with retry logic for basic error recovery
                max_retries = 2
                response = None
                response_time = 0

                for attempt in range(max_retries):
                    try:
                        start_time = time.time()
                        response = await role_connector.execute(role_prompt)
                        response_time = time.time() - start_time
                        break  # Success, exit retry loop
                    except Exception as e:
                        self.logger.warning(
                            f"Role {role.role_name} execution attempt {attempt + 1} failed: {e}"
                        )
                        if attempt < max_retries - 1:
                            # Wait before retry
                            await asyncio.sleep(1)
                            continue
                        else:
                            # All retries failed
                            raise e

                # Update performance metrics
                self.metrics["total_agent_calls"] += 1
                self.metrics["total_response_time"] += response_time
                self.metrics["average_response_time"] = (
                    self.metrics["total_response_time"]
                    / self.metrics["total_agent_calls"]
                )

                self.logger.info(
                    f"Role {role.role_name} response time: {response_time:.2f}s"
                )
                self.logger.debug(f"Stateful execution with role: {role.role_name}")
            else:
                response = "....."
                self.logger.debug(
                    f"Chat {chat_id}: no new updates for {role.role_name}, responding with placeholder"
                )

            # Save agent response to conversation with role information
            agent_message = {
                "role": "agent",
                "agent_name": role.agent_type,
                "role_name": role.role_name,
                "role_display_name": role.display_name,
                "content": response,
                "timestamp": datetime.now().isoformat(),
            }

            success = await self.storage.add_message(chat_id, agent_message)
            if not success:
                self.logger.warning("Failed to save agent response")
                self.role_last_seen_index[key] = len(conversation)
            else:
                # Update last seen index for this role to the end of conversation (including new message)
                self.role_last_seen_index[key] = len(conversation) + 1

                # Update response count for system reminder tracking
                if response != ".....":  # Don't count placeholder responses
                    role_key = (chat_id, role.role_name)
                    self.role_response_count[role_key] = (
                        self.role_response_count.get(role_key, 0) + 1
                    )

            self.logger.info(f"Role {role.role_name} processed message successfully")
            return response

        except Exception as e:
            error_msg = f"Error processing with role {role.role_name}: {e}"
            self.logger.error(error_msg)
            self.logger.debug("Exception details", exc_info=True)
            return f"❌ Error: {role.role_name} encountered an error while processing your message"

    def _format_conversation_for_role(
        self, new_messages: List[Dict], role: RoleConfig, chat_id: int
    ) -> Tuple[str, bool]:
        """
        Build role prompt from messages that appeared since the role's last response.

        Args:
            new_messages: Messages that happened after the role's previous turn
            role: Role configuration
            chat_id: Chat ID for system reminder tracking

        Returns:
            Tuple[str, bool]: (prompt text, has_meaningful_updates)
        """
        if not new_messages:
            return ".....", False

        # Filter out placeholder responses
        filtered_messages = []
        for msg in new_messages:
            content = (msg.get("content") or "").strip()
            if content == ".....":
                continue
            filtered_messages.append(msg)

        if not filtered_messages:
            return ".....", False

        # Build conversation context from all new messages
        context_lines: List[str] = []
        for msg in filtered_messages:
            if msg.get("role") == "user":
                content = msg.get("content", "")
                context_lines.append(f"User: {content}")
            elif msg.get("role") == "agent":
                agent_name = msg.get(
                    "role_display_name", msg.get("role_name", "Assistant")
                )
                content = msg.get("content", "")
                context_lines.append(f"Assistant ({agent_name}): {content}")

        conversation_context = "\n\n".join(context_lines)

        # Check if we need system reminder
        role_key = (chat_id, role.role_name)
        response_count = self.role_response_count.get(role_key, 0)

        if response_count > 0 and response_count % Config.SYSTEM_REMINDER_INTERVAL == 0:
            # Add system reminder
            system_reminder = f"\n\n--- SYSTEM REMINDER ---\n{role.system_prompt}\n--- END REMINDER ---\n\n"
            conversation_context = system_reminder + conversation_context

        prompt = conversation_context

        self.logger.debug(
            "Context for %s built from %d filtered messages (prompt len %d, response_count %d)",
            role.role_name,
            len(filtered_messages),
            len(prompt),
            response_count,
        )
        return prompt, True

    async def _reset_chat_role_sessions(self, chat_id: int) -> None:
        """
        Reset (shutdown) all stateful role sessions for a specific chat.

        Args:
            chat_id: Telegram chat ID
        """
        connector_keys = [
            key for key in self.connector_sessions.keys() if key[0] == chat_id
        ]
        index_keys = [
            key for key in self.role_last_seen_index.keys() if key[0] == chat_id
        ]

        if not connector_keys and not index_keys:
            return

        self.logger.debug(
            "Resetting %d role sessions and %d indices for chat %s",
            len(connector_keys),
            len(index_keys),
            chat_id,
        )

        for key in connector_keys:
            connector = self.connector_sessions.pop(key, None)
            if not connector:
                continue
            try:
                await connector.shutdown()
            except Exception as e:
                self.logger.warning(
                    f"Error shutting down connector for chat {chat_id}, role {key[1]}: {e}"
                )

        for key in index_keys:
            self.role_last_seen_index.pop(key, None)

    async def reset_conversation(self, chat_id: int) -> str:
        """
        Reset conversation history and role pointers for a chat.

        Args:
            chat_id: Telegram chat ID

        Returns:
            str: Confirmation message
        """
        try:
            # Clear conversation history
            success = await self.storage.clear_conversation(chat_id)

            # Reset role pointer for this chat
            if chat_id in self.chat_role_pointers:
                del self.chat_role_pointers[chat_id]
                self.logger.debug(f"Reset role pointer for chat {chat_id}")

            # Reset any active stateful sessions for this chat
            await self._reset_chat_role_sessions(chat_id)

            if success:
                self.logger.info(
                    f"Reset conversation and role state for chat {chat_id}"
                )
                return (
                    "🔄 Conversation reset successfully! Role sequence reset to start."
                )
            else:
                self.logger.error(f"Failed to reset conversation for chat {chat_id}")
                return "❌ Error: Could not reset conversation"

        except Exception as e:
            error_msg = f"Error resetting conversation: {e}"
            self.logger.error(error_msg)
            return f"❌ Error: {error_msg}"

    async def get_agent_status(self) -> Dict[str, bool]:
        """
        Get status of all configured roles/agents.

        Returns:
            Dict[str, bool]: Role availability status
        """
        status: Dict[str, bool] = {}

        for role in self.roles:
            try:
                connector = self._create_connector_for_role(role)
                status[role.agent_type] = connector.check_availability()
            except Exception as e:
                self.logger.warning(
                    f"Failed to check availability for role {role.role_name}: {e}"
                )
                status[role.agent_type] = False

        self.logger.debug(f"Role status: {status}")
        return status

    async def get_conversation_stats(self, chat_id: int) -> Dict[str, Any]:
        """
        Get statistics for a conversation.

        Args:
            chat_id: Telegram chat ID

        Returns:
            Dict[str, Any]: Conversation statistics
        """
        try:
            conversation = await self.storage.load_conversation(chat_id)

            # Count messages by role
            user_messages = sum(1 for msg in conversation if msg.get("role") == "user")
            agent_messages = sum(
                1 for msg in conversation if msg.get("role") == "agent"
            )

            # Count messages by agent
            agent_counts = {}
            for msg in conversation:
                if msg.get("role") == "agent":
                    agent_name = msg.get("agent_name", "unknown")
                    agent_counts[agent_name] = agent_counts.get(agent_name, 0) + 1

            # Get last message time
            last_message_time = None
            if conversation:
                last_message_time = conversation[-1].get("timestamp")

            return {
                "total_messages": len(conversation),
                "user_messages": user_messages,
                "agent_messages": agent_messages,
                "agent_counts": agent_counts,
                "last_message_time": last_message_time,
            }

        except Exception as e:
            self.logger.error(
                f"Error getting conversation stats for chat {chat_id}: {e}"
            )
            return {}

    async def get_system_status(self) -> Dict[str, Any]:
        """
        Get overall system status.

        Returns:
            Dict[str, Any]: System status information
        """
        try:
            # Agent status
            agent_status = await self.get_agent_status()

            # Storage stats
            storage_stats = await self.storage.get_storage_stats()

            # System info
            system_info = {
                "configured_roles": len(self.roles),
                "available_agents": sum(agent_status.values()),
                "total_chats": storage_stats.get("total_chats", 0),
                "total_messages": storage_stats.get("total_messages", 0),
                "storage_size_mb": storage_stats.get("total_size_mb", 0),
                "agent_details": agent_status,
                "active_role_sessions": len(self.connector_sessions),
            }

            return system_info

        except Exception as e:
            self.logger.error(f"Error getting system status: {e}")
            return {}

    async def health_check(self) -> Dict[str, bool]:
        """
        Perform comprehensive health check.

        Returns:
            Dict[str, bool]: Health check results
        """
        health = {
            "storage_ok": False,
            "roles_ok": False,
            "agents_available": False,
            "stateful_sessions_ok": False,
        }

        try:
            # Test storage
            test_chat_id = 999999  # Use a high number for testing
            test_message = {"role": "test", "content": "health check"}
            await self.storage.add_message(test_chat_id, test_message)
            loaded = await self.storage.load_conversation(test_chat_id)
            await self.storage.clear_conversation(test_chat_id)
            health["storage_ok"] = bool(loaded)

            # Test roles
            health["roles_ok"] = len(self.roles) > 0

            # Test agent availability
            status = await self.get_agent_status()
            health["agents_available"] = any(status.values())

            # Test stateful sessions
            health["stateful_sessions_ok"] = (
                len(self.connector_sessions) >= 0
            )  # Basic check that sessions dict exists

        except Exception as e:
            self.logger.error(f"Health check failed: {e}")

        return health

    def get_agent_info(self, agent_name: str) -> Optional[Dict[str, str]]:
        """
        Get information about a specific agent by role.

        Args:
            agent_name: Name of the agent

        Returns:
            Optional[Dict[str, str]]: Agent information or None if not found
        """
        # Find role that uses this agent type
        for role in self.roles:
            if role.agent_type == agent_name:
                try:
                    connector = self._create_connector_for_role(role)
                    info = connector.get_info()
                    info.update(
                        {
                            "role_name": role.role_name,
                            "display_name": role.display_name,
                            "cli_command": role.cli_command,
                        }
                    )
                    return info
                except Exception as e:
                    self.logger.warning(f"Failed to get info for {agent_name}: {e}")
                    return None
        return None

    async def get_chat_agent_info(self, chat_id: int) -> Dict[str, Any]:
        """
        Get role information for a specific chat.

        Args:
            chat_id: Telegram chat ID

        Returns:
            Dict[str, Any]: Chat role information
        """
        try:
            current_role_index = self.chat_role_pointers.get(chat_id, 0)
            current_role = self.roles[current_role_index]
            current_agent_name = current_role.agent_type

            # Get next few roles that will be used
            next_roles = []
            for i in range(3):  # Show next 3 roles
                future_index = (current_role_index + i) % len(self.roles)
                role = self.roles[future_index]
                try:
                    connector = self._get_or_create_role_connector(chat_id, role)
                    role_info = {
                        "role_name": role.role_name,
                        "display_name": role.display_name,
                        "agent_name": role.agent_type,
                        "available": connector.check_availability(),
                        "next_in_sequence": i == 0,
                    }
                except Exception:
                    role_info = {
                        "role_name": role.role_name,
                        "display_name": role.display_name,
                        "agent_name": role.agent_type,
                        "available": False,
                        "next_in_sequence": i == 0,
                    }
                next_roles.append(role_info)

            return {
                "current_role": current_role.role_name,
                "current_agent": current_agent_name,
                "role_index": current_role_index,
                "next_roles": next_roles,
                "total_roles": len(self.roles),
            }

        except Exception as e:
            self.logger.error(f"Error getting chat role info: {e}")
            return {}

    def get_chat_agent_summary(self) -> Dict[str, Any]:
        """
        Get summary of role usage across all chats.

        Returns:
            Dict[str, Any]: Role usage summary
        """
        try:
            role_usage = {role.role_name: 0 for role in self.roles}
            total_chats_with_roles = len(self.chat_role_pointers)

            for role_index in self.chat_role_pointers.values():
                if 0 <= role_index < len(self.roles):
                    role = self.roles[role_index]
                    role_usage[role.role_name] += 1

            return {
                "active_chats": total_chats_with_roles,
                "role_usage": role_usage,
                "active_role_sessions": len(self.connector_sessions),
                "next_roles": {
                    role.role_name: (i + 1) % len(self.roles)
                    for i, role in enumerate(self.roles)
                },
            }

        except Exception as e:
            self.logger.error(f"Error getting chat role summary: {e}")
            return {}

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get performance metrics for the NeuroCrew Lab instance.

        Returns:
            Dict[str, Any]: Performance metrics
        """
        return self.metrics.copy()

    async def set_agent_sequence(self, chat_id: int, role_sequence: List[str]) -> bool:
        """
        Set custom role sequence for a specific chat.

        Args:
            chat_id: Telegram chat ID
            role_sequence: Custom role sequence (role names)

        Returns:
            bool: True if successful
        """
        try:
            # Validate role sequence
            valid_roles = {role.role_name: role for role in self.roles}
            for role_name in role_sequence:
                if role_name not in valid_roles:
                    self.logger.error(f"Invalid role in sequence: {role_name}")
                    return False

            # Store custom sequence (could extend storage to support this)
            # For now, just reset pointer to first role in custom sequence
            if role_sequence and role_sequence[0] in valid_roles:
                try:
                    target_role = valid_roles[role_sequence[0]]
                    first_role_index = self.roles.index(target_role)
                    self.chat_role_pointers[chat_id] = first_role_index
                    self.logger.info(
                        f"Set custom role sequence for chat {chat_id}, starting with {role_sequence[0]}"
                    )
                    return True
                except ValueError:
                    pass

            return False

        except Exception as e:
            self.logger.error(f"Error setting role sequence: {e}")
            return False

    async def skip_to_next_agent(self, chat_id: int) -> Optional[str]:
        """
        Skip to the next available agent for a chat.

        Args:
            chat_id: Telegram chat ID

        Returns:
            Optional[str]: Next agent name or None if no agents available
        """
        try:
            # Simply call _get_next_role to get the next role
            # This will advance the pointer and return the next available role
            role = await self._get_next_role(chat_id)
            return role.agent_type if role else None

        except Exception as e:
            self.logger.error(f"Error skipping to next role: {e}")
            return None

    def _get_or_create_role_connector(self, chat_id: int, role):
        """
        Get or create a stateful connector for a specific role.

        Args:
            chat_id: Telegram chat ID
            role: RoleConfig object for the role

        Returns:
            BaseConnector: Stateful connector for the role
        """
        role_name = role.role_name
        key = (chat_id, role_name)

        connector = self.connector_sessions.get(key)
        if connector:
            if connector.is_alive():
                return connector
            # Connector died, remove so we can recreate
            del self.connector_sessions[key]
            # Critical Fix: Reset memory index so new process gets full history
            if key in self.role_last_seen_index:
                self.role_last_seen_index[key] = 0
                self.logger.info(
                    f"Resetting context index for {role_name} due to process restart"
                )

        connector = self._create_connector_for_role(role)
        self.connector_sessions[key] = connector
        return connector

    def _create_connector_for_role(self, role):
        """
        Create a connector instance for a specific role.

        Args:
            role: RoleConfig object for the role

        Returns:
            BaseConnector: Connector instance
        """
        agent_type = role.agent_type.lower()

        connector_class = get_connector_class(agent_type)
        if not connector_class:
            raise ValueError(f"Unsupported agent type: {agent_type}")

        # Create connector with pure stateful interface
        return connector_class()

    async def perform_startup_introductions(self) -> List[Tuple[RoleConfig, str]]:
        """
        Performs a startup introduction sequence for all active roles.
        This creates a "prologue" in the conversation history by having each
        agent introduce itself. This history becomes the initial context for the first user query.

        Returns:
            List of tuples containing (RoleConfig, introduction_text) to be delivered to Telegram.
        """
        self.logger.info("=== STARTING AGENT INTRODUCTION SEQUENCE ===")
        introduction_prompt = "Hello! Please introduce yourself and briefly describe your role and capabilities."
        SYSTEM_CHAT_ID = 0  # A virtual chat_id for this system-level process
        introductions_for_delivery: List[Tuple[RoleConfig, str]] = []

        # 1. Clear previous conversation and state for the target chat
        if Config.TARGET_CHAT_ID:
            self.logger.info(
                f"Clearing conversation history for chat ID {Config.TARGET_CHAT_ID}..."
            )
            await self.storage.clear_conversation(Config.TARGET_CHAT_ID)
            await self._reset_chat_role_sessions(Config.TARGET_CHAT_ID)

        for role in self.roles:
            self.logger.info(f"Introducing role: {role.role_name}...")
            connector = None
            introduction_text = (
                f"Error: Could not get introduction from {role.display_name}."
            )

            try:
                # 2. Create a new temporary session for the agent to reset its context
                connector = self._get_or_create_role_connector(SYSTEM_CHAT_ID, role)
                if connector.is_alive():
                    await connector.shutdown()

                # 3. Launch the agent and get its introduction
                await connector.launch(role.cli_command, role.system_prompt)
                self.logger.info(f"Launched {role.role_name} for introduction.")

                response = await connector.execute(introduction_prompt)
                introduction_text = response.strip()
                self.logger.info(
                    f"Introduction from {role.role_name}: {introduction_text}"
                )

            except Exception as e:
                self.logger.error(
                    f"Failed to get introduction from {role.role_name}: {e}"
                )
            finally:
                # 4. Save introduction to conversation history
                agent_message = {
                    "role": "agent",
                    "agent_name": role.agent_type,
                    "role_name": role.role_name,
                    "role_display_name": role.display_name,
                    "content": introduction_text,
                    "timestamp": datetime.now().isoformat(),
                }
                if Config.TARGET_CHAT_ID:
                    await self.storage.add_message(Config.TARGET_CHAT_ID, agent_message)

                introductions_for_delivery.append((role, introduction_text))

                # 5. Shut down the temporary session
                if connector:
                    await connector.shutdown()
                    key = (SYSTEM_CHAT_ID, role.role_name)
                    if key in self.connector_sessions:
                        del self.connector_sessions[key]
                self.logger.info(
                    f"Session for {role.role_name} closed after introduction."
                )

        self.logger.info("=== AGENT INTRODUCTION SEQUENCE COMPLETE ===")
        return introductions_for_delivery

    async def shutdown_role_sessions(self):
        """Gracefully shutdown all role-based stateful sessions with reduced logging."""
        self.logger.info("Shutting down role sessions...")

        # Set shutdown flag to prevent new operations
        self._shutdown_in_progress = True

        total_sessions = len(self.connector_sessions)
        if total_sessions == 0:
            self.logger.info("No active role sessions to shutdown")
            return

        successful_shutdowns = 0

        try:
            # Create list of sessions to shutdown (avoid modification during iteration)
            sessions_to_shutdown = list(self.connector_sessions.items())

            for i, ((chat_id, role_name), connector) in enumerate(
                sessions_to_shutdown, 1
            ):
                try:
                    # Check if connector is still alive
                    if hasattr(connector, "is_alive") and connector.is_alive():
                        # Try graceful shutdown with reduced timeout
                        try:
                            await asyncio.wait_for(
                                connector.shutdown(),
                                timeout=3.0,  # Reduced from 10.0
                            )
                            successful_shutdowns += 1
                        except asyncio.TimeoutError:
                            # Force terminate if timeout - no verbose logging
                            try:
                                if hasattr(connector, "process") and connector.process:
                                    connector.process.terminate()
                                    await asyncio.sleep(0.5)  # Reduced wait time
                                    if connector.process.poll() is None:
                                        connector.process.kill()
                            except Exception as e:
                                self.logger.debug(
                                    f"Error during force termination of {role_name}: {str(e)}"
                                )
                    else:
                        successful_shutdowns += 1

                except Exception as e:
                    self.logger.debug(f"Exception shutting down {role_name}: {str(e)}")

                # Small delay between shutdowns to prevent overwhelming the system
                if i < len(sessions_to_shutdown):
                    await asyncio.sleep(0.05)  # Reduced from 0.1

        except Exception as e:
            self.logger.error(f"Critical error during role sessions shutdown: {e}")

        finally:
            # Clear all session data
            self.connector_sessions.clear()
            self.role_last_seen_index.clear()
            self._shutdown_in_progress = False

            # Simple summary logging
            if successful_shutdowns == total_sessions:
                self.logger.info(
                    f"All {total_sessions} role sessions shut down successfully"
                )
            else:
                self.logger.info(
                    f"Role sessions shutdown: {successful_shutdowns}/{total_sessions} successful"
                )

            self.logger.info("=== ROLE SESSIONS GRACEFUL SHUTDOWN COMPLETED ===")
