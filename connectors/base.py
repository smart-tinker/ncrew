"""
Base connector class for AI coding agents.

This module provides the abstract base class for pure stateful connectors
that manage long-lived CLI agent processes.
"""

import asyncio
import time
from abc import ABC, abstractmethod
from typing import Optional
from utils.logger import get_logger


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
            self.logger.debug(f"Process {self.process.pid} already terminated with code {self.process.returncode}")
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
                self.logger.warning(f"Process {self.process.pid} did not terminate, force killing...")
                self.process.kill()
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=2.0)
                    self.logger.info(f"Process {self.process.pid} force killed.")
                except asyncio.TimeoutError:
                    self.logger.error(f"Process {self.process.pid} could not be killed, orphaned process may exist")
        except (ProcessLookupError, RuntimeError) as e:
            # Process might have already terminated or event loop closed
            self.logger.info(f"Process {self.process.pid} already terminated or event loop closed: {e}")
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

    async def _read_until_timeout(self, timeout: float = 30.0) -> str:
        """
        Enhanced stdout reading with reliable timeout detection for CLI agents.

        This method reads from the process stdout until no new data
        is received for the specified timeout period, indicating
        that the response is complete.

        Args:
            timeout: Seconds to wait without new data before considering response complete
                    Increased default for CLI agent processing time

        Returns:
            str: Collected response text

        Raises:
            RuntimeError: If process is not available for reading
        """
        if not self.process or not self.process.stdout:
            raise RuntimeError("Process not available for reading")

        self.logger.info(f"Reading from process stdout (timeout: {timeout}s)...")
        buffer = []
        last_received = time.time()
        consecutive_empty_reads = 0
        max_empty_reads = 50  # Increased for CLI agents that output line by line

        while True:
            try:
                # Use longer timeout for individual reads to accommodate CLI processing
                line = await asyncio.wait_for(
                    self.process.stdout.readline(),
                    timeout=1.0  # Increased from 0.1s
                )

                if line:
                    decoded_line = line.decode().rstrip()
                    if decoded_line:
                        buffer.append(decoded_line)
                        last_received = time.time()
                        consecutive_empty_reads = 0
                        self.logger.debug(f"Received line: {decoded_line[:100]}...")
                    else:
                        consecutive_empty_reads += 1
                        self.logger.debug(f"Empty line, consecutive empties: {consecutive_empty_reads}")
                else:
                    # No line received (EOF or no data available)
                    consecutive_empty_reads += 1

                    # Check if we've timed out based on last received data
                    elapsed = time.time() - last_received
                    if elapsed > timeout:
                        self.logger.info(f"Timeout reached after {elapsed:.1f}s without new data")
                        break

                    # Prevent infinite loops with too many consecutive empty reads
                    if consecutive_empty_reads >= max_empty_reads:
                        self.logger.warning(f"Max empty reads ({max_empty_reads}) reached, assuming response complete")
                        break

                    # Longer pause to give CLI agent time to generate response
                    await asyncio.sleep(0.2)

            except asyncio.TimeoutError:
                # Check if overall timeout has been exceeded
                elapsed = time.time() - last_received
                if elapsed > timeout:
                    self.logger.warning(f"Individual read timeout after {elapsed:.1f}s")
                    break
                # Continue trying on individual read timeouts
                self.logger.debug("Individual read timeout, continuing...")
                continue
            except Exception as e:
                self.logger.error(f"Error reading from process stdout: {e}")
                break

        result = '\n'.join(buffer)
        self.logger.info(f"Read completed: {len(buffer)} lines, {len(result)} characters total")

        if not result.strip():
            self.logger.warning("Empty result from process - possible CLI agent issue")
            self.logger.warning(f"Process PID: {self.process.pid}, Return code: {self.process.returncode}")

            # Try to get any stderr output for debugging
            if self.process.stderr:
                try:
                    stderr_output = await asyncio.wait_for(
                        self.process.stderr.read(),
                        timeout=1.0
                    )
                    if stderr_output:
                        stderr_text = stderr_output.decode().strip()
                        if stderr_text:
                            self.logger.error(f"Process stderr: {stderr_text}")
                except Exception as e:
                    self.logger.debug(f"Could not read stderr: {e}")

        return result

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
        if not text.endswith('\n'):
            text += '\n'

        try:
            self.process.stdin.write(text.encode('utf-8'))
            await self.process.stdin.drain()
            self.logger.debug(f"Sent to process: {text[:100]}...")
        except Exception as e:
            self.logger.error(f"Error sending to process: {e}")
            raise RuntimeError(f"Failed to send to process: {e}")

    def _get_clean_env(self) -> dict:
        """
        Get environment without proxy variables that might interfere with CLI agents.

        Returns:
            dict: Clean environment without proxy variables
        """
        import os
        clean_env = os.environ.copy()
        proxy_vars = [
            'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY',
            'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy'
        ]
        for var in proxy_vars:
            clean_env.pop(var, None)
        return clean_env