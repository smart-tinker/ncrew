"""
Dialogue Orchestrator for NeuroCrew Lab.

Manages autonomous dialogue cycles, role coordination, and conversation flow.
Handles message processing and agent interaction orchestration.
"""

from typing import Dict, List, Optional, Any, Tuple, AsyncGenerator

from app.config import RoleConfig
from app.core.agent_coordinator import AgentCoordinator
from app.core.session_manager import SessionManager
from app.utils.logger import get_logger
from app.utils.errors import (
    NCrewError,
    handle_errors
)


class DialogueOrchestrator:
    """
    Orchestrates autonomous dialogue between AI agents.

    Responsibilities:
    - Autonomous dialogue cycle management
    - Role selection and coordination
    - Message processing flow control
    - Agent interaction sequencing
    - Dialogue termination logic
    """

    def __init__(
        self,
        agent_coordinator: AgentCoordinator,
        session_manager: SessionManager
    ):
        """
        Initialize Dialogue Orchestrator.

        Args:
            agent_coordinator: Agent coordinator instance
            session_manager: Session manager instance
        """
        self.agent_coordinator = agent_coordinator
        self.session_manager = session_manager
        self.logger = get_logger(f"{self.__class__.__name__}")

        # Role-based mode state management
        self.chat_role_pointers: Dict[int, int] = {}  # chat_id -> role_index
        self._shutdown_in_progress: bool = False

    @handle_errors(
        logger=None,  # will use self.logger
        context="message_processing",
        return_on_error=None
    )
    async def handle_message(
        self,
        chat_id: int,
        user_text: str
    ) -> AsyncGenerator[Tuple[Optional[RoleConfig], str], None]:
        """
        Handle a user message and process it through continuous autonomous role dialogue cycle.

        Args:
            chat_id: Telegram chat ID
            user_text: User's message text

        Yields:
            Tuple[Optional[RoleConfig], str]: (role_config, raw_response) for each role in the cycle
        """
        self.logger.info(
            f"Starting continuous autonomous dialogue cycle for chat {chat_id}: {user_text[:100]}..."
        )

        # Add user message via session manager
        success = await self.session_manager.add_user_message(chat_id, user_text)
        if not success:
            yield (None, "❌ Error: Could not save your message")
            return

        # Run the autonomous cycle
        async for result in self._run_autonomous_cycle(chat_id):
            yield result

    async def _run_autonomous_cycle(
        self, chat_id: int
    ) -> AsyncGenerator[Tuple[Optional[RoleConfig], str], None]:
        """
        Execute the autonomous dialogue cycle where agents talk to each other.

        The cycle continues until all agents have "passed" (responded with ".....").

        Args:
            chat_id: Telegram chat ID

        Yields:
            Tuple[Optional[RoleConfig], str]: (role_config, raw_response) for each response
        """
        roles = self.agent_coordinator.get_roles()
        self.logger.info(f"Starting continuous cycle with {len(roles)} validated roles")

        cycle_count = 0
        consecutive_empty_responses = 0  # Count consecutive "....." responses
        consecutive_error_responses = 0

        while True:
            if self._shutdown_in_progress:
                self.logger.info(f"Shutdown requested, stopping dialogue cycle for chat {chat_id}")
                break

            cycle_count += 1
            self.logger.debug(f"--- Cycle {cycle_count} ---")

            # Get next role using round-robin pointer
            current_role_index = self.chat_role_pointers.get(chat_id, 0)
            if current_role_index >= len(roles):
                current_role_index = 0
                self.chat_role_pointers[chat_id] = 0

            role_config = roles[current_role_index]
            self.logger.debug(f"Activating role {cycle_count}: {role_config.role_name}")

            # Process with current role
            self.logger.debug(
                f"Chat {chat_id}: invoking process_with_role for {role_config.role_name}"
            )

            try:
                raw_response = await self._process_with_role(chat_id, role_config)
            except Exception as e:
                self.logger.error(f"Error processing with role {role_config.role_name}: {e}")
                raw_response = f"❌ Error processing with {role_config.role_name}: {e}"

            # Update pointer for next cycle
            self.chat_role_pointers[chat_id] = (current_role_index + 1) % len(roles)

            # Check for termination condition
            # 1. Moderator (e.g. Scrum Master) can stop the cycle immediately
            if raw_response.strip() == "....." and getattr(
                role_config, "is_moderator", False
            ):
                self.logger.info(
                    f"Moderator role {role_config.role_name} ended the dialogue. Cycle stopped immediately."
                )
                break

            # 2. Standard termination: exactly 5 dots from everyone consecutively
            if raw_response.strip() == ".....":
                consecutive_empty_responses += 1
                consecutive_error_responses = 0
                self.logger.info(
                    f"Role {role_config.role_name} has nothing to add ({consecutive_empty_responses}/{len(roles)})."
                )

                # If ALL agents consecutively responded with ".....", end the dialogue
                if consecutive_empty_responses >= len(roles):
                    self.logger.info(
                        f"All {len(roles)} agents finished dialogue. Cycle stopped."
                    )
                    break
                else:
                    # Continue cycle, but don't send response to Telegram
                    continue

            # Reset counter when we get meaningful response
            consecutive_empty_responses = 0

            # Check for error responses - they don't count towards termination
            if (
                raw_response.startswith("❌ Error:") or
                raw_response == "I'm sorry, I don't have a response for that."
            ):
                self.logger.warning(
                    f"Role {role_config.role_name} returned error response. Continuing to next role."
                )
                consecutive_error_responses += 1
                yield (role_config, raw_response)

                if consecutive_error_responses >= len(roles):
                    self.logger.error("All roles returned error responses in this cycle. Stopping dialogue.")
                    break
                continue
            else:
                consecutive_error_responses = 0

            # Yield the response for Telegram sending (only meaningful responses)
            yield (role_config, raw_response)

        self.logger.info(
            f"Continuous autonomous cycle completed after {cycle_count} iterations for chat {chat_id}"
        )

    @handle_errors(
        logger=None,  # will use self.logger
        context="role_processing",
        return_on_error="❌ Error processing message"
    )
    async def _process_with_role(self, chat_id: int, role: RoleConfig) -> str:
        """
        Process message through a specific role using stateful connectors.

        Args:
            chat_id: Telegram chat ID
            role: Role configuration for the role to process with

        Returns:
            str: Role's raw response
        """
        self.logger.info(f"Processing with role: {role.role_name}")

        # Get conversation delta for this role
        new_messages = await self.session_manager.get_conversation_delta(chat_id, role.role_name)

        # Format conversation for this role
        role_prompt, has_updates = self._format_conversation_for_role(
            new_messages, role, chat_id
        )

        if has_updates:
            # Get connector and execute
            connector = await self.agent_coordinator.get_or_create_connector(chat_id, role)

            # Check availability and launch if needed
            if not connector.is_alive():
                try:
                    await connector.launch(role.cli_command, role.system_prompt)
                    self.logger.info(f"Launched role process: {role.role_name}")
                except Exception as e:
                    self.logger.error(f"Failed to launch role {role.role_name}: {e}")
                    return f"❌ Error: Failed to launch {role.role_name}"

            # Execute the prompt
            try:
                response = await connector.execute(role_prompt)
                self.logger.info(f"Role {role.role_name} responded successfully")
            except Exception as e:
                self.logger.error(f"Error executing prompt with role {role.role_name}: {e}")
                return f"❌ Error: {role.role_name} failed to process message"

            # Save agent response via session manager
            await self.session_manager.add_agent_message(chat_id, role, response)

            return response
        else:
            # No new updates, return placeholder
            self.logger.debug(
                f"Chat {chat_id}: no new updates for {role.role_name}, responding with placeholder"
            )
            return "....."

    def _format_conversation_for_role(
        self,
        new_messages: List[Dict[str, Any]],
        role: RoleConfig,
        chat_id: int
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
            self.logger.debug(
                f"Role {role.role_name} (chat {chat_id}): no new messages, returning placeholder"
            )
            return ".....", False

        # Filter out placeholder responses
        filtered_messages = []
        for msg in new_messages:
            content = (msg.get("content") or "").strip()
            if content == ".....":
                continue
            filtered_messages.append(msg)

        if not filtered_messages:
            self.logger.debug(
                f"Role {role.role_name} (chat {chat_id}): all {len(new_messages)} new messages were placeholders, returning placeholder"
            )
            return ".....", False

        # Log filtered messages for debugging
        self.logger.debug(
            f"Role {role.role_name} (chat {chat_id}): "
            f"filtered {len(new_messages)} new messages down to {len(filtered_messages)} meaningful messages"
        )

        # Build conversation context from all new messages
        context_lines: List[str] = []
        for msg in filtered_messages:
            if msg.get("role") == "user":
                content = msg.get("content", "")
                context_lines.append(f"User: {content}")
            elif msg.get("role") == "agent":
                agent_name = msg.get(
                    "role_display", msg.get("role_name", "Assistant")
                )
                content = msg.get("content", "")
                context_lines.append(f"Assistant ({agent_name}): {content}")

        conversation_context = "\n\n".join(context_lines)

        # Check if we need system reminder
        if self.session_manager.should_add_system_reminder(chat_id, role.role_name):
            # Add system reminder with team work instruction
            # Use [SYSTEM REMINDER] instead of --- to avoid CLI flag parsing issues
            team_instruction = (
                f"\n[TEAM WORK INSTRUCTION]\n"
                f"ВАЖНО: Вы работаете в команде других AI-специалистов.\n"
                f"Ваша роль: {role.display_name} ({role.role_name})\n"
                f"Отвечайте ТОЛЬКО за свою область экспертизы\n"
                f"Сообщения от других участников команды - это контекст для вашей работы\n"
                f"НЕ отвечайте за других агентов, даже если они молчат\n"
                f"Если нет содержательного дополнения - используйте \".....\"\n"
                f"[END TEAM INSTRUCTION]\n\n"
            )
            system_reminder = (
                f"[SYSTEM REMINDER]\n{role.system_prompt}\n[END REMINDER]\n\n"
            )
            conversation_context = system_reminder + team_instruction + conversation_context

        prompt = conversation_context
        return prompt, True

    async def reset_chat_role_pointer(self, chat_id: int):
        """
        Reset role pointer for a specific chat.

        Args:
            chat_id: Telegram chat ID
        """
        if chat_id in self.chat_role_pointers:
            del self.chat_role_pointers[chat_id]
            self.logger.debug(f"Reset role pointer for chat {chat_id}")

    def set_chat_role_pointer(self, chat_id: int, role_index: int):
        """
        Set role pointer for a specific chat.

        Args:
            chat_id: Telegram chat ID
            role_index: Role index to set
        """
        roles = self.agent_coordinator.get_roles()
        if 0 <= role_index < len(roles):
            self.chat_role_pointers[chat_id] = role_index
            self.logger.debug(f"Set role pointer for chat {chat_id} to index {role_index}")

    def get_chat_role_info(self, chat_id: int) -> Dict[str, Any]:
        """
        Get role information for a specific chat.

        Args:
            chat_id: Telegram chat ID

        Returns:
            Dict[str, Any]: Chat role information
        """
        try:
            roles = self.agent_coordinator.get_roles()
            current_role_index = self.chat_role_pointers.get(chat_id, 0)
            current_role = roles[current_role_index]
            current_agent_name = current_role.agent_type

            return {
                "current_role": current_role.role_name,
                "current_agent": current_agent_name,
                "role_index": current_role_index,
                "total_roles": len(roles),
            }

        except Exception as e:
            self.logger.error(f"Error getting chat role info: {e}")
            return {}

    def get_chat_role_summary(self) -> Dict[str, Any]:
        """
        Get summary of role usage across all chats.

        Returns:
            Dict[str, Any]: Role usage summary
        """
        try:
            roles = self.agent_coordinator.get_roles()
            role_usage = {role.role_name: 0 for role in roles}
            total_chats_with_roles = len(self.chat_role_pointers)

            for role_index in self.chat_role_pointers.values():
                if 0 <= role_index < len(roles):
                    role = roles[role_index]
                    role_usage[role.role_name] += 1

            return {
                "active_chats": total_chats_with_roles,
                "role_usage": role_usage,
                "total_roles": len(roles),
                "next_roles": {
                    role.role_name: (i + 1) % len(roles)
                    for i, role in enumerate(roles)
                },
            }

        except Exception as e:
            self.logger.error(f"Error getting chat role summary: {e}")
            return {}

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
            valid_roles = {role.role_name: role for role in self.agent_coordinator.get_roles()}
            for role_name in role_sequence:
                if role_name not in valid_roles:
                    self.logger.error(f"Invalid role in sequence: {role_name}")
                    return False

            # Store custom sequence (could extend storage to support this)
            # For now, just reset pointer to first role in custom sequence
            if role_sequence and role_sequence[0] in valid_roles:
                try:
                    target_role = valid_roles[role_sequence[0]]
                    first_role_index = self.agent_coordinator.get_roles().index(target_role)
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
            roles = self.agent_coordinator.get_roles()
            current_pointer = self.chat_role_pointers.get(chat_id, 0)
            next_pointer = (current_pointer + 1) % len(roles)
            self.chat_role_pointers[chat_id] = next_pointer

            next_role = roles[next_pointer]
            return next_role.agent_type

        except Exception as e:
            self.logger.error(f"Error skipping to next role: {e}")
            return None

    def start_shutdown(self):
        """Start shutdown process."""
        self._shutdown_in_progress = True

    def cancel_shutdown(self):
        """Cancel shutdown process."""
        self._shutdown_in_progress = False