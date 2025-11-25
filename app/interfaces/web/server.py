from functools import wraps
import os
import re
import yaml
from flask import Flask, Response, render_template, request, redirect, url_for, jsonify
from dotenv import load_dotenv, find_dotenv, set_key
from pathlib import Path

from app.config.manager import multi_project_manager
from app.config import Config

ROLE_CONFIG_FIELDS = [
    "role_name",
    "display_name",
    "telegram_bot_name",
    "prompt_file",
    "agent_type",
    "cli_command",
    "description",
    "is_moderator",
    "telegram_bot_token",
]

load_dotenv()

# Resolve template directory relative to project root
base_dir = Path(__file__).resolve().parent.parent.parent.parent
template_dir = base_dir / "templates"

app = Flask(__name__, template_folder=str(template_dir))


def _sanitize_bot_name(role_name: str) -> str:
    """Normalize bot name from role name and add _Bot suffix."""
    if not role_name:
        return "New_Role_Bot"
    # Normalize to contain only alphanumerics/underscores
    candidate = re.sub(r"[^A-Za-z0-9_]+", "_", role_name.strip())
    # Collapse multiple underscores and strip leading/trailing ones
    candidate = re.sub(r"_+", "_", candidate).strip("_")
    if not candidate:
        candidate = "New_Role"
    # Add _Bot suffix if it's not there
    if not candidate.lower().endswith("_bot"):
        candidate += "_Bot"
    return candidate


# Custom YAML presenter to enforce quotes for strings with special chars or spaces
def str_presenter(dumper, data):
    if len(data.splitlines()) > 1:  # multiline
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    # Force quotes if string contains spaces or special yaml chars
    if (
        any(c in data for c in ":{}[],&*#?|-<>=!%@`")
        or " " in data
        or data.isdigit()
        or data.lower() in ("yes", "no", "on", "off", "true", "false", "null")
    ):
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style='"')
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


yaml.SafeDumper.add_representer(str, str_presenter)


# --- Auth ---
def check_auth(username, password):
    """This function is called to check if a username /
    password combination is valid.
    """
    return username == os.getenv("WEB_ADMIN_USER") and password == os.getenv(
        "WEB_ADMIN_PASS"
    )


def authenticate():
    """Sends a 401 response that enables basic auth"""
    return Response(
        "Could not verify your access level for that URL.\n"
        "You have to login with proper credentials",
        401,
        {"WWW-Authenticate": 'Basic realm="Login Required"'},
    )


def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)

    return decorated


import threading


# --- Role Management ---
def get_roles():
    """Get roles from the current project configuration."""
    project_name = Config.PROJECT_NAME
    project = multi_project_manager.get_project(project_name)
    if not project:
        return []
    
    config_data = project.load_config()
    roles = config_data.get("roles", [])
    
    # Ensure all tokens are loaded (if we wanted to load from .env we would do it here, 
    # but we prefer everything in config now)
    return roles


def save_roles(roles):
    """Save roles to the current project configuration."""
    project_name = Config.PROJECT_NAME
    project = multi_project_manager.get_project(project_name)
    if not project:
        return
    
    config_data = project.load_config()
    
    # Filter roles to only include allowed fields
    sanitized_roles = []
    for role in roles:
        sanitized_role = {
            key: role.get(key, "")
            for key in ROLE_CONFIG_FIELDS
            if role.get(key) is not None
        }
        sanitized_roles.append(sanitized_role)
    
    config_data["roles"] = sanitized_roles
    project.save_config(config_data)


@app.route("/")
@requires_auth
def chat_page():
    """Render the web chat page."""
    return render_template("chat.html")


@app.route("/settings")
@requires_auth
def settings():
    """Render the settings/admin page for role management."""
    roles = get_roles()
    return render_template("index.html", roles=roles)


