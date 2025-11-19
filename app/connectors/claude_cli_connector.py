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
        self._session_created: bool = False

    def is_alive(self) -> bool:  # type: ignore[override]
        return self._initialized

    async def launch(self, command: str, system_prompt: str):
        self.base_command = command or self.DEFAULT_COMMAND
        self.system_prompt = system_prompt.strip()
        self.session_id = str(uuid.uuid4())
        self._initialized = True
        self._session_created = False
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
        self._session_created = False

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

        # Session management logic:
        # 1. First call uses --session-id to create the session
        # 2. Subsequent calls use --resume to continue the session
        # 3. If session creation failed previously, fallback to --session-id
        if self.session_id:
            # Remove any existing session args from base command
            if "--session-id" in args:
                try:
                    idx = args.index("--session-id")
                    args.pop(idx)  # remove flag
                    if idx < len(args) and not args[idx].startswith("-"):
                        args.pop(idx)  # remove value
                except IndexError:
                    pass
            if "--resume" in args:
                try:
                    idx = args.index("--resume")
                    args.pop(idx)
                    if idx < len(args) and not args[idx].startswith("-"):
                        args.pop(idx)
                except IndexError:
                    pass

            # Add correct flag
            if self._session_created:
                args += ["--resume", self.session_id]
            else:
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

            # Handle specific case where session might be locked but we want to force usage
            # OR if --resume fails because session was lost/cleaned up
            # If --resume failed, we might want to reset _session_created and try again with --session-id?
            # But for now, let's just report the error to be safe.
            raise RuntimeError(f"Claude CLI failed: {error}")

        # Mark session as successfully created if we got a 0 return code
        if not self._session_created:
            self._session_created = True

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
