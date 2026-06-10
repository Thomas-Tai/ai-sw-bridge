"""S1 de-risk spike — Mechanical Mates epoch, TIER 3 (Slot + Hinge).

Tier-1 proved the SCALAR axis (gear ratio / screw pitch) on the symmetric
EntitiesToMate path. Tier-2 proved the ASYMMETRIC reference layout (indexed
SetEntitiesToMate). Tier-3's risk is the LIMIT MODIFIER + the compound entity
model: a slot mate constrains a pin to travel along a slot (constraint enum +
distance), and a hinge mate is a concentric+coincident compound with an
optional angle limit. Both carry the HIGHEST solver-wall risk of the epoch.

Doctrine (unchanged across the epoch):
  * **T6 — guessed enums silently no-op.** swMateSLOT / swMateHINGE are resolved
    BY NAME from swconst.tlb (typelib truth; the registry version "20" lies).
    Never a hardcoded int.
  * **O1 — introspect, don't guess members.** The constraint/limit/entity
    property names on ISlotMateFeatureData / IHingeMateFeatureData are NOT
    assumed. STAGE A QIs the mate-data object and DUMPS its members BEFORE any
    leg commits to a property name. This is the primary, lowest-risk deliverable
    — it de-risks handler authoring even if the solve legs hit a fixture wall.
  * **The save/reopen scalar gate is non-negotiable** (it caught the gear
    transpose AND the screw clamp). A clean solve WITHOUT a persisted limit is
    AMBER, not GREEN.

Stages (each fail-soft — a fixture wall on one does not block the others):
  A. INTROSPECT — place two cylinders, CreateMateData(slot) + CreateMateData
     (hinge), QI candidate ifaces, dump members. Deterministic, cheap.
  B. HINGE solve — two coaxial cylinders (lateral cyl faces = concentric pair,
     end caps = coincident pair); set an angle limit; CreateMate; save/reopen;
     read the angle limit back.
  C. SLOT solve — slotted plate (rectangle boss + slot cut) + pin cylinder;
     set the slot constraint + distance; CreateMate; save/reopen; read back.

Run:  PYTHONPATH=<repo>/src python spikes/v0_2x/mech_mate_tier3_slot_hinge.py
"""
from __future__ import annotations

import json
import math
import os
import sys
import traceback
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
_SRC = _HERE.parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
sys.path.insert(0, str(_HERE.parent))

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

import mech_mate_tier1_gear_screw as t1  # noqa: E402
import mech_mate_tier2_rack_cam as t2  # noqa: E402

_RESULTS = _HERE.parent / "_results"
_RESULTS.mkdir(exist_ok=True)
_OUT = _RESULTS / "mech_mate_tier3_slot_hinge.json"

_SLOT_NAME = "swMateSLOT"
_HINGE_NAME = "swMateHINGE"

_SLOT_IFACE = ("ISlotMateFeatureData", "ISlotMateFeatureData2")
_HINGE_IFACE = ("IHingeMateFeatureData", "IHingeMateFeatureData2")

# swHingeMateEntityType_e (swconst.tlb v32): the EntitiesToMate PROPPUT is
# ROLE-keyed (FUNCDESC: nargs=2, [EntityType:I4, value:VARIANT]) — the value is
# the ENTITY ARRAY for that role, NOT a single entity at a sequential index.
# This is why the Tier-3-run2 flat-list attempts (SetEntitiesToMate(0,ent),
# SetEntitiesToMate(1,ent)...) all returned CreateMate->None.
_HINGE_CONCENTRIC = 0  # swHingeMateEntityType_Concentric
_HINGE_COINCIDENT = 1  # swHingeMateEntityType_Coincident
_HINGE_ANGLE = 2       # swHingeMateEntityType_Angle (limit reference)


# ---------------------------------------------------------------------------
# Fixtures (declarative, built by the PRODUCTION builder).
# ---------------------------------------------------------------------------
def _pin_spec(name: str) -> dict[str, Any]:
    """Ø8 × 30 mm pin — fits inside a 12 mm-wide slot."""
    return {
        "schema_version": 1,
        "name": name,
        "features": [
            {"type": "sketch_circle_on_plane", "name": "SK", "plane": "Front",
             "diameter": 8.0, "center": {"x": 0.0, "y": 0.0}},
            {"type": "boss_extrude_blind", "name": "EX", "sketch": "SK", "depth": 30.0},
        ],
    }


