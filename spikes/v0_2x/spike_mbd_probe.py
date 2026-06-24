"""W72 MBD / DimXpert STRUCTURAL VANGUARD PROBE (throwaway, classification only).

NOT a handler. Answers the deepest structural prerequisites before any lane is
scoped, against the live seat:

  Q1  Does Extension.DimXpertManager[CreateSchema] return a valid pointer
      out-of-process, or wall (E_NOINTERFACE / None)?
  Q2  Does IDimXpertManager.DimXpertPart -> IDimXpertPart resolve OOP?
  Q3  Auto-recognition: does DimXpert see the cube's B-rep faces as DimXpert
      features WITHOUT a GUI (GetFeatureCount baseline)?
  Q4  Boundary-law test: does AutoDimensionScheme MATERIALIZE annotations OOP
      (kernel must traverse/solve the B-rep to recognize features -> predicted
      WALL risk), or ghost (ret True but zero delta)?
  Q5  Selection model: does a manual InsertSizeDimension act on a standard
      IFace2 selection (IEntity.Select2), or require IDimXpertFeature?
  Q6  Persistence: do schema features/annotations survive save -> close ->
      reopen (DimXpert schema in the 3D-annotation store)?

swDimXpertAutoDimSchemePartType_e: Prismatic=0 Turned=1
Prereq: SOLIDWORKS 2024 running.  Telemetry -> _results/mbd_probe.json (untracked).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_SRC = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_SRC))

RESULTS_PATH = (
    Path(__file__).resolve().parents[2]
    / "spikes"
    / "v0_2x"
    / "_results"
    / "mbd_probe.json"
)
results: dict[str, Any] = {
    "probe": "w72_mbd_dimxpert",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "gates": {},
    "telemetry": {},
}


def gate(name: str, ok: bool, detail: str = "") -> bool:
    results["gates"][name] = {"ok": bool(ok), "detail": str(detail)}
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return bool(ok)


def note(key: str, value: Any) -> None:
    results["telemetry"][key] = value
    print(f"   . {key} = {value!r}")


def _build_cube(path: str) -> bool:
    from ai_sw_bridge.spec.builder import build as part_build

    spec = {
        "schema_version": 1,
        "name": "W72_MBDCube",
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK",
                "plane": "Front",
                "width": 10.0,
                "height": 10.0,
            },
            {"type": "boss_extrude_blind", "name": "EX", "sketch": "SK", "depth": 10.0},
        ],
    }
    r = part_build(spec, save_as=path, save_format="current", no_dim=True)
    ok = getattr(r, "ok", None)
    if ok is None and isinstance(r, dict):
        ok = r.get("ok")
    return bool(ok) and os.path.isfile(path)


def _call(obj: Any, attr: str, *args: Any) -> Any:
    """Resolve attr; call ONLY if it is a Python routine (makepy bound method).
    A COM dispatch property value (CDispatch) is itself callable but must NOT
    be invoked — that was the 'Member not found' footgun on .DimXpertPart."""
    import inspect

    v = getattr(obj, attr)
    if inspect.isroutine(v):
        return v(*args)
    return v


# --- gen-free invokers for the swdimxpert tlb objects (NOT in makepy gen) ---
# IDimXpertPart & every IDimXpert* sub-object live in swdimxpert.tlb, which is
# deliberately NOT makepy-gen'd (protected SldWorks 32.0 gen stays untouched).
# GetTypeInfoCount==0 on these dispatches but GetIDsOfNames works, so drive them
# by runtime dispid with a FORCED DISPATCH_METHOD invkind (sidesteps the
# property/method auto-invoke ambiguity that yields spurious 'Member not found').
def _m(disp: Any, name: str, ret_vt: int = 24, arg_vts: tuple = (), *args: Any) -> Any:
    import pythoncom

    ole = disp._oleobj_ if hasattr(disp, "_oleobj_") else disp
    return ole.InvokeTypes(
        ole.GetIDsOfNames(name),
        0,
        pythoncom.DISPATCH_METHOD,
        (ret_vt, 0),
        arg_vts,
        *args,
    )


def _putp(disp: Any, name: str, val: Any) -> None:
    import pythoncom

    ole = disp._oleobj_ if hasattr(disp, "_oleobj_") else disp
    ole.Invoke(ole.GetIDsOfNames(name), 0, pythoncom.DISPATCH_PROPERTYPUT, 0, val)


def run() -> str:
    import win32com.client as w32

    from ai_sw_bridge.com.earlybind import typed, typed_qi
    from ai_sw_bridge.com.sw_type_info import wrapper_module

    mod = wrapper_module()
    sw = w32.Dispatch("SldWorks.Application")
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass
    tmp = tempfile.mkdtemp(prefix="w72_mbd_")
    cube = os.path.join(tmp, "W72_MBDCube.SLDPRT")

    if not gate("build_cube", _build_cube(cube), cube):
        return "WALL"

    # reopen the cube by path (self-contained file op)
    tsw = typed(sw, "ISldWorks", module=mod)
    ret = tsw.OpenDoc6(cube, 1, 1, "", 0, 0)
    doc = ret[0] if isinstance(ret, tuple) else ret
    if not gate("reopen_cube", doc is not None, "OpenDoc6"):
        return "WALL"

    mdoc2 = typed(doc, "IModelDoc2", module=mod)

    # ---- Q1: DimXpertManager pointer (E_NOINTERFACE risk) ----
    mgr_raw = None
    try:
        ext = mdoc2.Extension
        # makepy resolves DimXpertManager to the 2-arg overload
        # (Configuration, CreateSchema); single-bool lands in the string slot
        # -> Type mismatch. Pass config="" + CreateSchema=True.
        try:
            mgr_raw = ext.DimXpertManager("", True)
        except Exception:
            try:
                mgr_raw = ext.DimXpertManager(True)
            except Exception:
                mgr_raw = ext.DimXpertManager
    except Exception as exc:
        gate("Q1_manager_pointer", False, f"{type(exc).__name__}: {exc}")
        return "WALL"
    if not gate(
        "Q1_manager_pointer", mgr_raw is not None, f"DimXpertManager(True)={mgr_raw!r}"
    ):
        return "WALL"

    # ---- Q2: DimXpertPart ----
    # IDimXpertManager is in the main SldWorks tlb (typed); but IDimXpertPart
    # and every IDimXpert* sub-object live in the SEPARATE swdimxpert tlb which
    # is NOT makepy-gen'd -> they arrive as late-bound CDispatch. Call their
    # named methods late-bound directly (GetIDsOfNames), do NOT typed_qi them.
    part = None
    schema_name = None
    try:
        mgr = mgr_raw  # already a typed IDimXpertManager from the accessor
        try:
            schema_name = mgr.SchemaName
            note("schema_name", schema_name)
        except Exception as exc:
            note("schema_name_err", f"{type(exc).__name__}: {exc}")
        part = mgr.DimXpertPart  # late-bound CDispatch <COMObject DimXpertPart>
    except Exception as exc:
        gate("Q2_dimxpert_part", False, f"{type(exc).__name__}: {exc}")
        return "PARTIAL"
    if not gate("Q2_dimxpert_part", part is not None, f"DimXpertPart={part!r}"):
        return "PARTIAL"

    def _fc() -> int:
        try:
            return int(_m(part, "GetFeatureCount", 3))  # VT_I4
        except Exception:
            return -1

    def _ac() -> int:
        try:
            return int(_m(part, "GetAnnotationCount", 3))  # VT_I4
        except Exception:
            return -1

    # ---- Q3: auto-recognition baseline (no GUI) ----
    feat_before, anno_before = _fc(), _ac()
    note("feature_count_initial", feat_before)
    note("annotation_count_initial", anno_before)
    gate(
        "Q3_auto_recognition_readable",
        feat_before >= 0 and anno_before >= 0,
        f"features={feat_before} annotations={anno_before}",
    )

    # ---- Q4: AutoDimensionScheme (boundary-law materialize test) ----
    auto_ret = None
    try:
        opt = _m(part, "GetAutoDimSchemeOption", 9)  # VT_DISPATCH
        try:
            _putp(opt, "FeatureFilters", 0xFFFF)  # recognize ALL feature types
            _putp(opt, "ScopeAllFeature", True)
            _putp(opt, "PartType", 0)  # Prismatic
            _putp(opt, "ToleranceType", 0)  # PlusMinus
        except Exception as exc:
            note("autodim_option_set_err", f"{type(exc).__name__}: {exc}")
        # ret VT_BOOL(11), one VT_DISPATCH(9) arg
        auto_ret = _m(part, "AutoDimensionScheme", 11, ((9, 0),), opt)
    except Exception as exc:
        note("autodim_err", f"{type(exc).__name__}: {exc}")
    try:
        mdoc2.EditRebuild3()
    except Exception:
        pass
    feat_after_auto, anno_after_auto = _fc(), _ac()
    note("autodim_ret", auto_ret)
    note("feature_count_after_auto", feat_after_auto)
    note("annotation_count_after_auto", anno_after_auto)
    auto_materialized = (feat_after_auto > feat_before) or (
        anno_after_auto > anno_before
    )
    gate(
        "Q4_autodim_materializes",
        auto_materialized,
        f"ret={auto_ret} dFeat={feat_after_auto - feat_before} "
        f"dAnno={anno_after_auto - anno_before} "
        f"({'MATERIALIZE' if auto_materialized else 'GHOST/ret-only'})",
    )

    # ---- Q5: selection model — IFace2 via IEntity.Select2 ----
    size_ret = None
    sel_ok = False
    try:
        pdoc = typed_qi(doc, "IPartDoc", module=mod)
        bodies = _call(pdoc, "GetBodies2", 0, True)  # swSolidBody=0, visible only
        body = None
        if isinstance(bodies, (list, tuple)) and bodies:
            body = bodies[0]
        elif bodies is not None:
            body = bodies
        faces = None
        if body is not None:
            tbody = typed_qi(body, "IBody2", module=mod)
            faces = _call(tbody, "GetFaces")
        face = None
        if isinstance(faces, (list, tuple)) and faces:
            face = faces[0]
        elif faces is not None:
            face = faces
        if face is not None:
            try:
                ent = typed_qi(face, "IEntity", module=mod)
                sel_ok = bool(ent.Select2(False, 0))
            except Exception as exc:
                note("face_select_err", f"{type(exc).__name__}: {exc}")
        note("face_selected", sel_ok)
    except Exception as exc:
        note("selection_setup_err", f"{type(exc).__name__}: {exc}")
    anno_before_size = _ac()
    try:
        dopt = _m(part, "GetDimOption", 9)  # VT_DISPATCH
        size_ret = _m(part, "InsertSizeDimension", 11, ((9, 0),), dopt)
    except Exception as exc:
        note("size_dim_err", f"{type(exc).__name__}: {exc}")
    try:
        mdoc2.EditRebuild3()
    except Exception:
        pass
    anno_after_size = _ac()
    note("size_ret", size_ret)
    note("annotation_count_after_size", anno_after_size)
    size_materialized = anno_after_size > anno_before_size
    gate(
        "Q5_size_dim_from_iface2_selection",
        sel_ok and size_materialized,
        f"face_sel={sel_ok} ret={size_ret} "
        f"dAnno={anno_after_size - anno_before_size}",
    )

    # ---- Q6: persistence on save -> close -> reopen ----
    feat_live, anno_live = _fc(), _ac()
    note("feature_count_presave", feat_live)
    note("annotation_count_presave", anno_live)
    try:
        mdoc2.SaveAs3(cube, 0, 0)
    except Exception as exc:
        note("save_err", f"{type(exc).__name__}: {exc}")
    try:
        t = mdoc2.GetTitle
        t = t() if callable(t) else t
        sw.CloseDoc(t)
    except Exception:
        pass
    feat_reopen, anno_reopen = -1, -1
    try:
        ret2 = tsw.OpenDoc6(cube, 1, 1, "", 0, 0)
        doc2 = ret2[0] if isinstance(ret2, tuple) else ret2
        if doc2 is not None:
            ext2 = typed(doc2, "IModelDoc2", module=mod).Extension
            try:
                mgr2_raw = ext2.DimXpertManager("", False)
            except Exception:
                try:
                    mgr2_raw = ext2.DimXpertManager(False)
                except Exception:
                    mgr2_raw = ext2.DimXpertManager
            if mgr2_raw is not None:
                p2 = mgr2_raw.DimXpertPart  # late-bound CDispatch
                if p2 is not None:
                    try:
                        feat_reopen = int(_m(p2, "GetFeatureCount", 3))
                    except Exception:
                        pass
                    try:
                        anno_reopen = int(_m(p2, "GetAnnotationCount", 3))
                    except Exception:
                        pass
    except Exception as exc:
        note("reopen_err", f"{type(exc).__name__}: {exc}")
    note("feature_count_reopen", feat_reopen)
    note("annotation_count_reopen", anno_reopen)
    persisted = (feat_reopen >= feat_live and feat_live > feat_before) or (
        anno_reopen >= anno_live and anno_live > anno_before
    )
    gate(
        "Q6_persists_on_reopen",
        persisted,
        f"feat live={feat_live}->reopen={feat_reopen} "
        f"anno live={anno_live}->reopen={anno_reopen}",
    )

    # ---- verdict ----
    accessible = (
        results["gates"]["Q1_manager_pointer"]["ok"]
        and results["gates"]["Q2_dimxpert_part"]["ok"]
    )
    can_write = auto_materialized or size_materialized
    if accessible and can_write and persisted:
        return "GREEN"
    if accessible and can_write:
        return "WRITES_NO_PERSIST"
    if accessible:
        return "READABLE_WALL_ON_WRITE"
    return "WALL"


def main() -> int:
    import pythoncom

    pythoncom.CoInitialize()
    try:
        verdict = run()
    except Exception as exc:
        import traceback

        results["gates"]["UNEXPECTED"] = {
            "ok": False,
            "detail": f"{type(exc).__name__}: {exc}",
        }
        results["telemetry"]["traceback"] = traceback.format_exc()
        verdict = "WALL"
    finally:
        try:
            import win32com.client as w32

            w32.Dispatch("SldWorks.Application").CloseAllDocuments(True)
        except Exception:
            pass
        pythoncom.CoUninitialize()
    results["verdict"] = verdict
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(
        json.dumps(results, indent=2, default=str), encoding="utf-8"
    )
    print(f"\nVerdict: {verdict}  (wrote {RESULTS_PATH})")
    return 0 if verdict in ("GREEN", "WRITES_NO_PERSIST") else 1


if __name__ == "__main__":
    raise SystemExit(main())
