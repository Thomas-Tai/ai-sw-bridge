"""W59 / #9 — move_copy_body spike harness.

Authored seat-free (W1 Sonnet). RUN ON A LIVE SEAT (W0).

O1 introspection (NEVER guess):
    Phase 1 dumps the real InsertMoveCopyBody2-family method signatures
    from sldworks.tlb by FUNCDESC walk (no makepy regen, no GetTypeInfo
    on a live dispatch).  Token-walks IFeatureManager + IPartDoc for
    Move/Copy/Body members and records full parameter VT + names.

    The dumped signature is recorded in the spike JSON output and in
    the handler docstring (features/move_copy_body.py).

Verify-the-effect (the ONLY success signal):
    move  -> body-centroid / bbox translation by the commanded delta
             (re-measure after save->reopen)
    copy  -> body count +1 (persists after save->reopen)

    NEVER report success from ok=True, a non-None return, GetErrorCode2,
    or a feature-count alone.

Pipeline per kind:
    1. Build fixture (single box, 20x20x10mm)
    2. Measure before: body_count + per-body centroid (GetCenterOfMass)
    3. Call InsertMoveCopyBody2 (move: Copy=False, dx=5mm)
    4. Measure after: centroid delta
    5. Save->reopen->ForceRebuild3
    6. Re-measure: assert centroid delta persists

    7. Build fresh fixture
    8. Measure before: body_count
    9. Call InsertMoveCopyBody2 (copy: Copy=True, dx=20mm)
    10. Measure after: body_count +1
    11. Save->reopen->ForceRebuild3
    12. Re-measure: assert body_count persists

Exit codes: 0 = PASS, 2 = PARTIAL, 1 = FAIL
Output: JSON to stdout or --out file.

Usage:
    .venv-py310/Scripts/python.exe spikes/v0_2x/spike_move_copy_body.py
    .venv-py310/Scripts/python.exe spikes/v0_2x/spike_move_copy_body.py --out report.json
    .venv-py310/Scripts/python.exe spikes/v0_2x/spike_move_copy_body.py --mode vba
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

WORKTREE = Path(__file__).resolve().parents[2]
RESULTS_PATH = WORKTREE / "spikes" / "v0_2x" / "_results" / "move_copy_body.json"

SW_TLB_PATH = r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\sldworks.tlb"
SW_DEFAULT_TEMPLATE_PART = 8

BOX_W_M = 0.020
BOX_H_M = 0.020
BOX_D_M = 0.010

MOVE_DELTA_M = 0.005
COPY_OFFSET_M = 0.025

VT_MAP = {
    0: "VT_EMPTY",
    2: "VT_I2",
    3: "VT_I4",
    4: "VT_R4",
    5: "VT_R8",
    6: "VT_CY",
    7: "VT_DATE",
    8: "VT_BSTR",
    9: "VT_DISPATCH",
    10: "VT_ERROR",
    11: "VT_BOOL",
    12: "VT_VARIANT",
    13: "VT_UNKNOWN",
    16: "VT_I1",
    17: "VT_UI1",
    18: "VT_UI2",
    19: "VT_UI4",
    22: "VT_INT",
    23: "VT_UINT",
    24: "VT_VOID",
    26: "VT_LPSTR",
    0x2000: "VT_ARRAY_flag",
}

INVKIND_NAMES = {1: "FUNCTION", 2: "PROPERTYGET", 4: "PROPERTYPUT", 8: "PROPERTYPUTREF"}


def _vt_str(vt: int) -> str:
    base = vt & 0xFFF
    array = bool(vt & 0x2000)
    byref = bool(vt & 0x4000)
    name = VT_MAP.get(base, f"VT_{base}")
    suffix = ""
    if array:
        suffix += "[]"
    if byref:
        suffix += "*"
    return name + suffix


def _decode_tdesc(tdesc: Any) -> str:
    if tdesc is None:
        return "None"
    if isinstance(tdesc, (tuple, list)):
        vt = tdesc[0] if tdesc else 0
        if isinstance(vt, (tuple, list)):
            inner = _decode_tdesc(vt)
            return f"PTR({inner})"
        return _vt_str(int(vt))
    return str(tdesc)


def _decode_param_flags(flags: int) -> str:
    parts = []
    if flags & 0x1:
        parts.append("IN")
    if flags & 0x2:
        parts.append("OUT")
    if flags & 0x4:
        parts.append("LCID")
    if flags & 0x8:
        parts.append("RETVAL")
    if flags & 0x10:
        parts.append("OPT")
    if flags & 0x40:
        parts.append("HASDEFAULT")
    return "|".join(parts) if parts else "none"


def _decode_arg(arg_tuple: Any, param_name: str) -> dict[str, Any]:
    if not isinstance(arg_tuple, (tuple, list)) or len(arg_tuple) < 1:
        return {"name": param_name, "raw": str(arg_tuple)}
    tdesc = arg_tuple[0]
    flags = int(arg_tuple[1]) if len(arg_tuple) > 1 else 0
    default = arg_tuple[2] if len(arg_tuple) > 2 else None
    return {
        "name": param_name,
        "type": _decode_tdesc(tdesc),
        "flags": _decode_param_flags(flags),
        "default": default,
    }


def _walk_sldworks_fm_token_walk(tlb: Any, tokens: tuple[str, ...]) -> dict[str, Any]:
    """Walk sldworks.tlb FUNCDESC for interfaces matching tokens.

    Mirrors spike_rib.py's _walk_swconst_typelib pattern adapted for
    FUNCDESC method enumeration (not VARDESC enum enumeration).
    Targets IFeatureManager and IPartDoc specifically.
    """
    focus_ifaces = ("IFeatureManager", "IPartDoc", "IModelDoc2")
    report: dict[str, Any] = {"interfaces": {}}

    n = tlb.GetTypeInfoCount()
    for i in range(n):
        name, *_ = tlb.GetDocumentation(i)
        if name not in focus_ifaces:
            continue
        info = tlb.GetTypeInfo(i)
        ta = info.GetTypeAttr()
        matching_members: list[dict[str, Any]] = []

        for f_idx in range(ta.cFuncs):
            try:
                fd = info.GetFuncDesc(f_idx)
                memid = fd.memid
                names = info.GetNames(memid)
                if not names:
                    continue
                mname = names[0]
                if not any(t.lower() in mname.lower() for t in tokens):
                    continue

                param_names = list(names[1:]) if len(names) > 1 else []
                params: list[dict[str, Any]] = []
                for p_idx in range(fd.cParams):
                    p_name = (
                        param_names[p_idx] if p_idx < len(param_names) else f"p{p_idx}"
                    )
                    if fd.args and p_idx < len(fd.args):
                        params.append(_decode_arg(fd.args[p_idx], p_name))
                    else:
                        params.append({"name": p_name, "type": "unknown"})

                ret_type = _decode_tdesc(fd.elemdescFunc.tdesc)
                invkind = INVKIND_NAMES.get(fd.invkind, str(fd.invkind))

                matching_members.append(
                    {
                        "name": mname,
                        "memid": memid,
                        "invkind": invkind,
                        "cParams": fd.cParams,
                        "return_type": ret_type,
                        "params": params,
                    }
                )
            except Exception as exc:
                matching_members.append({"error": f"f_idx={f_idx}: {exc!r}"})

        if matching_members:
            report["interfaces"][name] = matching_members

    return report


def _sketch_rect_on_front(
    doc: Any, w: float, h: float, cx: float = 0.0, cy: float = 0.0
) -> None:
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    sk = doc.SketchManager
    sk.InsertSketch(True)
    sk.CreateCornerRectangle(
        cx - w / 2,
        cy - h / 2,
        0.0,
        cx + w / 2,
        cy + h / 2,
        0.0,
    )
    sk.InsertSketch(True)


def _extrude_merge(doc: Any, depth_m: float) -> Any:
    fm = doc.FeatureManager
    return fm.FeatureExtrusion3(
        True,
        False,
        False,
        0,
        0,
        depth_m,
        0.0,
        False,
        False,
        False,
        False,
        0.0,
        0.0,
        False,
        False,
        False,
        False,
        True,
        True,
        True,
        0,
        0,
        False,
    )


def _build_box(sw: Any) -> dict[str, Any]:
    """Build a single 20x20x10mm box fixture for move/copy testing."""
    result: dict[str, Any] = {}
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        result["error"] = "NewDocument returned None"
        return result

    try:
        _sketch_rect_on_front(doc, BOX_W_M, BOX_H_M)
        feat = _extrude_merge(doc, BOX_D_M)
        if feat is None or isinstance(feat, int):
            result["error"] = "extrude did not materialize"
            return result

        doc.ForceRebuild3(False)
        result["doc"] = doc
        result["built"] = True
    except Exception as exc:
        result["error"] = f"build failed: {exc!r}\n{traceback.format_exc()}"
    return result


def _get_bodies(doc: Any) -> list[Any]:
    """Get solid bodies via IPartDoc.GetBodies2 (type 0 = solid)."""
    try:
        bodies = doc.GetBodies2(0, True)
        if bodies is None:
            return []
        return list(bodies) if isinstance(bodies, (list, tuple)) else [bodies]
    except Exception:
        return []


def _body_centroid(doc: Any) -> dict[str, float] | None:
    """Read body centroid via IMassProperty2 on the part."""
    try:
        ext = doc.Extension
        mp = ext.CreateMassProperty()
        if mp is None:
            return None
        cog = mp.CenterOfMass
        if cog is None:
            return None
        if callable(cog):
            cog = cog()
        if cog is None:
            return None
        cog_list = list(cog) if isinstance(cog, (tuple, list)) else [cog]
        if len(cog_list) < 3:
            return None
        return {
            "x_m": float(cog_list[0]),
            "y_m": float(cog_list[1]),
            "z_m": float(cog_list[2]),
        }
    except Exception:
        return None


def _total_volume(doc: Any) -> float | None:
    """Sum volumes of all solid bodies."""
    bodies = _get_bodies(doc)
    if not bodies:
        return None
    total = 0.0
    for b in bodies:
        try:
            mp = b.GetMassProperties2(0)
            if mp and len(mp) >= 3:
                total += float(mp[2])
        except Exception:
            continue
    return total if total > 0 else None


def _save_fixture(sw: Any, doc: Any) -> dict[str, Any]:
    """Persist the in-memory doc to a temp path via SaveAs3 (W29 doctrine).

    Does NOT close or reopen — the caller owns the doc handle. Session
    teardown (close + reopen for verify) lives in the outer ``run()``
    finally via ``sw.CloseAllDocuments(True)`` + ``sw.OpenDoc6``, the
    only proven safe pattern; ``sw.CloseDoc`` mid-session corrupts the
    COM channel (next OpenDoc6 can fault).
    """
    result: dict[str, Any] = {"ok": False}
    tmp_dir = Path(tempfile.gettempdir()) / "ai-sw-bridge"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    save_path = str(tmp_dir / "spike_move_copy_body.sldprt")

    try:
        errors = 0
        warnings = 0
        ret = doc.SaveAs3(save_path, 0, 2, errors, warnings)
        if ret is None:
            ret = doc.SaveAs3(save_path, 0, 2)
        result["ok"] = True
        result["path"] = save_path
    except Exception as exc:
        result["error"] = f"{exc!r}\n{traceback.format_exc()}"
    return result


def _reopen_saved(sw: Any, save_path: str) -> dict[str, Any]:
    """Close everything then reopen the saved fixture for verify.

    Uses CloseAllDocuments(True) (the only safe teardown — NEVER
    CloseDoc mid-session, which corrupts the COM channel).
    """
    result: dict[str, Any] = {"ok": False}
    try:
        sw.CloseAllDocuments(True)
        doc_type = 1
        reopened = sw.OpenDoc6(save_path, doc_type, 0, "", 0, 0)
        if reopened is None:
            reopened = sw.OpenDoc6(save_path, doc_type, 0, "")
        if reopened is None:
            result["error"] = "OpenDoc6 returned None after CloseAllDocuments"
            return result
        reopened.ForceRebuild3(False)
        result["ok"] = True
        result["doc"] = reopened
    except Exception as exc:
        result["error"] = f"{exc!r}\n{traceback.format_exc()}"
    return result


def _probe_insert_move_copy_body_arity(fm: Any) -> dict[str, Any]:
    """Late-bound probe: check if InsertMoveCopyBody2 exists on FeatureManager."""
    result: dict[str, Any] = {"method_found": False}
    candidates = (
        "InsertMoveCopyBody2",
        "InsertMoveCopyBody",
        "MoveCopyBody2",
        "MoveCopyBody",
    )
    for name in candidates:
        try:
            m = getattr(fm, name, None)
            if m is not None:
                result["method_found"] = True
                result["method_name"] = name
                result["callable"] = callable(m)
                break
        except Exception:
            continue
    return result


def test_move(sw: Any, sig: dict[str, Any]) -> dict[str, Any]:
    """Move test: build box -> call move (dx=5mm) -> centroid delta -> reopen -> re-measure."""
    result: dict[str, Any] = {"kind": "move", "status": "UNKNOWN"}

    build = _build_box(sw)
    if not build.get("built"):
        result["status"] = "BUILD_FAILED"
        result["error"] = build.get("error", "unknown")
        return result

    doc = build["doc"]
    before_centroid = _body_centroid(doc)
    before_bodies = len(_get_bodies(doc))
    result["before"] = {
        "centroid": before_centroid,
        "body_count": before_bodies,
    }

    fm = doc.FeatureManager
    result["api_probe"] = _probe_insert_move_copy_body_arity(fm)

    if not sig.get("method_name"):
        result["status"] = "NO_METHOD"
        result["error"] = "no InsertMoveCopyBody2 method found in typelib"
        return result

    method_name = sig["method_name"]
    method_iface = sig.get("interface", "IFeatureManager")
    api_obj = fm if method_iface == "IFeatureManager" else doc

    try:
        call_result = _call_move_copy(
            api_obj,
            method_name,
            sig,
            dx=MOVE_DELTA_M,
            dy=0.0,
            dz=0.0,
            copy=False,
        )
        result["call_result"] = call_result
    except Exception as exc:
        result["call_error"] = f"{exc!r}\n{traceback.format_exc()}"
        result["status"] = "CALL_FAILED"
        return result

    doc.ForceRebuild3(False)

    after_centroid = _body_centroid(doc)
    result["after"] = {
        "centroid": after_centroid,
        "body_count": len(_get_bodies(doc)),
    }

    if before_centroid and after_centroid:
        dx_actual = after_centroid["x_m"] - before_centroid["x_m"]
        result["centroid_delta_x_m"] = dx_actual
        result["centroid_delta_expected_m"] = MOVE_DELTA_M

    save = _save_fixture(sw, doc)
    if not save.get("ok"):
        result["status"] = "SAVE_FAILED"
        result["save_error"] = save.get("error")
        return result

    sr = _reopen_saved(sw, save["path"])
    result["save_reopen"] = {"ok": sr.get("ok"), "error": sr.get("error")}

    if sr.get("ok") and sr.get("doc"):
        reopened = sr["doc"]
        reopen_centroid = _body_centroid(reopened)
        result["reopen"] = {"centroid": reopen_centroid}
        if before_centroid and reopen_centroid:
            dx_reopen = reopen_centroid["x_m"] - before_centroid["x_m"]
            result["reopen_delta_x_m"] = dx_reopen
            tolerance = MOVE_DELTA_M * 0.1
            if abs(dx_reopen - MOVE_DELTA_M) < tolerance:
                result["status"] = "PASS"
            elif abs(dx_reopen) > tolerance:
                result["status"] = "PARTIAL"
            else:
                result["status"] = "FAIL"
    else:
        result["status"] = "SAVE_REOPEN_FAILED"

    return result


def test_copy(sw: Any, sig: dict[str, Any]) -> dict[str, Any]:
    """Copy test: build box -> call copy (Copy=True, dx=25mm) -> body_count+1 -> reopen."""
    result: dict[str, Any] = {"kind": "copy", "status": "UNKNOWN"}

    build = _build_box(sw)
    if not build.get("built"):
        result["status"] = "BUILD_FAILED"
        result["error"] = build.get("error", "unknown")
        return result

    doc = build["doc"]
    before_bodies = len(_get_bodies(doc))
    before_vol = _total_volume(doc)
    result["before"] = {
        "body_count": before_bodies,
        "volume_mm3": before_vol,
    }

    fm = doc.FeatureManager
    result["api_probe"] = _probe_insert_move_copy_body_arity(fm)

    if not sig.get("method_name"):
        result["status"] = "NO_METHOD"
        result["error"] = "no InsertMoveCopyBody2 method found in typelib"
        return result

    method_name = sig["method_name"]
    method_iface = sig.get("interface", "IFeatureManager")
    api_obj = fm if method_iface == "IFeatureManager" else doc

    try:
        call_result = _call_move_copy(
            api_obj,
            method_name,
            sig,
            dx=COPY_OFFSET_M,
            dy=0.0,
            dz=0.0,
            copy=True,
        )
        result["call_result"] = call_result
    except Exception as exc:
        result["call_error"] = f"{exc!r}\n{traceback.format_exc()}"
        result["status"] = "CALL_FAILED"
        return result

    doc.ForceRebuild3(False)

    after_bodies = len(_get_bodies(doc))
    after_vol = _total_volume(doc)
    result["after"] = {
        "body_count": after_bodies,
        "volume_mm3": after_vol,
    }

    save = _save_fixture(sw, doc)
    if not save.get("ok"):
        result["status"] = "SAVE_FAILED"
        result["save_error"] = save.get("error")
        return result

    sr = _reopen_saved(sw, save["path"])
    result["save_reopen"] = {"ok": sr.get("ok"), "error": sr.get("error")}

    if sr.get("ok") and sr.get("doc"):
        reopened = sr["doc"]
        reopen_bodies = len(_get_bodies(reopened))
        result["reopen"] = {"body_count": reopen_bodies}
        if reopen_bodies > before_bodies:
            result["status"] = "PASS"
        elif after_bodies > before_bodies:
            result["status"] = "PARTIAL"
        else:
            result["status"] = "FAIL"
    else:
        result["status"] = "SAVE_REOPEN_FAILED"

    return result


def _call_move_copy(
    api_obj: Any,
    method_name: str,
    sig: dict[str, Any],
    dx: float,
    dy: float,
    dz: float,
    copy: bool,
) -> dict[str, Any]:
    """Call the discovered move/copy method.

    SEAT-GATED: the actual arg shape comes from the typelib dump.
    This function attempts the most likely signature:

    InsertMoveCopyBody2(Dx, Dy, Dz, Rx, Ry, Rz, Copy, NoOfBodiesToCopyTo)
        Dx/Dy/Dz: translation in meters (VT_R8)
        Rx/Ry/Rz: rotation in radians (VT_R8)
        Copy: VT_BOOL
        NoOfBodiesToCopyTo: VT_I4

    If the typelib dump shows a different arity, the seat runner adjusts
    this function before firing.
    """
    result: dict[str, Any] = {"method": method_name}

    cParams = sig.get("cParams", 0)
    params = sig.get("params", [])

    args: list[Any] = []
    for p in params:
        p_name = p.get("name", "").lower()
        p_type = p.get("type", "")
        if "dx" in p_name or "xtrans" in p_name:
            args.append(dx)
        elif "dy" in p_name or "ytrans" in p_name:
            args.append(dy)
        elif "dz" in p_name or "ztrans" in p_name:
            args.append(dz)
        elif "rx" in p_name or "xrot" in p_name:
            args.append(0.0)
        elif "ry" in p_name or "yrot" in p_name:
            args.append(0.0)
        elif "rz" in p_name or "zrot" in p_name:
            args.append(0.0)
        elif "copy" in p_name or "bcopy" in p_name:
            args.append(copy)
        elif "noof" in p_name or "instance" in p_name or "nbodies" in p_name:
            args.append(0)
        elif "VT_R8" in p_type or "VT_R4" in p_type:
            args.append(0.0)
        elif "VT_BOOL" in p_type:
            args.append(False)
        elif "VT_I4" in p_type or "VT_I2" in p_type or "VT_INT" in p_type:
            args.append(0)
        else:
            args.append(0)

    result["arg_count"] = len(args)
    result["args"] = [
        {"name": p.get("name", f"p{i}"), "value": args[i]}
        for i, p in enumerate(params)
        if i < len(args)
    ]

    method = getattr(api_obj, method_name)
    t0 = time.perf_counter()
    try:
        ret = method(*args)
        elapsed = (time.perf_counter() - t0) * 1000.0
        result["ok"] = True
        result["return"] = str(ret)[:200] if ret is not None else None
        result["return_type"] = type(ret).__name__
        result["elapsed_ms"] = elapsed
    except Exception as exc:
        elapsed = (time.perf_counter() - t0) * 1000.0
        result["ok"] = False
        result["error"] = f"{exc!r}"
        result["hresult"] = f"{exc.hresult:#010x}" if hasattr(exc, "hresult") else None
        result["elapsed_ms"] = elapsed

    return result


def run() -> dict[str, Any]:
    """Main run: TLB dump -> build fixture -> test move -> test copy."""
    output: dict[str, Any] = {
        "spike_id": "W59_move_copy_body",
        "timestamp": time.time(),
        "overall": "UNKNOWN",
    }

    output["tlb_dump"] = _phase1_tlb_dump()

    sig = _extract_best_signature(output["tlb_dump"])
    output["best_signature"] = sig

    try:
        import pythoncom

        pythoncom.CoInitialize()
    except Exception:
        pass

    try:
        from ai_sw_bridge.sw_com import get_sw_app

        sw = get_sw_app()
    except Exception as exc:
        output["error"] = f"could not connect to SW: {exc!r}"
        output["overall"] = "FAIL"
        return output

    try:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass

        try:
            output["sw_revision"] = str(sw.RevisionNumber)
        except Exception:
            output["sw_revision"] = "<unreadable>"

        print("=== W59 move_copy_body spike ===", file=sys.stderr)

        print("\n--- move test ---", file=sys.stderr)
        move_result = test_move(sw, sig)
        output["move"] = move_result
        print(f"  status: {move_result['status']}", file=sys.stderr)

        print("\n--- copy test ---", file=sys.stderr)
        copy_result = test_copy(sw, sig)
        output["copy"] = copy_result
        print(f"  status: {copy_result['status']}", file=sys.stderr)

        statuses = [move_result["status"], copy_result["status"]]
        if all(s == "PASS" for s in statuses):
            output["overall"] = "PASS"
        elif any(s == "PASS" for s in statuses):
            output["overall"] = "PARTIAL"
        else:
            output["overall"] = "FAIL"

        green = sum(1 for s in statuses if s == "PASS")
        output["summary"] = f"{green}/2 PASS"
        print(f"\n=== SUMMARY: {output['summary']} ===", file=sys.stderr)

    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass

    return output


def _phase1_tlb_dump() -> dict[str, Any]:
    """Phase 1: dump InsertMoveCopyBody2-family from sldworks.tlb."""
    report: dict[str, Any] = {
        "tlb_path": SW_TLB_PATH,
        "loadable": False,
    }
    try:
        import pythoncom

        tlb = pythoncom.LoadTypeLib(SW_TLB_PATH)
        report["loadable"] = True
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        return report

    tokens = ("MoveCopyBody", "MoveBody", "CopyBody", "MoveCopy")
    report["token_walk"] = _walk_sldworks_fm_token_walk(tlb, tokens)
    return report


def _extract_best_signature(tlb_dump: dict[str, Any]) -> dict[str, Any]:
    """Pick the best MoveCopyBody method signature from the TLB dump.

    Preference: InsertMoveCopyBody2 on IFeatureManager (FUNCTION invkind).
    Fallback: any MoveCopyBody method found.
    """
    token_walk = tlb_dump.get("token_walk", {})
    ifaces = token_walk.get("interfaces", {})

    best: dict[str, Any] = {}
    fallback: dict[str, Any] = {}

    for iface_name, members in ifaces.items():
        for m in members:
            if "error" in m:
                continue
            mname = m.get("name", "")
            if mname == "InsertMoveCopyBody2" and iface_name == "IFeatureManager":
                best = {**m, "interface": iface_name}
            elif "MoveCopyBody" in mname and not fallback:
                fallback = {**m, "interface": iface_name}

    return best if best else fallback


def emit_vba() -> str:
    return """' Spike W59 move_copy_body VBA oracle.
