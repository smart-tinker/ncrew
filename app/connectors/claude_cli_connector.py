"""Connector for Claude Code CLI in headless stream-json mode."""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import uuid
from typing import List

from app.connectors.base import BaseConnector


class ClaudeCLICodeConnector(BaseConnector):
    """Executes Claude Code CLI with `--print` stream-json output."""

    DEFAULT_COMMAND = (
        "claude -p --output-format stream-json --permission-mode bypassPermissions "
        "--dangerously-skip-permissions --verbose"
    )

    def __init__(self):
        super().__init__()
        self.base_command: str = self.DEFAULT_COMMAND
        self.session_id: str | None = None
        self.system_prompt: str = ""
        self._initialized: bool = False

    def is_alive(self) -> bool:  # type: ignore[override]
        return self._initialized

    async def launch(self, command: str, system_prompt: str):
        self.base_command = command or self.DEFAULT_COMMAND
        self.system_prompt = system_prompt.strip()
        self.session_id = str(uuid.uuid4())
        self._initialized = True
        await self._prime_session()

    async def execute(self, delta_prompt: str) -> str:
        if not self._initialized:
            raise RuntimeError("Claude connector not initialized")

        prompt = delta_prompt.strip()
        if not prompt:
            return ""

        response = await self._run_claude(prompt)
        return response.strip()

    async def follow_up(self, delta_prompt: str) -> str:
        return await self.execute(delta_prompt)

    async def shutdown(self):
        self.session_id = None
        self._initialized = False

    def check_availability(self) -> bool:  # type: ignore[override]
        import shutil

        executable = shlex.split(self.base_command)[0]
        return shutil.which(executable) is not None

    async def _prime_session(self):
        if not self.system_prompt:
            return
        primer = (
            f"{self.system_prompt}\n\nConfirm readiness with the single word READY."
        )
        try:
            await self._run_claude(primer)
        except Exception:
            pass

    async def _run_claude(self, prompt: str) -> str:
        args: List[str] = shlex.split(self.base_command)
        if "--session-id" not in args and self.session_id:
            args += ["--session-id", self.session_id]
        elif self.session_id:
            # Replace existing session id to ensure we control the session
            try:
                index = args.index("--session-id")
                args[index + 1] = self.session_id
            except (ValueError, IndexError):
                args += ["--session-id", self.session_id]

        args.append(prompt)

        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=os.getcwd(),
            env=os.environ.copy(),
            limit=2 * 1024 * 1024,  # 2MB limit for large JSON responses
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            error = (
                stderr.decode().strip() or stdout.decode().strip() or "unknown error"
            )
            raise RuntimeError(f"Claude CLI failed: {error}")

        responses: List[str] = []
        for raw_line in stdout.decode().splitlines():
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                event = json.loads(raw_line)
            except json.JSONDecodeError:
                continue

            event_type = event.get("type")
            if event_type == "system" and not self.session_id:
                session_id = event.get("session_id")
                if isinstance(session_id, str):
                    self.session_id = session_id
            elif event_type == "assistant":
                message = event.get("message", {})
                content = message.get("content", [])
                text_parts = [
                    chunk.get("text", "")
                    for chunk in content
                    if chunk.get("type") == "text"
                ]
                text = "\n".join(filter(None, text_parts)).strip()
                if text:
                    responses.append(text)
            elif event_type == "result" and event.get("is_error"):
                result_text = event.get("result") or "Claude CLI reported an error"
                raise RuntimeError(str(result_text))

        return "\n\n".join(responses)
