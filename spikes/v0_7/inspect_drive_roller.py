"""Phase 0 SANITY+DIAGNOSE: inspect the live DriveRoller part.

Reports:
  - Body bbox (to detect whether revolve_boss/revolve_cut produced geometry)
  - Each sketch's segments: type, ConstructionGeometry flag, endpoints
  - ModelToSketchTransform for SK_BeltGripGroove (re-confirm sketch axis mapping)

Run after `ai-sw-build examples/drive_roller/spec.json --no-dim`, with the
resulting part still open as the active doc in SW.
"""

from __future__ import annotations

import sys

import pythoncom  # noqa: F401  pywin32 COM init
import win32com.client


def _maybe(obj, name, default=None):
    try:
        return getattr(obj, name)
    except Exception:
        return default


def _safe(call):
    try:
        return call()
    except Exception as e:
        return f"<error: {e}>"


def main() -> int:
    sw = win32com.client.GetActiveObject("SldWorks.Application")
    doc = sw.ActiveDoc
    if doc is None:
        print("no active doc")
        return 1
    print(f"active doc: {doc.GetTitle}")

    # Body bbox via doc.GetPartBox -- legacy 6-double API.
    bbox = _safe(lambda: doc.GetPartBox(True))
    print(f"GetPartBox: {bbox}")

    # Walk all features in the tree; collect those whose specific-feature is a sketch.
    target_sketches = ("SK_Body", "SK_BeltGripGroove")
    sketches: dict[str, object] = {}
    f = doc.FirstFeature
    while f is not None:
        try:
            fname = f.Name
            ftype = f.GetTypeName2
        except Exception:
            fname, ftype = "?", "?"
        if ftype == "ProfileFeature" and fname in target_sketches:
            sk = _safe(lambda f=f: f.GetSpecificFeature2)
            if sk is not None:
                sketches[fname] = sk
        f = _safe(lambda f=f: f.GetNextFeature)

    print(f"\nfound sketches: {list(sketches.keys())}")
    for sketch_name in target_sketches:
        sk = sketches.get(sketch_name)
        if sk is None:
            print(f"\n[{sketch_name}] sketch not found in tree")
            continue
        print(f"\n[{sketch_name}]")
        # ModelToSketchTransform
        tx = _safe(lambda: sk.ModelToSketchTransform)
        ad = _safe(lambda: tx.ArrayData if tx else None)
        if ad:
            try:
                rows = list(ad)
                print(f"  ModelToSketchTransform ArrayData ({len(rows)} elements):")
                for i in range(0, min(len(rows), 16), 4):
                    print(f"    [{i:2d}..]: {rows[i:i + 4]}")
            except Exception as e:
                print(f"  ArrayData iter error: {e}")
        # Segments
        segs = _safe(lambda: sk.GetSketchSegments)
        if not segs:
            print("  no GetSketchSegments")
            continue
        for i, s in enumerate(segs):
            try:
                construction = bool(_maybe(s, "ConstructionGeometry", False))
            except Exception:
                construction = "?"
            try:
                seg_type_num = s.GetType
            except Exception:
                seg_type_num = "?"
            sp = _maybe(s, "GetStartPoint2")
            ep = _maybe(s, "GetEndPoint2")
            sp_xyz = (
                f"({sp.X * 1000:.2f}, {sp.Y * 1000:.2f}, {sp.Z * 1000:.2f})"
                if sp
                else "?"
            )
            ep_xyz = (
                f"({ep.X * 1000:.2f}, {ep.Y * 1000:.2f}, {ep.Z * 1000:.2f})"
                if ep
                else "?"
            )
            print(
                f"  seg[{i}] type={seg_type_num} construction={construction} "
                f"start={sp_xyz} end={ep_xyz}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