@app.route("/save", methods=["POST"])
@requires_auth
def save():
    roles = []
    role_names = request.form.getlist("role_name")
    display_names = request.form.getlist("display_name")
    telegram_bot_names = request.form.getlist("telegram_bot_name")
    prompt_files = request.form.getlist("system_prompt_file")
    agent_types = request.form.getlist("agent_type")
    cli_commands = request.form.getlist("cli_command")
    descriptions = request.form.getlist("description")
    bot_tokens = request.form.getlist("telegram_bot_token")

    # Checkboxes don't send value if unchecked, so we need a different strategy
    # But here we iterate by index.
    # WORKAROUND: We will check specific form keys like is_moderator_{index}
    # Or we can rely on hidden inputs. Let's look at how index.html will send it.
    # Standard way for list of objects in Flask form:
    # It's hard with getlist if checkboxes are sparse.
    # Better approach: get all keys and parse indices?
    # Or add hidden input with "false" before checkbox?
    # Yes, hidden input trick is standard.

    is_moderators = request.form.getlist("is_moderator")

    # Validate data integrity
    if not (
        len(role_names)
        == len(display_names)
        == len(agent_types)
        == len(cli_commands)
        == len(descriptions)
    ):
        return (
            "Error: Form data mismatch (list lengths differ). Please refresh and try again.",
            400,
        )

    total_roles = len(role_names)

    for i in range(total_roles):
        role_name = role_names[i]
        telegram_bot_name = ""
        if i < len(telegram_bot_names) and telegram_bot_names[i]:
            telegram_bot_name = telegram_bot_names[i]
        else:
            telegram_bot_name = _sanitize_bot_name(role_name)

        role = {
            "role_name": role_name,
            "display_name": display_names[i] if i < len(display_names) else "",
            "telegram_bot_name": telegram_bot_name,
            "prompt_file": prompt_files[i] if i < len(prompt_files) else "", # Changed system_prompt_file to prompt_file to match Config
            "agent_type": agent_types[i] if i < len(agent_types) else "",
            "cli_command": cli_commands[i] if i < len(cli_commands) else "",
            "description": descriptions[i] if i < len(descriptions) else "",
            "telegram_bot_token": bot_tokens[i] if i < len(bot_tokens) else "",
            "is_moderator": is_moderators[i] == "true"
            if i < len(is_moderators)
            else False,
        }
        roles.append(role)

    save_roles(roles)

    # Hot-reload configuration without service interruption
    try:
        from app.config import Config
        success = Config.reload_configuration(Config.PROJECT_NAME)
        if success:
            app.logger.info("🔄 Configuration hot-reloaded successfully")
        else:
            app.logger.error("❌ Configuration hot-reload failed")
    except Exception as e:
        app.logger.error(f"❌ Error during configuration hot-reload: {e}")

    return redirect(url_for("settings"))


@app.route("/prompt", methods=["GET"])
@requires_auth
def get_prompt():
    filepath = request.args.get("filepath")
    if not filepath:
        return jsonify({"error": "Filepath is required"}), 400

    try:
        # Load from shared prompts dir
        prompts_dir = multi_project_manager.get_prompts_dir()
        prompt_name = Path(filepath).name # filepath in request is likely just the filename or partial path
        
        # Security check: prompt should be in prompts_dir
        # Actually multi_project_manager.load_prompt expects prompt_name (filename without ext or with?)
        # Let's use load_prompt logic but adapted.
        # The frontend likely sends just filename
        
        content = multi_project_manager.load_prompt(prompt_name.replace(".md", ""))
        
        if content is None:
             return jsonify({"error": "File not found"}), 404
             
        return jsonify({"content": content})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/prompt", methods=["POST"])
