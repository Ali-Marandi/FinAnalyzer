"""
build_exe.py - Build script for FinAnalyzer Enterprise v2.0.0
Creates standalone executable using PyInstaller.
Supports Windows (EXE) and Linux binary builds.
"""

import PyInstaller.__main__
import platform
import os
import sys

def build():
    print("=" * 60)
    print("  FinAnalyzer Enterprise v2.0.0 - Build System")
    print(f"  Platform: {platform.system()} {platform.machine()}")
    print(f"  Python: {sys.version}")
    print("=" * 60)

    # Configuration
    app_name = "FinAnalyzer_Enterprise_v2"
    entry_point = "main.py"
    separator = ";" if platform.system() == "Windows" else ":"

    args = [
        entry_point,
        '--onefile',
        '--windowed',
        f'--name={app_name}',
        f'--add-data=core{separator}core',
        f'--add-data=ui{separator}ui',
        '--clean',
        '--noconfirm',
    ]

    # Windows-specific options
    if platform.system() == "Windows":
        icon_path = os.path.join("assets", "icon.ico")
        if os.path.exists(icon_path):
            args.append(f'--icon={icon_path}')

    print(f"\nBuild command: pyinstaller {' '.join(args)}")
    print("\nBuilding... (this may take several minutes)\n")

    try:
        PyInstaller.__main__.run(args)
        print("\n" + "=" * 60)
        print("  BUILD SUCCESSFUL!")
        print(f"  Output: dist/{app_name}")
        print("=" * 60)
    except Exception as e:
        print(f"\n  BUILD FAILED: {e}")
        sys.exit(1)


if __name__ == "__main__":
    build()
