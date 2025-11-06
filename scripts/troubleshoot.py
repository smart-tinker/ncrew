#!/usr/bin/env python3
"""
Comprehensive Troubleshooting Framework for NeuroCrew Lab

This script provides diagnostic tools and troubleshooting procedures for common issues:
- System diagnostics and health checks
- Network connectivity troubleshooting
- CLI agent debugging
- Configuration validation and repair
- Performance analysis
- Error log analysis
- Automated recovery procedures

Usage:
    python scripts/troubleshoot.py [--diagnose] [--fix] [--analyze-logs] [--performance]

Options:
    --diagnose          Run comprehensive diagnostics
    --fix              Attempt automatic fixes for common issues
    --analyze-logs     Analyze application logs for issues
    --performance      Run performance analysis
    --component COMP  Debug specific component
    --output FORMAT    Output format: json, text
"""

import os
import sys
import json
import time
import socket
import subprocess
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Callable
from dataclasses import dataclass, asdict
import logging
import re

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class DiagnosticResult:
    """Result of a diagnostic test."""
    component: str
    test_name: str
    status: str  # 'PASS', 'FAIL', 'WARN', 'SKIP'
    message: str
    details: Optional[Dict[str, Any]] = None
    fix_available: bool = False
    fix_command: Optional[str] = None
    auto_fix_available: bool = False


@dataclass
class TroubleshootingReport:
    """Complete troubleshooting report."""
    timestamp: str
    overall_health: str  # 'HEALTHY', 'DEGRADED', 'CRITICAL'
    total_issues: int
    critical_issues: int
    warnings: int
    diagnostics: List[DiagnosticResult]
    recommendations: List[str]
    recovery_actions: List[str]
    performance_metrics: Optional[Dict[str, float]] = None


