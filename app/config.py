"""
Configuration management for NeuroCrew Lab.

Loads project configuration from ~/.ncrew/<project>/config.yaml
"""

import os
import yaml
from typing import Dict, Optional, List, Any
from pathlib import Path
from dataclasses import dataclass, field, fields

from app.connectors import get_connector_spec
from app.utils.logger import get_logger
from app.config_manager import multi_project_manager


def _initialize_project_context() -> Dict[str, Any]:
    """Initialize project context from ~/.ncrew/."""
    project_name = os.getenv("NCREW_PROJECT") or multi_project_manager.get_current_project()

    if not project_name:
        project_name = "default"

    project = multi_project_manager.get_project(project_name)
    if project is None:
        raise FileNotFoundError(f"Project '{project_name}' not found and could not be created.")

    # Load config.yaml
    config = project.load_config()
    data_dir = project.project_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    # Set project name to environment for external tools
    os.environ["NCREW_PROJECT"] = project_name

    return {
        "project_name": project_name,
        "project_dir": project.project_dir,
        "config_file": project.get_config_file(),
        "config": config,
        "data_dir": data_dir,
        "prompts_dir": multi_project_manager.get_prompts_dir(),
        # Directly pass config values
        "main_bot_token": config.get("main_bot_token", ""),
        "target_chat_id": int(config.get("target_chat_id", 0)),
        "log_level": config.get("log_level", "INFO").upper(),
        "max_conversation_length": int(config.get("max_conversation_length", 200)),
        "agent_timeout": int(config.get("agent_timeout", 600)),
        "system_reminder_interval": int(config.get("system_reminder_interval", 5)),
    }


PROJECT_CONTEXT = _initialize_project_context()


@dataclass
class RoleConfig:
    """Конфигурация роли агента."""

    # Основные поля
    role_name: str
    display_name: str
    telegram_bot_name: str
    prompt_file: str  # Имя файла в ~/.ncrew/prompts/
    agent_type: str
    cli_command: str = ""

    # Дополнительная информация
    description: str = ""
    is_moderator: bool = False
    telegram_bot_token: str = ""  # Опционально в config.yaml

    # Runtime поля
    system_prompt: str = ""
    system_prompt_path: Optional[Path] = None

    def __post_init__(self):
        """Валидация и пост-обработка после инициализации."""
        connector_spec = get_connector_spec(self.agent_type)
        
        if not self.role_name:
            raise ValueError("role_name is required")
        if not self.telegram_bot_name:
            raise ValueError("telegram_bot_name is required")
        if not self.agent_type:
            raise ValueError("agent_type is required")
        if (not self.cli_command) and (not connector_spec or connector_spec.requires_cli):
            raise ValueError("cli_command is required")

        # Путь к промпту в ~/.ncrew/prompts/
        if self.prompt_file:
            prompts_dir = multi_project_manager.get_prompts_dir()
            self.system_prompt_path = prompts_dir / self.prompt_file

    def get_bot_token(self) -> Optional[str]:
        """Получает токен для Telegram бота этой роли."""
        return self.telegram_bot_token

    def __str__(self) -> str:
        return f"Role({self.role_name}: {self.display_name})"

    def __repr__(self) -> str:
        return f"RoleConfig(role_name='{self.role_name}', agent_type='{self.agent_type}')"


