#!/usr/bin/env python3
"""
Comprehensive System Requirements Validator for NeuroCrew Lab

This script performs ultra-thorough validation of all system requirements,
dependencies, and configuration prerequisites for running the NeuroCrew Lab application.

Usage:
    python scripts/validate_system.py [--verbose] [--fix] [--check-only]

Options:
    --verbose     Show detailed output for each check
    --fix         Attempt to automatically fix common issues
    --check-only  Skip fixes, only perform checks (default)
"""

import os
import sys
import subprocess
import platform
import json
import shutil
import asyncio
import importlib.util
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, asdict
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of a system validation check."""

    name: str
    status: str  # 'PASS', 'FAIL', 'WARN', 'SKIP'
    message: str
    details: Optional[Dict[str, Any]] = None
    fix_command: Optional[str] = None
    severity: str = "CRITICAL"  # 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'


class SystemValidator:
    """Comprehensive system validator for NeuroCrew Lab."""

    def __init__(
        self, project_root: Path, verbose: bool = False, auto_fix: bool = False
    ):
        self.project_root = project_root
        self.verbose = verbose
        self.auto_fix = auto_fix
        self.results: List[ValidationResult] = []
        self.system_info = self._get_system_info()

        # Paths to check
        self.venv_path = project_root / "venv"
        self.env_file = project_root / ".env"
        self.config_file = project_root / "config.py"
        self.main_file = project_root / "main.py"
        self.data_dir = project_root / "data"

    def _get_system_info(self) -> Dict[str, str]:
        """Collect system information."""
        return {
            "platform": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "architecture": platform.architecture()[0],
        }

    def _add_result(self, result: ValidationResult):
        """Add a validation result."""
        self.results.append(result)
        if self.verbose or result.status != "PASS":
            status_icon = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️", "SKIP": "⏭️"}.get(
                result.status, "❓"
            )

            print(f"{status_icon} {result.name}: {result.message}")
            if result.details and self.verbose:
                for key, value in result.details.items():
                    print(f"   {key}: {value}")
            if result.fix_command and result.status == "FAIL":
                print(f"   💡 Fix: {result.fix_command}")

    def validate_python_environment(self) -> ValidationResult:
        """Validate Python environment and version."""
        result = ValidationResult(
            name="Python Environment Check",
            status="PASS",
            message="Python environment validated",
        )

        try:
            # Check Python version
            python_version = sys.version_info
            if python_version < (3, 8):
                result.status = "FAIL"
                result.message = f"Python {python_version.major}.{python_version.minor} is not supported. Requires Python 3.8+"
                result.fix_command = "Install Python 3.8 or higher"
                return result

            # Check if we're in a virtual environment
            in_venv = hasattr(sys, "real_prefix") or (
                hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
            )

            if not in_venv and self.venv_path.exists():
                result.status = "WARN"
                result.message = "Virtual environment exists but not activated"
                result.fix_command = f"source {self.venv_path}/bin/activate"
            elif not in_venv:
                result.status = "WARN"
                result.message = "No virtual environment detected"
                result.fix_command = "python -m venv venv && source venv/bin/activate"

            result.details = {
                "python_version": f"{python_version.major}.{python_version.minor}.{python_version.micro}",
                "python_implementation": self.system_info["python_implementation"],
                "virtual_env": in_venv,
                "executable": sys.executable,
            }

        except Exception as e:
            result.status = "FAIL"
            result.message = f"Failed to validate Python environment: {str(e)}"

        return result

    def validate_project_structure(self) -> ValidationResult:
        """Validate project directory structure."""
        result = ValidationResult(
            name="Project Structure Check",
            status="PASS",
            message="Project structure validated",
        )

        required_files = [
            "main.py",
            "config.py",
            "requirements.txt",
            "ncrew.py",
            "telegram_bot.py",
            ".env",
        ]

        required_dirs = ["connectors", "storage", "utils", "data"]

        missing_files = []
        missing_dirs = []

        for file_path in required_files:
            if not (self.project_root / file_path).exists():
                missing_files.append(file_path)

        for dir_path in required_dirs:
            if not (self.project_root / dir_path).exists():
                missing_dirs.append(dir_path)

        if missing_files or missing_dirs:
            result.status = "FAIL"
            result.message = "Missing required project files or directories"
            result.details = {
                "missing_files": missing_files,
                "missing_dirs": missing_dirs,
            }
        else:
            result.details = {
                "project_root": str(self.project_root),
                "required_files": "✓ All present",
                "required_dirs": "✓ All present",
            }

        return result

    def validate_dependencies(self) -> ValidationResult:
        """Validate Python dependencies."""
        result = ValidationResult(
            name="Python Dependencies Check",
            status="PASS",
            message="All dependencies validated",
        )

        try:
            # Check if requirements.txt exists and parse it
            req_file = self.project_root / "requirements.txt"
            if not req_file.exists():
                result.status = "FAIL"
                result.message = "requirements.txt not found"
                return result

            # Parse requirements
            with open(req_file, "r") as f:
                requirements = [
                    line.strip()
                    for line in f
                    if line.strip() and not line.startswith("#")
                ]

            missing_packages = []
            outdated_packages = []
            installed_packages = []

            for req in requirements:
                package_name = req.split("==")[0].split(">=")[0].split("<=")[0]

                try:
                    spec = importlib.util.find_spec(package_name)
                    if spec is None:
                        missing_packages.append(package_name)
                    else:
                        installed_packages.append(package_name)
                except ImportError:
                    missing_packages.append(package_name)

            if missing_packages:
                result.status = "FAIL"
                result.message = (
                    f"Missing required packages: {', '.join(missing_packages)}"
                )
                result.fix_command = f"pip install -r {req_file}"
            else:
                result.message = (
                    f"All {len(installed_packages)} required packages installed"
                )

            result.details = {
                "required_packages": len(requirements),
                "installed_packages": len(installed_packages),
                "missing_packages": missing_packages,
                "package_list": installed_packages,
            }

        except Exception as e:
            result.status = "FAIL"
            result.message = f"Failed to validate dependencies: {str(e)}"

        return result

    def validate_configuration(self) -> ValidationResult:
        """Validate application configuration."""
        result = ValidationResult(
            name="Configuration Validation",
            status="PASS",
            message="Configuration validated",
        )

        try:
            # Check .env file exists
            if not self.env_file.exists():
                result.status = "FAIL"
                result.message = ".env file not found"
                result.fix_command = "cp .env.example .env && edit .env"
                return result

            # Load and validate .env
            with open(self.env_file, "r") as f:
                env_content = f.read()

            required_vars = ["TELEGRAM_BOT_TOKEN"]
            optional_vars = [
                "QWEN_CLI_PATH",
                "GEMINI_CLI_PATH",
                "CLAUDE_CLI_PATH",
                "OPENCODE_CLI_PATH",
                "CODEX_CLI_PATH",
                "MAX_CONVERSATION_LENGTH",
                "AGENT_TIMEOUT",
                "LOG_LEVEL",
                "DATA_DIR",
            ]

            missing_vars = []
            placeholder_vars = []

            for var in required_vars:
                if f"{var}=" not in env_content:
                    missing_vars.append(var)
                elif "your_" in env_content.split(f"{var}=")[1].split("\n")[0].lower():
                    placeholder_vars.append(var)

            if missing_vars:
                result.status = "FAIL"
                result.message = (
                    f"Missing required environment variables: {', '.join(missing_vars)}"
                )
            elif placeholder_vars:
                result.status = "WARN"
                result.message = (
                    f"Placeholder values detected: {', '.join(placeholder_vars)}"
                )

            # Validate Telegram bot token format
            if "TELEGRAM_BOT_TOKEN=" in env_content:
                token = (
                    env_content.split("TELEGRAM_BOT_TOKEN=")[1].split("\n")[0].strip()
                )
                if not token or len(token) < 20:
                    result.status = "FAIL"
                    result.message = "Invalid Telegram bot token format"

            result.details = {
                "env_file_exists": True,
                "required_vars": len(
                    [v for v in required_vars if f"{v}=" in env_content]
                ),
                "optional_vars": len(
                    [v for v in optional_vars if f"{v}=" in env_content]
                ),
                "missing_vars": missing_vars,
                "placeholder_vars": placeholder_vars,
            }

        except Exception as e:
            result.status = "FAIL"
            result.message = f"Failed to validate configuration: {str(e)}"

        return result

    def validate_cli_agents(self) -> ValidationResult:
        """Validate CLI agent availability."""
        result = ValidationResult(
            name="CLI Agents Validation", status="PASS", message="CLI agents validated"
        )

        try:
            cli_agents = {
                "qwen": ["qwen", "qwen-code"],
                "gemini": ["gemini", "gemini-cli"],
                "claude": ["claude", "claude-code"],
                "opencode": ["opencode"],
                "codex": ["codex"],
            }

            agent_status = {}
            missing_agents = []

            for agent_name, possible_commands in cli_agents.items():
                agent_found = False
                working_command = None

                for cmd in possible_commands:
                    try:
                        # Check if command exists in PATH
                        cmd_path = shutil.which(cmd)
                        if cmd_path:
                            # Try to run --version or --help to verify it works
                            result_check = subprocess.run(
                                [cmd, "--version"],
                                capture_output=True,
                                text=True,
                                timeout=5,
                            )
                            if result_check.returncode == 0:
                                agent_found = True
                                working_command = cmd
                                version_output = result_check.stdout.strip()
                            else:
                                # Try --help if --version fails
                                result_check = subprocess.run(
                                    [cmd, "--help"],
                                    capture_output=True,
                                    text=True,
                                    timeout=5,
                                )
                                if result_check.returncode == 0:
                                    agent_found = True
                                    working_command = cmd
                                    version_output = "Help command available"
                            break
                    except (
                        subprocess.TimeoutExpired,
                        FileNotFoundError,
                        PermissionError,
                    ):
                        continue

                agent_status[agent_name] = {
                    "found": agent_found,
                    "command": working_command,
                    "path": shutil.which(working_command) if working_command else None,
                }

                if not agent_found:
                    missing_agents.append(agent_name)

            if missing_agents:
                result.status = "WARN"
                result.message = f"CLI agents not found: {', '.join(missing_agents)}"
            else:
                result.message = "All CLI agents are available"

            result.details = {
                "total_agents": len(cli_agents),
                "found_agents": len([a for a in agent_status.values() if a["found"]]),
                "missing_agents": missing_agents,
                "agent_status": agent_status,
            }

        except Exception as e:
            result.status = "FAIL"
            result.message = f"Failed to validate CLI agents: {str(e)}"

        return result

    def validate_socks_support(self) -> ValidationResult:
        """Validate SOCKS proxy support in httpx."""
        result = ValidationResult(
            name="SOCKS Proxy Support Check",
            status="PASS",
            message="SOCKS proxy support validated",
        )

        try:
            # Try to import socksio (required by httpx for socks support)
            import importlib.util

            if importlib.util.find_spec("socksio") is None:
                # Double check by trying to initialize httpx with socks proxy
                try:
                    import httpx

                    # This is just a test initialization, doesn't connect
                    with httpx.Client(proxy="socks5://127.0.0.1:1080"):
                        pass
                except Exception as e:
                    if "Unknown scheme" in str(e) or "Scheme not supported" in str(e):
                        result.status = "FAIL"
                        result.message = (
                            "Missing SOCKS support. 'socksio' library is required."
                        )
                        result.fix_command = "pip install 'httpx[socks]'"
                        return result

            result.message = "SOCKS support (socksio) is available"

        except Exception as e:
            result.status = "WARN"
            result.message = f"Could not verify SOCKS support: {e}"

        return result

    def validate_socks_support(self) -> ValidationResult:
        """Validate SOCKS proxy support in httpx."""
        result = ValidationResult(
            name="SOCKS Proxy Support Check",
            status="PASS",
            message="SOCKS proxy support validated",
        )

        try:
            # Try to import socksio (required by httpx for socks support)
            import importlib.util

            if importlib.util.find_spec("socksio") is None:
                # Double check by trying to initialize httpx with socks proxy
                try:
                    import httpx

                    # This is just a test initialization, doesn't connect
                    with httpx.Client(proxy="socks5://127.0.0.1:1080"):
                        pass
                except Exception as e:
                    if "Unknown scheme" in str(e) or "Scheme not supported" in str(e):
                        result.status = "FAIL"
                        result.message = (
                            "Missing SOCKS support. 'socksio' library is required."
                        )
                        result.fix_command = "pip install 'httpx[socks]'"
                        return result

            result.message = "SOCKS support (socksio) is available"

        except Exception as e:
            result.status = "WARN"
            result.message = f"Could not verify SOCKS support: {e}"

        return result

    def validate_network_connectivity(self) -> ValidationResult:
        """Validate network connectivity for Telegram API."""
        result = ValidationResult(
            name="Network Connectivity Check",
            status="PASS",
            message="Network connectivity validated",
        )

        try:
            # Test Telegram API connectivity
            import socket

            telegram_hosts = ["api.telegram.org", "core.telegram.org"]
            connectivity_results = {}

            for host in telegram_hosts:
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(5)
                    result_code = sock.connect_ex((host, 443))
                    sock.close()

                    connectivity_results[host] = {
                        "status": "OK" if result_code == 0 else "FAIL",
                        "port": 443,
                        "timeout": 5,
                    }
                except Exception as e:
                    connectivity_results[host] = {"status": "ERROR", "error": str(e)}

            failed_hosts = [
                h for h, r in connectivity_results.items() if r["status"] != "OK"
            ]

            if failed_hosts:
                result.status = "FAIL"
                result.message = (
                    f"Cannot connect to Telegram hosts: {', '.join(failed_hosts)}"
                )
            else:
                result.message = "Telegram API connectivity confirmed"

            result.details = {
                "telegram_hosts": connectivity_results,
                "dns_resolution": "OK" if not failed_hosts else "FAILED",
                "proxy_detected": bool(
                    os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY")
                ),
            }

            # Check for proxy configuration issues
            proxy_vars = [
                "HTTP_PROXY",
                "HTTPS_PROXY",
                "http_proxy",
                "https_proxy",
                "ALL_PROXY",
                "all_proxy",
            ]
            proxy_config = {var: os.getenv(var) for var in proxy_vars if os.getenv(var)}

            if proxy_config:
                # Validate proxy URL format
                invalid_proxies = []
                for var, url in proxy_config.items():
                    # Accept socks:// as we now sanitize it in main.py
                    if not url.startswith(
                        ("http://", "https://", "socks4://", "socks5://", "socks://")
                    ):
                        invalid_proxies.append(f"{var}: {url}")

                if invalid_proxies:
                    result.status = "FAIL"
                    result.message = (
                        f"Invalid proxy configuration: {', '.join(invalid_proxies)}"
                    )
                    result.fix_command = "Check proxy environment variables format"

                result.details["proxy_config"] = proxy_config
                result.details["invalid_proxies"] = invalid_proxies

        except Exception as e:
            result.status = "FAIL"
            result.message = f"Failed to validate network connectivity: {str(e)}"

        return result

    def validate_file_permissions(self) -> ValidationResult:
        """Validate file and directory permissions."""
        result = ValidationResult(
            name="File Permissions Check",
            status="PASS",
            message="File permissions validated",
        )

        try:
            permission_issues = []

            # Check project root permissions
            if not os.access(self.project_root, os.R_OK | os.W_OK | os.X_OK):
                permission_issues.append("project_root: insufficient permissions")

            # Check data directory
            data_dir = self.project_root / "data"
            data_dir.mkdir(exist_ok=True)
            if not os.access(data_dir, os.R_OK | os.W_OK | os.X_OK):
                permission_issues.append("data directory: insufficient permissions")

            # Check log directory can be created
            log_dir = data_dir / "logs"
            log_dir.mkdir(exist_ok=True)
            if not os.access(log_dir, os.R_OK | os.W_OK | os.X_OK):
                permission_issues.append("logs directory: insufficient permissions")

            # Check conversation directory
            conv_dir = data_dir / "conversations"
            conv_dir.mkdir(exist_ok=True)
            if not os.access(conv_dir, os.R_OK | os.W_OK | os.X_OK):
                permission_issues.append(
                    "conversations directory: insufficient permissions"
                )

            # Check .env file permissions (should be readable but not world-readable)
            if self.env_file.exists():
                env_stat = self.env_file.stat()
                if env_stat.st_mode & 0o004:  # World-readable
                    permission_issues.append(
                        ".env file: too permissive (world-readable)"
                    )

            if permission_issues:
                result.status = "WARN"
                result.message = (
                    f"Permission issues found: {', '.join(permission_issues)}"
                )
                result.fix_command = "chmod 755 . && chmod 600 .env"

            result.details = {
                "project_root": str(self.project_root),
                "data_dir_writable": os.access(data_dir, os.W_OK),
                "env_file_protected": not (
                    self.env_file.exists() and self.env_file.stat().st_mode & 0o004
                ),
                "user": os.getenv("USER"),
                "permission_issues": permission_issues,
            }

        except Exception as e:
            result.status = "FAIL"
            result.message = f"Failed to validate file permissions: {str(e)}"

        return result

    def validate_system_resources(self) -> ValidationResult:
        """Validate system resources and limits."""
        result = ValidationResult(
            name="System Resources Check",
            status="PASS",
            message="System resources validated",
        )

        try:
            import psutil

            # Get system information
            cpu_count = psutil.cpu_count()
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage(str(self.project_root))

            warnings = []

            # Check memory (minimum 512MB required)
            if memory.available < 512 * 1024 * 1024:  # 512MB
                warnings.append("Low available memory")

            # Check disk space (minimum 1GB required)
            if disk.free < 1024 * 1024 * 1024:  # 1GB
                warnings.append("Low disk space")

            # Check CPU (minimum 1 core required)
            if cpu_count < 1:
                warnings.append("Insufficient CPU resources")

            if warnings:
                result.status = "WARN"
                result.message = f"Resource warnings: {', '.join(warnings)}"

            result.details = {
                "cpu_cores": cpu_count,
                "memory_total": f"{memory.total / (1024**3):.1f}GB",
                "memory_available": f"{memory.available / (1024**3):.1f}GB",
                "memory_percent": memory.percent,
                "disk_total": f"{disk.total / (1024**3):.1f}GB",
                "disk_free": f"{disk.free / (1024**3):.1f}GB",
                "disk_percent": (disk.used / disk.total) * 100,
                "warnings": warnings,
            }

        except ImportError:
            result.status = "WARN"
            result.message = "psutil not available - cannot check system resources"
            result.fix_command = "pip install psutil"
        except Exception as e:
            result.status = "FAIL"
            result.message = f"Failed to validate system resources: {str(e)}"

        return result

    def async_validate_telegram_bot(self) -> ValidationResult:
        """Async validation of Telegram bot functionality."""
        result = ValidationResult(
            name="Telegram Bot Validation",
            status="PASS",
            message="Telegram bot functionality validated",
        )

        async def check_telegram_bot():
            try:
                # Import telegram bot components
                sys.path.insert(0, str(self.project_root))
                from telegram import Update
                from telegram.ext import Application, CommandHandler
                from app.config import Config

                # Validate configuration
                Config.validate()

                # Create application instance (without starting)
                app = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()

                return True, "Telegram bot can be initialized successfully"

            except Exception as e:
                return False, f"Failed to initialize Telegram bot: {str(e)}"

        try:
            # Run async validation
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            success, message = loop.run_until_complete(check_telegram_bot())
            loop.close()

            if not success:
                result.status = "FAIL"
                result.message = message
            else:
                result.message = "Telegram bot initialization successful"

        except Exception as e:
            result.status = "FAIL"
            result.message = f"Telegram bot validation failed: {str(e)}"

        return result

    def run_all_validations(self) -> List[ValidationResult]:
        """Run all validation checks."""
        print("🔍 Starting comprehensive system validation...\n")

        validations = [
            self.validate_python_environment,
            self.validate_project_structure,
            self.validate_dependencies,
            self.validate_configuration,
            self.validate_cli_agents,
            self.validate_socks_support,
            self.validate_network_connectivity,
            self.validate_file_permissions,
            self.validate_system_resources,
            self.async_validate_telegram_bot,
        ]

        for validation in validations:
            try:
                result = validation()
                self._add_result(result)

                # Attempt auto-fix if enabled and status is FAIL
                if self.auto_fix and result.status == "FAIL" and result.fix_command:
                    print(f"🔧 Attempting auto-fix: {result.fix_command}")
                    try:
                        subprocess.run(
                            result.fix_command,
                            shell=True,
                            check=True,
                            capture_output=True,
                        )
                        print("✅ Auto-fix completed")
                    except subprocess.CalledProcessError as e:
                        print(f"❌ Auto-fix failed: {e}")

            except Exception as e:
                error_result = ValidationResult(
                    name=validation.__name__,
                    status="FAIL",
                    message=f"Validation crashed: {str(e)}",
                )
                self._add_result(error_result)

        return self.results

    def generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive validation report."""
        passed = len([r for r in self.results if r.status == "PASS"])
        failed = len([r for r in self.results if r.status == "FAIL"])
        warned = len([r for r in self.results if r.status == "WARN"])
        skipped = len([r for r in self.results if r.status == "SKIP"])

        overall_status = "PASS"
        if failed > 0:
            overall_status = "FAIL"
        elif warned > 0:
            overall_status = "WARN"

        return {
            "timestamp": str(Path().cwd()),
            "overall_status": overall_status,
            "summary": {
                "total": len(self.results),
                "passed": passed,
                "failed": failed,
                "warned": warned,
                "skipped": skipped,
            },
            "system_info": self.system_info,
            "results": [asdict(r) for r in self.results],
            "recommendations": self._generate_recommendations(),
        }

    def _generate_recommendations(self) -> List[str]:
        """Generate recommendations based on validation results."""
        recommendations = []

        failed_results = [r for r in self.results if r.status == "FAIL"]
        warned_results = [r for r in self.results if r.status == "WARN"]

        if failed_results:
            recommendations.append(
                "🚨 CRITICAL ISSUES FOUND - Address these before deployment:"
            )
            for result in failed_results:
                recommendations.append(f"  • {result.message}")
                if result.fix_command:
                    recommendations.append(f"    Fix: {result.fix_command}")

        if warned_results:
            recommendations.append(
                "\n⚠️ WARNINGS - Consider addressing for optimal performance:"
            )
            for result in warned_results:
                recommendations.append(f"  • {result.message}")

        # General recommendations
        recommendations.extend(
            [
                "\n📋 DEPLOYMENT CHECKLIST:",
                "  • All critical checks passed",
                "  • Configuration is valid",
                "  • CLI agents are available (optional for basic functionality)",
                "  • Network connectivity to Telegram API is working",
                "  • File permissions are set correctly",
                "  • System resources are adequate",
            ]
        )

        return recommendations


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate NeuroCrew Lab system requirements"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show detailed output"
    )
    parser.add_argument("--fix", action="store_true", help="Attempt to auto-fix issues")
    parser.add_argument(
        "--check-only", action="store_true", help="Only perform checks (default)"
    )
    parser.add_argument("--output", "-o", help="Output report to file")
    parser.add_argument("--json", action="store_true", help="Output JSON format")

    args = parser.parse_args()

    # Get project root
    project_root = Path(__file__).parent.parent
    if not (project_root / "main.py").exists():
        print("❌ Error: Not in a valid NeuroCrew Lab project directory")
        sys.exit(1)

    # Create validator
    validator = SystemValidator(
        project_root=project_root, verbose=args.verbose, auto_fix=args.fix
    )

    # Run validations
    results = validator.run_all_validations()

    # Generate report
    report = validator.generate_report()

    # Output results
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("\n" + "=" * 60)
        print(f"🏁 VALIDATION COMPLETE: {report['overall_status']}")
        print("=" * 60)
        print(f"Total: {report['summary']['total']}")
        print(f"✅ Passed: {report['summary']['passed']}")
        print(f"❌ Failed: {report['summary']['failed']}")
        print(f"⚠️ Warnings: {report['summary']['warned']}")
        print(f"⏭️ Skipped: {report['summary']['skipped']}")

        if report["recommendations"]:
            print("\n" + "=" * 60)
            print("📋 RECOMMENDATIONS")
            print("=" * 60)
            for rec in report["recommendations"]:
                print(rec)

    # Save report if requested
    if args.output:
        with open(args.output, "w") as f:
            if args.json:
                json.dump(report, f, indent=2)
            else:
                f.write(f"NeuroCrew Lab Validation Report\n")
                f.write(f"Generated: {report['timestamp']}\n")
                f.write(f"Status: {report['overall_status']}\n\n")
                for result in results:
                    f.write(f"{result.status}: {result.name}\n")
                    f.write(f"  {result.message}\n\n")

    # Exit with appropriate code
    exit_code = 0 if report["overall_status"] == "PASS" else 1
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
