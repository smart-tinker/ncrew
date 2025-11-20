"""
Message formatting utilities for NeuroCrew Lab.

This module provides utilities for formatting messages for Telegram
and other output formats.
"""

import textwrap
import re
from typing import List


def split_long_message(
    text: str, max_length: int = 4096, threshold: int = 4000
) -> List[str]:
    """
    Split a long message into multiple smaller messages for Telegram.

    Args:
        text: Message text to split
        max_length: Maximum allowed message length
        threshold: Threshold at which to start splitting

    Returns:
        List[str]: List of message chunks
    """
    if len(text) <= threshold:
        return [text]

    # Split by paragraphs first
    paragraphs = text.split("\n\n")
    messages = []
    current_message = ""

    for paragraph in paragraphs:
        # If adding this paragraph would exceed threshold
        if len(current_message) + len(paragraph) + 2 > threshold:
            if current_message:
                messages.append(current_message.strip())
                current_message = paragraph
            else:
                # Single paragraph too long, split by lines
                lines = paragraph.split("\n")
                for line in lines:
                    if len(current_message) + len(line) + 1 > threshold:
                        if current_message:
                            messages.append(current_message.strip())
                        current_message = line
                    else:
                        if current_message:
                            current_message += "\n" + line
                        else:
                            current_message = line
        else:
            if current_message:
                current_message += "\n\n" + paragraph
            else:
                current_message = paragraph

    # Add remaining text
    if current_message:
        messages.append(current_message.strip())

    # Ensure all messages are within max_length
    final_messages = []
    for message in messages:
        if len(message) > max_length:
            # Split into chunks with strict length enforcement
            for i in range(0, len(message), max_length):
                chunk = message[i : i + max_length]
                final_messages.append(chunk)
        else:
            final_messages.append(message)

    # Add part indicators if multiple messages and ensure length constraints
    if len(final_messages) > 1:
        for i in range(len(final_messages)):
            part_indicator = f"({i + 1}/{len(final_messages)}) "
            # If adding part indicator would exceed max_length, truncate the message
            if len(final_messages[i]) + len(part_indicator) > max_length:
                max_content_length = max_length - len(part_indicator)
                final_messages[i] = final_messages[i][:max_content_length]
            final_messages[i] = part_indicator + final_messages[i]

    return final_messages


def format_code_block(code: str, language: str = "") -> str:
    """
    Format code as a Telegram code block.

    Args:
        code: Code to format
        language: Programming language for syntax highlighting

    Returns:
        str: Formatted code block
    """
    if language:
        return f"```{language}\n{code}\n```"
    return f"```\n{code}\n```"


def format_inline_code(code: str) -> str:
    """
    Format inline code for Telegram.

    Args:
        code: Code to format

    Returns:
        str: Formatted inline code
    """
    return f"`{code}`"


def format_agent_response(agent_name: str, response: str) -> str:
    """
    Format an agent response for display in MarkdownV2.

    Args:
        agent_name: Name of the agent
        response: Agent's response (should be pre-formatted with format_telegram_message)

    Returns:
        str: Formatted response (MarkdownV2 compatible)
    """
    return f"🤖 **{agent_name.title()}**\n\n{response}"


def format_error_message(error_type: str, message: str) -> str:
    """
    Format an error message for display.

    Args:
        error_type: Type of error
        message: Error message

    Returns:
        str: Formatted error message (will be formatted by format_telegram_message)
    """
    return f"❌ **{error_type}**\n\n{message}"


def format_status_message(status: dict) -> str:
    """
    Format agent status message.

    Args:
        status: Dictionary of agent statuses

    Returns:
        str: Formatted status message (will be formatted by format_telegram_message)
    """
    lines = ["🤖 **Agent Status**:"]

    for agent_name, available in status.items():
        emoji = "✅" if available else "❌"
        lines.append(f"{emoji} {agent_name.title()}")

    return "\n".join(lines)


def format_welcome_message() -> str:
    """
    Get the welcome message for the bot.

    Returns:
        str: Welcome message (will be formatted by format_telegram_message)
    """
    return (
        "🚀 **Welcome to NeuroCrew Lab**\n\n"
        "I orchestrate multiple AI coding agents to help you with your tasks.\n\n"
        "**Available commands:**\n"
        "/help - Show help\n"
        "/reset - Reset conversation\n"
        "/status - Check agent status\n\n"
        "Just send me a message and I'll process it with AI agents!"
    )


def format_help_message() -> str:
    """
    Get the help message for the bot.

    Returns:
        str: Help message (will be formatted by format_telegram_message)
    """
    return (
        "🤖 **NeuroCrew Lab Help**\n\n"
        "**Commands:**\n"
        "/start - Welcome message\n"
        "/help - This help message\n"
        "/reset - Clear conversation history\n"
        "/status - Check agent availability\n"
        "/agents - Show current agent sequence\n"
        "/next - Switch to next agent\n"
        "/about - About NeuroCrew Lab\n\n"
        "**How it works:**\n"
        "• I cycle through different AI agents for each message\n"
        "• Each agent has unique capabilities and perspective\n"
        "• Use /agents to see your current agent sequence\n"
        "• Use /next to skip to the next available agent\n\n"
        "🎯 **Tip:** Different agents excel at different tasks!"
    )


