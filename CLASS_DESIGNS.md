# Detailed Class Designs for Interface-Agnostic NeuroCrew

## 1. Enhanced NeuroCrewApplication Class

```python
"""
Enhanced NeuroCrewApplication with interface-agnostic lifecycle management.
"""

import asyncio
import signal
from typing import Optional, Dict, Any, List, Set
from datetime import datetime
from enum import Enum

from app.config import Config
from app.core.engine import NeuroCrewLab
from app.interfaces.interface_manager import EnhancedInterfaceManager, InterfaceStatus
from app.interfaces.base import InterfaceType
from app.events.event_bus import EventBus, Event, CoreEvent, InterfaceEvent
from app.events.event_handlers import ApplicationEventHandler
from app.utils.logger import get_logger


class OperationMode(Enum):
    """Application operation modes."""
    HEADLESS = "headless"           # No interfaces - API/admin only
    SINGLE_INTERFACE = "single"    # One interface active
    MULTI_INTERFACE = "multi"      # Multiple interfaces active
    AUTO = "auto"                 # Auto-detect based on available interfaces


class ApplicationState(Enum):
    """Application lifecycle states."""
    INITIALIZING = "initializing"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class NeuroCrewApplication:
    """
    Enhanced main application class with interface-agnostic lifecycle management.

    Key Features:
    - Independent core startup sequence
    - Headless operation mode
    - Dynamic interface management
    - Event-driven architecture
    - Graceful degradation
    - Comprehensive health monitoring
    """

    def __init__(self, mode: OperationMode = OperationMode.AUTO):
        """
        Initialize the NeuroCrew application.

        Args:
            mode: Operation mode (AUTO will detect based on available interfaces)
        """
        self.logger = get_logger(f"{self.__class__.__name__}")

        # Application state
        self.state = ApplicationState.INITIALIZING
        self.operation_mode = mode
        self.startup_time: Optional[datetime] = None
        self.shutdown_event = asyncio.Event()

        # Core components
        self.ncrew: Optional[NeuroCrewLab] = None
        self.interface_manager: Optional[EnhancedInterfaceManager] = None
        self.event_bus: Optional[EventBus] = None
        self.event_handler: Optional[ApplicationEventHandler] = None

        # Configuration and capabilities
        self.config = Config
        self.active_interfaces: Set[InterfaceType] = set()
        self.capabilities: Dict[str, Any] = {}

        # Health and monitoring
        self.health_status: Dict[str, bool] = {}
        self.last_health_check: Optional[datetime] = None

        self.logger.info(f"NeuroCrewApplication initialized with mode: {mode.value}")

    async def initialize(self) -> bool:
        """
        Phase-based application initialization.

        Returns:
            bool: True if initialization successful
        """
        try:
            await self._emit_event(CoreEvent.APPLICATION_STARTING)
            self.state = ApplicationState.INITIALIZING

            # Phase 1: Core Engine Initialization (Always Required)
            if not await self._initialize_core_engine():
                return False

            # Phase 2: Interface Discovery and Registration (Optional)
            if not await self._initialize_interfaces():
                # Interface initialization failure should not stop core
                self.logger.warning("Interface initialization failed, continuing with core engine")

            # Phase 3: Determine Operation Mode and Setup
            await self._determine_operation_mode()
            await self._setup_event_handling()

            # Phase 4: Role Introductions (Conditional)
            if not await self._perform_role_introductions():
                return False

            self.state = ApplicationState.STARTING
            await self._emit_event(CoreEvent.APPLICATION_STARTED)

            self.logger.info("NeuroCrew Application initialized successfully")
            return True

        except Exception as e:
            self.logger.error(f"Failed to initialize application: {e}")
            self.state = ApplicationState.ERROR
            await self._emit_event(CoreEvent.APPLICATION_ERROR, {"error": str(e)})
            return False

    async def start(self) -> bool:
        """
        Start the application and all components.

        Returns:
            bool: True if start successful
        """
        try:
            if self.state != ApplicationState.STARTING:
                self.logger.error(f"Application not in startable state: {self.state.value}")
                return False

            self.logger.info("Starting NeuroCrew Application...")
            self.startup_time = datetime.now()

            # Start interface manager (may start zero interfaces)
            interface_success = await self.interface_manager.start() if self.interface_manager else True

            # Update application state and capabilities
            await self._update_application_state()

            # Log startup status
            active_count = len(self.active_interfaces)
            configured_count = len(self.interface_manager.configured_interfaces) if self.interface_manager else 0

            self.logger.info(f"Application started:")
            self.logger.info(f"  - Operation Mode: {self.operation_mode.value}")
            self.logger.info(f"  - NeuroCrew Engine: ✅")
            self.logger.info(f"  - Active Interfaces: {active_count}/{configured_count}")

            if active_count == 0:
                self.logger.info("🔧 Running in HEADLESS mode - interfaces can be added at runtime")
            else:
                active_names = [it.value for it in self.active_interfaces]
                self.logger.info(f"  - Active interfaces: {', '.join(active_names)}")

            self.state = ApplicationState.RUNNING
            return True

        except Exception as e:
            self.logger.error(f"Failed to start application: {e}")
            self.state = ApplicationState.ERROR
            return False

    async def run(self) -> None:
        """
        Main application loop.

        This method blocks until the application is stopped.
        """
        try:
            if self.state != ApplicationState.RUNNING:
                if not await self.initialize():
                    return
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
            self.state = ApplicationState.ERROR
        finally:
            await self.shutdown()

    async def add_interface(self, interface_type: InterfaceType, **kwargs) -> bool:
        """
        Add a new interface to the running application.

        Args:
            interface_type: The type of interface to add
            **kwargs: Additional arguments for interface creation

        Returns:
            bool: True if interface added successfully
        """
        try:
            if not self.interface_manager:
                self.logger.error("Interface manager not initialized")
                return False

            await self._emit_event(InterfaceEvent.INTERFACE_DISCOVERED, {
                "interface_type": interface_type.value,
                "action": "add_runtime"
            })

            success = await self.interface_manager.add_interface(interface_type, **kwargs)

            if success:
                self.active_interfaces.add(interface_type)
                await self._update_operation_mode()
                await self._emit_event(InterfaceEvent.INTERFACE_REGISTERED, {
                    "interface_type": interface_type.value
                })
                self.logger.info(f"Successfully added {interface_type.value} interface at runtime")
            else:
                await self._emit_event(InterfaceEvent.INTERFACE_ERROR, {
                    "interface_type": interface_type.value,
                    "error": "Failed to add interface"
                })
                self.logger.error(f"Failed to add {interface_type.value} interface at runtime")

            return success

        except Exception as e:
            self.logger.error(f"Error adding interface {interface_type.value}: {e}")
            return False

    async def remove_interface(self, interface_type: InterfaceType) -> bool:
        """
        Remove an interface from the running application.

        Args:
            interface_type: The type of interface to remove

        Returns:
            bool: True if interface removed successfully
        """
        try:
            if not self.interface_manager:
                self.logger.error("Interface manager not initialized")
                return False

            success = await self.interface_manager.remove_interface(interface_type)

            if success:
                self.active_interfaces.discard(interface_type)
                await self._update_operation_mode()
                await self._emit_event(InterfaceEvent.INTERFACE_UNREGISTERED, {
                    "interface_type": interface_type.value
                })
                self.logger.info(f"Successfully removed {interface_type.value} interface at runtime")
            else:
                self.logger.error(f"Failed to remove {interface_type.value} interface at runtime")

            return success

        except Exception as e:
            self.logger.error(f"Error removing interface {interface_type.value}: {e}")
            return False

    def get_status(self) -> Dict[str, Any]:
        """
        Get comprehensive application status.

        Returns:
            Dict: Application status information
        """
        status = {
            'application': {
                'state': self.state.value,
                'operation_mode': self.operation_mode.value,
                'startup_time': self.startup_time.isoformat() if self.startup_time else None,
                'uptime_seconds': (datetime.now() - self.startup_time).total_seconds() if self.startup_time else 0,
                'version': '1.0.0',
            },
            'ncrew_engine': {
                'initialized': self.ncrew is not None,
                'status': 'running' if self.ncrew else 'not_initialized',
                'roles_count': len(self.ncrew.roles) if self.ncrew else 0,
            },
            'interfaces': {
                'active_count': len(self.active_interfaces),
                'active_interfaces': [it.value for it in self.active_interfaces],
                'capabilities': self.capabilities,
            },
            'health': {
                'last_check': self.last_health_check.isoformat() if self.last_health_check else None,
                'status': self.health_status,
                'overall_healthy': all(self.health_status.values()) if self.health_status else False,
            }
        }

        # Add detailed interface manager status
        if self.interface_manager:
            status['interface_manager'] = self.interface_manager.get_interface_status()

        return status

    # Private Methods

    async def _initialize_core_engine(self) -> bool:
        """Initialize the core NeuroCrew engine (Phase 1)."""
        try:
            self.logger.info("=== PHASE 1: Core Engine Initialization ===")

            # Validate core configuration (interface-agnostic)
            if not self._validate_core_configuration():
                return False

            # Initialize NeuroCrew engine
            self.logger.info("Initializing NeuroCrew engine...")
            self.ncrew = NeuroCrewLab()
            await self.ncrew.initialize()

            # Initialize event bus
            self.event_bus = EventBus()
            await self.event_bus.start()

            # Log role information
            self.logger.info(f"NeuroCrew engine initialized with {len(self.ncrew.roles)} roles")
            for role in self.ncrew.roles:
                self.logger.info(f"  - {role.role_name} ({role.display_name})")

            await self._emit_event(CoreEvent.NCREW_INITIALIZED, {
                "roles_count": len(self.ncrew.roles)
            })

            return True

        except Exception as e:
            self.logger.error(f"Failed to initialize core engine: {e}")
            return False

    async def _initialize_interfaces(self) -> bool:
        """Initialize interface manager and discover interfaces (Phase 2)."""
        try:
            self.logger.info("=== PHASE 2: Interface Discovery and Registration ===")

            # Initialize enhanced interface manager
            self.interface_manager = EnhancedInterfaceManager(
                self.ncrew,
                self.event_bus
            )

            # Initialize interface manager
            success = await self.interface_manager.initialize()

            if success:
                # Get active interfaces
                self.active_interfaces = set(self.interface_manager.active_interfaces)
                self.logger.info(f"Interface manager initialized with {len(self.active_interfaces)} active interfaces")
            else:
                self.logger.warning("Interface manager initialization completed with issues")

            return True  # Continue even if some interfaces fail

        except Exception as e:
            self.logger.error(f"Failed to initialize interface manager: {e}")
            return True  # Continue without interfaces

    async def _determine_operation_mode(self) -> None:
        """Determine the operation mode based on available interfaces."""
        if self.operation_mode == OperationMode.AUTO:
            active_count = len(self.active_interfaces)

            if active_count == 0:
                self.operation_mode = OperationMode.HEADLESS
            elif active_count == 1:
                self.operation_mode = OperationMode.SINGLE_INTERFACE
            else:
                self.operation_mode = OperationMode.MULTI_INTERFACE

        self.logger.info(f"Operation mode determined: {self.operation_mode.value}")

    async def _setup_event_handling(self) -> None:
        """Setup event handling for the application."""
        try:
            self.event_handler = ApplicationEventHandler(self)

            # Subscribe to core events
            await self.event_bus.subscribe(CoreEvent.INTERFACE_ERROR, self.event_handler)
            await self.event_bus.subscribe(CoreEvent.HEALTH_CHECK_COMPLETED, self.event_handler)

            # Subscribe to interface events
            await self.event_bus.subscribe(InterfaceEvent.INTERFACE_READY, self.event_handler)
            await self.event_bus.subscribe(InterfaceEvent.INTERFACE_ERROR, self.event_handler)
            await self.event_bus.subscribe(InterfaceEvent.INTERFACE_RECOVERED, self.event_handler)

            self.logger.info("Event handling setup completed")

        except Exception as e:
            self.logger.error(f"Failed to setup event handling: {e}")

    async def _perform_role_introductions(self) -> bool:
        """Perform role introductions based on operation mode (Phase 3)."""
        try:
            self.logger.info("=== PHASE 3: Role Introductions ===")

            await self._emit_event(CoreEvent.ROLE_INTRODUCTION_STARTING)

            if self.operation_mode == OperationMode.HEADLESS:
                # Perform silent introductions for headless mode
                await self._perform_silent_introductions()
            else:
                # Perform introductions via available interfaces
                await self._perform_interface_introductions()

            await self._emit_event(CoreEvent.ROLE_INTRODUCTION_COMPLETED)
            self.logger.info("Role introductions completed")

            return True

        except Exception as e:
            self.logger.error(f"Failed during role introductions: {e}")
            return False

    async def _perform_silent_introductions(self) -> None:
        """Perform role introductions without any interface output."""
        self.logger.info("Performing silent role introductions (headless mode)...")

        introduction_prompt = "Hello! Please introduce yourself and briefly describe your role and capabilities."

        async for role_config, intro_text in self.ncrew.perform_startup_introductions():
            # Store introduction in conversation history
            await self._store_introduction_in_history(role_config, intro_text)
            self.logger.info(f"Silent introduction stored: {role_config.display_name}")

    async def _perform_interface_introductions(self) -> None:
        """Perform role introductions via available interfaces."""
        self.logger.info("Performing role introductions via interfaces...")

        if self.interface_manager:
            await self.interface_manager.perform_startup_introductions()

    async def _store_introduction_in_history(self, role_config, intro_text: str) -> None:
        """Store role introduction in conversation history."""
        try:
            if self.ncrew and self.config.TARGET_CHAT_ID:
                # Store as system message for context
                agent_message = {
                    "role": "system",
                    "agent_name": role_config.agent_type,
                    "role_name": role_config.role_name,
                    "role_display": role_config.display_name,
                    "content": f"[INTRODUCTION] {intro_text}",
                    "timestamp": datetime.now().isoformat(),
                }
                await self.ncrew.storage.add_message(self.config.TARGET_CHAT_ID, agent_message)

        except Exception as e:
            self.logger.error(f"Failed to store introduction in history: {e}")

    def _validate_core_configuration(self) -> bool:
        """Validate core application configuration (interface-agnostic)."""
        try:
            self.logger.info("Validating core configuration...")

            # Check role-based configuration
            if not self.config.is_role_based_enabled():
                self.logger.error("Role-based configuration not enabled")
                return False

            # Validate roles
            available_roles = self.config.get_available_roles()
            if not available_roles:
                self.logger.error("No roles configured")
                return False

            # Validate role dependencies
            validation_errors = self.config.validate_role_configuration()
            if validation_errors:
                self.logger.error(f"Role configuration validation failed: {validation_errors}")
                return False

            self.logger.info(f"Core configuration valid - {len(available_roles)} roles loaded")
            return True

        except Exception as e:
            self.logger.error(f"Core configuration validation failed: {e}")
            return False

    async def _update_application_state(self) -> None:
        """Update application state and capabilities."""
        try:
            # Update active interfaces from interface manager
            if self.interface_manager:
                self.active_interfaces = set(self.interface_manager.active_interfaces)

            # Update operation mode
            await self._update_operation_mode()

            # Update capabilities
            await self._update_capabilities()

        except Exception as e:
            self.logger.error(f"Failed to update application state: {e}")

    async def _update_operation_mode(self) -> None:
        """Update operation mode based on current active interfaces."""
        if self.operation_mode != OperationMode.AUTO:
            return  # Don't change manually set mode

        active_count = len(self.active_interfaces)
        new_mode = OperationMode.HEADLESS if active_count == 0 else \
                  OperationMode.SINGLE_INTERFACE if active_count == 1 else \
                  OperationMode.MULTI_INTERFACE

        if new_mode != self.operation_mode:
            old_mode = self.operation_mode
            self.operation_mode = new_mode
            self.logger.info(f"Operation mode changed: {old_mode.value} → {new_mode.value}")

    async def _update_capabilities(self) -> None:
        """Update application capabilities based on active interfaces."""
        self.capabilities = {
            'headless_operation': len(self.active_interfaces) == 0,
            'user_interaction': len(self.active_interfaces) > 0,
            'multi_interface': len(self.active_interfaces) > 1,
            'real_time_messaging': InterfaceType.TELEGRAM in self.active_interfaces,
            'web_interface': InterfaceType.WEB in self.active_interfaces,
            'api_access': InterfaceType.API in self.active_interfaces or True,  # API always available
            'runtime_interface_management': self.interface_manager is not None,
        }

    async def _emit_event(self, event_type, data: Dict[str, Any] = None) -> None:
        """Emit an event to the event bus."""
        if self.event_bus:
            event = Event(
                type=event_type,
                timestamp=datetime.now(),
                data=data or {}
            )
            await self.event_bus.publish(event)

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

        except Exception as e:
            self.logger.error(f"Failed to setup signal handlers: {e}")

    async def _main_loop(self) -> None:
        """Main application loop with health monitoring."""
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
        """Perform comprehensive health checks."""
        try:
            health_status = {}

            # Check NeuroCrew engine health
            if self.ncrew:
                ncrew_health = await self.ncrew.health_check()
                health_status['ncrew_engine'] = all(ncrew_health.values())
            else:
                health_status['ncrew_engine'] = False

            # Check interface health
            if self.interface_manager:
                interface_status = self.interface_manager.get_interface_status()
                active_interfaces = sum(
                    1 for status in interface_status.values()
                    if status['status'] == InterfaceStatus.ACTIVE.value
                )
                # Consider interface health good if at least one interface is active
                # or if we're in headless mode (interfaces optional)
                health_status['interfaces'] = (
                    active_interfaces > 0 or self.operation_mode == OperationMode.HEADLESS
                )
            else:
                health_status['interfaces'] = self.operation_mode == OperationMode.HEADLESS

            # Check event bus health
            if self.event_bus:
                health_status['event_bus'] = self.event_bus.is_healthy()
            else:
                health_status['event_bus'] = False

            # Update overall health status
            self.health_status = health_status
            self.last_health_check = datetime.now()

            # Emit health check completed event
            await self._emit_event(CoreEvent.HEALTH_CHECK_COMPLETED, health_status)

            # Log health status if there are issues
            if not all(health_status.values()):
                unhealthy_components = [k for k, v in health_status.items() if not v]
                self.logger.warning(f"Health check issues detected: {unhealthy_components}")

        except Exception as e:
            self.logger.error(f"Error during health check: {e}")
            self.health_status['health_check_error'] = False

    async def shutdown(self) -> None:
        """Graceful shutdown of the application."""
        try:
            if self.state == ApplicationState.STOPPED:
                return

            self.logger.info("=== APPLICATION SHUTDOWN SEQUENCE ===")
            await self._emit_event(CoreEvent.APPLICATION_STOPPING)
            self.state = ApplicationState.STOPPING
            self.shutdown_event.set()

            # Shutdown interface manager
            if self.interface_manager:
                self.logger.info("Shutting down interface manager...")
                await self.interface_manager.stop()

            # Shutdown NeuroCrew engine
            if self.ncrew:
                self.logger.info("Shutting down NeuroCrew engine...")
                await self.ncrew.shutdown_role_sessions()

            # Shutdown event bus
            if self.event_bus:
                self.logger.info("Shutting down event bus...")
                await self.event_bus.stop()

            # Calculate runtime
            if self.startup_time:
                runtime = datetime.now() - self.startup_time
                self.logger.info(f"Application shutdown complete. Total runtime: {runtime}")

            self.state = ApplicationState.STOPPED
            await self._emit_event(CoreEvent.APPLICATION_STOPPED)

        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}")
            self.state = ApplicationState.ERROR
```

