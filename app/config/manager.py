"""
Configuration management for NeuroCrew Lab.

Loads project configuration from ~/.ncrew/<project>/config.yaml
"""

import os
import shutil
import yaml
from typing import Dict, Optional, List, Any
from pathlib import Path
from dataclasses import dataclass, field, fields

from app.connectors import get_connector_spec
from app.utils.logger import get_logger

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ROLES_FILE = REPO_ROOT / "roles" / "agents.yaml"
DEFAULT_PROMPTS_DIR = REPO_ROOT / "roles" / "prompts"


class ProjectConfig:
    """Configuration for a single project."""

    def __init__(self, project_name: str, config_dir: Path):
        self.project_name = project_name
        self.config_dir = config_dir
        self.project_dir = config_dir / project_name
        self.logger = get_logger(f"ProjectConfig.{project_name}")

    def exists(self) -> bool:
        """Check if project directory exists."""
        return self.project_dir.exists()

    def create(self, config: Optional[Dict[str, Any]] = None):
        """Create project directory with default config.yaml."""
        self.project_dir.mkdir(parents=True, exist_ok=True)
        (self.project_dir / "data").mkdir(exist_ok=True)
        (self.project_dir / "data" / "conversations").mkdir(exist_ok=True)

        # Create default config.yaml
        if config is None:
            config = {
                "main_bot_token": "",
                "target_chat_id": 0,
                "log_level": "INFO",
                "roles": []
            }

        self.save_config(config)

    def get_config_file(self) -> Path:
        """Get path to project config.yaml file."""
        return self.project_dir / "config.yaml"

    def load_config(self) -> Dict[str, Any]:
        """Load configuration from config.yaml."""
        config_file = self.get_config_file()
        if not config_file.exists():
            return {}

        with open(config_file, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}

    def save_config(self, config: Dict[str, Any]):
        """Save configuration to config.yaml."""
        config_file = self.get_config_file()
        with open(config_file, 'w', encoding='utf-8') as f:
            yaml.safe_dump(config, f, sort_keys=False, allow_unicode=True, default_flow_style=False)

    def get_config_value(self, key: str, default: Any = None) -> Any:
        """Get configuration value."""
        config = self.load_config()
        return config.get(key, default)

    def set_config_value(self, key: str, value: Any):
        """Set configuration value."""
        config = self.load_config()
        config[key] = value
        self.save_config(config)