def _markdown_to_markdownv2(text: str) -> str:
    """
    Convert standard Markdown to Telegram MarkdownV2 format.
    
    Handles:
    - Headers (#, ##, ###) → bold text
    - **bold** → *bold*
    - *italic* or _italic_ → _italic_
    - Lists (- item, * item) → preserved with escaped chars
    - ```code``` blocks → preserved
    - `inline code` → preserved

    Args:
        text: Standard Markdown text
        
    Returns:
        str: Text converted to MarkdownV2 format (before escaping)
    """
    if not text:
        return ""
    
    # Split by code blocks first to avoid processing inside them
    parts = re.split(r"(```.*?```)", text, flags=re.DOTALL)
    
    result_parts = []
    for part in parts:
        if part.startswith("```"):
            # Code block - leave as is
            result_parts.append(part)
        else:
            # Process headers: # Title → *Title* (use bold since MarkdownV2 has no headers)
            part = re.sub(r"^#+\s+(.+)$", r"*\1*", part, flags=re.MULTILINE)
            
            # Convert **bold** to *bold* (MarkdownV2 uses single asterisk)
            part = re.sub(r"\*\*(.+?)\*\*", r"*\1*", part)
            
            # Convert _text_ italic patterns (already compatible)
            # Keep *text* single asterisks as they will be handled as formatting
            
            result_parts.append(part)
    
    return "".join(result_parts)


def format_telegram_message(text: str) -> str:
    """
    Format text for Telegram MarkdownV2 with proper escaping outside code blocks.

    Handles:
    - Conversion from Markdown to MarkdownV2 format
    - Characters to escape: _ * [ ] ( ) ~ > # + - = | { } . !
    - Preserves formatting markers (*bold*, _italic_)
    - Preserves code blocks (```...```) and inline code (`...`)

    Args:
        text: Text to format (can be Markdown)

    Returns:
        str: Telegram-formatted text (MarkdownV2 compatible)
    """
    if not text:
        return ""

    # First, convert Markdown to MarkdownV2 format
    text = _markdown_to_markdownv2(text)

    # Characters requiring escape in MarkdownV2 outside of formatting
    escape_chars = r"_*[]()~>#+-=|{}.!"

    # Split by code blocks (triple backticks)
    # Use non-greedy match for content inside code blocks
    # Flags=re.DOTALL ensures . matches newlines
    parts = re.split(r"(```.*?```)", text, flags=re.DOTALL)

    final_parts = []
    for part in parts:
        if part.startswith("```"):
            # It's a code block - return as is
            final_parts.append(part)
        else:
            # Process text outside code blocks
            # Now split by inline code (single backticks)
            inline_parts = re.split(r"(`[^`\n]+`)", part)

            for inline_part in inline_parts:
                if inline_part.startswith("`"):
                    # Inline code - return as is
                    final_parts.append(inline_part)
                else:
                    # Regular text - escape special chars, but preserve formatting
                    # Preserve *text* (bold) and _text_ (italic) by temporarily replacing them
                    # Use placeholders with digits only (won't be escaped)
                    preserved = {}
                    marker_count = 0
                    
                    # Preserve *bold* markers
                    def preserve_bold(m):
                        nonlocal marker_count
                        key = f"BOLD{marker_count:04d}"
                        preserved[key] = m.group(0)
                        marker_count += 1
                        return key
                    
                    inline_part = re.sub(r"\*[^\*\n]+\*", preserve_bold, inline_part)
                    
                    # Preserve _italic_ markers
                    def preserve_italic(m):
                        nonlocal marker_count
                        key = f"ITALIC{marker_count:04d}"
                        preserved[key] = m.group(0)
                        marker_count += 1
                        return key
                    
                    inline_part = re.sub(r"_[^_\n]+_", preserve_italic, inline_part)
                    
                    # Now escape special chars
                    escaped = re.sub(
                        f"([{re.escape(escape_chars)}])", r"\\\1", inline_part
                    )
                    
                    # Restore formatting markers
                    for key, value in preserved.items():
                        escaped = escaped.replace(key, value)
                    
                    final_parts.append(escaped)

    return "".join(final_parts)


def truncate_message(text: str, max_length: int = 100) -> str:
    """
    Truncate a message to a maximum length.

    Args:
        text: Message to truncate
        max_length: Maximum length

    Returns:
        str: Truncated message
    """
    if len(text) <= max_length:
        return text

    return text[: max_length - 3] + "..."


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename for safe file system usage.

    Args:
        filename: Filename to sanitize

    Returns:
        str: Sanitized filename
    """
    # Replace invalid characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, "_")

    # Remove leading/trailing spaces and dots
    filename = filename.strip(" .")

    # Ensure it's not empty
    if not filename:
        filename = "unnamed"

    return filename