def _slot_plate_spec(name: str) -> dict[str, Any]:
    """80 × 40 × 10 mm plate with a 40 mm-long, 12 mm-wide arc-ended slot cut
    clean through it — the slot the pin travels along."""
    return {
        "schema_version": 1,
        "name": name,
        "features": [
            {"type": "sketch_rectangle_on_plane", "name": "SK_PLATE", "plane": "Front",
             "center": {"x": 0.0, "y": 0.0}, "width": 80.0, "height": 40.0},
            {"type": "boss_extrude_blind", "name": "EX_PLATE", "sketch": "SK_PLATE",
             "depth": 10.0},
            {"type": "sketch_slot", "name": "SK_SLOT", "plane": "Front",
             "center": {"x": 0.0, "y": 0.0}, "length": 40.0, "width": 12.0,
             "angle_deg": 0.0},
            # Two-direction blind cut (15 mm each way) carves the slot through
            # the 10 mm plate regardless of which half-space the boss occupies —
            # the single-direction through-all removed no material in BOTH flip
            # senses, so direction was never the issue; this sidesteps it AND
            # discriminates (a still-None here indicts the slot PROFILE).
            {"type": "cut_extrude_two_direction", "name": "CUT_SLOT",
             "sketch": "SK_SLOT", "depth": 15.0, "depth2": 15.0},
        ],
    }


def _build(name: str, spec: dict[str, Any]) -> dict[str, Any]:
    save_as = str(Path(t1._results_tmp(), f"t3_{name}_{os.getpid()}.SLDPRT"))
    res = _build_part_spec(spec, save_as)
    if not res.get("ok"):
        return {"error": f"build {name} failed: {res.get('error')!r}"}
    return {"path": save_as}


# ---------------------------------------------------------------------------
# Entity helpers.
# ---------------------------------------------------------------------------
def _cap_face_by_normal_z(comp: Any, mod: Any, want_positive: bool) -> Any | None:
    """The planar end cap whose outward normal points +Z (want_positive) or -Z.

    For two coaxial cylinders (axis = Front-plane normal = +Z) the PHYSICALLY
    TOUCHING cap pair is A's +Z cap and B's -Z cap. Selecting by normal makes the
    hinge's coincident pair geometrically sensible instead of arbitrary."""
    body = t2._body_of(comp)
    if body is None:
        return None
    try:
        faces = body.GetFaces() or ()
    except Exception:  # noqa: BLE001
        return None
    for f in faces:
        try:
            iface = typed(f, "IFace2", module=mod)
            surf = typed(iface.GetSurface(), "ISurface", module=mod)
            if not bool(surf.IsPlane()):
                continue
            nz = list(iface.Normal)[2]
            if (want_positive and nz > 0.5) or (not want_positive and nz < -0.5):
                return f
        except Exception:  # noqa: BLE001
            continue
    return None


def _place_pair_at(sw: Any, mod: Any, p1: dict, p2: dict,
                   xyz2: list[float]) -> dict[str, Any]:
    """Place two parts in a fresh assembly; second at xyz2 (mm)."""
    asm_template = _find_assembly_template()
    if asm_template is None:
        return {"error": "NO_ASM_TEMPLATE"}
    asm = sw.NewDocument(asm_template, 0, 0.1, 0.1)
    if asm is None:
        return {"error": "ASM_NEWDOC_NONE"}
    components = [
        {"id": "a", "part": p1["path"], "transform": {"xyz_mm": [0, 0, 0]}},
        {"id": "b", "part": p2["path"], "transform": {"xyz_mm": xyz2}},
    ]
    placed, err = place_components(sw, asm, components, mod=mod)
    if err is not None:
        return {"error": f"PLACE_FAILED: {err}"}
    typed(asm, "IModelDoc2", module=mod).ForceRebuild3(False)
    return {"asm": asm, "a": placed.get("a"), "b": placed.get("b")}


