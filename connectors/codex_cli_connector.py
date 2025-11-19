"""Connector for Codex CLI non-interactive mode."""

from __future__ import annotations

import asyncio
import json
import os
import shlex
from typing import List

from connectors.base import BaseConnector


class CodexCLIConnector(BaseConnector):
    """Runs Codex CLI via `codex exec --json` and streams replies."""

    DEFAULT_COMMAND = (
        "codex exec --json --full-auto --sandbox workspace-write --skip-git-repo-check"
    )

    def __init__(self):
        super().__init__()
        self.base_command: str = self.DEFAULT_COMMAND
        self.system_prompt: str = ""
        self.thread_id: str | None = None
        self._initialized: bool = False

    def is_alive(self) -> bool:  # type: ignore[override]
        return self._initialized

    async def launch(self, command: str, system_prompt: str):
        self.base_command = command or self.DEFAULT_COMMAND
        self.system_prompt = system_prompt.strip()
        self.thread_id = None
        self._initialized = True
        await self._prime_session()

    async def execute(self, delta_prompt: str) -> str:
        if not self._initialized:
            raise RuntimeError("Codex connector not initialized")

        prompt = delta_prompt.strip()
        if not prompt:
            return ""

        if not self.thread_id:
            # Ensure Codex session exists before first real prompt
            await self._prime_session()

        response = await self._run_codex(prompt, resume=bool(self.thread_id))
        return response.strip()

    async def follow_up(self, delta_prompt: str) -> str:
        return await self.execute(delta_prompt)

    async def shutdown(self):
        self.thread_id = None
        self._initialized = False

    def check_availability(self) -> bool:  # type: ignore[override]
        import shutil

        executable = shlex.split(self.base_command)[0]
        return shutil.which(executable) is not None

    async def _prime_session(self):
        if not self.system_prompt:
            return

        primer = (
            f"{self.system_prompt}\n\n"
            "You are being initialized by an orchestrator. Respond with READY."
        )
        try:
            await self._run_codex(primer, resume=False)
        except Exception:
            # We only care about establishing the thread id; if this fails the
            # next execute call will raise again.
            pass

    async def _run_codex(self, prompt: str, resume: bool) -> str:
        args: List[str] = shlex.split(self.base_command)
        if resume and self.thread_id:
            args += ["resume", self.thread_id, prompt]
        else:
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
            error_msg = (
                stderr.decode().strip() or stdout.decode().strip() or "unknown error"
            )
            # Try to parse JSON error if possible
            try:
                for line in error_msg.splitlines():
                    if line.strip().startswith("{"):
                        err_json = json.loads(line)
                        if err_json.get("type") == "error":
                            error_msg = err_json.get("error", error_msg)
            except:
                pass

            raise RuntimeError(f"Codex CLI failed: {error_msg}")

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
            if event_type == "thread.started":
                thread_id = event.get("thread_id")
                if thread_id:
                    self.thread_id = thread_id
            elif event_type == "item.completed":
                item = event.get("item", {})
                if item.get("type") == "agent_message":
                    text = item.get("text", "").strip()
                    if text:
                        responses.append(text)

        return "\n\n".join(responses)
