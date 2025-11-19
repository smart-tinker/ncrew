"""
Base connector class for AI coding agents.

This module provides the abstract base class for pure stateful connectors
that manage long-lived CLI agent processes.
"""

import asyncio
import time
from abc import ABC, abstractmethod
from typing import Optional
from app.utils.logger import get_logger


class BaseConnector(ABC):
    """
    Abstract base class for PURE STATEFUL connectors to CLI agents.

    This class defines the pure stateful interface that all connectors
    must implement to manage long-lived CLI agent processes.
    """

    def __init__(self):
        """
        Initialize the pure stateful connector.

        No legacy parameters accepted - clean, minimal interface.
        """
        # Pure stateful interface properties
        self.process: Optional[asyncio.subprocess.Process] = None
        self.logger = get_logger(f"{self.__class__.__name__}")

    # === PURE STATEFUL INTERFACE ===

    @abstractmethod
    async def launch(self, command: str, system_prompt: str):
        """
        Launch CLI process in interactive mode and send system prompt.
        Stores the process in self.process.

        Args:
            command: CLI command to execute
            system_prompt: Initial system prompt to send to the process
        """
        pass

    @abstractmethod
    async def execute(self, delta_prompt: str) -> str:
        """
        Send new dialogue delta to the launched process and return response.

        Args:
            delta_prompt: New prompt/input to send to the process

        Returns:
            str: Response from the agent
        """
        pass

    @abstractmethod
    def check_availability(self) -> bool:
        """
        Check if the connector and its CLI agent are available.

        Returns:
            bool: True if available
        """
        pass

    async def shutdown(self):
        """
        Gracefully shutdown the CLI process with enhanced error handling.
        """
        if not self.process:
            return

        if self.process.returncode is not None:
            self.logger.debug(
                f"Process {self.process.pid} already terminated with code {self.process.returncode}"
            )
            self.process = None
            return

        self.logger.info(f"Shutting down process {self.process.pid}...")
        try:
            # Try graceful termination first
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
                self.logger.info(f"Process {self.process.pid} terminated gracefully.")
            except asyncio.TimeoutError:
                # Force kill if graceful termination fails
                self.logger.warning(
                    f"Process {self.process.pid} did not terminate, force killing..."
                )
                self.process.kill()
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=2.0)
                    self.logger.info(f"Process {self.process.pid} force killed.")
                except asyncio.TimeoutError:
                    self.logger.error(
                        f"Process {self.process.pid} could not be killed, orphaned process may exist"
                    )
        except (ProcessLookupError, RuntimeError) as e:
            # Process might have already terminated or event loop closed
            self.logger.info(
                f"Process {self.process.pid} already terminated or event loop closed: {e}"
            )
        except Exception as e:
            self.logger.error(f"Error shutting down process {self.process.pid}: {e}")
        finally:
            self.process = None

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit with cleanup."""
        await self.shutdown()

    def is_alive(self) -> bool:
        """
        Check if the CLI process is active with enhanced status checking.

        Returns:
            bool: True if process is running and responsive
        """
        if not self.process:
            return False

        if self.process.returncode is not None:
            return False

        # Additional check: try to get process status
        try:
            # Send signal 0 to check if process exists
            import os
            import signal

            os.kill(self.process.pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False

    async def _send_to_process(self, text: str) -> None:
        """
        Send text to the process stdin with error handling.

        Args:
            text: Text to send to the process

        Raises:
            RuntimeError: If process is not available for writing
        """
        if not self.process or not self.process.stdin:
            raise RuntimeError("Process not available for writing")

        # Ensure newline at the end
        if not text.endswith("\n"):
            text += "\n"

        try:
            self.process.stdin.write(text.encode("utf-8"))
            await self.process.stdin.drain()
            self.logger.debug(f"Sent to process: {text[:100]}...")
        except Exception as e:
            self.logger.error(f"Error sending to process: {e}")
            raise RuntimeError(f"Failed to send to process: {e}")

    def _get_clean_env(self) -> dict:
        """
        Get environment for the process.

        We allow proxy variables to be inherited so that agents can work
        behind proxies or VPNs.

        Returns:
            dict: Environment variables
        """
        import os

        # Simply inherit the full environment including proxy settings
        return os.environ.copy()