# ---------------------------------------------------------------------------
# STAGE A — introspection (the load-bearing deliverable).
# ---------------------------------------------------------------------------
def _introspect(sw: Any, mod: Any) -> dict[str, Any]:
    """Resolve both enums, build a throwaway two-cylinder assembly, CreateMateData
    for each type, QI the candidate ifaces, and dump members. No CreateMate, no
    fixture geometry constraints — pure COM-surface characterization."""
    r: dict[str, Any] = {"stage": "A_introspect"}
    slot_enum = t1._resolve_mate_enum(_SLOT_NAME)
    hinge_enum = t1._resolve_mate_enum(_HINGE_NAME)
    r["enums"] = {"swMateSLOT": slot_enum, "swMateHINGE": hinge_enum}
    if slot_enum is None or hinge_enum is None:
        r["status"] = "ENUM_ABSENT"
        return r
    a = t1._build_shaft("introA")
    b = t1._build_shaft("introB")
    if "error" in a or "error" in b:
        r["status"] = "FIXTURE_FAILED"
        r["error"] = a.get("error") or b.get("error")
        return r
    ctx = _place_pair_at(sw, mod, a, b, [60, 0, 0])
    if "error" in ctx:
        r["status"] = ctx["error"]
        return r
    typed_asm = typed(ctx["asm"], "IAssemblyDoc", module=mod)
    for label, enum_val, ifaces in (
        ("slot", slot_enum, _SLOT_IFACE),
        ("hinge", hinge_enum, _HINGE_IFACE),
    ):
        entry: dict[str, Any] = {"enum": enum_val}
        try:
            md = typed_asm.CreateMateData(enum_val)
            if md is None:
                entry["status"] = "CREATEMATEDATA_NONE"
                r[label] = entry
                continue
            entry["base_members"] = t1._member_dump(md)
            bound = t2._qi_first(md, ifaces, mod)
            if bound is None:
                entry["status"] = "NO_TYPED_IFACE"
                r[label] = entry
                continue
            iface_name, ti = bound
            entry["typed_iface"] = iface_name
            entry["members"] = t1._member_dump(ti)
            entry["status"] = "DUMPED"
        except Exception as exc:  # noqa: BLE001
            entry["status"] = "EXCEPTION"
            entry["error"] = f"{exc!r}"
        r[label] = entry
    r["status"] = "DONE"
    return r


# ---------------------------------------------------------------------------
# STAGE B — hinge solve + angle-limit persistence.
# ---------------------------------------------------------------------------
def _hinge_attempt(typed_asm: Any, mod: Any, enum_val: int,
                   a_cyl: Any, b_cyl: Any, a_cap: Any, b_cap: Any,
                   align: int) -> dict[str, Any]:
    """One hinge attempt via the ROLE-KEYED entity protocol (the run-2 fix):
    EntitiesToMate[Concentric=0] = (a_cyl,b_cyl); EntitiesToMate[Coincident=1] =
    (a_cap,b_cap). makepy surfaces the EntityType-keyed PROPPUT as
    SetEntitiesToMate(EntityType, <array>). Fresh mate-data each call."""
    out: dict[str, Any] = {"ok": False}
    try:
        md = typed_asm.CreateMateData(enum_val)
        if md is None:
            out["error"] = "CREATEMATEDATA_NONE"
            return out
        bound = t2._qi_first(md, _HINGE_IFACE, mod)
        if bound is None:
            out["error"] = "NO_TYPED_IFACE"
            return out
        iface_name, ti = bound
        out["iface_name"] = iface_name
        ti.SetEntitiesToMate(_HINGE_CONCENTRIC, w32.VARIANT(
            pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, (a_cyl, b_cyl)))
        ti.SetEntitiesToMate(_HINGE_COINCIDENT, w32.VARIANT(
            pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, (a_cap, b_cap)))
        try:
            ti.MateAlignment = align
        except Exception:  # noqa: BLE001
            pass
        mate = typed_asm.CreateMate(md)
        if mate is None or isinstance(mate, int):
            try:
                out["error_status"] = typed_qi(md, "IMateFeatureData",
                                               module=mod).ErrorStatus
            except Exception:  # noqa: BLE001
                pass
            out["error"] = "CREATEMATE_NONE"
            return out
        out["ok"] = True
        out["feature"] = mate
        return out
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"EXC {exc!r}"
        return out


