"""Shared seat-fixture helpers for the W60 sketch-editing derisk spikes.

W0-OWNED. Each lane's spike (`spike_sketch_<offset|convert|trim|pattern>.py`)
imports from here so the four spikes are UNIFORM and TRUSTWORTHY — no
hand-rolled sketch sequences (the W35/W37 0-segment footgun, where a bad
sequence yields an empty sketch and a bogus PASS/NO_OP) and no reinvented
durable-ref capture. Runs on the LIVE seat only (every recipe here is COM).

Design invariants (all copied from PROVEN spikes, cited inline):
  * Builds return the RAW late-bound doc that ``apply_sketch_edit`` expects —
    on the raw doc ``GetActiveSketch2`` / ``GetSketchSegments`` auto-invoke as
    properties (sketch_relations_pae.py:47-58).
  * Sketch names are DETERMINISTIC for a fresh part: the first sketch is
    ``"Sketch1"``; after an extrude consumes it, the next sketch is
    ``"Sketch2"``. The fixtures rely on this so the orchestrator can reopen by
    name.
  * Coordinates are in METRES (SW API unit); helpers take/return metres.

Recipe provenance:
  - connect / template / NewDocument …… sketch_relations_pae.py:39-44
  - InsertSketch toggle + re-select …… spike_a_extrude.py:68-81
  - FeatureExtrusion2 (23-arg boss) …… spike_a_extrude.py:97-121
  - durable-ref capture …………………… selection.live.capture_persist_id + DurableEdgeRef
  - save / typed-OpenDoc6 / reopen …… spike_hem_v5.py:70-121
"""

from __future__ import annotations

import math
import sys
import tempfile
from pathlib import Path
from typing import Any

import pythoncom
from win32com.client import VARIANT

