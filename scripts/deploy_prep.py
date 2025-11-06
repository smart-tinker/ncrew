#!/usr/bin/env python3
"""
Deployment Preparation and Monitoring Setup for NeuroCrew Lab

This script prepares the application for deployment and sets up monitoring infrastructure:
- Environment-specific configuration validation
- Deployment package creation
- Logging infrastructure setup
- Monitoring and alerting configuration
- Health check systems
- Service management configuration

Usage:
    python scripts/deploy_prep.py --env ENVIRONMENT [--setup-monitoring] [--create-package]

Options:
    --env ENVIRONMENT      Target environment (dev, staging, prod)
    --setup-monitoring     Setup monitoring and logging infrastructure
    --create-package       Create deployment package
    --check-only           Only validate readiness, don't make changes
    --output-dir DIR       Output directory for deployment artifacts
"""

import os
import sys
import json
import yaml
import shutil
import tarfile
import zipfile
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import logging

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
class DeploymentConfig:
    """Deployment configuration for different environments."""
    environment: str
    debug: bool
    log_level: str
    max_workers: int
    timeout_seconds: int
    health_check_interval: int
    metrics_enabled: bool
    monitoring_enabled: bool
    backup_enabled: bool
    ssl_enabled: bool
    database_config: Optional[Dict[str, Any]] = None
    redis_config: Optional[Dict[str, Any]] = None


@dataclass
class DeploymentReadiness:
    """Deployment readiness assessment."""
    ready: bool
    issues: List[str]
    warnings: List[str]
    recommendations: List[str]
    environment_config: Optional[DeploymentConfig] = None


