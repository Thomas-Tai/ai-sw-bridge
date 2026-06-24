"""Tests for ai_sw_bridge.selection.live — the live-COM bridge for DurableRef.

The module's only dependency on SOLIDWORKS is the ``com.earlybind`` seam
(``typed_extension`` / ``typed``). These tests monkeypatch that seam with
fakes, so the capture/resolve/select contract is exercised without pywin32 or
a live SW seat — mirroring the proven S-EARLYBIND round-trip shapes (the
``[out]`` status arrives as the 2nd tuple element).
"""

from __future__ import annotations

import math
import types

import pytest

from ai_sw_bridge.selection import live
from ai_sw_bridge.selection import BrepFingerprint, DurableEdgeRef, DurableRef
from ai_sw_bridge.com.earlybind import EarlyBindError


class _FakeEntity:
    """Stand-in for a resolved COM entity; records Select2 calls."""

    def __init__(self, selectable: bool = True) -> None:
        self._selectable = selectable
        self.select_calls: list[tuple[bool, int]] = []

    def Select2(self, append: bool, mark: int) -> bool:  # noqa: N802 — COM name
        self.select_calls.append((append, mark))
        return self._selectable


class _FakeExt:
    """Fake typed IModelDocExtension with scriptable persist behavior."""

    def __init__(self, *, read=None, resolve=None) -> None:
        self._read = read
        self._resolve = resolve

    def GetPersistReference3(self, entity):  # noqa: N802 — COM name
        if isinstance(self._read, Exception):
            raise self._read
        return self._read

    def GetObjectByPersistReference3(self, pid):  # noqa: N802 — COM name
        if isinstance(self._resolve, Exception):
            raise self._resolve
        return self._resolve


def _patch_ext(monkeypatch: pytest.MonkeyPatch, ext) -> None:
    monkeypatch.setattr(live.earlybind, "typed_extension", lambda doc, **k: ext)


_DOC = object()  # opaque doc handle; the fakes ignore it


# ---------------------------------------------------------------------------
# capture_persist_id
# ---------------------------------------------------------------------------


class TestCapturePersistId:
    def test_reads_bytes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_ext(monkeypatch, _FakeExt(read=memoryview(b"\x01\x02\x03")))
        assert live.capture_persist_id(_DOC, object()) == b"\x01\x02\x03"

    def test_none_doc_or_entity(self) -> None:
        assert live.capture_persist_id(None, object()) is None
        assert live.capture_persist_id(_DOC, None) is None

    def test_none_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_ext(monkeypatch, _FakeExt(read=None))
        assert live.capture_persist_id(_DOC, object()) is None

    def test_earlybind_error_degrades_to_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            live.earlybind,
            "typed_extension",
            lambda doc, **k: (_ for _ in ()).throw(EarlyBindError("no wrapper")),
        )
        assert live.capture_persist_id(_DOC, object()) is None

    def test_com_exception_degrades_to_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_ext(monkeypatch, _FakeExt(read=RuntimeError("com boom")))
        assert live.capture_persist_id(_DOC, object()) is None

    def test_uncoercible_token_degrades_to_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_ext(monkeypatch, _FakeExt(read=object()))  # bytes(object()) raises
        assert live.capture_persist_id(_DOC, object()) is None


# ---------------------------------------------------------------------------
# resolve_persist_id
# ---------------------------------------------------------------------------


