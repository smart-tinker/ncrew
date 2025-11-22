"""
Session Manager for NeuroCrew Lab.

Manages chat sessions, conversation history, and context tracking.
Handles session lifecycle and conversation state management.
"""

from datetime import datetime
from typing import Dict, List, Optional, Any

from app.config import Config, RoleConfig
from app.storage.file_storage import FileStorage
from app.core.memory_manager import MemoryManager
from app.utils.logger import get_logger
from app.utils.errors import (
    NCrewError,
    StorageError,
    ValidationError,
    handle_errors
)


class SessionManager:
    """
    Manages chat sessions and conversation history.

    Responsibilities:
    - Session lifecycle management
    - Conversation history tracking
    - Context index management for delta processing
    - Message persistence and retrieval
    - Session statistics and cleanup
    """

    def __init__(self, storage: FileStorage, memory_manager: MemoryManager):
        """
        Initialize Session Manager.

        Args:
            storage: File storage instance
            memory_manager: Memory manager instance
        """
        self.storage = storage
        self.memory_manager = memory_manager
        self.logger = get_logger(f"{self.__class__.__name__}")
        self._conversations_cleared = False

    async def initialize(self):
        """Initialize session manager and clear conversations on restart."""
        # Clear conversation histories on first message after restart to ensure new session
        if not self._conversations_cleared:
            await self._clear_all_conversations_on_restart()
            self._conversations_cleared = True

    @handle_errors(
        logger=None,  # will use self.logger
        context="message_addition",
        return_on_error=False
    )
    async def add_user_message(self, chat_id: int, user_text: str) -> bool:
        """
        Add a user message to the conversation.

        Args:
            chat_id: Telegram chat ID
            user_text: User message text

        Returns:
            bool: True if message was added successfully

        Raises:
            ValidationError: If message is empty
        """
        # Validate input
        if not user_text or not user_text.strip():
            raise ValidationError(
                "Empty message provided",
                field_name="user_text",
                value=user_text
            )

        # Add user message to conversation
        user_message = {
            "role": "user",
            "content": user_text,
            "timestamp": datetime.now().isoformat(),
        }

        success = await self.memory_manager.add_message(chat_id, user_message)
        if not success:
            self.logger.error("Failed to save user message")

        return success

    @handle_errors(
        logger=None,
        context="agent_message_addition",
        return_on_error=False
    )
    async def add_agent_message(
        self,
        chat_id: int,
        role: RoleConfig,
        response: str
    ) -> bool:
        """
        Add an agent message to the conversation.

        Args:
            chat_id: Telegram chat ID
            role: Role configuration
            response: Agent response text

        Returns:
            bool: True if message was added successfully
        """
        # Save agent response to conversation with role information
        agent_message = {
            "role": "agent",
            "agent_name": role.agent_type,
            "role_name": role.role_name,
            "role_display": role.display_name,
            "content": response,
            "timestamp": datetime.now().isoformat(),
        }

        success = await self.memory_manager.add_message(chat_id, agent_message)
        if success:
            # Update context index for this role
            self.memory_manager.increment_context_index(chat_id, role.role_name)

            # Create/update session in memory manager
            session = self.memory_manager.get_session(chat_id, role.role_name)
            if session:
                self.memory_manager.update_session(
                    chat_id=chat_id,
                    role_name=role.role_name,
                    message_count=session.message_count + 1
                )
            else:
                self.memory_manager.create_session(chat_id, role.role_name)
        else:
            self.logger.warning(f"Failed to save agent response for role {role.role_name}")

        return success

    async def get_conversation(self, chat_id: int) -> List[Dict[str, Any]]:
        """
        Get full conversation history for a chat.

        Args:
            chat_id: Telegram chat ID

        Returns:
            List[Dict[str, Any]]: Conversation messages
        """
        return await self.memory_manager.get_conversation(chat_id)

    async def get_conversation_delta(
        self,
        chat_id: int,
        role_name: str
    ) -> List[Dict[str, Any]]:
        """
        Get conversation messages that the role hasn't seen yet.

        Args:
            chat_id: Telegram chat ID
            role_name: Name of the role

        Returns:
            List[Dict[str, Any]]: New messages for the role
        """
        # Get full conversation history for context
        conversation = await self.memory_manager.get_conversation(chat_id)

        # Get context index for this role
        last_seen_index = self.memory_manager.get_context_index(chat_id, role_name)

        # Safety check: if index is out of bounds, reset to 0
        if last_seen_index < 0 or last_seen_index > len(conversation):
            self.logger.warning(
                f"Role {role_name}: invalid context index {last_seen_index}, "
                f"conversation size={len(conversation)}, resetting to 0"
            )
            self.memory_manager.set_context_index(chat_id, role_name, 0)
            last_seen_index = 0

        # Return new messages since the role's last response
        new_messages = conversation[last_seen_index:]

        # Enhanced delta tracking logging for debugging
        self.logger.info(
            f"🔄 DELTA: {role_name} (chat {chat_id}) - "
            f"index={last_seen_index}→{len(conversation)}, "
            f"getting {len(new_messages)} new messages"
        )

        # Log message previews for verification
        if new_messages:
            previews = []
            for msg in new_messages[:3]:  # First 3 messages
                role = msg.get('role', 'unknown')
                content = msg.get('content', '')[:30]
                previews.append(f"{role}:{content}...")
            self.logger.info(f"🔄 DELTA: {role_name} preview: {' | '.join(previews)}")
        elif last_seen_index < len(conversation):
            self.logger.warning(f"🔄 DELTA: {role_name} got empty delta despite index difference!")

        return new_messages

    def get_session_info(self, chat_id: int, role_name: str) -> Optional[Any]:
        """
        Get session information for a specific role in a chat.

        Args:
            chat_id: Telegram chat ID
            role_name: Name of the role

        Returns:
            Session information or None if not found
        """
        return self.memory_manager.get_session(chat_id, role_name)

    def should_add_system_reminder(self, chat_id: int, role_name: str) -> bool:
        """
        Check if system reminder should be added based on message count.

        Args:
            chat_id: Telegram chat ID
            role_name: Name of the role

        Returns:
            bool: True if system reminder should be added
        """
        session = self.memory_manager.get_session(chat_id, role_name)
        response_count = session.message_count if session else 0

        return (
            response_count > 0 and
            response_count % Config.SYSTEM_REMINDER_INTERVAL == 0
        )

    @handle_errors(
        logger=None,
        context="conversation_reset",
        return_on_error="❌ Failed to reset conversation"
    )
    async def reset_conversation(self, chat_id: int) -> str:
        """
        Reset conversation history for a chat.

        Args:
            chat_id: Telegram chat ID

        Returns:
            str: Confirmation message

        Raises:
            StorageError: If reset fails
        """
        # Clear conversation history using memory manager
        success = await self.memory_manager.clear_conversation(chat_id)

        if success:
            self.logger.info(f"Reset conversation for chat {chat_id}")
            return "🔄 Conversation reset successfully! Role sequence reset to start."
        else:
            self.logger.error(f"Failed to reset conversation for chat {chat_id}")
            raise StorageError(f"Failed to reset conversation for chat {chat_id}")

    async def reset_chat_sessions(self, chat_id: int) -> None:
        """
        Reset all session data for a specific chat.

        Args:
            chat_id: Telegram chat ID
        """
        # Memory manager sessions are automatically expired based on timeout
        self.logger.info(f"Reset sessions for chat {chat_id}")

    @handle_errors(
        logger=None,
        context="conversation_stats",
        return_on_error={}
    )
    async def get_conversation_stats(self, chat_id: int) -> Dict[str, Any]:
        """
        Get statistics for a conversation.

        Args:
            chat_id: Telegram chat ID

        Returns:
            Dict[str, Any]: Conversation statistics
        """
        # Get stats from memory manager
        stats = self.memory_manager.get_conversation_stats(chat_id)
        if not stats:
            return {
                "total_messages": 0,
                "user_messages": 0,
                "agent_messages": 0,
                "agent_counts": {},
                "last_message_time": None,
            }

        return {
            "total_messages": stats.total_messages,
            "user_messages": stats.user_messages,
            "agent_messages": stats.agent_messages,
            "agent_counts": stats.role_counts,
            "last_message_time": stats.last_message_time.isoformat() if stats.last_message_time else None,
        }

    async def _clear_all_conversations_on_restart(self):
        """Clear all conversation histories on application restart to ensure fresh session."""
        try:
            self.logger.info("🔄 Clearing all conversation histories for new session...")

            # Get all conversation stats from memory manager
            all_stats = self.memory_manager.get_all_conversation_stats()
            all_chat_ids = list(all_stats.keys())

            cleared_count = 0
            for chat_id in all_chat_ids:
                success = await self.memory_manager.clear_conversation(chat_id)
                if success:
                    cleared_count += 1
                    self.logger.debug(f"Cleared conversation for chat {chat_id}")
                else:
                    self.logger.warning(f"Failed to clear conversation for chat {chat_id}")

            self.logger.info(
                f"✅ Cleared {cleared_count}/{len(all_chat_ids)} conversation histories for new session"
            )

        except Exception as e:
            self.logger.error(f"Error clearing conversation histories on restart: {e}")
            # Don't fail initialization if cleanup fails
            pass

    def get_memory_stats(self) -> Dict[str, Any]:
        """
        Get memory manager statistics.

        Returns:
            Dict[str, Any]: Memory statistics
        """
        return self.memory_manager.get_memory_stats()

    async def shutdown(self):
        """Shutdown session manager and clean up resources."""
        self.logger.info("Shutting down session manager...")
        # Memory manager cleanup is handled by its own shutdown method