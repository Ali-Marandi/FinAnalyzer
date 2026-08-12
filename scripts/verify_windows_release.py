"""Fail-closed dependency gate for a clean FinAnalyzer Windows release build.

Run inside an isolated Windows virtual environment created from
requirements-windows-build.txt. The gate rejects known unsafe package versions,
blocks unused xhtml2pdf from shipping, writes an auditable dependency snapshot, and
runs pip-audit against the actual build environment.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, distributions, version
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_DIR = PROJECT_ROOT / "security-reports"
MINIMUM_SAFE_VERSIONS = {"wheel": "0.46.2", "pypdf": "6.15.0"}
BLOCKED_PACKAGES = {
    "xhtml2pdf": "xhtml2pdf 0.2.x is affected by PYSEC-2026-2056/CVE-2024-25885 and is not required by FinAnalyzer.",
}


def _parsed(value: str):
    try:
        from packaging.version import Version
    except ImportError as exc:
        raise RuntimeError("The Windows release gate requires the packaging module.") from exc
    return Version(value)


def installed_version(package: str) -> str | None:
    try:
        return version(package)
    except PackageNotFoundError:
        return None


def write_dependency_snapshot(report_dir: Path) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    packages = sorted(
        ({"name": dist.metadata["Name"], "version": dist.version} for dist in distributions()),
        key=lambda item: item["name"].lower(),
    )
    output = report_dir / "windows-build-dependencies.json"
    output.write_text(json.dumps(packages, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def enforce_versions() -> list[str]:
    findings: list[str] = []
    for package, minimum in MINIMUM_SAFE_VERSIONS.items():
        current = installed_version(package)
        if current is not None and _parsed(current) < _parsed(minimum):
            findings.append(f"{package} {current} is below the required secure version {minimum}.")
    for package, reason in BLOCKED_PACKAGES.items():
        current = installed_version(package)
        if current is not None:
            findings.append(f"{package} {current} is blocked: {reason}")
    return findings


def run_pip_audit(report_dir: Path) -> list[str]:
    output_path = report_dir / "pip-audit.json"
    command = [sys.executable, "-m", "pip_audit", "--local", "--skip-editable", "--format", "json"]
    completed = subprocess.run(command, cwd=PROJECT_ROOT, text=True, capture_output=True, check=False)  # nosec B603
    output_path.write_text(completed.stdout or "[]", encoding="utf-8")
    if completed.returncode == 0:
        return []
    try:
        payload = json.loads(completed.stdout or "[]")
    except json.JSONDecodeError:
        return ["pip-audit did not return valid JSON; inspect security-reports/pip-audit.json."]
    if isinstance(payload, dict):
        dependencies = payload.get("dependencies") or []
    elif isinstance(payload, list):
        dependencies = payload
    else:
        return ["pip-audit returned an unexpected JSON structure; inspect security-reports/pip-audit.json."]
    findings: list[str] = []
    for dependency in dependencies:
        if not isinstance(dependency, dict):
            return ["pip-audit returned an invalid dependency record; inspect security-reports/pip-audit.json."]
        vulnerabilities = dependency.get("vulns") or []
        for vuln in vulnerabilities:
            if isinstance(vuln, dict):
                findings.append(f"{dependency.get('name')} {dependency.get('version')}: {vuln.get('id')}")
    return findings or ["pip-audit failed without a parseable finding; inspect security-reports/pip-audit.json."]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run FinAnalyzer Windows release dependency gates.")
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    args = parser.parse_args()
    report_dir = Path(args.report_dir)
    snapshot = write_dependency_snapshot(report_dir)
    findings = enforce_versions()
    findings.extend(run_pip_audit(report_dir))
    if findings:
        print("Windows release dependency gate failed:")
        for finding in findings:
            print(f" - {finding}")
        print(f"Evidence: {snapshot} and {report_dir / 'pip-audit.json'}")
        return 1
    print(f"Windows release dependency gate passed. Dependency snapshot: {snapshot}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
