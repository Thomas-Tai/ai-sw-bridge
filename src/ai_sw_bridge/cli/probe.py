"""ai-sw-probe: COM connectivity check.

Verifies that SOLIDWORKS is running, that pywin32 can dispatch the
Application object, and reports the SW build revision plus any active
document. Use this first to confirm your install is healthy.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from ..sw_com import DOC_TYPE_NAMES, get_active_doc, get_sw_app, resolve
from .stability import add_tier, cli_stability


def probe() -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": False,
        "sw_revision": None,
        "active_doc": None,
        "error": None,
    }

    try:
        sw = get_sw_app()
    except Exception as exc:
        result["error"] = (
            f"could not dispatch SldWorks.Application: {exc!r}. "
            "Is SOLIDWORKS running?"
        )
        return result

    try:
        result["sw_revision"] = str(resolve(sw, "RevisionNumber"))
    except Exception as exc:
        result["error"] = f"connected but RevisionNumber failed: {exc!r}"

    try:
        doc = get_active_doc(sw)
        if doc is None:
            result["active_doc"] = None
        else:
            doc_info: dict[str, str | None] = {}
            try:
                doc_info["path"] = str(resolve(doc, "GetPathName"))
            except Exception:
                doc_info["path"] = None
            try:
                t = int(resolve(doc, "GetType"))
                doc_info["type"] = DOC_TYPE_NAMES.get(t, f"Unknown({t})")
            except Exception:
                doc_info["type"] = None
            try:
                doc_info["title"] = str(resolve(doc, "GetTitle"))
            except Exception:
                doc_info["title"] = None
            result["active_doc"] = doc_info
    except Exception as exc:
        result["error"] = (
            result["error"] or ""
        ) + f" | active_doc query failed: {exc!r}"

    result["ok"] = result["error"] is None
    return result


@cli_stability("experimental")
def main() -> int:
    parser = argparse.ArgumentParser(
        prog="ai-sw-probe",
        description=(
            "Probe the running SOLIDWORKS session: verify pywin32 can "
            "dispatch SldWorks.Application, report the SW revision, and "
            "summarize the active document (if any). Use this first to "
            "confirm your install is healthy. Takes no arguments."
        ),
    )
    add_tier(parser, "experimental")
    parser.parse_args()
    result = probe()
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
