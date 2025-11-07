"""
Configuration management for NeuroCrew Lab.

This module handles all configuration settings including environment variables,
CLI paths, and system parameters.
"""

import os
import yaml
from typing import Dict, Optional, List, Any
from pathlib import Path
from dotenv import load_dotenv
from dataclasses import dataclass, field

# Load environment variables from .env file
load_dotenv()


@dataclass
class RoleConfig:
    """Конфигурация роли агента."""
    # Основные поля (все обязательные аргументы идут первыми)
    role_name: str
    display_name: str
    telegram_bot_name: str
    system_prompt_file: str
    agent_type: str
    cli_command: str

    # Дополнительная информация (с значениями по умолчанию)
    description: str = ""

    # Runtime поля (загружаются при инициализации)
    system_prompt: str = ""
    system_prompt_path: Optional[Path] = None

    def __post_init__(self):
        """Валидация и пост-обработка после инициализации."""
        # Валидация обязательных полей
        if not self.role_name:
            raise ValueError("role_name is required")
        if not self.telegram_bot_name:
            raise ValueError("telegram_bot_name is required")
        if not self.agent_type:
            raise ValueError("agent_type is required")
        if not self.cli_command:
            raise ValueError("cli_command is required")

        # Преобразование строки в Path для системного промпта
        if self.system_prompt_file:
            self.system_prompt_path = Path(self.system_prompt_file)


    def get_bot_token(self) -> Optional[str]:
        """Получает токен для Telegram бота этой роли."""
        return Config.TELEGRAM_BOT_TOKENS.get(self.telegram_bot_name)

    def __str__(self) -> str:
        """Строковое представление роли."""
        return f"Role({self.role_name}: {self.display_name})"

    def __repr__(self) -> str:
        """Детальное строковое представление роли."""
        return (f"RoleConfig(role_name='{self.role_name}', "
                f"agent_type='{self.agent_type}', "
                f"cli_command='{self.cli_command}')")


class RolesRegistry:
    """Реестр ролей с возможностью поиска и фильтрации."""

    def __init__(self):
        self.roles: Dict[str, RoleConfig] = {}

    def add_role(self, role: RoleConfig):
        """Добавляет роль в реестр."""
        if role.role_name in self.roles:
            raise ValueError(f"Role '{role.role_name}' already exists")
        self.roles[role.role_name] = role

    def get_role(self, role_name: str) -> Optional[RoleConfig]:
        """Получает роль по имени."""
        return self.roles.get(role_name)

    def get_roles_by_agent_type(self, agent_type: str) -> List[RoleConfig]:
        """Возвращает список ролей для указанного типа агента."""
        return [role for role in self.roles.values() if role.agent_type == agent_type]


    def get_available_roles(self) -> List[RoleConfig]:
        """Возвращает список всех доступных ролей."""
        return list(self.roles.values())

    def validate_role_dependencies(self) -> List[str]:
        """Проверяет зависимости ролей и возвращает список ошибок."""
        errors = []

        for role_name, role in self.roles.items():
            # Проверяем наличие файла системного промпта
            if role.system_prompt_path and not role.system_prompt_path.exists():
                errors.append(f"Role '{role_name}': System prompt file not found: {role.system_prompt_path}")

            # Проверяем наличие токена для бота
            if not role.get_bot_token():
                errors.append(f"Role '{role_name}': No Telegram bot token found for '{role.telegram_bot_name}'")

            # Проверяем agent_type
            if not role.agent_type:
                errors.append(f"Role '{role_name}': agent_type is missing")
            else:
                # Проверяем, что коннектор существует
                connector_map = {
                    'qwen_acp': 'QwenACPConnector',
                    'gemini_acp': 'GeminiACPConnector',
                }
                if role.agent_type not in connector_map:
                    errors.append(f"Role '{role_name}': Unknown agent_type '{role.agent_type}'")

            # Проверяем cli_command
            if not role.cli_command or not role.cli_command.strip():
                errors.append(f"Role '{role_name}': cli_command is missing or empty")

        return errors


def create_role_from_dict(role_data: Dict[str, Any]) -> RoleConfig:
    """Создает RoleConfig из словаря (для YAML парсинга)."""
    # Создаем роль
    return RoleConfig(**role_data)


