"""Tests for ai_sw_bridge.selection.live — the live-COM bridge for DurableRef.

The module's only dependency on SOLIDWORKS is the ``com.earlybind`` seam
(``typed_extension`` / ``typed``). These tests monkeypatch that seam with
fakes, so the capture/resolve/select contract is exercised without pywin32 or
a live SW seat — mirroring the proven S-EARLYBIND round-trip shapes (the
``[out]`` status arrives as the 2nd tuple element).
"""

from __future__ import annotations

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
    return {"normal": list(normal), "centroid": list(centroid), "area_mm2": area,
            "bbox": ([0, 0, 0], [0, 0, 0])}


def _patch_faces(monkeypatch, face_to_geom: dict) -> None:
    """Make _iter_live_faces yield the keys and read_face_geometry map them."""
    faces = list(face_to_geom)
    monkeypatch.setattr(live, "_iter_live_faces", lambda doc: faces)
    monkeypatch.setattr(live, "read_face_geometry", lambda f: face_to_geom[f])


class TestResolveByFingerprint:
    def test_exact_hash_match(self, monkeypatch: pytest.MonkeyPatch) -> None:
        far = object()
        hit = object()
        _patch_faces(monkeypatch, {
            far: _geom((1, 0, 0), (0.01, 0, 0), 100.0),
            hit: _geom(_GEOM["normal"], _GEOM["centroid"], _GEOM["area_mm2"]),
        })
        r = live.resolve_by_fingerprint(_DOC, _ref())
        assert r.method == "fingerprint"
        assert r.entity is hit

    def test_geometry_proximity_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Same normal, centroid 0.5 mm off, different area -> hash differs but
        # within the lossy tolerances.
        near = object()
        _patch_faces(monkeypatch, {
            near: _geom((0.0, 0.0, 1.0), (0.0, 0.0, 0.0055), 2501.0),
        })
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
        geoms = {bad: None, good: _geom(_GEOM["normal"], _GEOM["centroid"], _GEOM["area_mm2"])}
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
        doc = types.SimpleNamespace(GetBodies2=(object(), good))  # object() has no GetFaces
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
    def test_persist_fail_then_fingerprint(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_ext(monkeypatch, _FakeExt(resolve=(object(), 1)))  # Deleted
        hit = object()
        _patch_faces(monkeypatch, {
            hit: _geom(_GEOM["normal"], _GEOM["centroid"], _GEOM["area_mm2"]),
        })
        r = live.resolve_ref(_DOC, _ref(persist_id=b"tok"))
        assert r.method == "fingerprint"
        assert r.entity is hit
        assert r.persist is not None and r.persist.status_name == "Deleted"

    def test_no_persist_id_uses_fingerprint(self, monkeypatch: pytest.MonkeyPatch) -> None:
        hit = object()
        _patch_faces(monkeypatch, {
            hit: _geom(_GEOM["normal"], _GEOM["centroid"], _GEOM["area_mm2"]),
        })
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
# Package re-exports
# ---------------------------------------------------------------------------


def test_package_reexports() -> None:
    from ai_sw_bridge import selection

    assert selection.capture_persist_id is live.capture_persist_id
    assert selection.resolve_ref is live.resolve_ref
    assert selection.PersistResolution is live.PersistResolution


# ---------------------------------------------------------------------------
# resolve_edge_ref — tier-1 persist only (no edge fingerprint in v1)
# ---------------------------------------------------------------------------


def _edge_ref(persist_id=b"\x01\x02"):
    return DurableEdgeRef(
        persist_id=persist_id,
        start=(0.0, 0.0, 0.0),
        end=(0.0, 0.0, 0.01),
        length=0.01,
    )


class TestResolveEdgeRef:
    def test_persist_hit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ent = _FakeEntity()
        _patch_ext(monkeypatch, _FakeExt(resolve=(ent, 0)))
        res = live.resolve_edge_ref(_DOC, _edge_ref())
        assert res.method == "persist_id"
        assert res.entity is ent

    def test_persist_deleted_is_unresolved(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_ext(monkeypatch, _FakeExt(resolve=(object(), 1)))  # status Deleted
        res = live.resolve_edge_ref(_DOC, _edge_ref())
        assert res.method == "unresolved"
        assert res.entity is None
        assert res.persist is not None and not res.persist.ok

    def test_no_persist_id_is_unresolved(self) -> None:
        res = live.resolve_edge_ref(_DOC, _edge_ref(persist_id=None))
        assert res.method == "unresolved"
        assert res.entity is None
        assert "no persist_id" in (res.note or "")