## 2. Enhanced Interface Manager

```python
"""
Enhanced Interface Manager with dynamic discovery and health monitoring.
"""

import asyncio
from typing import Dict, List, Optional, Set, Any, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass

from app.interfaces.interface_manager import InterfaceManager, InterfaceInfo, InterfaceStatus
from app.interfaces.base import BaseInterface, InterfaceType, MessageCapabilities
from app.events.event_bus import EventBus, Event, InterfaceEvent
from app.utils.logger import get_logger


@dataclass
class InterfaceHealthMetrics:
    """Health metrics for an interface."""
    status: InterfaceStatus
    last_check: datetime
    uptime_percentage: float = 100.0
    error_count: int = 0
    message_count: int = 0
    average_response_time: float = 0.0
    last_error: Optional[str] = None
    consecutive_failures: int = 0


class EnhancedInterfaceManager(InterfaceManager):
    """
    Enhanced interface manager with dynamic discovery, health monitoring, and recovery.

    Additional Features:
    - Runtime interface discovery
    - Continuous health monitoring
    - Automatic recovery mechanisms
    - Performance metrics collection
    - Circuit breaker pattern
    """

    def __init__(self, ncrew_instance=None, event_bus: Optional[EventBus] = None):
        """
        Initialize the enhanced interface manager.

        Args:
            ncrew_instance: The NeuroCrew instance to connect to
            event_bus: Event bus for publishing/receiving events
        """
        super().__init__(ncrew_instance)

        self.event_bus = event_bus
        self.health_metrics: Dict[InterfaceType, InterfaceHealthMetrics] = {}
        self.monitoring_active = False
        self.monitoring_task: Optional[asyncio.Task] = None
        self.discovery_interval = 300  # 5 minutes
        self.health_check_interval = 60  # 1 minute
        self.circuit_breaker_threshold = 3  # Max consecutive failures
        self.auto_recovery_enabled = True
        self.capability_cache: Dict[InterfaceType, MessageCapabilities] = {}

    async def initialize(self) -> bool:
        """
        Initialize with enhanced discovery and setup.

        Returns:
            bool: True if initialization successful
        """
        try:
            self.logger.info("Initializing Enhanced Interface Manager...")

            # Initialize base interface manager
            base_success = await super().initialize()

            # Perform enhanced discovery
            await self._enhanced_interface_discovery()

            # Setup health monitoring
            await self._setup_health_monitoring()

            # Initialize health metrics
            self._initialize_health_metrics()

            self.logger.info(f"Enhanced Interface Manager initialized with {len(self.active_interfaces)} active interfaces")
            return base_success

        except Exception as e:
            self.logger.error(f"Failed to initialize Enhanced Interface Manager: {e}")
            return False

    async def start(self) -> bool:
        """
        Start interfaces and monitoring.

        Returns:
            bool: True if start successful
        """
        try:
            # Start base interface manager
            success = await super().start()

            if success:
                # Start enhanced monitoring
                await self._start_health_monitoring()

                # Start periodic discovery
                await self._start_periodic_discovery()

            return success

        except Exception as e:
            self.logger.error(f"Failed to start Enhanced Interface Manager: {e}")
            return False

    async def stop(self) -> bool:
        """
        Stop interfaces and monitoring.

        Returns:
            bool: True if stop successful
        """
        try:
            # Stop enhanced monitoring
            await self._stop_health_monitoring()

            # Stop base interface manager
            return await super().stop()

        except Exception as e:
            self.logger.error(f"Failed to stop Enhanced Interface Manager: {e}")
            return False

    async def discover_interfaces(self) -> List[InterfaceType]:
        """
        Discover available interfaces in the system.

        Returns:
            List[InterfaceType]: List of discovered interface types
        """
        discovered = []

        try:
            # Check for known interface types
            for interface_type in InterfaceType:
                if await self._is_interface_available(interface_type):
                    discovered.append(interface_type)
                    self.logger.info(f"Discovered available interface: {interface_type.value}")

            return discovered

        except Exception as e:
            self.logger.error(f"Error during interface discovery: {e}")
            return []

    async def validate_interface_capabilities(self, interface_type: InterfaceType) -> bool:
        """
        Validate that an interface type has the required capabilities.

        Args:
            interface_type: The interface type to validate

        Returns:
            bool: True if interface has required capabilities
        """
        try:
            # Check cached capabilities first
            if interface_type in self.capability_cache:
                return True

            # Create temporary interface for validation
            temp_interface = interface_registry.create_interface(interface_type)
            if not temp_interface:
                return False

            # Validate capabilities
            capabilities = temp_interface.capabilities
            required_capabilities = self._get_required_capabilities()

            is_valid = self._validate_capabilities(capabilities, required_capabilities)

            if is_valid:
                self.capability_cache[interface_type] = capabilities

            return is_valid

        except Exception as e:
            self.logger.error(f"Error validating interface capabilities for {interface_type.value}: {e}")
            return False

    async def get_interface_health_metrics(self) -> Dict[str, Any]:
        """
        Get comprehensive health metrics for all interfaces.

        Returns:
            Dict: Health metrics for all interfaces
        """
        metrics = {}

        for interface_type, health_info in self.health_metrics.items():
            metrics[interface_type.value] = {
                'status': health_info.status.value,
                'last_check': health_info.last_check.isoformat(),
                'uptime_percentage': health_info.uptime_percentage,
                'error_count': health_info.error_count,
                'message_count': health_info.message_count,
                'average_response_time': health_info.average_response_time,
                'last_error': health_info.last_error,
                'consecutive_failures': health_info.consecutive_failures,
                'circuit_breaker_open': health_info.consecutive_failures >= self.circuit_breaker_threshold,
            }

        return metrics

    async def force_interface_recovery(self, interface_type: InterfaceType) -> bool:
        """
        Force recovery of a specific interface.

        Args:
            interface_type: The interface type to recover

        Returns:
            bool: True if recovery successful
        """
        try:
            self.logger.info(f"Force recovering interface: {interface_type.value}")

            if interface_type not in self.interfaces:
                self.logger.error(f"Interface {interface_type.value} not found")
                return False

            # Reset circuit breaker
            if interface_type in self.health_metrics:
                self.health_metrics[interface_type].consecutive_failures = 0

            # Attempt restart
            success = await self.restart_interface(interface_type)

            if success:
                self.logger.info(f"Interface {interface_type.value} recovered successfully")
                await self._emit_interface_event(InterfaceEvent.INTERFACE_RECOVERED, {
                    "interface_type": interface_type.value,
                    "recovery_type": "forced"
                })
            else:
                self.logger.error(f"Failed to recover interface {interface_type.value}")

            return success

        except Exception as e:
            self.logger.error(f"Error during interface recovery: {e}")
            return False

    # Private Methods

    async def _enhanced_interface_discovery(self) -> None:
        """Perform enhanced interface discovery."""
        try:
            discovered_interfaces = await self.discover_interfaces()

            for interface_type in discovered_interfaces:
                if interface_type not in self.configured_interfaces:
                    # Auto-configure discovered interfaces
                    if await self.validate_interface_capabilities(interface_type):
                        self.configured_interfaces.add(interface_type)
                        self.logger.info(f"Auto-configured discovered interface: {interface_type.value}")

        except Exception as e:
            self.logger.error(f"Error during enhanced discovery: {e}")

    async def _is_interface_available(self, interface_type: InterfaceType) -> bool:
        """Check if an interface type is available in the system."""
        try:
            if interface_type == InterfaceType.TELEGRAM:
                return bool(self.config.MAIN_BOT_TOKEN)
            elif interface_type == InterfaceType.WEB:
                return True  # Web interface always available
            elif interface_type == InterfaceType.API:
                return True  # API interface always available
            else:
                # For future interface types, add availability checks
                return False

        except Exception as e:
            self.logger.error(f"Error checking interface availability for {interface_type.value}: {e}")
            return False

    def _get_required_capabilities(self) -> Dict[str, bool]:
        """Get the required capabilities for interfaces."""
        return {
            'supports_text': True,
            'max_message_length': 100,  # Minimum message length
        }

    def _validate_capabilities(self, capabilities: MessageCapabilities, required: Dict[str, bool]) -> bool:
        """Validate interface capabilities against requirements."""
        # All interfaces must support text messaging
        if not capabilities.supports_markdown and not capabilities.supports_html:
            return False

        # Check minimum message length
        if capabilities.max_message_length < required.get('max_message_length', 100):
            return False

        return True

    def _initialize_health_metrics(self) -> None:
        """Initialize health metrics for all interfaces."""
        for interface_type in self.interfaces:
            self.health_metrics[interface_type] = InterfaceHealthMetrics(
                status=self.interfaces[interface_type].status,
                last_check=datetime.now()
            )

    async def _setup_health_monitoring(self) -> None:
        """Setup health monitoring for interfaces."""
        try:
            self.logger.info("Setting up interface health monitoring...")

            # Subscribe to interface events for health tracking
            if self.event_bus:
                await self.event_bus.subscribe(InterfaceEvent.MESSAGE_SENT, self._on_message_sent)
                await self.event_bus.subscribe(InterfaceEvent.MESSAGE_RECEIVED, self._on_message_received)

        except Exception as e:
            self.logger.error(f"Failed to setup health monitoring: {e}")

    async def _start_health_monitoring(self) -> None:
        """Start the health monitoring task."""
        try:
            if not self.monitoring_active:
                self.monitoring_active = True
                self.monitoring_task = asyncio.create_task(self._health_monitoring_loop())
                self.logger.info("Health monitoring started")

        except Exception as e:
            self.logger.error(f"Failed to start health monitoring: {e}")

    async def _stop_health_monitoring(self) -> None:
        """Stop the health monitoring task."""
        try:
            self.monitoring_active = False
            if self.monitoring_task:
                self.monitoring_task.cancel()
                try:
                    await self.monitoring_task
                except asyncio.CancelledError:
                    pass
                self.monitoring_task = None
                self.logger.info("Health monitoring stopped")

        except Exception as e:
            self.logger.error(f"Failed to stop health monitoring: {e}")

    async def _start_periodic_discovery(self) -> None:
        """Start periodic interface discovery."""
        try:
            asyncio.create_task(self._periodic_discovery_loop())

        except Exception as e:
            self.logger.error(f"Failed to start periodic discovery: {e}")

    async def _health_monitoring_loop(self) -> None:
        """Main health monitoring loop."""
        while self.monitoring_active:
            try:
                await self._perform_health_checks()
                await asyncio.sleep(self.health_check_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in health monitoring loop: {e}")
                await asyncio.sleep(5)

    async def _periodic_discovery_loop(self) -> None:
        """Periodic interface discovery loop."""
        while self.is_running:
            try:
                await self._enhanced_interface_discovery()
                await asyncio.sleep(self.discovery_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in periodic discovery loop: {e}")
                await asyncio.sleep(30)

    async def _perform_health_checks(self) -> None:
        """Perform health checks on all interfaces."""
        for interface_type in list(self.interfaces.keys()):
            try:
                await self._check_interface_health(interface_type)

            except Exception as e:
                self.logger.error(f"Error checking health for {interface_type.value}: {e}")

    async def _check_interface_health(self, interface_type: InterfaceType) -> None:
        """Check health of a specific interface."""
        try:
            if interface_type not in self.health_metrics:
                self._initialize_health_metrics()
                return

            health_info = self.health_metrics[interface_type]
            interface_info = self.interfaces[interface_type]

            # Check if interface is responsive
            is_healthy = await self._test_interface_responsiveness(interface_type)

            if is_healthy:
                health_info.status = InterfaceStatus.ACTIVE
                health_info.consecutive_failures = 0
                health_info.last_error = None
            else:
                health_info.consecutive_failures += 1
                health_info.last_error = "Interface unresponsive"

                # Check circuit breaker
                if health_info.consecutive_failures >= self.circuit_breaker_threshold:
                    health_info.status = InterfaceStatus.ERROR
                    await self._handle_interface_failure(interface_type, "Circuit breaker opened")

            health_info.last_check = datetime.now()

            # Update uptime percentage
            if interface_info.last_activity:
                total_runtime = (datetime.now() - self.startup_time).total_seconds()
                if total_runtime > 0:
                    # This is a simplified calculation
                    health_info.uptime_percentage = 100.0 - (health_info.error_count / total_runtime * 100)

        except Exception as e:
            self.logger.error(f"Error checking health for {interface_type.value}: {e}")

    async def _test_interface_responsiveness(self, interface_type: InterfaceType) -> bool:
        """Test if an interface is responsive."""
        try:
            interface_info = self.interfaces[interface_type]

            # Simple health check: check if interface is marked as active
            if interface_info.status != InterfaceStatus.ACTIVE:
                return False

            # For more comprehensive checks, you could:
            # - Send a ping message
            # - Check last activity time
            # - Test interface-specific health endpoints

            return True

        except Exception as e:
            self.logger.error(f"Error testing interface responsiveness for {interface_type.value}: {e}")
            return False

    async def _handle_interface_failure(self, interface_type: InterfaceType, reason: str) -> None:
        """Handle interface failure with recovery attempts."""
        try:
            self.logger.warning(f"Interface failure detected: {interface_type.value} - {reason}")

            await self._emit_interface_event(InterfaceEvent.INTERFACE_ERROR, {
                "interface_type": interface_type.value,
                "error": reason,
                "consecutive_failures": self.health_metrics[interface_type].consecutive_failures
            })

            # Attempt automatic recovery if enabled
            if self.auto_recovery_enabled:
                await self._attempt_interface_recovery(interface_type)

        except Exception as e:
            self.logger.error(f"Error handling interface failure: {e}")

    async def _attempt_interface_recovery(self, interface_type: InterfaceType) -> None:
        """Attempt automatic recovery of a failed interface."""
        try:
            self.logger.info(f"Attempting automatic recovery for {interface_type.value}")

            # Wait before recovery attempt
            await asyncio.sleep(5)

            # Attempt restart
            success = await self.restart_interface(interface_type)

            if success:
                self.logger.info(f"Automatic recovery successful for {interface_type.value}")
                await self._emit_interface_event(InterfaceEvent.INTERFACE_RECOVERED, {
                    "interface_type": interface_type.value,
                    "recovery_type": "automatic"
                })
            else:
                self.logger.error(f"Automatic recovery failed for {interface_type.value}")

        except Exception as e:
            self.logger.error(f"Error during interface recovery: {e}")

    async def _on_message_sent(self, event: Event) -> None:
        """Handle message sent event for metrics."""
        try:
            interface_type = event.data.get('interface_type')
            if interface_type and interface_type in self.health_metrics:
                self.health_metrics[interface_type].message_count += 1

        except Exception as e:
            self.logger.error(f"Error handling message sent event: {e}")

    async def _on_message_received(self, event: Event) -> None:
        """Handle message received event for metrics."""
        try:
            interface_type = event.data.get('interface_type')
            if interface_type and interface_type in self.health_metrics:
                self.health_metrics[interface_type].message_count += 1

        except Exception as e:
            self.logger.error(f"Error handling message received event: {e}")

    async def _emit_interface_event(self, event_type: InterfaceEvent, data: Dict[str, Any]) -> None:
        """Emit an interface event to the event bus."""
        if self.event_bus:
            event = Event(
                type=event_type,
                timestamp=datetime.now(),
                data=data
            )
            await self.event_bus.publish(event)
```

