#!/usr/bin/env python3
"""
External Dependencies Testing Suite for NeuroCrew Lab

This script performs comprehensive testing of all external dependencies including:
- CLI agent functionality and availability
- Network connectivity and API endpoints
- External service integrations
- Resource availability and performance

Usage:
    python scripts/test_external_deps.py [--comprehensive] [--performance] [--network-only]

Options:
    --comprehensive    Run all tests including performance benchmarks
    --performance      Focus on performance and load testing
    --network-only     Test only network connectivity endpoints
    --timeout N        Set timeout for individual tests (default: 30s)
    --parallel         Run tests in parallel where possible
"""

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Callable
import urllib.request
import urllib.error
import ssl
import logging

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    import psutil
except ImportError:
    psutil = None
    print("⚠️ psutil not available - some performance tests will be skipped")

try:
    import aiohttp
except ImportError:
    aiohttp = None
    print("⚠️ aiohttp not available - async network tests will be skipped")

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class DependencyTestResult:
    """Result of an external dependency test."""

    name: str
    category: str
    status: str  # 'PASS', 'FAIL', 'WARN', 'SKIP'
    message: str
    duration: float
    details: Optional[Dict[str, Any]] = None
    performance_metrics: Optional[Dict[str, float]] = None
    error_traceback: Optional[str] = None