class MultiProjectManager:
    """Manager for multiple NeuroCrew projects."""

    DEFAULT_CONFIG_DIR = Path.home() / ".ncrew"
    CURRENT_PROJECT_FILE = "current_project.txt"
    PROMPTS_DIR = "prompts"

    def __init__(self, config_dir: Optional[Path] = None):
        self.config_dir = config_dir or self.DEFAULT_CONFIG_DIR
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.prompts_dir = self.config_dir / self.PROMPTS_DIR
        self.prompts_dir.mkdir(exist_ok=True)
        self.logger = get_logger("MultiProjectManager")

        # Copy default prompts if prompts_dir is empty
        if not any(self.prompts_dir.glob("*.md")):
            self._copy_default_prompts()

    def get_prompts_dir(self) -> Path:
        """Get shared prompts directory."""
        return self.prompts_dir

    def get_current_project_file(self) -> Path:
        """Get path to file storing current project name."""
        return self.config_dir / self.CURRENT_PROJECT_FILE

    def get_current_project(self) -> Optional[str]:
        """Get name of currently active project."""
        project_file = self.get_current_project_file()
        if not project_file.exists():
            return None
        return project_file.read_text().strip()

    def set_current_project(self, project_name: str):
        """Set currently active project."""
        project_file = self.get_current_project_file()
        project_file.write_text(project_name)
        self.logger.info(f"Set current project to: {project_name}")

    def list_projects(self) -> List[str]:
        """List all available projects."""
        if not self.config_dir.exists():
            return []

        projects = []
        for item in self.config_dir.iterdir():
            if item.is_dir() and not item.name.startswith('.') and item.name != self.PROMPTS_DIR:
                # Check if it has config.yaml
                if (item / "config.yaml").exists():
                    projects.append(item.name)
        return sorted(projects)

    def project_exists(self, project_name: str) -> bool:
        """Check if project exists."""
        project_dir = self.config_dir / project_name
        return project_dir.exists() and (project_dir / "config.yaml").exists()

    def create_project(self, project_name: str, config: Optional[Dict[str, Any]] = None) -> ProjectConfig:
        """Create new project."""
        if self.project_exists(project_name):
            raise ValueError(f"Project '{project_name}' already exists")

        project = ProjectConfig(project_name, self.config_dir)
        project.create(config or self._build_default_project_config())

        self.logger.info(f"Created new project: {project_name}")
        return project

    def get_project(self, project_name: str) -> Optional[ProjectConfig]:
        """Get project configuration."""
        if not self.project_exists(project_name):
            return None
        return ProjectConfig(project_name, self.config_dir)

    def delete_project(self, project_name: str):
        """Delete project."""
        import shutil
        project_dir = self.config_dir / project_name
        if project_dir.exists():
            shutil.rmtree(project_dir)
            self.logger.info(f"Deleted project: {project_name}")

    def load_project_config(self, project_name: str) -> Dict[str, Any]:
        """Load project configuration and apply to environment."""
        project = self.get_project(project_name)
        if not project:
            raise ValueError(f"Project '{project_name}' not found")

        # Load project config.yaml
        config = project.load_config()

        # Apply to environment
        if config.get('main_bot_token'):
            os.environ['MAIN_BOT_TOKEN'] = config['main_bot_token']
        if config.get('target_chat_id'):
            os.environ['TARGET_CHAT_ID'] = str(config['target_chat_id'])
        if config.get('log_level'):
            os.environ['LOG_LEVEL'] = config['log_level']

        # Set bot tokens from roles
        for role in config.get('roles', []):
            if role.get('telegram_bot_token'):
                token_var = f"{role['telegram_bot_name'].upper()}_TOKEN"
                os.environ[token_var] = role['telegram_bot_token']

        self.set_current_project(project_name)

        return {
            "project_name": project_name,
            "config": config,
            "project_dir": str(project.project_dir),
            "prompts_dir": str(self.prompts_dir)
        }

    def save_prompt(self, prompt_name: str, content: str):
        """Save a prompt file to shared prompts directory."""
        prompt_file = self.prompts_dir / f"{prompt_name}.md"
        with open(prompt_file, 'w', encoding='utf-8') as f:
            f.write(content)
        self.logger.info(f"Saved prompt: {prompt_name}")

    def load_prompt(self, prompt_name: str) -> Optional[str]:
        """Load a prompt file from shared prompts directory."""
        prompt_file = self.prompts_dir / f"{prompt_name}.md"
        if not prompt_file.exists():
            return None
        with open(prompt_file, 'r', encoding='utf-8') as f:
            return f.read()

    def list_prompts(self) -> List[str]:
        """List all available prompts."""
        if not self.prompts_dir.exists():
            return []
        return [f.stem for f in self.prompts_dir.glob("*.md")]

    def _copy_default_prompts(self):
        if not DEFAULT_PROMPTS_DIR.exists():
            return
        for prompt_file in DEFAULT_PROMPTS_DIR.glob("*.md"):
            target = self.prompts_dir / prompt_file.name
            if not target.exists():
                shutil.copy2(prompt_file, target)
                self.logger.info(f"Seeded prompt: {prompt_file.name}")

    def _build_default_project_config(self) -> Dict[str, Any]:
        """Build default config from repository roles/agents.yaml if it exists."""
        config = {
            "main_bot_token": "",
            "target_chat_id": 0,
            "log_level": "INFO",
            "roles": []
        }

        if not DEFAULT_ROLES_FILE.exists():
            return config

        try:
            with open(DEFAULT_ROLES_FILE, 'r', encoding='utf-8') as f:
                default_roles_data = yaml.safe_load(f)

            if default_roles_data and 'roles' in default_roles_data:
                for role in default_roles_data['roles']:
                    role_copy = dict(role)
                    prompt_value = role_copy.pop('system_prompt_file', '')
                    if prompt_value:
                        prompt_path = Path(prompt_value)
                        role_copy['prompt_file'] = prompt_path.name
                    else:
                        role_copy['prompt_file'] = ''

                    role_copy.setdefault('telegram_bot_token', '')
                    config['roles'].append(role_copy)

                self.logger.info(f"Seeded {len(config['roles'])} roles from repository defaults")
        except Exception as e:
            self.logger.warning(f"Could not seed roles from repository: {e}")

        return config


# Global instance
multi_project_manager = MultiProjectManager()