## 3. Event System Implementation

```python
"""
Event system for loose coupling between core and interfaces.
"""

import asyncio
from typing import Dict, List, Callable, Optional, Any
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field
import weakref

from app.utils.logger import get_logger


class CoreEvent(Enum):
    """Core application events."""
    APPLICATION_STARTING = "application_starting"
    APPLICATION_STARTED = "application_started"
    APPLICATION_STOPPING = "application_stopping"
    APPLICATION_STOPPED = "application_stopped"
    APPLICATION_ERROR = "application_error"

    NCREW_INITIALIZING = "ncrew_initializing"
    NCREW_INITIALIZED = "ncrew_initialized"
    NCREW_SHUTTING_DOWN = "ncrew_shutting_down"

    ROLE_INTRODUCTION_STARTING = "role_introduction_starting"
    ROLE_INTRODUCTION_COMPLETED = "role_introduction_completed"

    HEALTH_CHECK_COMPLETED = "health_check_completed"
    CONFIGURATION_RELOADED = "configuration_reloaded"


class InterfaceEvent(Enum):
    """Interface-specific events."""
    INTERFACE_DISCOVERED = "interface_discovered"
    INTERFACE_REGISTERED = "interface_registered"
    INTERFACE_UNREGISTERED = "interface_unregistered"

    INTERFACE_INITIALIZING = "interface_initializing"
    INTERFACE_READY = "interface_ready"
    INTERFACE_ERROR = "interface_error"
    INTERFACE_RECOVERED = "interface_recovered"
    INTERFACE_SHUTDOWN = "interface_shutdown"

    MESSAGE_RECEIVED = "message_received"
    MESSAGE_SENT = "message_sent"
    INTERFACE_CAPACITY_CHANGED = "interface_capacity_changed"


class MessageEvent(Enum):
    """Message routing events."""
    MESSAGE_ROUTING_START = "message_routing_start"
    MESSAGE_ROUTING_COMPLETE = "message_routing_complete"
    MESSAGE_PROCESSING_START = "message_processing_start"
    MESSAGE_PROCESSING_COMPLETE = "message_processing_complete"
    AGENT_RESPONSE_READY = "agent_response_ready"


@dataclass
class Event:
    """Event data structure."""
    type: Enum
    timestamp: datetime
    data: Dict[str, Any] = field(default_factory=dict)
    source: Optional[str] = None
    correlation_id: Optional[str] = None
    priority: int = 0  # Higher priority events processed first


class EventFilter:
    """Filter for event subscriptions."""

    def __init__(
        self,
        event_types: Optional[List[Enum]] = None,
        source_filter: Optional[str] = None,
        data_filter: Optional[Dict[str, Any]] = None
    ):
        self.event_types = set(event_types) if event_types else None
        self.source_filter = source_filter
        self.data_filter = data_filter or {}

    def matches(self, event: Event) -> bool:
        """Check if an event matches this filter."""
        if self.event_types and event.type not in self.event_types:
            return False
        if self.source_filter and event.source != self.source_filter:
            return False
        if self.data_filter:
            for key, value in self.data_filter.items():
                if event.data.get(key) != value:
                    return False
        return True


class EventHandler:
    """Base event handler class."""

    def __init__(self, handler_id: str):
        self.handler_id = handler_id
        self.logger = get_logger(f"{self.__class__.__name__}[{handler_id}]")

    async def handle_event(self, event: Event) -> None:
        """Handle an event. Override in subclasses."""
        raise NotImplementedError("Subclasses must implement handle_event")


class EventBus:
    """
    Central event bus for loose coupling between components.

    Features:
    - Async event handling
    - Event filtering and routing
    - Event persistence and replay
    - Performance monitoring
    - Weak reference handling to prevent memory leaks
    """

    def __init__(self, max_history: int = 1000):
        """
        Initialize the event bus.

        Args:
            max_history: Maximum number of events to keep in history
        """
        self.logger = get_logger(f"{self.__class__.__name__}")
        self.is_running = False
        self.max_history = max_history

        # Event storage
        self.event_history: List[Event] = []
        self.event_handlers: Dict[Enum, List[weakref.ref]] = {}
        self.filtered_handlers: List[tuple] = []  # List of (filter, weakref)

        # Event processing
        self.event_queue: asyncio.Queue = asyncio.Queue()
        self.processing_task: Optional[asyncio.Task] = None
        self.event_count = 0
        self.processing_errors = 0

        # Performance monitoring
        self.start_time: Optional[datetime] = None
        self.last_event_time: Optional[datetime] = None

    async def start(self) -> None:
        """Start the event bus."""
        try:
            if self.is_running:
                return

            self.is_running = True
            self.start_time = datetime.now()
            self.processing_task = asyncio.create_task(self._event_processing_loop())

            self.logger.info("Event bus started")

        except Exception as e:
            self.logger.error(f"Failed to start event bus: {e}")
            raise

    async def stop(self) -> None:
        """Stop the event bus."""
        try:
            if not self.is_running:
                return

            self.is_running = False

            if self.processing_task:
                self.processing_task.cancel()
                try:
                    await self.processing_task
                except asyncio.CancelledError:
                    pass

            # Clear handlers to prevent memory leaks
            self.event_handlers.clear()
            self.filtered_handlers.clear()

            self.logger.info(f"Event bus stopped. Processed {self.event_count} events with {self.processing_errors} errors")

        except Exception as e:
            self.logger.error(f"Failed to stop event bus: {e}")

    async def publish(self, event: Event) -> None:
        """
        Publish an event to the event bus.

        Args:
            event: The event to publish
        """
        try:
            if not self.is_running:
                self.logger.warning("Event bus not running, dropping event")
                return

            # Add to queue for processing
            await self.event_queue.put(event)
            self.last_event_time = datetime.now()

        except Exception as e:
            self.logger.error(f"Failed to publish event {event.type}: {e}")

    async def subscribe(
        self,
        event_type: Enum,
        handler: Callable[[Event], None]
    ) -> str:
        """
        Subscribe to events of a specific type.

        Args:
            event_type: The event type to subscribe to
            handler: The event handler function

        Returns:
            str: Subscription ID for unsubscribing
        """
        try:
            if event_type not in self.event_handlers:
                self.event_handlers[event_type] = []

            # Use weak reference to prevent memory leaks
            if hasattr(handler, '__self__'):
                # Method handler
                handler_ref = weakref.WeakMethod(handler)
            else:
                # Function handler
                handler_ref = weakref.ref(handler)

            self.event_handlers[event_type].append(handler_ref)

            subscription_id = f"{event_type.value}_{len(self.event_handlers[event_type])}"
            self.logger.debug(f"Subscribed to {event_type.value} with ID {subscription_id}")

            return subscription_id

        except Exception as e:
            self.logger.error(f"Failed to subscribe to {event_type.value}: {e}")
            raise

    async def subscribe_filtered(
        self,
        event_filter: EventFilter,
        handler: Callable[[Event], None]
    ) -> str:
        """
        Subscribe to events matching a filter.

        Args:
            event_filter: The event filter
            handler: The event handler function

        Returns:
            str: Subscription ID for unsubscribing
        """
        try:
            # Use weak reference to prevent memory leaks
            if hasattr(handler, '__self__'):
                handler_ref = weakref.WeakMethod(handler)
            else:
                handler_ref = weakref.ref(handler)

            self.filtered_handlers.append((event_filter, handler_ref))

            subscription_id = f"filtered_{len(self.filtered_handlers)}"
            self.logger.debug(f"Subscribed with filter {subscription_id}")

            return subscription_id

        except Exception as e:
            self.logger.error(f"Failed to subscribe with filter: {e}")
            raise

    async def unsubscribe(self, subscription_id: str) -> None:
        """
        Unsubscribe from events.

        Args:
            subscription_id: The subscription ID to unsubscribe
        """
        try:
            # Remove from type-specific handlers
            for event_type, handlers in self.event_handlers.items():
                self.event_handlers[event_type] = [
                    h for h in handlers
                    if f"{event_type.value}_{handlers.index(h)}" != subscription_id
                ]

            # Remove from filtered handlers
            self.filtered_handlers = [
                (f, h) for f, h in self.filtered_handlers
                if f"filtered_{self.filtered_handlers.index((f, h))}" != subscription_id
            ]

            self.logger.debug(f"Unsubscribed: {subscription_id}")

        except Exception as e:
            self.logger.error(f"Failed to unsubscribe {subscription_id}: {e}")

    async def get_event_history(
        self,
        event_type: Optional[Enum] = None,
        since: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> List[Event]:
        """
        Get events from history.

        Args:
            event_type: Filter by event type
            since: Get events since this time
            limit: Maximum number of events to return

        Returns:
            List[Event]: Matching events
        """
        try:
            events = self.event_history

            # Filter by event type
            if event_type:
                events = [e for e in events if e.type == event_type]

            # Filter by time
            if since:
                events = [e for e in events if e.timestamp >= since]

            # Limit results
            if limit:
                events = events[-limit:]

            return events

        except Exception as e:
            self.logger.error(f"Failed to get event history: {e}")
            return []

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get event bus statistics.

        Returns:
            Dict: Statistics about the event bus
        """
        stats = {
            'is_running': self.is_running,
            'event_count': self.event_count,
            'processing_errors': self.processing_errors,
            'queue_size': self.event_queue.qsize(),
            'history_size': len(self.event_history),
            'handler_count': sum(len(handlers) for handlers in self.event_handlers.values()),
            'filtered_handler_count': len(self.filtered_handlers),
        }

        if self.start_time:
            stats['uptime_seconds'] = (datetime.now() - self.start_time).total_seconds()

        if self.last_event_time:
            stats['last_event_age_seconds'] = (datetime.now() - self.last_event_time).total_seconds()

        return stats

    def is_healthy(self) -> bool:
        """
        Check if the event bus is healthy.

        Returns:
            bool: True if healthy
        """
        if not self.is_running:
            return False

        # Check if processing task is still running
        if self.processing_task and self.processing_task.done():
            if self.processing_task.exception():
                return False

        # Check error rate
        if self.event_count > 0:
            error_rate = self.processing_errors / self.event_count
            if error_rate > 0.1:  # More than 10% errors
                return False

        return True

    # Private Methods

    async def _event_processing_loop(self) -> None:
        """Main event processing loop."""
        try:
            while self.is_running:
                try:
                    # Get event from queue
                    event = await asyncio.wait_for(
                        self.event_queue.get(),
                        timeout=1.0
                    )

                    await self._process_event(event)

                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    self.logger.error(f"Error in event processing loop: {e}")
                    self.processing_errors += 1
                    await asyncio.sleep(0.1)  # Prevent tight loop

        except asyncio.CancelledError:
            self.logger.info("Event processing loop cancelled")
        except Exception as e:
            self.logger.error(f"Critical error in event processing loop: {e}")

    async def _process_event(self, event: Event) -> None:
        """Process a single event."""
        try:
            self.event_count += 1

            # Store in history
            self._store_event(event)

            # Get handlers for this event type
            handlers = []

            # Type-specific handlers
            if event.type in self.event_handlers:
                for handler_ref in self.event_handlers[event.type]:
                    handler = handler_ref()
                    if handler:
                        handlers.append(handler)
                    else:
                        # Remove dead weak reference
                        self.event_handlers[event.type].remove(handler_ref)

            # Filtered handlers
            for event_filter, handler_ref in self.filtered_handlers:
                if event_filter.matches(event):
                    handler = handler_ref()
                    if handler:
                        handlers.append(handler)
                    else:
                        # Remove dead weak reference
                        self.filtered_handlers.remove((event_filter, handler_ref))

            # Execute handlers
            if handlers:
                await asyncio.gather(
                    *[self._execute_handler(handler, event) for handler in handlers],
                    return_exceptions=True
                )

        except Exception as e:
            self.logger.error(f"Error processing event {event.type}: {e}")
            self.processing_errors += 1

    def _store_event(self, event: Event) -> None:
        """Store event in history."""
        try:
            self.event_history.append(event)

            # Maintain max history size
            if len(self.event_history) > self.max_history:
                self.event_history = self.event_history[-self.max_history:]

        except Exception as e:
            self.logger.error(f"Error storing event: {e}")

    async def _execute_handler(self, handler: Callable, event: Event) -> None:
        """Execute an event handler safely."""
        try:
            if asyncio.iscoroutinefunction(handler):
                await handler(event)
            else:
                handler(event)

        except Exception as e:
            self.logger.error(f"Error executing event handler for {event.type}: {e}")
            self.processing_errors += 1
```