class Config:
    """Configuration class for NeuroCrew Lab."""

    # Главный токен для прослушивания
    MAIN_BOT_TOKEN: str = os.getenv('MAIN_BOT_TOKEN', '')

    # ID целевого чата
    TARGET_CHAT_ID: int = int(os.getenv('TARGET_CHAT_ID', '0'))

    # Новый формат токенов для ролей
    TELEGRAM_BOT_TOKENS: Dict[str, str] = {}

    # Role-based configuration
    roles_registry: Optional[RolesRegistry] = None
    role_based_enabled: bool = False

    # System Configuration
    MAX_CONVERSATION_LENGTH: int = int(os.getenv('MAX_CONVERSATION_LENGTH', '50'))
    AGENT_TIMEOUT: int = int(os.getenv('AGENT_TIMEOUT', '120'))
    LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO').upper()
    DATA_DIR: Path = Path(os.getenv('DATA_DIR', './data'))

    # System Reminder Configuration
    SYSTEM_REMINDER_INTERVAL: int = int(os.getenv('SYSTEM_REMINDER_INTERVAL', '5'))

    # Telegram Configuration
    TELEGRAM_MAX_MESSAGE_LENGTH: int = 4096
    MESSAGE_SPLIT_THRESHOLD: int = 4000  # Split before hitting limit

    
    @classmethod
    def validate(cls) -> bool:
        """
        Validate critical configuration settings.

        Returns:
            bool: True if all critical settings are valid

        Raises:
            ValueError: If critical settings are missing or invalid
        """
        # Проверка главного токена
        if not cls.MAIN_BOT_TOKEN or cls.MAIN_BOT_TOKEN == 'your_main_listener_bot_token_here':
            raise ValueError("MAIN_BOT_TOKEN не сконфигурирован.")

        # Проверка ID чата
        if cls.TARGET_CHAT_ID == 0:
            raise ValueError("TARGET_CHAT_ID не сконфигурирован.")

        # Проверка токенов ботов
        if not cls.TELEGRAM_BOT_TOKENS and cls.is_role_based_enabled():
            raise ValueError("TELEGRAM_BOT_TOKENS не сконфигурирован или имеет неверный формат.")

        if cls.MAX_CONVERSATION_LENGTH < 1:
            raise ValueError("MAX_CONVERSATION_LENGTH must be greater than 0")

        if cls.AGENT_TIMEOUT < 1:
            raise ValueError("AGENT_TIMEOUT must be greater than 0")

        if cls.LOG_LEVEL not in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']:
            raise ValueError(f"Invalid LOG_LEVEL: {cls.LOG_LEVEL}")

        return True

    # CLI методы удалены - теперь используем cli_command из agents.yaml

    @classmethod
    def get_data_dir(cls) -> Path:
        """
        Get the data directory and ensure it exists.

        Returns:
            Path: Data directory path
        """
        data_dir = Path(cls.DATA_DIR)
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir

    @classmethod
    def ensure_directories(cls) -> None:
        """Ensure all required directories exist."""
        data_dir = cls.get_data_dir()
        (data_dir / 'conversations').mkdir(exist_ok=True)
        (data_dir / 'logs').mkdir(exist_ok=True)

    @classmethod
    def _load_telegram_bot_tokens(cls):
        """Динамически загружает токены из переменных окружения на основе загруженных ролей."""
        if not cls.is_role_based_enabled():
            print("Warning: Role-based configuration is not enabled, skipping token loading")
            return

        token_dict = {}
        loaded_roles = cls.roles_registry.get_available_roles()

        if not loaded_roles:
            print("Warning: No roles found for token loading")
            cls.TELEGRAM_BOT_TOKENS = token_dict
            return

        print(f"Loading tokens for {len(loaded_roles)} roles...")

        for role in loaded_roles:
            # Проверяем, что у роли есть имя бота
            if not hasattr(role, 'telegram_bot_name') or not role.telegram_bot_name:
                print(f"Warning: Role '{role.role_name}' has no telegram_bot_name, skipping")
                continue

            # Формируем имя переменной окружения
            var_name = f"{role.telegram_bot_name.upper()}_TOKEN"

            # Получаем токен из переменных окружения
            token = os.getenv(var_name)

            if token:
                token_dict[role.telegram_bot_name] = token
                masked_token = token[:4] + "..." if len(token) > 4 else token
                print(f"✓ Loaded token for {role.telegram_bot_name} ({var_name}): {masked_token}")
            else:
                print(f"⚠ Token not found for {role.telegram_bot_name} ({var_name})")

        cls.TELEGRAM_BOT_TOKENS = token_dict

        print(f"Token loading completed: {len(cls.TELEGRAM_BOT_TOKENS)}/{len(loaded_roles)} tokens loaded")

    
    @classmethod
    def load_roles(cls, config_path: Path = Path('roles/agents.yaml')) -> bool:
        """
        Загружает и парсит конфигурацию ролей из agents.yaml.

        Args:
            config_path: Путь к файлу agents.yaml

        Returns:
            bool: True если конфигурация успешно загружена, False в противном случае
        """
        if not config_path.exists():
            return False

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)

            if not config_data or 'roles' not in config_data:
                return False

            # Создаем реестр ролей
            cls.roles_registry = RolesRegistry()

            # Загружаем роли
            for role_data in config_data.get('roles', []):
                try:
                    role = create_role_from_dict(role_data)
                    cls.roles_registry.add_role(role)
                except Exception as e:
                    print(f"Error loading role {role_data.get('role_name', 'unknown')}: {e}")
                    continue

            cls.role_based_enabled = True
            return True

        except Exception as e:
            print(f"Error loading role configuration: {e}")
            return False

    @classmethod
    def is_role_based_enabled(cls) -> bool:
        """Проверяет, включена ли ролевая конфигурация."""
        return cls.role_based_enabled and cls.roles_registry is not None

    @classmethod
    def get_available_roles(cls) -> List[RoleConfig]:
        """Возвращает список доступных ролей."""
        if cls.is_role_based_enabled():
            return cls.roles_registry.get_available_roles()
        return []

    @classmethod
    def get_role_sequence(cls, sequence_name: str = "default") -> List[RoleConfig]:
        """Возвращает последовательность ролей (только доступные роли)."""
        if cls.is_role_based_enabled():
            return cls.roles_registry.get_available_roles()
        return []

    @classmethod
    def get_role_by_name(cls, role_name: str) -> Optional[RoleConfig]:
        """Получает роль по имени."""
        if cls.is_role_based_enabled():
            return cls.roles_registry.get_role(role_name)
        return None

    @classmethod
    def get_roles_by_agent_type(cls, agent_type: str) -> List[RoleConfig]:
        """Возвращает список ролей для указанного типа агента."""
        if cls.is_role_based_enabled():
            return cls.roles_registry.get_roles_by_agent_type(agent_type)
        return []

    @classmethod
    def validate_role_configuration(cls) -> List[str]:
        """Проверяет конфигурацию ролей и возвращает список ошибок."""
        if not cls.is_role_based_enabled():
            return ["Role-based configuration is not enabled"]

        return cls.roles_registry.validate_role_dependencies()

    @classmethod
    def get_configuration_summary(cls) -> Dict[str, any]:
        """Возвращает сводку конфигурации."""
        summary = {
            'main_bot_configured': bool(cls.MAIN_BOT_TOKEN),
            'target_chat_id': cls.TARGET_CHAT_ID,
            'data_dir': str(cls.DATA_DIR),
            'max_conversation_length': cls.MAX_CONVERSATION_LENGTH,
            'agent_timeout': cls.AGENT_TIMEOUT,
            'system_reminder_interval': cls.SYSTEM_REMINDER_INTERVAL,
        }

        if cls.is_role_based_enabled():
            summary['mode'] = 'role_based'
            summary['total_roles'] = len(cls.get_available_roles())
            summary['configured_bots'] = len(cls.TELEGRAM_BOT_TOKENS)
        else:
            summary['mode'] = 'legacy'
            summary['configured_bots'] = len(cls.TELEGRAM_BOT_TOKENS)

        return summary


# Инициализация загрузчиков при импорте
Config.load_roles()  # Сначала загружаем ролевую конфигурацию
if Config.is_role_based_enabled():
    Config._load_telegram_bot_tokens()  # Затем загружаем токены на основе ролей

# Global configuration instance
config = Config()