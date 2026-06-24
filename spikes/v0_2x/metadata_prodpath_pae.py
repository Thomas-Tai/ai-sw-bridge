"""W29 production-path PAE — exercises the SHIPPING metadata lifecycle.

Unlike metadata_pae.py (which duplicates the COM logic inline), this driver
runs the ACTUAL production functions:
    propose_properties -> dry_run_properties -> commit_properties

so the seat verdict adjudicates the code that ships, not a parallel copy.

Gates:
  G1 propose ok           — schema + semantic validation pass
  G2 dry_run ok           — model file resolves
  G3 commit ok            — Add3 + Save3 + reopen read-back all match (the
                            commit_properties internal verify-the-EFFECT)
  G4 count delta          — count_after >= count_before + N
  G5 reopen read-back      — every prop's reopen value == set value
  G6 overwrite=false skip — a second commit with overwrite=false skips existing
  G7 doc-type fail-closed — a .sldprt path with a bogus (.txt) ext is rejected
                            at propose (semantic validator)

VERIFY THE EFFECT: G3/G5 read the props back AFTER a close+reopen cycle, which
also exercises the close-then-reopen path flagged in
reference_close_corrupts_com.md — if COM corrupts, G3 surfaces it as a reopen
failure rather than a false PASS.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

# repo_root = the worktree root (this file: <root>/spikes/v0_2x/metadata_prodpath_pae.py)
repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root / "src"))

# A real committed part fixture (copied so we never mutate the original).
# repo_root is the worktree root (.claude/worktrees/aisw-W29); the main checkout
# that holds the committed captures/ fixtures is parents[2] of that.
SOURCE_PART = (
    repo_root.parents[2] / "captures" / "v0_10_validation" / "filleted_box.SLDPRT"
)


def run() -> dict:
    result: dict = {"ok": False, "gates": {}, "errors": [], "stages": []}

    from ai_sw_bridge.metadata.lifecycle import (
        propose_properties,
        dry_run_properties,
        commit_properties,
    )

    if not SOURCE_PART.is_file():
        result["errors"].append(f"source part missing: {SOURCE_PART}")
        return result

    tmpdir = Path(tempfile.mkdtemp(prefix="aisw_W29_pae_"))
    test_part = tmpdir / "W29_props_box.sldprt"
    shutil.copy(SOURCE_PART, test_part)
    result["test_part"] = str(test_part)

    spec = {
        "kind": "properties",
        "model": str(test_part),
        "properties": {
            "PartNo": "BRK-001",
            "Description": "W29 test bracket",
            "Revision": "A",
        },
        "overwrite": True,
    }

    # G1 propose --------------------------------------------------------------
    result["stages"].append("propose")
    prop = propose_properties(spec)
    result["gates"]["G1_propose_ok"] = bool(prop.get("ok"))
    if not prop.get("ok"):
        result["errors"].append(f"propose failed: {prop.get('error')}")
        return result

    # G2 dry_run --------------------------------------------------------------
    result["stages"].append("dry_run")
    dry = dry_run_properties(spec)
    result["gates"]["G2_dry_run_ok"] = bool(dry.get("ok"))
    if not dry.get("ok"):
        result["errors"].append(f"dry_run failed: {dry.get('error')}")
        return result

    # G3-G5 commit (production COM path) --------------------------------------
    result["stages"].append("commit")
    from ai_sw_bridge.sw_com import get_sw_app

    sw = get_sw_app()
    if sw is None:
        result["errors"].append("get_sw_app() returned None")
        return result

    commit = commit_properties(sw, spec)
    result["commit_result"] = {
        k: commit.get(k)
        for k in (
            "ok",
            "count_before",
            "count_after",
            "saved",
            "summary",
            "errors",
            "read_back",
        )
    }
    result["gates"]["G3_commit_ok"] = bool(commit.get("ok"))

    rb = commit.get("read_back", [])
    result["gates"]["G5_reopen_read_back"] = bool(rb) and all(
        e.get("match") for e in rb
    )
    cb, ca = commit.get("count_before"), commit.get("count_after")
    n = len(commit.get("props_set", []))
    result["gates"]["G4_count_delta"] = (
        cb is not None and ca is not None and ca >= cb + n and n == 3
    )

    if not commit.get("ok"):
        result["errors"].extend(commit.get("errors", []))
        # keep going to record negative gates where possible

    # G6 overwrite=false skip -------------------------------------------------
    result["stages"].append("overwrite_false")
    spec_no_ow = dict(spec)
    spec_no_ow["properties"] = {"PartNo": "SHOULD-NOT-REPLACE"}
    spec_no_ow["overwrite"] = False
    commit2 = commit_properties(sw, spec_no_ow)
    skipped = commit2.get("props_skipped", [])
    result["overwrite_false_result"] = {
        "props_skipped": skipped,
        "props_set": commit2.get("props_set", []),
    }
    # PartNo already exists -> must be skipped, original value preserved
    result["gates"]["G6_overwrite_false_skip"] = any(
        s.get("name") == "PartNo" for s in skipped
    ) and not commit2.get("props_set")

    # G7 doc-type / ext fail-closed at propose --------------------------------
    result["stages"].append("fail_closed")
    bad_spec = dict(spec)
    bad_spec["model"] = str(test_part.with_suffix(".txt"))
    bad_prop = propose_properties(bad_spec)
    result["gates"]["G7_ext_fail_closed"] = (not bad_prop.get("ok")) and (
        "sldprt" in (bad_prop.get("error", "").lower())
        or "extension" in (bad_prop.get("error", "").lower())
    )

    # cleanup: close any docs the lifecycle left open (defensive)
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass

    result["ok"] = all(result["gates"].values())
    return result


if __name__ == "__main__":
    print("=== W29 production-path PAE ===", file=sys.stderr)
    out = run()
    print(json.dumps(out, indent=2, default=str))
    sys.exit(0 if out.get("ok") else 1)
