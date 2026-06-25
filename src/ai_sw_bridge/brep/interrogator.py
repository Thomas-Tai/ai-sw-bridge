"""B-rep interrogator — per-feature topology extraction (spec.md §2.2).

After a feature handler returns an ``IFeature`` handle, ``interrogate``
walks the resulting bodies/faces and produces a structured dict
describing the feature's topology: per-face bounding box, unit normal,
centroid, area, body-id, and a role hint derived from the normal.

E2.1 spike load-bearing findings baked in:

* Under pywin32 late binding, zero-arg IFace2 methods (``GetBox``,
  ``Normal``, ``GetArea``) are already invoked on attribute access —
  calling them with parens raises ``TypeError: 'tuple' object is not
  callable``. All reads below use property access.
* ``IEntity.GetSelectByIDString()`` is unreachable on the IFace2
  dispatch proxy returned via ``IFeature.GetFaces()`` (out-of-process
  marshaler limitation). Workaround: synthesize a session-scoped
  ``temp_id`` from ``"body{body_id}_face{face_idx}"``; downstream
  face_role resolution uses the role_hint + fingerprint instead.

Gated by ``flags.brep_interrogation`` (default OFF). When the flag is
OFF, ``interrogate`` returns ``None`` without touching COM.
"""

from __future__ import annotations

import base64
import logging
import math
import time
from dataclasses import dataclass
from typing import Any, Optional

from ..com.earlybind import EarlyBindError, read_persist_reference, typed_qi
from ..flags import resolve as resolve_flags
from ..telemetry import histogram as telemetry_histogram
from .surface_eval import evaluate_surface_at_uv, get_surface_parameter_range

logger = logging.getLogger("ai_sw_bridge.brep.interrogator")

# Alignment tolerance for axis-aligned role-hint heuristic (spec §2.3).
_AXIS_TOLERANCE = 1e-6


