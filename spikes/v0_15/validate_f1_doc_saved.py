"""Seat validation: F1 PAE commit reports doc_saved correctly (fix 6505bbc).
[RUN ON A LIVE SEAT]

Drives the *production* PAE functions (sw_propose/dry_run/commit_feature_add)
end-to-end and verifies the doc_saved-reporting fix: late-bound Save() returns
None on S_OK, and commit must now report doc_saved=True (it previously reported
False even though the file was written). Cross-checks against the file mtime so
the assertion does not rely on the return value alone.

  build box -> interrogate(persist_capture) -> DurableEdgeRef
  -> SaveAs3 temp .sldprt -> CloseDoc
  -> sw_propose_feature_add -> sw_dry_run_feature_add -> sw_commit_feature_add
  -> assert commit.doc_saved is True AND temp-file mtime advanced

Non-destructive: own temp .sldprt under %TEMP%; own proposals dir under %TEMP%;
deletes both at the end (unless --keep-file).

Verdict
-------
PASS    : commit.doc_saved is True and the file mtime advanced -> fix holds.
PARTIAL : the file mtime advanced (save happened) but doc_saved is not True
          -> the fix did not take effect / Save() return handling still wrong.
FAIL    : commit did not succeed, or the file was not written.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

os.environ["AI_SW_BRIDGE_FLAG_BREP_INTERROGATION"] = "1"
os.environ["AI_SW_BRIDGE_FLAG_PERSIST_CAPTURE"] = "1"

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

import pythoncom  # noqa: E402

from ai_sw_bridge.brep.interrogator import interrogate  # noqa: E402
from ai_sw_bridge.selection import DurableEdgeRef  # noqa: E402

from spike_persist_reference import build_single_box  # noqa: E402
from spike_earlybind_persist import connect_running_sw  # noqa: E402

SW_DEFAULT_TEMPLATE_PART = 8
FEATURE = {"type": "fillet_constant_radius", "radius_mm": 2.0}


class _Ctx:
    def __init__(self, doc: Any) -> None:
        self.doc = doc


def _title(d: Any) -> Any:
    t = d.GetTitle
    return t() if callable(t) else t


def run(keep_file: bool) -> dict[str, Any]:
    # Isolate proposals to a temp dir BEFORE importing mutate's dir reader runs.
    work = Path(tempfile.gettempdir()) / "ai-sw-bridge" / "validate_f1"
    work.mkdir(parents=True, exist_ok=True)
    os.environ["AI_SW_BRIDGE_PROPOSALS"] = str(work / "proposals")

    from ai_sw_bridge.mutate import (  # noqa: E402  (after env is set)
        sw_propose_feature_add,
        sw_dry_run_feature_add,
        sw_commit_feature_add,
    )

    result: dict[str, Any] = {}
    sw = connect_running_sw()

    # --- 1. Build + capture an edge ref -------------------------------------
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return {"overall": "FAIL", "reason": "NewDocument returned None"}
    build = build_single_box(doc)
    feat = doc.FeatureByName(build.get("feature_name")) if build.get("built") else None
    if feat is None:
        return {"overall": "FAIL", "reason": "could not get extrude feature"}

    payload = interrogate(feat, _Ctx(doc))
    captured = [e for e in (payload or {}).get("edges", []) if e.get("persist_id")]
    if not captured:
        _close(sw, doc)
        return {"overall": "FAIL", "reason": "no edge captured a persist token"}
    edge_ref = DurableEdgeRef.from_manifest_edge(captured[0])

    # --- 2. Save -> close ----------------------------------------------------
    tmp = work / "validate_f1_doc_saved.sldprt"
    if tmp.exists():
        try:
            tmp.unlink()
        except OSError:
            pass
    try:
        doc.SaveAs3(str(tmp), 0, 0)
    except Exception as e:  # noqa: BLE001
        _close(sw, doc)
        return {"overall": "FAIL", "reason": f"SaveAs3 raised: {e}"}
    if not tmp.exists():
        _close(sw, doc)
        return {"overall": "FAIL", "reason": "SaveAs3 produced no file"}
    try:
        sw.CloseDoc(_title(doc))
    except Exception:  # noqa: BLE001
        pass

    # --- 3. PAE: propose -> dry_run -> commit -------------------------------
    target = edge_ref.to_dict()
    prop = sw_propose_feature_add(str(tmp), FEATURE, target)
    result["propose"] = prop
    if not prop.get("ok"):
        _cleanup(work, tmp, keep_file, result)
        return {
            **result,
            "overall": "FAIL",
            "reason": f"propose failed: {prop.get('error')}",
        }
    pid = prop["proposal_id"]

    dry = sw_dry_run_feature_add(pid)
    result["dry_run"] = dry
    if not dry.get("ok"):
        _cleanup(work, tmp, keep_file, result)
        return {
            **result,
            "overall": "FAIL",
            "reason": f"dry_run failed: {dry.get('error')}",
        }

    mtime_before = tmp.stat().st_mtime
    time.sleep(1.0)  # ensure a detectable mtime delta on coarse filesystems
    commit = sw_commit_feature_add(pid)
    result["commit"] = commit
    mtime_after = tmp.stat().st_mtime if tmp.exists() else None
    result["mtime_advanced"] = bool(mtime_after and mtime_after > mtime_before)

    _cleanup(work, tmp, keep_file, result)

    saved_flag = commit.get("doc_saved") is True
    file_written = result["mtime_advanced"]
    if commit.get("ok") and saved_flag and file_written:
        overall, reason = "PASS", (
            "commit reported doc_saved=True and the file mtime advanced -- the "
            "doc_saved-reporting fix holds against late-bound Save() returning None"
        )
    elif commit.get("ok") and file_written and not saved_flag:
        overall, reason = "PARTIAL", (
            "the file was saved (mtime advanced) but commit.doc_saved is not True "
            "-- the fix did not take effect"
        )
    else:
        overall, reason = "FAIL", (
            f"commit ok={commit.get('ok')} doc_saved={commit.get('doc_saved')} "
            f"mtime_advanced={file_written}; error={commit.get('error')}"
        )
    result["overall"] = overall
    result["reason"] = reason
    return result


def _close(sw: Any, doc: Any) -> None:
    try:
        sw.CloseDoc(_title(doc))
    except Exception:  # noqa: BLE001
        pass


def _cleanup(work: Path, tmp: Path, keep: bool, result: dict[str, Any]) -> None:
    if keep:
        result["cleanup"] = f"kept temp file at {tmp} and proposals at {work}"
        return
    removed = []
    try:
        tmp.unlink()
        removed.append("temp file")
    except OSError:
        pass
    pdir = work / "proposals"
    if pdir.exists():
        for p in pdir.glob("*.json"):
            try:
                p.unlink()
            except OSError:
                pass
        removed.append("proposals")
    result["cleanup"] = (
        "removed " + ", ".join(removed) if removed else "nothing to remove"
    )


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--keep-file", action="store_true")
    args = p.parse_args()

    pythoncom.CoInitialize()
    try:
        result = run(args.keep_file)
    finally:
        pythoncom.CoUninitialize()

    payload = json.dumps(result, indent=2, default=str)
    if args.out is not None:
        args.out.write_text(payload, encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(payload)
    return {"PASS": 0, "PARTIAL": 2, "FAIL": 1}.get(result.get("overall"), 1)


if __name__ == "__main__":
    raise SystemExit(main())
