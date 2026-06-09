"""Wave-38 S1: drawing title-block PAE.

End-to-end seat test for the W38 title-block authoring path:

  1. Build a minimal .SLDPRT (20x20x10 box) in a temp dir.
  2. Propose a ``kind: "drawing"`` spec that carries a ``title_block`` block
     (Route B: drawing-level custom properties via W29 recipe reuse).
  3. dry_run — confirm the model file exists.
  4. commit  — build views, apply title-block fields to the drawing's
     CustomPropertyManager, SaveAs3 .SLDDRW, reopen and VERIFY THE EFFECT
     (Get4 read-back must equal set value — the no-op trap gate).
  5. Independently reopen the .SLDDRW here and Get4 each field (belt-and-
     braces — proves the verify ran and that the file on disk is the one
     we think it is).

Prereq: SOLIDWORKS 2024 SP1 running.

Exit: 0 iff all gates PASS; non-zero otherwise. Always writes
``spikes/v0_2x/_results/drawing_titleblock_pae.json``.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

WORKTREE = Path(__file__).resolve().parents[2]
RESULTS_PATH = (
    WORKTREE / "spikes" / "v0_2x" / "_results" / "drawing_titleblock_pae.json"
)

results: dict[str, Any] = {
    "pae": "w38_drawing_titleblock",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "gates": {},
}


def gate(name: str, ok: bool, detail: str = "") -> bool:
    results["gates"][name] = {"ok": ok, "detail": detail}
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}: {detail}")
    return ok


def save_results() -> None:
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(
        json.dumps(results, indent=2, default=str), encoding="utf-8"
    )
    print(f"  wrote {RESULTS_PATH}", file=sys.stderr)


TITLE_BLOCK = {
    "DrawingNo": "W38-BRK-001",
    "Title": "W38 Title-Block Seat",
    "Revision": "A",
    "DrawnBy": "TT",
    "Scale": "1:2",
    "Material": "6061-T6",
}


def _build_minimal_part(part_path: str) -> bool:
    """Build a 20x20x10 mm box as the drawing's model source."""
    from ai_sw_bridge.spec.builder import build as part_build

    spec = {
        "schema_version": 1,
        "name": "W38_Box",
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK_Box",
                "plane": "Front",
                "width": 20.0,
                "height": 20.0,
            },
            {
                "type": "boss_extrude_blind",
                "name": "EX_Box",
                "sketch": "SK_Box",
                "depth": 10.0,
            },
        ],
    }
    res = part_build(spec, no_dim=True, save_as=part_path)
    # build() returns a BuildResult; success == the .sldprt is on disk
    ok = getattr(res, "ok", None)
    if ok is None and isinstance(res, dict):
        ok = res.get("ok")
    return bool(ok) and os.path.isfile(part_path)


def _independent_reopen_verify(
    drawing_path: str, title_block: dict[str, str]
) -> dict[str, Any]:
    """Independent belt-and-braces verify — separate from the lifecycle's
    in-commit verify, so a bug in the lifecycle can't hide behind itself."""
    from ai_sw_bridge.com.earlybind import typed, typed_qi
    from ai_sw_bridge.com.sw_type_info import wrapper_module
    from ai_sw_bridge.sw_com import get_sw_app

    mod = wrapper_module()
    sw = get_sw_app()
    tsw = typed(sw, "ISldWorks", module=mod)

    # swDocDRAWING = 3
    ret = tsw.OpenDoc6(drawing_path, 3, 1, "", 0, 0)
    doc = ret[0] if isinstance(ret, tuple) else ret
    if doc is None:
        return {"ok": False, "errors": [f"OpenDoc6({drawing_path}) returned None"]}

    try:
        from ai_sw_bridge.com.earlybind import typed_qi as _tq  # noqa: F401

        mdoc2 = typed_qi(doc, "IModelDoc2", module=mod)
        cpm_raw = mdoc2.Extension.CustomPropertyManager("")
        if cpm_raw is None:
            return {"ok": False, "errors": ["cpm is None"]}
        typed_cpm = typed_qi(cpm_raw, "ICustomPropertyManager", module=mod)

        read_back: list[dict[str, Any]] = []
        errors: list[str] = []
        names_set = set(typed_cpm.GetNames() or ())
        for name, expected in title_block.items():
            exists = name in names_set
            try:
                _resolved, pvalue, _resolved2 = typed_cpm.Get4(name, False)
            except Exception as exc:
                errors.append(f"Get4({name}) raised {exc!r}")
                continue
            match = exists and pvalue == expected
            read_back.append({
                "name": name,
                "exists": exists,
                "expected": expected,
                "value": pvalue,
                "match": match,
            })
            if not match:
                errors.append(
                    f"reopen mismatch {name}: expected {expected!r}, "
                    f"got {pvalue!r} (exists={exists})"
                )
        return {
            "ok": not errors and len(read_back) == len(title_block),
            "read_back": read_back,
            "errors": errors,
        }
    finally:
        try:
            t = doc.GetTitle
            t = t() if callable(t) else t
            sw.CloseDoc(t)
        except Exception:
            pass


