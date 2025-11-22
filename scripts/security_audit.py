#!/usr/bin/env python3
"""
Security Audit and Configuration Validation Tool for NeuroCrew Lab

This script performs comprehensive security analysis including:
- Configuration security assessment
- Secret and token validation
- File permission auditing
- Input validation checks
- Network security analysis
- Dependency vulnerability scanning

Usage:
    python scripts/security_audit.py [--comprehensive] [--fix-permissions] [--check-secrets]

Options:
    --comprehensive    Run full security audit including dependency scanning
    --fix-permissions  Attempt to fix insecure file permissions
    --check-secrets    Validate all secret configurations
    --output FORMAT    Output format: json, text, or sarif
"""

import os
import re
import sys
import json
import stat
import hashlib
import subprocess
import secrets
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any, Set
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
class SecurityIssue:
    """Security issue found during audit."""
    severity: str  # 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'
    category: str  # 'secrets', 'permissions', 'configuration', 'dependencies', 'network'
    title: str
    description: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    recommendation: Optional[str] = None
    cwe_id: Optional[str] = None  # Common Weakness Enumeration ID
    cvss_score: Optional[float] = None


@dataclass
class SecurityReport:
    """Complete security audit report."""
    timestamp: str
    overall_score: float  # 0-10, higher is better
    total_issues: int
    issues_by_severity: Dict[str, int]
    issues_by_category: Dict[str, int]
    issues: List[SecurityIssue]
    recommendations: List[str]
    compliance_status: Dict[str, bool]


