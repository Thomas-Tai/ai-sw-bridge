"""Recipe-C cut #4 — advanced-shapes family (loft/rib/dome/wrap/boundary_boss/wizard_hole).

All six handlers are relocated byte-identical from mutate.py into the
HANDLER_REGISTRY seam.  The wizard-hole private helper cluster
(_arrays_from_out / _hole_table_sizes / _SIZE_ERROR_DISPLAY_LIMIT /
_format_size_catalog / _resolve_hole_args) moves here with the handler.

Registry disposition is PER-FEATURE — a structural boundary port relocates
code, it does NOT promote walls (the M1 undo-bug precedent, in reverse):
  * dome + wizard_hole were in HEAD ``_SUPPORTED_FEATURE_TYPES`` → GREEN
    (advertised through the registry).
  * loft / rib / wrap are documented PERMANENT kernel walls (loft NO-GO;
    rib WALLED both modes, df68c3c; wrap PROVEN kernel wall, permanently
    deferred) — propose-walled at HEAD; evacuated for provenance, registered
    WALLED so propose keeps fail-closing (the combine/split precedent).
  * boundary_boss was propose-walled at HEAD (never seat-proven) → DORMANT.
"""

from __future__ import annotations

from typing import Any

from ..com.earlybind import typed, typed_qi
from ..com.sw_type_info import wrapper_module
from ..selection import (
    resolve_manifest_face,
    select_entity,
)
from ..sw_com import get_sw_app
from .verify import materialized as _materialized

# Module-level proven status (kept for back-compat imports; the GREEN handlers
# in this module are dome + wizard_hole).
SPIKE_STATUS = "GREEN"

# Per-feature registry disposition (cut #4 Option A — preserve HEAD behavior).
# dome + wizard_hole were advertised at HEAD (in _SUPPORTED_FEATURE_TYPES).
# loft/rib/wrap/boundary_boss were propose-WALLED at HEAD (absent from
# _SUPPORTED); they relocate here but stay un-advertised so propose still
# fail-closes exactly as at HEAD.
DOME_STATUS = "GREEN"
WIZARD_HOLE_STATUS = "GREEN"
LOFT_STATUS = "WALLED"
RIB_STATUS = "WALLED"
WRAP_STATUS = "WALLED"
BOUNDARY_BOSS_STATUS = "DORMANT"

# swFmHoleWizard — CreateDefinition id for the Hole Wizard.
_SW_FM_HOLE_WZD = 25

# swWzdGeneralHoleTypes_e — the hole-wizard "generic type". LLM-facing names
# map to the integer InitializeHole expects.
_WZD_GENERIC_HOLE_TYPES = {
    "counterbore": 0,
    "countersink": 1,
    "hole": 2,
    "tap": 3,
    "pipe_tap": 4,
    "slot": 6,
}
# swEndConditions_e for the hole's end condition.
_WZD_END_CONDITIONS = {
    "blind": 0,
    "through_all": 1,
    "through_next": 2,
    "up_to_vertex": 3,
    "up_to_surface": 4,
    "offset_from_surface": 5,
}


def _create_loft(doc: Any, feature: dict, target: dict) -> tuple[bool, str | None]:
    """Create a loft (blend) feature from multiple profile sketches.

    Seat-validated (SW 2024 SP1): ``swFmBlend=9`` from ``swconst.tlb``.
    ``CreateDefinition(9)`` returns None without pre-selected profiles.
    Legacy ``InsertProtrusionBlend`` takes **17 args**.

    Pipeline: pre-select profiles → ``CreateDefinition(9)`` →
    ``typed_qi(ILoftFeatureData)`` → ``CreateFeature``.

    SEAT-PENDING (W0): CreateFeature materialization needs seat
    confirmation with correct profile geometry.
    """
    profiles = target.get("profiles") if isinstance(target, dict) else None
    if not isinstance(profiles, list) or len(profiles) < 2:
        return False, "target.profiles must be a list of >=2 sketch names"
    try:
        fm = doc.FeatureManager
        mod = wrapper_module()
        ext = typed(doc.Extension, "IModelDocExtension", module=mod)
        doc.ClearSelection2(True)
        for i, p in enumerate(profiles):
            append = i > 0
            if not ext.SelectByID2(p, "SKETCH", 0, 0, 0, append, 1, None, 0):
                return False, f"could not select profile sketch {p!r}"
        data = fm.CreateDefinition(9)
        if data is None:
            return (
                False,
                "CreateDefinition(9) returned None (profiles may not be compatible)",
            )
        fd = typed_qi(data, "ILoftFeatureData", module=mod)
        # SEAT-PENDING (W0): confirm CreateFeature materializes a loft.
        feat = fm.CreateFeature(fd)
        if _materialized(feat):
            return True, None
        return False, "CreateFeature did not materialize a loft"
    except Exception as exc:
        return False, f"loft pipeline failed: {exc!r}"