def run() -> int:
    print("=" * 70)
    print("Wave-38 S1: drawing title-block PAE")
    print("=" * 70)

    from ai_sw_bridge.mutate import (
        sw_commit_drawing,
        sw_dry_run_drawing,
        sw_propose_drawing,
    )

    _tmp = Path(tempfile.gettempdir())
    _ts = int(time.time())
    PART_PATH = str(_tmp / f"w38_titleblock_{_ts}.SLDPRT")
    DRAW_PATH = str(_tmp / f"w38_titleblock_{_ts}.SLDDRW")

    # --- Gate 1: build minimal part ---
    print("\n--- Building minimal part ---")
    built = _build_minimal_part(PART_PATH)
    if not gate("1_part_built", built and os.path.isfile(PART_PATH),
                f"part={PART_PATH}"):
        save_results()
        return 1

    # --- Gate 2: propose drawing spec with title_block ---
    print("\n--- Proposing drawing spec with title_block ---")
    spec: dict[str, Any] = {
        "kind": "drawing",
        "name": "W38_TitleBlock",
        "model": PART_PATH,
        "views": ["front", "top", "right", "isometric"],
        "sheet": {"template_size": "A3"},
        "title_block": TITLE_BLOCK,
    }
    prop = sw_propose_drawing(spec)
    if not gate("2_propose_ok", bool(prop.get("ok")),
                prop.get("error") or f"pid={prop.get('proposal_id')}"):
        save_results()
        return 1
    pid = prop["proposal_id"]

    # --- Gate 3: dry_run ---
    print("\n--- Dry run ---")
    dry = sw_dry_run_drawing(pid)
    if not gate("3_dry_run_ok", bool(dry.get("ok")),
                dry.get("error") or "model present"):
        save_results()
        return 1

    # --- Gate 4: commit — the load-bearing gate ---
    print("\n--- Commit drawing (applies title_block, verifies via reopen) ---")
    commit = sw_commit_drawing(pid, DRAW_PATH)
    results["commit_result"] = {
        "ok": commit.get("ok"),
        "sheet_count": commit.get("sheet_count"),
        "view_count": commit.get("view_count"),
        "save_path": commit.get("save_path"),
        "title_block": commit.get("title_block"),
        "title_block_verify": commit.get("title_block_verify"),
        "error": commit.get("error"),
    }
    if not gate("4_commit_ok", bool(commit.get("ok")),
                commit.get("error") or f"drawing={DRAW_PATH}"):
        save_results()
        return 1

    # --- Gate 5: file-on-disk ---
    print("\n--- File-on-disk check ---")
    if not gate("5_file_exists", os.path.isfile(DRAW_PATH),
                f"size={os.path.getsize(DRAW_PATH)} B"):
        save_results()
        return 1

    # --- Gate 6: independent reopen verify ---
    print("\n--- Independent reopen verify ---")
    time.sleep(0.5)
    indep = _independent_reopen_verify(DRAW_PATH, TITLE_BLOCK)
    results["independent_verify"] = indep
    if not gate("6_independent_reopen",
                bool(indep.get("ok")),
                "; ".join(indep.get("errors", [])) or
                f"{len(indep.get('read_back', []))} fields match"):
        save_results()
        return 1

    # --- Gate 7: every field matches (the load-bearing no-op trap gate) ---
    read_back = indep.get("read_back", [])
    per_field_ok = all(rb.get("match") for rb in read_back)
    if not gate("7_all_fields_match", per_field_ok and len(read_back) == len(TITLE_BLOCK),
                f"matched {sum(rb['match'] for rb in read_back)}/{len(TITLE_BLOCK)}"):
        save_results()
        return 1

    save_results()
    print("\nALL GATES PASS — W38 S1 GREEN")
    return 0


if __name__ == "__main__":
    sys.exit(run())
