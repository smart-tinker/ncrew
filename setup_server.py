"""
Setup server for NeuroCrew Lab - handles initial project creation.
Runs independently of main application for fresh installations.
"""

import os
from flask import Flask, render_template, request, jsonify, redirect, url_for
from pathlib import Path
from app.config.manager import MultiProjectManager
from app.config import Config

app = Flask(__name__, template_folder="templates")

# Global manager instance
manager = MultiProjectManager()


@app.route("/")
def setup():
    """Main setup page."""
    projects = manager.list_projects()

    if projects:
        # Projects exist, redirect to main app
        return redirect("http://localhost:8080")

    return render_template("setup.html")


@app.route("/api/create-project", methods=["POST"])
def create_project():
    """Create the first project."""
    try:
        data = request.get_json()
        project_name = data.get("project_name", "").strip()
        mode = data.get("mode", "web_only")

        if not project_name:
            return jsonify({"error": "Project name is required"}), 400

        if not project_name.replace("_", "").replace("-", "").isalnum():
            return jsonify(
                {
                    "error": "Project name can only contain letters, numbers, underscores and hyphens"
                }
            ), 400

        # Create project with appropriate config
        config = {
            "main_bot_token": data.get("main_bot_token", "") if mode == "full" else "",
            "target_chat_id": int(data.get("target_chat_id", 0))
            if mode == "full"
            else 0,
            "log_level": "INFO",
            "max_conversation_length": 200,
            "agent_timeout": 600,
            "system_reminder_interval": 5,
            "roles": [],
        }

        project = manager.create_project(project_name, config)
        manager.set_current_project(project_name)

        return jsonify(
            {
                "success": True,
                "project_name": project_name,
                "mode": mode,
                "redirect_url": "http://localhost:8080",
            }
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/check-status")
def check_status():
    """Check setup status."""
    projects = manager.list_projects()
    has_projects = len(projects) > 0

    return jsonify(
        {"has_projects": has_projects, "projects": projects, "ready": has_projects}
    )


def run_setup_server(host="0.0.0.0", port=8080):
    """Run the setup server."""
    print("🤖 NeuroCrew Lab - Setup Server")
    print("Starting setup server for initial configuration...")
    print(f"📱 Open: http://{host}:{port}")
    print("🔧 Create your first project to get started")
    print("")

    app.run(host=host, port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    run_setup_server()
