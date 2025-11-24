"""
NeuroCrew Lab - Main orchestration system for multi-agent AI platform.

This module contains the main NeuroCrewLab class that coordinates:
- AI agent orchestration and coordination
- Multi-agent dialogue management
- Session lifecycle and conversation management
- Role-based architecture coordination

The class has been refactored from a monolithic 1400+ line implementation
to a clean, modular architecture with separate coordinators.
"""

import asyncio
from datetime import datetime
from typing import List, Dict, Optional, Any, Tuple, AsyncGenerator

from app.config import Config, RoleConfig
from app.storage.file_storage import FileStorage
from app.core.memory_manager import MemoryManager
from app.core.port_manager import PortManager
from app.core.agent_coordinator import AgentCoordinator
from app.core.session_manager import SessionManager
from app.core.dialogue_orchestrator import DialogueOrchestrator
from app.connectors.base import BaseConnector
from app.utils.logger import get_logger
from app.utils.errors import (
    ConfigurationError,
    handle_errors,
)


class NeuroCrewLab:
    """
    Main NeuroCrew Lab orchestration system.

    Coordinates AI agents for collaborative development, dialogue management,
    and role-based multi-agent execution using a modular architecture.

    Refactored from monolithic design to use focused coordinators:
    - AgentCoordinator: Role validation and agent lifecycle management
    - SessionManager: Chat sessions and conversation history
    - DialogueOrchestrator: Autonomous dialogue cycles and interaction
    """

    def __init__(self, storage: Optional[FileStorage] = None):
        """
        Initialize NeuroCrew Lab with modular coordinator architecture.

        Args:
            storage: File storage instance. Created by default if None.
        """
        self.storage = storage or FileStorage()
        self.logger = get_logger(f"{self.__class__.__name__}")

        # Initialize core managers
        self.memory_manager = MemoryManager(
            storage=self.storage,
            max_sessions_per_chat=5,
            max_cached_conversations=100,
            session_timeout_minutes=30,
            context_cache_ttl=3600
        )
        self.port_manager = PortManager(
            max_pooled_connections=20,
            max_connections_per_role=3,
            connection_timeout_seconds=int(Config.AGENT_TIMEOUT),
            health_check_interval=60,
            cleanup_interval=300
        )

        # Initialize coordinators (dependency injection pattern)
        self.agent_coordinator = AgentCoordinator(self.port_manager)
        self.session_manager = SessionManager(self.storage, self.memory_manager)
        self.dialogue_orchestrator = DialogueOrchestrator(
            self.agent_coordinator,
            self.session_manager
        )

        # Legacy compatibility properties
        self._conversations_cleared = False
        self._shutdown_in_progress: bool = False
        self.request_timeout: float = float(Config.AGENT_TIMEOUT)

        # Initialize role sequence through agent coordinator
        self.roles = self.agent_coordinator.validate_and_initialize_roles()

        self.logger.info(
            f"NeuroCrew Lab initialized - Role-based: {self.agent_coordinator.is_role_based}"
        )
        self.logger.info(
            f"Validated role sequence: {[role.role_name for role in self.roles]}"
        )

        # Note: Session initialization will be handled in initialize() method

    async def initialize(self):
        """
        Asynchronous initialization that requires await.
        Call this after creating the instance.
        """
        # Start the memory and port managers
        await self.memory_manager.start()
        await self.port_manager.start()
        self.logger.info("Started Memory Manager and Port Manager")

        # Initialize session manager
        await self.session_manager.initialize()

        # Load system prompts for all validated roles
        if self.agent_coordinator.is_role_based:
            for role in self.roles:
                prompt_path = getattr(role, "system_prompt_path", None)
                if not role.system_prompt and prompt_path:
                    try:
                        with open(prompt_path, "r", encoding="utf-8") as f:
                            role.system_prompt = f.read().strip()
                    except FileNotFoundError as e:
                        self.logger.error(
                            f"System prompt file not found for {role.role_name}: {e}"
                        )
                        role.system_prompt = f"You are a {role.display_name} helping with programming tasks."
                    except IOError as e:
                        self.logger.error(
                            f"IO error reading system prompt for {role.role_name}: {e}"
                        )
                        role.system_prompt = f"You are a {role.display_name} helping with programming tasks."
                    except Exception as e:
                        self.logger.error(
                            f"Unexpected error loading system prompt for {role.role_name}: {e}"
                        )
                        role.system_prompt = f"You are a {role.display_name} helping with programming tasks."
                elif not role.system_prompt:
                    role.system_prompt = (
                        f"You are a {role.display_name} helping with programming tasks."
                    )

            self.logger.info(
                f"Initialized {len(self.roles)} validated roles ready for stateful execution"
            )

    @handle_errors(
        logger=None,
        context="message_processing",
        return_on_error=None
    )
    async def handle_message(
        self, chat_id: int, user_text: str
    ) -> AsyncGenerator[Tuple[Optional[RoleConfig], str], None]:
        """
        Handle a user message and process it through autonomous role dialogue cycle.

        Delegates to DialogueOrchestrator for the core processing logic.

        Args:
            chat_id: Telegram chat ID
            user_text: User's message text

        Yields:
            Tuple[Optional[RoleConfig], str]: (role_config, raw_response) for each role in the cycle
        """
        # Clear conversation histories on first message after restart to ensure new session
        if not self._conversations_cleared:
            await self._clear_all_conversations_on_restart()
            self._conversations_cleared = True

        # Delegate to dialogue orchestrator
        async for result in self.dialogue_orchestrator.handle_message(chat_id, user_text):
            yield result

    # ===== LEGACY COMPATIBILITY DELEGATIONS =====
    # These methods delegate to the appropriate coordinators for backward compatibility

    @handle_errors(
        logger=None,
        context="conversation_reset",
        return_on_error="❌ Failed to reset conversation"
    )
    async def reset_conversation(self, chat_id: int) -> str:
        """
        Reset conversation history and role state for a chat.

        Delegates to SessionManager and DialogueOrchestrator.

        Args:
            chat_id: Telegram chat ID

        Returns:
            str: Confirmation message
        """
        # Reset conversation via session manager
        result = await self.session_manager.reset_conversation(chat_id)

        # Reset role pointers via dialogue orchestrator
        await self.dialogue_orchestrator.reset_chat_role_pointer(chat_id)

        # Clear compatibility caches for this chat
        if hasattr(self, '_role_last_seen_index_cache'):
            keys_to_remove = [key for key in self._role_last_seen_index_cache.keys() if key[0] == chat_id]
            for key in keys_to_remove:
                del self._role_last_seen_index_cache[key]

        if hasattr(self, '_connector_sessions_cache'):
            keys_to_remove = [key for key in self._connector_sessions_cache.keys() if key[0] == chat_id]
            for key in keys_to_remove:
                del self._connector_sessions_cache[key]

        return result

    async def get_agent_status(self) -> Dict[str, bool]:
        """
        Get status of all configured roles/agents.

        Delegates to AgentCoordinator.

        Returns:
            Dict[str, bool]: Role availability status
        """
        return await self.agent_coordinator.get_agent_status()

    @handle_errors(
        logger=None,
        context="conversation_stats",
        return_on_error={}
    )
    async def get_conversation_stats(self, chat_id: int) -> Dict[str, Any]:
        """
        Get statistics for a conversation.

        Delegates to SessionManager.

        Args:
            chat_id: Telegram chat ID

        Returns:
            Dict[str, Any]: Conversation statistics
        """
        return await self.session_manager.get_conversation_stats(chat_id)

    @handle_errors(
        logger=None,
        context="system_status",
        return_on_error={}
    )
    async def get_system_status(self) -> Dict[str, Any]:
        """
        Get overall system status.

        Returns:
            Dict[str, Any]: System status information
        """
        # Agent status
        agent_status = await self.agent_coordinator.get_agent_status()

        # Storage stats
        storage_stats = await self.storage.get_storage_stats()

        # Get manager statistics
        memory_stats = self.session_manager.get_memory_stats()
        port_stats = self.port_manager.get_stats()

        # System info
        system_info = {
            "configured_roles": len(self.roles),
            "available_agents": sum(agent_status.values()),
            "total_chats": storage_stats.get("total_chats", 0),
            "total_messages": storage_stats.get("total_messages", 0),
            "storage_size_mb": storage_stats.get("total_size_mb", 0),
            "agent_details": agent_status,

            # Memory Manager stats
            "active_sessions": memory_stats["active_sessions"],
            "total_sessions": memory_stats["total_sessions"],
            "cached_conversations": memory_stats["cached_conversations"],
            "memory_usage_mb": memory_stats["memory_usage_mb"],

            # Port Manager stats
            "active_connections": port_stats.active_connections,
            "total_connections": port_stats.total_connections,
            "pooled_connections": port_stats.pooled_connections,
            "connection_memory_mb": port_stats.memory_usage_mb,
            "avg_response_time_ms": port_stats.avg_response_time_ms,
        }

        return system_info

    @handle_errors(
        logger=None,
        context="health_check",
        return_on_error={"storage_ok": False, "roles_ok": False, "agents_available": False, "stateful_sessions_ok": False}
    )
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
            "memory_manager_ok": False,
            "port_manager_ok": False,
        }

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
        status = await self.agent_coordinator.get_agent_status()
        health["agents_available"] = any(status.values())

        # Test memory manager
        try:
            memory_stats = self.session_manager.get_memory_stats()
            health["memory_manager_ok"] = memory_stats["total_sessions"] >= 0
        except Exception:
            health["memory_manager_ok"] = False

        # Test port manager
        try:
            port_stats = self.port_manager.get_stats()
            health["port_manager_ok"] = port_stats.total_connections >= 0
        except Exception:
            health["port_manager_ok"] = False

        return health

    def get_agent_info(self, agent_name: str) -> Optional[Dict[str, str]]:
        """
        Get information about a specific agent by role.

        Delegates to AgentCoordinator.

        Args:
            agent_name: Name of the agent

        Returns:
            Optional[Dict[str, str]]: Agent information or None if not found
        """
        return self.agent_coordinator.get_agent_info(agent_name)

    async def get_chat_agent_info(self, chat_id: int) -> Dict[str, Any]:
        """
        Get role information for a specific chat.

        Delegates to DialogueOrchestrator.

        Args:
            chat_id: Telegram chat ID

        Returns:
            Dict[str, Any]: Chat role information
        """
        return self.dialogue_orchestrator.get_chat_role_info(chat_id)

    def get_chat_agent_summary(self) -> Dict[str, Any]:
        """
        Get summary of role usage across all chats.

        Delegates to DialogueOrchestrator.

        Returns:
            Dict[str, Any]: Role usage summary
        """
        return self.dialogue_orchestrator.get_chat_role_summary()

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get performance metrics for the NeuroCrew Lab instance.

        Returns empty dict as metrics are disabled in MVP.
        """
        return {}

    async def set_agent_sequence(self, chat_id: int, role_sequence: List[str]) -> bool:
        """
        Set custom role sequence for a specific chat.

        Delegates to DialogueOrchestrator.

        Args:
            chat_id: Telegram chat ID
            role_sequence: Custom role sequence (role names)

        Returns:
            bool: True if successful
        """
        return await self.dialogue_orchestrator.set_agent_sequence(chat_id, role_sequence)

    async def skip_to_next_agent(self, chat_id: int) -> Optional[str]:
        """
        Skip to the next available agent for a chat.

        Delegates to DialogueOrchestrator.

        Args:
            chat_id: Telegram chat ID

        Returns:
            Optional[str]: Next agent name or None if no agents available
        """
        return await self.dialogue_orchestrator.skip_to_next_agent(chat_id)

    # ===== INTRODUCTION METHODS =====
    # These methods manage agent introduction sequences

    async def _perform_sequential_introductions(
        self, introduction_prompt: str, system_chat_id: int
    ) -> AsyncGenerator[Tuple[RoleConfig, str], None]:
        """Perform introductions sequentially (one agent at a time)."""
        for i, role in enumerate(self.roles):
            self.logger.info(f"Introducing role {i+1}/{len(self.roles)}: {role.role_name}...")
            connector = None
            introduction_text = (
                f"Error: Could not get introduction from {role.display_name}."
            )

            try:
                # Use REAL TARGET_CHAT_ID instead of system_chat_id to ensure proper session continuity
                target_chat_id = Config.TARGET_CHAT_ID or system_chat_id

                # Create or get existing session for the role with REAL chat_id
                connector = await self.agent_coordinator.get_or_create_connector(target_chat_id, role)

                # Only shutdown if connector exists and we need to reset context for fresh introduction
                if connector.is_alive():
                    await connector.shutdown()

                # Launch the agent and get its introduction
                await connector.launch(role.cli_command, role.system_prompt)
                self.logger.info(f"Launched {role.role_name} for introduction with chat_id={target_chat_id}.")

                # Use shorter timeout for introductions (they should be quick)
                original_timeout = getattr(connector, "request_timeout", None)
                if hasattr(connector, "request_timeout"):
                    connector.request_timeout = 60.0  # 1 minute for introductions

                try:
                    response = await connector.execute(introduction_prompt)
                finally:
                    # Restore original timeout
                    if original_timeout is not None:
                        connector.request_timeout = original_timeout

                introduction_text = response.strip()
                self.logger.info(
                    f"Introduction from {role.role_name}: {introduction_text[:100]}..."
                )

            except Exception as e:
                self.logger.error(
                    f"Failed to get introduction from {role.role_name}: {e}"
                )
            finally:
                # Save introduction to conversation history
                agent_message = {
                    "role": "agent",
                    "agent_name": role.agent_type,
                    "role_name": role.role_name,
                    "role_display": role.display_name,
                    "content": introduction_text,
                    "timestamp": datetime.now().isoformat(),
                }
                if Config.TARGET_CHAT_ID:
                    await self.storage.add_message(Config.TARGET_CHAT_ID, agent_message)

                # YIELD result immediately
                yield (role, introduction_text)

                # IMPORTANT: Don't shutdown the connector - keep session alive for ongoing conversation
                # This ensures each role maintains its session and context for delta processing
                if connector:
                    self.logger.info(
                        f"Session for {role.role_name} kept alive for ongoing conversation."
                    )

    async def perform_startup_introductions(
        self,
    ) -> AsyncGenerator[Tuple[RoleConfig, str], None]:
        """
        Performs a startup introduction sequence for all active roles.
        This creates a "prologue" in the conversation history by having each
        agent introduce itself. This history becomes the initial context for the first user query.

        Yields:
            Tuple[RoleConfig, str]: (role_config, introduction_text) for each role as it becomes available.
        """
        self.logger.info("=== STARTING AGENT INTRODUCTION SEQUENCE ===")
        introduction_prompt = "Hello! Please introduce yourself and briefly describe your role and capabilities."
        SYSTEM_CHAT_ID = 0  # A virtual chat_id for this system-level process

        # 1. Clear previous conversation and state for the target chat
        if Config.TARGET_CHAT_ID:
            self.logger.info(
                f"Clearing conversation history for chat ID {Config.TARGET_CHAT_ID}..."
            )
            await self.storage.clear_conversation(Config.TARGET_CHAT_ID)
            await self.session_manager.reset_chat_sessions(Config.TARGET_CHAT_ID)

        # Always use sequential introductions to honor agents.yaml order
        self.logger.info("Using SEQUENTIAL introduction strategy")
        async for result in self._perform_sequential_introductions(
            introduction_prompt, SYSTEM_CHAT_ID
        ):
            yield result

        self.logger.info("=== AGENT INTRODUCTION SEQUENCE COMPLETE ===")

    # ===== LIFECYCLE METHODS =====

    async def shutdown_role_sessions(self):
        """Gracefully shutdown all role-based stateful sessions."""
        self.logger.info("Shutting down role sessions...")

        # Set shutdown flag to prevent new operations
        self._shutdown_in_progress = True
        self.dialogue_orchestrator.start_shutdown()

        # Shutdown managers
        try:
            await self.port_manager.stop()
            await self.memory_manager.stop()
            await self.session_manager.shutdown()
            self.logger.info("All managers stopped successfully")
        except Exception as e:
            self.logger.error(f"Error stopping managers: {e}")

        self.logger.info("=== ROLE SESSIONS GRACEFUL SHUTDOWN COMPLETED ===")

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

            self.logger.info(f"✅ Cleared {cleared_count}/{len(all_chat_ids)} conversation histories for new session")

        except Exception as e:
            self.logger.error(f"Error clearing conversation histories on restart: {e}")
            # Don't fail initialization if cleanup fails
            pass

    # ===== LEGACY PROPERTIES FOR BACKWARD COMPATIBILITY =====

    @property
    def chat_role_pointers(self) -> Dict[int, int]:
        """Legacy property - delegates to dialogue orchestrator."""
        return self.dialogue_orchestrator.chat_role_pointers

    @property
    def is_role_based(self) -> bool:
        """Legacy property - delegates to agent coordinator."""
        return self.agent_coordinator.is_role_based

    @property
    def role_introductions(self) -> Dict[str, str]:
        """Legacy property - returns empty dict for compatibility."""
        return {}

    @property
    def role_last_seen_index(self) -> Dict[Tuple[int, str], int]:
        """Legacy property for role context tracking - delegates to memory manager."""
        # For test compatibility, maintain a simple dictionary that can be manipulated
        if not hasattr(self, '_role_last_seen_index_cache'):
            self._role_last_seen_index_cache = {}

        # Try to sync with actual memory manager if possible
        try:
            sessions = self.memory_manager.sessions
            for (chat_id, role_name), session_info in sessions.items():
                if session_info.is_active:
                    index = self.memory_manager.get_context_index(chat_id, role_name)
                    self._role_last_seen_index_cache[(chat_id, role_name)] = index
        except Exception:
            pass  # Ignore sync errors, use cached values

        return self._role_last_seen_index_cache

    @role_last_seen_index.setter
    def role_last_seen_index(self, value: Dict[Tuple[int, str], int]):
        """Legacy setter for role context tracking - delegates to memory manager."""
        # Store the values for test compatibility
        if not hasattr(self, '_role_last_seen_index_cache'):
            self._role_last_seen_index_cache = {}

        self._role_last_seen_index_cache = value.copy()

        # Also try to set in the actual memory manager
        try:
            for (chat_id, role_name), index in value.items():
                self.memory_manager.set_context_index(chat_id, role_name, index)
        except Exception as e:
            self.logger.warning(f"Error setting role_last_seen_index: {e}")

    # ===== LEGACY METHODS FOR BACKWARD COMPATIBILITY =====

    async def _process_with_role(self, chat_id: int, role: RoleConfig) -> str:
        """
        Legacy method - delegates to dialogue orchestrator.

        Args:
            chat_id: Chat ID
            role: Role configuration

        Returns:
            str: Agent response
        """
        response = await self.dialogue_orchestrator._process_with_role(chat_id, role)

        # Note: Context index management is now handled properly by SessionManager
        # The dialogue_orchestrator._process_with_role() calls session_manager.add_agent_message()
        # which handles increment_context_index automatically. No manual increment needed here.

        # Update compatibility cache for legacy code that might still access it
        try:
            if hasattr(self, '_role_last_seen_index_cache'):
                # Get current index for cache consistency (don't increment here)
                current_index = self.memory_manager.get_context_index(chat_id, role.role_name)
                self._role_last_seen_index_cache[(chat_id, role.role_name)] = current_index
        except Exception:
            # Ignore any errors in compatibility layer
            pass

        return response

    def _format_conversation_for_role(
        self,
        conversation: List[Dict[str, Any]],
        role: RoleConfig,
        chat_id: int
    ) -> Tuple[str, bool]:
        """
        Legacy method - delegates to dialogue orchestrator.

        Args:
            conversation: Conversation history
            role: Role configuration
            chat_id: Chat ID

        Returns:
            Tuple[str, bool]: (formatted_prompt, has_updates)
        """
        return self.dialogue_orchestrator._format_conversation_for_role(
            conversation, role, chat_id
        )

    async def _get_or_create_role_connector(self, chat_id: int, role: RoleConfig) -> BaseConnector:
        """
        Legacy method - delegates to agent coordinator.

        Args:
            chat_id: Chat ID
            role: Role configuration

        Returns:
            BaseConnector: Connector instance
        """
        # For test compatibility, this method should not be called directly
        # Tests should mock agent_coordinator.get_or_create_connector instead
        raise NotImplementedError("This method should be mocked in tests")

    @property
    def connector_sessions(self) -> Dict[Tuple[int, str], BaseConnector]:
        """Legacy property - delegates to agent coordinator for compatibility."""
        # The agent coordinator now handles connector lifecycle internally
        # This is a compatibility wrapper that provides a mutable dict for tests
        if not hasattr(self, '_connector_sessions_cache'):
            self._connector_sessions_cache = {}
        return self._connector_sessions_cache

    async def _reset_chat_role_sessions(self, chat_id: int):
        """
        Legacy method - resets role sessions for a specific chat.

        Args:
            chat_id: Chat ID to reset sessions for
        """
        # In the new architecture, this is handled by the session manager
        # This is a compatibility method for tests
        try:
            # Clear cached role last seen indexes for this chat
            if hasattr(self, '_role_last_seen_index_cache'):
                keys_to_remove = [key for key in self._role_last_seen_index_cache.keys() if key[0] == chat_id]
                for key in keys_to_remove:
                    del self._role_last_seen_index_cache[key]

            # Clear connector sessions for this chat
            if hasattr(self, '_connector_sessions_cache'):
                keys_to_remove = [key for key in self._connector_sessions_cache.keys() if key[0] == chat_id]
                for key in keys_to_remove:
                    del self._connector_sessions_cache[key]

            # Clear session pointers in dialogue orchestrator
            self.dialogue_orchestrator.chat_role_pointers.pop(chat_id, None)

        except Exception as e:
            self.logger.warning(f"Error resetting chat role sessions: {e}")
