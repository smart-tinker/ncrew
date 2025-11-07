"""
Security utilities for NeuroCrew Lab.

This module provides security functions for input validation, command sanitization,
and security checks to prevent command injection and other attacks.
"""

import re
import shlex
from typing import List, Optional, Set
from pathlib import Path


class SecurityValidator:
    """Security validation utilities for input sanitization and command checking."""

    # Dangerous characters and patterns that could lead to command injection
    DANGEROUS_PATTERNS = [
        r'[;&|`$(){}[\]<>*~]',   # Shell metacharacters (removed ? for normal questions)
        r'\.\.',                 # Directory traversal
        r'\/etc\/',              # System file access
        r'\/proc\/',             # Process filesystem
        r'\/sys\/',              # System filesystem
    ]

    # Allowed CLI commands for subprocess execution
    ALLOWED_CLI_COMMANDS = {
        'qwen', 'claude', 'gemini', 'chatgpt',  # AI agents
        'python', 'python3',                       # Python interpreters
        'node', 'npm',                             # Node.js tools
        'git',                                     # Version control
        'ls', 'cd', 'pwd', 'cat', 'echo',         # Basic shell commands
    }

    # Max message length to prevent DoS
    MAX_MESSAGE_LENGTH = 10000

    # Max file path length
    MAX_PATH_LENGTH = 4096

    def __init__(self):
        """Initialize security validator with compiled patterns."""
        self.dangerous_regex = re.compile('|'.join(self.DANGEROUS_PATTERNS), re.IGNORECASE)

    def validate_message_input(self, message: str) -> tuple[bool, Optional[str]]:
        """
        Validate incoming message input for security threats.

        Args:
            message: Input message to validate

        Returns:
            tuple[bool, Optional[str]]: (is_valid, error_message)
        """
        if not isinstance(message, str):
            return False, "Message must be a string"

        # Length check
        if len(message) > self.MAX_MESSAGE_LENGTH:
            return False, f"Message too long (max {self.MAX_MESSAGE_LENGTH} characters)"

        # Check for null bytes
        if '\x00' in message:
            return False, "Message contains invalid characters"

        # Check for test commands that might affect system stability
        # NOTE: Test commands are now allowed for legitimate testing
        # test_patterns = [
        #     r'^\s*тест\s*$',           # Russian test command
        #     r'^\s*test\s*$',           # English test command
        #     r'^\s*ТЕСТ\s*$',           # Russian test command (uppercase)
        #     r'^\s*TEST\s*$',           # English test command (uppercase)
        #     r'^\s*\.{3,}\s*$',         # Multiple dots (like ".....")
        # ]

        # test_pattern_regex = re.compile('|'.join(test_patterns), re.IGNORECASE)
        # if test_pattern_regex.search(message):
        #     return False, "Test commands are not allowed in this context"

        # Security checks removed - agents handle their own restrictions
        # message_dangerous_patterns = [
        #     r'[;&|`$(){}[\]<>*~]',           # Shell metacharacters
        #     r'\brm\s+-rf\s+/',               # rm -rf / command
        #     r'\brm\s+-rf\s+\.',             # rm -rf . command
        #     r'\bnc\s+-l\s+\d+',             # netcat listener
        #     r'\bwget\s+http',               # wget download
        #     r'\bcurl\s+http',               # curl download
        #     r'\.\./',                       # Directory traversal
        #     r'/etc/passwd',                 # System file access
        #     r'/proc/version',               # System file access
        #     r'/sys/',                       # System filesystem
        # ]

        # message_pattern_regex = re.compile('|'.join(message_dangerous_patterns), re.IGNORECASE)
        # if message_pattern_regex.search(message):
        #     return False, "Message contains potentially dangerous content"

        return True, None

    def validate_file_path(self, file_path: str) -> tuple[bool, Optional[str]]:
        """
        Validate file path to prevent directory traversal and system access.

        Args:
            file_path: File path to validate

        Returns:
            tuple[bool, Optional[str]]: (is_valid, error_message)
        """
        if not isinstance(file_path, str):
            return False, "File path must be a string"

        # Length check
        if len(file_path) > self.MAX_PATH_LENGTH:
            return False, f"Path too long (max {self.MAX_PATH_LENGTH} characters)"

        # Normalize path
        try:
            normalized_path = Path(file_path).resolve()
        except (OSError, ValueError) as e:
            return False, f"Invalid path: {e}"

        # Check for dangerous patterns
        if self.dangerous_regex.search(file_path):
            return False, "Path contains potentially dangerous content"

        # Check for null bytes
        if '\x00' in file_path:
            return False, "Path contains invalid characters"

        # Ensure path stays within expected boundaries
        try:
            # Restrict to current working directory and data directory
            cwd = Path.cwd()
            data_dir = Path.cwd() / 'data'

            # Allow paths within current directory or data directory
            if not (normalized_path.is_relative_to(cwd) or normalized_path.is_relative_to(data_dir)):
                return False, "Path outside allowed directories"
        except AttributeError:
            # Python < 3.9 fallback
            try:
                if str(normalized_path).startswith(str(cwd)) or str(normalized_path).startswith(str(data_dir)):
                    pass
                else:
                    return False, "Path outside allowed directories"
            except Exception:
                return False, "Invalid path validation"

        return True, None

    def validate_cli_command(self, command: str) -> tuple[bool, Optional[str]]:
        """
        Validate CLI command against allowlist to prevent command injection.

        Args:
            command: CLI command to validate

        Returns:
            tuple[bool, Optional[str]]: (is_valid, error_message)
        """
        if not isinstance(command, str):
            return False, "Command must be a string"

        # Parse command safely
        try:
            parts = shlex.split(command)
        except ValueError as e:
            return False, f"Invalid command format: {e}"

        if not parts:
            return False, "Empty command"

        # Extract base command (first part without path)
        base_command = Path(parts[0]).name

        # Check against allowlist
        if base_command not in self.ALLOWED_CLI_COMMANDS:
            return False, f"Command '{base_command}' not in allowlist"

        # Validate arguments - be more permissive with legitimate options
        for arg in parts[1:]:
            # Check for truly dangerous patterns in arguments
            if self.dangerous_regex.search(arg):
                # Allow common legitimate options like --help, --version
                if arg.startswith('--') and arg.lstrip('-').replace('-', '').isalnum():
                    continue
                # Allow single character options like -i, -v, -h
                elif arg.startswith('-') and len(arg) == 2 and arg[1].isalnum():
                    continue
                # Allow numbered options like -O2
                elif arg.startswith('-') and len(arg) == 3 and arg[1] == 'O' and arg[2].isdigit():
                    continue
                else:
                    return False, f"Argument '{arg}' contains dangerous content"

        return True, None

    def sanitize_message(self, message: str) -> str:
        """
        Sanitize message for safe logging and display.

        Args:
            message: Message to sanitize

        Returns:
            str: Sanitized message safe for logging
        """
        if not isinstance(message, str):
            return str(message)

        # Remove or replace sensitive information
        sanitized = message

        # Remove potential tokens (look for typical token patterns)
        token_pattern = r'\b[A-Za-z0-9]{20,}\b'
        sanitized = re.sub(token_pattern, '[REDACTED]', sanitized)

        # Remove API keys (common patterns)
        api_key_patterns = [
            r'\b[A-Za-z0-9_-]{32,}\b',  # Generic API keys
            r'sk-[A-Za-z0-9_-]+',       # OpenAI style
            r'ghp_[A-Za-z0-9_-]+',      # GitHub tokens
        ]

        for pattern in api_key_patterns:
            sanitized = re.sub(pattern, '[REDACTED]', sanitized)

        # Truncate very long messages
        if len(sanitized) > 500:
            sanitized = sanitized[:500] + '...'

        return sanitized

    def validate_role_name(self, role_name: str) -> tuple[bool, Optional[str]]:
        """
        Validate role name for security and format compliance.

        Args:
            role_name: Role name to validate

        Returns:
            tuple[bool, Optional[str]]: (is_valid, error_message)
        """
        if not isinstance(role_name, str):
            return False, "Role name must be a string"

        # Length check
        if not (2 <= len(role_name) <= 50):
            return False, "Role name must be 2-50 characters long"

        # Pattern check (alphanumeric, underscores, hyphens only)
        if not re.match(r'^[a-zA-Z0-9_-]+$', role_name):
            return False, "Role name can only contain letters, numbers, underscores, and hyphens"

        # Check for dangerous patterns
        if self.dangerous_regex.search(role_name):
            return False, "Role name contains potentially dangerous content"

        return True, None

    def get_allowed_commands(self) -> Set[str]:
        """
        Get the set of allowed CLI commands.

        Returns:
            Set[str]: Set of allowed command names
        """
        return self.ALLOWED_CLI_COMMANDS.copy()


# Global security validator instance
security_validator = SecurityValidator()


def validate_input(message: str, input_type: str = "message") -> tuple[bool, Optional[str]]:
    """
    Convenience function to validate different types of input.

    Args:
        message: Input to validate
        input_type: Type of input ("message", "file_path", "cli_command", "role_name")

    Returns:
        tuple[bool, Optional[str]]: (is_valid, error_message)
    """
    if input_type == "message":
        return security_validator.validate_message_input(message)
    elif input_type == "file_path":
        return security_validator.validate_file_path(message)
    elif input_type == "cli_command":
        return security_validator.validate_cli_command(message)
    elif input_type == "role_name":
        return security_validator.validate_role_name(message)
    else:
        return False, f"Unknown input type: {input_type}"


def sanitize_for_logging(message: str) -> str:
    """
    Convenience function to sanitize message for safe logging.

    Args:
        message: Message to sanitize

    Returns:
        str: Sanitized message
    """
    return security_validator.sanitize_message(message)