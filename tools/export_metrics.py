#!/usr/bin/env python
"""Export telemetry metrics to a sanitized JSON file.

Opt-in only. Refuses to run unless .telemetry/consent.txt exists (per
privacy_review.md and UIUX.md §14). Redaction via telemetry.scrub.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from ai_sw_bridge.telemetry.scrub import load_trade_secret_patterns, redact_string

_CONSENT_FILE = Path(".telemetry") / "consent.txt"
_DB_PATH = Path.home() / ".ai-sw-bridge" / "telemetry.sqlite"


def _redact_row(row: dict, trade_secret_patterns: list[re.Pattern[str]]) -> dict:
    """Redact sensitive strings in a metrics row."""
    labels = row.get("labels", {})
    redacted_labels = {}
    for k, v in labels.items():
        if isinstance(v, str):
            redacted_labels[k] = redact_string(v, trade_secret_patterns)
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
    trade_secret_patterns = load_trade_secret_patterns(config_path)

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
