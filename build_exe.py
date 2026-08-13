"""Build the FinAnalyzer Enterprise v2.6.1 desktop executable with close-readiness controls."""

from __future__ import annotations

import platform
import subprocess
import sys
from pathlib import Path

import PyInstaller.__main__


PROJECT_ROOT = Path(__file__).resolve().parent


def build() -> None:
    if platform.system() == "Windows":
        gate = PROJECT_ROOT / "scripts" / "verify_windows_release.py"
        print("Running the mandatory Windows dependency security gate...")
        subprocess.run([sys.executable, str(gate)], cwd=PROJECT_ROOT, check=True)  # nosec B603

    print("=" * 60)
    print("  FinAnalyzer Enterprise v2.6.1 — Verified Compliance Evidence Build")
    print(f"  Platform: {platform.system()} {platform.machine()}")
    print(f"  Python: {sys.version}")
    print("=" * 60)

    app_name = "FinAnalyzer_Enterprise_v2_6_1"
    separator = ";" if platform.system() == "Windows" else ":"
    args = [
        str(PROJECT_ROOT / "main.py"),
        "--onefile",
        "--windowed",
        f"--name={app_name}",
        f"--add-data={PROJECT_ROOT / 'core'}{separator}core",
        f"--add-data={PROJECT_ROOT / 'ui'}{separator}ui",
        "--hidden-import=core.plaid_connector",
        "--hidden-import=core.plaid_link_desktop",
        "--hidden-import=core.automated_reporting",
        "--hidden-import=core.security",
        "--hidden-import=core.authorization",
        "--hidden-import=core.audit",
        "--hidden-import=core.period_close",
        "--hidden-import=core.compliance_evidence",
        "--hidden-import=core.identity",
        "--hidden-import=msal",
        "--hidden-import=jwt",
        "--hidden-import=plaid",
        "--collect-submodules=plaid",
        "--clean",
        "--noconfirm",
    ]
    icon_path = PROJECT_ROOT / "assets" / "icon.ico"
    if platform.system() == "Windows":
        # Imported dynamically by WindowsDpapiProtector; make it explicit for PyInstaller.
        args.append("--hidden-import=win32crypt")
        if icon_path.exists():
            args.append(f"--icon={icon_path}")

    PyInstaller.__main__.run(args)
    print("=" * 60)
    print(f"  BUILD SUCCESSFUL — dist/{app_name}.exe (on Windows)")
    print("=" * 60)


if __name__ == "__main__":
    build()
