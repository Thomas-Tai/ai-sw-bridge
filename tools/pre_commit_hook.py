#!/usr/bin/env python3
"""Pre-commit hook: run ai-sw-build --lint on staged spec.json files.

Install:  python tools/pre_commit_hook.py install
Uninstall: python tools/pre_commit_hook.py uninstall

The hook runs `ai-sw-build --lint` on every staged spec.json and blocks
the commit if any lint findings are returned (exit code 6 from ai-sw-build).
Non-spec staged files are ignored.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK_PATH = REPO_ROOT / ".git" / "hooks" / "pre-commit"
VENV_PYTHON = REPO_ROOT / ".venv-freshtest" / "Scripts" / "python.exe"
BUILD_MODULE = "ai_sw_bridge.cli.build"

HOOK_SCRIPT = f"""#!/bin/sh
# ai-sw-bridge pre-commit hook: lint staged spec.json files
python="{VENV_PYTHON}"
buildmod="{BUILD_MODULE}"

staged=$(git diff --cached --name-only --diff-filter=ACM -- '*.json')
if [ -z "$staged" ]; then
    exit 0
fi

for f in $staged; do
    # Only lint files that look like spec.json (contain schema_version)
    if grep -q '"schema_version"' "$f" 2>/dev/null; then
        echo "linting $f..."
        "$python" -m "$buildmod" --lint "$f" > /dev/null 2>&1
        rc=$?
        if [ $rc -eq 6 ]; then
            echo "FAIL: lint findings in $f (run 'ai-sw-build --lint $f' for details)"
            exit 1
        elif [ $rc -ne 0 ]; then
            echo "WARN: ai-sw-build --lint exited $rc for $f (non-lint error; not blocking)"
        fi
    fi
done
exit 0
"""


def install() -> int:
    if HOOK_PATH.exists():
        print(f"Hook already exists at {HOOK_PATH}", file=sys.stderr)
        return 1
    HOOK_PATH.write_text(HOOK_SCRIPT, encoding="utf-8")
    # Make executable on Unix-like systems
    os.chmod(HOOK_PATH, 0o755)
    print(f"Installed pre-commit hook at {HOOK_PATH}")
    return 0


def uninstall() -> int:
    if not HOOK_PATH.exists():
        print("No hook to uninstall", file=sys.stderr)
        return 1
    HOOK_PATH.unlink()
    print("Uninstalled pre-commit hook")
    return 0


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in ("install", "uninstall"):
        print("Usage: python tools/pre_commit_hook.py [install|uninstall]")
        return 1
    if sys.argv[1] == "install":
        return install()
    return uninstall()


if __name__ == "__main__":
    sys.exit(main())
