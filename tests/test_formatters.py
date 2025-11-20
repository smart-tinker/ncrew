"""
Tests for message formatting utilities.
"""

import pytest
from app.utils.formatters import (
    format_telegram_message,
    split_long_message,
    format_code_block,
    format_inline_code,
    format_agent_response,
    format_error_message,
    format_status_message,
    format_welcome_message,
    format_help_message,
    truncate_message,
    sanitize_filename,
)


class TestFormatTelegramMessage:
    """Test Telegram message formatting for MarkdownV2 compatibility."""

    def test_empty_string(self):
        """Test formatting empty string."""
        assert format_telegram_message("") == ""

    def test_plain_text_no_special_chars(self):
        """Test plain text without special characters."""
        text = "Hello world"
        assert format_telegram_message(text) == text

    def test_escape_special_characters(self):
        """Test escaping of MarkdownV2 special characters."""
        text = "_*[]()~>#+-=|{}.!"
        expected = r"\_*\[\]\(\)\~\>\#\+\-\=\|\{\}\.\!"
        assert format_telegram_message(text) == expected

    def test_preserve_inline_code(self):
        """Test that inline code is preserved without escaping."""
        text = 'Use `print("hello")` for output'
        assert format_telegram_message(text) == text

    def test_preserve_code_block(self):
        """Test that code blocks are preserved without escaping."""
        text = """Here is code:
```
def func():
    pass
```
"""
        assert format_telegram_message(text) == text

    def test_markdown_to_markdownv2_conversion(self):
        """Test conversion from standard Markdown to MarkdownV2."""
        # Headers
        assert format_telegram_message("# Title") == "*Title*"
        assert format_telegram_message("## Subtitle") == "*Subtitle*"

        # Bold conversion
        assert format_telegram_message("**bold text**") == "*bold text*"
        assert format_telegram_message("__bold text__") == "*bold text*"  # Actually converted by _markdown_to_markdownv2

        # Mixed content
        text = """# Welcome
**Bold text** and _italic text_ with `code`"""
        result = format_telegram_message(text)
        assert "*Welcome*" in result
        assert "*Bold text*" in result
        assert "_italic text_" in result
        assert "`code`" in result

    def test_mixed_content_with_escaping(self):
        """Test mixed content with special chars, formatting, and code blocks."""
        text = """# Title with *bold* and `code`

```
if x > 0:
    print("ok")
```

Note: Use > and | carefully with [links](url)."""
        result = format_telegram_message(text)
        assert "*Title with *bold* and `code`*" in result  # Header converted, formatting preserved
        assert "```" in result  # Code block preserved
        assert r"\>" in result  # Special chars escaped
        assert r"\|" in result
        assert r"\[links\]\(url\)" in result

    def test_formatting_preservation_during_escaping(self):
        """Test that *bold* and _italic_ are preserved during special char escaping."""
        text = "*bold* _italic_ [link](url) > symbol"
        result = format_telegram_message(text)
        assert "*bold*" in result  # Bold preserved
        assert "_italic_" in result  # Italic preserved
        assert r"\[link\]\(url\)" in result  # Link escaped
        assert r"\>" in result  # > escaped

    def test_backslash_in_code(self):
        """Test backslash in code blocks and inline code."""
        text = """```python
path = "C:\\Users\\file.txt"
```

Or inline `C:\\path\\to\\file`"""
        assert format_telegram_message(text) == text

    def test_complex_markdown(self):
        """Test complex Markdown with headers, lists, code."""
        text = """# Project Status

## Features
- **Bold feature** with `code`
- _Italic feature_ using > comparison
- Link to [docs](url)

```python
def hello():
    print("world")
```"""
        result = format_telegram_message(text)
        # Headers converted
        assert "*Project Status*" in result
        assert "*Features*" in result
        # Formatting preserved
        assert "*Bold feature*" in result
        assert "_Italic feature_" in result
        assert "`code`" in result
        # Special chars escaped
        assert r"\>" in result
        assert r"\[docs\]\(url\)" in result
        # Code block preserved
        assert "```python" in result
        assert 'print("world")' in result


class TestSplitLongMessage:
    """Test message splitting functionality."""

    def test_short_message(self):
        """Test that short messages are not split."""
        text = "Short message"
        assert split_long_message(text) == ["Short message"]

    def test_long_message_split(self):
        """Test splitting of long messages."""
        text = "A" * 5000
        messages = split_long_message(text, max_length=4096, threshold=4000)
        assert len(messages) > 1
        assert all(len(msg) <= 4096 for msg in messages)

    def test_paragraph_splitting(self):
        """Test splitting by paragraphs."""
        text = "Paragraph 1\n\nParagraph 2\n\nParagraph 3"
        messages = split_long_message(text, max_length=20, threshold=15)
        assert len(messages) >= 2


class TestOtherFormatters:
    """Test other formatting functions."""

    def test_format_code_block(self):
        """Test code block formatting."""
        code = "print('hello')"
        assert format_code_block(code) == "```\nprint('hello')\n```"
        assert format_code_block(code, "python") == "```python\nprint('hello')\n```"

    def test_format_inline_code(self):
        """Test inline code formatting."""
        code = "print('hello')"
        assert format_inline_code(code) == "`print('hello')`"

    def test_format_agent_response(self):
        """Test agent response formatting."""
        response = format_agent_response("test_agent", "Hello world")
        assert "🤖 *Test_agent*" in response
        assert "Hello world" in response

    def test_format_error_message(self):
        """Test error message formatting."""
        error = format_error_message("Error", "Something went wrong")
        assert "❌ *Error*" in error
        assert "Something went wrong" in error

    def test_format_status_message(self):
        """Test status message formatting."""
        status = {"agent1": True, "agent2": False}
        message = format_status_message(status)
        assert "🤖 *Agent Status*:" in message
        assert "✅ Agent1" in message
        assert "❌ Agent2" in message

    def test_truncate_message(self):
        """Test message truncation."""
        long_text = "A" * 200
        truncated = truncate_message(long_text, 100)
        assert len(truncated) == 100
        assert truncated.endswith("...")

    def test_sanitize_filename(self):
        """Test filename sanitization."""
        filename = 'file<>:|?*name.txt'
        sanitized = sanitize_filename(filename)
        assert sanitized == "file______name.txt"</content>
<parameter name="filePath">tests/test_formatters.py