@dataclass(frozen=True)
class BrepFace:
    """One face's topological fingerprint payload.

    ``temp_id`` is session-scoped only — never written to the manifest.
    ``fingerprint`` is assigned by the fingerprint module (E2.3), not
    the interrogator; it's left empty here and populated in the
    manifest serializer.
    """

    face_idx: int
    body_id: int
    temp_id: str
    normal_vec: tuple[float, float, float]
    centroid: tuple[float, float, float]
    bbox: tuple[tuple[float, float, float], tuple[float, float, float]]
    area_mm2: float
    role_hint: str
    fingerprint: str = ""
    is_surface: bool = False
    is_hidden: bool = False
    persist_id: str = ""  # base64url (no pad) durable token; "" when uncaptured
    surface_uv: dict | None = (
        None  # Wave-5 E2: {point_mm, normal} at UV midpoint; None when not evaluated
    )

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable form for the manifest brep block.

        ``persist_id`` is included only when a token was captured (the
        ``persist_capture`` flag was on and the read succeeded); it is omitted
        otherwise so the manifest stays byte-identical to the no-capture case.
        ``surface_uv`` is included only when surface evaluation succeeded.
        """
        out: dict[str, Any] = {
            "face_idx": self.face_idx,
            "body_id": self.body_id,
            "temp_id": self.temp_id,
            "normal": list(self.normal_vec),
            "centroid": list(self.centroid),
            "bbox": [list(self.bbox[0]), list(self.bbox[1])],
            "area_mm2": self.area_mm2,
            "role_hint": self.role_hint,
            "fingerprint": self.fingerprint,
            "is_surface": self.is_surface,
            "is_hidden": self.is_hidden,
        }
        if self.persist_id:
            out["persist_id"] = self.persist_id
        if self.surface_uv and self.surface_uv.get("ok"):
            out["surface_uv"] = {
                "point_mm": self.surface_uv["point_mm"],
                "normal": self.surface_uv["normal"],
            }
        return out


@dataclass(frozen=True)
class BrepEdge:
    """One edge's durable-selection payload (Phase-0 edge capture).

    Captured only when the ``persist_capture`` flag is on — edges exist in the
    manifest solely to anchor durable references (e.g. a fillet on a specific
    edge), so unlike faces they are not part of the always-on interrogation.

    Endpoints come from ``IEdge.GetCurveParams2`` (the late-bind-friendly source;
    ``GetStartVertex``/``GetEndVertex`` throw ``com_error`` on SW 2024 SP1 — see
    ``spike_edge_persist``). ``length`` and ``midpoint`` prefer the *true* curve
    arc length (``ICurve.GetLength``) and curve midpoint (``ICurve.Evaluate`` at
    the parametric midpoint) when those COM reads succeed; they fall back to
    chord length / chord midpoint when they don't (straight edges, degenerate
    curves, unreachable vtable). ``curve_mid_source`` records which path fired
    so downstream consumers — and the edge-match predicate's forward-correct
    gates — can tell the two apart. See ``_edge_match.py`` for why the
    predicate is written to consume these fields unchanged under either regime.
    """

    edge_idx: int
    body_id: int
    start: tuple[float, float, float]
    end: tuple[float, float, float]
    length: float
    midpoint: tuple[float, float, float]
    persist_id: str = ""  # base64url (no pad) durable token; "" when uncaptured
    curve_mid_source: str = "chord"  # "curve" when true curve eval succeeded

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "edge_idx": self.edge_idx,
            "body_id": self.body_id,
            "start": list(self.start),
            "end": list(self.end),
            "length": self.length,
            "midpoint": list(self.midpoint),
            "curve_mid_source": self.curve_mid_source,
        }
        if self.persist_id:
            out["persist_id"] = self.persist_id
        return out


def interrogate(feature: Any, ctx: Any = None) -> Optional[dict[str, Any]]:
    """Run the L1 interrogation algorithm on a built feature.

    Returns a dict shaped ``{"feature": str, "faces": [BrepFace.to_dict()]}``
    or ``None`` when the ``brep_interrogation`` flag is OFF.

    Edge cases per spec.md §2.8:

    * Suppressed features (``IFeature.IsSuppressed()`` truthy) skip face
      walking entirely and return ``{"faces": [], "status": "suppressed"}``
      so downstream resolvers see a well-formed brep block instead of
      stale data from before suppression.
    * Hidden faces (``IFace2.IsHidden`` truthy) are still included but
      flagged with ``is_hidden=true`` so the resolver can deprioritize
      them when scoring ``face_role`` candidates.
    * Imported features (``IFeature.GetTypeName2() == "ImportFeature"``)
      have no native face topology accessible via the feature handle;
      the walker falls back to body-level enumeration via
      ``IFeature.GetBody`` if reachable, else returns
      ``{"faces": [], "status": "imported"}``.

    Lazy mode (spec.md §2.11): when ``ctx.referenced_face_roles`` is a
    non-None set, features not referenced by any downstream feature skip
    face walking entirely (``status: "no_downstream_refs"``). Features
    that are referenced have their faces walked normally but only faces
    whose ``role_hint`` matches an entry in the set are included.

    The ``ctx`` parameter carries build state (BuildContext). When it
    exposes a ``referenced_face_roles`` attribute, lazy mode activates.
    """
    flags = resolve_flags()
    if not flags.get("brep_interrogation", False):
        return None

    if _is_suppressed(feature):
        return {
            "feature": _feature_name(feature),
            "faces": [],
            "status": "suppressed",
        }

    is_import = _is_import_feature(feature)

    # Lazy mode (spec.md §2.11): extract the referenced-face set from ctx.
    referenced_face_roles: Optional[set] = None
    if ctx is not None:
        referenced_face_roles = getattr(ctx, "referenced_face_roles", None)

    feat_name = _feature_name(feature)
    mode_label = "eager"

    if referenced_face_roles is not None:
        mode_label = "lazy"
        roles_for_feature = {
            role for (name, role) in referenced_face_roles if name == feat_name
        }
        if not roles_for_feature:
            t0 = time.perf_counter()
            elapsed = time.perf_counter() - t0
            try:
                telemetry_histogram("brep_interrogation_seconds", elapsed, mode="lazy")
            except Exception:
                pass
            return {
                "feature": feat_name,
                "faces": [],
                "status": "no_downstream_refs",
            }

    # Phase-0 durable-selection capture: read per-face persist tokens when the
    # persist_capture flag is on and the live doc is reachable via ctx. Gated
    # separately from interrogation because it adds a COM read per face (hybrid
    # early binding). Fail-soft per face — a token that won't read stays "".
    capture = bool(flags.get("persist_capture", False))
    doc = getattr(ctx, "doc", None) if ctx is not None else None

    t0 = time.perf_counter()
    try:
        faces = _walk_faces(
            feature, force_body_walk=is_import, doc=doc, capture=capture
        )
    except Exception as e:
        logger.warning("brep interrogation failed: %s", e)
        return {"feature": feat_name, "faces": [], "error": str(e)}
    elapsed = time.perf_counter() - t0
    try:
        telemetry_histogram("brep_interrogation_seconds", elapsed, mode=mode_label)
    except Exception:
        pass

    if referenced_face_roles is not None:
        roles_for_feature = {
            role for (name, role) in referenced_face_roles if name == feat_name
        }
        faces = [f for f in faces if f.role_hint in roles_for_feature]

    payload: dict[str, Any] = {
        "feature": feat_name,
        "faces": [f.to_dict() for f in faces],
    }

    # Phase-0 edge capture: only when persist_capture is on and the live doc is
    # reachable (edges exist in the manifest purely to anchor durable refs). The
    # walk is body-scoped via the doc; fail-soft — any failure leaves no edges
    # block, keeping the no-capture manifest byte-identical.
    if capture and doc is not None:
        try:
            edges = _walk_edges(doc, capture=capture)
            if edges:
                payload["edges"] = [e.to_dict() for e in edges]
        except Exception as e:  # noqa: BLE001
            logger.warning("brep edge capture failed: %s", e)

    if is_import and not faces:
        payload["status"] = "imported"
    return payload


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _feature_name(feature: Any) -> str:
    try:
        return feature.Name or "unknown"
    except Exception:
        return "unknown"


def _walk_faces(
    feature: Any,
    *,
    force_body_walk: bool = False,
    doc: Any = None,
    capture: bool = False,
) -> list[BrepFace]:
    """Walk bodies → faces. Falls back to feature.GetFaces when bodies
    aren't reachable on the dispatch proxy.

    ``force_body_walk`` skips ``IFeature.GetFaces`` entirely — used for
    ImportFeature where the feature handle doesn't carry native face
    topology and the only path is via ``IFeature.GetBody``.

    ``doc``/``capture`` carry the Phase-0 durable-selection capture: when
    ``capture`` is true and ``doc`` is the live model doc, each probed face
    also gets its ``GetPersistReference3`` token read (fail-soft per face).
    """
    faces: list[BrepFace] = []

    if not force_body_walk:
        # Preferred path: IFeature.GetFaces() returns a SAFEARRAY
        # marshaled as a tuple under late binding. Treat it as the fast
        # path; if it raises or returns empty, fall back to body walk.
        direct = _try_feature_getfaces(feature)
        if direct:
            for idx, face in enumerate(direct):
                bf = _probe_face(
                    face, body_id=0, face_idx=idx, doc=doc, capture=capture
                )
                if bf is not None:
                    faces.append(bf)
            return faces

    # Fallback: walk bodies via the parent IPartDoc. ctx is not
    # plumbed through the current interrogate() signature, so this
    # path is only taken when the caller supplies a feature that
    # exposes a parent body chain via IFeature.GetBody (rare).
    body_id = 0
    body = _try_get_body(feature)
    while body is not None:
        raw = _try_get_faces(body)
        for idx, face in enumerate(raw):
            bf = _probe_face(
                face, body_id=body_id, face_idx=idx, doc=doc, capture=capture
            )
            if bf is not None:
                faces.append(bf)
        body = _next_body(body)
        body_id += 1
    return faces


def _try_feature_getfaces(feature: Any) -> list[Any]:
    try:
        result = feature.GetFaces
        if callable(result):
            result = result()
    except Exception:
        return []
    if result is None:
        return []
    if isinstance(result, (tuple, list)):
        return list(result)
    return []


def _try_get_body(feature: Any) -> Optional[Any]:
    try:
        body = feature.GetBody
        if callable(body):
            body = body()
        return body
    except Exception:
        return None


def _next_body(body: Any) -> Optional[Any]:
    try:
        nxt = body.GetNext
        if callable(nxt):
            nxt = nxt()
        return nxt
    except Exception:
        return None


def _try_get_faces(body: Any) -> list[Any]:
    try:
        result = body.GetFaces
        if callable(result):
            result = result()
    except Exception:
        return []
    if result is None:
        return []
    if isinstance(result, (tuple, list)):
        return list(result)
    return []


def read_face_geometry(face: Any) -> Optional[dict[str, Any]]:
    """Read the fingerprint-relevant geometry from one live ``IFace2`` proxy.

    Returns ``{"normal", "centroid", "area_mm2", "bbox"}`` (the exact subset
    ``brep.fingerprint.fingerprint`` consumes, computed identically to
    :func:`_probe_face`), or ``None`` when the load-bearing reads (box, normal)
    are unreachable. The selection fingerprint-fallback resolver
    (``selection.live.resolve_by_fingerprint``) uses this so a re-matched face
    hashes byte-identically to the one captured at build time.
    """
    box = _read_box(face)
    normal = _read_normal(face)
    if box is None or normal is None:
        return None
    area_mm2 = _read_area(face)
    return {
        "normal": normal,
        "centroid": _centroid_from_box(box),
        "area_mm2": area_mm2 if area_mm2 is not None else 0.0,
        "bbox": (box[:3], box[3:]),
    }


def _probe_face(
    face: Any,
    *,
    body_id: int,
    face_idx: int,
    doc: Any = None,
    capture: bool = False,
) -> Optional[BrepFace]:
    """Extract the six load-bearing attributes from one IFace2 proxy.

    When ``capture`` is true and ``doc`` is the live model doc, also reads the
    face's durable ``GetPersistReference3`` token and stores it base64url-encoded
    on ``BrepFace.persist_id``. The read is fail-soft: any failure leaves
    ``persist_id`` empty and the face is still returned with its geometry.
    """
    box = _read_box(face)
    normal = _read_normal(face)
    area_mm2 = _read_area(face)
    if box is None or normal is None:
        return None

    centroid = _centroid_from_box(box)
    temp_id = _synthetic_temp_id(body_id, face_idx)
    role = _role_hint(normal, centroid, box)
    is_surface = _read_is_surface(face)
    is_hidden = _read_is_hidden(face)

    persist_id = ""
    if capture and doc is not None:
        pid = read_persist_reference(doc, face)
        if pid:
            persist_id = base64.urlsafe_b64encode(pid).decode("ascii").rstrip("=")

    # Wave-5 E2: evaluate the face's surface at the parametric midpoint
    # for a more accurate point + normal than the box-derived approximation.
    surface_uv = None
    try:
        uv_range = get_surface_parameter_range(face)
        if uv_range.get("ok"):
            u_mid = (uv_range["u_min"] + uv_range["u_max"]) / 2.0
            v_mid = (uv_range["v_min"] + uv_range["v_max"]) / 2.0
            surface_uv = evaluate_surface_at_uv(face, u_mid, v_mid)
    except Exception:
        pass

    return BrepFace(
        face_idx=face_idx,
        body_id=body_id,
        temp_id=temp_id,
        normal_vec=normal,
        centroid=centroid,
        bbox=(box[:3], box[3:]),
        area_mm2=area_mm2 if area_mm2 is not None else 0.0,
        role_hint=role,
        is_surface=is_surface,
        is_hidden=is_hidden,
        persist_id=persist_id,
        surface_uv=surface_uv,
    )


# ---------------------------------------------------------------------------
# Edge capture (Phase-0 durable selection) — body-scoped, persist_capture only.
# ---------------------------------------------------------------------------


def _get_solid_bodies(doc: Any) -> list[Any]:
    """Return the doc's visible solid bodies (``swSolidBody=0``)."""
    try:
        result = doc.GetBodies2(0, True)
    except Exception:
        return []
    if isinstance(result, (tuple, list)):
        return [b for b in result if b is not None]
    return [result] if result is not None else []


