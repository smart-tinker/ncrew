#!/usr/bin/env python3
"""
Master Preflight Check for NeuroCrew Lab Deployment

This script runs ALL validation and diagnostic tools to provide a complete
deployment readiness assessment. It's the single entry point for comprehensive
system validation before deployment.

Usage:
    python scripts/preflight_check.py [--environment ENV] [--comprehensive] [--fix]

Options:
    --environment ENV    Target environment (dev, staging, prod)
    --comprehensive      Run full comprehensive validation
    --fix               Attempt automatic fixes where possible
    --output FORMAT     Output format: json, text, html
    --report-file FILE  Save detailed report to file
"""

import os
import sys
import json
import time
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import subprocess
import importlib.util

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@dataclass
class PreflightSection:
    """Results of a preflight check section."""
    name: str
    status: str  # 'PASS', 'FAIL', 'WARN', 'SKIP'
    duration: float
    tests_run: int
    tests_passed: int
    critical_issues: int
    warnings: int
    details: Dict[str, Any]
    fix_available: bool = False


@dataclass
class PreflightReport:
    """Complete preflight check report."""
    timestamp: str
    environment: str
    overall_status: str  # 'READY', 'NEEDS_FIXES', 'NOT_READY'
    total_duration: float
    sections: List[PreflightSection]
    summary: Dict[str, int]
    recommendations: List[str]
    next_steps: List[str]
    deployment_readiness_score: float  # 0-100


