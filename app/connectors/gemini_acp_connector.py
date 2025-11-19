"""
Gemini ACP connector implementing the experimental ACP JSON-RPC protocol.

This connector talks directly to the `gemini --experimental-acp` CLI and follows
the same handshake sequence as other ACP-compatible CLIs:

    initialize → session/new → session/prompt

Responses are streamed via `session/update` notifications. We accumulate the
`agent_message_chunk` text blocks into a single string that is returned to the
caller once the request completes.
"""

from __future__ import annotations

import asyncio
import json
import os
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.config import Config
from .base import BaseConnector

JsonDict = Dict[str, Any]


@dataclass
class _SessionInfo:
    pid: int
    session_id: str


class GeminiACPConnector(BaseConnector):
    """Connector that implements the Gemini ACP experimental protocol."""

    DEFAULT_COMMAND = "gemini --experimental-acp"
    AUTH_METHOD_GEMINI = "gemini-api-key"
    STREAM_READER_LIMIT = 2 * 1024 * 1024

    def __init__(self):
        super().__init__()
        self.message_id: int = 0
        self.session_id: Optional[str] = None
        self.initialized: bool = False
        self.authenticated: bool = False
        self.agent_capabilities: JsonDict = {}
        self.available_auth_methods: List[str] = []
        self._conversation_history: List[str] = []
        self.current_session: Optional[_SessionInfo] = None
        # Respect global timeout but never allow less than 5 seconds
        self.request_timeout: float = max(
            5.0, float(getattr(Config, "AGENT_TIMEOUT", 120))
        )

    async def launch(self, command: str, system_prompt: str):
        """Launch Gemini CLI and initialize ACP session."""
        if self.is_alive():
            await self.shutdown()

        args = self._prepare_command_args(command or self.DEFAULT_COMMAND)
        env = self._get_clean_env()
        self.logger.info("Starting Gemini ACP process: %s", " ".join(args))

        self.process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            limit=self.STREAM_READER_LIMIT,
        )

        # Verify process started successfully
        await asyncio.sleep(0.1)  # Small delay to let process start
        if not self.is_alive():
            raise RuntimeError(f"Gemini ACP process failed to start: {args}")

        self.message_id = 0
        self.session_id = None
        self.initialized = False
        self.authenticated = False
        self.agent_capabilities = {}
        self.available_auth_methods = []
        self._conversation_history = []

        try:
            await self._initialize()
            await self._create_session()

            if system_prompt.strip():
                await self._send_prompt(system_prompt)
        except Exception as e:
            self.logger.error(f"Failed to initialize Gemini ACP session: {e}")
            await self.shutdown()
            raise

    async def execute(self, delta_prompt: str) -> str:
        if not self.is_alive() or not self.session_id:
            raise RuntimeError(
                "Gemini ACP session is not active. Launch the connector first."
            )

        response_text = await self._send_prompt(delta_prompt)
        if response_text:
            self._conversation_history.append(response_text)
        return response_text

    async def follow_up(self, delta_prompt: str) -> str:
        return await self.execute(delta_prompt)

    async def shutdown(self):
        if self.is_alive() and self.session_id:
            try:
                await self._send_notification(
                    "session/cancel", {"sessionId": self.session_id}
                )
            except Exception:
                pass
        await super().shutdown()
        self.session_id = None
        self.initialized = False
        self.authenticated = False
        self.current_session = None

    def get_session_history(self) -> List[str]:
        return list(self._conversation_history)

    def get_info(self) -> Dict[str, Any]:
        return {
            "name": "Gemini ACP Connector (experimental)",
            "type": "gemini_acp",
            "status": "active" if self.is_alive() else "inactive",
            "session_id": self.session_id,
        }

    def check_availability(self) -> bool:
        import subprocess

        try:
            result = subprocess.run(
                ["gemini", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except Exception:
            return False

    async def _initialize(self):
        response, _ = await self._send_request(
            "initialize",
            {
                "protocolVersion": 1,
                "clientCapabilities": {
                    "fs": {"readTextFile": False, "writeTextFile": False},
                },
            },
        )
        self.initialized = True
        self.agent_capabilities = response.get("agentCapabilities", {})
        self.available_auth_methods = [
            str(method.get("id"))
            for method in response.get("authMethods", [])
            if isinstance(method, dict) and method.get("id")
        ]

    async def _create_session(self):
        result, _ = await self._send_request(
            "session/new",
            {
                "cwd": str(Path.cwd()),
                "mcpServers": [],
            },
        )
        session_id = result.get("sessionId")
        if not session_id:
            raise RuntimeError("Gemini ACP did not return a sessionId.")
        self.session_id = session_id
        if self.process:
            self.current_session = _SessionInfo(
                pid=self.process.pid, session_id=session_id
            )

    async def _send_prompt(self, prompt: str) -> str:
        result, aggregated_text = await self._send_request(
            "session/prompt",
            {
                "sessionId": self.session_id,
                "prompt": [
                    {
                        "type": "text",
                        "text": prompt,
                    }
                ],
            },
            collect_output=True,
        )

        stop_reason = result.get("stopReason")
        if stop_reason:
            self.logger.debug("Prompt completed (stopReason=%s)", stop_reason)

        return aggregated_text

    async def _send_request(
        self,
        method: str,
        params: JsonDict,
        collect_output: bool = False,
    ) -> Tuple[JsonDict, str]:
        if not self.process or not self.process.stdin or not self.process.stdout:
            raise RuntimeError("Gemini ACP process is not available.")

        request_id = self._next_message_id()
        message = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }

        await self._write_message(message)
        self.logger.debug("Sent request %s (%s)", request_id, method)

        collected_chunks: Optional[List[str]] = [] if collect_output else None
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.request_timeout

        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                self.logger.error(
                    "Timed out waiting for response (%s, id=%s)", method, request_id
                )
                raise RuntimeError(f"Gemini ACP timeout while waiting for {method}")
            try:
                message = await asyncio.wait_for(
                    self._read_message(), timeout=remaining
                )
                deadline = loop.time() + self.request_timeout
            except asyncio.TimeoutError:
                self.logger.error(
                    "Timed out waiting for response (%s, id=%s) after %.1fs",
                    method,
                    request_id,
                    self.request_timeout,
                )
                raise RuntimeError(
                    f"Gemini ACP timeout while waiting for {method}"
                ) from None
            except (BrokenPipeError, ConnectionResetError) as e:
                self.logger.error("Connection broken during ACP communication: %s", e)
                raise RuntimeError(f"Gemini ACP connection error: {e}") from e

            if message is None:
                raise RuntimeError("Gemini ACP process terminated unexpectedly.")

            if (
                "method" in message
                and "id" in message
                and message.get("id") != request_id
            ):
                await self._handle_agent_request(message)
                continue

            if message.get("id") == request_id:
                if "error" in message:
                    error = message["error"]
                    error_message = (
                        error.get("message", "Unknown error")
                        if isinstance(error, dict)
                        else str(error)
                    )
                    # Extract detailed error info if available
                    if isinstance(error, dict) and "data" in error:
                        data = error["data"]
                        if isinstance(data, dict) and "details" in data:
                            error_message += f" Details: {data['details']}"
                        else:
                            error_message += f" Data: {data}"

                    self.logger.error(
                        "Gemini ACP returned error for %s (id=%s): %s",
                        method,
                        request_id,
                        error,
                    )
                    raise RuntimeError(f"Gemini ACP error ({method}): {error_message}")

                result = message.get("result", {})
                aggregated_text = "".join(collected_chunks or [])
                return result, aggregated_text

            if "method" in message and "id" not in message:
                self._handle_notification(message, collected_chunks)

    async def _handle_agent_request(self, message: JsonDict):
        method = message.get("method")
        request_id = message.get("id")
        params = message.get("params", {})

        if request_id is None:
            return

        if method == "session/request_permission":
            result = self._auto_grant_permission(params)
        else:
            result = {
                "error": {
                    "code": -32601,
                    "message": f"Method {method} not supported by client.",
                }
            }

        if "error" in result:
            payload = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": result["error"],
            }
        else:
            payload = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": result,
            }

        await self._write_raw(json.dumps(payload) + "\n")

    def _auto_grant_permission(self, params: JsonDict) -> JsonDict:
        options = params.get("options", [])
        if not options:
            return {"outcome": {"outcome": "cancelled"}}

        selected = options[0]
        option_id = selected.get("optionId")
        if not option_id:
            return {"outcome": {"outcome": "cancelled"}}

        return {"outcome": {"outcome": "selected", "optionId": option_id}}

    def _handle_notification(
        self, message: JsonDict, collected_chunks: Optional[List[str]]
    ):
        method = message.get("method")
        params = message.get("params", {})

        if method == "session/update":
            update = params.get("update", {})
            update_type = update.get("sessionUpdate")
            content = update.get("content")

            if update_type == "agent_message_chunk":
                if collected_chunks is not None:
                    text = self._extract_text(content)
                    if text:
                        collected_chunks.append(text)
            elif update_type == "agent_thought_chunk":
                text = self._extract_text(content)
                if text:
                    self.logger.debug("Agent thought: %s", text)

    async def _send_notification(self, method: str, params: JsonDict):
        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        await self._write_message(message, expect_response=False)

    async def _write_message(self, message: JsonDict, expect_response: bool = True):
        if not self.process or not self.process.stdin:
            raise RuntimeError("Qwen ACP process stdin is not available.")
        await self._write_raw(json.dumps(message) + "\n")
        if expect_response:
            self.logger.debug("Message written: %s", message.get("method"))

    async def _write_raw(self, payload: str):
        assert self.process and self.process.stdin
        self.process.stdin.write(payload.encode("utf-8"))
        await self.process.stdin.drain()

    async def _read_message(self) -> Optional[JsonDict]:
        if not self.process or not self.process.stdout:
            raise RuntimeError("Gemini ACP process stdout is not available.")

        # Add read timeout to prevent hanging
        try:
            raw = await asyncio.wait_for(self.process.stdout.readline(), timeout=10.0)
        except asyncio.TimeoutError:
            self.logger.error("Timeout reading from Gemini ACP process stdout")
            raise RuntimeError("Gemini ACP process read timeout")

        if not raw:
            return None

        text = raw.decode("utf-8").strip()
        if not text:
            # Skip empty lines but don't recurse infinitely
            return await self._read_message()

        try:
            message = json.loads(text)
            self.logger.debug(
                "Received message: %s",
                message.get("method") or message.get("id"),
            )
            return message
        except json.JSONDecodeError as e:
            self.logger.warning(
                "Failed to decode JSON line from Gemini: %s (error: %s)", text, str(e)
            )
            # Continue reading instead of failing completely
            return await self._read_message()

    def _prepare_command_args(self, command: str) -> List[str]:
        args = shlex.split(command)
        if not args:
            args = shlex.split(self.DEFAULT_COMMAND)

        if "--experimental-acp" not in args:
            args.append("--experimental-acp")
        return args

    def _next_message_id(self) -> int:
        self.message_id += 1
        return self.message_id

    @staticmethod
    def _extract_text(content: Any) -> str:
        if isinstance(content, dict):
            return content.get("text") or ""
        if isinstance(content, list):
            fragments = [
                str(chunk.get("text"))
                for chunk in content
                if isinstance(chunk, dict) and chunk.get("text")
            ]
            return "".join(fragments)
        return ""

    def _get_clean_env(self) -> Dict[str, str]:
        """
        Get environment for the process.

        Simply inherit the full environment including proxy settings.
        """
        return os.environ.copy()
