"""
Web interface adapter for NeuroCrew.

This module provides the Web adapter that implements the BaseInterface
contract for web-based interactions, enhancing the existing web_server.py
to use the new interface abstraction layer.
"""

import asyncio
import json
import logging
from typing import List, Optional, Dict, Any, Callable
from datetime import datetime
from dataclasses import asdict
from pathlib import Path

from flask import Flask, Response, render_template, request, redirect, url_for, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room

from app.interfaces.base import (
    BaseInterface,
    MessageCapabilities,
    UserIdentity,
    ChatContext,
    Message,
    FormattedMessage,
    MessageType,
    InterfaceType,
    MessageFormatter,
    InterfaceEventHandler,
)
from app.config import Config, RoleConfig
from app.utils.formatters import (
    format_welcome_message,
    format_help_message,
    format_status_message,
    format_agent_response,
)
from app.utils.errors import (
    ConfigurationError,
    handle_errors,
    safe_execute
)
from app.utils.security import validate_input, sanitize_for_logging


class WebMessageFormatter(MessageFormatter):
    """Message formatter for Web interface."""

    async def format_text(self, content: str, **kwargs) -> FormattedMessage:
        """Format plain text for web interface."""
        # Escape HTML for web interface
        import html
        escaped_content = html.escape(content)

        return FormattedMessage(
            content=escaped_content,
            message_type=MessageType.TEXT,
            capabilities_used=self.capabilities,
            formatting_options={'html_escaped': True}
        )

    async def format_markdown(self, content: str, **kwargs) -> FormattedMessage:
        """Format markdown for web interface."""
        # Convert markdown to HTML for web interface
        try:
            import markdown
            html_content = markdown.markdown(
                content,
                extensions=['fenced_code', 'codehilite', 'tables', 'toc']
            )
        except ImportError:
            # Fallback to HTML escaping if markdown not available
            import html
            html_content = html.escape(content)

        return FormattedMessage(
            content=html_content,
            message_type=MessageType.HTML,
            capabilities_used=self.capabilities,
            formatting_options={'html_format': True}
        )

    async def format_html(self, content: str, **kwargs) -> FormattedMessage:
        """Format HTML for web interface."""
        # Web interface supports HTML directly
        return FormattedMessage(
            content=content,
            message_type=MessageType.HTML,
            capabilities_used=self.capabilities,
            formatting_options={'html_format': True}
        )

    async def format_agent_response(self, agent_name: str, content: str, **kwargs) -> List[FormattedMessage]:
        """Format agent response for web interface."""
        # Create formatted response with agent name as header
        formatted_content = f"""
<div class="agent-response">
    <div class="agent-header">
        <strong>{agent_name}</strong>
        <span class="agent-timestamp">{datetime.now().strftime('%H:%M:%S')}</span>
    </div>
    <div class="agent-content">
        {await self._format_content_with_markdown(content)}
    </div>
</div>
"""

        return [FormattedMessage(
            content=formatted_content,
            message_type=MessageType.HTML,
            capabilities_used=self.capabilities,
            formatting_options={'html_format': True, 'agent_response': True}
        )]

    async def format_system_status(self, status_data: Dict[str, Any]) -> FormattedMessage:
        """Format system status for web interface."""
        # Create HTML table for system status
        status_items = []
        for key, value in status_data.items():
            status_items.append(f"<tr><td><strong>{key}</strong></td><td>{value}</td></tr>")

        content = f"""
<div class="system-status">
    <h4>🔍 System Status</h4>
    <table class="status-table">
        {"".join(status_items)}
    </table>
</div>
"""

        return FormattedMessage(
            content=content,
            message_type=MessageType.HTML,
            capabilities_used=self.capabilities,
            formatting_options={'html_format': True, 'system_status': True}
        )

    async def _format_content_with_markdown(self, content: str) -> str:
        """Helper method to format content with markdown."""
        try:
            import markdown
            return markdown.markdown(
                content,
                extensions=['fenced_code', 'codehilite', 'tables', 'toc']
            )
        except ImportError:
            # Fallback to HTML escaping
            import html
            return html.escape(content).replace('\n', '<br>')