def _read_curve_params(edge: Any) -> Optional[tuple[float, ...]]:
    """``IEdge.GetCurveParams2`` -> tuple; head[0:3]=start xyz, head[3:6]=end xyz.

    The late-bind-friendly geometry source (``GetStartVertex``/``GetEndVertex``
    throw ``com_error`` on SW 2024 SP1 — see ``spike_edge_persist``).
    """
    try:
        result = edge.GetCurveParams2
        if callable(result):
            result = result()
    except Exception:
        return None
    if not isinstance(result, (tuple, list)) or len(result) < 6:
        return None
    try:
        return tuple(float(v) for v in result)
    except (TypeError, ValueError):
        return None


def _chord_mid(
    start: tuple[float, float, float], end: tuple[float, float, float]
) -> tuple[float, float, float]:
    """Midpoint of the chord (straight line) between two 3-points."""
    return (
        (start[0] + end[0]) / 2.0,
        (start[1] + end[1]) / 2.0,
        (start[2] + end[2]) / 2.0,
    )


def _read_curve_mid_and_arc(
    edge: Any,
    start: tuple[float, float, float],
    end: tuple[float, float, float],
) -> Optional[tuple[tuple[float, float, float], float, str]]:
    """Read the *true* curve midpoint (parametric midpoint) and arc length.

    Path: typed ``IEdge.GetCurve()`` -> typed_qi ``ICurve`` ->
    ``GetEndParams()`` for the parametric bounds,
    ``Evaluate((tmin+tmax)/2)`` for the curve midpoint, and
    ``ICurve.GetLength(tmin, tmax)`` for arc length.

    Seat-confirmed (A-run, SW 2024 SP1 rev 32.1.0): the late-bound edge
    proxies from ``body.GetEdges()`` cannot dispatch ``GetCurve`` or
    ``GetLength`` (``Member not found``); typed_qi to ``IEdge`` / ``ICurve``
    is required. ``ICurve`` exposes ``GetEndParams()`` (not
    ``GetParameterRange``), ``Evaluate(t)`` (not ``Evaluate2`` — the "2"
    variant takes a SAFEARRAY), and ``GetLength(t1, t2)`` (not a zero-arg
    ``IEdge.GetLength``). All reads are fail-soft — any step failing leaves
    that slot on ``None``, letting the caller fall back to chord geometry.

    Returns ``(curve_mid, arc_length, source_label)`` where ``source_label`` is
    one of ``"curve"`` (both reads OK), ``"curve-mid"`` (only Evaluate OK),
    ``"curve-arc"`` (only GetLength OK). Returns ``None`` when *both* reads
    failed (caller should use pure chord fallback).
    """

    def _call0(obj: Any, name: str) -> Any:
        try:
            attr = getattr(obj, name)
            return attr() if callable(attr) else attr
        except Exception:
            return None

    def _call1(obj: Any, name: str, arg: Any) -> Any:
        try:
            return getattr(obj, name)(arg)
        except Exception:
            return None

    # Typed chain: edge -> IEdge.GetCurve() -> ICurve.{GetEndParams, Evaluate,
    # GetLength}. Late-bound edge proxies from body.GetEdges() cannot dispatch
    # GetCurve or GetLength (A-run: Member not found); typed_qi is required.
    typed_curve = None
    try:
        te = typed_qi(edge, "IEdge")
        raw_curve = te.GetCurve()
        if raw_curve is not None:
            typed_curve = typed_qi(raw_curve, "ICurve")
    except EarlyBindError:
        typed_curve = None

    arc_length: Optional[float] = None
    curve_mid: Optional[tuple[float, float, float]] = None

    if typed_curve is not None:
        # ICurve.GetEndParams() -> (status, tmin, tmax, is_closed, is_periodic)
        try:
            ep = typed_curve.GetEndParams()
            if isinstance(ep, (tuple, list)) and len(ep) >= 3:
                tmin, tmax = float(ep[1]), float(ep[2])
            else:
                tmin, tmax = 0.0, 0.0
        except Exception:
            tmin, tmax = 0.0, 0.0

        if math.isfinite(tmin) and math.isfinite(tmax) and tmax > tmin:
            # ICurve.GetLength(tmin, tmax) — arc length in metres.
            try:
                gl = typed_curve.GetLength(tmin, tmax)
                gl_f = float(gl)
                if math.isfinite(gl_f) and gl_f >= 0.0:
                    arc_length = gl_f
            except Exception:
                pass

            # ICurve.Evaluate(tmid) — returns (x, y, z, dx, dy, dz, ...).
            # Evaluate (not Evaluate2 — the "2" variant takes a SAFEARRAY
            # and raises Type mismatch under pywin32).
            tmid = (tmin + tmax) / 2.0
            try:
                ev = typed_curve.Evaluate(tmid)
                if isinstance(ev, (tuple, list)) and len(ev) >= 3:
                    curve_mid = (float(ev[0]), float(ev[1]), float(ev[2]))
            except Exception:
                pass

    # Late-bound fallback (mock tests + future SW versions where late binding
    # may dispatch GetCurve / GetLength directly). Independent reads — a curve
    # chain failure must not suppress the length read.
    if arc_length is None:
        gl = _call0(edge, "GetLength")
        if gl is not None:
            try:
                gl_f = float(gl)
                if math.isfinite(gl_f) and gl_f >= 0.0:
                    arc_length = gl_f
            except (TypeError, ValueError):
                pass

    if curve_mid is None:
        curve = _call0(edge, "GetCurve")
        if curve is not None:
            pr = _call0(curve, "GetParameterRange")
            if isinstance(pr, (tuple, list)) and len(pr) >= 2:
                try:
                    tmin, tmax = float(pr[0]), float(pr[1])
                except (TypeError, ValueError):
                    tmin, tmax = 0.0, 0.0
                if math.isfinite(tmin) and math.isfinite(tmax) and tmax > tmin:
                    tmid = (tmin + tmax) / 2.0
                    ev = _call1(curve, "Evaluate", tmid)
                    if isinstance(ev, (tuple, list)) and len(ev) >= 3:
                        try:
                            curve_mid = (float(ev[0]), float(ev[1]), float(ev[2]))
                        except (TypeError, ValueError):
                            pass

    if curve_mid is None and arc_length is None:
        return None
    final_mid = curve_mid if curve_mid is not None else _chord_mid(start, end)
    final_len = arc_length if arc_length is not None else math.dist(start, end)
    if curve_mid is not None and arc_length is not None:
        source_label = "curve"
    elif curve_mid is not None:
        source_label = "curve-mid"
    else:
        source_label = "curve-arc"
    return (final_mid, final_len, source_label)


