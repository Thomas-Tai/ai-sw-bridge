"""Read-only ``import_diagnostics`` observe lane.

Reports the geometric *health* of a part's bodies — the actionable signals an
operator wants after importing foreign geometry (STEP / IGES) or before trusting
a model: how many solid vs surface bodies, any B-rep topology faults (decoded),
and SOLIDWORKS' own import-diagnosis status flag.

Measure-first reconnaissance (probe_import_diagnostics, live SW2024 SP1,
2026-06-24) settled what the COM endpoints actually yield:

  * ``IModelDoc2.CheckModel`` — DOES NOT EXIST in the SW2024 DLL (the classic
    name; absent like ``CreateEquationCurve2``). The real model-fault API is
    ``IBody2.Check3 -> IFaultEntity`` (``Count``, ``ErrorCode[i]``), and
    ``ErrorCode`` decodes via ``swFaultEntityErrorCode_e``. This is the
    load-bearing, actionable source — ``Count == 0`` on healthy geometry, no
    exceptions; non-zero enumerates real topology corruption.
  * ``IPartDoc.ImportDiagnosis(CloseAllGaps, RemoveFaces, FixFaces, Options)``
    -> Int32 — the 3 bools are REPAIR actions; we call it READ-ONLY with all
    three False. Its Int32 return was INVARIANT (``1``) across healthy native,
    healthy import, and a knit-off import in the probe — i.e. a *status / bodies-
    processed flag*, NOT a fault count. Surfaced as ``import_diagnosis_status``
    with that caveat, never as the primary metric. We NEVER pass a repair flag
    True — that would mutate, and this lane is pure-read.

Body breakdown is the reliable import-quality signal: an import that failed to
knit into a solid leaves SURFACE (sheet) bodies behind — ``surface_body_count``
> 0 is the unstitched-import flag, computable on any part without manufacturing
corrupt geometry.

``clean`` is the single-bool health verdict: solid bodies present, no surface
bodies, and zero Check3 faults.
"""

from __future__ import annotations

from typing import Any

from .sw_com import (
    DOC_TYPE_NAMES,
    SW_DOC_PART,
    get_active_doc,
    get_sw_app,
    resolve,
)

# swFaultEntityErrorCode_e (SW2024 DLL, build 32.1.0.123) — IFaultEntity.ErrorCode
# decode. Codes 1-36; the body/face/edge/shell topology fault taxonomy.
FAULT_CODE_NAMES = {
    1: "swBodyCorrupt", 2: "swBodyInvalidIdentifiers", 3: "swBodyInsideOut",
    4: "swBodyRegionsInconsistent", 5: "swEdgeNonPeriodicCurve",
    6: "swEdgeNonPeriodicNomGeom", 7: "swEdgeVertexNotLie",
    8: "swEdgeVertexNotLieNomGeom", 9: "swEdgeWrongDir",
    10: "swEdgeWrongDirNomGeom", 11: "swEdgeSpcurveOutOfTol",
    12: "swEdgeSpcurveOutOfTolNomGeom", 13: "swEdgeVerticesTouch",
    14: "swEdgeBadFaceOrder", 15: "swEdgeBadWire", 16: "swFaceBadVertex",
    17: "swFaceBadEdge", 18: "swFaceBadEdgeOrder", 19: "swFaceNoAccomVertex",
    20: "swFaceBadLoops", 21: "swFaceSelfIntersecting", 22: "swFaceBadWireframe",
    23: "swFaceCheckerFailure", 24: "swFaceFaceInconsistency",
    25: "swGeomStateSelfIntersect", 26: "swGeomDegenerate",
    27: "swRegionBadShells", 28: "swShellBadTopologyGeometry",
    29: "swShellIntersect", 30: "swTopolNotG1Continuous",
    31: "swTopolSizeBoxViolation", 32: "swTopolStateCheckFail",
    33: "swTopolStateNoGeometry", 34: "swEntityStateInvalid",
    35: "swTopolMissingGeometry", 36: "swEdgeTouchEdge",
}

# swBodyType_e
_SW_SOLID_BODY = 0
_SW_SHEET_BODY = 1


def _fault_code_name(code: Any) -> str:
    """Decode a raw ErrorCode int to its swFaultEntityErrorCode_e name."""
    try:
        return FAULT_CODE_NAMES.get(int(code), f"unknown_code_{code}")
    except (TypeError, ValueError):
        return f"unknown_code_{code}"


def _read_error_code(fault: Any, index: int) -> Any:
    """IFaultEntity.ErrorCode[index] — an indexed property. Late-bound it may
    resolve as a callable (``ErrorCode(i)``) or a subscriptable; try both."""
    try:
        return fault.ErrorCode(index)
    except Exception:
        try:
            return fault.ErrorCode[index]
        except Exception:
            return None


