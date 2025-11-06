# Qwen ACP Connector Guide

## Overview

NeuroCrew uses the official **Qwen Code 0.1.4** CLI in experimental ACP mode to power every role. The `QwenACPConnector` speaks the same JSON-RPC protocol as the CLI itself:

```
initialize → session/new → session/prompt
```

Responses stream back as `session/update` notifications. The connector aggregates the text chunks and returns fully assembled messages to the orchestration layer.

## Prerequisites

1. Install the CLI:
   ```bash
   npm install -g @qwen-code/qwen-code@0.1.4
   ```
2. Authenticate once (outside the app):
   ```bash
   qwen          # run interactively and complete OAuth flow
   ```
3. Confirm the binary is available:
   ```bash
   qwen --version  # should print 0.1.4
   ```

## Role Configuration

Every role is configured to use the unified connector. Example entry in `roles/agents.yaml`:

```yaml
- role_name: software_developer
  display_name: "Software Developer"
  telegram_bot_name: SoftwareDevBot
  system_prompt_file: "roles/prompts/software_developer.md"
  agent_type: "qwen_acp"
  cli_command: "qwen --experimental-acp"
  description: "Старший разработчик на базе ACP протокола qwen-code 0.1.4"
```

The same pair (`agent_type`, `cli_command`) is used for every agent so the orchestration layer always instantiates `QwenACPConnector`.

## Lifecycle

1. **Launch** – spawns `qwen --experimental-acp`, strips proxy variables, and performs the initialization handshake.
2. **Session creation** – calls `session/new` once and keeps the returned `sessionId`.
3. **Prompt execution** – sends `session/prompt` requests, collects streamed chunks, logs internal thoughts at DEBUG level, and returns the final text.
4. **Shutdown** – issues `session/cancel` and terminates the CLI when NeuroCrew rotates or stops roles.

## Direct Usage

```python
import asyncio

from connectors.qwen_acp_connector import QwenACPConnector


async def main():
    connector = QwenACPConnector()
    await connector.launch("qwen --experimental-acp", "You are a helpful coding assistant.")
    response = await connector.execute("Write a Python function to add two numbers.")
    print(response)
    await connector.shutdown()


asyncio.run(main())
```

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `Method not found` | Verify you are running Qwen CLI 0.1.4+ and the command includes `--experimental-acp`. |
| Authentication prompt | Run `qwen` interactively once and complete OAuth. |
| Empty responses | Check DEBUG logs (`QwenACPConnector`) – the CLI may be returning only thought chunks. |
| CLI not found | Ensure `qwen` is on the `PATH` for the user running the bot. |

## Test Coverage

`pytest tests/test_qwen_acp.py -q`

The mock server emulates the real CLI handshake and streaming behaviour, ensuring regressions around the ACP protocol are caught early.

## Operational Tips

- Enable DEBUG logging (`LOG_LEVEL=DEBUG`) when investigating protocol issues.
- Responses stream as chunks; you will see `agent_thought_chunk` lines in logs—those are suppressed from Telegram output.
- If the CLI is updated, re-run `npm install -g @qwen-code/qwen-code@latest` and verify `code --experimental-acp` still exposes the same methods.