def _probe_edge(
    edge: Any, *, body_id: int, edge_idx: int, doc: Any, capture: bool
) -> Optional[BrepEdge]:
    """Read one IEdge's endpoints + durable token. Fail-soft (None on no geom).

    Geometry prefers the *true* curve arc length / midpoint (``ICurve.GetLength``
    + ``ICurve.Evaluate`` at the parametric midpoint) when those reads succeed;
    falls back to chord length / chord midpoint otherwise. ``curve_mid_source``
    records which path produced the stored ``midpoint``/``length``.
    """
    cp = _read_curve_params(edge)
    if cp is None:
        return None
    start = (cp[0], cp[1], cp[2])
    end = (cp[3], cp[4], cp[5])
    midpoint = _chord_mid(start, end)
    length = math.dist(start, end)
    source = "chord"

    curve_data = _read_curve_mid_and_arc(edge, start, end)
    if curve_data is not None:
        curve_mid, arc_len, source_label = curve_data
        midpoint = curve_mid
        length = arc_len
        source = source_label

    persist_id = ""
    if capture and doc is not None:
        pid = read_persist_reference(doc, edge)
        if pid:
            persist_id = base64.urlsafe_b64encode(pid).decode("ascii").rstrip("=")

    return BrepEdge(
        edge_idx=edge_idx,
        body_id=body_id,
        start=start,
        end=end,
        length=length,
        midpoint=midpoint,
        persist_id=persist_id,
        curve_mid_source=source,
    )