class PreflightChecker:
    """Master preflight checker that coordinates all validation tools."""

    def __init__(self, project_root: Path, environment: str = 'dev'):
        self.project_root = project_root
        self.environment = environment
        self.start_time = time.time()
        self.sections: List[PreflightSection] = []

        # Validation tools to run
        self.validation_tools = [
            ('system_validation', 'System Requirements Validation', 'validate_system.py'),
            ('security_audit', 'Security Audit', 'security_audit.py'),
            ('external_deps', 'External Dependencies Testing', 'test_external_deps.py'),
            ('agent_validation', 'CLI Agent Integration', 'validate_agents.py'),
            ('troubleshoot', 'Application Diagnostics', 'troubleshoot.py')
        ]

    def run_validation_tool(self, tool_name: str, tool_title: str, script_name: str,
                           comprehensive: bool = False, auto_fix: bool = False) -> PreflightSection:
        """Run a specific validation tool and parse results."""
        print(f"\n🔍 Running {tool_title}...")
        start_time = time.time()

        script_path = self.project_root / 'scripts' / script_name
        if not script_path.exists():
            return PreflightSection(
                name=tool_title,
                status='FAIL',
                duration=0.0,
                tests_run=0,
                tests_passed=0,
                critical_issues=1,
                warnings=0,
                details={'error': f'Validation script not found: {script_path}'}
            )

        try:
            # Build command based on tool type
            cmd = [sys.executable, str(script_path)]

            if tool_name == 'system_validation':
                cmd.extend(['--verbose'] if comprehensive else [])
                if auto_fix:
                    cmd.append('--fix')
            elif tool_name == 'security_audit':
                cmd.extend(['--comprehensive'] if comprehensive else [])
                if auto_fix:
                    cmd.append('--fix-permissions')
            elif tool_name == 'external_deps':
                cmd.extend(['--comprehensive'] if comprehensive else [])
                cmd.extend(['--parallel'])
            elif tool_name == 'agent_validation':
                cmd.extend(['--comprehensive', '--benchmark'] if comprehensive else [])
                cmd.extend(['--parallel'])
            elif tool_name == 'troubleshoot':
                cmd.extend(['--diagnose'])
                if auto_fix:
                    cmd.append('--fix')

            # Run the validation tool
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout per tool
                cwd=self.project_root
            )

            duration = time.time() - start_time

            # Parse results based on tool type
            if tool_name == 'system_validation':
                return self._parse_system_validation(result, tool_title, duration)
            elif tool_name == 'security_audit':
                return self._parse_security_audit(result, tool_title, duration)
            elif tool_name == 'external_deps':
                return self._parse_external_deps(result, tool_title, duration)
            elif tool_name == 'agent_validation':
                return self._parse_agent_validation(result, tool_title, duration)
            elif tool_name == 'troubleshoot':
                return self._parse_troubleshoot(result, tool_title, duration)
            else:
                return self._parse_generic_output(result, tool_title, duration)

        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            return PreflightSection(
                name=tool_title,
                status='FAIL',
                duration=duration,
                tests_run=0,
                tests_passed=0,
                critical_issues=1,
                warnings=0,
                details={'error': 'Validation tool timed out'}
            )
        except Exception as e:
            duration = time.time() - start_time
            return PreflightSection(
                name=tool_title,
                status='FAIL',
                duration=duration,
                tests_run=0,
                tests_passed=0,
                critical_issues=1,
                warnings=0,
                details={'error': f'Validation tool error: {str(e)}'}
            )

    def _parse_system_validation(self, result: subprocess.CompletedProcess, title: str, duration: float) -> PreflightSection:
        """Parse system validation output."""
        # Look for key indicators in output
        output = result.stdout + result.stderr

        # Count passed/failed tests
        passed_tests = output.count('✅')
        failed_tests = output.count('❌')
        warning_tests = output.count('⚠️')

        # Determine status
        if result.returncode == 0 and failed_tests == 0:
            status = 'PASS'
        elif failed_tests > 0:
            status = 'FAIL'
        elif warning_tests > 0:
            status = 'WARN'
        else:
            status = 'FAIL'  # Unknown failure

        return PreflightSection(
            name=title,
            status=status,
            duration=duration,
            tests_run=passed_tests + failed_tests + warning_tests,
            tests_passed=passed_tests,
            critical_issues=failed_tests,
            warnings=warning_tests,
            details={
                'return_code': result.returncode,
                'output_length': len(output),
                'key_issues': self._extract_key_issues(output)
            },
            fix_available=failed_tests > 0
        )

    def _parse_security_audit(self, result: subprocess.CompletedProcess, title: str, duration: float) -> PreflightSection:
        """Parse security audit output."""
        output = result.stdout + result.stderr

        # Extract security score and issues
        security_score = 100  # Default
        critical_issues = 0
        warnings = 0

        # Look for security score
        if 'Security Score:' in output:
            try:
                score_line = [line for line in output.split('\n') if 'Security Score:' in line][0]
                security_score = float(score_line.split(':')[1].strip().split('/')[0])
            except:
                pass

        # Count issues by severity
        critical_issues = output.count('🚨') + output.count('CRITICAL')
        warnings = output.count('⚠️') + output.count('WARNING')

        status = 'PASS' if security_score >= 90 and critical_issues == 0 else \
                'WARN' if security_score >= 70 and critical_issues == 0 else 'FAIL'

        return PreflightSection(
            name=title,
            status=status,
            duration=duration,
            tests_run=critical_issues + warnings + 1,
            tests_passed=1 if status == 'PASS' else 0,
            critical_issues=critical_issues,
            warnings=warnings,
            details={
                'security_score': security_score,
                'return_code': result.returncode,
                'vulnerabilities_found': critical_issues > 0
            },
            fix_available=critical_issues > 0 or warnings > 0
        )

    def _parse_external_deps(self, result: subprocess.CompletedProcess, title: str, duration: float) -> PreflightSection:
        """Parse external dependencies test output."""
        output = result.stdout + result.stderr

        # Count test results
        passed_tests = output.count('✅')
        failed_tests = output.count('❌')
        total_tests = passed_tests + failed_tests

        if total_tests == 0:
            total_tests = 1  # Avoid division by zero

        status = 'PASS' if result.returncode == 0 and failed_tests == 0 else \
                'WARN' if failed_tests > 0 and passed_tests > 0 else 'FAIL'

        return PreflightSection(
            name=title,
            status=status,
            duration=duration,
            tests_run=total_tests,
            tests_passed=passed_tests,
            critical_issues=failed_tests,
            warnings=output.count('⚠️'),
            details={
                'connectivity_tests': passed_tests,
                'network_issues': failed_tests,
                'return_code': result.returncode
            },
            fix_available=failed_tests > 0
        )

    def _parse_agent_validation(self, result: subprocess.CompletedProcess, title: str, duration: float) -> PreflightSection:
        """Parse agent validation output."""
        output = result.stdout + result.stderr

        # Extract agent availability
        available_agents = 0
        total_agents = 5  # Expected number of agents

        if 'Available Agents:' in output:
            try:
                avail_line = [line for line in output.split('\n') if 'Available Agents:' in line][0]
                available_agents = int(avail_line.split(':')[1].strip().split('/')[0])
            except:
                pass

        failed_agents = total_agents - available_agents

        status = 'PASS' if available_agents >= 3 else \
                'WARN' if available_agents >= 1 else 'FAIL'

        return PreflightSection(
            name=title,
            status=status,
            duration=duration,
            tests_run=total_agents,
            tests_passed=available_agents,
            critical_issues=0,  # Agent issues are warnings, not critical for basic functionality
            warnings=failed_agents,
            details={
                'available_agents': available_agents,
                'total_agents': total_agents,
                'agent_coverage': (available_agents / total_agents) * 100
            },
            fix_available=failed_agents > 0
        )

    def _parse_troubleshoot(self, result: subprocess.CompletedProcess, title: str, duration: float) -> PreflightSection:
        """Parse troubleshooting output."""
        output = result.stdout + result.stderr

        # Determine health status
        health_status = 'CRITICAL'
        if 'HEALTHY' in output:
            health_status = 'HEALTHY'
        elif 'DEGRADED' in output:
            health_status = 'DEGRADED'
        elif 'CRITICAL' in output:
            health_status = 'CRITICAL'

        # Count issues
        critical_issues = output.count('🚨') + output.count('FAIL')
        warnings = output.count('⚠️') + output.count('WARN')

        status = 'PASS' if health_status == 'HEALTHY' else \
                'WARN' if health_status == 'DEGRADED' else 'FAIL'

        return PreflightSection(
            name=title,
            status=status,
            duration=duration,
            tests_run=critical_issues + warnings + 1,
            tests_passed=1 if status == 'PASS' else 0,
            critical_issues=critical_issues,
            warnings=warnings,
            details={
                'health_status': health_status,
                'component_issues': critical_issues,
                'performance_warnings': warnings
            },
            fix_available=critical_issues > 0
        )

    def _parse_generic_output(self, result: subprocess.CompletedProcess, title: str, duration: float) -> PreflightSection:
        """Parse generic tool output."""
        status = 'PASS' if result.returncode == 0 else 'FAIL'

        return PreflightSection(
            name=title,
            status=status,
            duration=duration,
            tests_run=1,
            tests_passed=1 if status == 'PASS' else 0,
            critical_issues=1 if status == 'FAIL' else 0,
            warnings=0,
            details={
                'return_code': result.returncode,
                'output_length': len(result.stdout + result.stderr)
            }
        )

    def _extract_key_issues(self, output: str) -> List[str]:
        """Extract key issues from validation output."""
        issues = []
        lines = output.split('\n')

        for line in lines:
            if any(keyword in line for keyword in ['❌', 'FAIL', 'ERROR', 'CRITICAL', 'MISSING']):
                # Clean up the line for readability
                clean_line = line.strip()
                clean_line = clean_line.replace('❌', '').replace('⚠️', '').strip()
                if clean_line and len(clean_line) < 200:  # Limit length
                    issues.append(clean_line)

        return issues[:5]  # Return top 5 issues

    def calculate_deployment_readiness_score(self) -> float:
        """Calculate overall deployment readiness score (0-100)."""
        if not self.sections:
            return 0.0

        total_score = 0.0
        total_weight = 0.0

        # Weight sections differently based on importance
        weights = {
            'System Requirements Validation': 25,
            'Security Audit': 20,
            'External Dependencies Testing': 20,
            'CLI Agent Integration': 15,
            'Application Diagnostics': 20
        }

        for section in self.sections:
            weight = weights.get(section.name, 10)

            # Calculate section score
            if section.tests_run == 0:
                section_score = 0
            else:
                section_score = (section.tests_passed / section.tests_run) * 100

                # Deduct points for critical issues
                section_score -= (section.critical_issues * 10)

                # Deduct points for warnings
                section_score -= (section.warnings * 5)

                section_score = max(0, min(100, section_score))

            total_score += section_score * (weight / 100)
            total_weight += weight

        if total_weight == 0:
            return 0.0

        return round(total_score, 1)

    def generate_recommendations(self) -> List[str]:
        """Generate deployment recommendations based on results."""
        recommendations = []

        # Analyze each section for recommendations
        for section in self.sections:
            if section.status == 'FAIL':
                if 'Security' in section.name:
                    recommendations.extend([
                        "🔒 SECURITY ISSUES FOUND:",
                        "  • Address all critical security vulnerabilities immediately",
                        "  • Fix file permissions for sensitive files",
                        "  • Remove any hardcoded secrets or credentials",
                        "  • Run security audit again after fixes"
                    ])
                elif 'System' in section.name:
                    recommendations.extend([
                        "🖥️ SYSTEM REQUIREMENTS:",
                        "  • Install missing Python packages",
                        "  • Create and activate virtual environment",
                        "  • Fix file system permissions",
                        "  • Ensure all dependencies are compatible"
                    ])
                elif 'External Dependencies' in section.name:
                    recommendations.extend([
                        "🌐 NETWORK DEPENDENCIES:",
                        "  • Check internet connectivity and DNS settings",
                        "  • Verify proxy configuration if applicable",
                        "  • Test Telegram API connectivity manually",
                        "  • Check SSL certificate configuration"
                    ])
                elif 'CLI Agent' in section.name:
                    recommendations.extend([
                        "🤖 CLI AGENTS:",
                        "  • Install missing CLI tools per documentation",
                        "  • Add CLI tools to system PATH",
                        "  • Test agent functionality manually",
                        "  • Configure agent paths in .env file"
                    ])
                elif 'Diagnostics' in section.name:
                    recommendations.extend([
                        "📊 APPLICATION ISSUES:",
                        "  • Review application logs for specific errors",
                        "  • Test component initialization manually",
                        "  • Verify configuration files are correct",
                        "  • Check for import or dependency conflicts"
                    ])

        if section.status == 'WARN':
            recommendations.append(f"⚠️ WARNING in {section.name}: Review and address warnings for optimal performance")

        # Add general recommendations
        readiness_score = self.calculate_deployment_readiness_score()
        if readiness_score >= 90:
            recommendations.append("✅ EXCELLENT: System is ready for production deployment")
        elif readiness_score >= 70:
            recommendations.append("⚠️ MODERATE: Address critical issues before production deployment")
        else:
            recommendations.append("🚨 POOR: Significant issues found - not ready for deployment")

        return list(set(recommendations))  # Remove duplicates

    def generate_next_steps(self) -> List[str]:
        """Generate next steps for deployment."""
        readiness_score = self.calculate_deployment_readiness_score()

        if readiness_score >= 90:
            return [
                "🎯 DEPLOYMENT READY:",
                "  • Run final smoke tests in staging environment",
                "  • Create deployment package using deployment prep tool",
                "  • Schedule deployment window with stakeholders",
                "  • Prepare rollback plan and monitoring",
                "  • Execute deployment following checklist"
            ]
        elif readiness_score >= 70:
            return [
                "🔧 FIXES NEEDED:",
                "  • Address all critical issues identified",
                "  • Re-run validation after fixes",
                "  • Test functionality in staging environment",
                "  • Review and update documentation",
                "  • Re-assess deployment readiness"
            ]
        else:
            return [
                "🚨 MAJOR ISSUES:",
                "  • Address all critical failures immediately",
                "  • Consider staging environment for testing",
                "  • Review system requirements and compatibility",
                "  • Update dependencies and configurations",
                "  • Seek technical support if needed"
            ]

    def run_comprehensive_check(self, comprehensive: bool = False, auto_fix: bool = False) -> PreflightReport:
        """Run comprehensive preflight check."""
        print("🚀 Starting Comprehensive NeuroCrew Lab Preflight Check")
        print("=" * 60)

        # Run all validation tools
        for tool_name, tool_title, script_name in self.validation_tools:
            section = self.run_validation_tool(tool_name, tool_title, script_name, comprehensive, auto_fix)
            self.sections.append(section)

            # Print immediate summary
            status_icon = {'PASS': '✅', 'FAIL': '❌', 'WARN': '⚠️', 'SKIP': '⏭️'}.get(section.status, '❓')
            print(f"{status_icon} {tool_title}: {section.status} ({section.tests_passed}/{section.tests_run} tests passed, {section.duration:.1f}s)")

        # Calculate overall metrics
        total_duration = time.time() - self.start_time
        total_tests = sum(s.tests_run for s in self.sections)
        total_passed = sum(s.tests_passed for s in self.sections)
        total_critical = sum(s.critical_issues for s in self.sections)
        total_warnings = sum(s.warnings for s in self.sections)

        # Determine overall status
        readiness_score = self.calculate_deployment_readiness_score()
        if readiness_score >= 90 and total_critical == 0:
            overall_status = 'READY'
        elif readiness_score >= 70:
            overall_status = 'NEEDS_FIXES'
        else:
            overall_status = 'NOT_READY'

        # Generate recommendations and next steps
        recommendations = self.generate_recommendations()
        next_steps = self.generate_next_steps()

        return PreflightReport(
            timestamp=datetime.now().isoformat(),
            environment=self.environment,
            overall_status=overall_status,
            total_duration=total_duration,
            sections=self.sections,
            summary={
                'total_tests': total_tests,
                'total_passed': total_passed,
                'total_critical': total_critical,
                'total_warnings': total_warnings,
                'readiness_score': readiness_score
            },
            recommendations=recommendations,
            next_steps=next_steps,
            deployment_readiness_score=readiness_score
        )

    def output_report(self, report: PreflightReport, format_type: str = 'text') -> str:
        """Generate formatted report output."""
        if format_type == 'json':
            return json.dumps(asdict(report), indent=2, default=str)

        elif format_type == 'html':
            return self._generate_html_report(report)

        else:  # text format
            output = []
            output.append("=" * 60)
            output.append(f"🚀 NEUROCREW LAB PREFLIGHT CHECK REPORT")
            output.append("=" * 60)
            output.append(f"Environment: {report.environment.upper()}")
            output.append(f"Timestamp: {report.timestamp}")
            output.append(f"Overall Status: {report.overall_status}")
            output.append(f"Readiness Score: {report.deployment_readiness_score}/100")
            output.append(f"Total Duration: {report.total_duration:.1f}s")
            output.append("")

            # Summary
            output.append("📊 SUMMARY:")
            summary = report.summary
            output.append(f"  Total Tests: {summary['total_tests']}")
            output.append(f"  Passed: {summary['total_passed']}")
            output.append(f"  Critical Issues: {summary['total_critical']}")
            output.append(f"  Warnings: {summary['total_warnings']}")
            output.append("")

            # Section details
            output.append("🔍 SECTION DETAILS:")
            for section in report.sections:
                status_icon = {'PASS': '✅', 'FAIL': '❌', 'WARN': '⚠️', 'SKIP': '⏭️'}.get(section.status, '❓')
                output.append(f"  {status_icon} {section.name}: {section.status}")
                output.append(f"    Tests: {section.tests_passed}/{section.tests_run} passed")
                output.append(f"    Critical: {section.critical_issues}, Warnings: {section.warnings}")
                output.append(f"    Duration: {section.duration:.1f}s")
                if section.details.get('key_issues'):
                    output.append(f"    Key Issues: {', '.join(section.details['key_issues'][:2])}")
                output.append("")

            # Recommendations
            if report.recommendations:
                output.append("📋 RECOMMENDATIONS:")
                for rec in report.recommendations:
                    output.append(f"  {rec}")
                output.append("")

            # Next steps
            if report.next_steps:
                output.append("🎯 NEXT STEPS:")
                for step in report.next_steps:
                    output.append(f"  {step}")
                output.append("")

            # Readiness assessment
            if report.deployment_readiness_score >= 90:
                output.append("🎉 DEPLOYMENT READY: System is prepared for production deployment")
            elif report.deployment_readiness_score >= 70:
                output.append("⚠️ NEEDS ATTENTION: Address issues before deployment")
            else:
                output.append("🚨 NOT READY: Major issues must be resolved")

            return "\n".join(output)

    def _generate_html_report(self, report: PreflightReport) -> str:
        """Generate HTML report."""
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>NeuroCrew Lab Preflight Check Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ background-color: #f0f0f0; padding: 20px; border-radius: 5px; }}
        .status-ready {{ color: green; font-weight: bold; }}
        .status-needs-fixes {{ color: orange; font-weight: bold; }}
        .status-not-ready {{ color: red; font-weight: bold; }}
        .section {{ margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }}
        .pass {{ color: green; }}
        .warn {{ color: orange; }}
        .fail {{ color: red; }}
        .recommendations {{ background-color: #f9f9f9; padding: 15px; border-radius: 5px; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🚀 NeuroCrew Lab Preflight Check Report</h1>
        <p><strong>Environment:</strong> {report.environment.upper()}</p>
        <p><strong>Timestamp:</strong> {report.timestamp}</p>
        <p><strong>Overall Status:</strong> <span class="status-{report.overall_status.lower()}">{report.overall_status}</span></p>
        <p><strong>Readiness Score:</strong> {report.deployment_readiness_score}/100</p>
        <p><strong>Total Duration:</strong> {report.total_duration:.1f}s</p>
    </div>

    <div class="section">
        <h2>📊 Summary</h2>
        <table>
            <tr><th>Metric</th><th>Value</th></tr>
            <tr><td>Total Tests</td><td>{report.summary['total_tests']}</td></tr>
            <tr><td>Passed</td><td>{report.summary['total_passed']}</td></tr>
            <tr><td>Critical Issues</td><td>{report.summary['total_critical']}</td></tr>
            <tr><td>Warnings</td><td>{report.summary['total_warnings']}</td></tr>
        </table>
    </div>

    <div class="section">
        <h2>🔍 Section Details</h2>
        <table>
            <tr><th>Section</th><th>Status</th><th>Tests</th><th>Critical</th><th>Warnings</th><th>Duration</th></tr>
"""

        for section in report.sections:
            status_class = section.status.lower()
            html += f"""
            <tr>
                <td>{section.name}</td>
                <td class="{status_class}">{section.status}</td>
                <td>{section.tests_passed}/{section.tests_run}</td>
                <td>{section.critical_issues}</td>
                <td>{section.warnings}</td>
                <td>{section.duration:.1f}s</td>
            </tr>
"""

        html += """
        </table>
    </div>

    <div class="section recommendations">
        <h2>📋 Recommendations</h2>
        <ul>
"""

        for rec in report.recommendations:
            html += f"            <li>{rec}</li>\n"

        html += """
        </ul>
    </div>

    <div class="section">
        <h2>🎯 Next Steps</h2>
        <ul>
"""

        for step in report.next_steps:
            html += f"            <li>{step}</li>\n"

        html += """
        </ul>
    </div>

</body>
</html>
"""
        return html


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Comprehensive preflight check for NeuroCrew Lab deployment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/preflight_check.py --environment staging --comprehensive
  python scripts/preflight_check.py --fix --output json
  python scripts/preflight_check.py --report-file preflight_report.html --output html
        """
    )

    parser.add_argument(
        '--environment',
        choices=['dev', 'staging', 'prod'],
        default='dev',
        help='Target environment (default: dev)'
    )
    parser.add_argument(
        '--comprehensive',
        action='store_true',
        help='Run comprehensive validation with all checks'
    )
    parser.add_argument(
        '--fix',
        action='store_true',
        help='Attempt automatic fixes where possible'
    )
    parser.add_argument(
        '--output',
        choices=['text', 'json', 'html'],
        default='text',
        help='Output format (default: text)'
    )
    parser.add_argument(
        '--report-file',
        help='Save detailed report to file'
    )

    args = parser.parse_args()

    # Validate project root
    if not (project_root / "main.py").exists():
        print("❌ Error: Not in a valid NeuroCrew Lab project directory")
        sys.exit(1)

    # Create preflight checker
    checker = PreflightChecker(project_root, args.environment)

    try:
        # Run comprehensive check
        report = checker.run_comprehensive_check(args.comprehensive, args.fix)

        # Output report
        output = checker.output_report(report, args.output)

        if args.report_file:
            report_path = Path(args.report_file)
            with open(report_path, 'w') as f:
                f.write(output)
            print(f"📄 Report saved to: {report_path}")
            if args.output != 'text':
                print("\n" + "="*60)
                print(f"🚀 NEUROCREW LAB PREFLIGHT CHECK: {report.overall_status}")
                print(f"Readiness Score: {report.deployment_readiness_score}/100")
                print("="*60)
        else:
            print(output)

        # Exit with appropriate code
        exit_code = 0 if report.overall_status == 'READY' else \
                    1 if report.overall_status == 'NEEDS_FIXES' else 2
        sys.exit(exit_code)

    except KeyboardInterrupt:
        print("\n❌ Preflight check interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Preflight check failed: {str(e)}")
        sys.exit(1)


if __name__ == '__main__':
    main()