class TestResolvePersistId:
    def test_ok_tuple(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ent = _FakeEntity()
        _patch_ext(monkeypatch, _FakeExt(resolve=(ent, 0)))
        r = live.resolve_persist_id(_DOC, b"tok")
        assert r.ok is True
        assert r.entity is ent
        assert r.status_code == 0
        assert r.status_name == "Ok"

    def test_deleted_status_not_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_ext(monkeypatch, _FakeExt(resolve=(object(), 1)))
        r = live.resolve_persist_id(_DOC, b"tok")
        assert r.ok is False
        assert r.entity is None
        assert r.status_code == 1
        assert r.status_name == "Deleted"

    def test_non_tuple_entity_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ent = _FakeEntity()
        _patch_ext(monkeypatch, _FakeExt(resolve=ent))
        r = live.resolve_persist_id(_DOC, b"tok")
        assert r.ok is True
        assert r.entity is ent
        assert r.status_code is None

    def test_none_object_with_ok_code_not_ok(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_ext(monkeypatch, _FakeExt(resolve=(None, 0)))
        r = live.resolve_persist_id(_DOC, b"tok")
        assert r.ok is False
        assert r.entity is None

    def test_none_persist_id(self) -> None:
        r = live.resolve_persist_id(_DOC, None)
        assert r.ok is False
        assert r.error == "no persist_id"

    def test_earlybind_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            live.earlybind,
            "typed_extension",
            lambda doc, **k: (_ for _ in ()).throw(EarlyBindError("x")),
        )
        r = live.resolve_persist_id(_DOC, b"tok")
        assert r.ok is False
        assert r.error and "earlybind" in r.error

    def test_com_exception(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_ext(monkeypatch, _FakeExt(resolve=ValueError("bad")))
        r = live.resolve_persist_id(_DOC, b"tok")
        assert r.ok is False
        assert r.error and "ValueError" in r.error


# ---------------------------------------------------------------------------
# resolve_ref (the hierarchy)
# ---------------------------------------------------------------------------


class TestResolveRef:
    def test_persist_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ent = _FakeEntity()
        _patch_ext(monkeypatch, _FakeExt(resolve=(ent, 0)))
        ref = types.SimpleNamespace(persist_id=b"tok")
        r = live.resolve_ref(_DOC, ref)
        assert r.method == "persist_id"
        assert r.entity is ent

    def test_persist_fail_falls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_ext(monkeypatch, _FakeExt(resolve=(object(), 1)))  # Deleted
        ref = types.SimpleNamespace(persist_id=b"tok")
        r = live.resolve_ref(_DOC, ref)
        assert r.method == "fingerprint_fallback"
        assert r.entity is None
        assert r.persist is not None and r.persist.status_name == "Deleted"
        assert r.note and "fingerprint" in r.note

    def test_no_persist_id_falls_back(self) -> None:
        ref = types.SimpleNamespace(persist_id=None)
        r = live.resolve_ref(_DOC, ref)
        assert r.method == "fingerprint_fallback"
        assert r.persist is None
        assert r.note and "no persist_id" in r.note


# ---------------------------------------------------------------------------
# select_entity
# ---------------------------------------------------------------------------


class TestSelectEntity:
    def test_selects(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ent = _FakeEntity(selectable=True)
        monkeypatch.setattr(live.earlybind, "typed", lambda obj, iface, **k: obj)
        assert live.select_entity(ent, append=True, mark=2) is True
        assert ent.select_calls == [(True, 2)]

    def test_none_entity_false(self) -> None:
        assert live.select_entity(None) is False
        assert live.select_entity(5) is False  # int sentinel

    def test_earlybind_error_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            live.earlybind,
            "typed",
            lambda obj, iface, **k: (_ for _ in ()).throw(EarlyBindError("x")),
        )
        assert live.select_entity(_FakeEntity()) is False

    def test_select_exception_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _Boom:
            def Select2(self, a, m):  # noqa: N802
                raise RuntimeError("nope")

        monkeypatch.setattr(live.earlybind, "typed", lambda obj, iface, **k: obj)
        assert live.select_entity(_Boom()) is False


# ---------------------------------------------------------------------------
# resolve_by_fingerprint (tier 2) + _iter_live_faces
# ---------------------------------------------------------------------------

# A reference geometry and its real fingerprint (computed via brep.fingerprint).
_GEOM = {"normal": [0.0, 0.0, 1.0], "centroid": [0.0, 0.0, 0.005], "area_mm2": 2500.0}
_FP = BrepFingerprint.from_face_dict(_GEOM)


def _ref(persist_id=None):
    return DurableRef(persist_id=persist_id, fingerprint=_FP, role_hint="+z_outboard")


def _geom(normal, centroid, area):
    return {
        "normal": list(normal),
        "centroid": list(centroid),
        "area_mm2": area,
        "bbox": ([0, 0, 0], [0, 0, 0]),
    }


def _patch_faces(monkeypatch, face_to_geom: dict) -> None:
    """Make _iter_live_faces yield the keys and read_face_geometry map them."""
    faces = list(face_to_geom)
    monkeypatch.setattr(live, "_iter_live_faces", lambda doc: faces)
    monkeypatch.setattr(live, "read_face_geometry", lambda f: face_to_geom[f])


class TestResolveByFingerprint:
    def test_exact_hash_match(self, monkeypatch: pytest.MonkeyPatch) -> None:
        far = object()
        hit = object()
        _patch_faces(
            monkeypatch,
            {
                far: _geom((1, 0, 0), (0.01, 0, 0), 100.0),
                hit: _geom(_GEOM["normal"], _GEOM["centroid"], _GEOM["area_mm2"]),
            },
        )
        r = live.resolve_by_fingerprint(_DOC, _ref())
        assert r.method == "fingerprint"
        assert r.entity is hit

    def test_geometry_proximity_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Same normal, centroid 0.5 mm off, different area -> hash differs but
        # within the lossy tolerances.
        near = object()
        _patch_faces(
            monkeypatch,
            {
                near: _geom((0.0, 0.0, 1.0), (0.0, 0.0, 0.0055), 2501.0),
            },
        )
        r = live.resolve_by_fingerprint(_DOC, _ref())
        assert r.method == "fingerprint_geom"
        assert r.entity is near

    def test_no_match_unresolved(self, monkeypatch: pytest.MonkeyPatch) -> None:
        far = object()
        _patch_faces(monkeypatch, {far: _geom((1, 0, 0), (0.05, 0, 0), 9.0)})
        r = live.resolve_by_fingerprint(_DOC, _ref())
        assert r.method == "unresolved"
        assert r.entity is None

    def test_ref_without_fingerprint(self) -> None:
        r = live.resolve_by_fingerprint(_DOC, types.SimpleNamespace(fingerprint=None))
        assert r.method == "unresolved"
        assert "no fingerprint" in r.note

    def test_unreadable_faces_skipped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        bad, good = object(), object()
        geoms = {
            bad: None,
            good: _geom(_GEOM["normal"], _GEOM["centroid"], _GEOM["area_mm2"]),
        }
        monkeypatch.setattr(live, "_iter_live_faces", lambda doc: [bad, good])
        monkeypatch.setattr(live, "read_face_geometry", lambda f: geoms[f])
        r = live.resolve_by_fingerprint(_DOC, _ref())
        assert r.method == "fingerprint"
        assert r.entity is good


class TestIterLiveFaces:
    def test_flattens_bodies(self) -> None:
        f1, f2, f3 = object(), object(), object()
        body_a = types.SimpleNamespace(GetFaces=(f1, f2))
        body_b = types.SimpleNamespace(GetFaces=(f3,))
        doc = types.SimpleNamespace(GetBodies2=(body_a, body_b))
        assert live._iter_live_faces(doc) == [f1, f2, f3]

    def test_no_bodies(self) -> None:
        doc = types.SimpleNamespace(GetBodies2=())
        assert live._iter_live_faces(doc) == []

    def test_body_without_faces_skipped(self) -> None:
        f1 = object()
        good = types.SimpleNamespace(GetFaces=(f1,))
        doc = types.SimpleNamespace(
            GetBodies2=(object(), good)
        )  # object() has no GetFaces
        assert live._iter_live_faces(doc) == [f1]

    def test_getbodies_raises(self) -> None:
        class _Doc:
            @property
            def GetBodies2(self):  # noqa: N802
                raise RuntimeError("no bodies")

        assert live._iter_live_faces(_Doc()) == []


# ---------------------------------------------------------------------------
# resolve_ref tier-2 integration
# ---------------------------------------------------------------------------


class TestResolveRefTier2:
    def test_persist_fail_then_fingerprint(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_ext(monkeypatch, _FakeExt(resolve=(object(), 1)))  # Deleted
        hit = object()
        _patch_faces(
            monkeypatch,
            {
                hit: _geom(_GEOM["normal"], _GEOM["centroid"], _GEOM["area_mm2"]),
            },
        )
        r = live.resolve_ref(_DOC, _ref(persist_id=b"tok"))
        assert r.method == "fingerprint"
        assert r.entity is hit
        assert r.persist is not None and r.persist.status_name == "Deleted"

    def test_no_persist_id_uses_fingerprint(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        hit = object()
        _patch_faces(
            monkeypatch,
            {
                hit: _geom(_GEOM["normal"], _GEOM["centroid"], _GEOM["area_mm2"]),
            },
        )
        r = live.resolve_ref(_DOC, _ref(persist_id=None))
        assert r.method == "fingerprint"
        assert r.entity is hit
        assert r.persist is None

    def test_allow_fingerprint_false_skips_tier2(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_ext(monkeypatch, _FakeExt(resolve=(object(), 1)))  # Deleted
        r = live.resolve_ref(_DOC, _ref(persist_id=b"tok"), allow_fingerprint=False)
        assert r.method == "fingerprint_fallback"
        assert r.entity is None
        assert "not attempted" in r.note


# ---------------------------------------------------------------------------
# resolve_manifest_face — the data-layer -> live-layer seam (OI-3)
# ---------------------------------------------------------------------------


def _manifest_face(*, persist_b64=None, normal=None, centroid=None, area=None):
    """A serialized manifest face dict (brep.manifest._serialize_face shape)."""
    face = {
        "normal": list(normal if normal is not None else _GEOM["normal"]),
        "centroid": list(centroid if centroid is not None else _GEOM["centroid"]),
        "area_mm2": area if area is not None else _GEOM["area_mm2"],
        "role_hint": "+z_outboard",
    }
    if persist_b64 is not None:
        face["persist_id"] = persist_b64
    return face


class TestResolveManifestFace:
    def test_persist_tier_preferred(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # base64url(b"tok") == "dG9r" (no padding); the face carries a token, so
        # tier 1 resolves and the live-face walk is never consulted.
        ent = _FakeEntity()
        _patch_ext(monkeypatch, _FakeExt(resolve=(ent, 0)))
        monkeypatch.setattr(live, "_iter_live_faces", _unexpected_face_walk)
        r = live.resolve_manifest_face(_DOC, _manifest_face(persist_b64="dG9r"))
        assert r.method == "persist_id"
        assert r.entity is ent

    def test_no_token_falls_back_to_fingerprint(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        hit = object()
        _patch_faces(
            monkeypatch,
            {
                hit: _geom(_GEOM["normal"], _GEOM["centroid"], _GEOM["area_mm2"]),
            },
        )
        r = live.resolve_manifest_face(_DOC, _manifest_face())  # no persist_id
        assert r.method == "fingerprint"
        assert r.entity is hit
        assert r.persist is None

    def test_persist_only_skips_face_walk(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_ext(monkeypatch, _FakeExt(resolve=(object(), 1)))  # Deleted
        monkeypatch.setattr(live, "_iter_live_faces", _unexpected_face_walk)
        r = live.resolve_manifest_face(
            _DOC, _manifest_face(persist_b64="dG9r"), allow_fingerprint=False
        )
        assert r.method == "fingerprint_fallback"
        assert r.entity is None


def _unexpected_face_walk(doc):
    raise AssertionError("live-face walk should not run on the persist path")


# ---------------------------------------------------------------------------
# Package re-exports
# ---------------------------------------------------------------------------


def test_package_reexports() -> None:
    from ai_sw_bridge import selection

    assert selection.capture_persist_id is live.capture_persist_id
    assert selection.resolve_ref is live.resolve_ref
    assert selection.resolve_manifest_face is live.resolve_manifest_face
    assert selection.resolve_by_edge_fingerprint is live.resolve_by_edge_fingerprint
    assert selection.PersistResolution is live.PersistResolution


# ---------------------------------------------------------------------------
# resolve_edge_ref — tier-1 persist + tier-2 edge fingerprint fallback
# ---------------------------------------------------------------------------


def _edge_ref(persist_id=b"\x01\x02"):
    return DurableEdgeRef(
        persist_id=persist_id,
        start=(0.0, 0.0, 0.0),
        end=(0.0, 0.0, 0.01),
        length=0.01,
    )


def _patch_edges(monkeypatch, edge_to_geom: dict) -> None:
    """Make _iter_live_edges yield the keys and _read_edge_geometry map them."""
    edges = list(edge_to_geom)
    monkeypatch.setattr(live, "_iter_live_edges", lambda doc: edges)
    monkeypatch.setattr(live, "_read_edge_geometry", lambda e: edge_to_geom[e])


def _unexpected_edge_walk(doc):
    raise AssertionError("live-edge walk should not run on the persist path")


class TestResolveEdgeRef:
    def test_persist_hit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ent = _FakeEntity()
        _patch_ext(monkeypatch, _FakeExt(resolve=(ent, 0)))
        res = live.resolve_edge_ref(_DOC, _edge_ref())
        assert res.method == "persist_id"
        assert res.entity is ent

    def test_persist_hit_short_circuits_edge_walk(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Persist success must not run the live-edge walk (tier-1 only)."""
        ent = _FakeEntity()
        _patch_ext(monkeypatch, _FakeExt(resolve=(ent, 0)))
        monkeypatch.setattr(live, "_iter_live_edges", _unexpected_edge_walk)
        res = live.resolve_edge_ref(_DOC, _edge_ref())
        assert res.method == "persist_id"
        assert res.entity is ent

    def test_persist_deleted_is_unresolved(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Patch the edge walk empty so tier-2 has no candidates — preserves
        # the "persist failure → unresolved" assertion now that tier-2 exists.
        _patch_ext(monkeypatch, _FakeExt(resolve=(object(), 1)))  # status Deleted
        _patch_edges(monkeypatch, {})
        res = live.resolve_edge_ref(_DOC, _edge_ref())
        assert res.method == "unresolved"
        assert res.entity is None
        assert res.persist is not None and not res.persist.ok

    def test_no_persist_id_is_unresolved(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Patch the edge walk empty so tier-2 has no candidates.
        _patch_edges(monkeypatch, {})
        res = live.resolve_edge_ref(_DOC, _edge_ref(persist_id=None))
        assert res.method == "unresolved"
        assert res.entity is None
        assert "no persist_id" in (res.note or "")


# ---------------------------------------------------------------------------
# _iter_live_edges — mirrors TestIterLiveFaces
# ---------------------------------------------------------------------------


class TestIterLiveEdges:
    def test_flattens_bodies(self) -> None:
        e1, e2, e3 = object(), object(), object()
        body_a = types.SimpleNamespace(GetEdges=(e1, e2))
        body_b = types.SimpleNamespace(GetEdges=(e3,))
        doc = types.SimpleNamespace(GetBodies2=(body_a, body_b))
        assert live._iter_live_edges(doc) == [e1, e2, e3]

    def test_no_bodies(self) -> None:
        doc = types.SimpleNamespace(GetBodies2=())
        assert live._iter_live_edges(doc) == []

    def test_body_without_edges_skipped(self) -> None:
        e1 = object()
        good = types.SimpleNamespace(GetEdges=(e1,))
        doc = types.SimpleNamespace(GetBodies2=(object(), good))
        assert live._iter_live_edges(doc) == [e1]

    def test_getbodies_raises(self) -> None:
        class _Doc:
            @property
            def GetBodies2(self):  # noqa: N802
                raise RuntimeError("no bodies")

        assert live._iter_live_edges(_Doc()) == []


# ---------------------------------------------------------------------------
# resolve_by_edge_fingerprint (tier 2) — wiring tests (predicate covered by
# TestEdgeMatchPredicate)
# ---------------------------------------------------------------------------

# Reference edge geometry: a 10 mm edge along +Z.
_EDGE_GEOM = {"start": [0.0, 0.0, 0.0], "end": [0.0, 0.0, 0.01], "length": 0.01}


def _edge_geom(start, end):
    midpoint = [(s + e) / 2.0 for s, e in zip(start, end)]
    length = math.sqrt(sum((a - b) ** 2 for a, b in zip(start, end)))
    return {
        "start": list(start),
        "end": list(end),
        "length": length,
        "midpoint": midpoint,
    }


class TestResolveByEdgeFingerprint:
    def test_endpoint_match_hits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        hit = object()
        far = object()
        _patch_edges(
            monkeypatch,
            {
                far: _edge_geom((0.05, 0.0, 0.0), (0.05, 0.0, 0.01)),  # 50 mm away
                hit: _edge_geom((0.0, 0.0, 0.0), (0.0, 0.0, 0.01)),  # exact match
            },
        )
        res = live.resolve_by_edge_fingerprint(_DOC, _edge_ref())
        assert res.method == "edge_fingerprint"
        assert res.entity is hit

    def test_no_match_unresolved(self, monkeypatch: pytest.MonkeyPatch) -> None:
        far = object()
        _patch_edges(
            monkeypatch,
            {
                far: _edge_geom((0.05, 0.0, 0.0), (0.05, 0.0, 0.01)),
            },
        )
        res = live.resolve_by_edge_fingerprint(_DOC, _edge_ref())
        assert res.method == "unresolved"
        assert res.entity is None

    def test_ref_without_endpoints(self) -> None:
        ref = types.SimpleNamespace(start=(), end=(), length=0.0)
        res = live.resolve_by_edge_fingerprint(_DOC, ref)
        assert res.method == "unresolved"
        assert "no endpoint geometry" in (res.note or "")

    def test_best_candidate_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Two matching candidates: the closer one (smaller key) wins."""
        near = object()
        far = object()
        _patch_edges(
            monkeypatch,
            {
                # Both match within tol; near is 0.1 mm off, far is 0.8 mm off.
                near: {"start": [0.0, 0.0, 0.0], "end": [0.0, 0.0001, 0.01]},
                far: {"start": [0.0, 0.0, 0.0], "end": [0.0, 0.0008, 0.01]},
            },
        )
        res = live.resolve_by_edge_fingerprint(_DOC, _edge_ref())
        assert res.method == "edge_fingerprint"
        assert res.entity is near

    def test_unreadable_edges_skipped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        bad, good = object(), object()
        geoms = {
            bad: None,  # _read_edge_geometry returns None → skipped
            good: _edge_geom((0.0, 0.0, 0.0), (0.0, 0.0, 0.01)),
        }
        monkeypatch.setattr(live, "_iter_live_edges", lambda doc: [bad, good])
        monkeypatch.setattr(live, "_read_edge_geometry", lambda e: geoms[e])
        res = live.resolve_by_edge_fingerprint(_DOC, _edge_ref())
        assert res.method == "edge_fingerprint"
        assert res.entity is good

    def test_reversed_endpoints_match(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Edge with start/end swapped still matches (unordered endpoint gate)."""
        hit = object()
        _patch_edges(
            monkeypatch,
            {
                hit: _edge_geom((0.0, 0.0, 0.01), (0.0, 0.0, 0.0)),  # reversed
            },
        )
        res = live.resolve_by_edge_fingerprint(_DOC, _edge_ref())
        assert res.method == "edge_fingerprint"
        assert res.entity is hit


# ---------------------------------------------------------------------------
# resolve_edge_ref tier-2 integration — mirrors TestResolveRefTier2
# ---------------------------------------------------------------------------


class TestResolveEdgeRefTier2:
    def test_persist_miss_then_fingerprint(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_ext(monkeypatch, _FakeExt(resolve=(object(), 1)))  # Deleted
        hit = object()
        _patch_edges(
            monkeypatch,
            {
                hit: _edge_geom((0.0, 0.0, 0.0), (0.0, 0.0, 0.01)),
            },
        )
        res = live.resolve_edge_ref(_DOC, _edge_ref(persist_id=b"tok"))
        assert res.method == "edge_fingerprint"
        assert res.entity is hit
        assert res.persist is not None and res.persist.status_name == "Deleted"

    def test_no_persist_id_uses_fingerprint(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        hit = object()
        _patch_edges(
            monkeypatch,
            {
                hit: _edge_geom((0.0, 0.0, 0.0), (0.0, 0.0, 0.01)),
            },
        )
        res = live.resolve_edge_ref(_DOC, _edge_ref(persist_id=None))
        assert res.method == "edge_fingerprint"
        assert res.entity is hit
        assert res.persist is None

    def test_allow_fingerprint_false_skips_tier2(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_ext(monkeypatch, _FakeExt(resolve=(object(), 1)))  # Deleted
        monkeypatch.setattr(live, "_iter_live_edges", _unexpected_edge_walk)
        res = live.resolve_edge_ref(
            _DOC, _edge_ref(persist_id=b"tok"), allow_fingerprint=False
        )
        assert res.method == "unresolved"
        assert res.entity is None
        assert "not attempted" in (res.note or "")


# ---------------------------------------------------------------------------
# Edge-match predicate (O2) — pure, SW-free "are these the same edge?" contract
# that worker S1 wires as tier-2 of resolve_edge_ref. See _edge_match.py for the
# spec; these are the adversarial cases that pin its behavior and document the
# chord-capture false-positive class.
# ---------------------------------------------------------------------------

from ai_sw_bridge.selection._edge_match import (  # noqa: E402
    chord_direction_error,
    edge_match_score,
    edges_match,
)


def _edge(start, end, *, length=None, midpoint=None):
    """Build an edge dict in the manifest / BrepEdge.to_dict shape."""
    d: dict = {"start": list(start), "end": list(end)}
    if length is not None:
        d["length"] = length
    if midpoint is not None:
        d["midpoint"] = list(midpoint)
    return d


# A straight edge along +X, 20 mm long, with chord-derived length/midpoint
# (exactly what interrogator._probe_edge captures today).
def _straight():
    return _edge(
        (0.0, 0.0, 0.0), (0.02, 0.0, 0.0), length=0.02, midpoint=(0.01, 0.0, 0.0)
    )


class TestEdgeMatchPredicate:
    def test_identity_matches_with_zero_key(self) -> None:
        key = edge_match_score(_straight(), _straight())
        assert key == (0.0, 0.0, 0.0)
        assert edges_match(_straight(), _straight())

    def test_reversed_orientation_matches(self) -> None:
        """Edges are undirected: the same edge with start/end swapped matches."""
        fwd = _straight()
        rev = _edge(
            (0.02, 0.0, 0.0), (0.0, 0.0, 0.0), length=0.02, midpoint=(0.01, 0.0, 0.0)
        )
        assert edges_match(fwd, rev)
        assert edge_match_score(fwd, rev) == (0.0, 0.0, 0.0)

    def test_shared_one_endpoint_differs(self) -> None:
        a = _straight()
        b = _edge((0.0, 0.0, 0.0), (0.0, 0.02, 0.0))  # shares start, different end
        assert edge_match_score(a, b) is None

    def test_translated_edge_differs(self) -> None:
        a = _straight()
        b = _edge((0.0, 0.01, 0.0), (0.02, 0.01, 0.0))  # shifted 10 mm in +Y
        assert edge_match_score(a, b) is None

    def test_endpoint_within_tol_matches(self) -> None:
        a = _straight()
        b = _edge((0.0, 0.0, 0.0), (0.02, 0.0005, 0.0))  # end drifted 0.5 mm < 1 mm
        # length/midpoint omitted so only the endpoint gate applies.
        assert edges_match(a, b)

    def test_endpoint_outside_tol_differs(self) -> None:
        a = _straight()
        b = _edge((0.0, 0.0, 0.0), (0.02, 0.002, 0.0))  # end drifted 2 mm > 1 mm
        assert edge_match_score(a, b) is None

    def test_straight_vs_arc_collide_under_chord_capture(self) -> None:
        """KNOWN false-positive: a straight edge and a semicircular arc sharing
        the same two vertices are indistinguishable when both carry only the
        *chord*-derived length/midpoint the interrogator captures today. This
        test documents the capture gap (not a bug in the predicate)."""
        straight = _straight()
        # Arc as captured today: chord length & chord midpoint — identical fields.
        arc_chord = _edge(
            (0.0, 0.0, 0.0), (0.02, 0.0, 0.0), length=0.02, midpoint=(0.01, 0.0, 0.0)
        )
        assert edges_match(straight, arc_chord)  # collision, by design of the data

    def test_true_curve_mid_separates_straight_from_arc(self) -> None:
        """The predicate is forward-correct: feed a *true* arc length and curve
        midpoint (a ~1-line interrogator follow-up away) and it cleanly rejects
        the straight/arc collision above — with ZERO predicate rework."""
        straight = _straight()
        # Semicircle, r = 10 mm, bulging +Y: arc length = pi*r, apex at (0.01, 0.01, 0).
        arc_true = _edge(
            (0.0, 0.0, 0.0),
            (0.02, 0.0, 0.0),
            length=math.pi * 0.01,
            midpoint=(0.01, 0.01, 0.0),
        )
        assert edge_match_score(straight, arc_true) is None

    def test_length_gate_is_load_bearing(self) -> None:
        """With matching endpoints + midpoint, a length delta alone rejects —
        proving length is an independent gate once a true arc length is captured."""
        a = _straight()
        b = _edge(
            (0.0, 0.0, 0.0), (0.02, 0.0, 0.0), length=0.025, midpoint=(0.01, 0.0, 0.0)
        )
        assert edge_match_score(a, b) is None

    def test_partial_dicts_match_on_endpoints_only(self) -> None:
        """Optional length/midpoint gates are skipped when either side omits
        them, so endpoint-only dicts still resolve."""
        a = _edge((0.0, 0.0, 0.0), (0.02, 0.0, 0.0))
        b = _edge((0.0, 0.0, 0.0), (0.02, 0.0, 0.0))
        assert edges_match(a, b)

    def test_malformed_returns_none_never_raises(self) -> None:
        assert (
            edge_match_score({"start": [0, 0, 0]}, _straight()) is None
        )  # missing end
        assert edge_match_score({"start": "bad", "end": [0, 0, 0]}, _straight()) is None
        assert (
            edge_match_score(_straight(), {"start": [0, 0], "end": [0, 0, 0]}) is None
        )

    def test_score_orders_closer_candidate_first(self) -> None:
        target = _edge((0.0, 0.0, 0.0), (0.02, 0.0, 0.0))
        near = _edge((0.0, 0.0, 0.0), (0.02, 0.0001, 0.0))  # 0.1 mm
        far = _edge((0.0, 0.0, 0.0), (0.02, 0.0008, 0.0))  # 0.8 mm
        k_near = edge_match_score(target, near)
        k_far = edge_match_score(target, far)
        assert k_near is not None and k_far is not None
        assert k_near < k_far  # smaller key == better candidate (S1 keeps the min)


class TestChordDirectionError:
    def test_parallel_is_near_zero(self) -> None:
        a = _edge((0.0, 0.0, 0.0), (0.02, 0.0, 0.0))
        b = _edge((0.0, 0.01, 0.0), (0.02, 0.01, 0.0))  # parallel, offset
        err = chord_direction_error(a, b)
        assert err is not None and err < 1e-9

    def test_antiparallel_is_also_near_zero(self) -> None:
        """Sign-agnostic: a reversed chord is the same direction for an edge."""
        a = _edge((0.0, 0.0, 0.0), (0.02, 0.0, 0.0))
        b = _edge((0.02, 0.0, 0.0), (0.0, 0.0, 0.0))
        err = chord_direction_error(a, b)
        assert err is not None and err < 1e-9

    def test_perpendicular_is_one(self) -> None:
        a = _edge((0.0, 0.0, 0.0), (0.02, 0.0, 0.0))
        b = _edge((0.0, 0.0, 0.0), (0.0, 0.02, 0.0))
        err = chord_direction_error(a, b)
        assert err is not None and abs(err - 1.0) < 1e-9

    def test_degenerate_chord_returns_none(self) -> None:
        a = _edge((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))  # zero-length chord
        b = _edge((0.0, 0.0, 0.0), (0.02, 0.0, 0.0))
        assert chord_direction_error(a, b) is None