## Implementation Integration

The enhanced designs integrate seamlessly with the existing NeuroCrew architecture:

### Key Integration Points

1. **Backward Compatibility**: Existing interfaces continue to work without changes
2. **Gradual Migration**: Features can be enabled incrementally
3. **Configuration Extensions**: New configuration options are optional
4. **API Compatibility**: Existing NeuroCrewLab API is preserved

### Migration Path

1. **Deploy Enhanced Core**: Start using the new `NeuroCrewApplication` class
2. **Enable Event System**: Gradually add event handling to components
3. **Activate Enhanced Interfaces**: Replace the basic `InterfaceManager` with the enhanced version
4. **Enable Headless Mode**: Configure operation modes for different deployment scenarios

### Benefits Achieved

1. **Interface Independence**: Core engine functions regardless of interface availability
2. **Runtime Flexibility**: Interfaces can be added/removed without service interruption
3. **Improved Reliability**: Interface failures don't affect core operation
4. **Enhanced Monitoring**: Comprehensive health monitoring and recovery mechanisms
5. **Event-Driven Architecture**: Loose coupling enables better extensibility and maintenance

This comprehensive design provides the interface-agnostic core application lifecycle requested while maintaining full compatibility with the existing NeuroCrew system and enabling new capabilities for flexible deployment and operation.