def _check_body(body: Any, body_kind: str, errors: list) -> dict[str, Any]:
    """Run IBody2.Check3 -> IFaultEntity on one body; return its fault summary."""
    entry: dict[str, Any] = {"body_kind": body_kind, "fault_count": 0, "codes": []}
    try:
        fault = resolve(body, "Check3")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Check3({body_kind}): {exc!r}")
        entry["fault_count"] = None
        return entry
    if fault is None:
        return entry
    try:
        cnt = int(resolve(fault, "Count"))
    except Exception as exc:  # noqa: BLE001
        errors.append(f"FaultEntity.Count({body_kind}): {exc!r}")
        entry["fault_count"] = None
        return entry
    entry["fault_count"] = cnt
    for i in range(cnt):
        entry["codes"].append(_fault_code_name(_read_error_code(fault, i)))
    return entry


def _sw_get_import_diagnostics_impl() -> dict[str, Any]:
    """v1 core — geometric health diagnostics for the active part.

    Keys:
      ``solid_body_count`` / ``surface_body_count`` / ``total_body_count`` —
        body breakdown (surface bodies = unstitched/incomplete-import flag).
      ``total_fault_count`` — sum of IBody2.Check3 faults across all bodies.
      ``faults_by_code`` — ``{swFaultEntityErrorCode_e name: count}`` aggregate.
      ``per_body`` — per-body ``{body_kind, fault_count, codes}``.
      ``import_diagnosis_status`` — IPartDoc.ImportDiagnosis(all-False) Int32
        (a status flag, NOT a fault count — see module docstring).
      ``clean`` — bool: solid bodies present, no surface bodies, zero faults.

    Parts only (assemblies/drawings rejected). Fail-soft: per-read failures land
    in ``errors``; the load-bearing witness is the body-count read.
    """
    result: dict[str, Any] = {
        "ok": False,
        "doc_path": None,
        "solid_body_count": None,
        "surface_body_count": None,
        "total_body_count": None,
        "total_fault_count": None,
        "faults_by_code": None,
        "per_body": None,
        "import_diagnosis_status": None,
        "clean": None,
        "error": None,
        "errors": [],
    }
    try:
        sw = get_sw_app()
        doc = get_active_doc(sw)
        if doc is None:
            result["error"] = "no_active_doc"
            return result
        try:
            result["doc_path"] = str(resolve(doc, "GetPathName"))
        except Exception:
            pass

        try:
            doc_type = int(resolve(doc, "GetType"))
        except Exception as exc:
            result["error"] = f"GetType failed: {exc!r}"
            return result
        if doc_type != SW_DOC_PART:
            result["error"] = (
                f"import_diagnostics requires a part (swDocPART={SW_DOC_PART}); "
                f"active doc is type {doc_type} ({DOC_TYPE_NAMES.get(doc_type)})"
            )
            return result

        # Body breakdown — the load-bearing read.
        try:
            solids = doc.GetBodies2(_SW_SOLID_BODY, False) or ()
            sheets = doc.GetBodies2(_SW_SHEET_BODY, False) or ()
        except Exception as exc:
            result["error"] = f"GetBodies2 failed: {exc!r}"
            return result
        solids = list(solids)
        sheets = list(sheets)
        result["solid_body_count"] = len(solids)
        result["surface_body_count"] = len(sheets)
        result["total_body_count"] = len(solids) + len(sheets)

        # Per-body Check3 fault enumeration.
        per_body: list[dict[str, Any]] = []
        by_code: dict[str, int] = {}
        total_faults = 0
        check_read_ok = True
        for body in solids:
            entry = _check_body(body, "solid", result["errors"])
            per_body.append(entry)
        for body in sheets:
            entry = _check_body(body, "surface", result["errors"])
            per_body.append(entry)
        for entry in per_body:
            fc = entry.get("fault_count")
            if fc is None:
                check_read_ok = False
                continue
            total_faults += fc
            for name in entry["codes"]:
                by_code[name] = by_code.get(name, 0) + 1
        result["per_body"] = per_body
        result["faults_by_code"] = by_code
        result["total_fault_count"] = total_faults if check_read_ok else None

        # ImportDiagnosis — READ-ONLY (all repair flags False). Status flag only.
        try:
            status = doc.ImportDiagnosis(False, False, False, 0)
            result["import_diagnosis_status"] = int(status) if status is not None else None
        except Exception as exc:  # noqa: BLE001
            result["errors"].append(f"ImportDiagnosis: {exc!r}")

        # clean verdict: a healthy solid part with no faults and no stray sheets.
        if check_read_ok:
            result["clean"] = (
                total_faults == 0
                and result["surface_body_count"] == 0
                and result["solid_body_count"] > 0
            )

        # ok when the load-bearing body breakdown read succeeded.
        result["ok"] = result["solid_body_count"] is not None
        return result
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"dispatch failed: {exc!r}"
        return result
