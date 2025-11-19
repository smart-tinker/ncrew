"""
Logging utilities for NeuroCrew Lab.

This module provides centralized logging configuration and utilities
with security enhancements to prevent sensitive data exposure.
"""

import logging
import sys
from pathlib import Path
from typing import Optional
from .security import sanitize_for_logging


def setup_logger(
    name: str,
    level: str = 'INFO',
    log_file: Optional[Path] = None,
    format_string: Optional[str] = None,
    use_security_formatter: bool = True
) -> logging.Logger:
    """
    Set up a logger with console and optional file output.

    Args:
        name: Logger name
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional log file path
        format_string: Custom format string
        use_security_formatter: Whether to use security-enhanced formatter

    Returns:
        logging.Logger: Configured logger instance
    """
    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False

    # Clear existing handlers
    logger.handlers.clear()

    # Default format
    if format_string is None:
        format_string = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

    # Use security formatter if enabled
    if use_security_formatter:
        formatter = SecurityFormatter(format_string)
    else:
        formatter = logging.Formatter(format_string)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler (if specified)
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)  # More verbose for files
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get an existing logger or create a default one.

    Args:
        name: Logger name

    Returns:
        logging.Logger: Logger instance
    """
    root_logger = logging.getLogger('ncrew')
    return root_logger.getChild(name)


class SecurityFormatter(logging.Formatter):
    """
    Custom logging formatter that automatically sanitizes sensitive data.
    """

    def __init__(self, fmt=None, datefmt=None):
        super().__init__(fmt, datefmt)

    def format(self, record):
        # Sanitize the message to prevent sensitive data exposure
        if hasattr(record, 'msg') and isinstance(record.msg, str):
            record.msg = sanitize_for_logging(record.msg)

        # Sanitize any additional arguments
        if hasattr(record, 'args') and record.args:
            sanitized_args = tuple(
                sanitize_for_logging(str(arg)) if isinstance(arg, str) else arg
                for arg in record.args
            )
            record.args = sanitized_args

        return super().format(record)


def log_function_call(logger: logging.Logger, func_name: str, **kwargs) -> None:
    """
    Log a function call with parameters (sanitized).

    Args:
        logger: Logger instance
        func_name: Name of the function being called
        **kwargs: Function parameters
    """
    # Sanitize parameters before logging
    sanitized_params = {}
    for k, v in kwargs.items():
        if isinstance(v, str):
            sanitized_params[k] = sanitize_for_logging(v)
        elif hasattr(v, '__str__'):
            sanitized_params[k] = sanitize_for_logging(str(v))
        else:
            sanitized_params[k] = v

    params_str = ', '.join(f"{k}={v}" for k, v in sanitized_params.items())
    logger.debug(f"Calling {func_name}({params_str})")


def log_error(logger: logging.Logger, error: Exception, context: str = "") -> None:
    """
    Log an error with context.

    Args:
        logger: Logger instance
        error: Exception that occurred
        context: Additional context information
    """
    context_str = f" [{context}]" if context else ""
    logger.error(f"Error{context_str}: {type(error).__name__}: {error}")


def log_info(logger: logging.Logger, message: str, level: str = 'INFO') -> None:
    """
    Log an informational message.

    Args:
        logger: Logger instance
        message: Message to log
        level: Log level (default: INFO)
    """
    log_method = getattr(logger, level.lower(), logger.info)
    log_method(message)


# Default logger configuration
default_logger = setup_logger('ncrew')
