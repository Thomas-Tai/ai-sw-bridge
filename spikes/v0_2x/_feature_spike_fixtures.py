"""W0-owned seat fixtures for the W62 Curves-group derisk spikes (LIVE seat only).

Provides a solid-body B-rep target + per-lane seeds so the four feature_add
spikes are UNIFORM and topologically sound — projection/split/intersection need
real geometry, never an abstract plane.

  build_block(sw) -> doc ............ 40x30x10 mm boss-extrude archetype (hem pattern)
  seed_circle_sketch(doc) -> name ... Ø10 mm circle sketch on the top face (helix base)
  seed_line_over_top(doc) -> (name, face) .. Front-plane line that projects +Z onto
                                              the top face (split_line / project_curve)
  top_face_edges(doc, n) -> [edges] . connected top-face edges (composite)
  save_and_reopen(sw, doc) -> doc ... proven typed-OpenDoc6 reopen for survival checks

Applies the W60 fixture lessons PROACTIVELY (these bit us once already):
  * plane / sketch selection via FeatureByName(...).Select2 — NOT
    Extension.SelectByID2 with a bare None ICallout (that marshals to
    com_error -2147352571 "Type mismatch").
  * FACE selection: a face is not a named feature, so SelectByID2 is required —
    but the ICallout MUST be VARIANT(VT_DISPATCH, None), never a bare None.
  * IFace2.GetEdges is a late-bound PROPERTY (returns the tuple) — no parens.
  * a seed sketch must carry >= 1 entity: SW culls an EMPTY sketch on close.
Deterministic naming: build_block consumes Sketch1, so the next sketch is
"Sketch2". Geometry params are W0-tunable on the seat.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

import pythoncom
from win32com.client import VARIANT

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = str(_REPO_ROOT / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

PART_TEMPLATE = r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\Part.PRTDOT"
_BLIND = 0  # swEndConditions_e.swEndCondBlind
_TOP_Z = 0.010  # top face of the 10 mm block, in metres


def _null_disp() -> Any:
    """ICallout null as a typed VARIANT (the edge_flange/hem recipe)."""
    return VARIANT(pythoncom.VT_DISPATCH, None)


def connect() -> Any:
    from ai_sw_bridge.sw_com import get_sw_app

    sw = get_sw_app()
    if sw is None:
        raise RuntimeError("get_sw_app() returned None — start SOLIDWORKS first")
    return sw


def _new_part(sw: Any) -> Any:
    doc = sw.NewDocument(PART_TEMPLATE, 0, 0, 0)
    if doc is None:
        raise RuntimeError(f"NewDocument returned None (template {PART_TEMPLATE!r})")
    return doc


def _select_feature(doc: Any, name: str, append: bool = False) -> Any:
    feat = doc.FeatureByName(name)
    if feat is None:
        raise RuntimeError(f"FeatureByName({name!r}) returned None")
    feat.Select2(append, 0)
    return feat


def build_block(sw: Any) -> Any:
    """40x30x10 mm solid box (Boss-Extrude1, consumes Sketch1). Returns the RAW
    late-bound doc the handlers consume."""
    doc = _new_part(sw)
    _select_feature(doc, "Front Plane")
    doc.SketchManager.InsertSketch(True)
    doc.SketchManager.CreateCornerRectangle(-0.020, -0.015, 0.0, 0.020, 0.015, 0.0)
    doc.SketchManager.InsertSketch(True)  # close Sketch1
    doc.ClearSelection2(True)
    _select_feature(doc, "Sketch1")
    doc.FeatureManager.FeatureExtrusion2(
        True, False, False, _BLIND, 0,
        0.010, 0.0, False, False, False, False,
        0.0, 0.0, False, False, False, False,
        True, True, True, 0, 0.0, False,
    )
    doc.ClearSelection2(True)
    return doc


def top_face(doc: Any) -> Any:
    """Select + return the live top IFace2 (z = +10 mm). Leaves it deselected."""
    doc.Extension.SelectByID2("", "FACE", 0.0, 0.0, _TOP_Z, False, 0, _null_disp(), 0)
    face = doc.SelectionManager.GetSelectedObject6(1, -1)
    doc.ClearSelection2(True)
    if face is None:
        raise RuntimeError("could not select the block top face")
    return face


def seed_circle_sketch(doc: Any) -> str:
    """Ø10 mm circle sketch on the top face -> persists as ``Sketch2``. Returns the
    sketch name; the helix handler selects it as the base profile."""
    face = top_face(doc)
    face.Select2(False, 0)
    doc.SketchManager.InsertSketch(True)  # open a sketch on the top face
    doc.SketchManager.CreateCircle(0.0, 0.0, 0.0, 0.005, 0.0, 0.0)  # in-plane coords
    doc.SketchManager.InsertSketch(True)  # close (non-empty -> persists)
    doc.ClearSelection2(True)
    return "Sketch2"


def seed_line_over_top(doc: Any) -> tuple[str, Any]:
    """A Front-plane line at y = +5 mm that projects (+Z) onto the top face.
    Returns ``(sketch_name, live_top_face)`` for split_line / project_curve."""
    _select_feature(doc, "Front Plane")
    doc.SketchManager.InsertSketch(True)
    doc.SketchManager.CreateLine(-0.025, 0.005, 0.0, 0.025, 0.005, 0.0)
    doc.SketchManager.InsertSketch(True)  # close
    doc.ClearSelection2(True)
    return "Sketch2", top_face(doc)


def top_face_edges(doc: Any, n: int = 2) -> list[Any]:
    """First ``n`` edges of the top face (live), for the composite-curve chain.
    GetEdges is a late-bound PROPERTY -> no parens."""
    face = top_face(doc)
    edges = list(face.GetEdges)
    if len(edges) < n:
        raise RuntimeError(f"top face has {len(edges)} edges, need {n}")
    return edges[:n]


def count_feature_nodes(doc: Any) -> int:
    """Headless-reliable feature-node count for the W62 verify gate.

    ``IModelDoc2.FirstFeature`` is unreachable on the raw late-bound doc
    (com_error -2147352573 "Member not found" on both raw and typed access).
    ``IFeatureManager.GetFeatures(False)`` IS reachable on the seat (probe
    returned 25 features on a fresh block), so it is the verify substrate
    for every W62 lane that gates on a feature-node delta (composite, helix,
    project_curve). split_line gates on ΔFace and does not need this.
    """
    feats = doc.FeatureManager.GetFeatures(False)
    if feats is None:
        return 0
    return len(feats)


def save_and_reopen(sw: Any, doc: Any) -> Any:
    """Save -> close-all -> reopen via the proven typed-OpenDoc6 recipe
    (spike_hem_v5). Returns the reopened RAW doc so the caller can re-measure."""
    from ai_sw_bridge.com.earlybind import typed
    from ai_sw_bridge.com.sw_type_info import wrapper_module

    mod = wrapper_module()
    tmp = tempfile.mktemp(suffix=".SLDPRT")
    doc.SaveAs3(tmp, 0, 2)
    sw.CloseAllDocuments(True)

    tsw = typed(sw, "ISldWorks", module=mod)
    tsw.OpenDoc6(tmp, 1, 1, "", 0, 0)
    doc2 = sw.ActiveDoc
    if doc2 is None:
        raise RuntimeError("ActiveDoc None after OpenDoc6 reopen")
    try:
        doc2.ForceRebuild3(False)
    except Exception:
        pass
    return doc2
