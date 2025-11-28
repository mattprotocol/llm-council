#!/usr/bin/env -S uv run python
"""
Automated Test Runner for LLM Council

This flexible testing framework:
1. Automatically starts/stops the server
2. Runs test scenarios defined in YAML/JSON
3. Evaluates results against expected outcomes
4. Iterates on fixes if tests fail
5. Reports results with detailed diagnostics

Usage:
    uv run -m tests.test_runner [--scenario NAME] [--max-iterations N]
"""

import asyncio
import json
import os
import signal
import subprocess
import sys
import time
import httpx
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field


@dataclass
class TestResult:
    """Result of a single test case."""
    name: str
    passed: bool
    expected: Any
    actual: Any
    error: Optional[str] = None
    duration_ms: float = 0
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TestScenario:
    """A test scenario with query and expected behavior."""
    name: str
    query: str
    expected_behavior: Dict[str, Any]
    tags: List[str] = field(default_factory=list)
    timeout_seconds: float = 120.0


class TestEvaluator:
    """Evaluates test results against expected outcomes."""
    
    @staticmethod
    def evaluate_contains(actual: str, expected: List[str]) -> bool:
        """Check if actual contains all expected substrings."""
        actual_lower = actual.lower()
        return all(exp.lower() in actual_lower for exp in expected)
    
    @staticmethod
    def evaluate_not_contains(actual: str, forbidden: List[str]) -> bool:
        """Check that actual does not contain forbidden substrings."""
        actual_lower = actual.lower()
        return not any(f.lower() in actual_lower for f in forbidden)
    
    @staticmethod
    def evaluate_tool_used(result: Dict, expected_tool: str) -> bool:
        """Check if expected tool was used."""
        tool_result = result.get("tool_result", {})
        if not tool_result:
            return False
        used_tool = f"{tool_result.get('server', '')}.{tool_result.get('tool', '')}"
        return expected_tool.lower() in used_tool.lower()
    
    @staticmethod
    def evaluate_response_type(result: Dict, expected_type: str) -> bool:
        """Check if response type matches (direct, deliberation)."""
        return result.get("type", "").lower() == expected_type.lower()
    
    @staticmethod
    def evaluate_has_content(actual: str, min_length: int = 50) -> bool:
        """Check if response has meaningful content."""
        return len(actual.strip()) >= min_length
    
    @staticmethod
    def evaluate_no_refusal(actual: str) -> bool:
        """Check that response doesn't contain refusal patterns."""
        refusal_patterns = [
            "i cannot access",
            "i don't have access",
            "i lack real-time",
            "my training data",
            "cutoff date",
            "i cannot provide current",
            "unable to access current",
        ]
        actual_lower = actual.lower()
        return not any(p in actual_lower for p in refusal_patterns)


