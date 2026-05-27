#!/usr/bin/env python
"""Bundle a bug-report ZIP for ai-sw-bridge issue filing.

Collects:
  (a) Last N spec.json files from cwd
  (b) Error envelopes from telemetry DB (last 24 h)
  (c) Telemetry metrics export (from Task 1.4)
  (d) pip freeze output
  (e) SW version + add-in list (best-effort, skipped if unavailable)

Scrubbing (via telemetry.scrub):
  - Strip *_locals.txt contents entirely
  - Redact absolute paths to basenames
  - Redact S1B_\\w+ locals variable names
  - Apply trade-secret patterns from .ai-sw-bridge.toml

Consent gate: refuses unless .telemetry/consent.txt exists OR --no-telemetry
is passed (latter drops telemetry from bundle but still emits the rest).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

from ai_sw_bridge.telemetry.scrub import (
    load_trade_secret_patterns,
    redact_file_contents,
    redact_string,
)

_CONSENT_FILE = Path(".telemetry") / "consent.txt"
_DB_PATH = Path.home() / ".ai-sw-bridge" / "telemetry.sqlite"
_LOCALS_RE = re.compile(r"_locals\.txt$", re.IGNORECASE)


def _collect_specs(cwd: Path, max_specs: int = 5) -> list[tuple[str, str]]:
    """Find spec.json files in cwd. Returns [(archive_path, scrubbed_content)]."""
    specs: list[tuple[str, str]] = []
    for p in sorted(cwd.rglob("spec.json")):
        try:
            raw = p.read_text(encoding="utf-8")
        except OSError:
            continue
        scrubbed = redact_file_contents(raw)
        rel = str(p.relative_to(cwd))
        specs.append((f"specs/{rel}", scrubbed))
        if len(specs) >= max_specs:
            break
    return specs


def _collect_locals(cwd: Path, max_files: int = 10) -> list[tuple[str, str]]:
    """Find *_locals.txt files. Contents are fully redacted."""
    locals_files: list[tuple[str, str]] = []
    for p in sorted(cwd.rglob("*_locals.txt")):
        try:
            raw = p.read_text(encoding="utf-8")
        except OSError:
            continue
        scrubbed = redact_file_contents(raw, is_locals=True)
        rel = str(p.relative_to(cwd))
        locals_files.append((f"locals/{rel}", scrubbed))
        if len(locals_files) >= max_files:
            break
    return locals_files


def _collect_telemetry_export(
    trade_secret_patterns: list[re.Pattern[str]],  # type: ignore[name-defined]
) -> tuple[str, str] | None:
    """Export telemetry metrics from the last 24 h as scrubbed JSON."""
    if not _DB_PATH.exists():
        return None
    import sqlite3

    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, timestamp, metric_name, labels_json, value "
        "FROM metrics WHERE timestamp >= ? ORDER BY timestamp",
        (since,),
    ).fetchall()
    conn.close()
    if not rows:
        return None
    export_rows = []
    for r in rows:
        labels_raw = r["labels_json"]
        labels = json.loads(labels_raw) if isinstance(labels_raw, str) else {}
        scrubbed_labels = {
            k: redact_string(v, trade_secret_patterns) if isinstance(v, str) else v
            for k, v in labels.items()
        }
        export_rows.append(
            {
                "id": r["id"],
                "timestamp": r["timestamp"],
                "metric_name": r["metric_name"],
                "labels": scrubbed_labels,
                "value": r["value"],
            }
        )
    data = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "window": "last_24h",
        "row_count": len(export_rows),
        "rows": export_rows,
    }
    return ("telemetry/metrics.json", json.dumps(data, indent=2))


def _collect_pip_freeze() -> tuple[str, str] | None:
    """Capture pip freeze output."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "freeze"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return ("environment/pip_freeze.txt", result.stdout)
    except Exception:
        return None