def _create_rib(doc: Any, feature: dict, target: dict) -> tuple[bool, str | None]:
    """Create a rib feature from a sketch.

    Seat-validated (SW 2024 SP1): no ``swFmRib`` in ``swconst.tlb``.
    Legacy ``IFeatureManager.InsertRib`` takes **10 args**:
    ``(draftAngle, draftType, draftDir, thickness, normalToSketch,
    refPlaneDir, ribTolerance, ribType, featureScope, autoSelect)``.

    SEAT-PENDING (W0): InsertRib materialization needs seat confirmation
    with correct sketch geometry and arg values.
    """
    sketch = target.get("sketch") if isinstance(target, dict) else None
    if not isinstance(sketch, str) or not sketch:
        return False, "target.sketch must be a non-empty sketch name"
    thickness_mm = (
        feature.get("thickness_mm", 2.0) if isinstance(feature, dict) else 2.0
    )
    thickness_m = float(thickness_mm) / 1000.0
    try:
        mod = wrapper_module()
        ext = typed(doc.Extension, "IModelDocExtension", module=mod)
        doc.ClearSelection2(True)
        if not ext.SelectByID2(sketch, "SKETCH", 0, 0, 0, False, 0, None, 0):
            return False, f"could not select rib sketch {sketch!r}"
        fm = doc.FeatureManager
        # SEAT-PENDING (W0): confirm InsertRib(10) materializes a rib.
        feat = fm.InsertRib(
            0.0,  # draftAngle
            0,  # draftType
            0,  # draftDir
            thickness_m,
            True,  # normalToSketch
            0,  # refPlaneDir
            0,  # ribTolerance
            0,  # ribType (linear)
            True,  # featureScope
            False,  # autoSelect
        )
        if _materialized(feat):
            return True, None
        return False, "InsertRib did not materialize"
    except Exception as exc:
        return False, f"rib pipeline failed: {exc!r}"


