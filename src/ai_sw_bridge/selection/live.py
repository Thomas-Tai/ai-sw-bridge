"""Live-COM bridge for :class:`DurableRef` (spec.md §5, Phase 0).

This is the production wiring of the durable-selection keystone proven by the
S-EARLYBIND spikes. ``DurableRef`` (and ``BrepFingerprint``) are pure data;
this module is the only place in the package that touches a live SOLIDWORKS
document to **capture** a persist token from an entity and **resolve** a token
back to a live entity.

It is deliberately thin and routes every OUT-param / Callout call through the
sanctioned hybrid escape hatch ``com.earlybind`` (late binding by default;
early-bound typed-wrap only where the marshaler needs it — see
``CODESTYLE.md §2.1.1``). The two load-bearing facts from the spikes:

* ``IModelDocExtension.GetObjectByPersistReference3(pid)`` returns
  ``(entity, errCode)`` under an early-bound typed Extension — the ``[out]``
  error code arrives as the 2nd tuple element (late binding cannot marshal it).
* The token survives a real save -> close -> reopen, **but** a freshly opened
  document must be rebuilt (``ForceRebuild3``) before the token resolves, else
  it comes back ``errCode=1`` ("Deleted"). Rebuild-on-open is the *caller's*
  responsibility (the open-existing-doc lane); this module assumes the doc is
  in a resolved state.

Resolution honors the deterministic fallback hierarchy from ``DurableRef``:

1. ``persist_id`` via ``GetObjectByPersistReference3`` (proven, reliable).
2. ``fingerprint`` re-match against the live body — exact-hash first, then a
   lossy normal/centroid proximity match (:func:`resolve_by_fingerprint`).
3. client-side hand-off (out of bridge core).

Every COM interaction is failure-tolerant: a capture that cannot read a token
returns ``None`` (the first-class "persist unavailable" state, so the manifest
degrades to fingerprint-only with no regression), and a resolve that fails
returns a structured outcome naming why — never a raw exception escaping into
the build loop.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from ..brep.fingerprint import fingerprint as _compute_fingerprint
from ..brep.interrogator import read_face_geometry
from ..com import earlybind

# Tier-2 (fingerprint) lossy-match tolerances. Looser than the fingerprint
# quantization (the exact-hash path handles tight matches); these bound the
# geometry-proximity fallback used when a rebuild perturbed a face past the
# quantization step. ``1 - normal_dot`` <= NORMAL_TOL and centroid distance
# <= CENTROID_TOL_M must both hold for a candidate to qualify.
_FP_NORMAL_TOL = 0.02      # ~11 deg of normal slop
_FP_CENTROID_TOL_M = 1e-3  # 1 mm centroid drift

# swPersistReferencedObjectStatus_e — the [out] code from
# GetObjectByPersistReference3. Only ``Ok`` yields a usable entity.
PERSIST_OK = 0
PERSIST_DELETED = 1
PERSIST_SUPPRESSED = 2
PERSIST_AMBIGUOUS = 3
PERSIST_INVALID = 4
PERSIST_STATUS_NAMES: dict[int, str] = {
    PERSIST_OK: "Ok",
    PERSIST_DELETED: "Deleted",
    PERSIST_SUPPRESSED: "Suppressed",
    PERSIST_AMBIGUOUS: "AmbiguousReference",
    PERSIST_INVALID: "InvalidReference",
}


def _is_entity(obj: Any) -> bool:
    """A real COM entity came back (not None, not an int error sentinel)."""
    return obj is not None and not isinstance(obj, int)


@dataclass(frozen=True)
class PersistResolution:
    """Outcome of a single ``GetObjectByPersistReference3`` round-trip.

    * ``entity`` — the resolved COM entity, or ``None`` if it did not resolve.
    * ``status_code`` — the raw ``[out]`` ``swPersistReferencedObjectStatus_e``
      code (``None`` if the call never returned one).
    * ``ok`` — ``True`` iff an entity resolved with an ``Ok`` (or absent) status.
    * ``error`` — a short reason string when the call failed outright.
    """

    entity: Any | None
    status_code: int | None
    ok: bool
    error: str | None = None

    @property
    def status_name(self) -> str | None:
        if self.status_code is None:
            return None
        return PERSIST_STATUS_NAMES.get(self.status_code, f"Unknown({self.status_code})")


@dataclass(frozen=True)
class RefResolution:
    """Outcome of resolving a whole :class:`DurableRef` through the hierarchy.

    * ``entity`` — the resolved entity, or ``None``.
    * ``method`` — ``"persist_id"`` (resolved via the token),
      ``"fingerprint_fallback"`` (persist unavailable/failed — the caller must
      re-match by fingerprint against the live body), or ``"unresolved"``.
    * ``persist`` — the underlying :class:`PersistResolution` when a token was
      attempted, else ``None``.
    * ``note`` — human-readable context.
    """

    entity: Any | None
    method: str
    persist: PersistResolution | None = None
    note: str | None = None


def capture_persist_id(doc: Any, entity: Any) -> bytes | None:
    """Read the durable persist token for *entity* from the live *doc*.

    Returns the raw token bytes, or ``None`` if the token cannot be read for
    any reason (entity has none, the API is unavailable, or the marshaler
    fails). ``None`` is the first-class "persist unavailable" state —
    ``DurableRef`` stores it as ``persist_id=None`` and the manifest omits the
    key, degrading cleanly to fingerprint-only.

    Args:
        doc: the live ``IModelDoc2`` the entity belongs to.
        entity: a face / edge / vertex COM object from that doc's body.
    """
    return earlybind.read_persist_reference(doc, entity)


def resolve_persist_id(doc: Any, persist_id: bytes | None) -> PersistResolution:
    """Resolve a persist token to a live entity on *doc*.

    Routes through an early-bound typed ``IModelDocExtension`` so the
    ``[out]`` status code is marshaled (the whole reason this call needs
    the hybrid escape hatch). Never raises — failures are reported in the
    returned :class:`PersistResolution`.
    """
    if persist_id is None:
        return PersistResolution(None, None, False, error="no persist_id")
    try:
        token = bytes(persist_id)
    except Exception as e:  # noqa: BLE001
        return PersistResolution(None, None, False, error=f"bad token: {e}")
    try:
        ext = earlybind.typed_extension(doc)
        res = ext.GetObjectByPersistReference3(token)
    except earlybind.EarlyBindError as e:
        return PersistResolution(None, None, False, error=f"earlybind: {e}")
    except Exception as e:  # noqa: BLE001
        return PersistResolution(None, None, False, error=f"{type(e).__name__}: {e}")

    if isinstance(res, tuple):
        obj = res[0] if res else None
        code = res[1] if len(res) > 1 and isinstance(res[1], int) else None
    else:
        obj, code = res, None

    resolved = _is_entity(obj) and (code is None or code == PERSIST_OK)
    return PersistResolution(obj if resolved else None, code, resolved)


def _iter_live_faces(doc: Any) -> list[Any]:
    """Return all solid-body faces of *doc* (best-effort, never raises).

    ``GetBodies2(swSolidBody=0, bVisibleOnly=True)`` then ``GetFaces`` per
    body. Both come back as SAFEARRAYs (tuples) under late binding; under
    early binding they may be methods — handled either way.
    """
    def _call(obj: Any, name: str, *args: Any) -> Any:
        attr = getattr(obj, name)
        return attr(*args) if callable(attr) else attr

    try:
        bodies = _call(doc, "GetBodies2", 0, True)
    except Exception:  # noqa: BLE001
        return []
    if not bodies:
        return []
    if not isinstance(bodies, (tuple, list)):
        bodies = [bodies]
    faces: list[Any] = []
    for body in bodies:
        if body is None:
            continue
        try:
            raw = _call(body, "GetFaces")
        except Exception:  # noqa: BLE001
            continue
        if raw is None:
            continue
        faces.extend(list(raw) if isinstance(raw, (tuple, list)) else [raw])
    return faces


def _geom_distance(fp: Any, geom: dict[str, Any]) -> tuple[float, float] | None:
    """Return ``(1 - normal_dot, centroid_distance_m)`` between a captured
    fingerprint *fp* and a live face *geom*, or ``None`` if either is malformed.
    """
    try:
        n0 = fp.normal
        c0 = fp.centroid
        n1 = geom["normal"]
        c1 = geom["centroid"]
        dot = abs(sum(a * b for a, b in zip(n0, n1)))
        dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(c0, c1)))
    except Exception:  # noqa: BLE001
        return None
    return (1.0 - dot, dist)


def resolve_by_fingerprint(doc: Any, ref: Any) -> RefResolution:
    """Tier-2 resolution: re-match ``ref.fingerprint`` against live geometry.

    Walks the live solid-body faces and computes each face's fingerprint the
    same way the manifest does (via ``brep.interrogator.read_face_geometry`` +
    ``brep.fingerprint.fingerprint``), so an unperturbed face matches by exact
    hash. When no exact hash matches (a rebuild moved the face past the
    quantization step), falls back to the closest face within the lossy
    normal/centroid tolerances. Returns ``method``:

    * ``"fingerprint"`` — exact hash match (reliable).
    * ``"fingerprint_geom"`` — lossy geometry-proximity match (best-effort).
    * ``"unresolved"`` — no acceptable candidate.
    """
    fp = getattr(ref, "fingerprint", None)
    if fp is None:
        return RefResolution(None, "unresolved", note="ref has no fingerprint")
    target_hash = getattr(fp, "hash_hex", None)

    best_face: Any = None
    best_key: tuple[float, float] | None = None
    for face in _iter_live_faces(doc):
        geom = read_face_geometry(face)
        if geom is None:
            continue
        try:
            h = _compute_fingerprint(
                {
                    "normal": list(geom["normal"]),
                    "centroid": list(geom["centroid"]),
                    "area_mm2": geom["area_mm2"],
                }
            )
        except Exception:  # noqa: BLE001
            h = None
        if target_hash is not None and h == target_hash:
            return RefResolution(face, "fingerprint", note="exact fingerprint match")
        dd = _geom_distance(fp, geom)
        if dd is None:
            continue
        n_err, dist = dd
        if n_err <= _FP_NORMAL_TOL and dist <= _FP_CENTROID_TOL_M:
            if best_key is None or dd < best_key:
                best_key = dd
                best_face = face

    if best_face is not None:
        return RefResolution(
            best_face,
            "fingerprint_geom",
            note=(
                f"lossy geometry match (no exact hash; 1-dot={best_key[0]:.4g}, "
                f"centroid_dist={best_key[1]:.4g} m)"
            ),
        )
    return RefResolution(None, "unresolved", note="no fingerprint match among live faces")


def resolve_ref(doc: Any, ref: Any, *, allow_fingerprint: bool = True) -> RefResolution:
    """Resolve a :class:`DurableRef` to a live entity via the full hierarchy.

    Tier 1 ``persist_id`` (proven, reliable) → tier 2 ``fingerprint`` re-match
    against the live body (lossy; :func:`resolve_by_fingerprint`). The
    ``persist`` field always carries the tier-1 outcome (or ``None`` if there
    was no token) so callers can see why the fallback was taken.

    Args:
        doc: the live document to resolve against (assumed rebuilt — a
            freshly opened doc must be ``ForceRebuild3``'d first, else the
            token resolves to ``Deleted``).
        ref: a ``DurableRef`` (uses ``persist_id`` then ``fingerprint``).
        allow_fingerprint: when ``False``, skip tier 2 (persist-only) — used
            where the cost of a full live-face walk isn't wanted.
    """
    pr: PersistResolution | None = None
    persist_id = getattr(ref, "persist_id", None)
    if persist_id is not None:
        pr = resolve_persist_id(doc, persist_id)
        if pr.ok:
            return RefResolution(pr.entity, "persist_id", persist=pr)
        persist_note = f"persist failed (status={pr.status_name}, error={pr.error})"
    else:
        persist_note = "no persist_id on ref"

    if allow_fingerprint and getattr(ref, "fingerprint", None) is not None:
        fr = resolve_by_fingerprint(doc, ref)
        return RefResolution(
            fr.entity,
            fr.method if fr.entity is not None else "unresolved",
            persist=pr,
            note=f"{persist_note}; {fr.note}",
        )

    return RefResolution(
        None,
        "fingerprint_fallback",
        persist=pr,
        note=f"{persist_note}; fingerprint re-match not attempted",
    )


def resolve_edge_ref(doc: Any, ref: Any) -> RefResolution:
    """Resolve a :class:`DurableEdgeRef` to a live edge (tier-1 persist only).

    Edges resolve by their ``GetPersistReference3`` token — proven robust through
    rebuild and reopen (``spike_edge_persist``). There is no edge fingerprint
    fallback in v1, so a missing/failed token yields ``"unresolved"`` (the caller
    degrades to client hand-off rather than a lossy geometric re-match).

    Args:
        doc: the live document (assumed rebuilt — a freshly opened doc must be
            ``ForceRebuild3``'d first, else the token resolves to ``Deleted``).
        ref: a ``DurableEdgeRef`` (uses ``persist_id``).
    """
    persist_id = getattr(ref, "persist_id", None)
    if persist_id is None:
        return RefResolution(None, "unresolved", note="edge ref has no persist_id")
    pr = resolve_persist_id(doc, persist_id)
    if pr.ok and pr.entity is not None:
        return RefResolution(pr.entity, "persist_id", persist=pr)
    return RefResolution(
        None,
        "unresolved",
        persist=pr,
        note=f"edge persist failed (status={pr.status_name}, error={pr.error})",
    )


def select_entity(entity: Any, *, append: bool = False, mark: int = 0) -> bool:
    """Select a resolved entity via an early-bound typed ``IEntity.Select2``.

    The Callout-free ``Select2(Append, Mark)`` form marshals cleanly; this is
    the proven post-resolve selection step (S-EARLYBIND). Returns ``False`` on
    any failure rather than raising, so a resolution that succeeded but whose
    selection failed is distinguishable by the caller.
    """
    if not _is_entity(entity):
        return False
    try:
        ent = earlybind.typed(entity, "IEntity")
        return bool(ent.Select2(append, mark))
    except earlybind.EarlyBindError:
        return False
    except Exception:  # noqa: BLE001
        return False


__all__ = [
    "PERSIST_AMBIGUOUS",
    "PERSIST_DELETED",
    "PERSIST_INVALID",
    "PERSIST_OK",
    "PERSIST_STATUS_NAMES",
    "PERSIST_SUPPRESSED",
    "PersistResolution",
    "RefResolution",
    "capture_persist_id",
    "resolve_by_fingerprint",
    "resolve_edge_ref",
    "resolve_persist_id",
    "resolve_ref",
    "select_entity",
]
