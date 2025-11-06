#!/usr/bin/env python3
"""
Agent Integration Validation System for NeuroCrew Lab

This script provides comprehensive validation of CLI agent integrations including:
- Agent availability and functionality testing
- Command execution and response validation
- Performance benchmarking
- Error handling and timeout testing
- Integration compatibility verification

Usage:
    python scripts/validate_agents.py [--agent AGENT_NAME] [--comprehensive] [--benchmark]

Options:
    --agent AGENT_NAME    Validate specific agent only
    --comprehensive      Run full comprehensive validation
    --benchmark          Include performance benchmarks
    --timeout N          Set timeout for agent commands (default: 30s)
    --parallel           Run validations in parallel
"""

import asyncio
import json
import os
import subprocess
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union
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
class AgentTestResult:
    """Result of an agent validation test."""
    agent_name: str
    test_name: str
    status: str  # 'PASS', 'FAIL', 'WARN', 'SKIP'
    message: str
    duration: float
    command: Optional[str] = None
    output: Optional[str] = None
    error_output: Optional[str] = None
    exit_code: Optional[int] = None
    performance_metrics: Optional[Dict[str, float]] = None
    capabilities: Optional[List[str]] = None


@dataclass
class AgentInfo:
    """Information about a CLI agent."""
    name: str
    display_name: str
    commands: List[str]
    description: str
    expected_capabilities: List[str]
    version_flag: str = '--version'
    help_flag: str = '--help'
    test_commands: Optional[List[str]] = None


