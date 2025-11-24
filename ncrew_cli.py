#!/usr/bin/env python3
"""
NeuroCrew Lab CLI for project management.

Usage:
    python ncrew_cli.py init <project_name>
    python ncrew_cli.py list
    python ncrew_cli.py switch <project_name>
    python ncrew_cli.py current
    python ncrew_cli.py delete <project_name>
"""

import sys
import argparse
from pathlib import Path
from app.config import multi_project_manager
from app.utils.logger import get_logger

logger = get_logger("NCrewCLI")


def cmd_init(args):
    """Initialize a new project."""
    project_name = args.project_name
    
    try:
        if multi_project_manager.project_exists(project_name):
            print(f"❌ Project '{project_name}' already exists")
            return 1
        
        project = multi_project_manager.create_project(project_name)
        multi_project_manager.set_current_project(project_name)
        
        print(f"✅ Created project: {project_name}")
        print(f"📁 Project directory: {project.project_dir}")
        print(f"\nNext steps:")
        print(f"1. Edit configuration: {project.get_config_file()}")
        print(f"2. Run: python main.py")
        return 0
        
    except Exception as e:
        print(f"❌ Error creating project: {e}")
        return 1


def cmd_list(args):
    """List all projects."""
    projects = multi_project_manager.list_projects()
    current = multi_project_manager.get_current_project()
    
    if not projects:
        print("No projects found. Create one with: python ncrew_cli.py init <project_name>")
        return 0
    
    print("Available projects:")
    for project_name in projects:
        marker = " (current)" if project_name == current else ""
        print(f"  - {project_name}{marker}")
    return 0


def cmd_switch(args):
    """Switch to a different project."""
    project_name = args.project_name
    
    if not multi_project_manager.project_exists(project_name):
        print(f"❌ Project '{project_name}' not found")
        return 1
    
    multi_project_manager.set_current_project(project_name)
    print(f"✅ Switched to project: {project_name}")
    return 0


def cmd_current(args):
    """Show current project."""
    current = multi_project_manager.get_current_project()
    
    if not current:
        print("No project selected. Use: python ncrew_cli.py switch <project_name>")
        return 1
    
    print(f"Current project: {current}")
    
    project = multi_project_manager.get_project(current)
    if project:
        print(f"Project directory: {project.project_dir}")
        print(f"Configuration file: {project.get_config_file()}")
    return 0


def cmd_delete(args):
    """Delete a project."""
    project_name = args.project_name
    
    if not multi_project_manager.project_exists(project_name):
        print(f"❌ Project '{project_name}' not found")
        return 1
    
    # Confirm deletion
    response = input(f"Are you sure you want to delete project '{project_name}'? (yes/no): ")
    if response.lower() != 'yes':
        print("Cancelled")
        return 0
    
    try:
        multi_project_manager.delete_project(project_name)
        print(f"✅ Deleted project: {project_name}")
        
        # If current project was deleted, switch to another
        current = multi_project_manager.get_current_project()
        if current == project_name:
            projects = multi_project_manager.list_projects()
            if projects:
                multi_project_manager.set_current_project(projects[0])
                print(f"Switched to project: {projects[0]}")
            else:
                # Remove current project file if no projects left
                multi_project_manager.get_current_project_file().unlink(missing_ok=True)
        
        return 0
        
    except Exception as e:
        print(f"❌ Error deleting project: {e}")
        return 1


def main():
    parser = argparse.ArgumentParser(
        description="NeuroCrew Lab - Multi-project CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s init my_project       Create new project
  %(prog)s list                   List all projects
  %(prog)s switch my_project      Switch to project
  %(prog)s current                Show current project
  %(prog)s delete my_project      Delete project
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # Init command
    parser_init = subparsers.add_parser('init', help='Create new project')
    parser_init.add_argument('project_name', help='Name of the project')
    parser_init.set_defaults(func=cmd_init)
    
    # List command
    parser_list = subparsers.add_parser('list', help='List all projects')
    parser_list.set_defaults(func=cmd_list)
    
    # Switch command
    parser_switch = subparsers.add_parser('switch', help='Switch to project')
    parser_switch.add_argument('project_name', help='Name of the project')
    parser_switch.set_defaults(func=cmd_switch)
    
    # Current command
    parser_current = subparsers.add_parser('current', help='Show current project')
    parser_current.set_defaults(func=cmd_current)
    
    # Delete command
    parser_delete = subparsers.add_parser('delete', help='Delete project')
    parser_delete.add_argument('project_name', help='Name of the project')
    parser_delete.set_defaults(func=cmd_delete)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
