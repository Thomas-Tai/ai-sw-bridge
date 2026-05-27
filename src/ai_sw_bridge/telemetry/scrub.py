"""Shared scrub/redaction utilities for telemetry export and bug reports.

Redaction rules per spec.md §8.8 and privacy_review.md:
  - Replace any string matching r"S1B_\\w+" with <redacted_local>
  - Replace absolute file paths with basename only
  - Replace trade-secret patterns from .ai-sw-bridge.toml with <REDACTED:trade_secret>
  - Strip *_locals.txt file contents entirely
"""

from __future__ import annotations

import re
from pathlib import Path

_REDACT_LOCALS = re.compile(r"S1B_\w+")
_REDACT_PATH = re.compile(r"(?:[A-Z]:)?[/\\]+(?:[^/\\]+[/\\]+)*[^/\\]+")
_TRADE_SECRET_TOKEN = "<REDACTED:trade_secret>"


def load_trade_secret_patterns(config_path: Path) -> list[re.Pattern[str]]:
    """Load trade-secret redaction patterns from .ai-sw-bridge.toml.

    Returns compiled regex list. Raises ValueError on invalid patterns
    (caller decides how to surface the error).
    """
    if not config_path.exists():
        return []
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            return []
    with open(config_path, "rb") as f:
        cfg = tomllib.load(f)
    raw_patterns = cfg.get("scrub", {}).get("trade_secret_patterns", [])
    compiled: list[re.Pattern[str]] = []
    for p in raw_patterns:
        try:
            compiled.append(re.compile(p))
        except re.error as e:
            raise ValueError(
                f"invalid trade-secret regex in {config_path}: " f"{p!r} -- {e}"
            ) from e
    return compiled


def redact_string(
    value: str,
    trade_secret_patterns: list[re.Pattern[str]] | None = None,
) -> str:
    """Apply redaction rules to a string value."""
    v = _REDACT_LOCALS.sub("<redacted_local>", value)
    for pat in trade_secret_patterns or []:
        v = pat.sub(_TRADE_SECRET_TOKEN, v)

    def _replace_path(m: re.Match[str]) -> str:
        full = m.group(0)
        if "/" in full or "\\" in full:
            return Path(full).name
        return full

    v = _REDACT_PATH.sub(_replace_path, v)
    return v


def redact_file_contents(
    text: str,
    trade_secret_patterns: list[re.Pattern[str]] | None = None,
    *,
    is_locals: bool = False,
) -> str:
    """Redact text content from a file.

    If is_locals=True, the entire content is replaced with <redacted_locals>
    since locals files contain engineering parameter values that are often
    trade-secret (per privacy_review.md §2.3).
    """
    if is_locals:
        return "<redacted_locals>"
    return redact_string(text, trade_secret_patterns)