def _create_dome(doc: Any, feature: dict, target: dict) -> tuple[bool, str | None]:
    """Create a dome on a selected planar face.

    Seat-validated recipe (W6 T2, spike ``28a5972`` = GREEN, SW 2024 SP1):
    no ``swFmDome`` in ``swconst.tlb``; the legacy ``IModelDoc2.InsertDome``
    (NOT on FeatureManager) takes 3 args ``(Height_m, ReverseDir,
    DoEllipticSurface)``. Two gotchas the seat exposed:

    * **Selection must use mark=1.** ``select_entity(face, mark=1)``; mark=0
      does *not* trigger creation.
    * **``InsertDome`` returns ``None`` even on success.** Do NOT trust the
      return value — verify materialization via a feature-count delta using
      ``len(FeatureManager.GetFeatures(True))`` (NOT ``GetFeatureCount()``,
      which is a property on the late-bound doc and is not callable; the dome
      PAE exposed this). Same pattern as ``_create_shell``.

    ``target`` shapes (durable preferred, mirrors ``ref_point`` / wizard_hole):

    * ``{"face_ref": <manifest-face dict>}`` — resolved through
      :func:`resolve_manifest_face` → :func:`select_entity` (mark=1).
    * ``{"face": [x,y,z]}`` — legacy coordinate pick; **walls out-of-process**
      (``SelectByID2(FACE)`` returns False), retained only as a fallback.

    ``feature.distance_mm`` is the dome height (default 5 mm); optional
    ``feature.reverse`` (bool) and ``feature.elliptical`` (bool).
    """
    distance_mm = feature.get("distance_mm", 5.0) if isinstance(feature, dict) else 5.0
    distance_m = float(distance_mm) / 1000.0
    reverse = (
        bool(feature.get("reverse", False)) if isinstance(feature, dict) else False
    )
    elliptical = (
        bool(feature.get("elliptical", False)) if isinstance(feature, dict) else False
    )
    if not isinstance(target, dict):
        return False, "target must be a dict with 'face_ref' or 'face'"
    doc.ForceRebuild3(False)
    try:
        _feats = doc.FeatureManager.GetFeatures(True)
        before = len(_feats) if _feats else 0
        try:
            doc.ClearSelection2(True)
        except Exception:  # noqa: BLE001
            pass

        face_ref = target.get("face_ref")
        if face_ref is not None:
            res = resolve_manifest_face(doc, face_ref)
            if res.entity is None:
                return False, f"dome face unresolved (method={res.method})"
            # mark=1 is REQUIRED for InsertDome (seat-proven; mark=0 no-ops).
            if not select_entity(res.entity, mark=1):
                return False, "could not select resolved face for dome"
        else:
            face = target.get("face")
            if not isinstance(face, (list, tuple)) or len(face) != 3:
                return (
                    False,
                    "target must contain a 'face_ref' or a 3-element 'face' [x,y,z]",
                )
            mod = wrapper_module()
            ext = typed(doc.Extension, "IModelDocExtension", module=mod)
            if not ext.SelectByID2(
                "",
                "FACE",
                float(face[0]),
                float(face[1]),
                float(face[2]),
                False,
                1,
                None,
                0,
            ):
                return False, "could not select face for dome"

        # InsertDome returns None even on success — verify via feature-count.
        doc.InsertDome(distance_m, reverse, elliptical)
        doc.ForceRebuild3(False)
        _feats = doc.FeatureManager.GetFeatures(True)
        after = len(_feats) if _feats else 0
        if after > before:
            return True, None
        return False, f"dome did not add a feature (count {before} -> {after})"
    except Exception as exc:
        return False, f"dome pipeline failed: {exc!r}"


def _create_wrap(doc: Any, feature: dict, target: dict) -> tuple[bool, str | None]:
    """Create a wrap feature (sketch wrapped onto a face).

    Seat-validated (SW 2024 SP1): no ``swFmWrap`` in ``swconst.tlb``.
    ``IFeatureManager.InsertWrapFeature`` takes **3 args** (legacy).
    ``IFeatureManager.InsertWrapFeature2`` takes **5 args**:
    ``(type, thickness, draftAngle, draftDir, pullDir)``.

    SEAT-PENDING (W0): InsertWrapFeature2 materialization needs seat
    confirmation with correct sketch+face selection.
    """
    sketch = target.get("sketch") if isinstance(target, dict) else None
    if not isinstance(sketch, str) or not sketch:
        return False, "target.sketch must be a non-empty sketch name"
    face = target.get("face") if isinstance(target, dict) else None
    if not isinstance(face, (list, tuple)) or len(face) != 3:
        return False, "target.face must be a 3-element [x,y,z]"
    thickness_mm = (
        feature.get("thickness_mm", 1.0) if isinstance(feature, dict) else 1.0
    )
    thickness_m = float(thickness_mm) / 1000.0
    try:
        mod = wrapper_module()
        ext = typed(doc.Extension, "IModelDocExtension", module=mod)
        doc.ClearSelection2(True)
        if not ext.SelectByID2(sketch, "SKETCH", 0, 0, 0, False, 0, None, 0):
            return False, f"could not select wrap sketch {sketch!r}"
        if not ext.SelectByID2(
            "", "FACE", float(face[0]), float(face[1]), float(face[2]), True, 0, None, 0
        ):
            return False, "could not select face for wrap"
        fm = doc.FeatureManager
        # SEAT-PENDING (W0): confirm InsertWrapFeature2(5) materializes.
        feat = fm.InsertWrapFeature2(
            0,  # type (0=emboss, 1=engrave, 2=scribe)
            thickness_m,
            0.0,  # draftAngle
            False,  # draftDir
            False,  # pullDir
        )
        if _materialized(feat):
            return True, None
        return False, "InsertWrapFeature2 did not materialize"
    except Exception as exc:
        return False, f"wrap pipeline failed: {exc!r}"


