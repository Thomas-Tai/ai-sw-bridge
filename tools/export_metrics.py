#!/usr/bin/env python
"""Export telemetry metrics to a sanitized JSON file.

Opt-in only. Refuses to run unless .telemetry/consent.txt exists (per
privacy_review.md and UIUX.md §14). Redaction rules per spec.md §8.8:
  - Replace any string matching r"S1B_\\w+" with <redacted_local>
  - Replace absolute file paths with basename only
  - Replace trade-secret patterns from .ai-sw-bridge.toml with <REDACTED:trade_secret>
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

_CONSENT_FILE = Path(".telemetry") / "consent.txt"
_DB_PATH = Path.home() / ".ai-sw-bridge" / "telemetry.sqlite"

_REDACT_LOCALS = re.compile(r"S1B_\w+")
_REDACT_PATH = re.compile(r"(?:[A-Z]:)?[/\\]+(?:[^/\\]+[/\\]+)*[^/\\]+")
_TRADE_SECRET_TOKEN = "<REDACTED:trade_secret>"


def _load_trade_secret_patterns(config_path: Path) -> list[re.Pattern[str]]:
    """Load trade-secret redaction patterns from .ai-sw-bridge.toml.

    Returns compiled regex list. Raises on invalid patterns.
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
            print(
                f"error: invalid trade-secret regex in {config_path}: "
                f"{p!r} -- {e}",
                file=sys.stderr,
            )
            sys.exit(1)
    return compiled


def _redact_value(value: str, trade_secret_patterns: list[re.Pattern[str]]) -> str:
    """Apply redaction rules to a string value."""
    v = _REDACT_LOCALS.sub("<redacted_local>", value)
    for pat in trade_secret_patterns:
        v = pat.sub(_TRADE_SECRET_TOKEN, v)
    # Path redaction: replace absolute paths with basename
    def _replace_path(m: re.Match[str]) -> str:
        full = m.group(0)
        # Only redact if it looks like a real path (has separator)
        if "/" in full or "\\" in full:
            return Path(full).name
        return full
    v = _REDACT_PATH.sub(_replace_path, v)
    return v


def _redact_row(
    row: dict, trade_secret_patterns: list[re.Pattern[str]]
) -> dict:
    """Redact sensitive strings in a metrics row."""
    labels = row.get("labels", {})
    redacted_labels = {}
    for k, v in labels.items():
        if isinstance(v, str):
            redacted_labels[k] = _redact_value(v, trade_secret_patterns)
        else:
            redacted_labels[k] = v
    return {**row, "labels": redacted_labels}


def export(output_path: Path, db_path: Path | None = None) -> dict:
    """Export all metrics rows as a redacted JSON dict."""
    effective_db = db_path or _DB_PATH
    if not effective_db.exists():
        return {"error": "no telemetry database found", "rows": []}

    conn = sqlite3.connect(str(effective_db))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, timestamp, metric_name, labels_json, value "
        "FROM metrics ORDER BY timestamp"
    ).fetchall()
    conn.close()

    config_path = Path(".ai-sw-bridge.toml")
    trade_secret_patterns = _load_trade_secret_patterns(config_path)

    export_rows = []
    for r in rows:
        row = {
            "id": r["id"],
            "timestamp": r["timestamp"],
            "metric_name": r["metric_name"],
            "labels": json.loads(r["labels_json"]),
            "value": r["value"],
        }
        export_rows.append(_redact_row(row, trade_secret_patterns))

    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "row_count": len(export_rows),
        "rows": export_rows,
    }


def main() -> None:
    consent = _CONSENT_FILE
    if not consent.exists():
        print(
            f"error: consent file not found at {consent}. "
            f"Create it to opt in to metric export.",
            file=sys.stderr,
        )
        sys.exit(1)

    output = Path("metrics_export.json")
    if len(sys.argv) > 1:
        output = Path(sys.argv[1])

    data = export(output)
    output.write_text(json.dumps(data, indent=2), encoding="utf-8")
    n = data.get("row_count", 0)
    print(
        f"exported {n} rows to {output}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
