"""
Port Manager for NeuroCrew Lab - Connection Pool Optimization.

This module provides advanced connection pooling and resource management
for CLI agent processes with intelligent lifecycle management.
"""

import asyncio
import psutil
import signal
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Set, Any, Callable
from dataclasses import dataclass, field
from collections import defaultdict
import weakref

from app.connectors.base import BaseConnector
from app.config import RoleConfig
from app.utils.logger import get_logger
from app.utils.errors import NCrewError, PortError


@dataclass
class ConnectionInfo:
    """Information about a managed connection."""
    connector: BaseConnector
    chat_id: int
    role_name: str
    process_id: Optional[int] = None
    created_at: datetime = field(default_factory=datetime.now)
    last_used: datetime = field(default_factory=datetime.now)
    usage_count: int = 0
    is_pooled: bool = True
    health_score: float = 1.0
    error_count: int = 0
    last_error: Optional[datetime] = None

    def touch(self):
        """Update last used timestamp and increment usage."""
        self.last_used = datetime.now()
        self.usage_count += 1

    def is_healthy(self) -> bool:
        """Check if connection is healthy."""
        return (
            self.health_score > 0.5 and
            self.error_count < 3 and
            (self.last_error is None or
             datetime.now() - self.last_error > timedelta(minutes=5))
        )

    def is_expired(self, max_idle_minutes: int = 60) -> bool:
        """Check if connection is expired based on idle time."""
        return datetime.now() - self.last_used > timedelta(minutes=max_idle_minutes)


@dataclass
class PoolStats:
    """Statistics for the connection pool."""
    total_connections: int = 0
    active_connections: int = 0
    pooled_connections: int = 0
    expired_connections: int = 0
    unhealthy_connections: int = 0
    memory_usage_mb: float = 0.0
    cpu_usage_percent: float = 0.0
    avg_response_time_ms: float = 0.0
    last_cleanup: datetime = field(default_factory=datetime.now)


class ProcessMonitor:
    """Monitor system processes and resource usage."""

    def __init__(self):
        self.logger = get_logger(f"{self.__class__.__name__}")
        self.monitored_processes: Dict[int, Dict[str, Any]] = {}

    def add_process(self, process_id: int, chat_id: int, role_name: str):
        """Add a process to monitor."""
        try:
            process = psutil.Process(process_id)
            self.monitored_processes[process_id] = {
                "chat_id": chat_id,
                "role_name": role_name,
                "process": process,
                "added_at": datetime.now()
            }
            self.logger.debug(f"Started monitoring process {process_id} for chat {chat_id}, role {role_name}")
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            self.logger.warning(f"Could not monitor process {process_id}: {e}")

    def remove_process(self, process_id: int):
        """Remove a process from monitoring."""
        self.monitored_processes.pop(process_id, None)
        self.logger.debug(f"Stopped monitoring process {process_id}")

    def get_process_stats(self) -> Dict[str, Any]:
        """Get statistics for monitored processes."""
        if not self.monitored_processes:
            return {
                "total_processes": 0,
                "memory_usage_mb": 0.0,
                "cpu_usage_percent": 0.0,
                "active_processes": 0
            }

        total_memory = 0.0
        total_cpu = 0.0
        active_processes = 0

        for process_id, info in list(self.monitored_processes.items()):
            try:
                process = info["process"]
                if process.is_running():
                    memory_info = process.memory_info()
                    total_memory += memory_info.rss / 1024 / 1024  # Convert to MB
                    total_cpu += process.cpu_percent()
                    active_processes += 1
                else:
                    # Process has terminated
                    self.remove_process(process_id)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                self.remove_process(process_id)

        return {
            "total_processes": len(self.monitored_processes),
            "memory_usage_mb": total_memory,
            "cpu_usage_percent": total_cpu,
            "active_processes": active_processes
        }

    def cleanup_terminated_processes(self):
        """Remove terminated processes from monitoring."""
        terminated = []

        for process_id, info in list(self.monitored_processes.items()):
            try:
                process = info["process"]
                if not process.is_running():
                    terminated.append(process_id)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                terminated.append(process_id)

        for process_id in terminated:
            self.remove_process(process_id)

        if terminated:
            self.logger.debug(f"Cleaned up {len(terminated)} terminated processes")