def _create_boundary_boss(
    doc: Any, feature: dict, target: dict
) -> tuple[bool, str | None]:
    """Create a boundary boss/base from 2-direction profiles.

    Seat-validated (SW 2024 SP1): **DEFERRED**.
    - No ``swFmBoundaryBoss`` in ``swconst.tlb`` (``swFeatureNameID_e``).
    - No ``InsertBoundaryBoss*`` method on ``IFeatureManager`` or
      ``IModelDoc2`` (probed via ``GetIDsOfNames``).
    - ``swBoundaryBoss*`` enums exist in ``swconst.tlb`` but only for
      sub-parameters (tangency, direction, curve influence), not for
      the feature creation itself.
    Boundary boss creation is not reachable out-of-process via the
    known API surface.
    """
    for key in ("dir1_profiles", "dir2_profiles"):
        val = target.get(key) if isinstance(target, dict) else None
        if not isinstance(val, list) or not val:
            return False, f"target.{key} must be a non-empty list of sketch names"
    return (
        False,
        "boundary_boss: no reachable creation API (DEFERRED — see WAVE5_HANDBACK.md)",
    )


def _arrays_from_out(ret: Any) -> list[list]:
    """Extract the array ([out] SAFEARRAY) elements from an early-bound call's
    return tuple, in order — the bool/scalar retval is ignored."""
    if not isinstance(ret, (tuple, list)):
        return []
    return [list(a) for a in ret if isinstance(a, (tuple, list))]


def _hole_table_sizes(hsd: Any, std_name: str, fastener_index: int) -> list[str]:
    """Valid size strings for a (standard, fastener) from the standards DB."""
    sizes: list[str] = []
    try:
        tt = hsd.GetFastenerTableTypes(std_name, fastener_index)
    except Exception:  # noqa: BLE001
        return sizes
    table_ids = [t for arr in _arrays_from_out(tt) for t in arr]
    table_id = table_ids[0] if table_ids else 0
    try:
        ht = hsd.GetFastenerTable(std_name, fastener_index, table_id)
    except Exception:  # noqa: BLE001
        return sizes
    table_raw = None
    for a in (ht if isinstance(ht, (tuple, list)) else [ht]):
        if a is not None and not isinstance(a, (bool, int, float, str, tuple, list)):
            table_raw = a
            break
    if table_raw is None:
        return sizes
    mod = wrapper_module()
    table = typed_qi(table_raw, "IHoleDataTable", module=mod)
    try:
        cnames = table.GetColumnNames()
    except Exception:  # noqa: BLE001
        return sizes
    cols = [c for arr in _arrays_from_out(cnames) for c in arr]
    size_col = next(
        (c for c in cols if "size" in str(c).lower()), cols[0] if cols else None
    )
    if size_col is None:
        return sizes
    try:
        rc = table.GetRowCount()
    except Exception:  # noqa: BLE001
        return sizes
    # The retval is a bool; the count is the first genuine (non-bool) int.
    counts = [
        v
        for v in (rc if isinstance(rc, (tuple, list)) else [rc])
        if isinstance(v, int) and not isinstance(v, bool)
    ]
    nrows = counts[0] if counts else 0
    for r in range(nrows):
        try:
            cell = table.GetCellData(size_col, r)
        except Exception:  # noqa: BLE001
            continue
        for v in (cell if isinstance(cell, (tuple, list)) else [cell]):
            if isinstance(v, str) and v:
                sizes.append(v)
                break
    return sizes