def _initialize_project_context() -> Dict[str, Any]:
    """Initialize project context from ~/.ncrew/."""
    project_name = os.getenv("NCREW_PROJECT") or multi_project_manager.get_current_project()

    if not project_name:
        existing_projects = multi_project_manager.list_projects()
        if existing_projects:
            project_name = existing_projects[0]
        else:
            project_name = "default"
            multi_project_manager.create_project(project_name)

    project = multi_project_manager.get_project(project_name)
    if project is None:
        project = multi_project_manager.create_project(project_name)

    # Load config.yaml
    config = project.load_config()

    # Apply to environment
    if config.get('main_bot_token'):
        os.environ['MAIN_BOT_TOKEN'] = config['main_bot_token']
    if config.get('target_chat_id'):
        os.environ['TARGET_CHAT_ID'] = str(config['target_chat_id'])
    if config.get('log_level'):
        os.environ['LOG_LEVEL'] = config['log_level']

    # Set bot tokens from roles
    for role in config.get('roles', []):
        if role.get('telegram_bot_token'):
            token_var = f"{role['telegram_bot_name'].upper()}_TOKEN"
            os.environ[token_var] = role['telegram_bot_token']

    os.environ["NCREW_PROJECT"] = project_name
    os.environ["NCREW_PROJECT_ROOT"] = str(project.project_dir)

    data_dir = project.project_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    return {
        "project_name": project_name,
        "project_dir": project.project_dir,
        "config_file": project.get_config_file(),
        "config": config,
        "data_dir": data_dir,
        "prompts_dir": multi_project_manager.get_prompts_dir(),
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
        # Сначала из конфига роли, потом из словаря
        if self.telegram_bot_token:
            return self.telegram_bot_token
        return Config.TELEGRAM_BOT_TOKENS.get(self.telegram_bot_name)

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

    # From config.yaml
    MAIN_BOT_TOKEN: str = os.getenv("MAIN_BOT_TOKEN", "")
    TARGET_CHAT_ID: int = int(os.getenv("TARGET_CHAT_ID", "0"))
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
    MAX_CONVERSATION_LENGTH: int = int(os.getenv("MAX_CONVERSATION_LENGTH", "200"))
    AGENT_TIMEOUT: int = int(os.getenv("AGENT_TIMEOUT", "600"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
    DATA_DIR: Path = Path(PROJECT_CONTEXT["data_dir"])
    ALLOW_DUMMY_TOKENS: bool = os.getenv("NCREW_ALLOW_DUMMY_TOKENS", "1").lower() in ("1", "true", "yes")

    SYSTEM_REMINDER_INTERVAL: int = int(os.getenv("SYSTEM_REMINDER_INTERVAL", "5"))

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
            token = role.telegram_bot_token or os.getenv(f"{role.telegram_bot_name.upper()}_TOKEN")

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
    def reload_configuration(cls) -> bool:
        """Hot-reload configuration from config.yaml."""
        cls.logger.info("🔄 Starting hot-reload of configuration")

        try:
            project = multi_project_manager.get_project(cls.PROJECT_NAME)
            if not project:
                cls.logger.error(f"Project {cls.PROJECT_NAME} not found")
                return False

            config = project.load_config()

            # Apply to environment
            if config.get('main_bot_token'):
                os.environ['MAIN_BOT_TOKEN'] = config['main_bot_token']
                cls.MAIN_BOT_TOKEN = config['main_bot_token']
            
            if config.get('target_chat_id'):
                os.environ['TARGET_CHAT_ID'] = str(config['target_chat_id'])
                cls.TARGET_CHAT_ID = config['target_chat_id']

            # Reload roles
            old_registry = cls.roles_registry
            cls.roles_registry = RolesRegistry()

            for role_data in config.get("roles", []):
                try:
                    role = create_role_from_dict(role_data)
                    cls.roles_registry.add_role(role)
                except Exception as e:
                    cls.logger.error(f"Failed to parse role {role_data.get('role_name', 'unknown')}: {e}")
                    continue

            cls.role_based_enabled = True
            cls._load_telegram_bot_tokens()

            cls.logger.info(f"✅ Hot-reload completed: {len(cls.roles_registry.get_available_roles())} roles loaded")
            return True

        except Exception as e:
            cls.logger.error(f"Hot-reload failed: {e}")
            return False


# Initialize
Config.load_roles()
if Config.is_role_based_enabled():
    Config._load_telegram_bot_tokens()

# Global configuration instance
config = Config()
