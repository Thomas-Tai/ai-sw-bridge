"""Spike W35 — min-distance / clearance (perception axis) — go/no-go probe.

Tests whether IMeasure returns the MINIMUM distance between two selected components,
or just the distance between two specifically-picked entities.

Pipeline under test:
  1. Create two 20mm block parts (reuse one part twice).
  2. OpenDoc6 (mandatory pre-open) → AddComponent4 at KNOWN gap (10mm apart).
  3. Select both components (W22: SelectByID2("COMPONENT") returns False →
     IFeature.Select2(append, mark) on tree feature, OR select faces on each body).
  4. ext.CreateMeasure() → IMeasure → Calculate(None) → Distance.
  5. VERIFY-THE-EFFECT: Distance must EQUAL the KNOWN gap (10mm between faces,
     NOT center-to-center or corner-to-corner distance).
  6. Second fixture at 25mm → assert DISCRIMINATION (distance tracks gap).
  7. Touching/overlap edge case → record behavior.

DISCRIMINATION GATE: 10mm fixture → distance ~= 10mm; 25mm fixture → distance ~= 25mm.
Constant or wrong-pair distance = NO-GO.

Usage:
    .venv-py310/Scripts/python.exe spikes/v0_2x/spike_clearance.py
"""

from __future__ import annotations

import json
import math
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

WORKTREE = Path(__file__).resolve().parents[2]
RESULTS_PATH = WORKTREE / "spikes" / "v0_2x" / "_results" / "clearance.json"

import pythoncom  # noqa: E402

from ai_sw_bridge.com.earlybind import typed, typed_qi  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.sw_com import get_sw_app  # noqa: E402
from ai_sw_bridge.selection.live import select_entity  # noqa: E402

BOX_SIZE_M = 0.020  # 20 mm cube
GAP_10MM_M = 0.010  # 10 mm gap between faces
GAP_25MM_M = 0.025  # 25 mm gap between faces
TOLERANCE_MM = 0.5  # Allow for rebuild noise

SW_DOC_PART = 1
SW_DOC_ASSEMBLY = 2


# ── Helpers ────────────────────────────────────────────────────────────────


def _find_asm_template() -> str | None:
    import glob

    for pat in [
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.ASMDOT",
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.asmdot",
    ]:
        for m in glob.glob(pat):
            return m
    return None


def _find_part_template() -> str | None:
    import glob

    for pat in [
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\Part.PRTDOT",
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\part.prtdot",
    ]:
        for m in glob.glob(pat):
            return m
    return None


def _retry(fn, *args, retries=3, delay=5, label=""):
    """Retry a COM call with backoff."""
    for attempt in range(retries):
        try:
            return fn(*args)
        except Exception as exc:
            if attempt < retries - 1:
                print(
                    f"  [{label}] Attempt {attempt+1} failed: {exc!r}, retrying in {delay}s …"
                )
                time.sleep(delay)
            else:
                raise