class RolesRegistry:
    """Реестр ролей."""

    def __init__(self):
        self.roles: Dict[str, RoleConfig] = {}

    def add_role(self, role: RoleConfig):
        if role.role_name in self.roles:
            raise ValueError(f"Role '{role.role_name}' already exists")
        self.roles[role.role_name] = role

    def get_role(self, role_name: str) -> Optional[RoleConfig]:
        return self.roles.get(role_name)

    def get_roles_by_agent_type(self, agent_type: str) -> List[RoleConfig]:
        return [role for role in self.roles.values() if role.agent_type == agent_type]

    def get_available_roles(self) -> List[RoleConfig]:
        return list(self.roles.values())

    def validate_role_dependencies(self) -> List[str]:
        """Проверяет зависимости ролей."""
        errors = []

        for role_name, role in self.roles.items():
            connector_spec = get_connector_spec(role.agent_type)
            
            # Проверяем наличие файла промпта
            if role.system_prompt_path and not role.system_prompt_path.exists():
                errors.append(
                    f"Role '{role_name}': Prompt file not found: {role.system_prompt_path}"
                )

            # Проверяем наличие токена
            if not role.get_bot_token():
                errors.append(
                    f"Role '{role_name}': No Telegram bot token for '{role.telegram_bot_name}'"
                )

            # Проверяем agent_type
            if not role.agent_type:
                errors.append(f"Role '{role_name}': agent_type is missing")
            elif not connector_spec:
                errors.append(f"Role '{role_name}': Unknown agent_type '{role.agent_type}'")

            # Проверяем cli_command
            requires_cli = connector_spec.requires_cli if connector_spec else True
            if requires_cli and (not role.cli_command or not role.cli_command.strip()):
                errors.append(f"Role '{role_name}': cli_command is missing or empty")

        return errors


def create_role_from_dict(role_data: Dict[str, Any]) -> RoleConfig:
    """Создает RoleConfig из словаря."""
    allowed_fields = {f.name for f in fields(RoleConfig)}
    sanitized_data = {k: v for k, v in role_data.items() if k in allowed_fields}
    return RoleConfig(**sanitized_data)