# Show at most this many size strings in validation error messages; beyond that
# we elide with a count suffix so the dry-run payload stays readable for the
# larger fastener tables (Tap Drills has ~70 entries in the ANSI Metric DB).
_SIZE_ERROR_DISPLAY_LIMIT = 20


def _format_size_catalog(sizes: list[str]) -> str:
    """Format a size list for an error message: full when short, elided with a
    count when long. Always byte-stable — the same input list always produces
    the same output, so downstream tests that assert on substrings stay green.
    """
    if not sizes:
        return "<no sizes enumerated>"
    if len(sizes) <= _SIZE_ERROR_DISPLAY_LIMIT:
        return ", ".join(sizes)
    head = ", ".join(sizes[:_SIZE_ERROR_DISPLAY_LIMIT])
    return f"{head}, ... ({len(sizes)} total)"


def _resolve_hole_args(
    generic_hole_type: int, standard: str, fastener_type: str, size: str
) -> tuple[bool, int, int, str | None]:
    """Resolve (std_index, fastener_index) and validate ``size`` against the
    live standards DB. Returns (ok, std_index, fastener_index, error).

    The Hole Wizard bridges COM to a local standards database; fastener indexes
    are contextual and sizes are exact DB strings (often ``Ø``-prefixed), so we
    query rather than guess (seat-proven by spike_wizhole_v5). The
    ``IHoleStandardsData`` byref [out] arrays require early binding.
    """
    sw = get_sw_app()
    mod = wrapper_module()
    hsd_raw = sw.GetHoleStandardsData(generic_hole_type)
    if hsd_raw is None:
        return False, -1, -1, f"GetHoleStandardsData({generic_hole_type}) returned None"
    hsd = typed_qi(hsd_raw, "IHoleStandardsData", module=mod)

    std_arrays = _arrays_from_out(hsd.GetHoleStandards())
    if len(std_arrays) < 2:
        return False, -1, -1, "GetHoleStandards returned no standards"
    std_indexes, std_names = std_arrays[0], std_arrays[1]
    std_index = None
    for idx, nm in zip(std_indexes, std_names):
        if str(nm).strip().lower() == standard.strip().lower():
            std_index = idx
            std_name = str(nm)
            break
    if std_index is None:
        return (
            False,
            -1,
            -1,
            (
                f"standard {standard!r} not found; available: "
                f"{_format_size_catalog([str(n) for n in std_names])}"
            ),
        )

    f_arrays = _arrays_from_out(hsd.GetFastenerTypes(std_name))
    if len(f_arrays) < 2:
        return False, -1, -1, f"no fastener types for standard {std_name!r}"
    f_indexes, f_names = f_arrays[0], f_arrays[1]
    fastener_index = None
    for idx, nm in zip(f_indexes, f_names):
        if str(nm).strip().lower() == fastener_type.strip().lower():
            fastener_index = idx
            break
    if fastener_index is None:
        return (
            False,
            -1,
            -1,
            (
                f"fastener type {fastener_type!r} not found for {std_name!r}; "
                f"available: {_format_size_catalog([str(n) for n in f_names])}"
            ),
        )

    valid_sizes = _hole_table_sizes(hsd, std_name, fastener_index)
    if not valid_sizes:
        # DB returned zero rows for this (standard, fastener) — either the
        # table is empty or the COM read failed. Surface as a diagnostic
        # error rather than silently accepting any size string; the caller
        # gets a structured envelope they can act on.
        return (
            False,
            -1,
            -1,
            (
                f"no sizes enumerated for {std_name!r}/{fastener_type!r} "
                f"(DB returned 0 rows — check IHoleDataTable.GetRowCount)"
            ),
        )
    if size not in valid_sizes:
        return (
            False,
            -1,
            -1,
            (
                f"size {size!r} invalid for {std_name!r}/{fastener_type!r}; "
                f"{len(valid_sizes)} valid sizes: {_format_size_catalog(valid_sizes)}"
            ),
        )
    return True, int(std_index), int(fastener_index), None