Option Explicit
Sub ProbeMoveCopyBody()
    Dim swApp As SldWorks.SldWorks
    Dim Part As SldWorks.ModelDoc2
    Dim Fm As SldWorks.FeatureManager
    Set swApp = Application.SldWorks
    Set Part = swApp.ActiveDoc
    Set Fm = Part.FeatureManager
    Part.ClearSelection2 True
    ' InsertMoveCopyBody2 signature from TLB dump — adjust args per dump
    Fm.InsertMoveCopyBody2 0.005, 0#, 0#, 0#, 0#, 0#, False, 0
End Sub
"""


def _scrub(o: Any) -> Any:
    if isinstance(o, dict):
        return {k: _scrub(v) for k, v in o.items() if k not in ("_val", "doc")}
    if isinstance(o, list):
        return [_scrub(v) for v in o]
    return o


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--mode", choices=["com", "vba"], default="com")
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args()

    if args.mode == "vba":
        out = Path(__file__).parent / "spike_move_copy_body.bas"
        out.write_text(emit_vba(), encoding="utf-8")
        print(f"wrote {out}", file=sys.stderr)
        return 0

    result = run()
    payload = json.dumps(
        _scrub(result), indent=2, default=lambda o: f"<{type(o).__name__}>"
    )
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(payload)

    return {"PASS": 0, "PARTIAL": 2, "FAIL": 1}.get(result.get("overall"), 1)


if __name__ == "__main__":
    raise SystemExit(main())
