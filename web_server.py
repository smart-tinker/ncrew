from functools import wraps
import os
import re
import yaml
from flask import Flask, Response, render_template, request, redirect, url_for
from dotenv import load_dotenv, find_dotenv, set_key

load_dotenv()

app = Flask(__name__)


def _sanitize_bot_name(raw_value: str, fallback: str) -> str:
    """Normalize bot name to contain only alphanumerics/underscores."""
    candidate = (raw_value or "").strip() or fallback
    candidate = re.sub(r"[^A-Za-z0-9_]+", "_", candidate)
    candidate = re.sub(r"_+", "_", candidate).strip("_")
    if not candidate:
        candidate = fallback.strip().upper().replace("-", "_")
    return candidate or "ROLE_BOT"

# --- Auth ---
def check_auth(username, password):
    """This function is called to check if a username /
    password combination is valid.
    """
    return username == os.getenv('WEB_ADMIN_USER') and password == os.getenv('WEB_ADMIN_PASS')

def authenticate():
    """Sends a 401 response that enables basic auth"""
    return Response(
    'Could not verify your access level for that URL.\n'
    'You have to login with proper credentials', 401,
    {'WWW-Authenticate': 'Basic realm="Login Required"'})

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
    with open('roles/agents.yaml', 'r') as f:
        roles_data = yaml.safe_load(f)

    roles = roles_data.get('roles', [])

    # Load tokens
    dotenv_path = find_dotenv()
    for role in roles:
        bot_name = role.get('telegram_bot_name')
        if bot_name:
            token_var = f"{bot_name.upper()}_TOKEN"
            token = os.getenv(token_var)
            role['telegram_bot_token'] = token if token else ''

    return roles

def save_roles(roles):
    # Save roles to yaml
    with open('roles/agents.yaml', 'w') as f:
        yaml.dump({'roles': roles}, f, sort_keys=False)

    # Save tokens to .env
    dotenv_path = find_dotenv()
    for role in roles:
        bot_name = role.get('telegram_bot_name')
        if bot_name:
            token_var = f"{bot_name.upper()}_TOKEN"
            set_key(dotenv_path, token_var, role.get('telegram_bot_token', ''))


@app.route('/')
@requires_auth
def index():
    roles = get_roles()
    return render_template('index.html', roles=roles)

@app.route('/save', methods=['POST'])
@requires_auth
def save():
    roles = []
    role_names = request.form.getlist('role_name')
    display_names = request.form.getlist('display_name')
    bot_names = request.form.getlist('telegram_bot_name')
    prompt_files = request.form.getlist('system_prompt_file')
    agent_types = request.form.getlist('agent_type')
    cli_commands = request.form.getlist('cli_command')
    descriptions = request.form.getlist('description')
    bot_tokens = request.form.getlist('telegram_bot_token')

    total_roles = len(role_names)

    for i in range(total_roles):
        role_name = role_names[i]
        telegram_bot_name = _sanitize_bot_name(bot_names[i] if i < len(bot_names) else "", role_name)

        role = {
            'role_name': role_name,
            'display_name': display_names[i] if i < len(display_names) else "",
            'telegram_bot_name': telegram_bot_name,
            'system_prompt_file': prompt_files[i] if i < len(prompt_files) else "",
            'agent_type': agent_types[i] if i < len(agent_types) else "",
            'cli_command': cli_commands[i] if i < len(cli_commands) else "",
            'description': descriptions[i] if i < len(descriptions) else "",
            'telegram_bot_token': bot_tokens[i] if i < len(bot_tokens) else ""
        }
        roles.append(role)

    save_roles(roles)

    # Create reload flag
    with open('.reload', 'w') as f:
        f.write('reload')

    return redirect(url_for('index'))


def run_web_server():
    app.run(host='0.0.0.0', port=8080)

if __name__ == '__main__':
    run_web_server()
