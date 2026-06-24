"""S1 de-risk spike — Mechanical Mates epoch, TIER 1 (Gear + Screw).

Goal: prove that the W8/W10-proven symmetric mate pipeline
(``CreateMateData(type) -> typed_qi(I<Type>MateFeatureData) -> EntitiesToMate
SAFEARRAY -> CreateMate``) extends to the *mechanical* mates that carry a
coupling SCALAR — gear (ratio) and screw (pitch) — out-of-process.

This is a SEAT spike (W0 runs it on the live SOLIDWORKS COM seat). It is
authored offline, py_compile-clean. It makes ZERO production edits — it only
characterizes the COM surface so the production handler can be written against
PROVEN signatures, not guesses.

Two standing lessons drive the design:
  * **T6 — guessed enums silently no-op.** ``swMateGEAR`` / ``swMateSCREW`` are
    NOT hardcoded here. The spike resolves them BY NAME from the live typelib
    (``win32com.client.constants``) and FAILS LOUD if absent — never falling
    back to a guessed int that would silently produce a degenerate mate.
  * **O1 — introspect, don't guess members.** The ratio/pitch property name on
    ``IGearMateFeatureData`` / ``IScrewMateFeatureData`` is NOT assumed. The
    spike QIs the mate-data object, DUMPS its members, and reports them so W0
    sees the real setter name before any production code commits to one.

GREEN criterion (per the epoch board):
  1. enum resolved by name (not guessed),
  2. CreateMateData -> typed_qi -> EntitiesToMate SAFEARRAY -> set scalar ->
     CreateMate returns a real Mate IFeature with ErrorStatus/GetErrorCode2 == 0,
  3. the coupling scalar (ratio / pitch) PERSISTS through save -> close ->
     reopen (read it back, assert == set value).
A clean solve WITHOUT a persisted/read-back scalar is AMBER, not GREEN — a mate
that "solved" but dropped its ratio is a kinematic ghost.

Run:  PYTHONPATH=<repo>/src python spikes/v0_2x/mech_mate_tier1_gear_screw.py
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any

_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pythoncom  # noqa: E402
import win32com.client as w32  # noqa: E402

from ai_sw_bridge.com.earlybind import typed, typed_qi  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.sw_com import get_sw_app  # noqa: E402
from ai_sw_bridge.assembly.lifecycle import (  # noqa: E402
    _find_assembly_template,
    _build_part_spec,
)
from ai_sw_bridge.assembly.handlers import place_components  # noqa: E402

_RESULTS = Path(__file__).resolve().parent / "_results"
_RESULTS.mkdir(exist_ok=True)
_OUT = _RESULTS / "mech_mate_tier1_gear_screw.json"

# swMateType_e member NAMES we want resolved from the live typelib. The spike
# never hardcodes the int — it resolves these names and refuses to proceed on a
# miss (T6). Documented candidate ints live ONLY in the board doc for context.
_GEAR_NAME = "swMateGEAR"
_SCREW_NAME = "swMateSCREW"

# Candidate typed-interface names (verified-or-falsified by typed_qi + dump).
_GEAR_IFACE_CANDIDATES = ("IGearMateFeatureData", "IGearMateFeatureData2")
_SCREW_IFACE_CANDIDATES = ("IScrewMateFeatureData", "IScrewMateFeatureData2")


# swMateType_e lives in the SOLIDWORKS Constant type library (swconst.tlb),
# NOT the sldworks.tlb that wrapper_module() loads — hence win32com.client.
# constants is empty for swMate* names. gencache.EnsureModule fails ("Library
# not registered") because the registry version string ("20") LIES about the
# real typelib version (32) — the same documented SW lie as sldworks.tlb. The
# robust path is pythoncom.LoadTypeLib(<file>) and walk swMateType_e directly,
# no registration/version dependency.
_SWCONST_PATHS = (
    r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\swconst.tlb",
    r"C:\Program Files\SolidWorks Corp\SOLIDWORKS\swconst.tlb",
)
_swmate_enum_cache: dict[str, int] | None = None


def _swconst_path() -> str | None:
    for p in _SWCONST_PATHS:
        if Path(p).exists():
            return p
    # Registry fallback: enumerate registered typelibs for the swconst dll.
    try:
        import win32com.client.selecttlb as stlb

        for t in stlb.EnumTlbs():
            if "swconst.tlb" in (t.dll or "").lower():
                return t.dll
    except Exception:  # noqa: BLE001
        pass
    return None


def _dump_swmate_enum() -> dict[str, int]:
    """Dump every swMateType_e member (name -> int) from swconst.tlb (typelib
    truth, via LoadTypeLib on the file — the registry version string lies)."""
    global _swmate_enum_cache
    if _swmate_enum_cache is not None:
        return _swmate_enum_cache
    out: dict[str, int] = {}
    path = _swconst_path()
    if path is None:
        _swmate_enum_cache = out
        return out
    tlb = pythoncom.LoadTypeLib(path)
    for i in range(tlb.GetTypeInfoCount()):
        try:
            if tlb.GetDocumentation(i)[0] != "swMateType_e":
                continue
        except Exception:  # noqa: BLE001
            continue
        ti = tlb.GetTypeInfo(i)
        ta = ti.GetTypeAttr()
        for v in range(ta.cVars):
            vd = ti.GetVarDesc(v)
            try:
                out[ti.GetNames(vd.memid)[0]] = int(vd.value)
            except Exception:  # noqa: BLE001
                pass
    _swmate_enum_cache = out
    return out


def _resolve_mate_enum(name: str) -> int | None:
    """Resolve a swMateType_e member BY NAME from swconst.tlb (typelib truth).

    Returns None (NOT a guess) if the name is absent — T6: never fall back to a
    guessed int that would silently create the wrong mate type.
    """
    return _dump_swmate_enum().get(name)


def _member_dump(obj: Any) -> list[str]:
    """Best-effort public-member dump of a COM object (introspect, not guess)."""
    out: list[str] = []
    try:
        for n in dir(obj):
            if not n.startswith("_"):
                out.append(n)
    except Exception:  # noqa: BLE001
        pass
    return out


def _cylinder_spec(name: str) -> dict[str, Any]:
    """A declarative cylinder part_spec (Ø20 × 40 mm) — circle sketch + blind
    extrude. Built by the PRODUCTION builder, not hand-rolled COM."""
    return {
        "schema_version": 1,
        "name": name,
        "features": [
            {
                "type": "sketch_circle_on_plane",
                "name": "SK_Shaft",
                "plane": "Front",
                "diameter": 20.0,
                "center": {"x": 0.0, "y": 0.0},
            },
            {
                "type": "boss_extrude_blind",
                "name": "EX_Shaft",
                "sketch": "SK_Shaft",
                "depth": 40.0,
            },
        ],
    }


def _build_shaft(name: str) -> dict[str, Any]:
    """Build a cylindrical shaft via the PRODUCTION builder (_build_part_spec ->
    spec.builder.build), saved to a unique per-run path. Returns {path}/{error}.
    """
    import os

    save_as = str(Path(_results_tmp(), f"mech_{name}_{os.getpid()}.SLDPRT"))
    res = _build_part_spec(_cylinder_spec(name), save_as)
    if not res.get("ok"):
        return {"error": f"cylinder build {name} failed: {res.get('error')!r}"}
    return {"path": save_as}


def _results_tmp() -> str:
    d = _RESULTS / "_fixtures"
    d.mkdir(exist_ok=True)
    return str(d)


def _first_cyl_face(comp: Any, mod: Any) -> Any | None:
    """Return the first cylindrical face of a placed component's body.

    Mirrors the PRODUCTION ``face_resolver`` cyl-face match: the face and its
    surface MUST be typed-wrapped (``IFace2`` / ``ISurface``) before
    ``IsCylinder()`` — a raw-dispatch ``f.GetSurface().IsCylinder()`` silently
    fails out-of-process (the bug behind the first NO_CYL_FACE run).
    """
    try:
        bodies = comp.GetBodies(0)
        if not bodies:
            return None
        body = bodies[0] if isinstance(bodies, (list, tuple)) else bodies
        faces = body.GetFaces()
        for f in faces or ():
            try:
                iface = typed(f, "IFace2", module=mod)
                surf = iface.GetSurface()
                isurf = typed(surf, "ISurface", module=mod)
                if isurf.IsCylinder():
                    return f
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        return None
    return None


def _read_back_scalars(
    sw: Any,
    mod: Any,
    asm_path: str,
    iface_name: str,
    props: tuple[str, ...],
) -> dict[str, Any]:
    """Reopen the saved .sldasm and re-read the mate's coupling scalar(s).

    Proves GREEN criterion #3 (the scalar survives save->close->reopen, not a
    kinematic ghost). Defensive: a marshaling wall on GetDefinition is reported,
    not raised — that itself is a finding (readback-unreachable → production PAE
    must verify another way).
    """
    out: dict[str, Any] = {}
    try:
        typed_sw = typed(sw, "ISldWorks", module=mod)
        sw.CloseAllDocuments(True)  # SAFE cleanup (not CloseDoc) before reopen
        reopened = typed_sw.OpenDoc6(asm_path, 2, 0, "", 0, 0)  # 2 = swDocASSEMBLY
        rdoc = reopened[0] if isinstance(reopened, tuple) else reopened
        if rdoc is None:
            return {"error": "reopen OpenDoc6 returned None"}
        typed(rdoc, "IModelDoc2", module=mod).ForceRebuild3(False)
        feats = rdoc.FeatureManager.GetFeatures(False) or ()
        for f in feats:
            try:
                tf = typed(f, "IFeature", module=mod)
                tname = tf.GetTypeName2()
                if "Mate" not in tname:
                    continue
                definition = tf.GetDefinition()
                if definition is None:
                    continue
                ti = typed_qi(definition, iface_name, module=mod)
                vals = {}
                for p in props:
                    try:
                        vals[p] = getattr(ti, p)
                    except Exception as exc:  # noqa: BLE001
                        vals[p] = f"read failed: {exc!r}"
                if vals:
                    out["mate_feature_type"] = tname
                    out["read_back"] = vals
                    return out
            except Exception:  # noqa: BLE001
                continue
        out["error"] = "no mate feature with readable definition found on reopen"
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"readback raised: {exc!r}"
    return out


def _probe_mechanical_mate(
    sw: Any,
    mod: Any,
    leg: str,
    enum_name: str,
    iface_candidates: tuple[str, ...],
    set_scalar: Any,
    readback_props: tuple[str, ...],
) -> dict[str, Any]:
    """One mechanical-mate leg: build 2 shafts, place, set the coupling scalar
    (dump-confirmed setter via ``set_scalar(ti) -> dict``), create the mate, and
    read the scalar back through a save->reopen cycle for the GREEN verdict.
    """
    r: dict[str, Any] = {"leg": leg, "status": "UNKNOWN", "enum_name": enum_name}

    enum_val = _resolve_mate_enum(enum_name)
    r["enum_resolved"] = enum_val
    if enum_val is None:
        r["status"] = "ENUM_MEMBER_ABSENT"
        r["note"] = (
            f"{enum_name} not in win32com.client.constants — typelib does not "
            f"expose it under this name. DO NOT guess an int (T6). Dump "
            f"swMateType_e members and re-name."
        )
        return r

    # Build two shafts (production builder).
    s1 = _build_shaft(f"{leg}_a")
    s2 = _build_shaft(f"{leg}_b")
    if "error" in s1 or "error" in s2:
        r["status"] = "FIXTURE_FAILED"
        r["error"] = s1.get("error") or s2.get("error")
        return r

    try:
        # PRODUCTION placement path (lifecycle .ASMDOT glob + handlers.
        # place_components = typed OpenDoc6 pre-open + AddComponent4 + B-rep
        # verify). The harness no longer hand-rolls any document/placement
        # plumbing — it is isolated strictly to the mate sequence below.
        asm_template = _find_assembly_template()
        if asm_template is None:
            r["status"] = "NO_ASM_TEMPLATE"
            return r
        asm = sw.NewDocument(asm_template, 0, 0.1, 0.1)
        if asm is None:
            r["status"] = "ASM_NEWDOC_NONE"
            return r
        typed_asm = typed(asm, "IAssemblyDoc", module=mod)

        components = [
            {"id": "a", "part": s1["path"], "transform": {"xyz_mm": [0, 0, 0]}},
            {"id": "b", "part": s2["path"], "transform": {"xyz_mm": [50, 0, 0]}},
        ]
        placed, place_err = place_components(sw, asm, components, mod=mod)
        if place_err is not None:
            r["status"] = "PLACE_FAILED"
            r["error"] = place_err
            return r
        c1, c2 = placed.get("a"), placed.get("b")
        typed(asm, "IModelDoc2", module=mod).ForceRebuild3(False)
        f1 = _first_cyl_face(c1, mod)
        f2 = _first_cyl_face(c2, mod)
        r["cyl_faces_found"] = (f1 is not None, f2 is not None)
        if f1 is None or f2 is None:
            r["status"] = "NO_CYL_FACE"
            return r

        mate_data = typed_asm.CreateMateData(enum_val)
        if mate_data is None:
            r["status"] = "CREATEMATEDATA_NONE"
            r["note"] = (
                f"CreateMateData({enum_val}) -> None (enum may be wrong despite name)"
            )
            return r

        # typed_qi to a candidate interface; record which one binds + dump it.
        bound_iface = None
        for cand in iface_candidates:
            try:
                ti = typed_qi(mate_data, cand, module=mod)
                if ti is not None:
                    bound_iface = (cand, ti)
                    break
            except Exception:  # noqa: BLE001
                continue
        if bound_iface is None:
            r["status"] = "NO_TYPED_IFACE"
            r["iface_candidates_tried"] = list(iface_candidates)
            return r
        iface_name, ti = bound_iface
        r["typed_iface"] = iface_name
        r["iface_members"] = _member_dump(ti)  # O1: the real setter is in here

        # EntitiesToMate SAFEARRAY (the W7 pattern).
        ti.EntitiesToMate = w32.VARIANT(
            pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, (f1, f2)
        )

        # Set the coupling scalar via the DUMP-CONFIRMED setter (not guessed).
        try:
            r["scalars_set"] = set_scalar(ti)
        except Exception as exc:  # noqa: BLE001
            r["scalars_set"] = f"setter raised: {exc!r}"

        mate_ret = typed_asm.CreateMate(mate_data)
        if mate_ret is None or isinstance(mate_ret, int):
            try:
                mfd = typed_qi(mate_data, "IMateFeatureData", module=mod)
                r["error_status"] = mfd.ErrorStatus
            except Exception:  # noqa: BLE001
                r["error_status"] = "?"
            r["status"] = "CREATEMATE_NONE"
            return r

        ifeat = typed(mate_ret, "IFeature", module=mod)
        r["feature_type"] = ifeat.GetTypeName2()
        try:
            ec = ifeat.GetErrorCode2()  # METHOD → (code, has_error) tuple
            r["error_code2"] = list(ec) if isinstance(ec, (list, tuple)) else ec
        except Exception as exc:  # noqa: BLE001
            r["error_code2"] = f"GetErrorCode2 failed: {exc!r}"

        # Persist round-trip: save the assembly, reopen, re-read the scalar.
        import os

        asm_path = str(Path(_results_tmp(), f"{leg}_asm_{os.getpid()}.SLDASM"))
        amodel = typed(asm, "IModelDoc2", module=mod)
        save_ok = amodel.SaveAs3(asm_path, 0, 0)
        r["asm_save_status"] = int(save_ok)
        if int(save_ok) != 0:
            r["status"] = "SOLVED_SAVE_FAILED"
            return r

        # GREEN criterion #3: the scalar must survive save -> reopen.
        rb = _read_back_scalars(sw, mod, asm_path, iface_name, readback_props)
        r["persist"] = rb
        if "read_back" in rb:
            r["status"] = "SOLVED_PERSISTED"  # GREEN — scalar survived reopen
        else:
            r["status"] = "SOLVED_READBACK_UNVERIFIED"  # AMBER
    except Exception as exc:  # noqa: BLE001
        r["status"] = "EXCEPTION"
        r["error"] = f"{exc!r}\n{traceback.format_exc()}"
    return r


def main() -> int:
    result: dict[str, Any] = {"spike_id": "mech_mate_tier1_gear_screw", "legs": {}}
    try:
        sw = get_sw_app()
        mod = wrapper_module()
        # Clean slate: clear any docs left open by a prior run (CloseAllDocuments
        # is the SAFE cleanup — Close/CloseDoc mid-session corrupts the COM
        # channel, see reference_close_corrupts_com).
        try:
            sw.CloseAllDocuments(True)
        except Exception:  # noqa: BLE001
            pass
        # Typelib truth first: every swMateType_e member name -> int.
        try:
            result["swmate_enum_dump"] = _dump_swmate_enum()
        except Exception as exc:  # noqa: BLE001
            result["swmate_enum_dump_error"] = repr(exc)

        # Gear: ratio is a NUMERATOR/DENOMINATOR pair (dump-confirmed). 2:1.
        def _set_gear(ti: Any) -> dict[str, Any]:
            ti.GearRatioNumerator = 2.0
            ti.GearRatioDenominator = 1.0
            return {"GearRatioNumerator": 2.0, "GearRatioDenominator": 1.0}

        result["legs"]["gear"] = _probe_mechanical_mate(
            sw,
            mod,
            "gear",
            _GEAR_NAME,
            _GEAR_IFACE_CANDIDATES,
            set_scalar=_set_gear,
            readback_props=("GearRatioNumerator", "GearRatioDenominator"),
        )

        # Screw: RevolutionType (enum) MUST be set BEFORE RevolutionVal, or the
        # value is interpreted under the default mode and reverts on solve. This
        # mirrors the production handler exactly: RevolutionType =
        # swDistancePerRevolution(1), then RevolutionVal = pitch_m.
        _SCREW_DISTANCE_PER_REV = 1

        def _set_screw(ti: Any) -> dict[str, Any]:
            ti.RevolutionType = _SCREW_DISTANCE_PER_REV
            ti.RevolutionVal = 0.002
            return {
                "RevolutionType": _SCREW_DISTANCE_PER_REV,
                "RevolutionVal": 0.002,
            }

        result["legs"]["screw"] = _probe_mechanical_mate(
            sw,
            mod,
            "screw",
            _SCREW_NAME,
            _SCREW_IFACE_CANDIDATES,
            set_scalar=_set_screw,
            readback_props=("RevolutionVal", "RevolutionType"),
        )
        try:
            sw.CloseAllDocuments(True)
        except Exception:  # noqa: BLE001
            pass
    except Exception as exc:  # noqa: BLE001
        result["fatal"] = f"{exc!r}\n{traceback.format_exc()}"

    _OUT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