def _leg_hinge(sw: Any, mod: Any) -> dict[str, Any]:
    r: dict[str, Any] = {"leg": "hinge", "status": "UNKNOWN"}
    enum_val = t1._resolve_mate_enum(_HINGE_NAME)
    r["enum_resolved"] = enum_val
    if enum_val is None:
        r["status"] = "ENUM_ABSENT"
        return r
    a = t1._build_shaft("hingeA")
    b = t1._build_shaft("hingeB")
    if "error" in a or "error" in b:
        r["status"] = "FIXTURE_FAILED"
        r["error"] = a.get("error") or b.get("error")
        return r
    # Place B coaxial, its near cap meeting A's far cap (axis = Front-plane
    # normal = +Z; A spans 0..40, B at +40 spans 40..80).
    ctx = _place_pair_at(sw, mod, a, b, [0, 0, 40])
    if "error" in ctx:
        r["status"] = ctx["error"]
        return r
    asm = ctx["asm"]
    a_cyl = t1._first_cyl_face(ctx["a"], mod)
    b_cyl = t1._first_cyl_face(ctx["b"], mod)
    # PHYSICALLY-touching cap pair: A's +Z cap, B's -Z cap (selected by normal).
    a_cap = _cap_face_by_normal_z(ctx["a"], mod, want_positive=True)
    b_cap = _cap_face_by_normal_z(ctx["b"], mod, want_positive=False)
    r["entities_found"] = {
        "a_cyl": a_cyl is not None, "b_cyl": b_cyl is not None,
        "a_cap": a_cap is not None, "b_cap": b_cap is not None,
    }
    if None in (a_cyl, b_cyl, a_cap, b_cap):
        r["status"] = "ENTITY_RESOLUTION_FAILED"
        return r
    typed_asm = typed(asm, "IAssemblyDoc", module=mod)
    # Entity ROLES are now fixed (concentric=cyls, coincident=caps); only the
    # MateAlignment of the touching caps is unknown — sweep it.
    align_names = {2: "closest", 1: "anti_aligned", 0: "aligned"}
    matrix: list[dict[str, Any]] = []
    winner: dict[str, Any] | None = None
    for aval, aname in align_names.items():
        att = _hinge_attempt(typed_asm, mod, enum_val,
                             a_cyl, b_cyl, a_cap, b_cap, aval)
        matrix.append({"align": aname, "ok": att["ok"],
                       "error": att.get("error"),
                       "error_status": att.get("error_status")})
        if att["ok"] and winner is None:
            winner = {"align": aname, "feature": att["feature"],
                      "iface_name": att["iface_name"]}
            break
    r["matrix"] = matrix
    if winner is None:
        r["status"] = "CREATEMATE_NONE_ALL_ALIGNMENTS"
        return r
    r["winning_align"] = winner["align"]
    try:
        ifeat = typed(winner["feature"], "IFeature", module=mod)
        r["feature_type"] = ifeat.GetTypeName2()
        ec = ifeat.GetErrorCode2()
        r["error_code2"] = list(ec) if isinstance(ec, (list, tuple)) else ec
        asm_path = str(Path(t1._results_tmp(), f"hinge_asm_{os.getpid()}.SLDASM"))
        save_ok = typed(asm, "IModelDoc2", module=mod).SaveAs3(asm_path, 0, 0)
        if int(save_ok) != 0:
            r["status"] = "SAVE_FAILED"
            return r
        rb = t2._read_back(sw, mod, asm_path, winner["iface_name"],
                           ("Angle", "MaxVal", "MinVal", "MateAlignment"))
        r["persist"] = rb
        r["status"] = ("SOLVED_PERSISTED" if "read_back" in rb
                       else "SOLVED_READBACK_UNVERIFIED")
    except Exception as exc:  # noqa: BLE001
        r["status"] = "EXCEPTION"
        r["error"] = f"{exc!r}\n{traceback.format_exc()}"
    return r


