"""ai-sw-doctor: operator preflight diagnostic for ai-sw-bridge.

The *entire* terminal vocabulary a chat-first operator needs. Runs a
handful of environment checks and prints operator-legible next steps. It
is COM/engine-inert at import: the only COM touch is the reused probe(),
called at runtime inside _check_solidworks_seat().

Read-only by default (spec §8.2). `--register` (spec §8.3) is the opt-in
automated MCP-client registration path, wired in Task B.
"""

from __future__ import annotations

import argparse
import json
import shutil
import struct
import sys
from typing import Any

from .probe import probe
from .stability import add_tier, cli_stability
from .streams import add_quiet_flag, apply_quiet

Check = dict[str, Any]


def _check(name: str, ok: bool, detail: str, fix: str | None = None) -> Check:
    return {"name": name, "ok": ok, "detail": detail, "fix": fix}


def _check_python_bitness() -> Check:
    bits = struct.calcsize("P") * 8
    if bits == 64:
        return _check("python_bitness", True, "Python is 64-bit.")
    return _check(
        "python_bitness",
        False,
        f"Python is {bits}-bit; SOLIDWORKS is 64-bit.",
        "Uninstall this Python and install 64-bit Python 3.x "
        "(python.org, tick 'Add to PATH'), then reinstall ai-sw-bridge.",
    )


def _check_pywin32() -> Check:
    # Importing win32com/pythoncom is COM-inert (no Dispatch). A failure
    # here is the classic 'pywin32 post-install never ran' footgun.
    try:
        import pythoncom  # noqa: F401
        import win32com.client  # noqa: F401
    except Exception as exc:  # noqa: BLE001 — report, don't crash
        return _check(
            "pywin32",
            False,
            f"pywin32 did not import: {exc!r}",
            "Run: python -m pywin32_postinstall -install  "
            "(inside the environment ai-sw-bridge is installed in).",
        )
    return _check("pywin32", True, "pywin32 imports cleanly.")


def _check_scripts_on_path() -> Check:
    if shutil.which("ai-sw-probe"):
        return _check("scripts_on_path", True, "ai-sw-* scripts are on PATH.")
    return _check(
        "scripts_on_path",
        False,
        "ai-sw-* scripts are not on PATH.",
        "Run: pipx ensurepath  then close and reopen your terminal.",
    )


def _check_solidworks_seat() -> Check:
    result = probe()
    if result.get("ok"):
        rev = result.get("sw_revision")
        return _check("solidworks_seat", True, f"Connected to SOLIDWORKS {rev}.")
    return _check(
        "solidworks_seat",
        False,
        str(result.get("error") or "probe failed"),
        "Is SOLIDWORKS open? Open it and re-run ai-sw-doctor. If it is "
        "already open, your Python may be 32-bit — see the python_bitness fix.",
    )


def _check_mcp_registration() -> Check:
    from ..mcp import registration as reg

    try:
        d = reg.detect("claude_desktop")
    except Exception as exc:  # noqa: BLE001
        return _check(
            "mcp_registration",
            False,
            f"detect failed: {exc!r}",
            "Run: ai-sw-doctor --register",
        )
    if d.get("present"):
        return _check(
            "mcp_registration",
            True,
            f"MCP server registered in {d['config_path']}.",
        )
    return _check(
        "mcp_registration",
        False,
        f"ai-sw-bridge not found in {d['config_path']}.",
        "Run: ai-sw-doctor --register  (writes a timestamped backup first).",
    )


_CHECK_NAMES = (
    "_check_python_bitness",
    "_check_pywin32",
    "_check_scripts_on_path",
    "_check_solidworks_seat",
    "_check_mcp_registration",
)


def run_doctor(*, run_probe: bool = True) -> dict[str, Any]:
    """Run every environment check and aggregate an operator verdict.

    ``run_probe=False`` skips the live-seat check (used by the packaged
    no-SW CI smoke, which asserts graceful failure, and by unit tests).

    Check functions are resolved by name from this module's namespace on
    every call (rather than a tuple of function objects captured once at
    import time) so that tests can ``monkeypatch.setattr(doctor,
    "_check_x", ...)`` and have ``run_doctor`` observe the replacement.
    """
    module = sys.modules[__name__]
    checks: list[Check] = []
    for name in _CHECK_NAMES:
        if name == "_check_solidworks_seat" and not run_probe:
            checks.append(_check("solidworks_seat", False, "skipped (--no-seat)", None))
            continue
        fn = getattr(module, name)
        checks.append(fn())
    ok = all(c["ok"] for c in checks)
    next_steps = [c["fix"] for c in checks if not c["ok"] and c["fix"]]
    return {"ok": ok, "checks": checks, "next_steps": next_steps}


@cli_stability("experimental")
def main() -> int:
    parser = argparse.ArgumentParser(
        prog="ai-sw-doctor",
        description=(
            "Preflight check for ai-sw-bridge: verifies 64-bit Python, "
            "pywin32, PATH, the SOLIDWORKS seat, and (optionally) registers "
            "the MCP server with your AI client. Run this first if anything "
            "misbehaves."
        ),
    )
    add_tier(parser, "experimental")
    add_quiet_flag(parser)
    parser.add_argument(
        "--no-seat",
        action="store_true",
        help="Skip the live-SOLIDWORKS check (env-only diagnosis).",
    )
    # --register / --client are declared here but only wired in Task B.
    parser.add_argument(
        "--register",
        action="store_true",
        help="Register the ai-sw-bridge MCP server with your AI client "
        "(Claude Desktop). Writes a timestamped backup first.",
    )
    parser.add_argument(
        "--client",
        default="claude_desktop",
        help="AI client to target for --register (default: claude_desktop).",
    )
    args = parser.parse_args()
    apply_quiet(args)

    if args.register:
        return _do_register(args.client)

    result = run_doctor(run_probe=not args.no_seat)
    print(json.dumps(result, indent=2, default=str))
    _print_human_summary(result)
    return 0 if result["ok"] else 1


def _print_human_summary(result: dict[str, Any]) -> None:
    for c in result["checks"]:
        mark = "OK " if c["ok"] else "FAIL"
        print(f"[{mark}] {c['name']}: {c['detail']}", file=sys.stderr)
    for step in result["next_steps"]:
        print(f"  -> {step}", file=sys.stderr)


def _do_register(client: str) -> int:
    from ..mcp import registration as reg  # function-local: keep import light

    try:
        out = reg.register(client)
    except ValueError as exc:  # unknown client
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(out, indent=2, default=str))
    # Transparency: name the file and show what we injected.
    print(f"config file: {out['config_path']}", file=sys.stderr)
    if out.get("backup_path"):
        print(f"backup:      {out['backup_path']}", file=sys.stderr)
    if out.get("changed"):
        command = out["entry"].get("command", "?")
        print(
            f"registered the ai-sw-bridge MCP server (command: {command}).",
            file=sys.stderr,
        )
    elif out.get("ok"):
        print("already registered — no change.", file=sys.stderr)
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