class AgentValidator:
    """Comprehensive CLI agent validator."""

    def __init__(self, project_root: Path, timeout: int = 30, parallel: bool = False):
        self.project_root = project_root
        self.timeout = timeout
        self.parallel = parallel
        self.results: List[AgentTestResult] = []

        # Define agents to validate
        self.agents = {
            'qwen': AgentInfo(
                name='qwen',
                display_name='Qwen Code CLI',
                commands=['qwen', 'qwen-code'],
                description='Qwen Code CLI tool for code generation',
                expected_capabilities=['code_generation', 'text_processing'],
                test_commands=[
                    'echo "print(\'Hello\')" | qwen-code --file -',
                    'qwen-code --help'
                ]
            ),
            'gemini': AgentInfo(
                name='gemini',
                display_name='Gemini CLI',
                commands=['gemini', 'gemini-cli'],
                description='Google Gemini CLI tool',
                expected_capabilities=['text_generation', 'code_assistance'],
                test_commands=[
                    'gemini --help',
                    'gemini --version'
                ]
            ),
            'claude': AgentInfo(
                name='claude',
                display_name='Claude Code CLI',
                commands=['claude', 'claude-code'],
                description='Anthropic Claude Code CLI tool',
                expected_capabilities=['code_analysis', 'text_generation'],
                test_commands=[
                    'claude --help',
                    'claude --version'
                ]
            ),
            'opencode': AgentInfo(
                name='opencode',
                display_name='OpenCode CLI',
                commands=['opencode'],
                description='OpenCode CLI tool for code development',
                expected_capabilities=['code_completion', 'code_generation'],
                test_commands=[
                    'opencode --help',
                    'opencode --version'
                ]
            ),
            'codex': AgentInfo(
                name='codex',
                display_name='Codex CLI',
                commands=['codex'],
                description='Codex CLI tool for code assistance',
                expected_capabilities=['code_generation', 'code_completion'],
                test_commands=[
                    'codex --help',
                    'codex --version'
                ]
            )
        }

        # Performance test parameters
        self.performance_tests = {
            'simple_command': 'echo "test" | {command}',
            'code_generation': 'echo "def hello(): pass" | {command}',
            'help_command': '{command} --help'
        }

    def _run_command(self, command: str, timeout: Optional[int] = None) -> Tuple[subprocess.CompletedProcess, float]:
        """Run a command and measure execution time."""
        if timeout is None:
            timeout = self.timeout

        start_time = time.time()
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self.project_root
            )
            duration = time.time() - start_time
            return result, duration
        except subprocess.TimeoutExpired as e:
            duration = time.time() - start_time
            # Create a mock result for timeout
            timeout_result = subprocess.CompletedProcess(
                args=command,
                returncode=-1,
                stdout='',
                stderr=f'Command timed out after {timeout}s'
            )
            return timeout_result, duration
        except Exception as e:
            duration = time.time() - start_time
            error_result = subprocess.CompletedProcess(
                args=command,
                returncode=-2,
                stdout='',
                stdout=str(e)
            )
            return error_result, duration

    def test_agent_availability(self, agent_info: AgentInfo) -> AgentTestResult:
        """Test if agent CLI tool is available."""
        start_time = time.time()

        for command in agent_info.commands:
            try:
                # Check if command exists
                which_result = subprocess.run(
                    ['which', command],
                    capture_output=True,
                    text=True,
                    timeout=5
                )

                if which_result.returncode == 0:
                    duration = time.time() - start_time
                    return AgentTestResult(
                        agent_name=agent_info.name,
                        test_name="availability",
                        status="PASS",
                        message=f"{agent_info.display_name} is available via '{command}'",
                        duration=duration,
                        command=f"which {command}",
                        output=which_result.stdout.strip(),
                        exit_code=which_result.returncode
                    )
            except subprocess.TimeoutExpired:
                continue
            except Exception:
                continue

        duration = time.time() - start_time
        return AgentTestResult(
            agent_name=agent_info.name,
            test_name="availability",
            status="FAIL",
            message=f"{agent_info.display_name} is not available in PATH",
            duration=duration,
            command=f"which {agent_info.commands[0]}",
            exit_code=1
        )

    def test_agent_version(self, agent_info: AgentInfo) -> AgentTestResult:
        """Test agent version information."""
        start_time = time.time()

        # First, find working command
        working_command = None
        for cmd in agent_info.commands:
            try:
                which_result = subprocess.run(['which', cmd], capture_output=True, text=True, timeout=5)
                if which_result.returncode == 0:
                    working_command = cmd
                    break
            except:
                continue

        if not working_command:
            duration = time.time() - start_time
            return AgentTestResult(
                agent_name=agent_info.name,
                test_name="version",
                status="SKIP",
                message=f"{agent_info.display_name} not available - skipping version test",
                duration=duration
            )

        # Try version command
        version_command = f"{working_command} {agent_info.version_flag}"
        result, duration = self._run_command(version_command)

        if result.returncode == 0 and result.stdout.strip():
            return AgentTestResult(
                agent_name=agent_info.name,
                test_name="version",
                status="PASS",
                message=f"Version information retrieved",
                duration=duration,
                command=version_command,
                output=result.stdout.strip() or result.stderr.strip(),
                exit_code=result.returncode
            )
        else:
            # Try help command as fallback
            help_command = f"{working_command} {agent_info.help_flag}"
            help_result, help_duration = self._run_command(help_command)

            if help_result.returncode == 0:
                return AgentTestResult(
                    agent_name=agent_info.name,
                    test_name="version",
                    status="WARN",
                    message=f"Version command failed, but help command works",
                    duration=duration + help_duration,
                    command=f"{version_command} | {help_command}",
                    output=help_result.stdout.strip()[:200] + "..." if len(help_result.stdout) > 200 else help_result.stdout.strip(),
                    exit_code=help_result.returncode
                )
            else:
                return AgentTestResult(
                    agent_name=agent_info.name,
                    test_name="version",
                    status="FAIL",
                    message=f"Neither version nor help commands work",
                    duration=duration + help_duration,
                    command=f"{version_command} | {help_command}",
                    error_output=result.stderr.strip() or help_result.stderr.strip(),
                    exit_code=result.returncode
                )

    def test_agent_functionality(self, agent_info: AgentInfo) -> AgentTestResult:
        """Test basic agent functionality."""
        start_time = time.time()

        # Find working command
        working_command = None
        for cmd in agent_info.commands:
            try:
                which_result = subprocess.run(['which', cmd], capture_output=True, text=True, timeout=5)
                if which_result.returncode == 0:
                    working_command = cmd
                    break
            except:
                continue

        if not working_command:
            duration = time.time() - start_time
            return AgentTestResult(
                agent_name=agent_info.name,
                test_name="functionality",
                status="SKIP",
                message=f"{agent_info.display_name} not available - skipping functionality test",
                duration=duration
            )

        # Test basic functionality
        test_commands = agent_info.test_commands or [f"{working_command} --help"]

        successful_tests = 0
        total_tests = len(test_commands)
        outputs = []

        for test_cmd in test_commands:
            try:
                # Replace command placeholder
                actual_command = test_cmd.replace('{command}', working_command)
                result, _ = self._run_command(actual_command, timeout=15)

                if result.returncode == 0:
                    successful_tests += 1
                    outputs.append(result.stdout.strip()[:100])
                else:
                    outputs.append(f"Error: {result.stderr.strip()[:100]}")

            except Exception as e:
                outputs.append(f"Exception: {str(e)[:100]}")

        duration = time.time() - start_time

        if successful_tests == total_tests:
            status = "PASS"
            message = f"All {total_tests} functionality tests passed"
        elif successful_tests > 0:
            status = "WARN"
            message = f"{successful_tests}/{total_tests} functionality tests passed"
        else:
            status = "FAIL"
            message = f"All {total_tests} functionality tests failed"

        return AgentTestResult(
            agent_name=agent_info.name,
            test_name="functionality",
            status=status,
            message=message,
            duration=duration,
            command=f"Tests: {test_commands}",
            output=" | ".join(outputs),
            capabilities=agent_info.expected_capabilities if successful_tests > 0 else []
        )

    def test_agent_performance(self, agent_info: AgentInfo) -> AgentTestResult:
        """Test agent performance benchmarks."""
        start_time = time.time()

        # Find working command
        working_command = None
        for cmd in agent_info.commands:
            try:
                which_result = subprocess.run(['which', cmd], capture_output=True, text=True, timeout=5)
                if which_result.returncode == 0:
                    working_command = cmd
                    break
            except:
                continue

        if not working_command:
            duration = time.time() - start_time
            return AgentTestResult(
                agent_name=agent_info.name,
                test_name="performance",
                status="SKIP",
                message=f"{agent_info.display_name} not available - skipping performance test",
                duration=duration
            )

        performance_metrics = {}
        test_results = []

        # Run performance tests
        for test_name, test_template in self.performance_tests.items():
            try:
                command = test_template.format(command=working_command)
                result, test_duration = self._run_command(command, timeout=20)

                performance_metrics[test_name] = test_duration
                test_results.append(f"{test_name}: {test_duration:.2f}s ({'PASS' if result.returncode == 0 else 'FAIL'})")

            except Exception as e:
                performance_metrics[test_name] = -1
                test_results.append(f"{test_name}: ERROR ({str(e)[:50]})")

        duration = time.time() - start_time
        avg_response_time = sum(v for v in performance_metrics.values() if v > 0) / len([v for v in performance_metrics.values() if v > 0]) if performance_metrics else 0

        return AgentTestResult(
            agent_name=agent_info.name,
            test_name="performance",
            status="PASS" if avg_response_time > 0 and avg_response_time < 10 else "WARN" if avg_response_time > 0 else "FAIL",
            message=f"Performance tests completed (avg: {avg_response_time:.2f}s)",
            duration=duration,
            performance_metrics=performance_metrics,
            output=" | ".join(test_results)
        )

    def test_agent_error_handling(self, agent_info: AgentInfo) -> AgentTestResult:
        """Test agent error handling capabilities."""
        start_time = time.time()

        # Find working command
        working_command = None
        for cmd in agent_info.commands:
            try:
                which_result = subprocess.run(['which', cmd], capture_output=True, text=True, timeout=5)
                if which_result.returncode == 0:
                    working_command = cmd
                    break
            except:
                continue

        if not working_command:
            duration = time.time() - start_time
            return AgentTestResult(
                agent_name=agent_info.name,
                test_name="error_handling",
                status="SKIP",
                message=f"{agent_info.display_name} not available - skipping error handling test",
                duration=duration
            )

        # Test error scenarios
        error_tests = [
            (f"{working_command} --invalid-flag", "Invalid flag test"),
            (f"{working_command} /nonexistent/file", "Nonexistent file test"),
            ("echo '' | " + working_command, "Empty input test")
        ]

        handled_errors = 0
        total_tests = len(error_tests)
        error_responses = []

        for test_command, test_name in error_tests:
            try:
                result, _ = self._run_command(test_command, timeout=10)

                # Check if the tool handles the error gracefully (non-zero exit code with meaningful message)
                if result.returncode != 0 and len(result.stderr.strip()) > 0:
                    handled_errors += 1
                    error_responses.append(f"{test_name}: Graceful")
                else:
                    error_responses.append(f"{test_name}: Poor handling")

            except subprocess.TimeoutExpired:
                error_responses.append(f"{test_name}: Timeout")
            except Exception:
                error_responses.append(f"{test_name}: Exception")

        duration = time.time() - start_time

        if handled_errors == total_tests:
            status = "PASS"
            message = f"Error handling test passed ({handled_errors}/{total_tests})"
        elif handled_errors > 0:
            status = "WARN"
            message = f"Partial error handling ({handled_errors}/{total_tests})"
        else:
            status = "FAIL"
            message = f"Poor error handling ({handled_errors}/{total_tests})"

        return AgentTestResult(
            agent_name=agent_info.name,
            test_name="error_handling",
            status=status,
            message=message,
            duration=duration,
            output=" | ".join(error_responses)
        )

    def validate_agent(self, agent_name: str, comprehensive: bool = False, benchmark: bool = False) -> List[AgentTestResult]:
        """Validate a specific agent."""
        if agent_name not in self.agents:
            raise ValueError(f"Unknown agent: {agent_name}")

        agent_info = self.agents[agent_name]
        results = []

        logger.info(f"Validating {agent_info.display_name}...")

        # Core tests
        tests = [
            self.test_agent_availability,
            self.test_agent_version,
            self.test_agent_functionality,
            self.test_agent_error_handling
        ]

        # Add performance test if requested
        if benchmark:
            tests.append(self.test_agent_performance)

        # Run tests
        for test_func in tests:
            try:
                result = test_func(agent_info)
                results.append(result)

                # Log result
                status_icon = {'PASS': '✅', 'FAIL': '❌', 'WARN': '⚠️', 'SKIP': '⏭️'}.get(result.status, '❓')
                logger.info(f"  {status_icon} {result.test_name}: {result.message} ({result.duration:.2f}s)")

            except Exception as e:
                error_result = AgentTestResult(
                    agent_name=agent_name,
                    test_name=f"{test_func.__name__}_crash",
                    status="FAIL",
                    message=f"Test crashed: {str(e)}",
                    duration=0.0
                )
                results.append(error_result)
                logger.error(f"  ❌ {test_func.__name__} crashed: {str(e)}")

        return results

    def validate_all_agents(self, comprehensive: bool = False, benchmark: bool = False) -> List[AgentTestResult]:
        """Validate all agents."""
        logger.info("Starting comprehensive agent validation...")

        all_results = []

        if self.parallel:
            # Run validations in parallel
            with ThreadPoolExecutor(max_workers=3) as executor:
                future_to_agent = {
                    executor.submit(self.validate_agent, agent_name, comprehensive, benchmark): agent_name
                    for agent_name in self.agents.keys()
                }

                for future in as_completed(future_to_agent):
                    agent_name = future_to_agent[future]
                    try:
                        agent_results = future.result()
                        all_results.extend(agent_results)
                    except Exception as e:
                        logger.error(f"Validation failed for {agent_name}: {str(e)}")
        else:
            # Run validations sequentially
            for agent_name in self.agents.keys():
                try:
                    agent_results = self.validate_agent(agent_name, comprehensive, benchmark)
                    all_results.extend(agent_results)
                except Exception as e:
                    logger.error(f"Validation failed for {agent_name}: {str(e)}")

        return all_results

    def generate_report(self, results: List[AgentTestResult]) -> Dict[str, Any]:
        """Generate comprehensive validation report."""
        # Group results by agent
        agent_results = {}
        for result in results:
            if result.agent_name not in agent_results:
                agent_results[result.agent_name] = []
            agent_results[result.agent_name].append(result)

        # Calculate statistics
        total_tests = len(results)
        passed = len([r for r in results if r.status == 'PASS'])
        failed = len([r for r in results if r.status == 'FAIL'])
        warned = len([r for r in results if r.status == 'WARN'])
        skipped = len([r for r in results if r.status == 'SKIP'])

        # Agent summary
        agent_summary = {}
        for agent_name, agent_tests in agent_results.items():
            agent_info = self.agents.get(agent_name)
            agent_summary[agent_name] = {
                'display_name': agent_info.display_name if agent_info else agent_name,
                'total_tests': len(agent_tests),
                'passed': len([t for t in agent_tests if t.status == 'PASS']),
                'failed': len([t for t in agent_tests if t.status == 'FAIL']),
                'warnings': len([t for t in agent_tests if t.status == 'WARN']),
                'available': any(t.status == 'PASS' and t.test_name == 'availability' for t in agent_tests),
                'capabilities': list(set([cap for t in agent_tests if t.capabilities for cap in t.capabilities]))
            }

        # Performance summary
        performance_metrics = {}
        for result in results:
            if result.test_name == 'performance' and result.performance_metrics:
                performance_metrics[result.agent_name] = result.performance_metrics

        # Overall status
        overall_status = 'PASS'
        if failed > 0:
            overall_status = 'FAIL'
        elif warned > 0:
            overall_status = 'WARN'

        return {
            'timestamp': str(Path().cwd()),
            'overall_status': overall_status,
            'summary': {
                'total_agents': len(self.agents),
                'available_agents': len([a for a in agent_summary.values() if a['available']]),
                'total_tests': total_tests,
                'passed': passed,
                'failed': failed,
                'warned': warned,
                'skipped': skipped
            },
            'agent_summary': agent_summary,
            'performance_metrics': performance_metrics,
            'detailed_results': [asdict(r) for r in results],
            'recommendations': self._generate_recommendations(agent_summary, results)
        }

    def _generate_recommendations(self, agent_summary: Dict, results: List[AgentTestResult]) -> List[str]:
        """Generate recommendations based on validation results."""
        recommendations = []

        unavailable_agents = [name for name, info in agent_summary.items() if not info['available']]
        failing_agents = [name for name, info in agent_summary.items() if info['failed'] > 0]

        if unavailable_agents:
            recommendations.extend([
                "🚦 AGENT INSTALLATION:",
                f"  • Install missing CLI agents: {', '.join(unavailable_agents)}",
                "  • Ensure agents are in system PATH",
                "  • Check agent documentation for installation instructions"
            ])

        if failing_agents:
            recommendations.extend([
                "⚠️ AGENT CONFIGURATION:",
                f"  • Fix configuration issues: {', '.join(failing_agents)}",
                "  • Update agent versions if compatibility issues detected",
                "  • Check environment variables and configuration files"
            ])

        # Performance recommendations
        slow_agents = []
        for result in results:
            if result.test_name == 'performance' and result.performance_metrics:
                avg_time = sum(v for v in result.performance_metrics.values() if v > 0) / len([v for v in result.performance_metrics.values() if v > 0])
                if avg_time > 5:  # More than 5 seconds average
                    slow_agents.append(result.agent_name)

        if slow_agents:
            recommendations.extend([
                "⚡ PERFORMANCE OPTIMIZATION:",
                f"  • Consider optimizing slow agents: {', '.join(slow_agents)}",
                "  • Check system resources and agent configuration",
                "  • Monitor agent performance during operation"
            ])

        # General recommendations
        available_count = len([info for info in agent_summary.values() if info['available']])
        total_count = len(agent_summary)

        if available_count < total_count:
            recommendations.extend([
                f"\n📊 AVAILABILITY: {available_count}/{total_count} agents available",
                "  • Core functionality may work with available agents",
                "  • Consider installing missing agents for full functionality"
            ])
        else:
            recommendations.append("\n✅ All agents are available and configured correctly")

        return recommendations


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Validate CLI agent integrations")
    parser.add_argument('--agent', help='Validate specific agent only')
    parser.add_argument('--comprehensive', action='store_true', help='Run comprehensive validation')
    parser.add_argument('--benchmark', action='store_true', help='Include performance benchmarks')
    parser.add_argument('--timeout', type=int, default=30, help='Command timeout in seconds')
    parser.add_argument('--parallel', action='store_true', help='Run validations in parallel')
    parser.add_argument('--output', '-o', help='Output report file')
    parser.add_argument('--json', action='store_true', help='Output JSON format')

    args = parser.parse_args()

    # Get project root
    project_root = Path(__file__).parent.parent
    if not (project_root / "main.py").exists():
        print("❌ Error: Not in a valid NeuroCrew Lab project directory")
        sys.exit(1)

    # Create validator
    validator = AgentValidator(
        project_root=project_root,
        timeout=args.timeout,
        parallel=args.parallel
    )

    print("🤖 Starting agent validation...\n")

    # Run validations
    try:
        if args.agent:
            if args.agent not in validator.agents:
                print(f"❌ Unknown agent: {args.agent}")
                print(f"Available agents: {', '.join(validator.agents.keys())}")
                sys.exit(1)

            results = validator.validate_agent(args.agent, args.comprehensive, args.benchmark)
        else:
            results = validator.validate_all_agents(args.comprehensive, args.benchmark)

    except KeyboardInterrupt:
        print("\n❌ Agent validation interrupted")
        sys.exit(1)

    # Generate report
    report = validator.generate_report(results)

    # Output results
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print("="*60)
        print(f"🤖 AGENT VALIDATION COMPLETE: {report['overall_status']}")
        print("="*60)

        # Summary
        summary = report['summary']
        print(f"Available Agents: {summary['available_agents']}/{summary['total_agents']}")
        print(f"Total Tests: {summary['total_tests']}")
        print(f"✅ Passed: {summary['passed']}")
        print(f"❌ Failed: {summary['failed']}")
        print(f"⚠️ Warnings: {summary['warned']}")
        print(f"⏭️ Skipped: {summary['skipped']}")

        # Agent details
        print("\n📊 Agent Status:")
        for agent_name, info in report['agent_summary'].items():
            status_icon = "✅" if info['available'] else "❌"
            print(f"  {status_icon} {info['display_name']}: {info['passed']}/{info['total_tests']} tests passed")
            if info['capabilities']:
                print(f"      Capabilities: {', '.join(info['capabilities'])}")

        # Performance summary
        if report['performance_metrics']:
            print("\n⚡ Performance Summary:")
            for agent, metrics in report['performance_metrics'].items():
                avg_time = sum(v for v in metrics.values() if v > 0) / len([v for v in metrics.values() if v > 0]) if metrics else 0
                print(f"  {agent}: {avg_time:.2f}s average response time")

        # Recommendations
        if report['recommendations']:
            print("\n📋 RECOMMENDATIONS:")
            for rec in report['recommendations']:
                print(rec)

    # Save report if requested
    if args.output:
        with open(args.output, 'w') as f:
            if args.json:
                json.dump(report, f, indent=2, default=str)
            else:
                f.write(f"NeuroCrew Lab Agent Validation Report\n")
                f.write(f"Generated: {report['timestamp']}\n")
                f.write(f"Status: {report['overall_status']}\n\n")
                for result in results:
                    f.write(f"{result.agent_name} - {result.test_name}: {result.status}\n")
                    f.write(f"  {result.message}\n\n")

    # Exit with appropriate code
    exit_code = 0 if report['overall_status'] in ['PASS', 'WARN'] else 1
    sys.exit(exit_code)


if __name__ == '__main__':
    main()