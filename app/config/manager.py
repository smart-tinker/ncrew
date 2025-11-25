"""
Multi-project configuration manager for NeuroCrew Lab.

Each project is a directory with a single config.yaml file.
Prompts are shared across all projects in ~/.ncrew/prompts/
"""

import os
import shutil
import yaml
from pathlib import Path
from typing import Dict, Optional, List, Any

from app.utils.logger import get_logger


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_ROLES_FILE = REPO_ROOT / "roles" / "agents.yaml"
DEFAULT_PROMPTS_DIR = REPO_ROOT / "roles" / "prompts"


class ProjectConfig:
    """Configuration for a single project."""
    
    def __init__(self, project_name: str, config_dir: Path):
        self.project_name = project_name
        self.config_dir = config_dir
        self.project_dir = config_dir / project_name
        self.logger = get_logger(f"ProjectConfig.{project_name}")
        
    def exists(self) -> bool:
        """Check if project directory exists."""
        return self.project_dir.exists()
    
    def create(self, config: Optional[Dict[str, Any]] = None):
        """Create project directory with default config.yaml."""
        self.project_dir.mkdir(parents=True, exist_ok=True)
        (self.project_dir / "data").mkdir(exist_ok=True)
        (self.project_dir / "data" / "conversations").mkdir(exist_ok=True)
        
        # Create default config.yaml
        if config is None:
            config = {
                "main_bot_token": "",
                "target_chat_id": 0,
                "log_level": "INFO",
                "roles": []
            }
        
        self.save_config(config)
    
    def get_config_file(self) -> Path:
        """Get path to project config.yaml file."""
        return self.project_dir / "config.yaml"
    
    def load_config(self) -> Dict[str, Any]:
        """Load configuration from config.yaml."""
        config_file = self.get_config_file()
        if not config_file.exists():
            return {}
        
        with open(config_file, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    
    def save_config(self, config: Dict[str, Any]):
        """Save configuration to config.yaml."""
        config_file = self.get_config_file()
        with open(config_file, 'w', encoding='utf-8') as f:
            yaml.safe_dump(config, f, sort_keys=False, allow_unicode=True, default_flow_style=False)
    
    def get_config_value(self, key: str, default: Any = None) -> Any:
        """Get configuration value."""
        config = self.load_config()
        return config.get(key, default)
    
    def set_config_value(self, key: str, value: Any):
        """Set configuration value."""
        config = self.load_config()
        config[key] = value
        self.save_config(config)


class MultiProjectManager:
    """Manager for multiple NeuroCrew projects."""
    
    DEFAULT_CONFIG_DIR = Path.home() / ".ncrew"
    CURRENT_PROJECT_FILE = "current_project.txt"
    PROMPTS_DIR = "prompts"
    
    def __init__(self, config_dir: Optional[Path] = None):
        self.config_dir = config_dir or self.DEFAULT_CONFIG_DIR
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.prompts_dir = self.config_dir / self.PROMPTS_DIR
        self.prompts_dir.mkdir(exist_ok=True)
        self.logger = get_logger("MultiProjectManager")
        
        # Copy default prompts if prompts_dir is empty
        if not any(self.prompts_dir.glob("*.md")):
            self._copy_default_prompts()

        # If no projects exist, create a default one
        if not self.list_projects():
            self.logger.info("No projects found. Creating 'default' project...")
            self.create_project("default")
            self.set_current_project("default")
    
    def get_prompts_dir(self) -> Path:
        """Get shared prompts directory."""
        return self.prompts_dir
    
    def get_current_project_file(self) -> Path:
        """Get path to file storing current project name."""
        return self.config_dir / self.CURRENT_PROJECT_FILE
    
    def get_current_project(self) -> Optional[str]:
        """Get name of currently active project."""
        project_file = self.get_current_project_file()
        if not project_file.exists():
            return None
        return project_file.read_text().strip()
    
    def set_current_project(self, project_name: str):
        """Set currently active project."""
        project_file = self.get_current_project_file()
        project_file.write_text(project_name)
        self.logger.info(f"Set current project to: {project_name}")
    
    def list_projects(self) -> List[str]:
        """List all available projects."""
        if not self.config_dir.exists():
            return []
        
        projects = []
        for item in self.config_dir.iterdir():
            if item.is_dir() and not item.name.startswith('.') and item.name != self.PROMPTS_DIR:
                # Check if it has config.yaml
                if (item / "config.yaml").exists():
                    projects.append(item.name)
        return sorted(projects)
    
    def project_exists(self, project_name: str) -> bool:
        """Check if project exists."""
        project_dir = self.config_dir / project_name
        return project_dir.exists() and (project_dir / "config.yaml").exists()
    
    def create_project(self, project_name: str, config: Optional[Dict[str, Any]] = None) -> ProjectConfig:
        """Create new project."""
        if self.project_exists(project_name):
            raise ValueError(f"Project '{project_name}' already exists")
        
        project = ProjectConfig(project_name, self.config_dir)
        project.create(config or self._build_default_project_config())
        
        self.logger.info(f"Created new project: {project_name}")
        return project
    
    def get_project(self, project_name: str) -> Optional[ProjectConfig]:
        """Get project configuration."""
        if not self.project_exists(project_name):
            return None
        return ProjectConfig(project_name, self.config_dir)
    
    def delete_project(self, project_name: str):
        """Delete project."""
        import shutil
        project_dir = self.config_dir / project_name
        if project_dir.exists():
            shutil.rmtree(project_dir)
            self.logger.info(f"Deleted project: {project_name}")

    def load_project_config(self, project_name: str) -> Dict[str, Any]:
        """Load project configuration and apply to environment."""
        from app.config import Config
        project = self.get_project(project_name)
        if not project:
            raise ValueError(f"Project '{project_name}' not found")

        # Load project config.yaml
        config = project.load_config()

        self.set_current_project(project_name)

        # Trigger a hot-reload in the Config class
        Config.reload_configuration(project_name)

        return {
            "project_name": project_name,
            "config": config,
            "project_dir": str(project.project_dir),
            "prompts_dir": str(self.prompts_dir)
        }

    def save_prompt(self, prompt_name: str, content: str):
        """Save a prompt file to shared prompts directory."""
        prompt_file = self.prompts_dir / f"{prompt_name}.md"
        with open(prompt_file, 'w', encoding='utf-8') as f:
            f.write(content)
        self.logger.info(f"Saved prompt: {prompt_name}")

    def load_prompt(self, prompt_name: str) -> Optional[str]:
        """Load a prompt file from shared prompts directory."""
        prompt_file = self.prompts_dir / f"{prompt_name}.md"
        if not prompt_file.exists():
            return None
        with open(prompt_file, 'r', encoding='utf-8') as f:
            return f.read()

    def list_prompts(self) -> List[str]:
        """List all available prompts."""
        if not self.prompts_dir.exists():
            return []
        return [f.stem for f in self.prompts_dir.glob("*.md")]

    def _copy_default_prompts(self):
        if not DEFAULT_PROMPTS_DIR.exists():
            return
        for prompt_file in DEFAULT_PROMPTS_DIR.glob("*.md"):
            target = self.prompts_dir / prompt_file.name
            if not target.exists():
                shutil.copy2(prompt_file, target)
                self.logger.info(f"Seeded prompt: {prompt_file.name}")
    
    def _build_default_project_config(self) -> Dict[str, Any]:
        """Build default config from repository roles/agents.yaml if it exists."""
        config = {
            "main_bot_token": "",
            "target_chat_id": 0,
            "log_level": "INFO",
            "roles": []
        }
        
        if not DEFAULT_ROLES_FILE.exists():
            return config
        
        try:
            with open(DEFAULT_ROLES_FILE, 'r', encoding='utf-8') as f:
                default_roles_data = yaml.safe_load(f)
            
            if default_roles_data and 'roles' in default_roles_data:
                for role in default_roles_data['roles']:
                    role_copy = dict(role)
                    prompt_value = role_copy.pop('system_prompt_file', '')
                    if prompt_value:
                        prompt_path = Path(prompt_value)
                        role_copy['prompt_file'] = prompt_path.name
                    else:
                        role_copy['prompt_file'] = ''
                    
                    role_copy.setdefault('telegram_bot_token', '')
                    config['roles'].append(role_copy)
                
                self.logger.info(f"Seeded {len(config['roles'])} roles from repository defaults")
        except Exception as e:
            self.logger.warning(f"Could not seed roles from repository: {e}")
        
        return config


# Global instance
multi_project_manager = MultiProjectManager()