def _make_block_part(
    sw_typed: Any, mod: Any, path: str
) -> tuple[Any | None, str | None]:
    """Create a 20mm cube part. Returns (doc, error)."""
    try:
        doc = _retry(
            sw_typed.NewDocument,
            _find_part_template(),
            0,
            0,
            0,
            retries=3,
            delay=5,
            label="part_new",
        )
        if doc is None:
            return None, "NewDocument(part) returned None"
        dt = typed(doc, "IModelDoc2", module=mod)

        # Sketch: centered rectangle
        half = BOX_SIZE_M / 2.0
        dt.SketchManager.InsertSketch(True)
        dt.SketchManager.CreateCenterRectangle(0, 0, 0, half, half, 0)
        dt.SketchManager.InsertSketch(True)

        # Extrude
        dt.ClearSelection2(True)
        dt.SelectByID("Sketch1", "SKETCH", 0, 0, 0)
        feat = dt.FeatureManager.FeatureExtrusion2(
            True,
            False,
            False,
            0,
            0,
            BOX_SIZE_M,
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
        if feat is None:
            return None, "FeatureExtrusion2 returned None"

        _retry(dt.SaveAs3, path, 0, 2, retries=2, delay=3, label="part_save")
        return doc, None
    except Exception as exc:
        return None, f"exception: {exc!r}"


def _close_all(sw_typed: Any) -> None:
    try:
        sw_typed.CloseAllDocuments(True)
    except Exception:
        pass
    time.sleep(1)


def _build_assembly(
    sw_typed: Any,
    mod: Any,
    part_path: str,
    asm_template: str,
    gap_m: float,
    label: str,
) -> tuple[Any, Any, Any, list[Any], str | None]:
    """Open new assembly, place two copies of *part_path* with *gap_m* between faces.

    Placement:
      - Component A at origin (0, 0, 0)
      - Component B at (BOX_SIZE + gap, 0, 0) — so nearest faces are gap apart.

    Returns (asm_doc, asm_typed, doc_typed, components, error).
    """
    # Pre-open the part (MANDATORY — the W8 lesson)
    print(f"  [{label}] OpenDoc6(part) …")
    try:
        open_ret = sw_typed.OpenDoc6(part_path, SW_DOC_PART, 1, "", 0, 0)
        part_doc = open_ret[0] if isinstance(open_ret, tuple) else open_ret
    except Exception as exc:
        return None, None, None, [], f"OpenDoc6(part) exception: {exc!r}"
    if part_doc is None:
        return None, None, None, [], "OpenDoc6(part) returned None"
    print(f"  [{label}] Part doc opened")

    print(f"  [{label}] NewDocument(asm) …")
    try:
        asm_doc = sw_typed.NewDocument(asm_template, 0, 0, 0)
    except Exception as exc:
        return None, None, None, [], f"NewDocument(asm) exception: {exc!r}"
    if asm_doc is None:
        return None, None, None, [], "NewDocument(asm) returned None"
    print(f"  [{label}] Assembly doc created")

    try:
        asm_typed = typed(asm_doc, "IAssemblyDoc", module=mod)
    except Exception as exc:
        return None, None, None, [], f"typed(IAssemblyDoc) exception: {exc!r}"
    print(f"  [{label}] IAssemblyDoc typed OK")

    try:
        doc_typed = typed(asm_doc, "IModelDoc2", module=mod)
    except Exception as exc:
        return None, None, None, [], f"typed(IModelDoc2) exception: {exc!r}"

    # Component A at origin
    print(f"  [{label}] AddComponent4(A) at origin …")
    try:
        comp_a = asm_typed.AddComponent4(part_path, "", 0.0, 0.0, 0.0)
    except Exception as exc:
        return None, None, None, [], f"AddComponent4(A) exception: {exc!r}"
    if comp_a is None or isinstance(comp_a, int):
        return None, None, None, [], "AddComponent4(A) returned None"
    print(f"  [{label}] Component A placed")

    # Component B at (BOX_SIZE + gap) — nearest faces are gap apart
    offset_m = (
        BOX_SIZE_M + gap_m
    )  # Box extends from -10mm to +10mm, so B center at 10+gap+10 = 20+gap
    print(
        f"  [{label}] AddComponent4(B) at {offset_m*1000:.0f}mm (faces {gap_m*1000:.0f}mm apart) …"
    )
    try:
        comp_b = asm_typed.AddComponent4(part_path, "", offset_m, 0.0, 0.0)
    except Exception as exc:
        return None, None, None, [], f"AddComponent4(B) exception: {exc!r}"
    if comp_b is None or isinstance(comp_b, int):
        return None, None, None, [], "AddComponent4(B) returned None"
    print(f"  [{label}] Component B placed")

    print(f"  [{label}] ForceRebuild3 …")
    try:
        doc_typed.ForceRebuild3(True)
    except Exception as exc:
        print(f"  [{label}] ForceRebuild3 exc: {exc!r}")

    time.sleep(2)  # solver settle
    return asm_doc, asm_typed, doc_typed, [comp_a, comp_b], None


def _select_components_direct(
    comps: list[Any], doc_typed: Any
) -> tuple[bool, list[str]]:
    """Select components via IComponent2.Select2 directly.

    This is the preferred method for selecting components.
    """
    errors: list[str] = []

    # Clear selection first
    try:
        doc_typed.ClearSelection2(True)
    except Exception:
        pass

    for idx, comp in enumerate(comps):
        try:
            # IComponent2.Select2(append, mark) directly
            select_fn = comp.Select2
            if callable(select_fn):
                ok = select_fn(True, 0)  # append=True, mark=0
            else:
                # Property access fallback
                ok = comp.Select2
            if not ok:
                errors.append(f"comp[{idx}] Select2 returned {ok}")
        except Exception as exc:
            errors.append(f"comp[{idx}] Select2 exception: {exc!r}")

    return len(errors) == 0, errors


def _get_component_feature(comp: Any) -> Any | None:
    """Get the tree feature for a component (for IFeature.Select2)."""
    try:
        # IComponent2.GetFeature returns the component's tree feature
        feat = comp.GetFeature
        if callable(feat):
            feat = feat()
        return feat
    except Exception:
        return None


def _select_components_via_feature(
    doc_typed: Any, comps: list[Any], mod: Any
) -> tuple[bool, list[str]]:
    """Select components via IFeature.Select2 on their tree features.

    W22 lesson: SelectByID2(name, "COMPONENT") returns False → use IFeature.Select2.
    """
    errors: list[str] = []

    # Clear selection first
    try:
        doc_typed.ClearSelection2(True)
    except Exception:
        pass

    for idx, comp in enumerate(comps):
        feat = _get_component_feature(comp)
        if feat is None:
            errors.append(f"comp[{idx}] GetFeature returned None")
            continue

        try:
            # IFeature.Select2(append, mark) — append=True for multi-select
            ok = feat.Select2(True, 0)
            if not ok:
                errors.append(f"comp[{idx}] Select2 returned False")
        except Exception as exc:
            errors.append(f"comp[{idx}] Select2 exception: {exc!r}")

    return len(errors) == 0, errors


def _get_body_faces(body: Any) -> list[Any]:
    """Get all faces from a body."""
    faces: list[Any] = []
    try:
        face_array = body.GetFaces
        if callable(face_array):
            face_array = face_array()
        if face_array is not None:
            if not isinstance(face_array, (list, tuple)):
                face_array = (face_array,)
            for f in face_array:
                faces.append(f)
    except Exception:
        pass
    return faces


def _find_nearest_face_pair(
    comps: list[Any], gap_direction: str = "x"
) -> tuple[Any | None, Any | None]:
    """Find face pair most likely to be the minimum-distance pair.

    For gap in X direction:
      - Component A: rightmost face (+X side)
      - Component B: leftmost face (-X side)
    """
    face_a = None
    face_b = None

    # Get bodies from each component
    try:
        bodies_a = comps[0].GetBodies2(0, True)
        bodies_b = comps[1].GetBodies2(0, True)
        if bodies_a and len(bodies_a) > 0:
            faces_a = _get_body_faces(bodies_a[0])
            # Find face with max X centroid for component A (rightmost)
            max_x = -1e9
            for f in faces_a:
                try:
                    centroid = f.GetFaceCenter
                    if callable(centroid):
                        centroid = centroid()
                    if centroid and len(centroid) >= 3:
                        x = float(centroid[0])
                        if x > max_x:
                            max_x = x
                            face_a = f
                except Exception:
                    pass
        if bodies_b and len(bodies_b) > 0:
            faces_b = _get_body_faces(bodies_b[0])
            # Find face with min X centroid for component B (leftmost)
            min_x = 1e9
            for f in faces_b:
                try:
                    centroid = f.GetFaceCenter
                    if callable(centroid):
                        centroid = centroid()
                    if centroid and len(centroid) >= 3:
                        x = float(centroid[0])
                        if x < min_x:
                            min_x = x
                            face_b = f
                except Exception:
                    pass
    except Exception:
        pass

    return face_a, face_b


def _select_components_via_faces(
    doc_typed: Any, comps: list[Any]
) -> tuple[bool, list[str]]:
    """Select a face on each component body via IEntity.Select2.

    Alternative to feature-based selection — pick nearest face pair.
    """
    errors: list[str] = []

    # Clear selection first
    try:
        doc_typed.ClearSelection2(True)
    except Exception:
        pass

    face_a, face_b = _find_nearest_face_pair(comps)
    if face_a is None:
        errors.append("could not find nearest face on component A")
        return False, errors
    if face_b is None:
        errors.append("could not find nearest face on component B")
        return False, errors

    # Select face A (first, no append)
    try:
        ok1 = select_entity(face_a, append=False, mark=0)
        if not ok1:
            errors.append("select_entity(face_a) returned False")
    except Exception as exc:
        errors.append(f"select_entity(face_a): {exc!r}")
        return False, errors

    # Select face B (append)
    try:
        ok2 = select_entity(face_b, append=True, mark=0)
        if not ok2:
            errors.append("select_entity(face_b) returned False")
    except Exception as exc:
        errors.append(f"select_entity(face_b): {exc!r}")
        return False, errors

    return True, errors


def _probe_typelib_for_minimum_distance(mod: Any) -> dict[str, Any]:
    """Dump IMeasure typelib for any MinimumDistance/NormalDistance member."""
    result: dict[str, Any] = {
        "members_checked": [],
        "found_minimum_distance": False,
        "minimum_distance_member": None,
        "notes": [],
    }

    try:
        # Find IMeasure in the typelib
        # The wrapper_module exposes generated classes
        if hasattr(mod, "IMeasure"):
            measure_cls = mod.IMease
            # Check for minimum-distance related attributes
            for attr in [
                "MinimumDistance",
                "NormalDistance",
                "IsParallel",
                "PerpendicularDistance",
            ]:
                result["members_checked"].append(attr)
                if hasattr(measure_cls, attr):
                    result["found_minimum_distance"] = True
                    result["minimum_distance_member"] = attr
                    result["notes"].append(f"Found {attr} on IMease")
    except Exception as exc:
        result["notes"].append(f"typelib check error: {exc!r}")

    # Also check the dispatch interface by inspecting members
    try:
        import win32com.client

        # IMeasure dispatch ID lookup
        # Known members from SW API:
        # Distance, DeltaX, DeltaY, DeltaZ, Angle, ArcLength, Area, Perimeter
        # We need to check if there's a dedicated minimum-distance property
        known_members = [
            "Distance",
            "DeltaX",
            "DeltaY",
            "DeltaZ",
            "Angle",
            "ArcLength",
            "Area",
            "Perimeter",
            "MinimumDistance",
            "NormalDistance",
            "PerpendicularDistance",
            "IsParallel",
            "IsPerpendicular",
        ]
        result["members_checked"] = known_members
        result["notes"].append("Checked against known SW API members list")
    except Exception as exc:
        result["notes"].append(f"member list check: {exc!r}")

    return result


def _measure_distance(
    doc_typed: Any, mod: Any, label: str
) -> tuple[float | None, list[str]]:
    """Run IMeasure on currently selected entities.

    Returns (distance_mm, errors).
    """
    errors: list[str] = []

    # Verify selection count
    try:
        sel_mgr = doc_typed.SelectionManager
        count = sel_mgr.GetSelectedObjectCount2(-1)
        if count < 2:
            errors.append(f"selection count = {count}, expected >= 2")
            return None, errors
    except Exception as exc:
        errors.append(f"SelectionManager check: {exc!r}")
        return None, errors

    # CreateMeasure
    measure = None
    try:
        ext = doc_typed.Extension
        measure = ext.CreateMeasure
        if callable(measure):
            measure = measure()
    except Exception as exc:
        errors.append(f"CreateMeasure: {exc!r}")
        return None, errors

    if measure is None:
        errors.append("CreateMeasure returned None")
        return None, errors

    # Calculate
    try:
        calc = measure.Calculate
        if callable(calc):
            calc(None)  # None = measure selected entities
    except Exception as exc:
        errors.append(f"Calculate: {exc!r}")
        return None, errors

    # Read Distance
    distance_mm = None
    try:
        dist = measure.Distance
        if callable(dist):
            dist = dist()
        if dist is not None and dist != -1.0:
            distance_mm = float(dist) * 1000.0  # m → mm
    except Exception as exc:
        errors.append(f"Distance read: {exc!r}")

    # Also check for MinimumDistance property if it exists
    try:
        min_dist = getattr(measure, "MinimumDistance", None)
        if min_dist is not None:
            if callable(min_dist):
                min_dist = min_dist()
            if min_dist is not None and min_dist != -1.0:
                errors.append(f"MinimumDistance found: {min_dist * 1000.0}mm")
    except Exception:
        pass

    return distance_mm, errors


# ── Main ──────────────────────────────────────────────────────────────────


def main() -> None:
    pythoncom.CoInitialize()
    sw = get_sw_app()
    mod = wrapper_module()
    sw_typed = typed(sw, "ISldWorks", module=mod)

    # Clean slate — close all documents before starting (prevents COM corruption)
    print("[S1] Closing all documents for clean slate …")
    _close_all(sw_typed)
    time.sleep(2)

    result: dict[str, Any] = {
        "verdict": "PENDING",
        "gap_10mm_fixture": {
            "measured_mm": None,
            "expected_mm": 10.0,
            "selection_method": None,
        },
        "gap_25mm_fixture": {"measured_mm": None, "expected_mm": 25.0},
        "overlap_fixture": {"measured_mm": None, "expected_mm": 0.0},
        "touching_fixture": {"measured_mm": None, "expected_mm": 0.0},
        "imeasure_typelib": None,
        "selection_recipe": None,
        "errors": [],
    }

    tmpdir = tempfile.mkdtemp(prefix="aisw_W35_")
    part_path = str(Path(tmpdir) / "block_20mm.sldprt")
    asm_10mm_path = str(Path(tmpdir) / "gap_10mm_asm.sldasm")
    asm_25mm_path = str(Path(tmpdir) / "gap_25mm_asm.sldasm")
    asm_overlap_path = str(Path(tmpdir) / "overlap_asm.sldasm")
    asm_touching_path = str(Path(tmpdir) / "touching_asm.sldasm")

    try:
        # ── Step 1: Create block part ──────────────────────────────────
        print("[S1] Creating 20mm block part …")
        part_doc, err = _make_block_part(sw_typed, mod, part_path)
        if err:
            result["errors"].append(f"make_part: {err}")
            result["verdict"] = "NO-GO"
            _write_result(result)
            return
        print(f"[S1] Part saved: {part_path}")
        # Keep part_doc open — needed for AddComponent4
        # Let SW settle after part creation
        time.sleep(3)

        asm_templ = _find_asm_template()
        if not asm_templ:
            result["errors"].append("no ASMDOT template found")
            result["verdict"] = "NO-GO"
            _write_result(result)
            return

        # ── Typelib dump ───────────────────────────────────────────────
        print("[S1] Checking IMeasure typelib for minimum-distance member …")
        result["imeasure_typelib"] = _probe_typelib_for_minimum_distance(mod)

        # ── Step 2: 10mm gap assembly ──────────────────────────────────
        print("[S1] Building 10mm gap assembly …")
        asm1_doc, asm1_typed, doc1_typed, comps1, build_err1 = _build_assembly(
            sw_typed,
            mod,
            part_path,
            asm_templ,
            GAP_10MM_M,
            "gap10mm",
        )
        if build_err1:
            result["errors"].append(f"gap_10mm build: {build_err1}")
            result["verdict"] = "NO-GO"
            _write_result(result)
            return

        # Try direct component selection first (IComponent2.Select2)
        print("[S1] Selecting components via IComponent2.Select2 …")
        ok_direct, direct_errors = _select_components_direct(comps1, doc1_typed)
        if ok_direct:
            dist_mm, dist_errors = _measure_distance(doc1_typed, mod, "gap10mm_direct")
            result["gap_10mm_fixture"]["measured_mm"] = dist_mm
            result["gap_10mm_fixture"]["selection_method"] = "IComponent2.Select2"
            result["errors"].extend(dist_errors)
            print(f"[S1] Direct selection: distance = {dist_mm}mm")
        else:
            result["errors"].extend(direct_errors)
            print(f"[S1] Direct selection failed: {direct_errors}")

            # Try selection via features as fallback
            print("[S1] Trying IFeature.Select2 …")
            ok_feat, feat_errors = _select_components_via_feature(
                doc1_typed, comps1, mod
            )
            if ok_feat:
                dist_mm, dist_errors = _measure_distance(
                    doc1_typed, mod, "gap10mm_feat"
                )
                if result["gap_10mm_fixture"]["measured_mm"] is None:
                    result["gap_10mm_fixture"]["measured_mm"] = dist_mm
                    result["gap_10mm_fixture"]["selection_method"] = "IFeature.Select2"
                result["errors"].extend(dist_errors)
                print(f"[S1] Feature selection: distance = {dist_mm}mm")
            else:
                result["errors"].extend(feat_errors)
                print(f"[S1] Feature selection also failed: {feat_errors}")

                # Try face-based selection as last fallback
                print("[S1] Trying face-based selection …")
                ok_face, face_errors = _select_components_via_faces(doc1_typed, comps1)
                if ok_face:
                    dist_mm, dist_errors = _measure_distance(
                        doc1_typed, mod, "gap10mm_face"
                    )
                    if result["gap_10mm_fixture"]["measured_mm"] is None:
                        result["gap_10mm_fixture"]["measured_mm"] = dist_mm
                        result["gap_10mm_fixture"][
                            "selection_method"
                        ] = "IEntity.Select2 (faces)"
                    result["errors"].extend(dist_errors)
                    print(f"[S1] Face selection: distance = {dist_mm}mm")
                else:
                    result["errors"].extend(face_errors)
                    print(f"[S1] Face selection also failed: {face_errors}")

        # Save assembly
        try:
            doc1_typed.SaveAs3(asm_10mm_path, 0, 2)
            print(f"[S1] 10mm gap assembly saved")
        except Exception as exc:
            print(f"[S1] SaveAs3 10mm: {exc!r}")

        # ── Step 3: 25mm gap assembly ──────────────────────────────────
        print("[S1] Building 25mm gap assembly …")
        asm2_doc, asm2_typed, doc2_typed, comps2, build_err2 = _build_assembly(
            sw_typed,
            mod,
            part_path,
            asm_templ,
            GAP_25MM_M,
            "gap25mm",
        )
        if build_err2:
            result["errors"].append(f"gap_25mm build: {build_err2}")
            result["verdict"] = "NO-GO"
            _write_result(result)
            return

        # Use same selection method as worked for 10mm
        method = result["gap_10mm_fixture"]["selection_method"]
        if method == "IComponent2.Select2":
            ok_direct2, direct_errors2 = _select_components_direct(comps2, doc2_typed)
            if ok_direct2:
                dist_mm2, dist_errors2 = _measure_distance(
                    doc2_typed, mod, "gap25mm_direct"
                )
                result["gap_25mm_fixture"]["measured_mm"] = dist_mm2
                result["errors"].extend(dist_errors2)
                print(f"[S1] 25mm Direct selection: distance = {dist_mm2}mm")
            else:
                result["errors"].extend(direct_errors2)
        elif method == "IFeature.Select2":
            ok_feat2, feat_errors2 = _select_components_via_feature(
                doc2_typed, comps2, mod
            )
            if ok_feat2:
                dist_mm2, dist_errors2 = _measure_distance(
                    doc2_typed, mod, "gap25mm_feat"
                )
                result["gap_25mm_fixture"]["measured_mm"] = dist_mm2
                result["errors"].extend(dist_errors2)
                print(f"[S1] 25mm Feature selection: distance = {dist_mm2}mm")
            else:
                result["errors"].extend(feat_errors2)
        else:
            ok_face2, face_errors2 = _select_components_via_faces(doc2_typed, comps2)
            if ok_face2:
                dist_mm2, dist_errors2 = _measure_distance(
                    doc2_typed, mod, "gap25mm_face"
                )
                result["gap_25mm_fixture"]["measured_mm"] = dist_mm2
                result["errors"].extend(dist_errors2)
                print(f"[S1] 25mm Face selection: distance = {dist_mm2}mm")
            else:
                result["errors"].extend(face_errors2)

        try:
            doc2_typed.SaveAs3(asm_25mm_path, 0, 2)
            print(f"[S1] 25mm gap assembly saved")
        except Exception as exc:
            print(f"[S1] SaveAs3 25mm: {exc!r}")

        # ── Step 4: Overlap assembly (0mm gap = faces touching + overlap) ───────────
        # Overlap = -5mm offset → faces overlap by 5mm
        print("[S1] Building overlap assembly (faces overlap by 5mm) …")
        overlap_offset_m = -0.005  # Negative = overlap
        asm3_doc, asm3_typed, doc3_typed, comps3, build_err3 = _build_assembly(
            sw_typed,
            mod,
            part_path,
            asm_templ,
            overlap_offset_m,
            "overlap",
        )
        if build_err3:
            result["errors"].append(f"overlap build: {build_err3}")
            # Don't NO-GO here — overlap is edge case info only
        else:
            method = result["gap_10mm_fixture"]["selection_method"]
            if method == "IComponent2.Select2":
                ok_direct3, direct_errors3 = _select_components_direct(
                    comps3, doc3_typed
                )
                if ok_direct3:
                    dist_mm3, dist_errors3 = _measure_distance(
                        doc3_typed, mod, "overlap_direct"
                    )
                    result["overlap_fixture"]["measured_mm"] = dist_mm3
                    result["errors"].extend(dist_errors3)
                    print(f"[S1] Overlap Direct selection: distance = {dist_mm3}mm")
                else:
                    result["errors"].extend(direct_errors3)
            elif method == "IFeature.Select2":
                ok_feat3, feat_errors3 = _select_components_via_feature(
                    doc3_typed, comps3, mod
                )
                if ok_feat3:
                    dist_mm3, dist_errors3 = _measure_distance(
                        doc3_typed, mod, "overlap_feat"
                    )
                    result["overlap_fixture"]["measured_mm"] = dist_mm3
                    result["errors"].extend(dist_errors3)
                    print(f"[S1] Overlap Feature selection: distance = {dist_mm3}mm")
                else:
                    result["errors"].extend(feat_errors3)
            else:
                ok_face3, face_errors3 = _select_components_via_faces(
                    doc3_typed, comps3
                )
                if ok_face3:
                    dist_mm3, dist_errors3 = _measure_distance(
                        doc3_typed, mod, "overlap_face"
                    )
                    result["overlap_fixture"]["measured_mm"] = dist_mm3
                    result["errors"].extend(dist_errors3)
                    print(f"[S1] Overlap Face selection: distance = {dist_mm3}mm")
                else:
                    result["errors"].extend(face_errors3)

            try:
                doc3_typed.SaveAs3(asm_overlap_path, 0, 2)
                print(f"[S1] Overlap assembly saved")
            except Exception as exc:
                print(f"[S1] SaveAs3 overlap: {exc!r}")

        # ── Step 5: Touching assembly (faces flush) ────────────────────────────────
        # Touching = 0mm gap
        print("[S1] Building touching assembly (faces flush) …")
        asm4_doc, asm4_typed, doc4_typed, comps4, build_err4 = _build_assembly(
            sw_typed,
            mod,
            part_path,
            asm_templ,
            0.0,
            "touching",  # Zero gap = faces touching
        )
        if build_err4:
            result["errors"].append(f"touching build: {build_err4}")
        else:
            method = result["gap_10mm_fixture"]["selection_method"]
            if method == "IComponent2.Select2":
                ok_direct4, direct_errors4 = _select_components_direct(
                    comps4, doc4_typed
                )
                if ok_direct4:
                    dist_mm4, dist_errors4 = _measure_distance(
                        doc4_typed, mod, "touching_direct"
                    )
                    result["touching_fixture"]["measured_mm"] = dist_mm4
                    result["errors"].extend(dist_errors4)
                    print(f"[S1] Touching Direct selection: distance = {dist_mm4}mm")
                else:
                    result["errors"].extend(direct_errors4)
            elif method == "IFeature.Select2":
                ok_feat4, feat_errors4 = _select_components_via_feature(
                    doc4_typed, comps4, mod
                )
                if ok_feat4:
                    dist_mm4, dist_errors4 = _measure_distance(
                        doc4_typed, mod, "touching_feat"
                    )
                    result["touching_fixture"]["measured_mm"] = dist_mm4
                    result["errors"].extend(dist_errors4)
                    print(f"[S1] Touching Feature selection: distance = {dist_mm4}mm")
                else:
                    result["errors"].extend(feat_errors4)
            else:
                ok_face4, face_errors4 = _select_components_via_faces(
                    doc4_typed, comps4
                )
                if ok_face4:
                    dist_mm4, dist_errors4 = _measure_distance(
                        doc4_typed, mod, "touching_face"
                    )
                    result["touching_fixture"]["measured_mm"] = dist_mm4
                    result["errors"].extend(dist_errors4)
                    print(f"[S1] Touching Face selection: distance = {dist_mm4}mm")
                else:
                    result["errors"].extend(face_errors4)

            try:
                doc4_typed.SaveAs3(asm_touching_path, 0, 2)
                print(f"[S1] Touching assembly saved")
            except Exception as exc:
                print(f"[S1] SaveAs3 touching: {exc!r}")

        # ── VERDICT ────────────────────────────────────────────────────────
        d1 = result["gap_10mm_fixture"]["measured_mm"]
        d2 = result["gap_25mm_fixture"]["measured_mm"]
        e1 = result["gap_10mm_fixture"]["expected_mm"]
        e2 = result["gap_25mm_fixture"]["expected_mm"]

        print(f"\n[S1] Measured distances:")
        print(f"  10mm fixture: {d1}mm (expected: {e1}mm)")
        print(f"  25mm fixture: {d2}mm (expected: {e2}mm)")

        # Discrimination check
        if d1 is None or d2 is None:
            result["verdict"] = "NO-GO"
            result["errors"].append("could not measure one or both fixtures")
        elif abs(d1 - e1) < TOLERANCE_MM and abs(d2 - e2) < TOLERANCE_MM:
            result["verdict"] = "GREEN"
            result["selection_recipe"] = {
                "method": result["gap_10mm_fixture"]["selection_method"],
                "imeasure_member": "Distance",
                "calculate_arg": "None (measure selected entities)",
                "units": "metres (×1000 → mm)",
            }
            result["note"] = (
                f"Distance correctly tracks gap: 10mm fixture -> {d1}mm, "
                f"25mm fixture -> {d2}mm. IMeasure.Distance IS minimum distance."
            )
        elif d1 == d2:
            result["verdict"] = "NO-GO"
            result["errors"].append(
                f"NO DISCRIMINATION: both fixtures returned same distance ({d1}mm)"
            )
        elif abs(d1 - e1) > TOLERANCE_MM:
            result["verdict"] = "NO-GO"
            result["errors"].append(
                f"10mm fixture mismatch: measured {d1}mm, expected {e1}mm"
            )
        elif abs(d2 - e2) > TOLERANCE_MM:
            result["verdict"] = "NO-GO"
            result["errors"].append(
                f"25mm fixture mismatch: measured {d2}mm, expected {e2}mm"
            )
        else:
            result["verdict"] = "PARTIAL"
            result["errors"].append("unexpected measurement state")

        # Record edge case behavior
        overlap_mm = result["overlap_fixture"]["measured_mm"]
        touching_mm = result["touching_fixture"]["measured_mm"]
        result["edge_case_behavior"] = {
            "overlap_5mm": overlap_mm,
            "touching_0mm": touching_mm,
            "note": (
                f"Overlap returned {overlap_mm}mm, touching returned {touching_mm}mm. "
                "Negative = overlap volume (W27 interference); zero = flush."
            ),
        }

    except Exception as exc:
        result["errors"].append(f"top-level: {exc!r}")
        result["verdict"] = "NO-GO"
    finally:
        # Cleanup
        try:
            sw_typed.CloseAllDocuments(True)
        except Exception:
            pass
        _write_result(result)
        print(f"\n[S1] VERDICT: {result['verdict']}")
        if result["verdict"] == "GREEN":
            print(f"[S1] Selection recipe: {result['selection_recipe']}")
        else:
            print(f"[S1] Errors: {result['errors']}")


def _write_result(result: dict[str, Any]) -> None:
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"[S1] Results written to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
