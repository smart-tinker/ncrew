import json
import sys
from pathlib import Path

import pytest

from connectors.claude_cli_connector import ClaudeCLICodeConnector

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
            {"type": "text", "text": f"Claude: {args.prompt}"}
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
    await connector.launch(f"python {script_path}", "System prime")

    response = await connector.execute("Ping")
    assert "Claude: Ping" in response

    await connector.shutdown()