class SecurityAuditor:
    """Comprehensive security auditor for NeuroCrew Lab."""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.issues: List[SecurityIssue] = []
        self.severity_weights = {'CRITICAL': 10, 'HIGH': 7, 'HIGH': 5, 'MEDIUM': 3, 'LOW': 1, 'INFO': 0.1}
        self.sensitive_patterns = [
            # API Keys
            r'(?i)(api[_-]?key|apikey|key[_-]?id)\s*[:=]\s*["\']?[a-zA-Z0-9_-]{20,}["\']?',
            # Tokens
            r'(?i)(token|access[_-]?token|auth[_-]?token|bearer[_-]?token)\s*[:=]\s*["\']?[a-zA-Z0-9._-]{20,}["\']?',
            # Passwords
            r'(?i)(password|passwd|pwd)\s*[:=]\s*["\'][^"\']{8,}["\']',
            # Secrets
            r'(?i)(secret|private[_-]?key|secret[_-]?key)\s*[:=]\s*["\'][a-zA-Z0-9._/-]{20,}["\']',
            # Database connections
            r'(?i)(mongodb|mysql|postgresql|redis):\/\/[^:]+:[^@]+@[^\/]+',
            # Webhook URLs with secrets
            r'https?://[^/]+/[a-zA-Z0-9_-]{20,}',
            # Bot tokens (Telegram)
            r'\d+:[a-zA-Z0-9_-]{35}'
        ]

        # File permissions to check
        self.insecure_permissions = {
            0o777: "World-readable and writable",
            0o666: "World-readable and writable",
            0o444: "World-readable",
            0o222: "World-writable"
        }

        # Critical files that should have restricted permissions
        self.protected_files = [
            '.env',
            '.env.*',
            '*key*',
            '*secret*',
            '*token*',
            'config.py',
            'settings.py'
        ]

    def add_issue(self, issue: SecurityIssue):
        """Add a security issue to the report."""
        self.issues.append(issue)
        logger.warning(f"{issue.severity}: {issue.title} - {issue.description}")

    def scan_for_hardcoded_secrets(self) -> List[SecurityIssue]:
        """Scan codebase for hardcoded secrets and credentials."""
        logger.info("Scanning for hardcoded secrets...")

        extensions_to_scan = ['.py', '.js', '.ts', '.json', '.yaml', '.yml', '.env', '.ini', '.conf']
        files_to_scan = []

        # Collect files to scan
        for ext in extensions_to_scan:
            files_to_scan.extend(self.project_root.rglob(f'*{ext}'))

        # Skip certain directories
        skip_dirs = {'.git', '__pycache__', 'node_modules', '.pytest_cache', 'venv', 'env'}
        files_to_scan = [f for f in files_to_scan if not any(skip_dir in f.parts for skip_dir in skip_dirs)]

        secrets_found = []

        for file_path in files_to_scan:
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    lines = content.split('\n')

                for line_num, line in enumerate(lines, 1):
                    for pattern_num, pattern in enumerate(self.sensitive_patterns):
                        matches = re.finditer(pattern, line)
                        for match in matches:
                            # Skip if it's clearly a placeholder
                            matched_text = match.group()
                            if any(placeholder in matched_text.lower() for placeholder in [
                                'your_', 'example', 'placeholder', 'xxx', 'test', 'demo', 'fake'
                            ]):
                                continue

                            # Skip common configuration keys
                            if any(config_key in matched_text.lower() for config_key in [
                                'api_key_example', 'token_example', 'secret_example'
                            ]):
                                continue

                            issue = SecurityIssue(
                                severity='HIGH',
                                category='secrets',
                                title=f"Potential hardcoded secret detected (Pattern {pattern_num + 1})",
                                description=f"Sensitive pattern found: {matched_text[:50]}{'...' if len(matched_text) > 50 else ''}",
                                file_path=str(file_path.relative_to(self.project_root)),
                                line_number=line_num,
                                recommendation="Move secret to environment variables or secure storage",
                                cwe_id="CWE-798",
                                cvss_score=7.5
                            )
                            secrets_found.append(issue)
                            self.add_issue(issue)

            except Exception as e:
                logger.error(f"Error scanning {file_path}: {str(e)}")

        return secrets_found

    def audit_file_permissions(self) -> List[SecurityIssue]:
        """Audit file and directory permissions."""
        logger.info("Auditing file permissions...")

        permission_issues = []

        for item_path in self.project_root.rglob('*'):
            try:
                if not item_path.exists():
                    continue

                stat_info = item_path.stat()
                file_mode = stat_info.st_mode & 0o777

                # Check for world-writable files/directories
                if file_mode & 0o002:  # World-writable
                    severity = 'CRITICAL' if item_path.is_file() and any(
                        pattern in item_path.name for pattern in ['key', 'secret', 'token', 'env']
                    ) else 'HIGH'

                    issue = SecurityIssue(
                        severity=severity,
                        category='permissions',
                        title="World-writable file or directory",
                        description=f"{item_path.relative_to(self.project_root)} has world-writable permissions ({oct(file_mode)})",
                        file_path=str(item_path.relative_to(self.project_root)),
                        recommendation=f"Remove world-writable permissions: chmod o-w {item_path}",
                        cwe_id="CWE-732",
                        cvss_score=8.0 if severity == 'CRITICAL' else 6.5
                    )
                    permission_issues.append(issue)
                    self.add_issue(issue)

                # Check protected files for excessive permissions
                if item_path.is_file():
                    file_name = item_path.name.lower()
                    if any(protected in file_name for protected in ['key', 'secret', 'token', '.env']):
                        if file_mode & 0o044:  # World-readable
                            issue = SecurityIssue(
                                severity='CRITICAL',
                                category='permissions',
                                title="Sensitive file with world-readable permissions",
                                description=f"Protected file {item_path.relative_to(self.project_root)} is world-readable",
                                file_path=str(item_path.relative_to(self.project_root)),
                                recommendation=f"Restrict file permissions: chmod 600 {item_path}",
                                cwe_id="CWE-200",
                                cvss_score=9.0
                            )
                            permission_issues.append(issue)
                            self.add_issue(issue)

            except Exception as e:
                logger.error(f"Error auditing permissions for {item_path}: {str(e)}")

        return permission_issues

    def validate_configuration_security(self) -> List[SecurityIssue]:
        """Validate configuration security settings."""
        logger.info("Validating configuration security...")

        config_issues = []

        # Check .env file
        env_file = self.project_root / '.env'
        if env_file.exists():
            try:
                with open(env_file, 'r') as f:
                    env_content = f.read()

                # Check for placeholder values
                placeholder_patterns = [
                    (r'(?i)(your_|example_|test_|demo_|fake_)token\b', 'TELEGRAM_BOT_TOKEN'),
                    (r'(?i)(your_|example_|test_|demo_|fake_)key\b', 'API_KEYS'),
                    (r'(?i)(your_|example_|test_|demo_|fake_)secret\b', 'SECRETS')
                ]

                for pattern, config_type in placeholder_patterns:
                    if re.search(pattern, env_content):
                        issue = SecurityIssue(
                            severity='HIGH',
                            category='configuration',
                            title=f"Placeholder values in {config_type}",
                            description=f"Configuration contains placeholder values that need to be replaced",
                            file_path='.env',
                            recommendation="Replace placeholder values with actual secrets",
                            cwe_id="CWE-20",
                            cvss_score=6.1
                        )
                        config_issues.append(issue)
                        self.add_issue(issue)

                # Check token format
                bot_token_match = re.search(r'TELEGRAM_BOT_TOKEN\s*=\s*([^\s]+)', env_content)
                if bot_token_match:
                    token = bot_token_match.group(1).strip('"\'')
                    if token == 'your_bot_token_here' or len(token) < 20:
                        issue = SecurityIssue(
                            severity='HIGH',
                            category='configuration',
                            title="Invalid Telegram bot token format",
                            description="Telegram bot token appears to be invalid or placeholder",
                            file_path='.env',
                            recommendation="Configure a valid Telegram bot token",
                            cwe_id="CWE-20",
                            cvss_score=6.1
                        )
                        config_issues.append(issue)
                        self.add_issue(issue)

            except Exception as e:
                logger.error(f"Error reading .env file: {str(e)}")

        # Check config.py for security issues
        config_file = self.project_root / 'config.py'
        if config_file.exists():
            try:
                with open(config_file, 'r') as f:
                    config_content = f.read()

                # Check for hardcoded values
                if re.search(r'(token|key|secret)\s*=\s*["\'][^"\']{10,}["\']', config_content, re.IGNORECASE):
                    issue = SecurityIssue(
                        severity='MEDIUM',
                        category='configuration',
                        title="Potential hardcoded credentials in config",
                        description="Configuration file may contain hardcoded sensitive values",
                        file_path='config.py',
                        recommendation="Move sensitive values to environment variables",
                        cwe_id="CWE-798",
                        cvss_score=5.5
                    )
                    config_issues.append(issue)
                    self.add_issue(issue)

            except Exception as e:
                logger.error(f"Error reading config.py: {str(e)}")

        return config_issues

    def scan_dependencies_for_vulnerabilities(self) -> List[SecurityIssue]:
        """Scan dependencies for known vulnerabilities."""
        logger.info("Scanning dependencies for vulnerabilities...")

        vuln_issues = []

        # Check requirements.txt
        req_file = self.project_root / 'requirements.txt'
        if req_file.exists():
            try:
                with open(req_file, 'r') as f:
                    requirements = [line.strip() for line in f if line.strip() and not line.startswith('#')]

                # Known vulnerable packages and their fixed versions
                vulnerable_packages = {
                    'urllib3': {
                        'vulnerable_versions': ['<1.26.5'],
                        'cve': 'CVE-2021-33503',
                        'description': 'Certificate verification bypass vulnerability',
                        'fixed_version': '1.26.5'
                    },
                    'requests': {
                        'vulnerable_versions': ['<2.25.1'],
                        'cve': 'CVE-2021-33503',
                        'description': 'Certificate verification bypass vulnerability',
                        'fixed_version': '2.25.1'
                    },
                    'pyyaml': {
                        'vulnerable_versions': ['<5.4.1'],
                        'cve': 'CVE-2020-1747',
                        'description': 'Arbitrary code execution vulnerability',
                        'fixed_version': '5.4.1'
                    }
                }

                for req in requirements:
                    package_name = req.split('==')[0].split('>=')[0].split('<=')[0].strip('<>=')

                    if package_name in vulnerable_packages:
                        vuln_info = vulnerable_packages[package_name]

                        issue = SecurityIssue(
                            severity='HIGH',
                            category='dependencies',
                            title=f"Vulnerable dependency: {package_name}",
                            description=f"{vuln_info['description']} ({vuln_info['cve']})",
                            recommendation=f"Upgrade to {package_name}>={vuln_info['fixed_version']}",
                            cwe_id="CWE-1035",
                            cvss_score=7.5
                        )
                        vuln_issues.append(issue)
                        self.add_issue(issue)

            except Exception as e:
                logger.error(f"Error scanning requirements.txt: {str(e)}")

        return vuln_issues

    def check_input_validation(self) -> List[SecurityIssue]:
        """Check for proper input validation in the codebase."""
        logger.info("Checking input validation...")

        validation_issues = []

        # Scan Python files for input validation issues
        py_files = list(self.project_root.rglob('*.py'))
        py_files = [f for f in py_files if not any(skip_dir in f.parts for skip_dir in ['.git', '__pycache__', 'venv'])]

        for py_file in py_files:
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    lines = content.split('\n')

                for line_num, line in enumerate(lines, 1):
                    # Check for direct use of user input without validation
                    dangerous_patterns = [
                        (r'input\(\)\s*\.\s*[a-z_]+\(', "Direct method call on user input without validation"),
                        (r'eval\s*\(\s*input\s*\(', "Using eval() on user input - dangerous"),
                        (r'exec\s*\(\s*input\s*\(', "Using exec() on user input - dangerous"),
                        (r'os\.system\s*\(\s*input\s*\(', "Using os.system() on user input - dangerous"),
                        (r'subprocess\.run\s*\(\s*input\s*\(', "Using subprocess.run() on user input - dangerous"),
                    ]

                    for pattern, description in dangerous_patterns:
                        if re.search(pattern, line):
                            issue = SecurityIssue(
                                severity='CRITICAL' if 'eval' in pattern or 'exec' in pattern else 'HIGH',
                                category='configuration',
                                title=description,
                                description=f"Line {line_num}: {line.strip()}",
                                file_path=str(py_file.relative_to(self.project_root)),
                                line_number=line_num,
                                recommendation="Validate and sanitize all user input before processing",
                                cwe_id="CWE-20" if 'eval' in pattern else "CWE-78",
                                cvss_score=9.0 if 'eval' in pattern else 7.5
                            )
                            validation_issues.append(issue)
                            self.add_issue(issue)

            except Exception as e:
                logger.error(f"Error analyzing {py_file}: {str(e)}")

        return validation_issues

    def assess_network_security(self) -> List[SecurityIssue]:
        """Assess network security configurations."""
        logger.info("Assessing network security...")

        network_issues = []

        # Check for hardcoded URLs and endpoints
        py_files = list(self.project_root.rglob('*.py'))

        for py_file in py_files:
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    lines = content.split('\n')

                for line_num, line in enumerate(lines, 1):
                    # Check for hardcoded HTTP endpoints without SSL
                    http_urls = re.findall(r'http://[^\s\'"]+', line)
                    for url in http_urls:
                        if 'localhost' not in url and '127.0.0.1' not in url:
                            issue = SecurityIssue(
                                severity='MEDIUM',
                                category='network',
                                title="Insecure HTTP URL detected",
                                description=f"HTTP URL without SSL: {url}",
                                file_path=str(py_file.relative_to(self.project_root)),
                                line_number=line_num,
                                recommendation="Use HTTPS URLs for all external communications",
                                cwe_id="CWE-319",
                                cvss_score=5.3
                            )
                            network_issues.append(issue)
                            self.add_issue(issue)

            except Exception as e:
                logger.error(f"Error analyzing {py_file}: {str(e)}")

        # Check for proxy configuration issues
        env_file = self.project_root / '.env'
        if env_file.exists():
            try:
                with open(env_file, 'r') as f:
                    env_content = f.read()

                # Check for insecure proxy protocols
                if 'http://' in env_content.lower():
                    issue = SecurityIssue(
                        severity='MEDIUM',
                        category='network',
                        title="Potentially insecure proxy configuration",
                        description="HTTP proxy URL detected - consider using HTTPS",
                        file_path='.env',
                        recommendation="Use HTTPS proxy URLs or verify proxy security",
                        cwe_id="CWE-319",
                        cvss_score=4.8
                    )
                    network_issues.append(issue)
                    self.add_issue(issue)

            except Exception as e:
                logger.error(f"Error checking proxy configuration: {str(e)}")

        return network_issues

    def calculate_security_score(self) -> float:
        """Calculate overall security score (0-10)."""
        if not self.issues:
            return 10.0

        total_weight = sum(self.severity_weights[issue.severity] for issue in self.issues)
        max_possible_weight = 10 * len(self.issues)  # Assume max severity of 10 for all issues

        if max_possible_weight == 0:
            return 10.0

        # Score = 10 - (total_weight / max_possible_weight * 10)
        score = max(0, 10 - (total_weight / max_possible_weight * 10))
        return round(score, 2)

    def generate_recommendations(self) -> List[str]:
        """Generate security recommendations based on findings."""
        recommendations = []

        if not self.issues:
            recommendations.append("✅ No security issues found. Maintain current security practices.")
            return recommendations

        # Group issues by category for targeted recommendations
        categories = {}
        for issue in self.issues:
            if issue.category not in categories:
                categories[issue.category] = []
            categories[issue.category].append(issue)

        # Generate category-specific recommendations
        if 'secrets' in categories:
            recommendations.extend([
                "🔐 SECRETS MANAGEMENT:",
                "  • Move all secrets to environment variables or secure vault",
                "  • Use secret management tools like HashiCorp Vault or AWS Secrets Manager",
                "  • Implement secret rotation policies",
                "  • Never commit secrets to version control"
            ])

        if 'permissions' in categories:
            recommendations.extend([
                "📁 FILE PERMISSIONS:",
                "  • Restrict permissions on sensitive files (chmod 600 for .env files)",
                "  • Remove world-writable permissions (chmod o-w)",
                "  • Use file system ACLs for additional protection"
            ])

        if 'configuration' in categories:
            recommendations.extend([
                "⚙️ CONFIGURATION SECURITY:",
                "  • Validate all user inputs before processing",
                "  • Use environment variables for configuration",
                "  • Implement proper error handling without information disclosure"
            ])

        if 'dependencies' in categories:
            recommendations.extend([
                "📦 DEPENDENCY MANAGEMENT:",
                "  • Regularly update dependencies to latest secure versions",
                "  • Use dependency scanning tools in CI/CD pipeline",
                "  • Pin dependency versions to prevent unexpected updates"
            ])

        if 'network' in categories:
            recommendations.extend([
                "🌐 NETWORK SECURITY:",
                "  • Use HTTPS for all external communications",
                "  • Validate SSL certificates properly",
                "  • Implement network segmentation and firewall rules"
            ])

        # General recommendations
        recommendations.extend([
            "\n🛡️ GENERAL SECURITY:",
            "  • Implement security scanning in CI/CD pipeline",
            "  • Regular security audits and penetration testing",
            "  • Keep all systems and dependencies updated",
            "  • Implement proper logging and monitoring for security events",
            "  • Create security incident response procedures"
        ])

        return recommendations

    def fix_file_permissions(self) -> Tuple[int, List[str]]:
        """Attempt to fix insecure file permissions."""
        logger.info("Attempting to fix file permissions...")

        fixed_files = 0
        errors = []

        for item_path in self.project_root.rglob('*'):
            try:
                if not item_path.exists():
                    continue

                stat_info = item_path.stat()
                file_mode = stat_info.st_mode & 0o777

                # Fix world-writable permissions
                if file_mode & 0o002:
                    new_mode = file_mode & ~0o002  # Remove world-writable
                    item_path.chmod(new_mode)
                    fixed_files += 1
                    logger.info(f"Fixed world-writable permissions on {item_path}")

                # Fix sensitive files that are world-readable
                if item_path.is_file():
                    file_name = item_path.name.lower()
                    if any(protected in file_name for protected in ['key', 'secret', 'token', '.env']):
                        if file_mode & 0o044:  # World-readable
                            new_mode = file_mode & ~0o044  # Remove world-readable
                            item_path.chmod(new_mode)
                            fixed_files += 1
                            logger.info(f"Fixed world-readable permissions on sensitive file {item_path}")

            except Exception as e:
                errors.append(f"Error fixing permissions for {item_path}: {str(e)}")

        return fixed_files, errors

    def generate_report(self) -> SecurityReport:
        """Generate comprehensive security report."""
        issues_by_severity = {severity: 0 for severity in self.severity_weights.keys()}
        issues_by_category = {}

        for issue in self.issues:
            issues_by_severity[issue.severity] += 1
            if issue.category not in issues_by_category:
                issues_by_category[issue.category] = 0
            issues_by_category[issue.category] += 1

        # Check compliance status
        compliance_status = {
            'no_hardcoded_secrets': all(issue.category != 'secrets' for issue in self.issues if issue.severity in ['CRITICAL', 'HIGH']),
            'proper_file_permissions': all(issue.category != 'permissions' for issue in self.issues if issue.severity == 'CRITICAL'),
            'input_validation': all(issue.category != 'configuration' for issue in self.issues if 'eval' in issue.description.lower() or 'exec' in issue.description.lower()),
            'secure_dependencies': all(issue.category != 'dependencies' for issue in self.issues if issue.severity == 'HIGH')
        }

        return SecurityReport(
            timestamp=str(Path().cwd()),
            overall_score=self.calculate_security_score(),
            total_issues=len(self.issues),
            issues_by_severity=issues_by_severity,
            issues_by_category=issues_by_category,
            issues=self.issues,
            recommendations=self.generate_recommendations(),
            compliance_status=compliance_status
        )


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Security audit for NeuroCrew Lab")
    parser.add_argument('--comprehensive', action='store_true', help='Run comprehensive security audit')
    parser.add_argument('--fix-permissions', action='store_true', help='Attempt to fix insecure file permissions')
    parser.add_argument('--check-secrets', action='store_true', help='Focus on secret detection')
    parser.add_argument('--output', '-o', help='Output report file')
    parser.add_argument('--format', choices=['json', 'text', 'sarif'], default='text', help='Output format')
    parser.add_argument('--quiet', '-q', action='store_true', help='Suppress detailed output')

    args = parser.parse_args()

    # Get project root
    project_root = Path(__file__).parent.parent
    if not (project_root / "main.py").exists():
        print("❌ Error: Not in a valid NeuroCrew Lab project directory")
        sys.exit(1)

    # Create auditor
    auditor = SecurityAuditor(project_root)

    print("🔒 Starting security audit...\n")

    # Run security checks
    try:
        if args.check_secrets:
            auditor.scan_for_hardcoded_secrets()
        else:
            auditor.scan_for_hardcoded_secrets()
            auditor.audit_file_permissions()
            auditor.validate_configuration_security()
            auditor.check_input_validation()

            if args.comprehensive:
                auditor.scan_dependencies_for_vulnerabilities()
                auditor.assess_network_security()

    except KeyboardInterrupt:
        print("\n❌ Security audit interrupted")
        sys.exit(1)

    # Fix permissions if requested
    if args.fix_permissions:
        fixed_files, errors = auditor.fix_file_permissions()
        print(f"🔧 Fixed permissions for {fixed_files} files")
        if errors:
            for error in errors:
                print(f"  ❌ {error}")

    # Generate report
    report = auditor.generate_report()

    # Output results
    if args.format == 'json':
        print(json.dumps(asdict(report), indent=2, default=str))
    elif args.format == 'sarif':
        # Convert to SARIF format
        sarif_report = {
            "version": "2.1.0",
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "runs": [{
                "tool": {"driver": {"name": "NeuroCrew Lab Security Auditor", "version": "1.0.0"}},
                "results": [
                    {
                        "level": issue.severity.lower(),
                        "message": {"text": issue.description},
                        "locations": [{
                            "physicalLocation": {
                                "artifactLocation": {"uri": issue.file_path},
                                "region": {"startLine": issue.line_number or 1}
                            }
                        }],
                        "properties": {
                            "cwe": issue.cwe_id,
                            "cvssScore": issue.cvss_score
                        }
                    }
                    for issue in report.issues
                ]
            }]
        }
        print(json.dumps(sarif_report, indent=2))
    else:
        # Text format
        print("="*60)
        print(f"🔒 SECURITY AUDIT REPORT")
        print("="*60)
        print(f"Security Score: {report.overall_score}/10")
        print(f"Total Issues: {report.total_issues}")
        print()

        # Issues by severity
        print("📊 Issues by Severity:")
        for severity, count in report.issues_by_severity.items():
            if count > 0:
                icon = {'CRITICAL': '🚨', 'HIGH': '⚠️', 'MEDIUM': '⚡', 'LOW': '💡', 'INFO': 'ℹ️'}.get(severity, '❓')
                print(f"  {icon} {severity}: {count}")

        # Issues by category
        print("\n📂 Issues by Category:")
        for category, count in report.issues_by_category.items():
            print(f"  {category}: {count}")

        # Compliance status
        print("\n✅ Compliance Status:")
        for compliance, status in report.compliance_status.items():
            status_icon = "✅" if status else "❌"
            print(f"  {status_icon} {compliance.replace('_', ' ').title()}")

        # Critical issues
        critical_issues = [i for i in report.issues if i.severity == 'CRITICAL']
        if critical_issues:
            print(f"\n🚨 CRITICAL ISSUES ({len(critical_issues)}):")
            for issue in critical_issues:
                print(f"  • {issue.title}")
                print(f"    {issue.description}")
                if issue.file_path:
                    print(f"    File: {issue.file_path}")
                if issue.recommendation:
                    print(f"    Recommendation: {issue.recommendation}")

        # Recommendations
        if not args.quiet and report.recommendations:
            print("\n📋 RECOMMENDATIONS:")
            for rec in report.recommendations:
                print(rec)

    # Save report if requested
    if args.output:
        with open(args.output, 'w') as f:
            if args.format == 'json':
                json.dump(asdict(report), f, indent=2, default=str)
            elif args.format == 'sarif':
                # Use SARIF format from above
                pass
            else:
                f.write(f"NeuroCrew Lab Security Audit Report\n")
                f.write(f"Generated: {report.timestamp}\n")
                f.write(f"Security Score: {report.overall_score}/10\n")
                f.write(f"Total Issues: {report.total_issues}\n\n")
                for issue in report.issues:
                    f.write(f"{issue.severity}: {issue.title}\n")
                    f.write(f"  {issue.description}\n\n")

    # Exit with appropriate code based on critical issues
    critical_count = report.issues_by_severity.get('CRITICAL', 0)
    high_count = report.issues_by_severity.get('HIGH', 0)
    exit_code = 1 if critical_count > 0 or high_count > 0 else 0
    sys.exit(exit_code)


if __name__ == '__main__':
    main()