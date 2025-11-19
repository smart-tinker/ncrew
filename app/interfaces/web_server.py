from functools import wraps
import os
import re
import yaml
from flask import Flask, Response, render_template, request, redirect, url_for, jsonify
from dotenv import load_dotenv, find_dotenv, set_key
from pathlib import Path

ROLE_YAML_FIELDS = [
    "role_name",
    "display_name",
    "telegram_bot_name",
    "system_prompt_file",
    "agent_type",
    "cli_command",
    "description",
]

load_dotenv()

# Resolve template directory relative to project root
base_dir = Path(__file__).resolve().parent.parent.parent
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


# --- Role Management ---
def get_roles():
    with open("roles/agents.yaml", "r") as f:
        roles_data = yaml.safe_load(f)

    roles = roles_data.get("roles", [])

    # Load tokens
    dotenv_path = find_dotenv()
    for role in roles:
        bot_name = role.get("telegram_bot_name")
        if bot_name:
            token_var = f"{bot_name.upper()}_TOKEN"
            token = os.getenv(token_var)
            role["telegram_bot_token"] = token if token else ""

    return roles


def save_roles(roles):
    # Save roles to yaml without sensitive token data
    sanitized_roles = []
    for role in roles:
        sanitized_role = {
            key: role.get(key, "")
            for key in ROLE_YAML_FIELDS
            if role.get(key) not in (None, "")
            or key in ("role_name", "telegram_bot_name")
        }
        sanitized_roles.append(sanitized_role)

    with open("roles/agents.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(
            {"roles": sanitized_roles}, f, sort_keys=False, allow_unicode=True
        )

    # Save tokens to .env
    dotenv_path = find_dotenv()
    for role in roles:
        bot_name = role.get("telegram_bot_name")
        if bot_name:
            token_var = f"{bot_name.upper()}_TOKEN"
            token_value = role.get("telegram_bot_token", "") or ""
            set_key(dotenv_path, token_var, token_value, quote_mode="never")


@app.route("/")
@requires_auth
def index():
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
            "system_prompt_file": prompt_files[i] if i < len(prompt_files) else "",
            "agent_type": agent_types[i] if i < len(agent_types) else "",
            "cli_command": cli_commands[i] if i < len(cli_commands) else "",
            "description": descriptions[i] if i < len(descriptions) else "",
            "telegram_bot_token": bot_tokens[i] if i < len(bot_tokens) else "",
        }
        roles.append(role)

    save_roles(roles)

    # Create reload flag
    with open(".reload", "w") as f:
        f.write("reload")

    return redirect(url_for("index"))


@app.route("/prompt", methods=["GET"])
@requires_auth
def get_prompt():
    filepath = request.args.get("filepath")
    if not filepath:
        return jsonify({"error": "Filepath is required"}), 400

    try:
        # Basic security check to prevent directory traversal
        base_dir = Path.cwd()
        full_path = (base_dir / filepath).resolve()
        if not full_path.is_relative_to(base_dir):
            return jsonify({"error": "Invalid filepath"}), 400

        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
        return jsonify({"content": content})
    except FileNotFoundError:
        return jsonify({"error": "File not found"}), 404
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
        # Basic security check
        base_dir = Path.cwd()
        full_path = (base_dir / filepath).resolve()
        if not full_path.is_relative_to(base_dir):
            return jsonify({"error": "Invalid filepath"}), 400

        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        return jsonify({"message": "File saved successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def run_web_server():
    app.run(host="0.0.0.0", port=8080)


if __name__ == "__main__":
    run_web_server()