class ExternalDepsTester:
    """Comprehensive external dependencies tester."""

    def __init__(self, project_root: Path, timeout: int = 30, parallel: bool = False):
        self.project_root = project_root
        self.timeout = timeout
        self.parallel = parallel
        self.results: List[DependencyTestResult] = []
        self.test_start_time = time.time()

        # Test configuration
        self.telegram_api_hosts = ["api.telegram.org", "core.telegram.org", "t.me"]

        self.cli_agents = {
            "qwen": ["qwen", "qwen-code"],
            "gemini": ["gemini", "gemini-cli"],
            "claude": ["claude", "claude-code"],
            "opencode": ["opencode"],
            "codex": ["codex"],
        }

        self.test_endpoints = {
            "telegram_api": "https://api.telegram.org/bot{token}/getMe",
            "google_dns": "8.8.8.8:53",
            "cloudflare_dns": "1.1.1.1:53",
        }

    def _run_test(self, test_func: Callable, *args, **kwargs) -> DependencyTestResult:
        """Run a test function and measure performance."""
        start_time = time.time()
        test_name = test_func.__name__.replace("test_", "")

        try:
            result = test_func(*args, **kwargs)
            duration = time.time() - start_time

            if isinstance(result, DependencyTestResult):
                result.duration = duration
                return result
            else:
                return DependencyTestResult(
                    name=test_name,
                    category="general",
                    status="PASS",
                    message="Test completed successfully",
                    duration=duration,
                    details={"result": result},
                )

        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Test {test_name} failed: {str(e)}")

            return DependencyTestResult(
                name=test_name,
                category="general",
                status="FAIL",
                message=f"Test failed: {str(e)}",
                duration=duration,
                error_traceback=str(e),
            )

    def test_cli_agent_availability(self) -> DependencyTestResult:
        """Test CLI agent availability and basic functionality."""
        result = DependencyTestResult(
            name="CLI Agent Availability",
            category="cli_agents",
            status="PASS",
            message="CLI agents tested",
            duration=0.0,
            details={"agents": {}},
        )

        agent_results = {}
        failed_agents = []
        working_agents = []

        for agent_name, commands in self.cli_agents.items():
            agent_info = {
                "found": False,
                "working_command": None,
                "version": None,
                "response_time": None,
                "error": None,
            }

            for cmd in commands:
                try:
                    # Test command availability
                    cmd_path = subprocess.run(
                        ["which", cmd],
                        capture_output=True,
                        text=True,
                        timeout=self.timeout,
                    )

                    if cmd_path.returncode == 0:
                        agent_info["found"] = True
                        agent_info["working_command"] = cmd

                        # Test command execution
                        start_time = time.time()
                        version_result = subprocess.run(
                            [cmd, "--version"],
                            capture_output=True,
                            text=True,
                            timeout=self.timeout,
                        )
                        response_time = time.time() - start_time

                        if version_result.returncode == 0:
                            agent_info["version"] = (
                                version_result.stdout.strip()
                                or version_result.stderr.strip()
                            )
                            agent_info["response_time"] = response_time
                            working_agents.append(agent_name)
                        else:
                            # Try help command
                            help_result = subprocess.run(
                                [cmd, "--help"],
                                capture_output=True,
                                text=True,
                                timeout=self.timeout,
                            )
                            if help_result.returncode == 0:
                                agent_info["version"] = "Help command available"
                                agent_info["response_time"] = response_time
                                working_agents.append(agent_name)
                            else:
                                agent_info["error"] = (
                                    "Command exists but failed to execute"
                                )
                                failed_agents.append(agent_name)
                        break

                except subprocess.TimeoutExpired:
                    agent_info["error"] = "Command timeout"
                    break
                except Exception as e:
                    agent_info["error"] = str(e)
                    continue

            agent_results[agent_name] = agent_info

        # Determine overall status
        if not working_agents:
            result.status = "FAIL"
            result.message = "No CLI agents are available"
        elif failed_agents:
            result.status = "WARN"
            result.message = f"Some CLI agents unavailable: {', '.join(failed_agents)}"
        else:
            result.message = f"All {len(working_agents)} CLI agents available"

        result.details = {
            "agents": agent_results,
            "working_count": len(working_agents),
            "failed_count": len(failed_agents),
            "working_agents": working_agents,
            "failed_agents": failed_agents,
        }

        return result

    def test_network_connectivity(self) -> DependencyTestResult:
        """Test network connectivity to required endpoints."""
        result = DependencyTestResult(
            name="Network Connectivity",
            category="network",
            status="PASS",
            message="Network connectivity tested",
            duration=0.0,
            details={"hosts": {}},
        )

        connectivity_results = {}
        failed_hosts = []

        # Test Telegram API hosts
        for host in self.telegram_api_hosts:
            host_info = {
                "dns_resolution": False,
                "tcp_connection": False,
                "response_time": None,
                "error": None,
            }

            try:
                # DNS resolution
                start_time = time.time()
                ip_addresses = socket.gethostbyname_ex(host)[2]
                dns_time = time.time() - start_time
                host_info["dns_resolution"] = True
                host_info["ip_addresses"] = ip_addresses
                host_info["dns_time"] = dns_time

                # TCP connection test
                start_time = time.time()
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(10)
                connection_result = sock.connect_ex((host, 443))
                sock.close()
                tcp_time = time.time() - start_time
                host_info["response_time"] = tcp_time
                host_info["tcp_connection"] = connection_result == 0

                if connection_result != 0:
                    failed_hosts.append(host)
                    host_info["error"] = f"TCP connection failed: {connection_result}"

            except socket.gaierror as e:
                host_info["error"] = f"DNS resolution failed: {str(e)}"
                failed_hosts.append(host)
            except Exception as e:
                host_info["error"] = str(e)
                failed_hosts.append(host)

            connectivity_results[host] = host_info

        # Test DNS servers
        dns_servers = [("Google DNS", "8.8.8.8", 53), ("Cloudflare DNS", "1.1.1.1", 53)]

        for name, ip, port in dns_servers:
            try:
                start_time = time.time()
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.settimeout(5)
                sock.sendto(b"test", (ip, port))
                sock.close()
                response_time = time.time() - start_time

                connectivity_results[f"dns_{name.lower().replace(' ', '_')}"] = {
                    "tcp_connection": True,
                    "response_time": response_time,
                    "error": None,
                }
            except Exception as e:
                connectivity_results[f"dns_{name.lower().replace(' ', '_')}"] = {
                    "tcp_connection": False,
                    "response_time": None,
                    "error": str(e),
                }

        # Check for proxy configuration
        proxy_vars = ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]
        proxy_config = {var: os.getenv(var) for var in proxy_vars if os.getenv(var)}
        connectivity_results["proxy_config"] = proxy_config

        if failed_hosts:
            result.status = "FAIL"
            result.message = f"Cannot connect to: {', '.join(failed_hosts)}"
        else:
            result.message = "All network endpoints reachable"

        result.details = {
            "hosts": connectivity_results,
            "successful_hosts": len(
                [
                    h
                    for h in connectivity_results.values()
                    if h.get("tcp_connection", False)
                ]
            ),
            "failed_hosts": failed_hosts,
        }

        return result

    async def test_telegram_api_async(self) -> DependencyTestResult:
        """Test Telegram API connectivity asynchronously."""
        result = DependencyTestResult(
            name="Telegram API Async Test",
            category="network",
            status="PASS",
            message="Telegram API async test completed",
            duration=0.0,
        )

        if not aiohttp:
            result.status = "SKIP"
            result.message = "aiohttp not available - skipping async test"
            return result

        try:
            # Load bot token from app.config
            env_file = self.project_root / ".env"
            if not env_file.exists():
                result.status = "SKIP"
                result.message = ".env file not found - skipping API test"
                return result

            # Parse .env file
            with open(env_file, "r") as f:
                for line in f:
                    if line.startswith("TELEGRAM_BOT_TOKEN="):
                        token = line.split("=", 1)[1].strip()
                        break
                else:
                    result.status = "SKIP"
                    result.message = "TELEGRAM_BOT_TOKEN not found in .env file"
                    return result

            if token == "your_bot_token_here":
                result.status = "SKIP"
                result.message = "Using placeholder bot token - skipping API test"
                return result

            # Test API endpoint
            url = f"https://api.telegram.org/bot{token}/getMe"

            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                start_time = time.time()
                async with session.get(url) as response:
                    response_time = time.time() - start_time
                    response_data = await response.json()

                    if response.status == 200:
                        result.status = "PASS"
                        result.message = f"Telegram API working - bot: {response_data.get('result', {}).get('username', 'Unknown')}"
                        result.details = {
                            "response_time": response_time,
                            "bot_info": response_data.get("result", {}),
                            "api_status": response.status,
                        }
                    else:
                        result.status = "FAIL"
                        result.message = f"Telegram API error: {response.status}"
                        result.details = {
                            "response_time": response_time,
                            "error_data": response_data,
                            "api_status": response.status,
                        }

        except asyncio.TimeoutError:
            result.status = "FAIL"
            result.message = "Telegram API request timeout"
        except Exception as e:
            result.status = "FAIL"
            result.message = f"Telegram API test failed: {str(e)}"

        return result

    def test_ssl_certificates(self) -> DependencyTestResult:
        """Test SSL certificate validation for Telegram endpoints."""
        result = DependencyTestResult(
            name="SSL Certificate Validation",
            category="security",
            status="PASS",
            message="SSL certificates validated",
            duration=0.0,
            details={"hosts": {}},
        )

        ssl_results = {}
        failed_certs = []

        for host in ["api.telegram.org"]:
            try:
                context = ssl.create_default_context()

                start_time = time.time()
                with socket.create_connection(
                    (host, 443), timeout=self.timeout
                ) as sock:
                    with context.wrap_socket(sock, server_hostname=host) as ssock:
                        cert = ssock.getpeercert()
                        connection_time = time.time() - start_time

                        ssl_results[host] = {
                            "valid": True,
                            "connection_time": connection_time,
                            "cert_subject": dict(x[0] for x in cert.get("subject", [])),
                            "cert_issuer": dict(x[0] for x in cert.get("issuer", [])),
                            "cert_version": cert.get("version"),
                            "cert_serial": cert.get("serialNumber"),
                            "not_before": cert.get("notBefore"),
                            "not_after": cert.get("notAfter"),
                        }

            except ssl.SSLCertVerificationError as e:
                ssl_results[host] = {
                    "valid": False,
                    "error": f"SSL certificate verification failed: {str(e)}",
                }
                failed_certs.append(host)
            except Exception as e:
                ssl_results[host] = {"valid": False, "error": str(e)}
                failed_certs.append(host)

        if failed_certs:
            result.status = "FAIL"
            result.message = f"SSL certificate issues for: {', '.join(failed_certs)}"
        else:
            result.message = "All SSL certificates valid"

        result.details = {
            "hosts": ssl_results,
            "valid_certs": len(
                [h for h in ssl_results.values() if h.get("valid", False)]
            ),
            "failed_certs": failed_certs,
        }

        return result

    def test_system_resources(self) -> DependencyTestResult:
        """Test system resource availability and performance."""
        result = DependencyTestResult(
            name="System Resources Test",
            category="performance",
            status="PASS",
            message="System resources tested",
            duration=0.0,
        )

        if not psutil:
            result.status = "SKIP"
            result.message = "psutil not available - skipping resource test"
            return result

        try:
            # CPU tests
            cpu_count = psutil.cpu_count()
            cpu_percent = psutil.cpu_percent(interval=1)

            # Memory tests
            memory = psutil.virtual_memory()

            # Disk tests
            disk = psutil.disk_usage(str(self.project_root))
            disk_io = psutil.disk_io_counters()

            # Network tests
            network = psutil.net_io_counters()

            # Resource benchmarks
            warnings = []
            if memory.available < 512 * 1024 * 1024:  # 512MB
                warnings.append("Low available memory")
            if disk.free < 1024 * 1024 * 1024:  # 1GB
                warnings.append("Low disk space")
            if cpu_percent > 90:
                warnings.append("High CPU usage")

            result.details = {
                "cpu": {"count": cpu_count, "percent": cpu_percent},
                "memory": {
                    "total": memory.total,
                    "available": memory.available,
                    "percent": memory.percent,
                    "used": memory.used,
                },
                "disk": {
                    "total": disk.total,
                    "used": disk.used,
                    "free": disk.free,
                    "percent": (disk.used / disk.total) * 100,
                },
                "network": {
                    "bytes_sent": network.bytes_sent,
                    "bytes_recv": network.bytes_recv,
                    "packets_sent": network.packets_sent,
                    "packets_recv": network.packets_recv,
                },
                "warnings": warnings,
            }

            if warnings:
                result.status = "WARN"
                result.message = f"Resource warnings: {', '.join(warnings)}"

            result.performance_metrics = {
                "cpu_benchmark": cpu_count,
                "memory_available_gb": memory.available / (1024**3),
                "disk_free_gb": disk.free / (1024**3),
            }

        except Exception as e:
            result.status = "FAIL"
            result.message = f"System resource test failed: {str(e)}"

        return result

    def test_file_system_performance(self) -> DependencyTestResult:
        """Test file system performance for data storage."""
        result = DependencyTestResult(
            name="File System Performance",
            category="performance",
            status="PASS",
            message="File system performance tested",
            duration=0.0,
        )

        try:
            data_dir = self.project_root / "data"
            data_dir.mkdir(exist_ok=True)

            test_file = data_dir / "performance_test.tmp"

            # Write performance test
            test_data = b"x" * 1024 * 1024  # 1MB test data
            write_start = time.time()
            with open(test_file, "wb") as f:
                f.write(test_data)
            write_time = time.time() - write_start

            # Read performance test
            read_start = time.time()
            with open(test_file, "rb") as f:
                read_data = f.read()
            read_time = time.time() - read_start

            # Cleanup
            test_file.unlink()

            # Calculate speeds
            write_speed_mbps = (1.0 / write_time) if write_time > 0 else 0
            read_speed_mbps = (1.0 / read_time) if read_time > 0 else 0

            # Performance evaluation
            warnings = []
            if write_speed_mbps < 10:  # Less than 10MB/s write
                warnings.append("Slow write performance")
            if read_speed_mbps < 50:  # Less than 50MB/s read
                warnings.append("Slow read performance")

            result.details = {
                "write_speed_mbps": write_speed_mbps,
                "read_speed_mbps": read_speed_mbps,
                "write_time_s": write_time,
                "read_time_s": read_time,
                "test_data_size_mb": 1.0,
            }

            result.performance_metrics = {
                "write_throughput_mbps": write_speed_mbps,
                "read_throughput_mbps": read_speed_mbps,
                "write_latency_ms": write_time * 1000,
                "read_latency_ms": read_time * 1000,
            }

            if warnings:
                result.status = "WARN"
                result.message = f"Performance warnings: {', '.join(warnings)}"
            else:
                result.message = f"File system performance - Write: {write_speed_mbps:.1f}MB/s, Read: {read_speed_mbps:.1f}MB/s"

        except Exception as e:
            result.status = "FAIL"
            result.message = f"File system performance test failed: {str(e)}"

        return result

    def test_configuration_load(self) -> DependencyTestResult:
        """Test configuration loading and validation."""
        result = DependencyTestResult(
            name="Configuration Load Test",
            category="configuration",
            status="PASS",
            message="Configuration loaded successfully",
            duration=0.0,
        )

        try:
            # Test config import
            sys.path.insert(0, str(self.project_root))
            import config

            # Validate configuration
            config.Config.validate()

            # Check critical settings
            bot_token = config.Config.TELEGRAM_BOT_TOKEN
            cli_paths = config.Config.CLI_PATHS
            agent_sequence = config.Config.AGENT_SEQUENCE

            result.details = {
                "bot_token_set": bool(bot_token and bot_token != "your_bot_token_here"),
                "cli_paths_count": len(cli_paths),
                "agent_sequence": agent_sequence,
                "max_conversation_length": config.Config.MAX_CONVERSATION_LENGTH,
                "agent_timeout": config.Config.AGENT_TIMEOUT,
                "log_level": config.Config.LOG_LEVEL,
            }

            if not bot_token or bot_token == "your_bot_token_here":
                result.status = "WARN"
                result.message = "Telegram bot token not configured"

        except Exception as e:
            result.status = "FAIL"
            result.message = f"Configuration load failed: {str(e)}"

        return result

    async def run_all_tests(
        self,
        comprehensive: bool = False,
        performance_only: bool = False,
        network_only: bool = False,
    ) -> List[DependencyTestResult]:
        """Run all external dependency tests."""
        print("🧪 Starting comprehensive external dependency testing...\n")

        # Determine which tests to run
        tests_to_run = []

        if network_only:
            tests_to_run = [
                ("network", self.test_network_connectivity),
                ("async", self.test_telegram_api_async),
                ("ssl", self.test_ssl_certificates),
            ]
        elif performance_only:
            tests_to_run = [
                ("resources", self.test_system_resources),
                ("filesystem", self.test_file_system_performance),
            ]
        else:
            tests_to_run = [
                ("cli_agents", self.test_cli_agent_availability),
                ("network", self.test_network_connectivity),
                ("async", self.test_telegram_api_async),
                ("ssl", self.test_ssl_certificates),
                ("config", self.test_configuration_load),
            ]

            if comprehensive:
                tests_to_run.extend(
                    [
                        ("resources", self.test_system_resources),
                        ("filesystem", self.test_file_system_performance),
                    ]
                )

        # Run tests
        if self.parallel:
            with ThreadPoolExecutor(max_workers=4) as executor:
                future_to_test = {}

                for test_type, test_func in tests_to_run:
                    if asyncio.iscoroutinefunction(test_func):
                        # Run async tests in event loop
                        future = executor.submit(asyncio.run, test_func())
                    else:
                        future = executor.submit(self._run_test, test_func)
                    future_to_test[future] = test_type

                for future in as_completed(future_to_test):
                    test_type = future_to_test[future]
                    try:
                        result = future.result()
                        if isinstance(result, DependencyTestResult):
                            result.category = test_type
                        self.results.append(result)
                    except Exception as e:
                        error_result = DependencyTestResult(
                            name=f"{test_type}_crash",
                            category=test_type,
                            status="FAIL",
                            message=f"Test crashed: {str(e)}",
                            duration=0.0,
                        )
                        self.results.append(error_result)
        else:
            # Run tests sequentially
            for test_type, test_func in tests_to_run:
                if asyncio.iscoroutinefunction(test_func):
                    result = await test_func()
                    result.category = test_type
                else:
                    result = self._run_test(test_func)
                    result.category = test_type

                self.results.append(result)

                # Print immediate result
                status_icon = {
                    "PASS": "✅",
                    "FAIL": "❌",
                    "WARN": "⚠️",
                    "SKIP": "⏭️",
                }.get(result.status, "❓")
                print(
                    f"{status_icon} {result.name}: {result.message} ({result.duration:.2f}s)"
                )

        return self.results

    def generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive test report."""
        total_duration = time.time() - self.test_start_time
        passed = len([r for r in self.results if r.status == "PASS"])
        failed = len([r for r in self.results if r.status == "FAIL"])
        warned = len([r for r in self.results if r.status == "WARN"])
        skipped = len([r for r in self.results if r.status == "SKIP"])

        overall_status = "PASS"
        if failed > 0:
            overall_status = "FAIL"
        elif warned > 0:
            overall_status = "WARN"

        # Performance summary
        performance_metrics = {}
        for result in self.results:
            if result.performance_metrics:
                performance_metrics[result.name] = result.performance_metrics

        return {
            "timestamp": str(Path().cwd()),
            "total_duration": total_duration,
            "overall_status": overall_status,
            "summary": {
                "total": len(self.results),
                "passed": passed,
                "failed": failed,
                "warned": warned,
                "skipped": skipped,
            },
            "categories": {
                category: {
                    "count": len([r for r in self.results if r.category == category]),
                    "passed": len(
                        [
                            r
                            for r in self.results
                            if r.category == category and r.status == "PASS"
                        ]
                    ),
                    "failed": len(
                        [
                            r
                            for r in self.results
                            if r.category == category and r.status == "FAIL"
                        ]
                    ),
                }
                for category in set(r.category for r in self.results)
            },
            "performance_metrics": performance_metrics,
            "results": [asdict(r) for r in self.results],
            "recommendations": self._generate_recommendations(),
        }

    def _generate_recommendations(self) -> List[str]:
        """Generate recommendations based on test results."""
        recommendations = []

        failed_results = [r for r in self.results if r.status == "FAIL"]
        warned_results = [r for r in self.results if r.status == "WARN"]

        # Critical failures
        if failed_results:
            recommendations.append("🚨 CRITICAL FAILURES - Must be resolved:")
            for result in failed_results:
                recommendations.append(f"  • {result.name}: {result.message}")

        # Warnings
        if warned_results:
            recommendations.append("\n⚠️ WARNINGS - Should be addressed:")
            for result in warned_results:
                recommendations.append(f"  • {result.name}: {result.message}")

        # Performance recommendations
        performance_issues = [
            r
            for r in self.results
            if r.category == "performance" and r.status == "WARN"
        ]
        if performance_issues:
            recommendations.append("\n⚡ PERFORMANCE OPTIMIZATIONS:")
            recommendations.append("  • Consider upgrading system resources")
            recommendations.append("  • Optimize file system performance")
            recommendations.append("  • Monitor resource usage during operation")

        # Network recommendations
        network_issues = [
            r for r in self.results if r.category == "network" and r.status != "PASS"
        ]
        if network_issues:
            recommendations.append("\n🌐 NETWORK CONNECTIVITY:")
            recommendations.append("  • Check firewall settings")
            recommendations.append("  • Verify proxy configuration")
            recommendations.append("  • Test DNS resolution")

        return recommendations


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Test NeuroCrew Lab external dependencies"
    )
    parser.add_argument(
        "--comprehensive", action="store_true", help="Run comprehensive tests"
    )
    parser.add_argument(
        "--performance", action="store_true", help="Run performance tests only"
    )
    parser.add_argument(
        "--network-only", action="store_true", help="Run network tests only"
    )
    parser.add_argument(
        "--timeout", type=int, default=30, help="Test timeout in seconds"
    )
    parser.add_argument("--parallel", action="store_true", help="Run tests in parallel")
    parser.add_argument("--output", "-o", help="Output report to file")
    parser.add_argument("--json", action="store_true", help="Output JSON format")

    args = parser.parse_args()

    # Get project root
    project_root = Path(__file__).parent.parent
    if not (project_root / "main.py").exists():
        print("❌ Error: Not in a valid NeuroCrew Lab project directory")
        sys.exit(1)

    # Create tester
    tester = ExternalDepsTester(
        project_root=project_root, timeout=args.timeout, parallel=args.parallel
    )

    # Run tests
    results = await tester.run_all_tests(
        comprehensive=args.comprehensive,
        performance_only=args.performance,
        network_only=args.network_only,
    )

    # Generate report
    report = tester.generate_report()

    # Output results
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("\n" + "=" * 60)
        print(f"🏁 EXTERNAL DEPENDENCIES TEST COMPLETE: {report['overall_status']}")
        print("=" * 60)
        print(f"Total Duration: {report['total_duration']:.2f}s")
        print(f"Total Tests: {report['summary']['total']}")
        print(f"✅ Passed: {report['summary']['passed']}")
        print(f"❌ Failed: {report['summary']['failed']}")
        print(f"⚠️ Warnings: {report['summary']['warned']}")
        print(f"⏭️ Skipped: {report['summary']['skipped']}")

        # Category breakdown
        print("\n📊 Results by Category:")
        for category, stats in report["categories"].items():
            print(f"  {category}: {stats['passed']}/{stats['count']} passed")

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
                f.write(f"NeuroCrew Lab External Dependencies Test Report\n")
                f.write(f"Generated: {report['timestamp']}\n")
                f.write(f"Duration: {report['total_duration']:.2f}s\n")
                f.write(f"Status: {report['overall_status']}\n\n")
                for result in results:
                    f.write(f"{result.status}: {result.name}\n")
                    f.write(f"  {result.message}\n\n")

    # Exit with appropriate code
    exit_code = 0 if report["overall_status"] in ["PASS", "WARN"] else 1
    sys.exit(exit_code)


if __name__ == "__main__":
    asyncio.run(main())
