import json
import sys
from pathlib import Path

import pytest

from app.connectors.codex_cli_connector import CodexCLIConnector

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
        prefix = "Resume"
    else:
        thread_id = str(uuid.uuid4())
        prompt = args[0]
        prefix = "Init"

    events = [
        {"type": "thread.started", "thread_id": thread_id},
        {"type": "turn.started"},
        {"type": "item.completed", "item": {"id": "item_0", "type": "agent_message", "text": f"Echo [{prefix} {thread_id}]: {prompt}"}},
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

    # Since we provided a system prompt, the session was primed (Init) during launch.
    # So the first user message is already a Resume.
    assert "Echo [Resume " in first
    assert "]: Hello" in first

    # Extract thread_id from first response to verify persistence
    import re

    match = re.search(r"Echo \[Resume (.*?)\]", first)
    assert match
    thread_id = match.group(1)

    second = await connector.execute("World")
    # Should be Resume with SAME UUID
    assert f"Echo [Resume {thread_id}]: World" == second

    await connector.shutdown()