def _walk_edges(doc: Any, *, capture: bool) -> list[BrepEdge]:
    """Walk every solid body's edges, capturing token + endpoint geometry."""
    edges: list[BrepEdge] = []
    for body_id, body in enumerate(_get_solid_bodies(doc)):
        try:
            raw = body.GetEdges
            if callable(raw):
                raw = raw()
        except Exception:
            continue
        if not isinstance(raw, (tuple, list)):
            continue
        for idx, edge in enumerate(raw):
            be = _probe_edge(
                edge, body_id=body_id, edge_idx=idx, doc=doc, capture=capture
            )
            if be is not None:
                edges.append(be)
    return edges


def _read_box(face: Any) -> Optional[tuple[float, float, float, float, float, float]]:
    try:
        result = face.GetBox
        if callable(result):
            result = result()
    except Exception:
        return None
    if not isinstance(result, (tuple, list)) or len(result) != 6:
        return None
    try:
        return tuple(float(v) for v in result)  # type: ignore[return-value]
    except (TypeError, ValueError):
        return None


def _read_normal(face: Any) -> Optional[tuple[float, float, float]]:
    try:
        result = face.Normal
        if callable(result):
            result = result()
    except Exception:
        return None
    if not isinstance(result, (tuple, list)) or len(result) != 3:
        return None
    try:
        return tuple(float(v) for v in result)  # type: ignore[return-value]
    except (TypeError, ValueError):
        return None