@requires_auth
def save_prompt():
    data = request.json
    filepath = data.get("filepath")
    content = data.get("content")

    if not filepath or content is None:
        return jsonify({"error": "Filepath and content are required"}), 400

    try:
        # Save to shared prompts dir
        prompt_name = Path(filepath).stem
        multi_project_manager.save_prompt(prompt_name, content)
        
        return jsonify({"message": "File saved successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- Chat API Routes ---
@app.route("/api/chat/history")
@requires_auth
def get_chat_history():
    """Get chat history from FileStorage."""
    import asyncio
    from app.config import Config
    from app.storage.file_storage import FileStorage

    try:
        chat_id = Config.TARGET_CHAT_ID
        if not chat_id:
            return jsonify({"error": "TARGET_CHAT_ID not configured"}), 400

        # Run async storage operation
        storage = FileStorage()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        conversation = loop.run_until_complete(storage.load_conversation(chat_id))
        loop.close()

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


@app.route("/api/chat/updates")
@requires_auth
def get_chat_updates():
    """Get new messages since last_index (for polling)."""
    import asyncio
    from app.config import Config
    from app.storage.file_storage import FileStorage

    try:
        last_index = request.args.get("last_index", 0, type=int)
        chat_id = Config.TARGET_CHAT_ID
        if not chat_id:
            return jsonify({"error": "TARGET_CHAT_ID not configured"}), 400

        # Run async storage operation
        storage = FileStorage()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        conversation = loop.run_until_complete(storage.load_conversation(chat_id))
        loop.close()

        # Get only new messages
        new_messages = conversation[last_index:] if last_index < len(conversation) else []

        messages = []
        for msg in new_messages:
            messages.append({
                "role": msg.get("role", "unknown"),
                "role_display": msg.get("role_display") or msg.get("display_name") or msg.get("role", "Unknown"),
                "text": msg.get("text") or msg.get("content", ""),
                "timestamp": msg.get("timestamp", ""),
            })

        return jsonify({"messages": messages})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/chat/message", methods=["POST"])
@requires_auth
def send_chat_message():
    """
    Accept a message from the web chat and process it through the engine.
    This integrates the web interface with the bot's message handling.
    """
    import asyncio
    from app.config import Config
    from app.storage.file_storage import FileStorage
    from datetime import datetime

    try:
        data = request.json
        text = data.get("text", "").strip()

        if not text:
            return jsonify({"error": "Message cannot be empty"}), 400

        chat_id = Config.TARGET_CHAT_ID
        if not chat_id:
            return jsonify({"error": "TARGET_CHAT_ID not configured"}), 400

        # Store the user message
        storage = FileStorage()
        user_message = {
            "role": "user",
            "role_display": "User",
            "text": text,
            "timestamp": datetime.now().isoformat(),
        }

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Add message to storage
        success = loop.run_until_complete(storage.add_message(chat_id, user_message))

        if not success:
            loop.close()
            return jsonify({"error": "Failed to store message"}), 500

        # Trigger message processing through engine
        # Import here to avoid circular imports
        from app.core.engine import NeuroCrewLab
        from app.interfaces.telegram.bot import TelegramBot

        try:
            ncrew = NeuroCrewLab(storage=storage)
            loop.run_until_complete(ncrew.initialize())

            async def run_engine():
                async for _ in ncrew.handle_message(chat_id, text):
                    # Responses are streamed via storage/bots; nothing to return to HTTP caller
                    pass

            # Process the message through the engine (consume async generator)
            loop.run_until_complete(run_engine())
        except Exception as engine_error:
            # Log but don't fail the request - message was stored
            import logging
            logging.warning(f"Engine processing error: {engine_error}")

        loop.close()

        return jsonify({"success": True, "message": "Message sent and processed"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- Project Management API ---
@app.route("/api/projects/list", methods=["GET"])
@requires_auth
def list_projects():
    """List all available projects."""
    try:
        projects = multi_project_manager.list_projects()
        current_project = multi_project_manager.get_current_project()
        return jsonify({
            "projects": projects,
            "current_project": current_project
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/projects/create", methods=["POST"])
@requires_auth
def create_project():
    """Create a new project."""
    data = request.json
    project_name = data.get("project_name")
    
    if not project_name:
        return jsonify({"error": "Project name is required"}), 400
        
    # Basic validation for project name (alphanumeric + underscores/hyphens)
    if not re.match(r"^[a-zA-Z0-9_-]+$", project_name):
         return jsonify({"error": "Invalid project name. Use only letters, numbers, underscores, and hyphens."}), 400

    try:
        if multi_project_manager.project_exists(project_name):
            return jsonify({"error": f"Project '{project_name}' already exists"}), 400
            
        multi_project_manager.create_project(project_name)
        
        # Switch to the new project
        multi_project_manager.load_project_config(project_name)
        
        return jsonify({
            "success": True, 
            "message": f"Project '{project_name}' created and activated",
            "project_name": project_name
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/projects/switch", methods=["POST"])
@requires_auth
def switch_project():
    """Switch to a different project."""
    data = request.json
    project_name = data.get("project_name")
    
    if not project_name:
        return jsonify({"error": "Project name is required"}), 400

    try:
        if not multi_project_manager.project_exists(project_name):
            return jsonify({"error": f"Project '{project_name}' not found"}), 404
            
        multi_project_manager.load_project_config(project_name)
        
        return jsonify({
            "success": True, 
            "message": f"Switched to project '{project_name}'",
            "project_name": project_name
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def run_web_server():
    import time
    import logging

    retries = 5
    port = 8080

    while retries > 0:
        try:
            app.run(host="0.0.0.0", port=port, use_reloader=False)
            break
        except OSError as e:
            if "Address already in use" in str(e) and retries > 0:
                logging.warning(
                    f"Port {port} is busy, retrying in 1 second... ({retries} retries left)"
                )
                time.sleep(1.0)
                retries -= 1
            else:
                raise


if __name__ == "__main__":
    run_web_server()
