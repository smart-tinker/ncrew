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
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config import Config
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
        self.request_timeout: float = max(30.0, float(getattr(Config, "AGENT_TIMEOUT", 120)))
        # Deadlock detection configuration
        self.max_consecutive_timeouts: int = int(getattr(Config, "GEMINI_MAX_TIMEOUTS", 5))

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
        )

        self.message_id = 0
        self.session_id = None
        self.initialized = False
        self.authenticated = False
        self.agent_capabilities = {}
        self.available_auth_methods = []
        self._conversation_history = []

        await self._initialize()
        await self._create_session()

        if system_prompt.strip():
            await self._send_prompt(system_prompt)

    async def execute(self, delta_prompt: str) -> str:
        if not self.is_alive() or not self.session_id:
            raise RuntimeError("Gemini ACP session is not active. Launch the connector first.")

        response_text = await self._send_prompt(delta_prompt)
        if response_text:
            self._conversation_history.append(response_text)
        return response_text

    async def follow_up(self, delta_prompt: str) -> str:
        return await self.execute(delta_prompt)

    async def shutdown(self):
        if self.is_alive() and self.session_id:
            try:
                await self._send_notification("session/cancel", {"sessionId": self.session_id})
                # Give process time to handle the notification
                await asyncio.sleep(0.1)
            except Exception as e:
                self.logger.debug("Error sending session cancel notification: %s", str(e))

        # Terminate process properly with reduced timeout
        if self.process:
            try:
                self.process.terminate()
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=1.0)  # Reduced from 3.0
                except asyncio.TimeoutError:
                    self.logger.debug("Process did not terminate gracefully, force killing...")  # Reduced verbosity
                    self.process.kill()
                    await asyncio.wait_for(self.process.wait(), timeout=1.0)  # Reduced from 2.0
            except (ProcessLookupError, RuntimeError) as e:
                # Process might have already terminated or event loop closed
                self.logger.debug("Process already terminated or event loop closed: %s", str(e))  # Reduced verbosity
            except Exception as e:
                self.logger.debug("Error shutting down process: %s", str(e))  # Reduced verbosity

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
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "NeuroCrew Lab Gemini Connector",
                    "version": "1.0.0"
                }
            },
            collect_output=False,
        )

        self.logger.debug(f"Initialize response: {response}")

        if "capabilities" in response:
            self.agent_capabilities = response["capabilities"]
        if "availableAuthMethods" in response:
            self.available_auth_methods = response["availableAuthMethods"]

        self.logger.info(f"Available auth methods: {self.available_auth_methods}")
        self.logger.info(f"Capabilities: {self.agent_capabilities}")

        self.initialized = True
        self.logger.info("Gemini ACP initialized successfully")

    async def _create_session(self):
        response, _ = await self._send_request(
            "session/new",
            {
                "sessionId": None,
                "mode": "interactive",
                "cwd": os.getcwd(),
                "mcpServers": []
            },
            collect_output=False,
        )

        if "result" in response and "sessionId" in response["result"]:
            self.session_id = response["result"]["sessionId"]
            if self.process and self.session_id:
                self.current_session = _SessionInfo(
                    pid=self.process.pid,
                    session_id=self.session_id
                )
            self.logger.info(f"Gemini ACP session created: {self.session_id}")
        else:
            self.logger.error(f"Session creation failed. Response: {response}")
            raise RuntimeError(f"Failed to create Gemini ACP session. Response: {response}")

    async def _send_prompt(self, prompt: str) -> str:
        self.logger.debug(f"Sending prompt: {prompt[:100]}...")
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

        self.logger.debug(f"Prompt result: {result}")
        self.logger.debug(f"Aggregated text length: {len(aggregated_text)}")

        # Handle both direct result and result.result structure
        if "result" in result:
            result = result["result"]

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

        self.message_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.message_id,
            "method": method,
            "params": params
        }

        request_json = json.dumps(request) + "\n"
        self.logger.debug(f"Sending request: {method}")

        # Send request
        self.process.stdin.write(request_json.encode('utf-8'))
        await self.process.stdin.drain()

        # Read response
        if collect_output:
            return await self._read_response_with_output()
        else:
            return await self._read_response(), ""

    async def _read_response(self) -> JsonDict:
        """Read a single JSON-RPC response."""
        if not self.process or not self.process.stdout:
            raise RuntimeError("Process not available for reading")

        try:
            # Read line by line until we get a complete JSON response
            while True:
                line = await asyncio.wait_for(
                    self.process.stdout.readline(),
                    timeout=self.request_timeout
                )

                if not line:
                    self.logger.warning("Gemini ACP process closed unexpectedly - attempting graceful degradation")
                    # Return empty response instead of crashing
                    return {"error": {"code": -1, "message": "Process closed unexpectedly"}, "result": {"text": ""}}

                line_str = line.decode('utf-8').strip()
                if not line_str:
                    continue

                try:
                    response = json.loads(line_str)
                    self.logger.debug(f"Received response for method: {response.get('id', 'unknown')}")
                    return response
                except json.JSONDecodeError:
                    # Not a complete JSON message, continue reading
                    continue

        except asyncio.TimeoutError:
            raise RuntimeError(f"Timeout waiting for Gemini ACP response (>{self.request_timeout}s)")

    async def _read_response_with_output(self) -> Tuple[JsonDict, str]:
        """Read response and collect streaming output with enhanced deadlock detection."""
        import time
        aggregated_text = ""
        final_response = None
        start_time = time.time()
        consecutive_timeouts = 0
        last_activity_time = start_time

        while time.time() - start_time < self.request_timeout:
            try:
                response = await asyncio.wait_for(self._read_response(), timeout=1.0)
                # Reset timeout counters on successful response
                consecutive_timeouts = 0
                last_activity_time = time.time()
            except asyncio.TimeoutError:
                consecutive_timeouts += 1
                time_since_last_activity = time.time() - last_activity_time

                # Enhanced deadlock detection
                if consecutive_timeouts >= self.max_consecutive_timeouts:
                    self.logger.error(f"Deadlock detected: {self.max_consecutive_timeouts} consecutive timeouts, forcing abort")
                    if aggregated_text:
                        # Return whatever we have collected
                        final_response = {
                            "result": {
                                "text": aggregated_text,
                                "source": "partial_response_deadlock_recovery",
                                "final_response": False
                            }
                        }
                        break
                    else:
                        raise RuntimeError(f"Subprocess deadlock: No response for {max_consecutive_timeouts} consecutive attempts")

                # Check if we have enough to proceed
                if final_response is not None:
                    self.logger.debug(f"Timeout waiting for more responses (consecutive: {consecutive_timeouts}), proceeding with available data")
                    break

                # Enhanced logging for debugging
                if consecutive_timeouts == 2:  # Log on second timeout to reduce spam
                    self.logger.warning(f"Multiple timeouts detected ({consecutive_timeouts}), last activity: {time_since_last_activity:.1f}s ago")

                continue

            # self.logger.debug(f"Received response: {response}")

            # Check if this is a notification about agent message chunk
            if response.get("method") == "session/update":
                params = response.get("params", {})
                update = params.get("update", {})
                session_update_type = update.get("sessionUpdate", "unknown")
                # self.logger.debug(f"Session update: {session_update_type}")

                # Handle agent message chunks with validation
                try:
                    if "agentMessageChunk" in params:
                        chunk_text = params["agentMessageChunk"]
                        if isinstance(chunk_text, str) and chunk_text.strip():
                            aggregated_text += chunk_text
                            self.logger.debug(f"Received legacy format chunk: {len(chunk_text)} chars")
                        else:
                            self.logger.warning(f"Invalid agentMessageChunk format: {type(chunk_text)}")
                    elif session_update_type == "agent_message_chunk":
                        # Handle new format with nested update structure
                        content = update.get("content", {})
                        if isinstance(content, dict):
                            content_type = content.get("type")
                            if content_type == "text":
                                chunk_text = content.get("text", "")
                                if isinstance(chunk_text, str) and chunk_text.strip():
                                    aggregated_text += chunk_text
                                    self.logger.debug(f"Received new format chunk: {len(chunk_text)} chars")
                                else:
                                    self.logger.warning(f"Invalid text content in agent_message_chunk: {type(chunk_text)}")
                            else:
                                self.logger.warning(f"Unsupported content type in agent_message_chunk: {content_type}")
                        else:
                            self.logger.warning(f"Invalid content structure in agent_message_chunk: {type(content)}")
                    elif "done" in params and params["done"]:
                        self.logger.debug("Session update indicates completion (legacy format)")
                        break
                    elif session_update_type == "done":
                        self.logger.info("Session update indicates completion (new format)")
                        break
                    elif "error" in params:
                        error_msg = params.get('error', 'Unknown error')
                        self.logger.error(f"Session update error: {error_msg}")
                        # Don't break immediately - try to get partial response
                        if aggregated_text:
                            self.logger.info("Continuing despite error, using aggregated text")
                            break
                        else:
                            self.logger.warning("No aggregated text available, breaking due to error")
                            break
                    else:
                        # Unknown session update type - log but continue
                        self.logger.debug(f"Unknown session update type: {session_update_type}")
                        if session_update_type not in ["unknown"]:
                            self.logger.debug(f"Session update params: {list(params.keys())}")

                except Exception as e:
                    self.logger.error(f"Error processing session update: {e}")
                    # Continue processing if we have aggregated text
                    if aggregated_text:
                        self.logger.info("Continuing despite parse error, using aggregated text")
                        break

            # Check if this is the final response to our request
            elif "id" in response and response["id"] == self.message_id:
                final_response = response
                self.logger.debug(f"Final response received: {final_response}")
                # Continue reading for a short time to get any remaining chunks

        if final_response is None:
            self.logger.warning("Did not receive final response, but we have aggregated text")
            # In some cases, we might not get a final response but still have the content
            # Create a proper final response with aggregated text
            if aggregated_text.strip():
                final_response = {
                    "result": {
                        "text": aggregated_text,
                        "source": "aggregated_chunks",
                        "final_response": False
                    }
                }
                self.logger.info(f"Using aggregated text as response ({len(aggregated_text)} chars)")
            else:
                # No content available - create empty response
                final_response = {
                    "result": {
                        "text": "",
                        "source": "no_content",
                        "final_response": False
                    }
                }
                self.logger.warning("No content available, returning empty response")

        # Check for errors with graceful handling
        if final_response and "error" in final_response:
            error = final_response["error"]
            error_msg = error.get('message', 'Unknown error')

            # Try to use aggregated text despite the error
            if aggregated_text.strip():
                self.logger.error(f"Gemini ACP error occurred, but using aggregated text: {error_msg}")
                # Create fallback response with aggregated text
                final_response = {
                    "result": {
                        "text": aggregated_text,
                        "source": "fallback_despite_error",
                        "final_response": False,
                        "original_error": error_msg
                    }
                }
                self.logger.info(f"Created fallback response with aggregated text ({len(aggregated_text)} chars)")
            else:
                self.logger.error(f"Gemini ACP error occurred with no content available: {error_msg}")
                # Return empty response with error info
                final_response = {
                    "result": {
                        "text": "",
                        "source": "error_fallback",
                        "final_response": False,
                        "original_error": error_msg
                    }
                }

        # Check if the result contains the response directly
        if final_response and "result" in final_response:
            result_data = final_response["result"]
            self.logger.debug(f"Final result data: {result_data}")
            if "response" in result_data:
                if isinstance(result_data["response"], str):
                    aggregated_text = result_data["response"]
                    self.logger.debug(f"Found text in result.response (string): {len(aggregated_text)} chars")
                elif isinstance(result_data["response"], dict) and "text" in result_data["response"]:
                    aggregated_text = result_data["response"]["text"]
                    self.logger.debug(f"Found text in result.response.text: {len(aggregated_text)} chars")
            elif "text" in result_data:
                aggregated_text = result_data["text"]
                self.logger.debug(f"Found text in result.text: {len(aggregated_text)} chars")

        return final_response, aggregated_text

    async def _send_notification(self, method: str, params: JsonDict):
        """Send a JSON-RPC notification (no response expected)."""
        if not self.process or not self.process.stdin:
            raise RuntimeError("Process not available for writing")

        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        }

        notification_json = json.dumps(notification) + "\n"
        self.process.stdin.write(notification_json.encode('utf-8'))
        await self.process.stdin.drain()

    def _prepare_command_args(self, command: str) -> List[str]:
        """Prepare command arguments, handling shell quoting."""
        try:
            # Use shlex to properly parse the command
            args = shlex.split(command)
        except ValueError:
            # Fallback: simple split if shlex fails
            args = command.split()

        # Ensure the command exists
        if args and not os.path.isfile(args[0]) and not shutil.which(args[0]):
            # Try to find gemini in PATH
            gemini_path = shutil.which("gemini")
            if gemini_path:
                args[0] = gemini_path

        return args