class WebAdapter(BaseInterface):
    """
    Web interface adapter implementing BaseInterface contract.

    This adapter handles web-based interactions through Flask and WebSocket
    while exposing a clean interface-agnostic API to the NeuroCrew system.
    """

    def __init__(self, interface_type: InterfaceType = InterfaceType.WEB):
        """Initialize the Web adapter."""
        super().__init__(interface_type)

        self.app: Optional[Flask] = None
        self.socketio: Optional[SocketIO] = None
        self._capabilities: Optional[MessageCapabilities] = None
        self.formatter: Optional[WebMessageFormatter] = None
        self.ncrew = None  # Will be injected by InterfaceManager
        self.connected_clients: Dict[str, Dict[str, Any]] = {}
        self.message_handlers: Dict[str, Callable] = {}

    @property
    def capabilities(self) -> MessageCapabilities:
        """Get Web interface capabilities."""
        if self._capabilities is None:
            self._capabilities = MessageCapabilities(
                supports_markdown=True,
                supports_html=True,
                max_message_length=50000,  # Much larger for web
                supports_files=True,
                supports_images=True,
                supports_audio=False,  # Could be enabled with additional work
                supports_video=False,  # Could be enabled with additional work
                supports_inline_buttons=False,  # Web uses different interaction patterns
                supports_typing_indicators=True  # Via WebSocket events
            )
        return self._capabilities

    async def initialize(self) -> bool:
        """
        Initialize the Web adapter.

        Returns:
            bool: True if initialization successful
        """
        try:
            # Initialize Flask app
            self.app = Flask(__name__,
                           template_folder=str(Path(__file__).parent.parent.parent / "templates"))
            self.app.config['SECRET_KEY'] = 'neurocrew-web-interface-secret'

            # Initialize SocketIO
            self.socketio = SocketIO(
                self.app,
                cors_allowed_origins="*",
                async_mode='threading'
            )

            # Initialize formatter
            self.formatter = WebMessageFormatter(self.capabilities)

            # Set up Flask routes and WebSocket handlers
            self._setup_flask_routes()
            self._setup_socketio_handlers()

            self.logger.info("Web adapter initialized successfully")
            return True

        except Exception as e:
            self.logger.error(f"Failed to initialize Web adapter: {e}")
            await self._emit_interface_error(e)
            return False

    async def start(self) -> bool:
        """
        Start the Web adapter.

        Returns:
            bool: True if start successful
        """
        try:
            if not self.app or not self.socketio:
                await self.initialize()

            self.is_running = True
            await self._emit_interface_ready()
            self.logger.info("Web adapter started successfully")
            return True

        except Exception as e:
            self.logger.error(f"Failed to start Web adapter: {e}")
            await self._emit_interface_error(e)
            return False

    async def stop(self) -> bool:
        """
        Stop the Web adapter gracefully.

        Returns:
            bool: True if stop successful
        """
        try:
            self.is_running = False

            # Disconnect all clients
            for client_id in list(self.connected_clients.keys()):
                try:
                    self.socketio.emit('disconnect', room=client_id)
                except:
                    pass

            self.connected_clients.clear()
            await self._emit_interface_shutdown()
            self.logger.info("Web adapter stopped successfully")
            return True

        except Exception as e:
            self.logger.error(f"Error stopping Web adapter: {e}")
            return False

    async def send_message(self, chat_context: ChatContext, message: FormattedMessage) -> bool:
        """
        Send a message through Web interface.

        Args:
            chat_context: The chat context for routing
            message: The formatted message to send

        Returns:
            bool: True if message sent successfully
        """
        try:
            if not self.is_running or not self.socketio:
                self.logger.warning("Web adapter not running, cannot send message")
                return False

            # Prepare message data for WebSocket
            message_data = {
                'id': f"msg_{datetime.now().timestamp()}",
                'content': message.content,
                'message_type': message.message_type.value,
                'timestamp': datetime.now().isoformat(),
                'chat_id': chat_context.chat_id,
                'formatting_options': message.formatting_options or {},
                'metadata': message.metadata or {}
            }

            # Send message to specific chat room
            room_name = f"chat_{chat_context.chat_id}"
            self.socketio.emit('message', message_data, room=room_name)

            return True

        except Exception as e:
            self.logger.error(f"Failed to send web message: {e}")
            return False

    async def send_typing_indicator(self, chat_context: ChatContext, is_typing: bool) -> bool:
        """
        Send or stop typing indicator in web interface.

        Args:
            chat_context: The chat context
            is_typing: Whether to start or stop typing indicator

        Returns:
            bool: True if action successful
        """
        try:
            if not self.is_running or not self.socketio:
                return False

            room_name = f"chat_{chat_context.chat_id}"
            typing_data = {
                'chat_id': chat_context.chat_id,
                'is_typing': is_typing,
                'timestamp': datetime.now().isoformat()
            }

            self.socketio.emit('typing', typing_data, room=room_name)
            return True

        except Exception as e:
            self.logger.error(f"Failed to send typing indicator: {e}")
            return False

    def set_ncrew_instance(self, ncrew_instance) -> None:
        """
        Set the NeuroCrew instance for this adapter.

        Args:
            ncrew_instance: The NeuroCrew instance
        """
        self.ncrew = ncrew_instance

    def get_flask_app(self) -> Optional[Flask]:
        """Get the Flask application for external serving."""
        return self.app

    def get_socketio_instance(self) -> Optional[SocketIO]:
        """Get the SocketIO instance for external serving."""
        return self.socketio

    def run_server(self, host: str = "0.0.0.0", port: int = 8080, debug: bool = False) -> None:
        """
        Run the Flask web server with SocketIO.

        Args:
            host: Host to bind to
            port: Port to bind to
            debug: Enable debug mode
        """
        if self.socketio:
            self.socketio.run(self.app, host=host, port=port, debug=debug)

    def _setup_flask_routes(self) -> None:
        """Set up Flask HTTP routes."""

        @self.app.route("/")
        def index():
            """Main chat interface."""
            return render_template("web_chat.html")

        @self.app.route("/chat/<conversation_type>")
        def chat_page(conversation_type):
            """Chat page with specific conversation type."""
            valid_types = ["file", "voice", "image", "video"]
            if conversation_type not in valid_types:
                return f"Invalid conversation type: {conversation_type}", 400
            return render_template("web_chat.html", conversation_type=conversation_type)

        @self.app.route("/api/chat/history")
        def get_chat_history():
            """Get chat history API endpoint."""
            try:
                chat_id = request.args.get("chat_id", str(Config.TARGET_CHAT_ID))
                if not self.ncrew:
                    return jsonify({"error": "NeuroCrew not initialized"}), 500

                # Get conversation from storage
                conversation = asyncio.run(self.ncrew.storage.load_conversation(chat_id))

                # Format messages for frontend
                messages = []
                for msg in conversation:
                    messages.append({
                        "role": msg.get("role", "unknown"),
                        "role_display": msg.get("role_display") or msg.get("display_name") or msg.get("role", "Unknown"),
                        "text": msg.get("text") or msg.get("content", ""),
                        "timestamp": msg.get("timestamp", ""),
                    })

                return jsonify({"messages": messages, "total": len(messages)})

            except Exception as e:
                return jsonify({"error": str(e)}), 500

        @self.app.route("/api/status")
        def get_status():
            """Get system status API endpoint."""
            try:
                if not self.ncrew:
                    return jsonify({"error": "NeuroCrew not initialized"}), 500

                status = asyncio.run(self.ncrew.get_system_status())
                return jsonify(status)

            except Exception as e:
                return jsonify({"error": str(e)}), 500

        @self.app.route("/api/agents")
        def get_agents():
            """Get agent information API endpoint."""
            try:
                if not self.ncrew:
                    return jsonify({"error": "NeuroCrew not initialized"}), 500

                chat_id = request.args.get("chat_id", str(Config.TARGET_CHAT_ID))
                agent_info = asyncio.run(self.ncrew.get_chat_agent_info(chat_id))
                return jsonify(agent_info or {})

            except Exception as e:
                return jsonify({"error": str(e)}), 500

    def _setup_socketio_handlers(self) -> None:
        """Set up SocketIO WebSocket handlers."""

        @self.socketio.on('connect')
        def handle_connect():
            """Handle client connection."""
            self.logger.info(f"Client connected: {request.sid}")
            self.connected_clients[request.sid] = {
                'connected_at': datetime.now().isoformat(),
                'chat_id': None
            }

        @self.socketio.on('disconnect')
        def handle_disconnect():
            """Handle client disconnection."""
            self.logger.info(f"Client disconnected: {request.sid}")
            if request.sid in self.connected_clients:
                del self.connected_clients[request.sid]

        @self.socketio.on('join_chat')
        def handle_join_chat(data):
            """Handle client joining a chat room."""
            chat_id = data.get('chat_id', str(Config.TARGET_CHAT_ID))
            room_name = f"chat_{chat_id}"

            join_room(room_name)

            if request.sid in self.connected_clients:
                self.connected_clients[request.sid]['chat_id'] = chat_id

            emit('joined_chat', {'chat_id': chat_id})

        @self.socketio.on('leave_chat')
        def handle_leave_chat(data):
            """Handle client leaving a chat room."""
            chat_id = data.get('chat_id')
            if chat_id:
                room_name = f"chat_{chat_id}"
                leave_room(room_name)

                if request.sid in self.connected_clients:
                    self.connected_clients[request.sid]['chat_id'] = None

                emit('left_chat', {'chat_id': chat_id})

        @self.socketio.on('message')
        def handle_message(data):
            """Handle incoming message from client."""
            try:
                chat_id = data.get('chat_id', str(Config.TARGET_CHAT_ID))
                content = data.get('text', '').strip()

                if not content:
                    emit('error', {'message': 'Message cannot be empty'})
                    return

                # Get client info
                client_info = self.connected_clients.get(request.sid, {})
                user_identity = UserIdentity(
                    user_id=request.sid,
                    username=f"web_user_{request.sid[:8]}",
                    display_name=f"Web User",
                    interface_type=InterfaceType.WEB,
                    chat_id=chat_id
                )

                chat_context = ChatContext(
                    chat_id=chat_id,
                    interface_type=InterfaceType.WEB,
                    user_identity=user_identity,
                    metadata={'session_id': request.sid}
                )

                message = Message(
                    content=content,
                    message_type=MessageType.TEXT,
                    sender=user_identity,
                    chat_context=chat_context,
                    timestamp=datetime.now().isoformat(),
                    metadata={'web_session_id': request.sid}
                )

                # Validate input
                is_valid, error_msg = validate_input(content, "message")
                if not is_valid:
                    self.logger.warning(f"Security check failed for web message: {error_msg}")
                    emit('error', {'message': 'Message contains potentially dangerous content'})
                    return

                # Log sanitized message
                sanitized_message = sanitize_for_logging(content)
                self.logger.info(f"Web message from {user_identity.display_name}: {sanitized_message[:100]}...")

                # Route message through interface abstraction
                asyncio.create_task(self._emit_message_received(message))

            except Exception as e:
                self.logger.error(f"Error handling web message: {e}")
                emit('error', {'message': 'Failed to process message'})

        @self.socketio.on('typing')
        def handle_typing(data):
            """Handle typing indicator from client."""
            try:
                chat_id = data.get('chat_id', str(Config.TARGET_CHAT_ID))
                is_typing = data.get('is_typing', False)

                client_info = self.connected_clients.get(request.sid, {})
                user_identity = UserIdentity(
                    user_id=request.sid,
                    username=f"web_user_{request.sid[:8]}",
                    display_name=f"Web User",
                    interface_type=InterfaceType.WEB,
                    chat_id=chat_id
                )

                chat_context = ChatContext(
                    chat_id=chat_id,
                    interface_type=InterfaceType.WEB,
                    user_identity=user_identity,
                    metadata={'session_id': request.sid}
                )

                # Broadcast typing indicator to other clients in the room
                room_name = f"chat_{chat_id}"
                typing_data = {
                    'chat_id': chat_id,
                    'is_typing': is_typing,
                    'user_display': user_identity.display_name,
                    'timestamp': datetime.now().isoformat()
                }

                self.socketio.emit('typing', typing_data, room=room_name, include_self=False)

            except Exception as e:
                self.logger.error(f"Error handling typing indicator: {e}")


# Register the Web adapter
from app.interfaces.base import interface_registry
interface_registry.register_interface(InterfaceType.WEB, WebAdapter)