class Troubleshooter:
    """Comprehensive troubleshooting framework."""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.results: List[DiagnosticResult] = []
        self.start_time = time.time()

        # Define components to diagnose
        self.components = {
            'system': {
                'name': 'System Environment',
                'tests': [
                    self.check_python_version,
                    self.check_virtual_environment,
                    self.check_dependencies,
                    self.check_system_resources,
                    self.check_file_permissions
                ]
            },
            'network': {
                'name': 'Network Connectivity',
                'tests': [
                    self.check_internet_connectivity,
                    self.check_telegram_api_connectivity,
                    self.check_dns_resolution,
                    self.check_proxy_configuration,
                    self.check_ssl_certificates
                ]
            },
            'configuration': {
                'name': 'Configuration',
                'tests': [
                    self.check_env_file,
                    self.check_telegram_token,
                    self.check_cli_agent_paths,
                    self.check_data_directories,
                    self.check_log_configuration
                ]
            },
            'cli_agents': {
                'name': 'CLI Agents',
                'tests': [
                    self.check_agent_availability,
                    self.check_agent_functionality,
                    self.check_agent_performance,
                    self.check_agent_configuration
                ]
            },
            'application': {
                'name': 'Application',
                'tests': [
                    self.check_import_modules,
                    self.check_telegram_bot_initialization,
                    self.check_storage_system,
                    self.check_logging_system
                ]
            }
        }

    def add_result(self, result: DiagnosticResult):
        """Add a diagnostic result."""
        self.results.append(result)
        status_icon = {'PASS': '✅', 'FAIL': '❌', 'WARN': '⚠️', 'SKIP': '⏭️'}.get(result.status, '❓')
        logger.info(f"{status_icon} {result.component}.{result.test_name}: {result.message}")

    def check_python_version(self) -> DiagnosticResult:
        """Check Python version and environment."""
        try:
            import sys
            version_info = sys.version_info

            if version_info < (3, 8):
                return DiagnosticResult(
                    component='system',
                    test_name='python_version',
                    status='FAIL',
                    message=f'Python {version_info.major}.{version_info.minor} is not supported (requires 3.8+)',
                    details={
                        'current_version': f'{version_info.major}.{version_info.minor}.{version_info.micro}',
                        'required_version': '3.8+',
                        'python_path': sys.executable
                    },
                    fix_available=True,
                    fix_command='Install Python 3.8 or higher'
                )

            # Check if in virtual environment
            in_venv = hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)

            if not in_venv and (self.project_root / 'venv').exists():
                return DiagnosticResult(
                    component='system',
                    test_name='python_version',
                    status='WARN',
                    message='Virtual environment exists but not activated',
                    details={
                        'version': f'{version_info.major}.{version_info.minor}.{version_info.micro}',
                        'virtual_env': in_venv,
                        'venv_exists': (self.project_root / 'venv').exists()
                    },
                    fix_available=True,
                    fix_command=f'source {self.project_root}/venv/bin/activate',
                    auto_fix_available=False
                )

            return DiagnosticResult(
                component='system',
                test_name='python_version',
                status='PASS',
                message=f'Python {version_info.major}.{version_info.minor}.{version_info.micro} OK',
                details={
                    'version': f'{version_info.major}.{version_info.minor}.{version_info.micro}',
                    'virtual_env': in_venv,
                    'python_path': sys.executable
                }
            )

        except Exception as e:
            return DiagnosticResult(
                component='system',
                test_name='python_version',
                status='FAIL',
                message=f'Failed to check Python version: {str(e)}'
            )

    def check_virtual_environment(self) -> DiagnosticResult:
        """Check virtual environment status."""
        venv_path = self.project_root / 'venv'

        if not venv_path.exists():
            return DiagnosticResult(
                component='system',
                test_name='virtual_environment',
                status='WARN',
                message='Virtual environment not found',
                details={
                    'venv_path': str(venv_path),
                    'recommended_action': 'Create virtual environment'
                },
                fix_available=True,
                fix_command=f'python -m venv {venv_path}',
                auto_fix_available=True
            )

        # Check if venv is properly structured
        required_dirs = ['bin', 'lib', 'include']
        missing_dirs = []

        for dir_name in required_dirs:
            if not (venv_path / dir_name).exists():
                missing_dirs.append(dir_name)

        if missing_dirs:
            return DiagnosticResult(
                component='system',
                test_name='virtual_environment',
                status='FAIL',
                message=f'Virtual environment incomplete: missing {", ".join(missing_dirs)}',
                details={
                    'venv_path': str(venv_path),
                    'missing_dirs': missing_dirs
                },
                fix_available=True,
                fix_command=f'Recreate virtual environment: rm -rf {venv_path} && python -m venv {venv_path}'
            )

        return DiagnosticResult(
            component='system',
            test_name='virtual_environment',
            status='PASS',
            message='Virtual environment properly configured',
            details={
                'venv_path': str(venv_path),
                'activated': hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)
            }
        )

    def check_dependencies(self) -> DiagnosticResult:
        """Check Python dependencies."""
        req_file = self.project_root / 'requirements.txt'

        if not req_file.exists():
            return DiagnosticResult(
                component='system',
                test_name='dependencies',
                status='FAIL',
                message='requirements.txt not found',
                fix_available=True,
                fix_command='Create requirements.txt with required dependencies'
            )

        try:
            # Parse requirements
            with open(req_file, 'r') as f:
                requirements = [line.strip().split('==')[0].split('>=')[0].split('<=')[0]
                              for line in f if line.strip() and not line.startswith('#')]

            missing_packages = []
            installed_packages = []

            for package in requirements:
                try:
                    __import__(package.replace('-', '_'))
                    installed_packages.append(package)
                except ImportError:
                    missing_packages.append(package)

            if missing_packages:
                return DiagnosticResult(
                    component='system',
                    test_name='dependencies',
                    status='FAIL',
                    message=f'Missing packages: {", ".join(missing_packages)}',
                    details={
                        'required_packages': len(requirements),
                        'installed_packages': len(installed_packages),
                        'missing_packages': missing_packages
                    },
                    fix_available=True,
                    fix_command=f'pip install -r {req_file}',
                    auto_fix_available=True
                )

            return DiagnosticResult(
                component='system',
                test_name='dependencies',
                status='PASS',
                message=f'All {len(installed_packages)} required packages installed',
                details={
                    'installed_packages': installed_packages
                }
            )

        except Exception as e:
            return DiagnosticResult(
                component='system',
                test_name='dependencies',
                status='FAIL',
                message=f'Failed to check dependencies: {str(e)}'
            )

    def check_system_resources(self) -> DiagnosticResult:
        """Check system resources."""
        try:
            import psutil

            # CPU check
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()

            # Memory check
            memory = psutil.virtual_memory()

            # Disk check
            disk = psutil.disk_usage(str(self.project_root))

            warnings = []

            if cpu_percent > 90:
                warnings.append('High CPU usage')
            if memory.percent > 90:
                warnings.append('High memory usage')
            if disk.percent > 90:
                warnings.append('Low disk space')
            if memory.available < 512 * 1024 * 1024:  # 512MB
                warnings.append('Low available memory')

            status = 'WARN' if warnings else 'PASS'

            return DiagnosticResult(
                component='system',
                test_name='system_resources',
                status=status,
                message=f'Resources OK{": " + ", ".join(warnings) if warnings else ""}',
                details={
                    'cpu_percent': cpu_percent,
                    'cpu_count': cpu_count,
                    'memory_percent': memory.percent,
                    'memory_available_gb': memory.available / (1024**3),
                    'disk_percent': disk.percent,
                    'disk_free_gb': disk.free / (1024**3),
                    'warnings': warnings
                }
            )

        except ImportError:
            return DiagnosticResult(
                component='system',
                test_name='system_resources',
                status='SKIP',
                message='psutil not available - cannot check system resources',
                fix_available=True,
                fix_command='pip install psutil'
            )
        except Exception as e:
            return DiagnosticResult(
                component='system',
                test_name='system_resources',
                status='FAIL',
                message=f'Failed to check system resources: {str(e)}'
            )

    def check_file_permissions(self) -> DiagnosticResult:
        """Check file permissions."""
        try:
            permission_issues = []

            # Check .env file permissions
            env_file = self.project_root / '.env'
            if env_file.exists():
                env_stat = env_file.stat()
                if env_stat.st_mode & 0o044:  # World-readable
                    permission_issues.append('.env file is world-readable')

            # Check data directory permissions
            data_dir = self.project_root / 'data'
            if data_dir.exists():
                if not os.access(data_dir, os.W_OK):
                    permission_issues.append('Data directory is not writable')

            if permission_issues:
                return DiagnosticResult(
                    component='system',
                    test_name='file_permissions',
                    status='FAIL',
                    message=f'Permission issues: {", ".join(permission_issues)}',
                    details={
                        'issues': permission_issues
                    },
                    fix_available=True,
                    fix_command='chmod 600 .env && chmod 755 data/'
                )

            return DiagnosticResult(
                component='system',
                test_name='file_permissions',
                status='PASS',
                message='File permissions OK'
            )

        except Exception as e:
            return DiagnosticResult(
                component='system',
                test_name='file_permissions',
                status='FAIL',
                message=f'Failed to check file permissions: {str(e)}'
            )

    def check_internet_connectivity(self) -> DiagnosticResult:
        """Check basic internet connectivity."""
        try:
            # Test DNS resolution
            socket.gethostbyname('google.com')

            # Test HTTP connection
            import urllib.request
            response = urllib.request.urlopen('https://httpbin.org/ip', timeout=10)

            return DiagnosticResult(
                component='network',
                test_name='internet_connectivity',
                status='PASS',
                message='Internet connectivity OK',
                details={
                    'external_ip': response.read().decode().strip()
                }
            )

        except Exception as e:
            return DiagnosticResult(
                component='network',
                test_name='internet_connectivity',
                status='FAIL',
                message=f'Internet connectivity issue: {str(e)}',
                details={
                    'error': str(e)
                }
            )

    def check_telegram_api_connectivity(self) -> DiagnosticResult:
        """Check Telegram API connectivity."""
        try:
            # Test connection to Telegram API
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            result = sock.connect_ex(('api.telegram.org', 443))
            sock.close()

            if result == 0:
                return DiagnosticResult(
                    component='network',
                    test_name='telegram_api_connectivity',
                    status='PASS',
                    message='Telegram API reachable'
                )
            else:
                return DiagnosticResult(
                    component='network',
                    test_name='telegram_api_connectivity',
                    status='FAIL',
                    message=f'Cannot connect to Telegram API (error code: {result})',
                    details={
                        'error_code': result,
                        'host': 'api.telegram.org',
                        'port': 443
                    }
                )

        except Exception as e:
            return DiagnosticResult(
                component='network',
                test_name='telegram_api_connectivity',
                status='FAIL',
                message=f'Telegram API connectivity check failed: {str(e)}'
            )

    def check_dns_resolution(self) -> DiagnosticResult:
        """Check DNS resolution."""
        try:
            hosts = ['api.telegram.org', 'google.com', 'github.com']
            dns_results = {}
            failed_hosts = []

            for host in hosts:
                try:
                    ip_addresses = socket.gethostbyname_ex(host)[2]
                    dns_results[host] = {
                        'status': 'OK',
                        'ip_addresses': ip_addresses
                    }
                except Exception as e:
                    dns_results[host] = {
                        'status': 'FAILED',
                        'error': str(e)
                    }
                    failed_hosts.append(host)

            if failed_hosts:
                return DiagnosticResult(
                    component='network',
                    test_name='dns_resolution',
                    status='FAIL',
                    message=f'DNS resolution failed for: {", ".join(failed_hosts)}',
                    details={
                        'results': dns_results,
                        'failed_hosts': failed_hosts
                    }
                )

            return DiagnosticResult(
                component='network',
                test_name='dns_resolution',
                status='PASS',
                message='DNS resolution OK for all test hosts',
                details={
                    'results': dns_results
                }
            )

        except Exception as e:
            return DiagnosticResult(
                component='network',
                test_name='dns_resolution',
                status='FAIL',
                message=f'DNS resolution check failed: {str(e)}'
            )

    def check_proxy_configuration(self) -> DiagnosticResult:
        """Check proxy configuration."""
        proxy_vars = ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']
        proxy_config = {var: os.getenv(var) for var in proxy_vars if os.getenv(var)}

        if not proxy_config:
            return DiagnosticResult(
                component='network',
                test_name='proxy_configuration',
                status='PASS',
                message='No proxy configuration detected'
            )

        # Validate proxy URL format
        invalid_proxies = []
        for var, url in proxy_config.items():
            if not url.startswith(('http://', 'https://', 'socks4://', 'socks5://')):
                invalid_proxies.append(f'{var}: {url}')

        if invalid_proxies:
            return DiagnosticResult(
                component='network',
                test_name='proxy_configuration',
                status='FAIL',
                message=f'Invalid proxy configuration: {", ".join(invalid_proxies)}',
                details={
                    'proxy_config': proxy_config,
                    'invalid_proxies': invalid_proxies
                },
                fix_available=True,
                fix_command='Fix proxy environment variables format'
            )

        return DiagnosticResult(
            component='network',
            test_name='proxy_configuration',
            status='PASS',
            message='Proxy configuration detected and appears valid',
            details={
                'proxy_config': {k: v for k, v in proxy_config.items() if 'token' not in v.lower()}  # Hide tokens
            }
        )

    def check_ssl_certificates(self) -> DiagnosticResult:
        """Check SSL certificate validation."""
        try:
            import ssl
            import socket

            context = ssl.create_default_context()

            with socket.create_connection(('api.telegram.org', 443), timeout=10) as sock:
                with context.wrap_socket(sock, server_hostname='api.telegram.org') as ssock:
                    cert = ssock.getpeercert()

                    return DiagnosticResult(
                        component='network',
                        test_name='ssl_certificates',
                        status='PASS',
                        message='SSL certificate validation OK',
                        details={
                            'subject': dict(x[0] for x in cert.get('subject', [])),
                            'issuer': dict(x[0] for x in cert.get('issuer', [])),
                            'not_after': cert.get('notAfter'),
                            'version': cert.get('version')
                        }
                    )

        except ssl.SSLCertVerificationError as e:
            return DiagnosticResult(
                component='network',
                test_name='ssl_certificates',
                status='FAIL',
                message=f'SSL certificate verification failed: {str(e)}',
                details={
                    'error': str(e)
                }
            )
        except Exception as e:
            return DiagnosticResult(
                component='network',
                test_name='ssl_certificates',
                status='FAIL',
                message=f'SSL certificate check failed: {str(e)}'
            )

    def check_env_file(self) -> DiagnosticResult:
        """Check .env file."""
        env_file = self.project_root / '.env'

        if not env_file.exists():
            return DiagnosticResult(
                component='configuration',
                test_name='env_file',
                status='FAIL',
                message='.env file not found',
                details={
                    'env_file_path': str(env_file)
                },
                fix_available=True,
                fix_command='cp .env.example .env && edit .env'
            )

        try:
            with open(env_file, 'r') as f:
                env_content = f.read()

            required_vars = ['TELEGRAM_BOT_TOKEN']
            missing_vars = []
            placeholder_vars = []

            for var in required_vars:
                if f"{var}=" not in env_content:
                    missing_vars.append(var)
                elif "your_" in env_content.split(f"{var}=")[1].split('\n')[0].lower():
                    placeholder_vars.append(var)

            if missing_vars:
                return DiagnosticResult(
                    component='configuration',
                    test_name='env_file',
                    status='FAIL',
                    message=f'Missing required variables: {", ".join(missing_vars)}',
                    details={
                        'missing_vars': missing_vars,
                        'placeholder_vars': placeholder_vars
                    }
                )

            if placeholder_vars:
                return DiagnosticResult(
                    component='configuration',
                    test_name='env_file',
                    status='WARN',
                    message=f'Placeholder values detected: {", ".join(placeholder_vars)}',
                    details={
                        'placeholder_vars': placeholder_vars
                    }
                )

            return DiagnosticResult(
                component='configuration',
                test_name='env_file',
                status='PASS',
                message='.env file properly configured'
            )

        except Exception as e:
            return DiagnosticResult(
                component='configuration',
                test_name='env_file',
                status='FAIL',
                message=f'Failed to read .env file: {str(e)}'
            )

    def check_telegram_token(self) -> DiagnosticResult:
        """Check Telegram bot token."""
        try:
            sys.path.insert(0, str(self.project_root))
            from config import Config

            if not Config.TELEGRAM_BOT_TOKEN:
                return DiagnosticResult(
                    component='configuration',
                    test_name='telegram_token',
                    status='FAIL',
                    message='TELEGRAM_BOT_TOKEN not configured'
                )

            if Config.TELEGRAM_BOT_TOKEN == 'your_bot_token_here':
                return DiagnosticResult(
                    component='configuration',
                    test_name='telegram_token',
                    status='FAIL',
                    message'TELEGRAM_BOT_TOKEN is placeholder value'
                )

            if len(Config.TELEGRAM_BOT_TOKEN) < 20:
                return DiagnosticResult(
                    component='configuration',
                    test_name='telegram_token',
                    status='FAIL',
                    message='TELEGRAM_BOT_TOKEN appears invalid (too short)'
                )

            return DiagnosticResult(
                component='configuration',
                test_name='telegram_token',
                status='PASS',
                message='TELEGRAM_BOT_TOKEN properly configured'
            )

        except Exception as e:
            return DiagnosticResult(
                component='configuration',
                test_name='telegram_token',
                status='FAIL',
                message=f'Failed to check Telegram token: {str(e)}'
            )

    def check_cli_agent_paths(self) -> DiagnosticResult:
        """Check CLI agent paths configuration."""
        try:
            sys.path.insert(0, str(self.project_root))
            from config import Config

            agent_paths = Config.CLI_PATHS
            missing_agents = []

            for agent_name, path in agent_paths.items():
                try:
                    # Try to find the command
                    subprocess.run(['which', path], capture_output=True, check=True, timeout=5)
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
                    missing_agents.append(agent_name)

            if missing_agents:
                return DiagnosticResult(
                    component='configuration',
                    test_name='cli_agent_paths',
                    status='WARN',
                    message=f'Some CLI agents not found: {", ".join(missing_agents)}',
                    details={
                        'configured_agents': list(agent_paths.keys()),
                        'missing_agents': missing_agents
                    }
                )

            return DiagnosticResult(
                component='configuration',
                test_name='cli_agent_paths',
                status='PASS',
                message='All CLI agent paths configured'
            )

        except Exception as e:
            return DiagnosticResult(
                component='configuration',
                test_name='cli_agent_paths',
                status='FAIL',
                message=f'Failed to check CLI agent paths: {str(e)}'
            )

    def check_data_directories(self) -> DiagnosticResult:
        """Check data directories."""
        data_dir = self.project_root / 'data'

        if not data_dir.exists():
            return DiagnosticResult(
                component='configuration',
                test_name='data_directories',
                status='WARN',
                message='Data directory not found',
                details={
                    'data_dir': str(data_dir)
                },
                fix_available=True,
                fix_command=f'mkdir -p {data_dir}/logs {data_dir}/conversations',
                auto_fix_available=True
            )

        required_subdirs = ['logs', 'conversations']
        missing_subdirs = []

        for subdir in required_subdirs:
            if not (data_dir / subdir).exists():
                missing_subdirs.append(subdir)

        if missing_subdirs:
            return DiagnosticResult(
                component='configuration',
                test_name='data_directories',
                status='WARN',
                message=f'Missing data subdirectories: {", ".join(missing_subdirs)}',
                details={
                    'missing_subdirs': missing_subdirs
                },
                fix_available=True,
                fix_command=f'mkdir -p {" ".join(str(data_dir / subdir) for subdir in missing_subdirs)}',
                auto_fix_available=True
            )

        # Check permissions
        if not os.access(data_dir, os.W_OK):
            return DiagnosticResult(
                component='configuration',
                test_name='data_directories',
                status='FAIL',
                message='Data directory is not writable',
                fix_available=True,
                fix_command=f'chmod 755 {data_dir}'
            )

        return DiagnosticResult(
            component='configuration',
            test_name='data_directories',
            status='PASS',
            message='Data directories properly configured'
        )

    def check_log_configuration(self) -> DiagnosticResult:
        """Check logging configuration."""
        log_dir = self.project_root / 'data' / 'logs'

        if not log_dir.exists():
            return DiagnosticResult(
                component='configuration',
                test_name='log_configuration',
                status='WARN',
                message='Log directory not found',
                fix_available=True,
                fix_command=f'mkdir -p {log_dir}',
                auto_fix_available=True
            )

        # Check if we can write to log directory
        test_log = log_dir / 'test.log'
        try:
            with open(test_log, 'w') as f:
                f.write('test')
            test_log.unlink()

            return DiagnosticResult(
                component='configuration',
                test_name='log_configuration',
                status='PASS',
                message='Log configuration OK'
            )

        except Exception as e:
            return DiagnosticResult(
                component='configuration',
                test_name='log_configuration',
                status='FAIL',
                message=f'Cannot write to log directory: {str(e)}',
                fix_available=True,
                fix_command=f'chmod 755 {log_dir}'
            )

    def check_agent_availability(self) -> DiagnosticResult:
        """Check CLI agent availability."""
        cli_agents = {
            'qwen': ['qwen', 'qwen-code'],
            'gemini': ['gemini', 'gemini-cli'],
            'claude': ['claude', 'claude-code'],
            'opencode': ['opencode'],
            'codex': ['codex']
        }

        available_agents = {}
        missing_agents = []

        for agent_name, commands in cli_agents.items():
            agent_found = False
            working_command = None

            for cmd in commands:
                try:
                    subprocess.run(['which', cmd], capture_output=True, check=True, timeout=5)
                    agent_found = True
                    working_command = cmd
                    break
                except:
                    continue

            if agent_found:
                available_agents[agent_name] = working_command
            else:
                missing_agents.append(agent_name)

        if missing_agents:
            return DiagnosticResult(
                component='cli_agents',
                test_name='agent_availability',
                status='WARN',
                messagef'Some CLI agents not available: {", ".join(missing_agents)}',
                details={
                    'available_agents': available_agents,
                    'missing_agents': missing_agents
                }
            )

        return DiagnosticResult(
            component='cli_agents',
            test_name='agent_availability',
            status='PASS',
            message=f'All {len(available_agents)} CLI agents available',
            details={
                'available_agents': available_agents
            }
        )

    def check_agent_functionality(self) -> DiagnosticResult:
        """Check CLI agent functionality."""
        cli_agents = ['qwen', 'gemini', 'claude', 'opencode', 'codex']
        working_agents = []
        failed_agents = []

        for agent in cli_agents:
            try:
                # Try to find working command
                working_command = None
                for cmd in [agent, f'{agent}-code', f'{agent}-cli']:
                    try:
                        subprocess.run(['which', cmd], capture_output=True, check=True, timeout=5)
                        working_command = cmd
                        break
                    except:
                        continue

                if not working_command:
                    failed_agents.append(f'{agent} (not found)')
                    continue

                # Test basic functionality
                result = subprocess.run([working_command, '--help'], capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    working_agents.append(agent)
                else:
                    failed_agents.append(f'{agent} (help command failed)')

            except subprocess.TimeoutExpired:
                failed_agents.append(f'{agent} (timeout)')
            except Exception:
                failed_agents.append(f'{agent} (error)')

        if failed_agents:
            return DiagnosticResult(
                component='cli_agents',
                test_name='agent_functionality',
                status='WARN',
                messagef'Some CLI agents have issues: {", ".join(failed_agents)}',
                details={
                    'working_agents': working_agents,
                    'failed_agents': failed_agents
                }
            )

        return DiagnosticResult(
            component='cli_agents',
            test_name='agent_functionality',
            status='PASS',
            messagef'All CLI agents working properly',
            details={
                'working_agents': working_agents
            }
        )

    def check_agent_performance(self) -> DiagnosticResult:
        """Check CLI agent performance."""
        try:
            # Test with a simple agent
            test_commands = [
                ('qwen', 'echo "test" | qwen-code --help' if os.system('which qwen-code >/dev/null 2>&1') == 0 else 'qwen --help'),
                ('gemini', 'gemini --help' if os.system('which gemini >/dev/null 2>&1') == 0 else 'gemini-cli --help'),
            ]

            performance_results = {}
            slow_agents = []

            for agent_name, command in test_commands:
                try:
                    start_time = time.time()
                    result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=15)
                    duration = time.time() - start_time

                    performance_results[agent_name] = {
                        'duration': duration,
                        'success': result.returncode == 0
                    }

                    if duration > 5:  # More than 5 seconds is considered slow
                        slow_agents.append(agent_name)

                except Exception:
                    performance_results[agent_name] = {
                        'duration': -1,
                        'success': False
                    }

            if slow_agents:
                return DiagnosticResult(
                    component='cli_agents',
                    test_name='agent_performance',
                    status='WARN',
                    messagef'Some agents are slow: {", ".join(slow_agents)}',
                    details={
                        'performance_results': performance_results,
                        'slow_agents': slow_agents
                    }
                )

            return DiagnosticResult(
                component='cli_agents',
                test_name='agent_performance',
                status='PASS',
                message='CLI agents performing well',
                details={
                    'performance_results': performance_results
                }
            )

        except Exception as e:
            return DiagnosticResult(
                component='cli_agents',
                test_name='agent_performance',
                status='FAIL',
                message=f'Agent performance check failed: {str(e)}'
            )

    def check_agent_configuration(self) -> DiagnosticResult:
        """Check agent configuration consistency."""
        try:
            sys.path.insert(0, str(self.project_root))
            from config import Config

            cli_paths = Config.CLI_PATHS
            configured_agents = list(cli_paths.keys())
            expected_agents = ['qwen', 'gemini', 'claude', 'opencode', 'codex']

            missing_configs = set(expected_agents) - set(configured_agents)
            extra_configs = set(configured_agents) - set(expected_agents)

            if missing_configs:
                return DiagnosticResult(
                    component='cli_agents',
                    test_name='agent_configuration',
                    status='WARN',
                    messagef'Missing agent configurations: {", ".join(missing_configs)}',
                    details={
                        'configured_agents': configured_agents,
                        'expected_agents': expected_agents,
                        'missing_configs': list(missing_configs)
                    }
                )

            return DiagnosticResult(
                component='cli_agents',
                test_name='agent_configuration',
                status='PASS',
                message='Agent configuration consistent',
                details={
                    'configured_agents': configured_agents
                }
            )

        except Exception as e:
            return DiagnosticResult(
                component='cli_agents',
                test_name='agent_configuration',
                status='FAIL',
                messagef'Agent configuration check failed: {str(e)}'
            )

    def check_import_modules(self) -> DiagnosticResult:
        """Check if core modules can be imported."""
        try:
            modules_to_test = [
                'telegram_bot',
                'ncrew',
                'config',
                'utils.logger',
                'utils.formatters',
                'connectors.base',
                'storage.file_storage'
            ]

            import_results = {}
            failed_imports = []

            for module_name in modules_to_test:
                try:
                    sys.path.insert(0, str(self.project_root))
                    __import__(module_name)
                    import_results[module_name] = 'SUCCESS'
                except Exception as e:
                    import_results[module_name] = f'FAILED: {str(e)}'
                    failed_imports.append(module_name)

            if failed_imports:
                return DiagnosticResult(
                    component='application',
                    test_name='import_modules',
                    status='FAIL',
                    messagef'Failed to import modules: {", ".join(failed_imports)}',
                    details={
                        'import_results': import_results,
                        'failed_imports': failed_imports
                    }
                )

            return DiagnosticResult(
                component='application',
                test_name='import_modules',
                status='PASS',
                message='All core modules imported successfully',
                details={
                    'import_results': import_results
                }
            )

        except Exception as e:
            return DiagnosticResult(
                component='application',
                test_name='import_modules',
                status='FAIL',
                messagef'Module import test failed: {str(e)}'
            )

    def check_telegram_bot_initialization(self) -> DiagnosticResult:
        """Check Telegram bot initialization."""
        try:
            sys.path.insert(0, str(self.project_root))
            from config import Config

            # Validate configuration first
            Config.validate()

            # Try to create telegram bot application
            from telegram import Update
            from telegram.ext import Application

            app = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()

            return DiagnosticResult(
                component='application',
                test_name='telegram_bot_initialization',
                status='PASS',
                message='Telegram bot can be initialized successfully'
            )

        except Exception as e:
            return DiagnosticResult(
                component='application',
                test_name='telegram_bot_initialization',
                status='FAIL',
                messagef'Telegram bot initialization failed: {str(e)}',
                details={
                    'error': str(e)
                }
            )

    def check_storage_system(self) -> DiagnosticResult:
        """Check storage system functionality."""
        try:
            sys.path.insert(0, str(self.project_root))
            from storage.file_storage import FileStorage

            # Create test storage instance
            test_data_dir = self.project_root / 'data' / 'test_storage'
            test_data_dir.mkdir(exist_ok=True)

            storage = FileStorage(str(test_data_dir))

            # Test basic operations
            test_chat_id = 'test_chat_123'
            test_message = {'role': 'user', 'content': 'Hello, world!', 'timestamp': datetime.now().isoformat()}

            # Save test message
            storage.save_message(test_chat_id, test_message)

            # Load messages
            loaded_messages = storage.load_messages(test_chat_id)

            # Cleanup
            import shutil
            shutil.rmtree(test_data_dir)

            if not loaded_messages:
                return DiagnosticResult(
                    component='application',
                    test_name='storage_system',
                    status='FAIL',
                    message='Storage system - failed to load saved message'
                )

            return DiagnosticResult(
                component='application',
                test_name='storage_system',
                status='PASS',
                message='Storage system working correctly',
                details={
                    'test_chat_id': test_chat_id,
                    'messages_loaded': len(loaded_messages)
                }
            )

        except Exception as e:
            return DiagnosticResult(
                component='application',
                test_name='storage_system',
                status='FAIL',
                messagef'Storage system test failed: {str(e)}',
                details={
                    'error': str(e)
                }
            )

    def check_logging_system(self) -> DiagnosticResult:
        """Check logging system."""
        try:
            sys.path.insert(0, str(self.project_root))
            from utils.logger import setup_logger

            # Test logger creation
            test_logger = setup_logger('test_logger', 'INFO')

            # Test logging
            test_logger.info('Test log message')

            return DiagnosticResult(
                component='application',
                test_name='logging_system',
                status='PASS',
                message='Logging system working correctly'
            )

        except Exception as e:
            return DiagnosticResult(
                component='application',
                test_name='logging_system',
                status='FAIL',
                messagef'Logging system test failed: {str(e)}',
                details={
                    'error': str(e)
                }
            )

    def run_diagnostics(self, component: Optional[str] = None) -> List[DiagnosticResult]:
        """Run comprehensive diagnostics."""
        logger.info("Starting comprehensive diagnostics...")

        self.results = []

        if component:
            if component not in self.components:
                raise ValueError(f"Unknown component: {component}")

            components_to_test = {component: self.components[component]}
        else:
            components_to_test = self.components

        # Run tests for each component
        for comp_name, comp_info in components_to_test.items():
            logger.info(f"Testing {comp_info['name']}...")

            for test_func in comp_info['tests']:
                try:
                    result = test_func()
                    self.add_result(result)
                except Exception as e:
                    error_result = DiagnosticResult(
                        component=comp_name,
                        test_name=test_func.__name__,
                        status='FAIL',
                        message=f'Test crashed: {str(e)}'
                    )
                    self.add_result(error_result)

        return self.results

    def analyze_logs(self, log_file: Optional[Path] = None) -> Dict[str, Any]:
        """Analyze application logs for issues."""
        if not log_file:
            log_file = self.project_root / 'data' / 'logs' / 'neurocrew.log'

        if not log_file.exists():
            return {
                'status': 'NO_LOGS',
                'message': 'Log file not found',
                'log_file': str(log_file)
            }

        try:
            # Read recent log entries (last 1000 lines)
            with open(log_file, 'r') as f:
                lines = f.readlines()[-1000:]

            # Analyze log patterns
            error_count = len([line for line in lines if 'ERROR' in line])
            warning_count = len([line for line in lines if 'WARNING' in line])
            exception_count = len([line for line in lines if 'Exception' in line or 'Traceback' in line])

            # Find common error patterns
            error_patterns = {
                'proxy_errors': len([line for line in lines if 'proxy' in line.lower() and 'error' in line.lower()]),
                'timeout_errors': len([line for line in lines if 'timeout' in line.lower()]),
                'connection_errors': len([line for line in lines if 'connection' in line.lower() and 'error' in line.lower()]),
                'agent_errors': len([line for line in lines if 'agent' in line.lower() and 'error' in line.lower()]),
                'telegram_errors': len([line for line in lines if 'telegram' in line.lower() and 'error' in line.lower()])
            }

            # Extract recent exceptions
            recent_exceptions = []
            for i, line in enumerate(lines):
                if 'Traceback' in line:
                    exception_lines = []
                    j = i
                    while j < len(lines) and not lines[j].strip().startswith('---'):
                        exception_lines.append(lines[j].strip())
                        j += 1
                        if j - i > 20:  # Limit exception length
                            break
                    if exception_lines:
                        recent_exceptions.append('\n'.join(exception_lines))

            return {
                'status': 'ANALYZED',
                'log_file': str(log_file),
                'total_lines': len(lines),
                'error_count': error_count,
                'warning_count': warning_count,
                'exception_count': exception_count,
                'error_patterns': error_patterns,
                'recent_exceptions': recent_exceptions[-5:],  # Last 5 exceptions
                'health_score': max(0, 100 - (error_count * 2) - (warning_count * 1) - (exception_count * 5))
            }

        except Exception as e:
            return {
                'status': 'ERROR',
                'message': f'Failed to analyze logs: {str(e)}',
                'log_file': str(log_file)
            }

    def generate_report(self, log_analysis: Optional[Dict] = None) -> TroubleshootingReport:
        """Generate comprehensive troubleshooting report."""
        total_issues = len([r for r in self.results if r.status == 'FAIL'])
        critical_issues = total_issues  # All FAIL are critical for troubleshooting
        warnings = len([r for r in self.results if r.status == 'WARN'])

        # Determine overall health
        if total_issues == 0:
            overall_health = 'HEALTHY'
        elif total_issues <= 2:
            overall_health = 'DEGRADED'
        else:
            overall_health = 'CRITICAL'

        # Generate recommendations
        recommendations = self._generate_recommendations()

        # Generate recovery actions
        recovery_actions = self._generate_recovery_actions()

        return TroubleshootingReport(
            timestamp=datetime.now().isoformat(),
            overall_health=overall_health,
            total_issues=total_issues,
            critical_issues=critical_issues,
            warnings=warnings,
            diagnostics=self.results,
            recommendations=recommendations,
            recovery_actions=recovery_actions
        )

    def _generate_recommendations(self) -> List[str]:
        """Generate troubleshooting recommendations."""
        recommendations = []

        # Group issues by component
        component_issues = {}
        for result in self.results:
            if result.status == 'FAIL':
                if result.component not in component_issues:
                    component_issues[result.component] = []
                component_issues[result.component].append(result)

        # Component-specific recommendations
        if 'system' in component_issues:
            recommendations.extend([
                "🖥️ SYSTEM ISSUES:",
                "  • Install Python 3.8+ if using older version",
                "  • Create and activate virtual environment",
                "  • Install missing dependencies: pip install -r requirements.txt",
                "  • Fix file permissions: chmod 600 .env && chmod 755 data/"
            ])

        if 'network' in component_issues:
            recommendations.extend([
                "🌐 NETWORK ISSUES:",
                "  • Check internet connectivity and DNS settings",
                "  • Verify proxy configuration format and connectivity",
                "  • Test Telegram API connectivity manually",
                "  • Check SSL certificate validity and system time"
            ])

        if 'configuration' in component_issues:
            recommendations.extend([
                "⚙️ CONFIGURATION ISSUES:",
                "  • Create .env file from .env.example template",
                "  • Configure valid Telegram bot token",
                "  • Set up CLI agent paths and verify availability",
                "  • Create required data directories"
            ])

        if 'cli_agents' in component_issues:
            recommendations.extend([
                "🤖 CLI AGENT ISSUES:",
                "  • Install missing CLI tools according to documentation",
                "  • Add CLI tools to system PATH",
                "  • Test agent functionality manually",
                "  • Check agent documentation for setup requirements"
            ])

        if 'application' in component_issues:
            recommendations.extend([
                "📱 APPLICATION ISSUES:",
                "  • Check import paths and Python path configuration",
                "  • Verify Telegram bot token and API connectivity",
                "  • Test storage system permissions and disk space",
                "  • Check logging configuration and directory permissions"
            ])

        # General recommendations
        if not component_issues:
            recommendations.append("✅ No critical issues found - system is healthy")

        recommendations.extend([
            "\n🔧 GENERAL TROUBLESHOOTING:",
            "  • Run individual component tests for detailed diagnosis",
            "  • Check application logs for specific error messages",
            "  • Test network connectivity to Telegram API endpoints",
            "  • Verify all environment variables are properly set",
            "  • Ensure all dependencies are installed and compatible"
        ])

        return recommendations

    def _generate_recovery_actions(self) -> List[str]:
        """Generate automated recovery actions."""
        recovery_actions = []

        # Check which issues can be auto-fixed
        auto_fixable = [r for r in self.results if r.status == 'FAIL' and r.auto_fix_available]

        if auto_fixable:
            recovery_actions.extend([
                "🔧 AUTOMATED RECOVERY AVAILABLE:",
                f"  • {len(auto_fixable)} issues can be automatically fixed"
            ])

        # Specific recovery commands
        recovery_commands = []
        for result in self.results:
            if result.status == 'FAIL' and result.fix_command:
                recovery_commands.append(f"  • {result.fix_command}")

        if recovery_commands:
            recovery_actions.extend([
                "💡 RECOVERY COMMANDS:"
            ] + recovery_commands[:5])  # Limit to top 5

        # Manual recovery steps
        recovery_actions.extend([
            "\n🔍 MANUAL RECOVERY STEPS:",
            "  • Review diagnostic results for specific error details",
            "  • Check application logs in data/logs/neurocrew.log",
            "  • Test Telegram bot token validity with BotFather",
            "  • Verify CLI agent installation and PATH configuration",
            "  • Check system resources and disk space availability"
        ])

        return recovery_actions

    def attempt_auto_fixes(self) -> List[str]:
        """Attempt automatic fixes for common issues."""
        fixes_applied = []

        for result in self.results:
            if result.status == 'FAIL' and result.auto_fix_available and result.fix_command:
                try:
                    logger.info(f"Attempting auto-fix: {result.fix_command}")

                    # Run the fix command
                    if isinstance(result.fix_command, str):
                        if result.fix_command.startswith('mkdir'):
                            os.makedirs(result.fix_command.split()[-1], exist_ok=True)
                            fixes_applied.append(f"Created directory: {result.fix_command.split()[-1]}")
                        elif result.fix_command.startswith('chmod'):
                            # Basic chmod support
                            parts = result.fix_command.split()
                            if len(parts) == 3:
                                mode = int(parts[1], 8)
                                file_path = Path(parts[2])
                                if file_path.exists():
                                    file_path.chmod(mode)
                                    fixes_applied.append(f"Fixed permissions for: {file_path}")

                except Exception as e:
                    logger.error(f"Auto-fix failed: {str(e)}")

        return fixes_applied


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Comprehensive troubleshooting for NeuroCrew Lab")
    parser.add_argument('--diagnose', action='store_true', help='Run comprehensive diagnostics')
    parser.add_argument('--fix', action='store_true', help='Attempt automatic fixes')
    parser.add_argument('--analyze-logs', action='store_true', help='Analyze application logs')
    parser.add_argument('--performance', action='store_true', help='Run performance analysis')
    parser.add_argument('--component', help='Debug specific component')
    parser.add_argument('--output', choices=['json', 'text'], default='text', help='Output format')
    parser.add_argument('--log-file', help='Specific log file to analyze')

    args = parser.parse_args()

    # Get project root
    project_root = Path(__file__).parent.parent
    if not (project_root / "main.py").exists():
        print("❌ Error: Not in a valid NeuroCrew Lab project directory")
        sys.exit(1)

    # Create troubleshooter
    troubleshooter = Troubleshooter(project_root)

    print("🔧 Starting NeuroCrew Lab Troubleshooting Framework\n")

    try:
        # Run diagnostics
        if args.diagnose or not any([args.analyze_logs, args.performance]):
            results = troubleshooter.run_diagnostics(args.component)
            print(f"📊 Completed {len(results)} diagnostic tests\n")

        # Attempt fixes if requested
        if args.fix:
            fixes_applied = troubleshooter.attempt_auto_fixes()
            if fixes_applied:
                print(f"🔧 Applied {len(fixes_applied)} automatic fixes:")
                for fix in fixes_applied:
                    print(f"  • {fix}")
                print()

        # Analyze logs if requested
        log_analysis = None
        if args.analyze_logs:
            log_file = Path(args.log_file) if args.log_file else None
            log_analysis = troubleshooter.analyze_logs(log_file)

            if log_analysis['status'] == 'ANALYZED':
                print(f"📋 Log Analysis Results:")
                print(f"  • Total lines: {log_analysis['total_lines']}")
                print(f"  • Errors: {log_analysis['error_count']}")
                print(f"  • Warnings: {log_analysis['warning_count']}")
                print(f"  • Exceptions: {log_analysis['exception_count']}")
                print(f"  • Health score: {log_analysis['health_score']}/100")
                print()

        # Performance analysis placeholder
        if args.performance:
            print("⚡ Performance analysis not yet implemented")

        # Generate report
        report = troubleshooter.generate_report(log_analysis)

        # Output results
        if args.output == 'json':
            print(json.dumps(asdict(report), indent=2, default=str))
        else:
            print("="*60)
            print(f"🏥 TROUBLESHOOTING REPORT: {report.overall_health}")
            print("="*60)
            print(f"Critical Issues: {report.critical_issues}")
            print(f"Warnings: {report.warnings}")
            print(f"Diagnostics Run: {len(report.diagnostics)}")

            # Component breakdown
            component_status = {}
            for result in report.diagnostics:
                if result.component not in component_status:
                    component_status[result.component] = {'PASS': 0, 'FAIL': 0, 'WARN': 0, 'SKIP': 0}
                component_status[result.component][result.status] += 1

            print(f"\n📊 Component Status:")
            for component, status in component_status.items():
                total = sum(status.values())
                passed = status['PASS']
                icon = "✅" if passed == total else "❌" if status['FAIL'] > 0 else "⚠️"
                print(f"  {icon} {component}: {passed}/{total} tests passed")

            # Critical issues
            critical_results = [r for r in report.diagnostics if r.status == 'FAIL']
            if critical_results:
                print(f"\n🚨 Critical Issues ({len(critical_results)}):")
                for result in critical_results:
                    print(f"  • {result.component}.{result.test_name}: {result.message}")
                    if result.fix_command:
                        print(f"    Fix: {result.fix_command}")

            # Recommendations
            if report.recommendations:
                print(f"\n📋 Recommendations:")
                for rec in report.recommendations:
                    print(rec)

            # Recovery actions
            if report.recovery_actions:
                print(f"\n🔧 Recovery Actions:")
                for action in report.recovery_actions:
                    print(action)

        # Exit with appropriate code
        exit_code = 0 if report.overall_health == 'HEALTHY' else 1 if report.overall_health == 'DEGRADED' else 2
        sys.exit(exit_code)

    except KeyboardInterrupt:
        print("\n❌ Troubleshooting interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Troubleshooting failed: {str(e)}")
        sys.exit(1)


if __name__ == '__main__':
    main()