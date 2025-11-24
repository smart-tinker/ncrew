"""
Multi-project configuration manager for NeuroCrew Lab.

Manages configuration for multiple projects stored in ~/.ncrew/
Each project has its own configuration and state.
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Optional, List, Any
from dotenv import load_dotenv, set_key, find_dotenv

from app.utils.logger import get_logger


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
    
    def create(self):
        """Create project directory structure."""
        self.project_dir.mkdir(parents=True, exist_ok=True)
        (self.project_dir / "roles").mkdir(exist_ok=True)
        (self.project_dir / "prompts").mkdir(exist_ok=True)
        (self.project_dir / "data").mkdir(exist_ok=True)
        (self.project_dir / "data" / "conversations").mkdir(exist_ok=True)
        
    def get_env_file(self) -> Path:
        """Get path to project .env file."""
        return self.project_dir / ".env"
    
    def get_roles_file(self) -> Path:
        """Get path to project roles/agents.yaml file."""
        return self.project_dir / "roles" / "agents.yaml"
    
    def load_env(self) -> Dict[str, str]:
        """Load environment variables from project .env file."""
        env_file = self.get_env_file()
        if not env_file.exists():
            return {}
        
        env_vars = {}
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    if '=' in line:
                        key, value = line.split('=', 1)
                        env_vars[key.strip()] = value.strip().strip('"').strip("'")
        return env_vars
    
    def save_env(self, env_vars: Dict[str, str]):
        """Save environment variables to project .env file."""
        env_file = self.get_env_file()
        with open(env_file, 'w') as f:
            for key, value in env_vars.items():
                f.write(f'{key}="{value}"\n')
    
    def get_config_value(self, key: str, default: Any = None) -> Any:
        """Get configuration value from project .env."""
        env_vars = self.load_env()
        return env_vars.get(key, default)
    
    def set_config_value(self, key: str, value: str):
        """Set configuration value in project .env."""
        env_vars = self.load_env()
        env_vars[key] = value
        self.save_env(env_vars)


class MultiProjectManager:
    """Manager for multiple NeuroCrew projects."""
    
    DEFAULT_CONFIG_DIR = Path.home() / ".ncrew"
    CURRENT_PROJECT_FILE = "current_project.txt"
    
    def __init__(self, config_dir: Optional[Path] = None):
        self.config_dir = config_dir or self.DEFAULT_CONFIG_DIR
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.logger = get_logger("MultiProjectManager")
        
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
        return [d.name for d in self.config_dir.iterdir() 
                if d.is_dir() and not d.name.startswith('.')]
    
    def project_exists(self, project_name: str) -> bool:
        """Check if project exists."""
        return (self.config_dir / project_name).exists()
    
    def create_project(self, project_name: str) -> ProjectConfig:
        """Create new project."""
        if self.project_exists(project_name):
            raise ValueError(f"Project '{project_name}' already exists")
        
        project = ProjectConfig(project_name, self.config_dir)
        project.create()
        
        # Create default .env file
        default_env = {
            "MAIN_BOT_TOKEN": "",
            "TARGET_CHAT_ID": "0",
            "LOG_LEVEL": "INFO",
            "MAX_CONVERSATION_LENGTH": "200",
            "AGENT_TIMEOUT": "600"
        }
        project.save_env(default_env)
        
        # Create default agents.yaml
        default_roles = {
            "roles": []
        }
        roles_file = project.get_roles_file()
        with open(roles_file, 'w') as f:
            yaml.safe_dump(default_roles, f, sort_keys=False, allow_unicode=True)
        
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
        project = self.get_project(project_name)
        if not project:
            raise ValueError(f"Project '{project_name}' not found")
        
        # Load project .env
        env_vars = project.load_env()
        
        # Apply to current environment
        for key, value in env_vars.items():
            os.environ[key] = value
        
        # Load roles configuration
        roles_file = project.get_roles_file()
        roles_config = None
        if roles_file.exists():
            with open(roles_file, 'r') as f:
                roles_config = yaml.safe_load(f)
        
        self.set_current_project(project_name)
        
        return {
            "project_name": project_name,
            "env_vars": env_vars,
            "roles": roles_config,
            "project_dir": str(project.project_dir)
        }


# Global instance
multi_project_manager = MultiProjectManager()