def _read_area(face: Any) -> Optional[float]:
    try:
        result = face.GetArea
        if callable(result):
            result = result()
    except Exception:
        return None
    try:
        # SW returns m²; convert to mm².
        return float(result) * 1e6
    except (TypeError, ValueError):
        return None


def _read_is_surface(face: Any) -> bool:
    try:
        result = face.IsSurface
        if callable(result):
            result = result()
        return bool(result)
    except Exception:
        return False


def _read_is_hidden(face: Any) -> bool:
    """Read IFace2.IsHidden — true when the face is hidden from view.

    Some SW builds expose ``Visible`` as the inverse instead; fall back
    to that when ``IsHidden`` isn't reachable.
    """
    try:
        result = face.IsHidden
        if callable(result):
            result = result()
        return bool(result)
    except Exception:
        pass
    try:
        visible = face.Visible
        if callable(visible):
            visible = visible()
        return not bool(visible)
    except Exception:
        return False


def _is_suppressed(feature: Any) -> bool:
    """Check IFeature.IsSuppressed() — true when the feature is suppressed
    in the active configuration. Suppressed features have stale or
    absent geometry; interrogation must skip them entirely.
    """
    try:
        result = feature.IsSuppressed
        if callable(result):
            result = result()
        return bool(result)
    except Exception:
        return False


