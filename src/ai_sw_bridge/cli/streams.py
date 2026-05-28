"""Stream-contract helpers for CLI entry points (UIUX §2.2, §3.3).

Every CLI must support a uniform ``--quiet`` flag that suppresses
stderr entirely while leaving stdout (the JSON envelope) untouched.
This module provides:

- :func:`add_quiet_flag` — wires ``--quiet`` into an argparse parser.
- :func:`apply_quiet` — at runtime, redirects ``sys.stderr`` to
  ``/dev/null`` (or its Windows equivalent) when ``args.quiet`` is set.
- :func:`should_use_color` — ``False`` when ``NO_COLOR`` is set,
  stderr is not a TTY, or ``--quiet`` redirected stderr to devnull.
- :func:`strip_ansi` — remove ANSI SGR escape sequences from text.
- :class:`PlainFormatter` — logging formatter that strips ANSI when
  color is not available.
- :func:`progress_cr` — returns ``\\r`` on a TTY, ``\\n`` otherwise
  (so progress patterns degrade to one-per-line in pipes).

The two-stream contract (UIUX §2.1) is invariant: stdout always
carries the JSON envelope. ``--quiet`` only silences stderr.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from typing import TextIO

_ANSI_SGR_RE = re.compile(r"\x1b\[[0-9;]*m")
_color_cache: bool | None = None


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


def should_use_color(*, _reset: bool = False) -> bool:
    """Whether stderr output should include ANSI color codes.

    Returns ``False`` when any of:

    * ``NO_COLOR`` env var is set (https://no-color.org/ — any value).
    * ``sys.stderr`` is not a TTY (pipe, file, CI capture).
    * ``--quiet`` redirected stderr to devnull (isatty() is False).

    The result is cached after the first call for process lifetime.
    Pass ``_reset=True`` to invalidate the cache (tests only);
    returns ``None`` in that case without evaluating.
    """
    global _color_cache
    if _reset:
        _color_cache = None
        return None  # type: ignore[return-value]
    if _color_cache is not None:
        return _color_cache
    if os.environ.get("NO_COLOR") is not None:
        _color_cache = False
        return False
    try:
        _color_cache = bool(sys.stderr.isatty())
    except Exception:
        _color_cache = False
    return _color_cache


def strip_ansi(text: str) -> str:
    """Remove ANSI SGR escape sequences (``\\x1b[...m``) from *text*."""
    return _ANSI_SGR_RE.sub("", text)


class PlainFormatter(logging.Formatter):
    """Logging formatter that strips ANSI codes when color is unavailable.

    When ``force_plain`` is ``None`` (default), the decision is made
    lazily per-record via :func:`should_use_color`. This means
    ``apply_quiet`` can run either before or after the formatter is
    created — the first log record evaluates the current stderr state.
    """

    def __init__(
        self,
        fmt: str | None = None,
        datefmt: str | None = None,
        *,
        force_plain: bool | None = None,
    ) -> None:
        super().__init__(fmt=fmt, datefmt=datefmt)
        self._force_plain = force_plain

    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        if self._force_plain is True:
            return strip_ansi(msg)
        if self._force_plain is None and not should_use_color():
            return strip_ansi(msg)
        return msg


def progress_cr() -> str:
    r"""Return ``\r`` on a TTY (overwrite line), ``\n`` otherwise.

    Progress patterns (spinners, percent bars) should use this as
    their line terminator so CI logs get one update per line instead
    of garbled overwrites.
    """
    try:
        return "\r" if sys.stderr.isatty() else "\n"
    except Exception:
        return "\n"
