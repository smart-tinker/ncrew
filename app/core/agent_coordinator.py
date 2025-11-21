"""
Agent Coordinator for NeuroCrew Lab.

Manages role validation, agent lifecycle, and connector coordination.
Handles all agent-related operations including role validation and connector management.
"""

import subprocess
from typing import Dict, List, Optional, Any
from app.config import Config, RoleConfig
from app.connectors import get_connector_class, get_connector_spec
from app.connectors.base import BaseConnector
from app.core.port_manager import PortManager
from app.utils.logger import get_logger
from app.utils.errors import (
    NCrewError,
    ConfigurationError,
    handle_errors
)


class AgentCoordinator:
    """
    Manages AI agent coordination, role validation, and connector lifecycle.

    Responsibilities:
    - Role sequence validation and resource checks
    - Connector creation and management
    - Agent availability monitoring
    - Role-based agent coordination
    """

    def __init__(self, port_manager: PortManager):
        """
        Initialize Agent Coordinator.

        Args:
            port_manager: Port manager instance for connection handling
        """
        self.port_manager = port_manager
        self.logger = get_logger(f"{self.__class__.__name__}")
        self.roles: List[RoleConfig] = []
        self.is_role_based = Config.is_role_based_enabled()

    def validate_and_initialize_roles(self) -> List[RoleConfig]:
        """
        Initialize and validate role sequence with full chain validation.

        Returns:
            List[RoleConfig]: Validated and enabled roles

        Raises:
            ConfigurationError: If role validation fails
        """
        if not self.is_role_based:
            raise ConfigurationError(
                "Role-based configuration is required. Please ensure roles/agents.yaml exists and is valid.",
                config_key="role_based_mode"
            )

        try:
            # Load default role sequence
            all_roles = Config.get_role_sequence("default")

            # Validate complete chain for each role
            validated_roles = []
            validation_summary = {
                "total": len(all_roles),
                "valid": 0,
                "invalid": 0,
                "issues": [],
            }

            self.logger.debug("=== ROLE CHAIN VALIDATION ===")
            for role in all_roles:
                validation_result = self._validate_role_chain(role)

                if validation_result["valid"]:
                    validated_roles.append(role)
                    validation_summary["valid"] += 1
                    self.logger.debug(f"✅ {role.role_name} - VALID")
                else:
                    validation_summary["invalid"] += 1
                    validation_summary["issues"].extend(validation_result["issues"])
                    self.logger.warning(
                        f"❌ {role.role_name} - INVALID: {', '.join(validation_result['issues'])}"
                    )

            # Log summary
            self.logger.debug(f"=== VALIDATION SUMMARY ===")
            self.logger.debug(f"Total roles: {validation_summary['total']}")
            self.logger.debug(f"Valid roles: {validation_summary['valid']}")
            self.logger.debug(f"Invalid roles: {validation_summary['invalid']}")

            if validation_summary["valid"] == 0:
                raise ConfigurationError(
                    "❌ CRITICAL: No valid roles found. System cannot start.",
                    config_key="role_validation"
                )

            # Enforce resource availability (command + token)
            enabled_roles = self._filter_roles_by_resources(validated_roles)

            if not enabled_roles:
                raise ConfigurationError(
                    "❌ CRITICAL: No enabled roles after resource checks.",
                    config_key="resource_validation"
                )

            self.roles = enabled_roles
            self.logger.info(
                f"🎯 Active roles in queue: {[role.role_name for role in self.roles]}"
            )
            self.logger.info(
                "Resource validation summary: enabled=%d disabled=%d",
                len(self.roles),
                len(validated_roles) - len(self.roles),
            )

            return self.roles

        except Exception as e:
            self.logger.error(f"Failed to initialize and validate role sequence: {e}")
            raise ConfigurationError(
                "Failed to initialize role sequence",
                config_key="role_validation",
                original_error=e
            )

    def _filter_roles_by_resources(self, roles: List[RoleConfig]) -> List[RoleConfig]:
        """
        Filter roles based on resource availability (CLI command and bot token).

        Args:
            roles: List of validated roles

        Returns:
            List[RoleConfig]: Roles with available resources
        """
        enabled_roles = []
        disabled_roles = []

        for role in roles:
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

        for role, missing in disabled_roles:
            self.logger.warning(
                f"Role {role.role_name} disabled (missing: {', '.join(missing)})"
            )

        return enabled_roles

    def _validate_role_chain(self, role: RoleConfig) -> Dict[str, Any]:
        """
        Validate complete chain: Role + Connector + Command + Token

        Args:
            role: Role configuration to validate

        Returns:
            dict: {'valid': bool, 'issues': list}
        """
        issues = []

        connector_spec = get_connector_spec(getattr(role, "agent_type", None))

        # 1. Validate role configuration
        if not getattr(role, "role_name", None):
            issues.append("missing role_name")
        if not getattr(role, "agent_type", None):
            issues.append("missing agent_type")
        if not getattr(role, "telegram_bot_name", None):
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

    def _validate_connector(self, agent_type: str) -> bool:
        """
        Check if connector exists for agent type.

        Args:
            agent_type: Type of agent to validate

        Returns:
            bool: True if connector is available
        """
        try:
            connector_class = get_connector_class(agent_type)
            return connector_class is not None
        except ImportError as e:
            self.logger.error(f"Connector import error: {e}")
            return False

    def _validate_cli_command(self, cli_command: str) -> bool:
        """
        Validate CLI command is available.

        Args:
            cli_command: Command string to validate

        Returns:
            bool: True if command is available
        """
        try:
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

    def _validate_telegram_token(self, telegram_bot_name: str) -> bool:
        """
        Validate Telegram bot token exists and is not empty.

        Args:
            telegram_bot_name: Name of the Telegram bot

        Returns:
            bool: True if token is valid
        """
        try:
            if not getattr(Config, "TELEGRAM_BOT_TOKENS", None):
                return False

            token = Config.TELEGRAM_BOT_TOKENS.get(telegram_bot_name)
            return token is not None and len(token.strip()) > 0
        except Exception:
            return False

    def create_connector_for_role(self, role: RoleConfig) -> BaseConnector:
        """
        Create a connector instance for a specific role.

        Args:
            role: Role configuration

        Returns:
            BaseConnector: Connector instance

        Raises:
            ValueError: If agent type is unsupported
        """
        agent_type = role.agent_type.lower()

        connector_class = get_connector_class(agent_type)
        if not connector_class:
            raise ValueError(f"Unsupported agent type: {agent_type}")

        return connector_class()

    async def get_or_create_connector(self, chat_id: int, role: RoleConfig) -> BaseConnector:
        """
        Get or create a connector for a role using port manager.

        Args:
            chat_id: Telegram chat ID
            role: Role configuration

        Returns:
            BaseConnector: Connector instance
        """
        def connector_factory():
            return self.create_connector_for_role(role)

        return await self.port_manager.get_or_create_connection(
            chat_id, role.role_name, connector_factory
        )

    async def get_agent_status(self) -> Dict[str, bool]:
        """
        Get status of all configured roles/agents.

        Returns:
            Dict[str, bool]: Role availability status
        """
        status: Dict[str, bool] = {}

        for role in self.roles:
            try:
                connector = self.create_connector_for_role(role)
                status[role.agent_type] = connector.check_availability()
            except Exception as e:
                self.logger.warning(
                    f"Failed to check availability for role {role.role_name}: {e}"
                )
                status[role.agent_type] = False

        self.logger.debug(f"Role status: {status}")
        return status

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
                    connector = self.create_connector_for_role(role)
                    info = connector.get_info()
                    info.update({
                        "role_name": role.role_name,
                        "display_name": role.display_name,
                        "cli_command": role.cli_command,
                    })
                    return info
                except Exception as e:
                    self.logger.warning(f"Failed to get info for {agent_name}: {e}")
                    return None
        return None

    def get_roles(self) -> List[RoleConfig]:
        """
        Get list of validated roles.

        Returns:
            List[RoleConfig]: Validated roles
        """
        return self.roles

    def get_role_count(self) -> int:
        """
        Get number of validated roles.

        Returns:
            int: Number of roles
        """
        return len(self.roles)