def _is_import_feature(feature: Any) -> bool:
    """Check IFeature.GetTypeName2() == "ImportFeature".

    Imported features (from STEP, IGES, Parasolid, etc.) have no
    native face topology accessible via ``IFeature.GetFaces`` — the
    walker has to fall back to body-level enumeration.
    """
    try:
        result = feature.GetTypeName2
        if callable(result):
            result = result()
        return str(result) == "ImportFeature"
    except Exception:
        pass
    # Older SW builds only expose GetTypeName.
    try:
        result = feature.GetTypeName
        if callable(result):
            result = result()
        return str(result) == "ImportFeature"
    except Exception:
        return False


def _centroid_from_box(
    box: tuple[float, float, float, float, float, float],
) -> tuple[float, float, float]:
    """Midpoint of the bbox — cheap, avoids GetCenterOfMass (spec §2.2)."""
    return (
        (box[0] + box[3]) / 2.0,
        (box[1] + box[4]) / 2.0,
        (box[2] + box[5]) / 2.0,
    )


def _synthetic_temp_id(body_id: int, face_idx: int) -> str:
    """Session-scoped placeholder for GetSelectByIDString.

    The E2.1 spike found IEntity.GetSelectByIDString unreachable on the
    IFace2 dispatch proxy returned via IFeature.GetFaces(); the
    out-of-process marshaler does not expose the full vtable. We use a
    body-local index as the stable-in-session identifier. Downstream
    face_role resolution uses role_hint + fingerprint, NOT temp_id.
    """
    return f"body{body_id}_face{face_idx}"


def _role_hint(
    normal: tuple[float, float, float],
    centroid: tuple[float, float, float],
    box: tuple[float, float, float, float, float, float],
) -> str:
    """Axis-aligned role hint per spec.md §2.3.

    Returns one of ``"+x_outboard"``, ``"-x_inboard"``, ``"+y_outboard"``,
    ... ``"oblique"``. "Outboard" vs "inboard" is decided by comparing
    the centroid's signed projection along the normal against the bbox
    midpoint along the dominant axis.
    """
    axes = ("x", "y", "z")
    for i, axis in enumerate(axes):
        n = normal[i]
        if abs(abs(n) - 1.0) > _AXIS_TOLERANCE:
            # other components must be ~0 for an axis-aligned normal
            other = [abs(normal[j]) for j in range(3) if j != i]
            if any(v > _AXIS_TOLERANCE for v in other):
                continue
            continue
        other = [abs(normal[j]) for j in range(3) if j != i]
        if any(v > _AXIS_TOLERANCE for v in other):
            continue
        sign = "+" if n > 0 else "-"
        # Outboard if centroid projection >= bbox midpoint along axis.
        midpoint = (box[i] + box[i + 3]) / 2.0
        projection = centroid[i]
        side = "outboard" if projection >= midpoint else "inboard"
        return f"{sign}{axis}_{side}"
    return "oblique"


__all__ = [
    "BrepEdge",
    "BrepFace",
    "interrogate",
    "read_face_geometry",
]
