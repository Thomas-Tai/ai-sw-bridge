"""W64 seat-proof — durable-ref coordinate_system origin/axis placement OOP.

Proves the UPGRADED mutate._create_coordinate_system durable path on the live
seat: optional origin_ref / x_axis_ref / y_axis_ref (each a {"persist_id":
b64} durable token) resolve via tier-1 persist, select via the callout-free
IEntity.Select2 with role marks origin=1 / X=2 / Y=4, then
InsertCoordinateSystem anchors the CS to that geometry.

The W64 mark-grid probe confirmed marks {1,2,4} route when set via
Extension.SelectByID2. This probe confirms the SAME marks route when set via
select_entity()'s IEntity.Select2(append, mark) — the path the production
handler actually uses.

Decisive discriminator: the chosen origin VERTEX is the +X/+Y/top CORNER of
the centered block at (+W/2, +H/2, +D) = (0.020, 0.015, 0.010), which is NOT
the model origin. After creation we read the CS transform; if its origin lands
at the corner (not 0,0,0), the Select2 marks routed.

Verdicts:
  PASS  — handler ok + CoordSys node + (origin at corner if transform readable)
          + survives reopen.
  WEAK_PASS — materializes + survives but transform unreadable (still strong:
          the W64 grid probe showed wrong/unrouted marks do NOT materialize).
  FAIL  — handler False / no node / origin at (0,0,0) (marks did not route).

Usage:
    C:/Python314/python.exe spikes/v0_2x/probe_csys_durable_oop.py
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

RESULTS_PATH = (
    Path(__file__).resolve().parents[1] / "_results" / "probe_csys_durable_oop.json"
)

import pythoncom  # noqa: E402
from win32com.client import VARIANT  # noqa: E402

from _feature_spike_fixtures import build_block, save_and_reopen  # noqa: E402
from ai_sw_bridge.sw_com import get_sw_app  # noqa: E402
from ai_sw_bridge import mutate  # noqa: E402
from ai_sw_bridge.selection.live import capture_persist_id  # noqa: E402

BOX_W_M = 0.040
BOX_H_M = 0.030
BOX_D_M = 0.010

CORNER = (BOX_W_M / 2, BOX_H_M / 2, BOX_D_M)  # origin vertex (NOT model origin)
X_EDGE = (0.0, BOX_H_M / 2, BOX_D_M)  # top +Y edge midpoint (runs along X)
Y_EDGE = (BOX_W_M / 2, 0.0, BOX_D_M)  # top +X edge midpoint (runs along Y)


def _null() -> Any:
    return VARIANT(pythoncom.VT_DISPATCH, None)


def _count(doc: Any) -> int:
    try:
        f = doc.FeatureManager.GetFeatures(False)
        return len(f) if f else 0
    except Exception:
        return 0


def _type_name(node: Any) -> str | None:
    for a in ("GetTypeName2", "GetTypeName"):
        try:
            m = getattr(node, a)
            return str(m() if callable(m) else m)
        except Exception:
            continue
    return None


def _find_csys(doc: Any):
    try:
        feats = doc.FeatureManager.GetFeatures(False) or []
    except Exception:
        return None, None
    for n in feats:
        t = _type_name(n)
        if t and "coord" in t.lower():
            return n, t
    return None, None


def _csys_name(node: Any) -> str | None:
    for a in ("Name", "GetName"):
        try:
            m = getattr(node, a)
            return str(m() if callable(m) else m)
        except Exception:
            continue
    return None


def _csys_origin(doc: Any, name: str) -> tuple[list[float] | None, str]:
    """Read the CS transform origin. The harvested API exposes
    GetCoordinateSystemTransformByName(NameIn)->MathTransform (NOT ...ByName2).
    The MathTransform ArrayData is 16 doubles: 3x3 rotation (0..8),
    translation (9,10,11) = CS origin in metres, scale(12), 0,0,0.
    Tries both the doc and its Extension; reports which worked."""
    for holder_name, holder in (("doc", doc), ("ext", getattr(doc, "Extension", None))):
        if holder is None:
            continue
        for meth in (
            "GetCoordinateSystemTransformByName",
            "GetCoordinateSystemTransformByName2",
        ):
            try:
                fn = getattr(holder, meth, None)
                if fn is None:
                    continue
                xform = fn(name)
                if xform is None:
                    continue
                arr = xform.ArrayData
                if arr is None or len(arr) < 12:
                    continue
                return [
                    float(arr[9]),
                    float(arr[10]),
                    float(arr[11]),
                ], f"{holder_name}.{meth}"
            except Exception as exc:  # noqa: BLE001
                _LAST_XFORM_ERR.append(
                    f"{holder_name}.{meth}: {type(exc).__name__}: {exc}"
                )
                continue
    return None, "unreadable"


_LAST_XFORM_ERR: list[str] = []


def _pick(doc: Any, sel_type: str, x: float, y: float, z: float):
    try:
        doc.ClearSelection2(True)
        if not doc.Extension.SelectByID2("", sel_type, x, y, z, False, 0, _null(), 0):
            return None
        ent = doc.SelectionManager.GetSelectedObject6(1, -1)
        doc.ClearSelection2(True)
        return ent
    except Exception:
        return None


def _ref(doc: Any, sel_type: str, pt) -> dict | None:
    ent = _pick(doc, sel_type, *pt)
    if ent is None:
        return None
    pid = capture_persist_id(doc, ent)
    if pid is None:
        return None
    return {"persist_id": base64.urlsafe_b64encode(pid).decode().rstrip("=")}


def run() -> dict[str, Any]:
    result: dict[str, Any] = {"probe_id": "W64_csys_durable_oop"}
    try:
        sw = get_sw_app()
    except Exception as exc:
        return {**result, "overall": "ERROR", "reason": f"connect: {exc!r}"}

    doc = build_block(sw)
    try:
        before = _count(doc)
        origin_ref = _ref(doc, "VERTEX", CORNER)
        x_ref = _ref(doc, "EDGE", X_EDGE)
        y_ref = _ref(doc, "EDGE", Y_EDGE)
        result["captured"] = {
            "origin": origin_ref is not None,
            "x_axis": x_ref is not None,
            "y_axis": y_ref is not None,
        }
        if not (origin_ref and x_ref and y_ref):
            return {**result, "overall": "ERROR", "reason": "durable capture failed"}

        target = {"origin_ref": origin_ref, "x_axis_ref": x_ref, "y_axis_ref": y_ref}
        ok, note = mutate._create_coordinate_system(doc, {}, target)
        result["handler_ok"] = ok
        result["handler_note"] = note

        after = _count(doc)
        result["node_delta"] = after - before
        node, tname = _find_csys(doc)
        result["csys_type"] = tname
        name = _csys_name(node) if node is not None else None
        result["csys_name"] = name

        origin_xyz, xform_via = _csys_origin(doc, name) if name else (None, "no-name")
        result["csys_origin_xyz"] = origin_xyz
        result["transform_read_via"] = xform_via
        if origin_xyz is None:
            result["transform_read_errors"] = _LAST_XFORM_ERR[:6]
        result["expected_corner"] = list(CORNER)
        origin_at_corner = None
        if origin_xyz is not None:
            origin_at_corner = all(
                abs(a - b) < 1e-4 for a, b in zip(origin_xyz, CORNER)
            )
            result["origin_at_corner"] = origin_at_corner
            result["origin_at_model_zero"] = all(abs(a) < 1e-4 for a in origin_xyz)

        # Save -> reopen survival.
        try:
            doc2 = save_and_reopen(sw, doc)
            n2, t2 = _find_csys(doc2) if doc2 is not None else (None, None)
            result["survives_reopen"] = t2 is not None
        except Exception as exc:
            result["survives_reopen"] = False
            result["reopen_error"] = f"{type(exc).__name__}: {exc}"

        materialized = ok and tname is not None and result.get("survives_reopen")
        if materialized and origin_at_corner is True:
            result["overall"] = "PASS"
            result["finding"] = (
                "Durable CS anchored at the chosen corner vertex (not the model "
                "origin) — select_entity Select2 marks {1,2,4} route correctly OOP."
            )
        elif materialized and origin_xyz is None:
            result["overall"] = "WEAK_PASS"
            result["finding"] = (
                "Durable CS materializes + survives reopen; transform origin "
                "unreadable so corner-anchoring not directly confirmed (the W64 "
                "grid probe established that unrouted marks do NOT materialize)."
            )
        elif materialized and origin_at_corner is False:
            result["overall"] = "FAIL"
            result["finding"] = (
                f"CS materialized but origin {origin_xyz} is not the corner — "
                "marks did NOT route (CS defaulted to model origin)."
            )
        else:
            result["overall"] = "FAIL"
            result["finding"] = f"handler_ok={ok}, note={note!r}, type={tname}"
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
    return result


def main() -> None:
    pythoncom.CoInitialize()
    try:
        result = run()
    finally:
        pythoncom.CoUninitialize()
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(
        json.dumps(result, indent=2, default=lambda o: f"<{type(o).__name__}>"),
        encoding="utf-8",
    )
    print(f"overall: {result.get('overall')}", file=sys.stderr)
    print(f"csys_origin_xyz: {result.get('csys_origin_xyz')}", file=sys.stderr)
    print(f"finding: {result.get('finding')}", file=sys.stderr)
    print(f"results -> {RESULTS_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
