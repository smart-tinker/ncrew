"""
Обработка ошибок для NeuroCrew Lab.

Базовые классы и функции для унифицированной обработки ошибок
вместо многочисленных блоков except Exception.
"""

from enum import Enum
from typing import Optional, Any, Dict
import logging
from pathlib import Path


class ErrorSeverity(Enum):
    """Уровни критичности ошибок."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Категории ошибок."""
    CONNECTOR = "connector"
    STORAGE = "storage"
    TELEGRAM = "telegram"
    CONFIGURATION = "configuration"
    NETWORK = "network"
    TIMEOUT = "timeout"
    VALIDATION = "validation"
    SYSTEM = "system"


class NCrewError(Exception):
    """
    Базовый класс ошибок NeuroCrew Lab.

    Заменяет множественные блоки except Exception на структурированный подход.
    """

    def __init__(
        self,
        message: str,
        category: ErrorCategory = ErrorCategory.SYSTEM,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        details: Optional[Dict[str, Any]] = None,
        original_error: Optional[Exception] = None
    ):
        super().__init__(message)
        self.message = message
        self.category = category
        self.severity = severity
        self.details = details or {}
        self.original_error = original_error

    def to_dict(self) -> Dict[str, Any]:
        """Преобразование ошибки в словарь для логирования."""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "category": self.category.value,
            "severity": self.severity.value,
            "details": self.details,
            "original_error": str(self.original_error) if self.original_error else None
        }


class ConnectorError(NCrewError):
    """Ошибка при работе с AI-коннекторами."""

    def __init__(self, message: str, connector_name: str = "", original_error: Optional[Exception] = None):
        super().__init__(
            message=message,
            category=ErrorCategory.CONNECTOR,
            severity=ErrorSeverity.HIGH,
            details={"connector_name": connector_name},
            original_error=original_error
        )
        self.connector_name = connector_name


class StorageError(NCrewError):
    """Ошибка при работе с хранилищем данных."""

    def __init__(self, message: str, file_path: Optional[Path] = None, original_error: Optional[Exception] = None):
        super().__init__(
            message=message,
            category=ErrorCategory.STORAGE,
            severity=ErrorSeverity.MEDIUM,
            details={"file_path": str(file_path) if file_path else None},
            original_error=original_error
        )
        self.file_path = file_path


class TelegramError(NCrewError):
    """Ошибка при работе с Telegram."""

    def __init__(self, message: str, chat_id: Optional[int] = None, original_error: Optional[Exception] = None):
        super().__init__(
            message=message,
            category=ErrorCategory.TELEGRAM,
            severity=ErrorSeverity.MEDIUM,
            details={"chat_id": chat_id},
            original_error=original_error
        )
        self.chat_id = chat_id


class ConfigurationError(NCrewError):
    """Ошибка конфигурации."""

    def __init__(self, message: str, config_key: str = "", original_error: Optional[Exception] = None):
        super().__init__(
            message=message,
            category=ErrorCategory.CONFIGURATION,
            severity=ErrorSeverity.CRITICAL,
            details={"config_key": config_key},
            original_error=original_error
        )
        self.config_key = config_key


class TimeoutError(NCrewError):
    """Ошибка таймаута."""

    def __init__(self, message: str, timeout_seconds: float = 0, operation: str = ""):
        super().__init__(
            message=message,
            category=ErrorCategory.TIMEOUT,
            severity=ErrorSeverity.HIGH,
            details={"timeout_seconds": timeout_seconds, "operation": operation}
        )
        self.timeout_seconds = timeout_seconds
        self.operation = operation


class ValidationError(NCrewError):
    """Ошибка валидации данных."""

    def __init__(self, message: str, field_name: str = "", value: Any = None):
        super().__init__(
            message=message,
            category=ErrorCategory.VALIDATION,
            severity=ErrorSeverity.LOW,
            details={"field_name": field_name, "value": str(value)},
        )
        self.field_name = field_name
        self.value = value


class MemoryError(NCrewError):
    """Ошибка управления памятью."""

    def __init__(self, message: str, memory_type: str = "", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            category=ErrorCategory.SYSTEM,
            severity=ErrorSeverity.HIGH,
            details={"memory_type": memory_type, **(details or {})},
        )
        self.memory_type = memory_type