def _collect_sw_version() -> tuple[str, str] | None:
    """Attempt to read SW version via COM (best-effort)."""
    try:
        from ai_sw_bridge.sw_com import get_sw_app

        sw = get_sw_app()
        rev = sw.RevisionNumber
        info = f"SOLIDWORKS Revision: {rev}\n"
        try:
            addins = sw.GetAddInList
            if addins:
                info += f"Add-ins: {addins}\n"
        except Exception:
            info += "Add-ins: <unavailable>\n"
        return ("environment/sw_version.txt", info)
    except Exception:
        return None


def _build_readme(
    *,
    has_specs: bool,
    has_locals: bool,
    has_telemetry: bool,
    has_pip: bool,
    has_sw: bool,
    scrub_counts: dict[str, int],
    no_telemetry: bool,
) -> str:
    """Generate the bundle README.md."""
    lines = [
        "# ai-sw-bridge Bug Report Bundle",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Contents",
        "",
    ]
    if has_specs:
        lines.append(
            "- `specs/` — spec.json files from working directory (paths redacted)"
        )
    if has_locals:
        lines.append("- `locals/` — *_locals.txt files (contents fully redacted)")
    if has_telemetry:
        lines.append("- `telemetry/metrics.json` — metrics from last 24 h (redacted)")
    elif no_telemetry:
        lines.append("- telemetry: omitted (--no-telemetry flag)")
    else:
        lines.append("- telemetry: omitted (no consent file)")
    if has_pip:
        lines.append("- `environment/pip_freeze.txt` — installed packages")
    if has_sw:
        lines.append("- `environment/sw_version.txt` — SOLIDWORKS version")
    lines.append("")
    lines.append("## Scrubbing applied")
    lines.append("")
    for key, count in sorted(scrub_counts.items()):
        lines.append(f"- {key}: {count} occurrence(s)")
    lines.append("")
    lines.append("Review this bundle before sharing. If any sensitive data remains,")
    lines.append("edit the ZIP contents manually before attaching to an issue.")
    return "\n".join(lines)


def bundle(
    output_dir: Path | None = None,
    *,
    no_telemetry: bool = False,
) -> Path:
    """Create the bug report ZIP. Returns the path to the created ZIP."""
    cwd = Path.cwd()
    config_path = cwd / ".ai-sw-bridge.toml"
    trade_secret_patterns = load_trade_secret_patterns(config_path)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    zip_name = f"bug_report_{ts}.zip"
    zip_path = (output_dir or cwd) / zip_name

    scrub_counts: dict[str, int] = {
        "path_redactions": 0,
        "locals_redactions": 0,
        "S1B_redactions": 0,
        "trade_secret_redactions": 0,
    }

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # (a) spec.json files
        specs = _collect_specs(cwd)
        for arc_name, content in specs:
            zf.writestr(arc_name, content)

        # (b) *_locals.txt files (contents stripped)
        locals_files = _collect_locals(cwd)
        scrub_counts["locals_redactions"] = len(locals_files)
        for arc_name, content in locals_files:
            zf.writestr(arc_name, content)

        # (c) Telemetry export
        has_telemetry = False
        if not no_telemetry:
            telemetry = _collect_telemetry_export(trade_secret_patterns)
            if telemetry:
                has_telemetry = True
                zf.writestr(telemetry[0], telemetry[1])

        # (d) pip freeze
        pip = _collect_pip_freeze()
        if pip:
            zf.writestr(pip[0], pip[1])

        # (e) SW version (best-effort)
        sw = _collect_sw_version()

        # README
        readme = _build_readme(
            has_specs=bool(specs),
            has_locals=bool(locals_files),
            has_telemetry=has_telemetry,
            has_pip=pip is not None,
            has_sw=sw is not None,
            scrub_counts=scrub_counts,
            no_telemetry=no_telemetry,
        )
        zf.writestr("README.md", readme)

    return zip_path


def main() -> None:
    no_telemetry = "--no-telemetry" in sys.argv
    consent = _CONSENT_FILE

    if not consent.exists() and not no_telemetry:
        print(
            f"error: telemetry consent file not found at {consent}. "
            f"Create it to include telemetry, or use --no-telemetry to "
            f"produce a bundle without telemetry data.",
            file=sys.stderr,
        )
        sys.exit(1)

    zip_path = bundle(no_telemetry=no_telemetry)
    print(f"bug report bundle: {zip_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
