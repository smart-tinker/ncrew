"""
Tests for Telegram message formatting.
"""

import pytest
from app.utils.formatters import format_telegram_message


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
        expected = r"\_\*\[\]\(\)\~\>\#\+\-\=\|\{\}\.\!"
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

    def test_mixed_content(self):
        """Test mixed content with special chars, inline code, and code blocks."""
        text = """# Title with *bold* and `code`

```
if x > 0:
    print("ok")
```

Note: Use > and | carefully."""
        # Header becomes *bold*, single * are preserved as formatting, then special chars escaped
        expected = r"""*Title with *bold\* and `code`\*

```
if x > 0:
    print("ok")
```

Note: Use \> and \| carefully\."""
        assert format_telegram_message(text) == expected

    def test_backslash_in_code(self):
        """Test backslash in code blocks and inline code."""
        text = """```python
path = "C:\\Users\\file.txt"
```

Or inline `C:\\path\\to\\file`"""
        assert format_telegram_message(text) == text