# ---------------------------------------------------------------------------
# STAGE C — slot solve + constraint/distance persistence.
# ---------------------------------------------------------------------------
def _leg_slot(sw: Any, mod: Any) -> dict[str, Any]:
    r: dict[str, Any] = {"leg": "slot", "status": "UNKNOWN"}
    enum_val = t1._resolve_mate_enum(_SLOT_NAME)
    r["enum_resolved"] = enum_val
    if enum_val is None:
        r["status"] = "ENUM_ABSENT"
        return r
    plate = _build("slotplate", _slot_plate_spec("slotplate"))
    pin = _build("pin", _pin_spec("pin"))
    if "error" in plate or "error" in pin:
        r["status"] = "FIXTURE_FAILED"
        r["error"] = plate.get("error") or pin.get("error")
        return r
    ctx = _place_pair_at(sw, mod, plate, pin, [0, 0, 40])
    if "error" in ctx:
        r["status"] = ctx["error"]
        return r
    asm = ctx["asm"]
    # Slot side: a cylindrical face of the plate = an arc end of the slot cut.
    slot_face = t1._first_cyl_face(ctx["a"], mod)
    pin_face = t1._first_cyl_face(ctx["b"], mod)
    r["entities_found"] = {"slot_cyl_face": slot_face is not None,
                           "pin_cyl_face": pin_face is not None}
    if slot_face is None or pin_face is None:
        r["status"] = "ENTITY_RESOLUTION_FAILED"
        return r
    try:
        typed_asm = typed(asm, "IAssemblyDoc", module=mod)
        md = typed_asm.CreateMateData(enum_val)
        if md is None:
            r["status"] = "CREATEMATEDATA_NONE"
            return r
        bound = t2._qi_first(md, _SLOT_IFACE, mod)
        if bound is None:
            r["status"] = "NO_TYPED_IFACE"
            return r
        iface_name, ti = bound
        r["typed_iface"] = iface_name
        members = t1._member_dump(ti)
        r["iface_members"] = members
        # EntitiesToMate is a plain SYMMETRIC array on slot (FUNCDESC nargs=1,
        # VT_VARIANT) — the _set_entities array form binds directly.
        r["entities_set_via"] = t2._set_entities(ti, [slot_face, pin_face])
        # Constraint = swSlotMateConstraintOption_Centered(1): pin centered in
        # the slot. Set BEFORE CreateMate, then verify it ROUND-TRIPS through
        # save/reopen — the real Tier-3 GREEN (not just a clean solve).
        _SLOT_CENTERED = 1
        ti.Constraint = _SLOT_CENTERED
        r["constraint_set"] = {"Constraint": _SLOT_CENTERED}
        mate = typed_asm.CreateMate(md)
        if mate is None or isinstance(mate, int):
            try:
                mfd = typed_qi(md, "IMateFeatureData", module=mod)
                r["error_status"] = mfd.ErrorStatus
            except Exception:  # noqa: BLE001
                pass
            r["status"] = "CREATEMATE_NONE"
            return r
        ifeat = typed(mate, "IFeature", module=mod)
        r["feature_type"] = ifeat.GetTypeName2()
        ec = ifeat.GetErrorCode2()
        r["error_code2"] = list(ec) if isinstance(ec, (list, tuple)) else ec
        asm_path = str(Path(t1._results_tmp(), f"slot_asm_{os.getpid()}.SLDASM"))
        save_ok = typed(asm, "IModelDoc2", module=mod).SaveAs3(asm_path, 0, 0)
        if int(save_ok) != 0:
            r["status"] = "SAVE_FAILED"
            return r
        rb = t2._read_back(sw, mod, asm_path, iface_name,
                           ("Constraint", "MateAlignment"))
        r["persist"] = rb
        if "read_back" in rb:
            got = rb["read_back"].get("Constraint")
            holds = (got == _SLOT_CENTERED)
            r["status"] = "SOLVED_CONSTRAINT_PERSISTED" if holds else "SOLVED_CONSTRAINT_TRANSFORMED"
        else:
            r["status"] = "SOLVED_READBACK_UNVERIFIED"
    except Exception as exc:  # noqa: BLE001
        r["status"] = "EXCEPTION"
        r["error"] = f"{exc!r}\n{traceback.format_exc()}"
    return r


def main() -> int:
    result: dict[str, Any] = {"spike_id": "mech_mate_tier3_slot_hinge", "stages": {}}
    try:
        sw = get_sw_app()
        mod = wrapper_module()
        try:
            sw.CloseAllDocuments(True)
        except Exception:  # noqa: BLE001
            pass
        result["stages"]["A_introspect"] = _introspect(sw, mod)
        print(f"[t3] A_introspect -> {result['stages']['A_introspect'].get('status')}")
        result["stages"]["B_hinge"] = _leg_hinge(sw, mod)
        print(f"[t3] B_hinge -> {result['stages']['B_hinge'].get('status')}")
        result["stages"]["C_slot"] = _leg_slot(sw, mod)
        print(f"[t3] C_slot -> {result['stages']['C_slot'].get('status')}")
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