def _create_wizard_hole(
    doc: Any, feature: dict, target: dict
) -> tuple[bool, str | None]:
    """Create a hole-wizard feature at a point on a face.

    Seat-validated recipe (spike_wizhole_v5 = PASS): resolve the DB args, place
    a sketch point at the requested location on the target face, then
    ``CreateDefinition(25) → typed_qi(IWizardHoleFeatureData2) → InitializeHole
    → CreateFeature``.

    Placement supports two ``target`` shapes (durable preferred):

    * **Durable face-ref (C, seat-validated ``spike_wizhole_durable`` = PASS):**
      ``{"face_ref": <manifest-face dict>, "point": [x,y,z]}`` — the face is
      resolved through the persist→fingerprint hierarchy
      (:func:`resolve_manifest_face`) and selected as a live entity, so the
      placement survives rebuilds/topology shuffles. The sketch is built on the
      *resolved* face (proven: ``select_entity`` of the resolved face is a valid
      ``InsertSketch`` base, just like the v1 coordinate pick).
    * **Legacy coordinate (v1):** ``{"face": [x,y,z], "point": [x,y,z]}`` — the
      face is picked by raw model-metre coords via ``SelectByID``.

    ``point`` is the on-face hole location in model metres in both cases.
    Returns (ok, error).
    """
    generic = _WZD_GENERIC_HOLE_TYPES[feature["hole_type"]]
    end_cond = _WZD_END_CONDITIONS[feature.get("end_condition", "blind")]
    ok, std_idx, fast_idx, err = _resolve_hole_args(
        generic, feature["standard"], feature["fastener_type"], feature["size"]
    )
    if not ok:
        return False, err

    mod = wrapper_module()
    doc.ForceRebuild3(False)
    px, py, pz = target["point"]
    try:
        # Select the placement face: durable face-ref first, else legacy coords.
        try:
            doc.ClearSelection2(True)
        except Exception:  # noqa: BLE001
            pass
        face_ref = target.get("face_ref")
        if face_ref is not None:
            res = resolve_manifest_face(doc, face_ref)
            if res.entity is None:
                return False, f"placement face unresolved (method={res.method})"
            if not select_entity(res.entity):
                return False, "could not select resolved placement face"
        else:
            fx, fy, fz = target["face"]
            if not doc.SelectByID("", "FACE", fx, fy, fz):
                return False, f"could not select target face at {target['face']}"
        sk = doc.SketchManager
        sk.InsertSketch(True)
        pt = sk.CreatePoint(px, py, pz)
        sk.InsertSketch(True)
        if pt is None:
            return False, "CreatePoint returned None"

        def _select_point() -> bool:
            try:
                doc.ClearSelection2(True)
            except Exception:  # noqa: BLE001
                pass
            m = getattr(pt, "Select2", None)
            if m is not None:
                try:
                    if m(False, 0):
                        return True
                except Exception:  # noqa: BLE001
                    pass
            return bool(doc.SelectByID("", "SKETCHPOINT", px, py, pz))

        if not _select_point():
            return False, "could not select the placement point"

        fm = doc.FeatureManager
        data = fm.CreateDefinition(_SW_FM_HOLE_WZD)
        fd = typed_qi(data, "IWizardHoleFeatureData2", module=mod)
        fd.InitializeHole(generic, std_idx, fast_idx, feature["size"], end_cond)
        depth_mm = feature.get("depth_mm")
        if depth_mm is not None and hasattr(fd, "Depth"):
            fd.Depth = depth_mm / 1000.0
        _select_point()  # re-assert after InitializeHole
        feat = fm.CreateFeature(data)
        if _materialized(feat):
            return True, None
        return False, "CreateFeature did not materialize"
    except Exception as exc:
        return False, f"wizard-hole pipeline failed: {exc!r}"
