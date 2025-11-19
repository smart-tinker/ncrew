import json
import sys
from pathlib import Path

import pytest

from connectors.codex_cli_connector import CodexCLIConnector

MOCK_SCRIPT = """
import json
import sys
import uuid

def main():
    args = sys.argv[1:]
    if not args:
        print(json.dumps({"type": "thread.started", "thread_id": str(uuid.uuid4())}))
        return

    if args[0] == "resume":
        thread_id = args[1]
        prompt = args[2]
    else:
        thread_id = str(uuid.uuid4())
        prompt = args[0]

    events = [
        {"type": "thread.started", "thread_id": thread_id},
        {"type": "turn.started"},
        {"type": "item.completed", "item": {"id": "item_0", "type": "agent_message", "text": f"Echo: {prompt}"}},
        {"type": "turn.completed"},
    ]
    for event in events:
        print(json.dumps(event))


if __name__ == "__main__":
    main()
"""


@pytest.mark.asyncio
async def test_codex_cli_connector(tmp_path: Path):
    script_path = tmp_path / "mock_codex.py"
    script_path.write_text(MOCK_SCRIPT)

    connector = CodexCLIConnector()
    await connector.launch(f"python {script_path}", "System init")

    first = await connector.execute("Hello")
    assert first == "Echo: Hello"

    second = await connector.execute("World")
    assert second == "Echo: World"

    await connector.shutdown()
