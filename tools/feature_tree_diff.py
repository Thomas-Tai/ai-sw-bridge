"""Capture and diff a SOLIDWORKS part's feature tree + equation values.

Used as the behavior-preservation gate for the class-hierarchy refactor:
build MMP on master, capture; build MMP on the refactor branch, capture;
diff. If the two snapshots match, the refactor preserved the COM-level
output the test suite cannot verify.

Usage:
    tools/feature_tree_diff.py capture <part.sldprt> <out.json>
    tools/feature_tree_diff.py diff <baseline.json> <candidate.json>

The capture step requires SOLIDWORKS to be running and the part to be
openable. The diff step is pure JSON comparison; no SW needed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _open_part(sw: Any, part_path: str) -> Any:
    """Open a part read-only via OpenDoc6."""
    # swDocPART=1, swOpenDocOptions_Silent=1, no specific config
    err_pointer = 0
    warn_pointer = 0
    doc = sw.OpenDoc6(str(part_path), 1, 1, "", err_pointer, warn_pointer)
    if doc is None:
        raise RuntimeError(f"OpenDoc6 returned None for {part_path}")
    return doc


def _walk_features(doc: Any) -> list[dict[str, str]]:
    """Walk the feature tree top-level via FeatureByPositionReverse.

    Returns a list of ``{"name": ..., "type": ...}`` in tree order.
    Uses ``GetTypeName2`` which is stable across SW versions.
    """
    out: list[dict[str, str]] = []
    # FeatureManager.GetFeatureCount returns top-level only when
    # includeSubFeats=False. We want top-level for tree-shape comparison.
    fm = doc.FeatureManager
    n = fm.GetFeatureCount(False)
    # Walk from position 0 (oldest) forward via FeatureByPositionReverse(n-1-i)
    for i in range(n):
        feat = doc.FeatureByPositionReverse(n - 1 - i)
        if feat is None:
            out.append({"name": "<null>", "type": "<null>"})
            continue
        try:
            name = feat.Name
        except Exception:
            name = "<no-name>"
        try:
            type_name = feat.GetTypeName2
        except Exception:
            type_name = "<no-type>"
        out.append({"name": str(name), "type": str(type_name)})
    return out


def _read_equations(doc: Any) -> list[dict[str, Any]]:
    """Read all equation entries via EquationMgr.

    Returns ``[{"index": i, "equation": text, "value": float|None}]``.
    """
    out: list[dict[str, Any]] = []
    eq = doc.GetEquationMgr
    if eq is None:
        return out
    count = eq.GetCount
    for i in range(count):
        try:
            text = eq.Equation(i)
        except Exception:
            text = "<read-error>"
        try:
            value = eq.Value(i)
        except Exception:
            value = None
        out.append(
            {
                "index": i,
                "equation": str(text) if text is not None else None,
                "value": float(value) if isinstance(value, (int, float)) else None,
            }
        )
    return out


def cmd_capture(part_path: str, out_path: str, use_active: bool) -> int:
    # Import here so `diff` works without pywin32 installed.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    from ai_sw_bridge.sw_com import get_sw_app

    sw = get_sw_app()
    if use_active:
        doc = sw.ActiveDoc
        if doc is None:
            raise RuntimeError(
                "--use-active-doc: SW has no active document. Open the part "
                "(or run a build that leaves it open) and try again."
            )
        recorded_path = part_path or str(doc.GetPathName) or "<active-doc>"
    else:
        doc = _open_part(sw, part_path)
        recorded_path = str(part_path)
    snapshot = {
        "part_path": recorded_path,
        "features": _walk_features(doc),
        "equations": _read_equations(doc),
    }
    Path(out_path).write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    print(
        f"captured {len(snapshot['features'])} features, "
        f"{len(snapshot['equations'])} equations -> {out_path}"
    )
    return 0


def cmd_diff(baseline_path: str, candidate_path: str) -> int:
    a = json.loads(Path(baseline_path).read_text(encoding="utf-8"))
    b = json.loads(Path(candidate_path).read_text(encoding="utf-8"))

    a_feats = [(f["name"], f["type"]) for f in a["features"]]
    b_feats = [(f["name"], f["type"]) for f in b["features"]]

    feature_match = a_feats == b_feats
    print(f"baseline:  {baseline_path}   ({len(a_feats)} features)")
    print(f"candidate: {candidate_path}  ({len(b_feats)} features)")
    print()
    if feature_match:
        print("FEATURE TREE: PASS  (identical name+type sequence)")
    else:
        print("FEATURE TREE: FAIL")
        # Show first divergence
        for i in range(max(len(a_feats), len(b_feats))):
            ai = a_feats[i] if i < len(a_feats) else None
            bi = b_feats[i] if i < len(b_feats) else None
            if ai != bi:
                print(f"  pos {i}: baseline={ai!r}  candidate={bi!r}")
                if i >= 4:
                    print("  (truncated)")
                    break

    # Compare equations by index — formula text + numeric value (rounded
    # to micrometers so float noise from independent solves doesn't trip).
    a_eqs = {e["index"]: e for e in a["equations"]}
    b_eqs = {e["index"]: e for e in b["equations"]}
    eq_match = True
    diffs: list[str] = []
    for i in sorted(set(a_eqs) | set(b_eqs)):
        ae = a_eqs.get(i)
        be = b_eqs.get(i)
        if ae is None or be is None:
            eq_match = False
            diffs.append(
                f"  idx {i}: only in {'baseline' if be is None else 'candidate'}"
            )
            continue
        if ae["equation"] != be["equation"]:
            eq_match = False
            diffs.append(
                f"  idx {i}: equation differs\n"
                f"    baseline:  {ae['equation']!r}\n"
                f"    candidate: {be['equation']!r}"
            )
            continue
        av, bv = ae["value"], be["value"]
        if av is None or bv is None:
            if av != bv:
                eq_match = False
                diffs.append(f"  idx {i}: value-availability differs: {av!r} vs {bv!r}")
            continue
        if abs(av - bv) > 1e-6:
            eq_match = False
            diffs.append(
                f"  idx {i}: value differs: baseline={av} candidate={bv} "
                f"(delta={bv-av:+g})"
            )

    print()
    if eq_match:
        print(f"EQUATIONS:    PASS  ({len(a_eqs)} entries, all match)")
    else:
        print(f"EQUATIONS:    FAIL  ({len(diffs)} differences)")
        for d in diffs[:10]:
            print(d)
        if len(diffs) > 10:
            print(f"  (... {len(diffs) - 10} more)")

    return 0 if (feature_match and eq_match) else 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    pc = sub.add_parser(
        "capture", help="capture feature tree + equations from a .SLDPRT"
    )
    pc.add_argument(
        "part_path",
        nargs="?",
        default="",
        help="absolute path to the .SLDPRT to capture (omit with --use-active-doc)",
    )
    pc.add_argument("out_path", help="output JSON path")
    pc.add_argument(
        "--use-active-doc",
        action="store_true",
        help="capture from SW's currently-active document instead of OpenDoc6",
    )

    pd = sub.add_parser("diff", help="diff two captured snapshots")
    pd.add_argument("baseline", help="baseline JSON")
    pd.add_argument("candidate", help="candidate JSON")

    args = p.parse_args()
    if args.cmd == "capture":
        return cmd_capture(args.part_path, args.out_path, args.use_active_doc)
    if args.cmd == "diff":
        return cmd_diff(args.baseline, args.candidate)
    return 2


if __name__ == "__main__":
    sys.exit(main())
