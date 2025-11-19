# tests/test_opencode_acp.py
import asyncio
import json
import sys
from pathlib import Path

import pytest
import pytest_asyncio

from app.connectors.opencode_acp_connector import OpenCodeACPConnector


MOCK_SERVER_SOURCE = """
import asyncio
import json
import sys


async def read_line(reader: asyncio.StreamReader):
    raw = await reader.readline()
    if not raw:
        return None
    return json.loads(raw.decode())


async def write_line(writer: asyncio.StreamWriter, message):
    writer.write((json.dumps(message) + "\\n").encode())
    await writer.drain()


async def main():
    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)
    transport, protocol_w = await loop.connect_write_pipe(asyncio.streams.FlowControlMixin, sys.stdout)
    writer = asyncio.StreamWriter(transport, protocol_w, None, loop)

    session_id = "mock-session-id"

    while True:
        message = await read_line(reader)
        if message is None:
            break

        method = message.get("method")
        msg_id = message.get("id")

        if method == "initialize":
            await write_line(
                writer,
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "protocolVersion": 1,
                        "authMethods": [],
                        "agentCapabilities": {"loadSession": False, "promptCapabilities": {}},
                    },
                },
            )
        elif method == "session/new":
            await write_line(
                writer,
                {"jsonrpc": "2.0", "id": msg_id, "result": {"sessionId": session_id}},
            )
        elif method == "session/prompt":
            prompt_blocks = message["params"]["prompt"]
            text = " ".join(block.get("text", "") for block in prompt_blocks if isinstance(block, dict))
            await write_line(
                writer,
                {
                    "jsonrpc": "2.0",
                    "method": "session/update",
                    "params": {
                        "sessionId": session_id,
                        "update": {
                            "sessionUpdate": "agent_message_chunk",
                            "content": {"type": "text", "text": f"Mock response to: {text}"},
                        },
                    },
                },
            )
            await write_line(
                writer,
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {"stopReason": "end_turn"},
                },
            )
        elif method == "session/cancel":
            await write_line(
                writer,
                {"jsonrpc": "2.0", "id": msg_id, "result": {}},
            )
        else:
            await write_line(
                writer,
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32601, "message": f"Unknown method: {method}"},
                },
            )


if __name__ == "__main__":
    asyncio.run(main())
"""


@pytest_asyncio.fixture
async def mock_opencode_command(tmp_path: Path):
    """Create a temporary mock OpenCode ACP server and return the command string."""
    script_path = tmp_path / "mock_opencode_acp.py"
    script_path.write_text(MOCK_SERVER_SOURCE)
    command = f"{sys.executable} -u {script_path}"
    yield command


@pytest.mark.asyncio
async def test_opencode_acp_connector_integration(mock_opencode_command):
    connector = OpenCodeACPConnector()

    await connector.launch(mock_opencode_command, "System prompt for tests.")
    assert connector.is_alive()
    assert connector.session_id == "mock-session-id"

    user_prompt = "Write hello world."
    response = await connector.execute(user_prompt)
    assert response == f"Mock response to: {user_prompt}"

    follow_up_prompt = "And add tests."
    follow_up = await connector.follow_up(follow_up_prompt)
    assert follow_up == f"Mock response to: {follow_up_prompt}"

    history = connector.get_session_history()
    assert history == [response, follow_up]

    await connector.shutdown()
    assert not connector.is_alive()