# Path bootstrap: make `ai_sw_bridge` importable when this is run as a script
# from spikes/v0_2x (mirrors sketch_relations_pae.py:35-36).
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = str(_REPO_ROOT / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

PART_TEMPLATE = r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\Part.PRTDOT"
_SW_END_COND_BLIND = 0  # swEndConditions_e.swEndCondBlind


# ---------------------------------------------------------------------------
# Connection + document
# ---------------------------------------------------------------------------


def connect() -> Any:
    """Return the live RAW SW app (``get_sw_app``). Raises if no seat."""
    from ai_sw_bridge.sw_com import get_sw_app

    sw = get_sw_app()
    if sw is None:
        raise RuntimeError("get_sw_app() returned None — start SOLIDWORKS first")
    return sw


def new_part(sw: Any) -> Any:
    """New blank part. Returns the RAW late-bound IModelDoc2 (what the
    production ``apply_sketch_edit`` consumes)."""
    doc = sw.NewDocument(PART_TEMPLATE, 0, 0, 0)
    if doc is None:
        raise RuntimeError(f"NewDocument returned None (template {PART_TEMPLATE!r})")
    return doc


# ---------------------------------------------------------------------------
# Sketch primitives (the proven open/close toggle)
# ---------------------------------------------------------------------------


def _open_sketch_on_plane(doc: Any, plane: str = "Front Plane") -> None:
    # Proven path: FeatureByName -> Select2 (mirrors _base.open_sketch_for_edit).
    # Avoids SelectByID2's ICallout VT_DISPATCH null-marshaling trap (a bare
    # Python None -> com_error "Type mismatch" -2147352571).
    feat = doc.FeatureByName(plane)
    if feat is None:
        raise RuntimeError(f"FeatureByName({plane!r}) returned None")
    feat.Select2(False, 0)
    doc.SketchManager.InsertSketch(True)


def _close_sketch(doc: Any) -> None:
    doc.SketchManager.InsertSketch(True)
    try:
        doc.ClearSelection2(True)
    except Exception:
        pass
    try:
        doc.EditRebuild3
    except Exception:
        pass


def build_rect_sketch(doc: Any, plane: str = "Front Plane") -> tuple[str, int]:
    """40×30 mm corner rectangle → closed ``Sketch1`` (4 segments).

    For the OFFSET lane: offset entities ``[0,1,2,3]`` (chain) expands the loop.
    """
    _open_sketch_on_plane(doc, plane)
    doc.SketchManager.CreateCornerRectangle(-0.020, -0.015, 0.0, 0.020, 0.015, 0.0)
    _close_sketch(doc)
    return "Sketch1", 4


def build_circle_sketch(doc: Any, plane: str = "Front Plane") -> tuple[str, int]:
    """One Ø10 mm circle → closed ``Sketch1`` (1 segment).

    For the PATTERN lane: a 3×1 linear pattern of entity ``[0]`` adds 2 copies.
    """
    _open_sketch_on_plane(doc, plane)
    doc.SketchManager.CreateCircle(0.0, 0.0, 0.0, 0.005, 0.0, 0.0)
    _close_sketch(doc)
    return "Sketch1", 1


def build_overhang_lines_sketch(
    doc: Any, plane: str = "Front Plane"
) -> tuple[str, int, tuple[float, float, float]]:
    """Horizontal bar crossed by TWO verticals -> closed ``Sketch1`` (3
    segments). Returns ``(name, seg_count, pick_xyz)`` where ``pick_xyz`` is the
    MIDPOINT of the horizontal, between the two verticals.

    For the TRIM lane: ``swSketchTrimClosest`` at the midpoint deletes the
    interior piece of the horizontal bounded by the two intersections and SPLITS
    the bar into two disconnected stubs -> 3 -> 4 segments (delta +1). A dangling
    overhang would only SHORTEN a line (delta 0) and could never prove the
    count-delta contract; an interior bounded segment forces the kernel to add a
    stub. (Name kept for spike-compat; geometry is a cross, not an overhang.)
    """
    _open_sketch_on_plane(doc, plane)
    sm = doc.SketchManager
    sm.CreateLine(-0.020, 0.000, 0.0, 0.020, 0.000, 0.0)   # horizontal bar H, y=0
    sm.CreateLine(-0.010, -0.010, 0.0, -0.010, 0.010, 0.0)  # vertical V1 at x=-10mm
    sm.CreateLine(0.010, -0.010, 0.0, 0.010, 0.010, 0.0)    # vertical V2 at x=+10mm
    _close_sketch(doc)
    pick_xyz = (0.005, 0.000, 0.0)  # on H, between V1(-10) and V2(+10), 5mm clear of origin
    return "Sketch1", 3, pick_xyz


def build_mirror_seed_sketch(
    doc: Any, plane: str = "Front Plane"
) -> tuple[str, int, list[int], int]:
    """A vertical construction CENTERLINE on the Y axis + an L of two lines on
    the +X side -> closed ``Sketch1`` (3 segments). Returns
    ``(name, seg_count, mirror_entity_indices, centerline_index)``.

    For the MIRROR lane (W61): mirroring the two +X lines about the centerline
    adds two -X copies -> 3 -> 5 (delta +2). Segment order from
    GetSketchSegments is creation order: [centerline(0), h-line(1), v-line(2)].
    CreateCenterLine + IModelDoc2.SketchMirror both DLL-verified (SW2024 v32).
    """
    _open_sketch_on_plane(doc, plane)
    sm = doc.SketchManager
    sm.CreateCenterLine(0.0, -0.020, 0.0, 0.0, 0.020, 0.0)  # vertical centerline on Y
    sm.CreateLine(0.005, 0.000, 0.0, 0.015, 0.000, 0.0)     # +X horizontal
    sm.CreateLine(0.015, 0.000, 0.0, 0.015, 0.010, 0.0)     # +X vertical (forms an L)
    _close_sketch(doc)
    return "Sketch1", 3, [1, 2], 0


def build_box_top_sketch(doc: Any) -> tuple[str, Any]:
    """Extrude a 40×30×10 mm box (consumes ``Sketch1`` → Boss-Extrude1), then
    open an EMPTY sketch on the top face → ``Sketch2``. Returns
    ``(sketch_name, top_perimeter_edge)`` — a model edge lying in the Sketch2
    plane, ready to Convert (projects → +1 segment).

    For the CONVERT lane. The returned edge is what the spike feeds to
    ``capture_edge_ref`` to build the durable ref param.
    """
    # rectangle on Front, boss-extrude 10 mm (spike_a_extrude.py:97-121)
    _open_sketch_on_plane(doc, "Front Plane")
    doc.SketchManager.CreateCornerRectangle(-0.020, -0.015, 0.0, 0.020, 0.015, 0.0)
    doc.SketchManager.InsertSketch(True)  # close Sketch1
    doc.ClearSelection2(True)
    _sk_feat = doc.FeatureByName("Sketch1")  # sketch is a feature -> FeatureByName, not SelectByID2 (None-callout trap)
    _sk_feat.Select2(False, 0)
    fm = doc.FeatureManager
    fm.FeatureExtrusion2(
        True, False, False, _SW_END_COND_BLIND, 0,
        0.010, 0.0, False, False, False, False,
        0.0, 0.0, False, False, False, False,
        True, True, True, 0, 0.0, False,
    )
    doc.ClearSelection2(True)

    # select the top face (z = +10 mm), grab an edge, open Sketch2 on it
    top_z = 0.010
    # a face is NOT a named feature -> SelectByID2, but pass the ICallout as a
    # null VARIANT(VT_DISPATCH) (hem/edge_flange recipe), never a bare None.
    null_disp = VARIANT(pythoncom.VT_DISPATCH, None)
    doc.Extension.SelectByID2("", "FACE", 0.0, 0.0, top_z, False, 0, null_disp, 0)
    swsel = doc.SelectionManager
    face = swsel.GetSelectedObject6(1, -1)
    if face is None:
        raise RuntimeError("could not select the top face of the box fixture")
    edges = list(face.GetEdges)  # GetEdges is a late-bound PROPERTY (returns the tuple) -> no parens
    if not edges:
        raise RuntimeError("top face has no edges to convert")
    edge = edges[0]
    # open a sketch on the still-selected top face and SEED it with one short
    # line so the feature PERSISTS as Sketch2 (SW culls an EMPTY sketch on close,
    # so the orchestrator's reopen-by-name would miss it). Convert then projects
    # the perimeter edge as a SECOND segment (before=1, after=2).
    doc.SketchManager.InsertSketch(True)
    doc.SketchManager.CreateLine(-0.018, -0.013, 0.0, -0.014, -0.013, 0.0)  # seed (in-plane z=0)
    _close_sketch(doc)
    return "Sketch2", edge


# ---------------------------------------------------------------------------
# Durable edge-ref capture (convert lane)
# ---------------------------------------------------------------------------


def capture_edge_ref(doc: Any, edge: Any) -> dict[str, Any]:
    """Capture a live IEdge as a JSON-able ``DurableEdgeRef`` dict (what the
    ``sketch_convert`` op's ``refs`` param accepts).

    Uses ``selection.live.capture_persist_id`` for the persist token (v1
    resolves by token only) plus the edge endpoints for the human-readable /
    fingerprint geometry the dataclass requires.
    """
    from ai_sw_bridge.selection.live import capture_persist_id
    from ai_sw_bridge.selection._edge_ref import DurableEdgeRef

    pid = capture_persist_id(doc, edge)

    def _vert_point(getter_name: str) -> tuple[float, float, float]:
        try:
            v = getattr(edge, getter_name)()
            if v is None:
                return (0.0, 0.0, 0.0)
            p = v.GetPoint()
            return (float(p[0]), float(p[1]), float(p[2]))
        except Exception:
            return (0.0, 0.0, 0.0)

    start = _vert_point("GetStartVertex")
    end = _vert_point("GetEndVertex")
    length = math.dist(start, end)
    ref = DurableEdgeRef(persist_id=pid, start=start, end=end, length=length)
    return ref.to_dict()


# ---------------------------------------------------------------------------
# Verify helpers: segment count + save/reopen survival
# ---------------------------------------------------------------------------


def count_named_segments(doc: Any, sketch_name: str) -> int:
    """Open the named sketch, count its segments, close. Dogfoods the
    production ``_base`` helpers so the spike measures what the op measures."""
    from ai_sw_bridge.spec.sketch_editing._base import (
        close_sketch,
        count_segments,
        open_sketch_for_edit,
    )

    open_sketch_for_edit(doc, sketch_name)
    sk = doc.GetActiveSketch2
    n = count_segments(sk)
    close_sketch(doc)
    return n


def save_and_reopen(sw: Any, doc: Any) -> Any:
    """Save → close-all → reopen via the PROVEN typed-``OpenDoc6`` recipe
    (spike_hem_v5.py:84-101). Returns the reopened RAW doc (``sw.ActiveDoc``),
    so the caller can ``count_named_segments`` to prove the edit persisted.
    """
    from ai_sw_bridge.com.earlybind import typed
    from ai_sw_bridge.com.sw_type_info import wrapper_module

    mod = wrapper_module()
    tmp = tempfile.mktemp(suffix=".SLDPRT")
    doc.SaveAs3(tmp, 0, 2)
    sw.CloseAllDocuments(True)

    tsw = typed(sw, "ISldWorks", module=mod)
    tsw.OpenDoc6(tmp, 1, 1, "", 0, 0)  # Type=1 swDocPART, Options=1, [out] as 0
    doc2 = sw.ActiveDoc  # dynamic flavor — matches in-session property reads
    if doc2 is None:
        raise RuntimeError("ActiveDoc None after OpenDoc6 reopen")
    try:
        doc2.ForceRebuild3(False)
    except Exception:
        pass
    return doc2
