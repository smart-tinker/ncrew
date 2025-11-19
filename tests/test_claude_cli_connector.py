import json
import sys
from pathlib import Path

import pytest

from app.connectors.claude_cli_connector import ClaudeCLICodeConnector

MOCK_SCRIPT = """
import argparse
import json
import sys

parser = argparse.ArgumentParser()
parser.add_argument("prompt")
parser.add_argument("--session-id", dest="session_id")
args = parser.parse_args()

session_id = args.session_id or "mock-session"

print(json.dumps({"type": "system", "session_id": session_id}))
print(json.dumps({
    "type": "assistant",
    "message": {
        "content": [
            {"type": "text", "text": f"Claude [{session_id}]: {args.prompt}"}
        ]
    }
}))
print(json.dumps({"type": "result", "is_error": False}))
"""


@pytest.mark.asyncio
async def test_claude_cli_connector(tmp_path: Path):
    script_path = tmp_path / "mock_claude.py"
    script_path.write_text(MOCK_SCRIPT)

    connector = ClaudeCLICodeConnector()
    # Launch usually generates a random session ID internally if one isn't provided by output
    # But our mock outputs one.
    await connector.launch(f"python {script_path}", "System prime")

    response1 = await connector.execute("Ping")
    assert "Claude [" in response1
    assert "]: Ping" in response1

    # Extract session ID
    import re

    match = re.search(r"Claude \[(.*?)\]", response1)
    assert match
    session_id = match.group(1)

    # Second call should use same session ID
    response2 = await connector.execute("Pong")
    assert f"Claude [{session_id}]: Pong" == response2

    await connector.shutdown()
