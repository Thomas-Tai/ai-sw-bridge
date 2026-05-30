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
# Package re-exports
# ---------------------------------------------------------------------------


def test_package_reexports() -> None:
    from ai_sw_bridge import selection

    assert selection.capture_persist_id is live.capture_persist_id
    assert selection.resolve_ref is live.resolve_ref
    assert selection.PersistResolution is live.PersistResolution