class Config:
    """Configuration class for NeuroCrew Lab."""

    logger = get_logger("Config")

    # From config.yaml (via PROJECT_CONTEXT)
    MAIN_BOT_TOKEN: str = PROJECT_CONTEXT["main_bot_token"]
    TARGET_CHAT_ID: int = PROJECT_CONTEXT["target_chat_id"]
    TELEGRAM_BOT_TOKENS: Dict[str, str] = {}

    # Project metadata
    PROJECT_NAME: str = PROJECT_CONTEXT["project_name"]
    PROJECT_DIR: Path = PROJECT_CONTEXT["project_dir"]
    PROJECT_CONFIG_FILE: Path = PROJECT_CONTEXT["config_file"]
    PROMPTS_DIR: Path = PROJECT_CONTEXT["prompts_dir"]

    # Role-based configuration
    roles_registry: Optional[RolesRegistry] = None
    role_based_enabled: bool = False

    # System Configuration
    MAX_CONVERSATION_LENGTH: int = PROJECT_CONTEXT["max_conversation_length"]
    AGENT_TIMEOUT: int = PROJECT_CONTEXT["agent_timeout"]
    LOG_LEVEL: str = PROJECT_CONTEXT["log_level"]
    DATA_DIR: Path = Path(PROJECT_CONTEXT["data_dir"])
    ALLOW_DUMMY_TOKENS: bool = os.getenv("NCREW_ALLOW_DUMMY_TOKENS", "1").lower() in ("1", "true", "yes")

    SYSTEM_REMINDER_INTERVAL: int = PROJECT_CONTEXT["system_reminder_interval"]

    # Telegram Configuration
    TELEGRAM_MAX_MESSAGE_LENGTH: int = 4096
    MESSAGE_SPLIT_THRESHOLD: int = 4000

    @classmethod
    def validate(cls) -> bool:
        """Validate critical configuration settings."""
        if not cls.MAIN_BOT_TOKEN or cls.MAIN_BOT_TOKEN == "your_main_listener_bot_token_here":
            if not cls.ALLOW_DUMMY_TOKENS:
                raise ValueError("MAIN_BOT_TOKEN не сконфигурирован.")
            cls.logger.warning("⚠️  Running with dummy MAIN_BOT_TOKEN (test mode)")

        if cls.TARGET_CHAT_ID == 0:
            if not cls.ALLOW_DUMMY_TOKENS:
                raise ValueError("TARGET_CHAT_ID не сконфигурирован.")
            cls.logger.warning("⚠️  Running with TARGET_CHAT_ID = 0 (test mode)")

        if not cls.TELEGRAM_BOT_TOKENS and cls.is_role_based_enabled():
            if not cls.ALLOW_DUMMY_TOKENS:
                raise ValueError("TELEGRAM_BOT_TOKENS не сконфигурирован.")
            cls.logger.warning("⚠️  Running with no bot tokens (test mode)")

        if cls.MAX_CONVERSATION_LENGTH < 1:
            raise ValueError("MAX_CONVERSATION_LENGTH must be greater than 0")

        if cls.AGENT_TIMEOUT < 1:
            raise ValueError("AGENT_TIMEOUT must be greater than 0")

        if cls.LOG_LEVEL not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            raise ValueError(f"Invalid LOG_LEVEL: {cls.LOG_LEVEL}")

        return True

    @classmethod
    def get_data_dir(cls) -> Path:
        """Get the data directory and ensure it exists."""
        data_dir = Path(cls.DATA_DIR)
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir

    @classmethod
    def ensure_directories(cls) -> None:
        """Ensure all required directories exist."""
        data_dir = cls.get_data_dir()
        (data_dir / "conversations").mkdir(exist_ok=True)
        (data_dir / "logs").mkdir(exist_ok=True)

    @classmethod
    def _load_telegram_bot_tokens(cls):
        """Загружает токены из ролей."""
        if not cls.is_role_based_enabled():
            cls.logger.debug("Role-based configuration is not enabled")
            return

        token_dict = {}
        loaded_roles = cls.roles_registry.get_available_roles()

        if not loaded_roles:
            cls.logger.debug("No roles found for token loading")
            cls.TELEGRAM_BOT_TOKENS = token_dict
            return

        cls.logger.debug(f"Loading tokens for {len(loaded_roles)} roles...")

        loaded_count = 0
        for role in loaded_roles:
            if not hasattr(role, "telegram_bot_name") or not role.telegram_bot_name:
                continue

            # Токен может быть в самой роли или в переменных окружения
            token = role.telegram_bot_token

            if token:
                token_dict[role.telegram_bot_name] = token
                loaded_count += 1
                cls.logger.debug(f"Token loaded for {role.telegram_bot_name}")
            else:
                cls.logger.warning(f"Token not found for {role.telegram_bot_name}")

        cls.TELEGRAM_BOT_TOKENS = token_dict
        cls.logger.info(f"Token loading completed: {loaded_count}/{len(loaded_roles)} tokens loaded")

    @classmethod
    def load_roles(cls) -> bool:
        """Загружает роли из config.yaml текущего проекта."""
        try:
            project = multi_project_manager.get_project(cls.PROJECT_NAME)
            if not project:
                cls.logger.error(f"Project {cls.PROJECT_NAME} not found")
                return False

            config = project.load_config()
            
            if not config or "roles" not in config:
                cls.logger.warning("No roles in config.yaml")
                cls.roles_registry = RolesRegistry()
                cls.role_based_enabled = False
                return False

            cls.roles_registry = RolesRegistry()

            for role_data in config.get("roles", []):
                try:
                    role = create_role_from_dict(role_data)
                    cls.roles_registry.add_role(role)
                except Exception as e:
                    cls.logger.error(f"Error loading role {role_data.get('role_name', 'unknown')}: {e}")
                    continue

            cls.role_based_enabled = True
            return True

        except Exception as e:
            cls.logger.error(f"Error loading role configuration: {e}")
            return False

    @classmethod
    def is_role_based_enabled(cls) -> bool:
        return cls.role_based_enabled and cls.roles_registry is not None

    @classmethod
    def get_available_roles(cls) -> List[RoleConfig]:
        if cls.is_role_based_enabled():
            return cls.roles_registry.get_available_roles()
        return []

    @classmethod
    def get_role_sequence(cls, sequence_name: str = "default") -> List[RoleConfig]:
        if cls.is_role_based_enabled():
            return cls.roles_registry.get_available_roles()
        return []

    @classmethod
    def get_role_by_name(cls, role_name: str) -> Optional[RoleConfig]:
        if cls.is_role_based_enabled():
            return cls.roles_registry.get_role(role_name)
        return None

    @classmethod
    def get_roles_by_agent_type(cls, agent_type: str) -> List[RoleConfig]:
        if cls.is_role_based_enabled():
            return cls.roles_registry.get_roles_by_agent_type(agent_type)
        return []

    @classmethod
    def validate_role_configuration(cls) -> List[str]:
        if not cls.is_role_based_enabled():
            return ["Role-based configuration is not enabled"]
        return cls.roles_registry.validate_role_dependencies()

    @classmethod
    def get_configuration_summary(cls) -> Dict[str, any]:
        """Возвращает сводку конфигурации."""
        summary = {
            "project_name": cls.PROJECT_NAME,
            "main_bot_configured": bool(cls.MAIN_BOT_TOKEN),
            "target_chat_id": cls.TARGET_CHAT_ID,
            "data_dir": str(cls.DATA_DIR),
            "max_conversation_length": cls.MAX_CONVERSATION_LENGTH,
            "agent_timeout": cls.AGENT_TIMEOUT,
        }

        if cls.is_role_based_enabled():
            summary["mode"] = "role_based"
            summary["total_roles"] = len(cls.get_available_roles())
            summary["configured_bots"] = len(cls.TELEGRAM_BOT_TOKENS)
        else:
            summary["mode"] = "no_roles"

        return summary

    @classmethod
    def reload_configuration(cls, project_name: str) -> bool:
        """Hot-reload configuration for a new project."""
        cls.logger.info(f"🔄 Switching project and reloading configuration to '{project_name}'...")

        global PROJECT_CONTEXT

        try:
            # Re-initialize project context for the new project
            os.environ["NCREW_PROJECT"] = project_name
            project = multi_project_manager.get_project(project_name)
            if not project:
                cls.logger.error(f"Project '{project_name}' not found during reload.")
                return False

            config = project.load_config()
            data_dir = project.project_dir / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            
            PROJECT_CONTEXT = {
                "project_name": project_name,
                "project_dir": project.project_dir,
                "config_file": project.get_config_file(),
                "config": config,
                "data_dir": data_dir,
                "prompts_dir": multi_project_manager.get_prompts_dir(),
                "main_bot_token": config.get("main_bot_token", ""),
                "target_chat_id": int(config.get("target_chat_id", 0)),
                "log_level": config.get("log_level", "INFO").upper(),
                "max_conversation_length": int(config.get("max_conversation_length", 200)),
                "agent_timeout": int(config.get("agent_timeout", 600)),
                "system_reminder_interval": int(config.get("system_reminder_interval", 5)),
            }

            # Update Config class attributes
            cls.PROJECT_NAME = PROJECT_CONTEXT["project_name"]
            cls.MAIN_BOT_TOKEN = PROJECT_CONTEXT["main_bot_token"]
            cls.TARGET_CHAT_ID = PROJECT_CONTEXT["target_chat_id"]
            cls.LOG_LEVEL = PROJECT_CONTEXT["log_level"]
            cls.MAX_CONVERSATION_LENGTH = PROJECT_CONTEXT["max_conversation_length"]
            cls.AGENT_TIMEOUT = PROJECT_CONTEXT["agent_timeout"]
            cls.SYSTEM_REMINDER_INTERVAL = PROJECT_CONTEXT["system_reminder_interval"]
            cls.DATA_DIR = Path(PROJECT_CONTEXT["data_dir"])

            # Reload roles and tokens
            cls.load_roles()
            cls._load_telegram_bot_tokens()

            cls.logger.info(f"✅ Hot-reload to '{project_name}' completed: {len(cls.get_available_roles())} roles loaded.")
            return True

        except Exception as e:
            cls.logger.error(f"Hot-reload failed: {e}")
            # Restore previous project name if reload fails
            os.environ["NCREW_PROJECT"] = cls.PROJECT_NAME
            return False

# Initialize
Config.load_roles()
if Config.is_role_based_enabled():
    Config._load_telegram_bot_tokens()

# Global configuration instance
config = Config()