class PortManager:
    """
    Advanced connection pool manager for CLI agent processes.

    Provides intelligent lifecycle management, health monitoring,
    and resource optimization for agent connections.
    """

    def __init__(
        self,
        max_pooled_connections: int = 20,
        max_connections_per_role: int = 3,
        connection_timeout_seconds: int = 600,
        health_check_interval: int = 60,
        cleanup_interval: int = 300
    ):
        """
        Initialize the Port Manager.

        Args:
            max_pooled_connections: Maximum total pooled connections
            max_connections_per_role: Maximum connections per role across all chats
            connection_timeout_seconds: Default timeout for connection operations
            health_check_interval: Seconds between health checks
            cleanup_interval: Seconds between cleanup cycles
        """
        self.max_pooled_connections = max_pooled_connections
        self.max_connections_per_role = max_connections_per_role
        self.connection_timeout_seconds = connection_timeout_seconds

        self.logger = get_logger(f"{self.__class__.__name__}")

        # Connection management
        self.connections: Dict[Tuple[int, str], ConnectionInfo] = {}
        self.role_connections: Dict[str, Set[Tuple[int, str]]] = defaultdict(set)
        self.process_connections: Dict[int, Tuple[int, str]] = {}

        # Process monitoring
        self.process_monitor = ProcessMonitor()

        # Statistics
        self.stats = PoolStats()

        # Background tasks
        self._health_check_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()

        # Response time tracking
        self.response_times: List[float] = []

    async def start(self):
        """Start the port manager and background tasks."""
        self.logger.info("Starting Port Manager...")
        self._health_check_task = asyncio.create_task(self._background_health_check())
        self._cleanup_task = asyncio.create_task(self._background_cleanup())

    async def stop(self):
        """Stop the port manager and cleanup all connections."""
        self.logger.info("Stopping Port Manager...")
        self._shutdown_event.set()

        # Cancel background tasks
        if self._health_check_task:
            self._health_check_task.cancel()
        if self._cleanup_task:
            self._cleanup_task.cancel()

        # Wait for tasks to finish
        try:
            await asyncio.gather(
                self._health_check_task,
                self._cleanup_task,
                return_exceptions=True
            )
        except Exception:
            pass

        # Cleanup all connections
        await self.cleanup_all_connections()

    # === Connection Management ===

    async def get_or_create_connection(
        self,
        chat_id: int,
        role_name: str,
        connector_factory: Callable[[], BaseConnector]
    ) -> BaseConnector:
        """
        Get existing connection or create new one with intelligent pooling.

        Args:
            chat_id: Telegram chat ID
            role_name: Role name for the connection
            connector_factory: Factory function to create new connector

        Returns:
            BaseConnector: Ready-to-use connector
        """
        connection_key = (chat_id, role_name)

        # Try to get existing connection
        if connection_key in self.connections:
            conn_info = self.connections[connection_key]
            if (conn_info.is_healthy() and
                conn_info.connector.is_alive() and
                getattr(conn_info.connector, '_initialized', True)):
                conn_info.touch()
                self.logger.debug(f"Reusing existing connection for chat {chat_id}, role {role_name}")
                return conn_info.connector
            else:
                # Connection is unhealthy, remove it
                self.logger.debug(f"Removing unhealthy/uninitialized connection for chat {chat_id}, role {role_name}")
                await self._remove_connection(connection_key)

        # Check connection limits
        await self._enforce_connection_limits(role_name)

        # Create new connection
        connector = connector_factory()
        conn_info = ConnectionInfo(
            connector=connector,
            chat_id=chat_id,
            role_name=role_name
        )

        self.connections[connection_key] = conn_info
        self.role_connections[role_name].add(connection_key)

        self.logger.info(f"Created new connection for chat {chat_id}, role {role_name}")
        self._update_stats()

        return connector

    async def launch_connection(
        self,
        chat_id: int,
        role_name: str,
        command: str,
        system_prompt: str,
        connector_factory: Callable[[], BaseConnector]
    ) -> BaseConnector:
        """
        Launch a new connection with command and system prompt.

        Args:
            chat_id: Telegram chat ID
            role_name: Role name for the connection
            command: CLI command to execute
            system_prompt: System prompt to send to the agent
            connector_factory: Factory function to create new connector

        Returns:
            BaseConnector: Launched connector
        """
        start_time = time.time()

        try:
            connector = await self.get_or_create_connection(chat_id, role_name, connector_factory)
            await connector.launch(command, system_prompt)

            # Update connection info and process monitoring
            connection_key = (chat_id, role_name)
            if connection_key in self.connections:
                conn_info = self.connections[connection_key]
                if hasattr(connector, 'process') and connector.process:
                    process_id = connector.process.pid
                    conn_info.process_id = process_id
                    self.process_connections[process_id] = connection_key
                    self.process_monitor.add_process(process_id, chat_id, role_name)

            # Track response time
            response_time = (time.time() - start_time) * 1000
            self._track_response_time(response_time)

            self.logger.info(f"Launched connection for chat {chat_id}, role {role_name}")
            return connector

        except Exception as e:
            self.logger.error(f"Failed to launch connection for chat {chat_id}, role {role_name}: {e}")
            # Record error in connection info if it exists
            connection_key = (chat_id, role_name)
            if connection_key in self.connections:
                self._record_connection_error(connection_key)
            raise

    async def execute_with_connection(
        self,
        chat_id: int,
        role_name: str,
        prompt: str,
        connector_factory: Callable[[], BaseConnector]
    ) -> str:
        """
        Execute a prompt with connection management and timeout handling.

        Args:
            chat_id: Telegram chat ID
            role_name: Role name for the connection
            prompt: Prompt to execute
            connector_factory: Factory function to create new connector

        Returns:
            str: Response from the agent
        """
        start_time = time.time()

        try:
            connector = await self.get_or_create_connection(chat_id, role_name, connector_factory)

            # Execute with timeout
            response = await asyncio.wait_for(
                connector.execute(prompt),
                timeout=self.connection_timeout_seconds
            )

            # Track response time
            response_time = (time.time() - start_time) * 1000
            self._track_response_time(response_time)

            return response

        except asyncio.TimeoutError:
            self.logger.warning(f"Execution timeout for chat {chat_id}, role {role_name}")
            # Remove problematic connection to prevent reuse of dead connectors
            connection_key = (chat_id, role_name)
            try:
                await self._remove_connection(connection_key)
                self.logger.debug(f"Removed timed-out connection for chat {chat_id}, role {role_name}")
            except Exception as cleanup_error:
                self.logger.error(f"Failed to cleanup timed-out connection: {cleanup_error}")
            raise
        except Exception as e:
            self.logger.error(f"Execution error for chat {chat_id}, role {role_name}: {e}")
            # Remove problematic connection to prevent reuse
            connection_key = (chat_id, role_name)
            try:
                await self._remove_connection(connection_key)
                self.logger.debug(f"Removed failed connection for chat {chat_id}, role {role_name}")
            except Exception as cleanup_error:
                self.logger.error(f"Failed to cleanup failed connection: {cleanup_error}")
            raise

    async def remove_connection(self, chat_id: int, role_name: str) -> bool:
        """
        Remove a specific connection and cleanup resources.

        Args:
            chat_id: Telegram chat ID
            role_name: Role name

        Returns:
            bool: True if connection was removed
        """
        connection_key = (chat_id, role_name)
        return await self._remove_connection(connection_key)

    async def _remove_connection(self, connection_key: Tuple[int, str]) -> bool:
        """Internal method to remove a connection by key."""
        if connection_key not in self.connections:
            return False

        chat_id, role_name = connection_key
        conn_info = self.connections.pop(connection_key)

        try:
            # Shutdown connector
            await conn_info.connector.shutdown()

            # Remove from mappings
            self.role_connections[role_name].discard(connection_key)
            if not self.role_connections[role_name]:
                del self.role_connections[role_name]

            # Remove process monitoring
            if conn_info.process_id:
                self.process_connections.pop(conn_info.process_id, None)
                self.process_monitor.remove_process(conn_info.process_id)

            self.logger.debug(f"Removed connection for chat {chat_id}, role {role_name}")
            self._update_stats()
            return True

        except Exception as e:
            self.logger.error(f"Error removing connection for chat {chat_id}, role {role_name}: {e}")
            return False

    async def cleanup_chat_connections(self, chat_id: int) -> int:
        """
        Remove all connections for a specific chat.

        Args:
            chat_id: Telegram chat ID

        Returns:
            int: Number of connections removed
        """
        connections_to_remove = [
            (c_chat_id, role_name) for c_chat_id, role_name in self.connections.keys()
            if c_chat_id == chat_id
        ]

        removed_count = 0
        for c_chat_id, role_name in connections_to_remove:
            if await self.remove_connection(c_chat_id, role_name):
                removed_count += 1

        if removed_count > 0:
            self.logger.info(f"Cleaned up {removed_count} connections for chat {chat_id}")

        return removed_count

    async def cleanup_all_connections(self) -> int:
        """
        Remove all connections.

        Returns:
            int: Number of connections removed
        """
        all_connections = list(self.connections.keys())
        removed_count = 0

        for chat_id, role_name in all_connections:
            if await self.remove_connection(chat_id, role_name):
                removed_count += 1

        self.logger.info(f"Cleaned up all {removed_count} connections")
        return removed_count

    # === Health Monitoring ===

    async def check_connection_health(self, chat_id: int, role_name: str) -> bool:
        """
        Check health of a specific connection.

        Args:
            chat_id: Telegram chat ID
            role_name: Role name

        Returns:
            bool: True if connection is healthy
        """
        connection_key = (chat_id, role_name)
        conn_info = self.connections.get(connection_key)

        if not conn_info:
            return False

        try:
            # Basic health checks
            is_healthy = (
                conn_info.connector.is_alive() and
                conn_info.is_healthy()
            )

            # Update health score
            if is_healthy:
                conn_info.health_score = min(1.0, conn_info.health_score + 0.1)
            else:
                conn_info.health_score = max(0.0, conn_info.health_score - 0.2)

            return is_healthy

        except Exception as e:
            self.logger.warning(f"Health check error for chat {chat_id}, role {role_name}: {e}")
            self._record_connection_error(connection_key)
            return False

    async def health_check_all_connections(self) -> Dict[str, int]:
        """
        Perform health check on all connections.

        Returns:
            Dict[str, int]: Health check results
        """
        healthy_count = 0
        unhealthy_count = 0

        for connection_key in list(self.connections.keys()):
            chat_id, role_name = connection_key
            if await self.check_connection_health(chat_id, role_name):
                healthy_count += 1
            else:
                unhealthy_count += 1

        return {
            "healthy": healthy_count,
            "unhealthy": unhealthy_count,
            "total": len(self.connections)
        }

    # === Statistics and Monitoring ===

    def get_stats(self) -> PoolStats:
        """
        Get comprehensive pool statistics.

        Returns:
            PoolStats: Current pool statistics
        """
        self._update_stats()
        return self.stats

    def get_connection_info(self, chat_id: int, role_name: str) -> Optional[ConnectionInfo]:
        """
        Get information about a specific connection.

        Args:
            chat_id: Telegram chat ID
            role_name: Role name

        Returns:
            Optional[ConnectionInfo]: Connection information
        """
        return self.connections.get((chat_id, role_name))

    def get_all_connections(self) -> List[ConnectionInfo]:
        """
        Get information about all connections.

        Returns:
            List[ConnectionInfo]: List of all connection information
        """
        return list(self.connections.values())

    def _record_connection_error(self, connection_key: Tuple[int, str]):
        """Record an error for a connection."""
        if connection_key in self.connections:
            conn_info = self.connections[connection_key]
            conn_info.error_count += 1
            conn_info.last_error = datetime.now()
            conn_info.health_score = max(0.0, conn_info.health_score - 0.3)

    def _track_response_time(self, response_time_ms: float):
        """Track response time for statistics."""
        self.response_times.append(response_time_ms)
        # Keep only last 100 measurements
        if len(self.response_times) > 100:
            self.response_times = self.response_times[-100:]

    def _update_stats(self):
        """Update internal statistics."""
        total_connections = len(self.connections)
        active_connections = sum(
            1 for conn in self.connections.values()
            if conn.connector.is_alive() and conn.is_healthy()
        )
        pooled_connections = sum(
            1 for conn in self.connections.values()
            if conn.is_pooled
        )

        # Get process stats
        process_stats = self.process_monitor.get_process_stats()

        # Calculate average response time
        avg_response_time = 0.0
        if self.response_times:
            avg_response_time = sum(self.response_times) / len(self.response_times)

        self.stats = PoolStats(
            total_connections=total_connections,
            active_connections=active_connections,
            pooled_connections=pooled_connections,
            expired_connections=0,  # Will be updated in cleanup
            unhealthy_connections=total_connections - active_connections,
            memory_usage_mb=process_stats["memory_usage_mb"],
            cpu_usage_percent=process_stats["cpu_usage_percent"],
            avg_response_time_ms=avg_response_time,
            last_cleanup=datetime.now()
        )

    async def _enforce_connection_limits(self, role_name: str):
        """Enforce connection limits for a role."""
        role_conns = self.role_connections.get(role_name, set())
        active_conns = [
            key for key in role_conns
            if key in self.connections and self.connections[key].is_healthy()
        ]

        if len(active_conns) >= self.max_connections_per_role:
            # Remove oldest unhealthy connection
            oldest_key = None
            oldest_time = datetime.now()

            for key in active_conns:
                conn_info = self.connections[key]
                if conn_info.last_used < oldest_time:
                    oldest_time = conn_info.last_used
                    oldest_key = key

            if oldest_key:
                await self._remove_connection(oldest_key)
                self.logger.debug(f"Enforced connection limit for role {role_name}")

    # === Background Tasks ===

    async def _background_health_check(self):
        """Background task for periodic health checks."""
        self.logger.debug("Started background health check task")

        while not self._shutdown_event.is_set():
            try:
                await asyncio.sleep(60)  # Health check every minute

                if self._shutdown_event.is_set():
                    break

                await self.health_check_all_connections()
                self.process_monitor.cleanup_terminated_processes()

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Background health check error: {e}")

        self.logger.debug("Background health check task stopped")

    async def _background_cleanup(self):
        """Background task for periodic cleanup."""
        self.logger.debug("Started background cleanup task")

        while not self._shutdown_event.is_set():
            try:
                await asyncio.sleep(300)  # Cleanup every 5 minutes

                if self._shutdown_event.is_set():
                    break

                # Remove expired connections
                expired_connections = []
                current_time = datetime.now()

                for key, conn_info in list(self.connections.items()):
                    if conn_info.is_expired():
                        expired_connections.append(key)

                for key in expired_connections:
                    await self._remove_connection(key)
                    chat_id, role_name = key
                    self.logger.debug(f"Cleaned up expired connection for chat {chat_id}, role {role_name}")

                if expired_connections:
                    self.logger.info(f"Cleaned up {len(expired_connections)} expired connections")

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Background cleanup error: {e}")

        self.logger.debug("Background cleanup task stopped")