"""Stream-contract helpers for CLI entry points (UIUX §2.2, §3.3).

Every CLI must support a uniform ``--quiet`` flag that suppresses
stderr entirely while leaving stdout (the JSON envelope) untouched.
This module provides:

- :func:`add_quiet_flag` — wires ``--quiet`` into an argparse parser.
- :func:`apply_quiet` — at runtime, redirects ``sys.stderr`` to
  ``/dev/null`` (or its Windows equivalent) when ``args.quiet`` is set.

The two-stream contract (UIUX §2.1) is invariant: stdout always
carries the JSON envelope. ``--quiet`` only silences stderr.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import TextIO


def add_quiet_flag(parser: argparse.ArgumentParser) -> None:
    """Wire ``--quiet`` into the given argparse parser.

    The flag is uniform across every ai-sw-* CLI per UIUX §3.3.
    """
    parser.add_argument(
        "--quiet",
        action="store_true",
        default=False,
        help=(
            "Suppress stderr output entirely (UIUX §2.2). stdout JSON "
            "is unaffected. Use in CI scripts that want exit-code-only "
            "behavior."
        ),
    )


def apply_quiet(args: argparse.Namespace) -> TextIO | None:
    """Apply ``--quiet`` if set on *args*.

    Redirects :data:`sys.stderr` to ``os.devnull`` and returns the
    original stream so the caller can restore it on exit (mostly
    useful for tests; CLIs are short-lived processes that don't
    bother restoring).

    Returns ``None`` when ``args.quiet`` is False or absent.
    """
    if not getattr(args, "quiet", False):
        return None
    original = sys.stderr
    sys.stderr = open(os.devnull, "w")  # noqa: SIM115 — process-lifetime
    return original
