"""
Interface-agnostic application lifecycle for NeuroCrew.

This module provides the main application class that manages the lifecycle
of the NeuroCrew system independently of specific interfaces, allowing
the core application to run and function even when no interfaces are configured.
"""

import asyncio
import logging
import signal
from typing import Optional, Dict, Any, List
from datetime import datetime

from app.config import Config
from app.core.engine import NeuroCrewLab
from app.interfaces.interface_manager import InterfaceManager, InterfaceStatus
from app.interfaces.base import InterfaceType
from app.utils.logger import get_logger


class NeuroCrewApplication:
    """
    Main application class with interface-agnostic lifecycle management.

    This class provides:
    - Core application lifecycle independent of interfaces
    - Graceful startup and shutdown handling
    - Interface management coordination
    - Role-based initialization
    - System health monitoring
    """

    def __init__(self):
        """Initialize the NeuroCrew application."""
        self.logger = get_logger(f"{self.__class__.__name__}")

        # Core components
        self.ncrew: Optional[NeuroCrewLab] = None
        self.interface_manager: Optional[InterfaceManager] = None

        # Application state
        self.is_running = False
        self.startup_time: Optional[datetime] = None
        self.shutdown_event = asyncio.Event()

        # Configuration
        self.config = Config
        self.min_interfaces_required = 0  # Can run with zero interfaces

        self.logger.info("NeuroCrewApplication initialized")

    async def initialize(self) -> bool:
        """
        Initialize the application components.

        Returns:
            bool: True if initialization successful
        """
        try:
            self.logger.info("Initializing NeuroCrew Application...")

            # Validate configuration
            if not self._validate_configuration():
                return False

            # Initialize core NeuroCrew engine
            if not await self._initialize_ncrew():
                return False

            # Initialize interface manager
            if not await self._initialize_interface_manager():
                return False

            self.logger.info("NeuroCrew Application initialized successfully")
            return True

        except Exception as e:
            self.logger.error(f"Failed to initialize application: {e}")
            return False

    async def start(self) -> bool:
        """
        Start the application and all components.

        Returns:
            bool: True if start successful
        """
        try:
            self.logger.info("Starting NeuroCrew Application...")
            self.startup_time = datetime.now()

            # Start interface manager (may start zero interfaces)
            interface_success = await self.interface_manager.start()

            # Log startup status
            active_interfaces = len(self.interface_manager.active_interfaces)
            configured_interfaces = len(self.interface_manager.configured_interfaces)

            self.logger.info(f"Application started:")
            self.logger.info(f"  - NeuroCrew Engine: ✅")
            self.logger.info(f"  - Active Interfaces: {active_interfaces}/{configured_interfaces}")

            if active_interfaces == 0:
                self.logger.warning("⚠️  No active interfaces - application running in headless mode")
                self.logger.info("Interfaces can be added later via the InterfaceManager")
            else:
                active_names = [it.value for it in self.interface_manager.active_interfaces]
                self.logger.info(f"  - Active interfaces: {', '.join(active_names)}")

            self.is_running = True
            return True

        except Exception as e:
            self.logger.error(f"Failed to start application: {e}")
            return False

    async def run(self) -> None:
        """
        Run the application main loop.

        This method blocks until the application is stopped.
        """
        try:
            if not self.is_running:
                if not await self.start():
                    return

            # Setup signal handlers
            self._setup_signal_handlers()

            self.logger.info("Application running. Press Ctrl+C to stop.")

            # Main application loop
            await self._main_loop()

        except KeyboardInterrupt:
            self.logger.info("Application stopped by user")
        except Exception as e:
            self.logger.error(f"Unexpected error in application loop: {e}")
        finally:
            await self.shutdown()

    async def stop(self) -> bool:
        """
        Stop the application gracefully.

        Returns:
            bool: True if stop successful
        """
        try:
            self.logger.info("Stopping NeuroCrew Application...")
            self.is_running = False
            self.shutdown_event.set()

            # Stop interface manager
            if self.interface_manager:
                await self.interface_manager.stop()

            # Shutdown NeuroCrew engine
            if self.ncrew:
                await self._shutdown_ncrew()

            # Calculate runtime
            if self.startup_time:
                runtime = datetime.now() - self.startup_time
                self.logger.info(f"Application stopped. Total runtime: {runtime}")

            return True

        except Exception as e:
            self.logger.error(f"Error stopping application: {e}")
            return False

    async def shutdown(self) -> None:
        """Shutdown the application (alias for stop)."""
        await self.stop()

    def get_status(self) -> Dict[str, Any]:
        """
        Get comprehensive application status.

        Returns:
            Dict: Application status information
        """
        status = {
            'application': {
                'is_running': self.is_running,
                'startup_time': self.startup_time.isoformat() if self.startup_time else None,
                'uptime_seconds': (datetime.now() - self.startup_time).total_seconds() if self.startup_time else 0,
                'version': '1.0.0',
            },
            'ncrew_engine': {
                'initialized': self.ncrew is not None,
                'status': 'running' if self.ncrew else 'not_initialized'
            }
        }

        # Add interface manager status
        if self.interface_manager:
            status['interfaces'] = self.interface_manager.get_interface_status()
            status['interface_manager'] = {
                'active_interfaces': len(self.interface_manager.active_interfaces),
                'configured_interfaces': len(self.interface_manager.configured_interfaces),
                'is_running': self.interface_manager.is_running
            }

        return status

    async def add_interface(self, interface_type: InterfaceType, **kwargs) -> bool:
        """
        Add a new interface to the running application.

        Args:
            interface_type: The type of interface to add
            **kwargs: Additional arguments for interface creation

        Returns:
            bool: True if interface added successfully
        """
        if not self.interface_manager:
            self.logger.error("Interface manager not initialized")
            return False

        success = await self.interface_manager.add_interface(interface_type, **kwargs)
        if success:
            self.logger.info(f"Successfully added {interface_type.value} interface")
            # Start the new interface if application is running
            if self.is_running:
                await self.interface_manager.start()
        else:
            self.logger.error(f"Failed to add {interface_type.value} interface")

        return success

    async def remove_interface(self, interface_type: InterfaceType) -> bool:
        """
        Remove an interface from the running application.

        Args:
            interface_type: The type of interface to remove

        Returns:
            bool: True if interface removed successfully
        """
        if not self.interface_manager:
            self.logger.error("Interface manager not initialized")
            return False

        success = await self.interface_manager.remove_interface(interface_type)
        if success:
            self.logger.info(f"Successfully removed {interface_type.value} interface")
        else:
            self.logger.error(f"Failed to remove {interface_type.value} interface")

        return success

    async def restart_interface(self, interface_type: InterfaceType) -> bool:
        """
        Restart a specific interface.

        Args:
            interface_type: The type of interface to restart

        Returns:
            bool: True if interface restarted successfully
        """
        if not self.interface_manager:
            self.logger.error("Interface manager not initialized")
            return False

        return await self.interface_manager.restart_interface(interface_type)

    async def send_system_message(self, message: str) -> bool:
        """
        Send a system message through all active interfaces.

        Args:
            message: The system message to send

        Returns:
            bool: True if message sent successfully
        """
        if not self.interface_manager:
            return False

        return await self.interface_manager.send_message_to_all_interfaces(message)

    # Private methods

    def _validate_configuration(self) -> bool:
        """Validate application configuration."""
        try:
            self.logger.info("Validating configuration...")

            # Check role-based configuration
            if not self.config.is_role_based_enabled():
                self.logger.warning("Role-based configuration not enabled")
                return False

            # Validate roles
            available_roles = self.config.get_available_roles()
            if not available_roles:
                self.logger.error("No roles configured")
                return False

            self.logger.info(f"Configuration valid - {len(available_roles)} roles loaded")
            return True

        except Exception as e:
            self.logger.error(f"Configuration validation failed: {e}")
            return False

    async def _initialize_ncrew(self) -> bool:
        """Initialize the NeuroCrew engine."""
        try:
            self.logger.info("Initializing NeuroCrew engine...")
            self.ncrew = NeuroCrewLab()
            await self.ncrew.initialize()

            # Log role information
            self.logger.info(f"NeuroCrew engine initialized with {len(self.ncrew.roles)} roles:")
            for role in self.ncrew.roles:
                self.logger.info(f"  - {role.role_name} ({role.display_name})")

            return True

        except Exception as e:
            self.logger.error(f"Failed to initialize NeuroCrew engine: {e}")
            return False

    async def _initialize_interface_manager(self) -> bool:
        """Initialize the interface manager."""
        try:
            self.logger.info("Initializing interface manager...")
            self.interface_manager = InterfaceManager(self.ncrew)

            # Initialize the manager (will discover configured interfaces)
            success = await self.interface_manager.initialize()

            if success:
                self.logger.info("Interface manager initialized")
            else:
                self.logger.warning("Interface manager initialization completed with some issues")

            return True  # Continue even if some interfaces fail

        except Exception as e:
            self.logger.error(f"Failed to initialize interface manager: {e}")
            return False

    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""
        try:
            loop = asyncio.get_running_loop()

            def handle_sigint():
                if self.shutdown_event.is_set():
                    self.logger.warning("Second SIGINT received, forcing immediate exit")
                    loop.stop()
                    return
                self.logger.info("SIGINT received. Initiating graceful shutdown...")
                loop.call_soon_threadsafe(
                    lambda: asyncio.create_task(self.shutdown())
                )

            if hasattr(loop, "add_signal_handler"):
                loop.add_signal_handler(signal.SIGINT, handle_sigint)
                if hasattr(signal, "SIGTERM"):
                    loop.add_signal_handler(signal.SIGTERM, handle_sigint)
            else:
                # Fallback for platforms without signal handlers
                signal.signal(
                    signal.SIGINT,
                    lambda *_: loop.call_soon_threadsafe(
                        lambda: asyncio.create_task(self.shutdown())
                    ),
                )
                if hasattr(signal, "SIGTERM"):
                    signal.signal(
                        signal.SIGTERM,
                        lambda *_: loop.call_soon_threadsafe(
                            lambda: asyncio.create_task(self.shutdown())
                        ),
                    )

        except Exception as e:
            self.logger.error(f"Failed to setup signal handlers: {e}")

    async def _main_loop(self) -> None:
        """Main application loop."""
        try:
            while not self.shutdown_event.is_set():
                try:
                    # Perform periodic health checks
                    await self._perform_health_checks()

                    # Wait for shutdown signal or next health check
                    try:
                        await asyncio.wait_for(
                            self.shutdown_event.wait(),
                            timeout=60.0  # Health check every 60 seconds
                        )
                        break
                    except asyncio.TimeoutError:
                        continue

                except asyncio.CancelledError:
                    self.logger.info("Main loop cancelled")
                    break
                except Exception as e:
                    self.logger.error(f"Error in main loop: {e}")
                    await asyncio.sleep(5)  # Wait before retrying

        except Exception as e:
            self.logger.error(f"Critical error in main loop: {e}")

    async def _perform_health_checks(self) -> None:
        """Perform periodic health checks."""
        try:
            # Check NeuroCrew engine health
            if self.ncrew:
                # Could add more sophisticated health checks here
                pass

            # Check interface health
            if self.interface_manager:
                # Log interface status periodically
                status = self.interface_manager.get_interface_status()
                active_count = sum(
                    1 for info in status.values()
                    if info['status'] == InterfaceStatus.ACTIVE.value
                )

                if active_count == 0:
                    self.logger.debug("No active interfaces - running in headless mode")
                else:
                    self.logger.debug(f"Health check: {active_count} active interfaces")

        except Exception as e:
            self.logger.error(f"Error during health check: {e}")

    async def _shutdown_ncrew(self) -> None:
        """Shutdown the NeuroCrew engine."""
        try:
            if self.ncrew:
                self.logger.info("Shutting down NeuroCrew engine...")

                # Shutdown role sessions
                if hasattr(self.ncrew, 'shutdown_role_sessions'):
                    await self.ncrew.shutdown_role_sessions()

                self.ncrew = None
                self.logger.info("NeuroCrew engine shutdown complete")

        except Exception as e:
            self.logger.error(f"Error shutting down NeuroCrew engine: {e}")


class ApplicationFactory:
    """Factory class for creating NeuroCrew applications."""

    @staticmethod
    def create_application() -> NeuroCrewApplication:
        """
        Create a new NeuroCrew application instance.

        Returns:
            NeuroCrewApplication: The application instance
        """
        return NeuroCrewApplication()

    @staticmethod
    async def create_and_run() -> None:
        """
        Create and run a NeuroCrew application.

        This is a convenience method for simple use cases.
        """
        app = ApplicationFactory.create_application()

        # Initialize the application
        if not await app.initialize():
            logging.error("Failed to initialize application")
            return

        # Run the application
        await app.run()