class DeploymentPreparer:
    """Deployment preparation and monitoring setup."""

    def __init__(self, project_root: Path, environment: str):
        self.project_root = project_root
        self.environment = environment.lower()
        self.output_dir = project_root / "deployments" / self.environment
        self.config_dir = project_root / "config" / self.environment
        self.monitoring_dir = project_root / "monitoring"

        # Ensure directories exist
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.monitoring_dir.mkdir(parents=True, exist_ok=True)

        # Environment-specific configurations
        self.environment_configs = {
            'dev': DeploymentConfig(
                environment='dev',
                debug=True,
                log_level='DEBUG',
                max_workers=2,
                timeout_seconds=60,
                health_check_interval=30,
                metrics_enabled=True,
                monitoring_enabled=False,
                backup_enabled=False,
                ssl_enabled=False
            ),
            'staging': DeploymentConfig(
                environment='staging',
                debug=True,
                log_level='INFO',
                max_workers=4,
                timeout_seconds=120,
                health_check_interval=60,
                metrics_enabled=True,
                monitoring_enabled=True,
                backup_enabled=True,
                ssl_enabled=True
            ),
            'prod': DeploymentConfig(
                environment='prod',
                debug=False,
                log_level='WARNING',
                max_workers=8,
                timeout_seconds=180,
                health_check_interval=30,
                metrics_enabled=True,
                monitoring_enabled=True,
                backup_enabled=True,
                ssl_enabled=True
            )
        }

        if self.environment not in self.environment_configs:
            raise ValueError(f"Unsupported environment: {self.environment}")

    def validate_readiness(self) -> DeploymentReadiness:
        """Validate deployment readiness."""
        logger.info(f"Validating deployment readiness for {self.environment} environment...")

        issues = []
        warnings = []
        recommendations = []

        # 1. Check environment configuration
        env_config = self.environment_configs[self.environment]

        # 2. Validate project structure
        required_files = [
            'main.py',
            'config.py',
            'requirements.txt',
            '.env'
        ]

        missing_files = []
        for file_path in required_files:
            if not (self.project_root / file_path).exists():
                missing_files.append(file_path)

        if missing_files:
            issues.append(f"Missing required files: {', '.join(missing_files)}")

        # 3. Validate .env configuration
        env_file = self.project_root / '.env'
        if env_file.exists():
            with open(env_file, 'r') as f:
                env_content = f.read()

            required_vars = ['TELEGRAM_BOT_TOKEN']
            for var in required_vars:
                if f"{var}=" not in env_content:
                    issues.append(f"Missing required environment variable: {var}")
                elif "your_" in env_content.split(f"{var}=")[1].split('\n')[0].lower():
                    warnings.append(f"Placeholder value detected for {var}")

        # 4. Check dependencies
        req_file = self.project_root / 'requirements.txt'
        if req_file.exists():
            try:
                # Try to import dependencies
                with open(req_file, 'r') as f:
                    requirements = [line.strip().split('==')[0] for line in f if line.strip() and not line.startswith('#')]

                missing_packages = []
                for package in requirements:
                    try:
                        __import__(package.replace('-', '_'))
                    except ImportError:
                        missing_packages.append(package)

                if missing_packages:
                    issues.append(f"Missing Python packages: {', '.join(missing_packages)}")

            except Exception as e:
                warnings.append(f"Could not validate dependencies: {str(e)}")

        # 5. Environment-specific checks
        if self.environment == 'prod':
            # Production-specific validations
            if env_config.debug:
                warnings.append("Debug mode enabled in production")

            if not env_config.ssl_enabled:
                issues.append("SSL must be enabled in production")

            if env_config.log_level in ['DEBUG', 'INFO']:
                warnings.append("Consider using WARNING or ERROR log level in production")

        # 6. Check CLI agents availability
        cli_agents = ['qwen', 'gemini', 'claude', 'opencode', 'codex']
        missing_agents = []
        for agent in cli_agents:
            try:
                subprocess.run(['which', agent], capture_output=True, check=True, timeout=5)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                missing_agents.append(agent)

        if missing_agents:
            warnings.append(f"Some CLI agents not available: {', '.join(missing_agents)}")

        # 7. Check directories and permissions
        data_dir = self.project_root / 'data'
        if not data_dir.exists():
            warnings.append("Data directory does not exist")
        else:
            if not os.access(data_dir, os.W_OK):
                issues.append("Data directory is not writable")

        # 8. Generate recommendations
        if not issues and not warnings:
            recommendations.append("✅ System is ready for deployment")
        else:
            recommendations.extend([
                "📋 DEPLOYMENT CHECKLIST:",
                "  • Address all critical issues before deployment",
                "  • Review and address warnings for optimal performance",
                "  • Test all functionality in staging before production deployment",
                "  • Have rollback plan ready",
                "  • Monitor system health after deployment"
            ])

        return DeploymentReadiness(
            ready=len(issues) == 0,
            issues=issues,
            warnings=warnings,
            recommendations=recommendations,
            environment_config=env_config
        )

    def create_environment_config(self) -> Path:
        """Create environment-specific configuration file."""
        config_path = self.config_dir / 'deployment_config.py'

        env_config = self.environment_configs[self.environment]

        config_content = f'''"""
Deployment configuration for {self.environment.upper()} environment.

Generated automatically by deploy_prep.py on {datetime.now().isoformat()}
"""

import os
from pathlib import Path

# Environment settings
ENVIRONMENT = "{env_config.environment}"
DEBUG = {env_config.debug}
LOG_LEVEL = "{env_config.log_level}"

# Performance settings
MAX_WORKERS = {env_config.max_workers}
TIMEOUT_SECONDS = {env_config.timeout_seconds}
HEALTH_CHECK_INTERVAL = {env_config.health_check_interval}

# Feature flags
METRICS_ENABLED = {env_config.metrics_enabled}
MONITORING_ENABLED = {env_config.monitoring_enabled}
BACKUP_ENABLED = {env_config.backup_enabled}
SSL_ENABLED = {env_config.ssl_enabled}

# Paths
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "data" / "logs"
CONFIG_DIR = BASE_DIR / "config" / "{self.environment}"

# Agent configuration
CLI_AGENTS = {{
    "qwen": os.getenv("QWEN_CLI_PATH", "qwen"),
    "gemini": os.getenv("GEMINI_CLI_PATH", "gemini"),
    "claude": os.getenv("CLAUDE_CLI_PATH", "claude"),
    "opencode": os.getenv("OPENCODE_CLI_PATH", "opencode"),
    "codex": os.getenv("CODEX_CLI_PATH", "codex")
}}

# Telegram configuration
TELEGRAM_CONFIG = {{
    "max_message_length": 4096,
    "message_split_threshold": 4000,
    "rate_limit": 30,  # messages per minute
    "timeout": 30
}}

# Logging configuration
LOGGING_CONFIG = {{
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {{
        "standard": {{
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S"
        }},
        "json": {{
            "format": "%(asctime)s %(name)s %(levelname)s %(message)s",
            "class": "pythonjsonlogger.jsonlogger.JsonFormatter"
        }}
    }},
    "handlers": {{
        "console": {{
            "level": "{env_config.log_level}",
            "class": "logging.StreamHandler",
            "formatter": "standard"
        }},
        "file": {{
            "level": "{env_config.log_level}",
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "json",
            "filename": str(LOG_DIR / "neurocrew.log"),
            "maxBytes": 10485760,  # 10MB
            "backupCount": 5
        }}
    }},
    "loggers": {{
        "": {{
            "handlers": ["console", "file"],
            "level": "{env_config.log_level}"
        }},
        "telegram_bot": {{
            "handlers": ["console", "file"],
            "level": "{env_config.log_level}",
            "propagate": False
        }},
        "ncrew": {{
            "handlers": ["console", "file"],
            "level": "{env_config.log_level}",
            "propagate": False
        }}
    }}
}}
'''

        with open(config_path, 'w') as f:
            f.write(config_content)

        logger.info(f"Environment configuration created: {config_path}")
        return config_path

    def setup_logging_infrastructure(self) -> List[Path]:
        """Setup logging infrastructure."""
        logger.info("Setting up logging infrastructure...")

        created_files = []

        # Create log directories
        log_dir = self.project_root / 'data' / 'logs'
        log_dir.mkdir(parents=True, exist_ok=True)

        # Create logrotate configuration
        logrotate_config = self.monitoring_dir / 'logrotate.conf'
        logrotate_content = f"""# Logrotate configuration for NeuroCrew Lab
{log_dir}/*.log {{
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 644 $USER $USER
    postrotate
        # Send signal to reload logs if running as daemon
        # kill -USR1 $(cat /var/run/neurocrew.pid) 2>/dev/null || true
    endscript
}}
"""
        with open(logrotate_config, 'w') as f:
            f.write(logrotate_content)
        created_files.append(logrotate_config)

        # Create systemd service file (if production)
        if self.environment == 'prod':
            service_file = self.monitoring_dir / 'neurocrew.service'
            service_content = f"""[Unit]
Description=NeuroCrew Lab Service
After=network.target

[Service]
Type=simple
User={os.getenv('USER', 'neurocrew')}
WorkingDirectory={self.project_root}
Environment=PATH={self.project_root}/venv/bin
ExecStart={self.project_root}/venv/bin/python {self.project_root}/main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=neurocrew

# Security settings
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths={self.project_root}/data

[Install]
WantedBy=multi-user.target
"""
            with open(service_file, 'w') as f:
                f.write(service_content)
            created_files.append(service_file)

        logger.info(f"Logging infrastructure setup complete. Files created: {len(created_files)}")
        return created_files

    def setup_monitoring(self) -> List[Path]:
        """Setup monitoring and alerting configuration."""
        logger.info("Setting up monitoring infrastructure...")

        created_files = []

        # Create Prometheus configuration
        prometheus_config = self.monitoring_dir / 'prometheus.yml'
        prometheus_content = f"""# Prometheus configuration for NeuroCrew Lab
global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files:
  - "neurocrew_rules.yml"

scrape_configs:
  - job_name: 'neurocrew'
    static_configs:
      - targets: ['localhost:8080']
    scrape_interval: 5s
    metrics_path: /metrics

alerting:
  alertmanagers:
    - static_configs:
        - targets:
          - localhost:9093
"""
        with open(prometheus_config, 'w') as f:
            f.write(prometheus_content)
        created_files.append(prometheus_config)

        # Create alert rules
        alert_rules = self.monitoring_dir / 'neurocrew_rules.yml'
        rules_content = """# NeuroCrew Lab Alert Rules
groups:
  - name: neurocrew_alerts
    rules:
      - alert: HighErrorRate
        expr: rate(neurocrew_errors_total[5m]) > 0.1
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "High error rate detected"
          description: "Error rate is {{ $value }} errors per second"

      - alert: HighResponseTime
        expr: histogram_quantile(0.95, rate(neurocrew_response_time_seconds_bucket[5m])) > 5
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High response time detected"
          description: "95th percentile response time is {{ $value }} seconds"

      - alert: AgentFailure
        expr: neurocrew_agent_failures_total > 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Agent failure detected"
          description: "Agent failures in the last minute"

      - alert: TelegramBotDown
        expr: up{job="neurocrew"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Telegram bot is down"
          description: "NeuroCrew Lab Telegram bot is not responding"

      - alert: LowDiskSpace
        expr: (node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"}) < 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Low disk space"
          description: "Disk space is below 10%"
"""
        with open(alert_rules, 'w') as f:
            f.write(rules_content)
        created_files.append(alert_rules)

        # Create Grafana dashboard
        grafana_dashboard = self.monitoring_dir / 'neurocrew_dashboard.json'
        dashboard_content = {
            "dashboard": {
                "id": None,
                "title": "NeuroCrew Lab Monitoring",
                "tags": ["neurocrew", "telegram"],
                "timezone": "browser",
                "panels": [
                    {
                        "title": "Request Rate",
                        "type": "graph",
                        "targets": [
                            {
                                "expr": "rate(neurocrew_requests_total[5m])",
                                "legendFormat": "{{{agent}}}"
                            }
                        ],
                        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0}
                    },
                    {
                        "title": "Response Time",
                        "type": "graph",
                        "targets": [
                            {
                                "expr": "histogram_quantile(0.95, rate(neurocrew_response_time_seconds_bucket[5m]))",
                                "legendFormat": "95th percentile"
                            },
                            {
                                "expr": "histogram_quantile(0.50, rate(neurocrew_response_time_seconds_bucket[5m]))",
                                "legendFormat": "50th percentile"
                            }
                        ],
                        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 0}
                    }
                ],
                "time": {"from": "now-1h", "to": "now"},
                "refresh": "5s"
            }
        }

        with open(grafana_dashboard, 'w') as f:
            json.dump(dashboard_content, f, indent=2)
        created_files.append(grafana_dashboard)

        # Create health check script
        health_check = self.monitoring_dir / 'health_check.py'
        health_content = f'''#!/usr/bin/env python3
"""
Health check script for NeuroCrew Lab.

This script performs health checks and returns appropriate exit codes.
"""
import sys
import requests
import time
import subprocess
from pathlib import Path

# Configuration
HEALTH_CHECK_URL = "http://localhost:8080/health"
TIMEOUT = 10

def check_telegram_bot():
    """Check if Telegram bot is responsive."""
    try:
        response = requests.get(HEALTH_CHECK_URL, timeout=TIMEOUT)
        return response.status_code == 200
    except:
        return False

def check_cli_agents():
    """Check if CLI agents are available."""
    agents = ["qwen", "gemini", "claude", "opencode", "codex"]
    available = 0

    for agent in agents:
        try:
            result = subprocess.run(["which", agent], capture_output=True, timeout=5)
            if result.returncode == 0:
                available += 1
        except:
            pass

    return available >= 2  # At least 2 agents should be available

def main():
    """Main health check."""
    start_time = time.time()

    checks = [
        ("Telegram Bot", check_telegram_bot),
        ("CLI Agents", check_cli_agents)
    ]

    passed = 0
    total = len(checks)

    for check_name, check_func in checks:
        if check_func():
            print(f"✅ {check_name}: OK")
            passed += 1
        else:
            print(f"❌ {check_name}: FAILED")

    duration = time.time() - start_time
    print(f"Health check completed in {{duration:.2f}}s")

    if passed == total:
        print("🎉 All health checks passed")
        sys.exit(0)
    elif passed > 0:
        print("⚠️ Some health checks failed")
        sys.exit(1)
    else:
        print("🚨 All health checks failed")
        sys.exit(2)

if __name__ == "__main__":
    main()
'''
        with open(health_check, 'w') as f:
            f.write(health_content)
        created_files.append(health_check)

        # Make health check executable
        health_check.chmod(0o755)

        logger.info(f"Monitoring infrastructure setup complete. Files created: {len(created_files)}")
        return created_files

    def create_deployment_package(self) -> Path:
        """Create deployment package."""
        logger.info("Creating deployment package...")

        # Create package filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        package_name = f"neurocrew-{self.environment}-{timestamp}"
        package_path = self.output_dir / f"{package_name}.tar.gz"

        # Files to include in package
        include_files = [
            'main.py',
            'config.py',
            'ncrew.py',
            'telegram_bot.py',
            'requirements.txt',
            '.env.example'
        ]

        include_dirs = [
            'connectors',
            'storage',
            'utils'
        ]

        # Create temporary directory for packaging
        temp_dir = self.output_dir / package_name
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        temp_dir.mkdir()

        try:
            # Copy files
            for file_path in include_files:
                src = self.project_root / file_path
                if src.exists():
                    dst = temp_dir / file_path
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)

            # Copy directories
            for dir_path in include_dirs:
                src = self.project_root / dir_path
                if src.exists():
                    dst = temp_dir / dir_path
                    shutil.copytree(src, dst)

            # Copy environment config
            env_config_file = self.create_environment_config()
            shutil.copy2(env_config_file, temp_dir / 'config' / 'deployment_config.py')

            # Copy monitoring files if enabled
            if self.environment_configs[self.environment].monitoring_enabled:
                monitoring_dst = temp_dir / 'monitoring'
                shutil.copytree(self.monitoring_dir, monitoring_dst, dirs_exist_ok=True)

            # Create deployment script
            deploy_script = temp_dir / 'deploy.sh'
            deploy_content = f'''#!/bin/bash
# Deployment script for NeuroCrew Lab - {self.environment.upper()} environment

set -e

echo "🚀 Deploying NeuroCrew Lab to {self.environment.upper()} environment..."

# Check Python version
python_version=$(python3 --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
if [[ $(echo "$python_version >= 3.8" | bc -l) -eq 0 ]]; then
    echo "❌ Python 3.8+ required, found $python_version"
    exit 1
fi

# Create virtual environment if not exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo "📦 Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Check .env file
if [ ! -f ".env" ]; then
    echo "⚙️ Creating .env file from template..."
    cp .env.example .env
    echo "📝 Please edit .env file with your configuration"
    exit 1
fi

# Create data directories
echo "📁 Creating data directories..."
mkdir -p data/logs data/conversations

# Set permissions
chmod 600 .env
chmod +x monitoring/health_check.py

# Run health check
echo "🏥 Running health check..."
if [ -f "monitoring/health_check.py" ]; then
    python3 monitoring/health_check.py
fi

echo "✅ Deployment completed successfully!"
echo "🎯 Run 'python main.py' to start the application"
'''
            with open(deploy_script, 'w') as f:
                f.write(deploy_content)
            deploy_script.chmod(0o755)

            # Create README for deployment
            readme_file = temp_dir / 'README_DEPLOYMENT.md'
            readme_content = f'''# NeuroCrew Lab Deployment

Environment: {self.environment.upper()}
Created: {datetime.now().isoformat()}

## Quick Start

1. Extract the package:
   ```bash
   tar -xzf {package_name}.tar.gz
   cd {package_name}
   ```

2. Run deployment script:
   ```bash
   ./deploy.sh
   ```

3. Configure environment:
   ```bash
   # Edit .env file with your settings
   vim .env
   ```

4. Start the application:
   ```bash
   source venv/bin/activate
   python main.py
   ```

## Configuration

- Environment configuration: `config/deployment_config.py`
- Environment variables: `.env`
- Logging: `data/logs/`

## Monitoring

- Health check: `monitoring/health_check.py`
- Metrics: Available at `/metrics` endpoint if enabled

## Troubleshooting

1. Check logs: `tail -f data/logs/neurocrew.log`
2. Run health check: `python3 monitoring/health_check.py`
3. Validate dependencies: `python3 -c "import telegram_bot, ncrew"`

## Support

For issues and support, check the logs and health check output.
'''
            with open(readme_file, 'w') as f:
                f.write(readme_content)

            # Create tar.gz package
            with tarfile.open(package_path, 'w:gz') as tar:
                tar.add(temp_dir, arcname=package_name)

            # Calculate package size
            package_size = package_path.stat().st_size / (1024 * 1024)  # MB

            logger.info(f"Deployment package created: {package_path} ({package_size:.1f} MB)")
            return package_path

        finally:
            # Clean up temporary directory
            if temp_dir.exists():
                shutil.rmtree(temp_dir)

    def generate_deployment_report(self, readiness: DeploymentReadiness, package_path: Optional[Path] = None) -> Dict[str, Any]:
        """Generate deployment report."""
        return {
            'timestamp': datetime.now().isoformat(),
            'environment': self.environment,
            'ready': readiness.ready,
            'package_created': str(package_path) if package_path else None,
            'issues': readiness.issues,
            'warnings': readiness.warnings,
            'recommendations': readiness.recommendations,
            'configuration': asdict(readiness.environment_config) if readiness.environment_config else None,
            'next_steps': [
                "🎯 DEPLOYMENT CHECKLIST:",
                "  • All critical issues resolved",
                "  • Configuration validated for target environment",
                "  • Deployment package created and tested",
                "  • Monitoring and logging infrastructure ready",
                "  • Rollback plan prepared",
                "  • Post-deployment verification procedures defined"
            ]
        }


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Prepare NeuroCrew Lab for deployment")
    parser.add_argument('--env', required=True, choices=['dev', 'staging', 'prod'],
                       help='Target environment')
    parser.add_argument('--setup-monitoring', action='store_true',
                       help='Setup monitoring and logging infrastructure')
    parser.add_argument('--create-package', action='store_true',
                       help='Create deployment package')
    parser.add_argument('--check-only', action='store_true',
                       help='Only validate readiness, do not make changes')
    parser.add_argument('--output-dir', type=str,
                       help='Output directory for deployment artifacts')

    args = parser.parse_args()

    # Get project root
    project_root = Path(__file__).parent.parent
    if not (project_root / "main.py").exists():
        print("❌ Error: Not in a valid NeuroCrew Lab project directory")
        sys.exit(1)

    # Create deployment preparer
    preparer = DeploymentPreparer(project_root, args.env)

    print(f"🚀 Deployment preparation for {args.env.upper()} environment\n")

    try:
        # Validate readiness
        readiness = preparer.validate_readiness()

        # Output validation results
        if readiness.ready:
            print("✅ System is ready for deployment!")
        else:
            print("❌ System has issues that must be resolved before deployment")

        if readiness.issues:
            print(f"\n🚨 Critical Issues ({len(readiness.issues)}):")
            for issue in readiness.issues:
                print(f"  • {issue}")

        if readiness.warnings:
            print(f"\n⚠️ Warnings ({len(readiness.warnings)}):")
            for warning in readiness.warnings:
                print(f"  • {warning}")

        # Stop here if check-only or not ready
        if args.check_only or not readiness.ready:
            print("\n" + "="*60)
            print("📋 RECOMMENDATIONS:")
            for rec in readiness.recommendations:
                print(rec)
            sys.exit(0 if readiness.ready else 1)

        # Create environment configuration
        print(f"\n⚙️ Creating environment configuration...")
        preparer.create_environment_config()

        # Setup monitoring if requested
        package_path = None
        if args.setup_monitoring:
            print(f"📊 Setting up monitoring infrastructure...")
            preparer.setup_logging_infrastructure()
            preparer.setup_monitoring()

        # Create deployment package
        if args.create_package:
            print(f"📦 Creating deployment package...")
            package_path = preparer.create_deployment_package()

        # Generate and output report
        report = preparer.generate_deployment_report(readiness, package_path)

        print(f"\n" + "="*60)
        print(f"🎉 DEPLOYMENT PREPARATION COMPLETE")
        print("="*60)

        if package_path:
            print(f"📦 Package: {package_path}")

        print(f"📝 Report generated with {len(report['issues'])} issues and {len(report['warnings'])} warnings")

        # Save deployment report
        report_file = preparer.output_dir / f"deployment_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)

        print(f"💾 Report saved: {report_file}")

        # Next steps
        print(f"\n📋 NEXT STEPS:")
        for step in report['next_steps']:
            print(f"  {step}")

        sys.exit(0)

    except KeyboardInterrupt:
        print("\n❌ Deployment preparation interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Deployment preparation failed: {str(e)}")
        sys.exit(1)


if __name__ == '__main__':
    main()