class PortError(NCrewError):
    """Ошибка управления портами/соединениями."""

    def __init__(self, message: str, connection_info: str = "", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            category=ErrorCategory.SYSTEM,
            severity=ErrorSeverity.HIGH,
            details={"connection_info": connection_info, **(details or {})},
        )
        self.connection_info = connection_info


def log_error(logger: logging.Logger, error: Exception, context: str = "") -> None:
    """
    Унифицированное логирование ошибок.

    Args:
        logger: Логгер
        error: Исключение
        context: Контекст ошибки
    """
    if isinstance(error, NCrewError):
        # Структурированное логирование для NCrewError
        error_data = error.to_dict()
        context_str = f" [{context}]" if context else ""

        if error.severity == ErrorSeverity.CRITICAL:
            logger.critical(f"CRITICAL{context_str}: {error_data['error_type']} - {error_data['message']}")
        elif error.severity == ErrorSeverity.HIGH:
            logger.error(f"HIGH{context_str}: {error_data['error_type']} - {error_data['message']}")
        elif error.severity == ErrorSeverity.MEDIUM:
            logger.warning(f"MEDIUM{context_str}: {error_data['error_type']} - {error_data['message']}")
        else:
            logger.info(f"LOW{context_str}: {error_data['error_type']} - {error_data['message']}")

        # Детали в debug
        if error.details:
            logger.debug(f"Error details: {error.details}")

    else:
        # Для стандартных исключений
        context_str = f" [{context}]" if context else ""
        logger.error(f"Unexpected error{context_str}: {type(error).__name__}: {error}")


def handle_exception(
    func_name: str,
    error: Exception,
    logger: Optional[logging.Logger] = None,
    context: str = "",
    reraise: bool = False
) -> Optional[str]:
    """
    Обработчик исключений для замены блоков except Exception.

    Args:
        func_name: Имя функции где произошла ошибка
        error: Исключение
        logger: Логгер
        context: Контекст
        reraise: Перебросить исключение

    Returns:
        Сообщение об ошибке для пользователя или None если reraise=True
    """
    if logger:
        log_error(logger, error, f"{func_name}{context}")

    # Формируем пользовательское сообщение
    if isinstance(error, ConnectorError):
        return f"❌ Ошибка AI-ассистента: {error.message}"
    elif isinstance(error, StorageError):
        return f"❌ Ошибка сохранения данных: {error.message}"
    elif isinstance(error, TelegramError):
        return f"❌ Ошибка отправки сообщения: {error.message}"
    elif isinstance(error, TimeoutError):
        return f"⏰ Превышено время ожидания: {error.message}"
    elif isinstance(error, ValidationError):
        return f"⚠️ Ошибка валидации: {error.message}"
    elif isinstance(error, ConfigurationError):
        return f"⚙️ Ошибка конфигурации: {error.message}"
    else:
        return f"❌ Произошла непредвиденная ошибка: {str(error)}"

    if reraise:
        raise error

    return None


def safe_execute(
    func,
    logger: Optional[logging.Logger] = None,
    context: str = "",
    default_return: Any = None,
    error_message: Optional[str] = None
) -> Any:
    """
    Безопасное выполнение функции с обработкой ошибок.

    Args:
        func: Функция для выполнения
        logger: Логгер
        context: Контекст выполнения
        default_return: Значение по умолчанию при ошибке
        error_message: Пользовательское сообщение об ошибке

    Returns:
        Результат функции или default_return при ошибке
    """
    try:
        return func()
    except Exception as e:
        func_name = getattr(func, '__name__', 'unknown_function')

        # Логируем ошибку
        if logger:
            log_error(logger, e, f"{func_name}{context}")

        # Если нужно вернуть ошибку пользователю
        if error_message:
            user_msg = handle_exception(func_name, e, logger, context, reraise=False)
            return error_message if user_msg else default_return

        return default_return


# Удобные декораторы для обработки ошибок
def handle_errors(
    logger: Optional[logging.Logger] = None,
    context: str = "",
    return_on_error: Any = None,
    error_message: Optional[str] = None
):
    """
    Декоратор для автоматической обработки ошибок в функциях.

    Usage:
        @handle_errors(logger=my_logger, context="processing user input")
        def my_function():
            pass
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            return safe_execute(
                lambda: func(*args, **kwargs),
                logger=logger,
                context=context,
                default_return=return_on_error,
                error_message=error_message
            )
        return wrapper
    return decorator