"""
Memory Manager for NeuroCrew Lab - Optimized Agent Context Tracking.

This module provides sophisticated memory management for agent sessions,
conversation history, and context tracking with performance optimization.
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass, field
from collections import defaultdict, OrderedDict
import weakref
from pathlib import Path

from app.config import RoleConfig
from app.storage.file_storage import FileStorage
from app.utils.logger import get_logger
from app.utils.errors import NCrewError, MemoryError


@dataclass
class SessionInfo:
    """Information about an active agent session."""
    chat_id: int
    role_name: str
    process_id: Optional[int] = None
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    message_count: int = 0
    context_index: int = 0
    is_active: bool = True

    def touch(self):
        """Update last activity timestamp."""
        self.last_activity = datetime.now()

    def is_expired(self, timeout_minutes: int = 30) -> bool:
        """Check if session is expired based on inactivity."""
        return datetime.now() - self.last_activity > timedelta(minutes=timeout_minutes)


@dataclass
class ConversationStats:
    """Statistics for a conversation."""
    chat_id: int
    total_messages: int = 0
    user_messages: int = 0
    agent_messages: int = 0
    last_message_time: Optional[datetime] = None
    role_counts: Dict[str, int] = field(default_factory=dict)

    def update(self, message: Dict[str, Any]):
        """Update stats with a new message."""
        self.total_messages += 1
        self.last_message_time = datetime.now()

        if message.get("role") == "user":
            self.user_messages += 1
        elif message.get("role") == "agent":
            self.agent_messages += 1
            role_name = message.get("role_name", "unknown")
            self.role_counts[role_name] = self.role_counts.get(role_name, 0) + 1


class LRUOrderedDict(OrderedDict):
    """LRU Cache with maximum size and expiration."""

    def __init__(self, maxsize: int = 128, ttl_seconds: int = 3600):
        super().__init__()
        self.maxsize = maxsize
        self.ttl_seconds = ttl_seconds
        self.timestamps = {}

    def _is_expired(self, key):
        """Check if an entry has expired."""
        if key not in self.timestamps:
            return True
        return time.time() - self.timestamps[key] > self.ttl_seconds

    def _cleanup_expired(self):
        """Remove expired entries."""
        expired_keys = [k for k in self.keys() if self._is_expired(k)]
        for k in expired_keys:
            self.pop(k, None)
            self.timestamps.pop(k, None)

    def __setitem__(self, key, value):
        """Set item with LRU eviction and expiration."""
        self._cleanup_expired()

        if key in self:
            self.move_to_end(key)
        else:
            if len(self) >= self.maxsize:
                oldest_key = next(iter(self))
                self.pop(oldest_key, None)
                self.timestamps.pop(oldest_key, None)

        super().__setitem__(key, value)
        self.timestamps[key] = time.time()

    def __getitem__(self, key):
        """Get item and update its position."""
        if key not in self or self._is_expired(key):
            raise KeyError(key)

        self.move_to_end(key)
        self.timestamps[key] = time.time()
        return super().__getitem__(key)


class MemoryManager:
    """
    Advanced memory management for NeuroCrew Lab.

    Optimizes agent context tracking, session management, and conversation
    history with intelligent caching and cleanup strategies.
    """

    def __init__(
        self,
        storage: FileStorage,
        max_sessions_per_chat: int = 5,
        max_cached_conversations: int = 100,
        session_timeout_minutes: int = 30,
        context_cache_ttl: int = 3600
    ):
        """
        Initialize the Memory Manager.

        Args:
            storage: File storage instance for conversation persistence
            max_sessions_per_chat: Maximum active sessions per chat
            max_cached_conversations: Maximum conversations to cache in memory
            session_timeout_minutes: Minutes of inactivity before session expiration
            context_cache_ttl: Time-to-live for context cache entries in seconds
        """
        self.storage = storage
        self.max_sessions_per_chat = max_sessions_per_chat
        self.session_timeout_minutes = session_timeout_minutes
        self.logger = get_logger(f"{self.__class__.__name__}")

        # Session management with optimized indexing
        self.sessions: Dict[Tuple[int, str], SessionInfo] = {}
        self.chat_sessions: Dict[int, Set[Tuple[int, str]]] = defaultdict(set)
        self.process_mapping: Dict[int, Tuple[int, str]] = {}  # pid -> (chat_id, role_name)

        # Conversation caching with LRU eviction
        self.conversation_cache = LRUOrderedDict(
            maxsize=max_cached_conversations,
            ttl_seconds=context_cache_ttl
        )

        # Conversation statistics
        self.conversation_stats: Dict[int, ConversationStats] = {}

        # Memory usage tracking
        self.memory_stats = {
            "total_sessions": 0,
            "active_sessions": 0,
            "cached_conversations": 0,
            "memory_usage_mb": 0.0,
            "last_cleanup": datetime.now()
        }

        # Cleanup task
        self._cleanup_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()

    async def start(self):
        """Start the memory manager and background cleanup task."""
        self.logger.info("Starting Memory Manager...")
        self._cleanup_task = asyncio.create_task(self._background_cleanup())

    async def stop(self):
        """Stop the memory manager and cleanup resources."""
        self.logger.info("Stopping Memory Manager...")
        self._shutdown_event.set()

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        await self.cleanup_all_sessions()

    # === Session Management ===

    def create_session(
        self,
        chat_id: int,
        role_name: str,
        process_id: Optional[int] = None
    ) -> SessionInfo:
        """
        Create a new agent session with intelligent resource management.

        Args:
            chat_id: Telegram chat ID
            role_name: Role name for the session
            process_id: Process ID if process is already started

        Returns:
            SessionInfo: Created session information
        """
        # Check session limits
        existing_sessions = self.chat_sessions[chat_id]
        if len(existing_sessions) >= self.max_sessions_per_chat:
            # Remove oldest inactive session
            self._evict_oldest_session(chat_id)

        # Create new session
        session_key = (chat_id, role_name)
        session = SessionInfo(
            chat_id=chat_id,
            role_name=role_name,
            process_id=process_id
        )

        self.sessions[session_key] = session
        self.chat_sessions[chat_id].add(session_key)

        if process_id:
            self.process_mapping[process_id] = session_key

        self._update_memory_stats()
        self.logger.debug(f"Created session for chat {chat_id}, role {role_name}")

        return session

    def get_session(self, chat_id: int, role_name: str) -> Optional[SessionInfo]:
        """
        Get an existing session.

        Args:
            chat_id: Telegram chat ID
            role_name: Role name

        Returns:
            Optional[SessionInfo]: Session if found and active
        """
        session_key = (chat_id, role_name)
        session = self.sessions.get(session_key)

        if session and session.is_active and not session.is_expired(self.session_timeout_minutes):
            session.touch()
            return session

        return None

    def get_session_by_process(self, process_id: int) -> Optional[SessionInfo]:
        """
        Get session by process ID.

        Args:
            process_id: Process ID

        Returns:
            Optional[SessionInfo]: Session if found
        """
        session_key = self.process_mapping.get(process_id)
        if session_key:
            return self.sessions.get(session_key)
        return None

    def update_session(
        self,
        chat_id: int,
        role_name: str,
        process_id: Optional[int] = None,
        message_count: Optional[int] = None,
        context_index: Optional[int] = None
    ):
        """
        Update session information.

        Args:
            chat_id: Telegram chat ID
            role_name: Role name
            process_id: New process ID (optional)
            message_count: New message count (optional)
            context_index: New context index (optional)
        """
        session_key = (chat_id, role_name)
        session = self.sessions.get(session_key)

        if session:
            session.touch()
            if process_id is not None:
                # Remove old process mapping
                if session.process_id:
                    self.process_mapping.pop(session.process_id, None)

                session.process_id = process_id
                if process_id:
                    self.process_mapping[process_id] = session_key

            if message_count is not None:
                session.message_count = message_count

            if context_index is not None:
                session.context_index = context_index

    def remove_session(self, chat_id: int, role_name: str) -> bool:
        """
        Remove a session and clean up resources.

        Args:
            chat_id: Telegram chat ID
            role_name: Role name

        Returns:
            bool: True if session was removed
        """
        session_key = (chat_id, role_name)
        session = self.sessions.pop(session_key, None)

        if session:
            # Clean up mappings
            self.chat_sessions[chat_id].discard(session_key)
            if self.chat_sessions[chat_id]:
                del self.chat_sessions[chat_id]

            if session.process_id:
                self.process_mapping.pop(session.process_id, None)

            self.logger.debug(f"Removed session for chat {chat_id}, role {role_name}")
            self._update_memory_stats()
            return True

        return False

    def get_chat_sessions(self, chat_id: int) -> List[SessionInfo]:
        """
        Get all sessions for a chat.

        Args:
            chat_id: Telegram chat ID

        Returns:
            List[SessionInfo]: List of active sessions
        """
        session_keys = self.chat_sessions.get(chat_id, set())
        sessions = []

        for key in session_keys:
            session = self.sessions.get(key)
            if session and session.is_active and not session.is_expired(self.session_timeout_minutes):
                sessions.append(session)

        return sessions

    # === Conversation Management ===

    async def get_conversation(self, chat_id: int, use_cache: bool = True) -> List[Dict[str, Any]]:
        """
        Get conversation with intelligent caching.

        Args:
            chat_id: Telegram chat ID
            use_cache: Whether to use cached conversation

        Returns:
            List[Dict[str, Any]]: Conversation history
        """
        if use_cache and chat_id in self.conversation_cache:
            try:
                return self.conversation_cache[chat_id]
            except KeyError:
                pass

        # Load from storage
        conversation = await self.storage.load_conversation(chat_id)

        # Cache the result
        if use_cache:
            self.conversation_cache[chat_id] = conversation

        # Update statistics
        if chat_id not in self.conversation_stats:
            self.conversation_stats[chat_id] = ConversationStats(chat_id=chat_id)

        # Recalculate stats
        stats = self.conversation_stats[chat_id]
        stats.total_messages = len(conversation)
        stats.user_messages = sum(1 for msg in conversation if msg.get("role") == "user")
        stats.agent_messages = sum(1 for msg in conversation if msg.get("role") == "agent")
        stats.role_counts = {}
        for msg in conversation:
            if msg.get("role") == "agent":
                role_name = msg.get("role_name", "unknown")
                stats.role_counts[role_name] = stats.role_counts.get(role_name, 0) + 1

        if conversation:
            stats.last_message_time = datetime.fromisoformat(conversation[-1].get("timestamp", datetime.now().isoformat()))

        return conversation

    async def add_message(self, chat_id: int, message: Dict[str, Any]) -> bool:
        """
        Add a message to conversation and update caches.

        Args:
            chat_id: Telegram chat ID
            message: Message to add

        Returns:
            bool: True if message was added successfully
        """
        success = await self.storage.add_message(chat_id, message)

        if success:
            # Invalidate cache for this chat
            self.conversation_cache.pop(chat_id, None)

            # Update statistics
            if chat_id not in self.conversation_stats:
                self.conversation_stats[chat_id] = ConversationStats(chat_id=chat_id)

            self.conversation_stats[chat_id].update(message)

        return success

    async def clear_conversation(self, chat_id: int) -> bool:
        """
        Clear conversation and clean up related data.

        Args:
            chat_id: Telegram chat ID

        Returns:
            bool: True if conversation was cleared
        """
        success = await self.storage.clear_conversation(chat_id)

        if success:
            # Clear caches and stats
            self.conversation_cache.pop(chat_id, None)
            self.conversation_stats.pop(chat_id, None)

            # Clear all session context indices for this chat
            for session_key, session in list(self.sessions.items()):
                if session_key[0] == chat_id:
                    session.context_index = 0

        return success

    # === Context Management ===

    def get_context_index(self, chat_id: int, role_name: str) -> int:
        """
        Get the current context index for a role.

        Args:
            chat_id: Telegram chat ID
            role_name: Role name

        Returns:
            int: Current context index
        """
        session = self.get_session(chat_id, role_name)
        return session.context_index if session else 0

    def set_context_index(self, chat_id: int, role_name: str, index: int):
        """
        Set the context index for a role.

        Args:
            chat_id: Telegram chat ID
            role_name: Role name
            index: New context index
        """
        self.update_session(chat_id, role_name, context_index=index)

    def increment_context_index(self, chat_id: int, role_name: int) -> int:
        """
        Increment context index for a role.

        Args:
            chat_id: Telegram chat ID
            role_name: Role name

        Returns:
            int: New context index
        """
        session = self.get_session(chat_id, role_name)
        if session:
            session.context_index += 1
            session.touch()
            return session.context_index

        # Create new session if it doesn't exist
        new_session = self.create_session(chat_id, role_name)
        new_session.context_index = 1
        return 1

    # === Statistics and Monitoring ===

    def get_memory_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive memory statistics.

        Returns:
            Dict[str, Any]: Memory usage statistics
        """
        self._update_memory_stats()
        return self.memory_stats.copy()

    def get_conversation_stats(self, chat_id: int) -> Optional[ConversationStats]:
        """
        Get statistics for a specific conversation.

        Args:
            chat_id: Telegram chat ID

        Returns:
            Optional[ConversationStats]: Conversation statistics
        """
        return self.conversation_stats.get(chat_id)

    def get_all_conversation_stats(self) -> Dict[int, ConversationStats]:
        """
        Get statistics for all conversations.

        Returns:
            Dict[int, ConversationStats]: All conversation statistics
        """
        return self.conversation_stats.copy()

    def _update_memory_stats(self):
        """Update internal memory statistics."""
        active_sessions = sum(
            1 for s in self.sessions.values()
            if s.is_active and not s.is_expired(self.session_timeout_minutes)
        )

        total_memory_mb = (
            len(self.sessions) * 0.1 +  # Approximate session memory
            len(self.conversation_cache) * 0.5 +  # Approximate conversation cache
            len(self.conversation_stats) * 0.1  # Approximate stats memory
        )

        self.memory_stats.update({
            "total_sessions": len(self.sessions),
            "active_sessions": active_sessions,
            "cached_conversations": len(self.conversation_cache),
            "memory_usage_mb": total_memory_mb,
            "last_cleanup": datetime.now()
        })

    # === Cleanup and Maintenance ===

    def _evict_oldest_session(self, chat_id: int):
        """
        Remove the oldest inactive session for a chat.

        Args:
            chat_id: Telegram chat ID
        """
        session_keys = list(self.chat_sessions.get(chat_id, set()))
        if not session_keys:
            return

        # Find oldest inactive session
        oldest_session = None
        oldest_time = datetime.now()

        for key in session_keys:
            session = self.sessions.get(key)
            if session and session.last_activity < oldest_time:
                oldest_time = session.last_activity
                oldest_session = key

        if oldest_session:
            self.remove_session(oldest_session[0], oldest_session[1])

    async def cleanup_expired_sessions(self):
        """Remove expired sessions."""
        expired_sessions = []

        for key, session in list(self.sessions.items()):
            if session.is_expired(self.session_timeout_minutes):
                expired_sessions.append(key)

        for chat_id, role_name in expired_sessions:
            self.remove_session(chat_id, role_name)
            self.logger.debug(f"Cleaned up expired session for chat {chat_id}, role {role_name}")

    async def cleanup_all_sessions(self):
        """Remove all sessions."""
        all_sessions = list(self.sessions.keys())
        for chat_id, role_name in all_sessions:
            self.remove_session(chat_id, role_name)

        self.logger.info("Cleaned up all sessions")

    async def _background_cleanup(self):
        """Background task for periodic cleanup."""
        self.logger.debug("Started background cleanup task")

        while not self._shutdown_event.is_set():
            try:
                await asyncio.sleep(300)  # Cleanup every 5 minutes

                if self._shutdown_event.is_set():
                    break

                await self.cleanup_expired_sessions()
                self._update_memory_stats()

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Background cleanup error: {e}")

        self.logger.debug("Background cleanup task stopped")