class ServerManager:
    """Manages the LLM Council server lifecycle for testing."""
    
    def __init__(self, project_root: str, port: int = 8001):
        self.project_root = Path(project_root)
        self.port = port
        self.backend_process: Optional[subprocess.Popen] = None
        self.base_url = f"http://localhost:{port}"
    
    async def is_server_running(self) -> bool:
        """Check if the server is already running."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/")
                return response.status_code == 200
        except Exception:
            return False
    
    async def start_server(self, timeout: int = 120) -> bool:
        """
        Start the backend server and wait for it to be ready.
        
        Returns True if server started successfully, False otherwise.
        """
        # Check if already running
        if await self.is_server_running():
            print("ℹ️  Server already running, using existing instance")
            return True
        
        print(f"🚀 Starting backend server on port {self.port}...")
        
        # Set up environment
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        
        # Start the backend using uv run uvicorn
        self.backend_process = subprocess.Popen(
            [
                "uv", "run", "uvicorn", "backend.main:app",
                "--host", "0.0.0.0",
                "--port", str(self.port),
                "--log-level", "warning"
            ],
            cwd=str(self.project_root),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            preexec_fn=os.setsid if sys.platform != "win32" else None
        )
        
        # Wait for server to be ready
        start_time = time.time()
        while time.time() - start_time < timeout:
            if await self.is_server_running():
                print(f"✅ Server started successfully (took {time.time() - start_time:.1f}s)")
                return True
            
            # Check if process died
            if self.backend_process.poll() is not None:
                stdout, _ = self.backend_process.communicate()
                print(f"❌ Server process died unexpectedly")
                print(f"   Output: {stdout.decode()[:500] if stdout else 'None'}")
                return False
            
            await asyncio.sleep(1)
        
        print(f"❌ Server failed to start within {timeout}s timeout")
        await self.stop_server()
        return False
    
    async def stop_server(self):
        """Stop the backend server if we started it."""
        if self.backend_process is not None:
            print("🛑 Stopping backend server...")
            try:
                # Kill the process group (Unix) or just the process (Windows)
                if sys.platform != "win32":
                    os.killpg(os.getpgid(self.backend_process.pid), signal.SIGTERM)
                else:
                    self.backend_process.terminate()
                
                # Wait for graceful shutdown
                try:
                    self.backend_process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    print("⚠️  Force killing server...")
                    if sys.platform != "win32":
                        os.killpg(os.getpgid(self.backend_process.pid), signal.SIGKILL)
                    else:
                        self.backend_process.kill()
                
                print("✅ Server stopped")
            except Exception as e:
                print(f"⚠️  Error stopping server: {e}")
            finally:
                self.backend_process = None


class LLMCouncilTestClient:
    """HTTP client for testing LLM Council API."""
    
    def __init__(self, base_url: str = "http://localhost:8001"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=300.0)
    
    async def health_check(self) -> bool:
        """Check if server is running."""
        try:
            response = await self.client.get(f"{self.base_url}/")
            return response.status_code == 200
        except Exception:
            return False
    
    async def call_mcp_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call an MCP tool directly."""
        response = await self.client.post(
            f"{self.base_url}/api/mcp/call",
            params={"tool_name": tool_name},
            json=arguments
        )
        if response.status_code != 200:
            raise Exception(f"MCP call failed: {response.text}")
        return response.json()
    
    async def send_message(
        self,
        query: str,
        conversation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send a message and get the response."""
        if not conversation_id:
            # Create new conversation (send empty JSON body)
            create_resp = await self.client.post(f"{self.base_url}/api/conversations", json={})
            if create_resp.status_code != 200:
                raise Exception(f"Failed to create conversation: {create_resp.text}")
            conversation_id = create_resp.json()["id"]
        
        # Send message
        response = await self.client.post(
            f"{self.base_url}/api/conversations/{conversation_id}/message",
            json={"content": query}
        )
        
        if response.status_code != 200:
            raise Exception(f"Failed to send message: {response.text}")
        
        return response.json()
    
    async def close(self):
        await self.client.aclose()


class AutomatedTestRunner:
    """
    Automated test runner with evaluation and iteration support.
    Includes automatic server lifecycle management.
    """
    
    def __init__(
        self,
        base_url: str = "http://localhost:8001",
        max_iterations: int = 3,
        results_dir: str = "tmp/test_results",
        project_root: Optional[str] = None,
        auto_manage_server: bool = True
    ):
        self.base_url = base_url
        self.client = LLMCouncilTestClient(base_url)
        self.max_iterations = max_iterations
        self.results_dir = Path(results_dir)
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.evaluator = TestEvaluator()
        self.auto_manage_server = auto_manage_server
        
        # Determine project root
        if project_root:
            self.project_root = Path(project_root)
        else:
            # Auto-detect from current file location
            self.project_root = Path(__file__).parent.parent
        
        # Extract port from base_url
        port = int(base_url.split(":")[-1].rstrip("/"))
        self.server_manager = ServerManager(str(self.project_root), port)
    
    def load_scenarios(self, scenario_file: Optional[str] = None) -> List[TestScenario]:
        """Load test scenarios from file or use defaults."""
        # Try explicit file first
        if scenario_file and Path(scenario_file).exists():
            with open(scenario_file) as f:
                data = json.load(f)
            return [TestScenario(**s) for s in data["scenarios"]]
        
        # Try default scenarios.json in tests directory
        default_file = Path(__file__).parent / "scenarios.json"
        if default_file.exists():
            with open(default_file) as f:
                data = json.load(f)
            return [TestScenario(**s) for s in data["scenarios"]]
        
        # Fallback to hardcoded defaults
        return [
            TestScenario(
                name="current_news_websearch",
                query="What are today's top 5 news headlines?",
                expected_behavior={
                    "tool_used": "websearch.search",
                    "no_refusal": True,
                    "has_content": True,
                    "min_length": 100,
                },
                tags=["mcp", "websearch", "current-events"]
            ),
            TestScenario(
                name="current_date_tool",
                query="What is the current date and time?",
                expected_behavior={
                    "tool_used": "system-date-time.get-system-date-time",
                    "no_refusal": True,
                    "has_content": True,
                },
                tags=["mcp", "datetime"]
            ),
            TestScenario(
                name="calculator_addition",
                query="What is 47 + 83?",
                expected_behavior={
                    "tool_used": "calculator.add",
                    "contains": ["130"],
                    "has_content": True,
                },
                tags=["mcp", "calculator"]
            ),
            TestScenario(
                name="factual_no_tool",
                query="What is the capital of France?",
                expected_behavior={
                    "contains": ["paris"],
                    "has_content": True,
                    "response_type": "direct",
                },
                tags=["factual", "no-tool"]
            ),
            TestScenario(
                name="deliberation_opinion",
                query="Which programming language should I learn first, Python or JavaScript?",
                expected_behavior={
                    "has_content": True,
                    "min_length": 200,
                    "response_type": "deliberation",
                },
                tags=["deliberation", "opinion"]
            ),
        ]
    
    async def run_single_test(self, scenario: TestScenario) -> TestResult:
        """Run a single test scenario and evaluate results."""
        start_time = time.time()
        
        try:
            result = await self.client.send_message(scenario.query)
            duration_ms = (time.time() - start_time) * 1000
            
            # Extract response content (handle both direct and deliberation responses)
            response_content = ""
            if "direct_response" in result and result["direct_response"]:
                response_content = result["direct_response"].get("response", "")
            elif "stage3" in result and result["stage3"]:
                response_content = result["stage3"].get("response", "")
            
            # Evaluate against expected behavior
            checks = []
            passed = True
            
            expected = scenario.expected_behavior
            
            # Check tool usage
            if "tool_used" in expected:
                tool_check = self.evaluator.evaluate_tool_used(result, expected["tool_used"])
                checks.append(("tool_used", tool_check, expected["tool_used"]))
                passed = passed and tool_check
            
            # Check response type
            if "response_type" in expected:
                type_check = self.evaluator.evaluate_response_type(result, expected["response_type"])
                checks.append(("response_type", type_check, expected["response_type"]))
                passed = passed and type_check
            
            # Check content contains
            if "contains" in expected:
                contains_check = self.evaluator.evaluate_contains(response_content, expected["contains"])
                checks.append(("contains", contains_check, expected["contains"]))
                passed = passed and contains_check
            
            # Check content not contains
            if "not_contains" in expected:
                not_contains_check = self.evaluator.evaluate_not_contains(response_content, expected["not_contains"])
                checks.append(("not_contains", not_contains_check, expected["not_contains"]))
                passed = passed and not_contains_check
            
            # Check no refusal
            if expected.get("no_refusal"):
                refusal_check = self.evaluator.evaluate_no_refusal(response_content)
                checks.append(("no_refusal", refusal_check, True))
                passed = passed and refusal_check
            
            # Check has content
            if expected.get("has_content"):
                min_len = expected.get("min_length", 50)
                content_check = self.evaluator.evaluate_has_content(response_content, min_len)
                checks.append(("has_content", content_check, f"min_length={min_len}"))
                passed = passed and content_check
            
            return TestResult(
                name=scenario.name,
                passed=passed,
                expected=expected,
                actual=response_content[:500] + "..." if len(response_content) > 500 else response_content,
                duration_ms=duration_ms,
                details={
                    "checks": checks,
                    "full_result_keys": list(result.keys()),
                    "tool_result": result.get("tool_result"),
                }
            )
            
        except Exception as e:
            return TestResult(
                name=scenario.name,
                passed=False,
                expected=scenario.expected_behavior,
                actual=None,
                error=str(e),
                duration_ms=(time.time() - start_time) * 1000
            )
    
    async def run_all_tests(
        self,
        scenarios: Optional[List[TestScenario]] = None,
        tags_filter: Optional[List[str]] = None
    ) -> List[TestResult]:
        """Run all test scenarios."""
        if scenarios is None:
            scenarios = self.load_scenarios()
        
        # Filter by tags if specified
        if tags_filter:
            scenarios = [s for s in scenarios if any(t in s.tags for t in tags_filter)]
        
        print(f"\n{'='*60}")
        print(f"Running {len(scenarios)} test scenarios")
        print(f"{'='*60}\n")
        
        results = []
        for i, scenario in enumerate(scenarios, 1):
            print(f"[{i}/{len(scenarios)}] Testing: {scenario.name}")
            print(f"    Query: {scenario.query[:60]}...")
            
            result = await self.run_single_test(scenario)
            results.append(result)
            
            status = "✅ PASS" if result.passed else "❌ FAIL"
            print(f"    {status} ({result.duration_ms:.0f}ms)")
            
            if not result.passed:
                if result.error:
                    print(f"    Error: {result.error}")
                else:
                    for check_name, check_passed, check_expected in result.details.get("checks", []):
                        if not check_passed:
                            print(f"    Failed check: {check_name} (expected: {check_expected})")
            print()
        
        return results
    
    def save_results(self, results: List[TestResult], iteration: int = 0):
        """Save test results to file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = self.results_dir / f"test_results_{timestamp}_iter{iteration}.json"
        
        results_data = {
            "timestamp": timestamp,
            "iteration": iteration,
            "total": len(results),
            "passed": sum(1 for r in results if r.passed),
            "failed": sum(1 for r in results if not r.passed),
            "results": [
                {
                    "name": r.name,
                    "passed": r.passed,
                    "expected": r.expected,
                    "actual": r.actual,
                    "error": r.error,
                    "duration_ms": r.duration_ms,
                    "details": r.details,
                }
                for r in results
            ]
        }
        
        with open(filename, "w") as f:
            json.dump(results_data, f, indent=2, default=str)
        
        print(f"\nResults saved to: {filename}")
        return filename
    
    def generate_report(self, results: List[TestResult]) -> str:
        """Generate a human-readable test report."""
        total = len(results)
        passed = sum(1 for r in results if r.passed)
        failed = total - passed
        
        report = []
        report.append("\n" + "="*60)
        report.append("TEST REPORT")
        report.append("="*60)
        report.append(f"\nTotal: {total} | Passed: {passed} | Failed: {failed}")
        report.append(f"Pass Rate: {passed/total*100:.1f}%\n")
        
        if failed > 0:
            report.append("FAILED TESTS:")
            report.append("-"*40)
            for r in results:
                if not r.passed:
                    report.append(f"\n❌ {r.name}")
                    if r.error:
                        report.append(f"   Error: {r.error}")
                    for check_name, check_passed, check_expected in r.details.get("checks", []):
                        if not check_passed:
                            report.append(f"   • {check_name}: expected {check_expected}")
                    if r.actual:
                        report.append(f"   Actual (truncated): {str(r.actual)[:200]}...")
        
        report.append("\n" + "="*60)
        return "\n".join(report)
    
    async def run_with_iteration(
        self,
        scenarios: Optional[List[TestScenario]] = None,
        on_failure: Optional[Callable[[List[TestResult]], None]] = None
    ) -> List[TestResult]:
        """
        Run tests with iteration on failures.
        Automatically manages server lifecycle if auto_manage_server is True.
        
        Args:
            scenarios: Test scenarios to run
            on_failure: Callback when tests fail (for fix iteration)
        
        Returns:
            Final test results
        """
        results = []
        server_started_by_us = False
        
        try:
            # Start server if auto-management is enabled
            if self.auto_manage_server:
                # Check if server is already running
                if not await self.client.health_check():
                    if await self.server_manager.start_server():
                        server_started_by_us = True
                    else:
                        print("❌ Failed to start server automatically")
                        return []
                else:
                    print("ℹ️  Using existing server instance")
            else:
                # Just check if server is running
                if not await self.client.health_check():
                    print("❌ Server not running. Start with ./start.sh first or enable auto_manage_server.")
                    return []
            
            for iteration in range(self.max_iterations):
                print(f"\n{'#'*60}")
                print(f"# ITERATION {iteration + 1}/{self.max_iterations}")
                print(f"{'#'*60}")
                
                results = await self.run_all_tests(scenarios)
                self.save_results(results, iteration)
                print(self.generate_report(results))
                
                # Check if all tests pass
                if all(r.passed for r in results):
                    print("\n✅ ALL TESTS PASSED!")
                    return results
                
                # If there's a failure callback and more iterations, call it
                if on_failure and iteration < self.max_iterations - 1:
                    print("\n🔧 Attempting fixes...")
                    on_failure(results)
                    await asyncio.sleep(2)  # Wait for potential changes
                else:
                    print(f"\n⚠️  Tests still failing after iteration {iteration + 1}")
        
        finally:
            # Stop server if we started it
            if server_started_by_us:
                await self.server_manager.stop_server()
        
        return results
    
    async def close(self):
        await self.client.close()


async def main():
    """Main entry point for test runner."""
    import argparse
    
    parser = argparse.ArgumentParser(description="LLM Council Automated Test Runner")
    parser.add_argument("--scenario", help="Run specific scenario by name")
    parser.add_argument("--tags", help="Filter by tags (comma-separated)")
    parser.add_argument("--max-iterations", type=int, default=1, help="Max fix iterations")
    parser.add_argument("--scenarios-file", help="Path to scenarios JSON file")
    parser.add_argument("--base-url", default="http://localhost:8001", help="API base URL")
    parser.add_argument("--no-auto-server", action="store_true", 
                       help="Disable automatic server start/stop (requires manual server management)")
    parser.add_argument("--server-startup-timeout", type=int, default=60,
                       help="Timeout in seconds for server startup (default: 60)")
    args = parser.parse_args()
    
    runner = AutomatedTestRunner(
        base_url=args.base_url,
        max_iterations=args.max_iterations,
        auto_manage_server=not args.no_auto_server
    )
    
    try:
        scenarios = runner.load_scenarios(args.scenarios_file)
        
        # Filter by name if specified
        if args.scenario:
            scenarios = [s for s in scenarios if s.name == args.scenario]
            if not scenarios:
                print(f"No scenario found with name: {args.scenario}")
                return
        
        # Filter by tags
        tags_filter = args.tags.split(",") if args.tags else None
        if tags_filter:
            scenarios = [s for s in scenarios if any(t in s.tags for t in tags_filter)]
        
        results = await runner.run_with_iteration(scenarios)
        
        # Exit code based on results
        sys.exit(0 if all(r.passed for r in results) else 1)
        
    finally:
        await runner.close()


if __name__ == "__main__":
    asyncio.run(main())
