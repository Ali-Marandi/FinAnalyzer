"""Authorized, non-destructive security validation runner for FinAnalyzer.

This runner is intentionally limited to local code, local tests, dependency metadata,
and repository history. It never probes Microsoft Entra, Plaid, bank systems, SMTP,
Telegram, customer networks, or public endpoints. Use a separately authorized,
independent engagement for network or production penetration testing.

Examples:
    python scripts/run_security_validation.py --suite identity
    python scripts/run_security_validation.py --suite all --include-static --include-dependencies
"""

from __future__ import annotations

import argparse
import shutil
# Commands passed to subprocess are built only from fixed, internal security-tool lists.
import subprocess  # nosec B404
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_SUITES = {
    "identity": ["tests/test_identity_v23.py", "tests/test_enterprise_security.py"],
    "banking": ["tests/test_plaid_v2.py"],
    "reporting": ["tests/test_reporting_v2.py"],
    "all": [
        "tests/test_identity_v23.py",
        "tests/test_enterprise_security.py",
        "tests/test_plaid_v2.py",
        "tests/test_reporting_v2.py",
    ],
}


def run(command: list[str], label: str) -> int:
    print(f"\n== {label} ==")
    # The argument vector is never assembled from raw user input.
    completed = subprocess.run(command, cwd=PROJECT_ROOT, check=False)  # nosec B603
    return completed.returncode


def executable(name: str) -> str | None:
    return shutil.which(name)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run only authorized local FinAnalyzer security validation.")
    parser.add_argument("--suite", choices=sorted(TEST_SUITES), default="all")
    parser.add_argument("--include-static", action="store_true", help="Run Bandit source scan when installed.")
    parser.add_argument("--include-dependencies", action="store_true", help="Run pip-audit when installed.")
    parser.add_argument("--include-secrets", action="store_true", help="Run Gitleaks repository scan when installed.")
    args = parser.parse_args()

    failures = []
    if run([sys.executable, "-m", "unittest", *TEST_SUITES[args.suite], "-v"], "Identity and authorization regression tests"):
        failures.append("regression-tests")

    if args.include_static:
        bandit = executable("bandit")
        if not bandit:
            print("Bandit skipped: install requirements-security.txt to enable static analysis.")
        elif run([bandit, "-q", "-r", "core", "ui", "scripts", "-x", "tests"], "Bandit static analysis"):
            failures.append("bandit")

    if args.include_dependencies:
        pip_audit = executable("pip-audit")
        if not pip_audit:
            print("pip-audit skipped: install requirements-security.txt to enable dependency auditing.")
        # Audit the resolved local environment. This avoids installing or resolving optional
        # runtime integrations while a validation scan is running.
        elif run([pip_audit, "--local", "--skip-editable"], "Dependency vulnerability audit"):
            failures.append("dependency-audit")

    if args.include_secrets:
        gitleaks = executable("gitleaks")
        if not gitleaks:
            print("Gitleaks skipped: install the official Gitleaks binary to enable repository secret scanning.")
        elif run([gitleaks, "detect", "--source", ".", "--no-banner", "--redact"], "Repository secret scan"):
            failures.append("secret-scan")

    if failures:
        print("\nSecurity validation failed: " + ", ".join(failures))
        return 1
    print("\nSecurity validation completed without local findings in the selected checks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
