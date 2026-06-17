"""Offline tests for the mate_reference feature handler (W63 lane 1).

Tests the Mode-A quarantine stub, Mode-B multi-mark selection pipeline,
and the verify-gate (feature-node delta + GetTypeName2 == "MateReference").

Fake-COM pattern mirrors ``test_wave5_handlers.py`` / ``test_mutate_feature_add.py``:
each fake patches the COM seam on the lane module itself (not on ``mutate``).
"""

from __future__ import annotations

from typing import Any

import pytest

from ai_sw_bridge.features import mate_reference as mr


# ---------------------------------------------------------------------------
# Fake COM objects
# ---------------------------------------------------------------------------


class _FakeEntity:
    """Stand-in for a resolved live entity (face/edge)."""

    def __init__(self, name: str = "entity") -> None:
        self.name = name


class _FakeFeatureNode:
    """Stand-in for a feature node returned by ``GetFeatures(False)``."""

    def __init__(self, name: str, type_name: str) -> None:
        self.Name = name
        self._type_name = type_name

    def GetTypeName2(self) -> str:
        return self._type_name


class _FakeFeatureManager:
    """Tracks feature nodes; ``CreateFeature`` bumps the count."""

    def __init__(self, initial_nodes: list[_FakeFeatureNode] | None = None) -> None:
        self._nodes: list[_FakeFeatureNode] = list(initial_nodes or [])

    def GetFeatures(self, top_level_only: bool) -> tuple:
        return tuple(self._nodes)

    def add_node(self, node: _FakeFeatureNode) -> None:
        self._nodes.append(node)


class _FakeDoc:
    """Minimal fake ``IModelDoc2`` for mate_reference handler testing."""

    def __init__(self, fm: _FakeFeatureManager | None = None) -> None:
        self.FeatureManager = fm or _FakeFeatureManager()
        self._clear_calls: list[bool] = []
        self._rebuild_calls: list[bool] = []
        self._insert_mate_ref_called = False
        self._insert_mate_ref_result: Any = True
        self._insert_mate_ref_raises: Exception | None = None

    def ClearSelection2(self, top: bool) -> None:
        self._clear_calls.append(top)

    def ForceRebuild3(self, verify: bool) -> None:
        self._rebuild_calls.append(verify)

    def InsertMateReference(self):
        self._insert_mate_ref_called = True
        if self._insert_mate_ref_raises is not None:
            raise self._insert_mate_ref_raises
        return self._insert_mate_ref_result


def _seed_nodes(n: int = 5) -> list[_FakeFeatureNode]:
    return [_FakeFeatureNode(f"Feat{i}", "Extrusion") for i in range(n)]


def _patch_selection(
    monkeypatch: pytest.MonkeyPatch,
    *,
    resolve_ok: bool = True,
    select_ok: bool = True,
) -> dict[str, list]:
    """Patch resolve_manifest_face / resolve_ref / select_entity on the lane module."""
    calls: dict[str, list] = {"resolve_face": [], "resolve_ref": [], "select": []}
    entity = _FakeEntity()

    class _FakeRes:
        def __init__(self, ent: Any, method: str) -> None:
            self.entity = ent
            self.method = method

    def _fake_resolve_face(doc: Any, ref: Any, **kw: Any) -> _FakeRes:
        calls["resolve_face"].append(ref)
        return _FakeRes(entity if resolve_ok else None, "persist_id" if resolve_ok else "unresolved")

    def _fake_resolve_ref(doc: Any, ref: Any, **kw: Any) -> _FakeRes:
        calls["resolve_ref"].append(ref)
        return _FakeRes(entity if resolve_ok else None, "persist_id" if resolve_ok else "unresolved")

    def _fake_select(ent: Any, *, append: bool = False, mark: int = 0) -> bool:
        calls["select"].append({"entity": ent, "append": append, "mark": mark})
        return select_ok

    monkeypatch.setattr(mr, "resolve_manifest_face", _fake_resolve_face)
    monkeypatch.setattr(mr, "resolve_ref", _fake_resolve_ref)
    monkeypatch.setattr(mr, "select_entity", _fake_select)
    return calls


# ---------------------------------------------------------------------------
# Mode-A quarantine tests
# ---------------------------------------------------------------------------


class TestModeAQuarantined:
    """Mode-A must return None (no-op stub) — no speculative enum probing."""

    def test_mode_a_returns_none(self) -> None:
        doc = _FakeDoc()
        result = mr._try_mode_a(doc, {"type": "mate_reference"}, {})
        assert result is None

    def test_mode_a_does_not_call_any_com(self) -> None:
        doc = _FakeDoc()
        mr._try_mode_a(doc, {"type": "mate_reference", "entities": []}, {})
        assert not doc._insert_mate_ref_called
        assert not doc._rebuild_calls


# ---------------------------------------------------------------------------
# Mode-B success path
# ---------------------------------------------------------------------------


class TestModeBSuccess:
    def test_single_entity_primary(self, monkeypatch: pytest.MonkeyPatch) -> None:
        nodes = _seed_nodes(5)
        fm = _FakeFeatureManager(nodes)
        doc = _FakeDoc(fm)
        calls = _patch_selection(monkeypatch)

        feature = {
            "type": "mate_reference",
            "entities": [{"ref": {"face": "F1"}, "role": "primary"}],
        }
        result = mr._try_mode_b(doc, feature, {})
        assert result is True
        assert doc._insert_mate_ref_called
        assert len(calls["select"]) == 1
        assert calls["select"][0]["append"] is False
        assert calls["select"][0]["mark"] == 1

    def test_three_entities_multi_mark(self, monkeypatch: pytest.MonkeyPatch) -> None:
        nodes = _seed_nodes(5)
        fm = _FakeFeatureManager(nodes)
        doc = _FakeDoc(fm)
        calls = _patch_selection(monkeypatch)

        feature = {
            "type": "mate_reference",
            "entities": [
                {"ref": {"face": "F1"}, "role": "primary"},
                {"ref": {"face": "F2"}, "role": "secondary"},
                {"ref": {"face": "F3"}, "role": "tertiary"},
            ],
        }
        result = mr._try_mode_b(doc, feature, {})
        assert result is True
        assert doc._insert_mate_ref_called
        assert len(calls["select"]) == 3
        assert calls["select"][0] == {"entity": calls["select"][0]["entity"], "append": False, "mark": 1}
        assert calls["select"][1] == {"entity": calls["select"][1]["entity"], "append": True, "mark": 2}
        assert calls["select"][2] == {"entity": calls["select"][2]["entity"], "append": True, "mark": 4}

    def test_two_entities_primary_secondary(self, monkeypatch: pytest.MonkeyPatch) -> None:
        nodes = _seed_nodes(3)
        fm = _FakeFeatureManager(nodes)
        doc = _FakeDoc(fm)
        calls = _patch_selection(monkeypatch)

        feature = {
            "type": "mate_reference",
            "entities": [
                {"ref": {"face": "F1"}, "role": "primary"},
                {"ref": {"face": "F2"}, "role": "secondary"},
            ],
        }
        result = mr._try_mode_b(doc, feature, {})
        assert result is True
        assert len(calls["select"]) == 2
        assert calls["select"][0]["mark"] == 1
        assert calls["select"][1]["mark"] == 2


# ---------------------------------------------------------------------------
# Mode-B failure paths
# ---------------------------------------------------------------------------


class TestModeBFailure:
    def test_no_entities_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_selection(monkeypatch)
        doc = _FakeDoc()
        result = mr._try_mode_b(doc, {"type": "mate_reference"}, {})
        assert result is None

    def test_empty_entities_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_selection(monkeypatch)
        doc = _FakeDoc()
        result = mr._try_mode_b(doc, {"type": "mate_reference", "entities": []}, {})
        assert result is None

    def test_entity_without_ref_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_selection(monkeypatch)
        doc = _FakeDoc()
        feature = {
            "type": "mate_reference",
            "entities": [{"role": "primary"}],
        }
        result = mr._try_mode_b(doc, feature, {})
        assert result is None

    def test_unresolved_entity_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_selection(monkeypatch, resolve_ok=False)
        doc = _FakeDoc()
        feature = {
            "type": "mate_reference",
            "entities": [{"ref": {"face": "F1"}, "role": "primary"}],
        }
        result = mr._try_mode_b(doc, feature, {})
        assert result is None

    def test_select_failure_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_selection(monkeypatch, select_ok=False)
        doc = _FakeDoc()
        feature = {
            "type": "mate_reference",
            "entities": [{"ref": {"face": "F1"}, "role": "primary"}],
        }
        result = mr._try_mode_b(doc, feature, {})
        assert result is None

    def test_insert_mate_ref_exception_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_selection(monkeypatch)
        nodes = _seed_nodes(3)
        fm = _FakeFeatureManager(nodes)
        doc = _FakeDoc(fm)
        doc._insert_mate_ref_raises = RuntimeError("COM error")
        feature = {
            "type": "mate_reference",
            "entities": [{"ref": {"face": "F1"}, "role": "primary"}],
        }
        result = mr._try_mode_b(doc, feature, {})
        assert result is None

    def test_unknown_role_skipped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = _patch_selection(monkeypatch)
        nodes = _seed_nodes(3)
        fm = _FakeFeatureManager(nodes)
        doc = _FakeDoc(fm)
        feature = {
            "type": "mate_reference",
            "entities": [{"ref": {"face": "F1"}, "role": "quarternary"}],
        }
        result = mr._try_mode_b(doc, feature, {})
        assert result is None
        assert len(calls["select"]) == 0


# ---------------------------------------------------------------------------
# Entity-resolution dispatch (dict vs DurableRef)
# ---------------------------------------------------------------------------


class TestEntityResolution:
    def test_dict_ref_uses_resolve_manifest_face(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = _patch_selection(monkeypatch)
        nodes = _seed_nodes(3)
        fm = _FakeFeatureManager(nodes)
        doc = _FakeDoc(fm)
        face_dict = {"feature": "Box", "role": "top"}
        feature = {
            "type": "mate_reference",
            "entities": [{"ref": face_dict, "role": "primary"}],
        }
        mr._try_mode_b(doc, feature, {})
        assert len(calls["resolve_face"]) == 1
        assert calls["resolve_face"][0] is face_dict
        assert len(calls["resolve_ref"]) == 0

    def test_object_ref_uses_resolve_ref(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = _patch_selection(monkeypatch)
        nodes = _seed_nodes(3)
        fm = _FakeFeatureManager(nodes)
        doc = _FakeDoc(fm)

        class _FakeDurableRef:
            persist_id = b"\x01\x02"
            fingerprint = "abc123"

        dref = _FakeDurableRef()
        feature = {
            "type": "mate_reference",
            "entities": [{"ref": dref, "role": "primary"}],
        }
        mr._try_mode_b(doc, feature, {})
        assert len(calls["resolve_ref"]) == 1
        assert calls["resolve_ref"][0] is dref
        assert len(calls["resolve_face"]) == 0


# ---------------------------------------------------------------------------
# Verify-gate tests
# ---------------------------------------------------------------------------


class TestVerifyGate:
    """The W21/W42 ghost trap: call_ok + name + 'no error' is NOT proof."""

    def test_no_delta_fails(self) -> None:
        nodes = _seed_nodes(5)
        fm = _FakeFeatureManager(nodes)
        doc = _FakeDoc(fm)
        ok, msg = mr._verify(doc, before=5)
        assert ok is False
        assert "no feature-node delta" in msg

    def test_delta_with_correct_type_succeeds(self) -> None:
        nodes = _seed_nodes(5)
        nodes.append(_FakeFeatureNode("MateRef1", "MateReference"))
        fm = _FakeFeatureManager(nodes)
        doc = _FakeDoc(fm)
        ok, msg = mr._verify(doc, before=5)
        assert ok is True
        assert "mode_b" in msg

    def test_delta_without_correct_type_fails(self) -> None:
        nodes = _seed_nodes(5)
        nodes.append(_FakeFeatureNode("SomethingElse", "Extrusion"))
        fm = _FakeFeatureManager(nodes)
        doc = _FakeDoc(fm)
        ok, msg = mr._verify(doc, before=5)
        assert ok is False
        assert "no MateReference node found" in msg


# ---------------------------------------------------------------------------
# End-to-end handler tests
# ---------------------------------------------------------------------------


class TestCreateMateReference:
    def test_full_pipeline_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        nodes = _seed_nodes(5)
        fm = _FakeFeatureManager(nodes)
        doc = _FakeDoc(fm)
        _patch_selection(monkeypatch)

        feature = {
            "type": "mate_reference",
            "name": "MateRef-1",
            "entities": [
                {"ref": {"face": "F1"}, "role": "primary"},
                {"ref": {"face": "F2"}, "role": "secondary"},
            ],
        }

        def _add_node_on_insert():
            fm.add_node(_FakeFeatureNode("MateRef1", "MateReference"))
            return True

        doc.InsertMateReference = _add_node_on_insert

        ok, note = mr.create_mate_reference(doc, feature, {})
        assert ok is True
        assert note is not None and "mode_b" in note

    def test_full_pipeline_verify_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        nodes = _seed_nodes(5)
        fm = _FakeFeatureManager(nodes)
        doc = _FakeDoc(fm)
        _patch_selection(monkeypatch)

        feature = {
            "type": "mate_reference",
            "entities": [{"ref": {"face": "F1"}, "role": "primary"}],
        }
        ok, err = mr.create_mate_reference(doc, feature, {})
        assert ok is False
        assert err is not None

    def test_all_modes_fail(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_selection(monkeypatch, resolve_ok=False)
        nodes = _seed_nodes(3)
        fm = _FakeFeatureManager(nodes)
        doc = _FakeDoc(fm)

        feature = {
            "type": "mate_reference",
            "entities": [{"ref": {"face": "F1"}, "role": "primary"}],
        }
        ok, err = mr.create_mate_reference(doc, feature, {})
        assert ok is False
        assert "all modes failed" in err


# ---------------------------------------------------------------------------
# Callable-or-property guard
# ---------------------------------------------------------------------------


class TestCallableOrPropertyGuard:
    """InsertMateReference may be a property on late-bound IDispatch."""

    def test_insert_as_property(self, monkeypatch: pytest.MonkeyPatch) -> None:
        nodes = _seed_nodes(3)
        fm = _FakeFeatureManager(nodes)
        doc = _FakeDoc(fm)
        _patch_selection(monkeypatch)

        class _PropDoc(_FakeDoc):
            InsertMateReference = True

        pdoc = _PropDoc(fm)
        feature = {
            "type": "mate_reference",
            "entities": [{"ref": {"face": "F1"}, "role": "primary"}],
        }
        result = mr._try_mode_b(pdoc, feature, {})
        assert result is True


# ---------------------------------------------------------------------------
# Never-raise contract (§0 HARD RULE)
# ---------------------------------------------------------------------------


class TestNeverRaise:
    """§0: Return (False, reason) on any failure — NEVER raise."""

    def test_unexpected_exception_in_count_nodes(self) -> None:
        class _BrokenDoc:
            class FeatureManager:
                def GetFeatures(self, top_level: bool):
                    raise RuntimeError("COM link severed")

        doc = _BrokenDoc()
        ok, err = mr.create_mate_reference(doc, {"type": "mate_reference", "entities": []}, {})
        assert ok is False
        assert "unexpected error" in err

    def test_unexpected_exception_type_error(self) -> None:
        ok, err = mr.create_mate_reference(None, None, None)  # type: ignore[arg-type]
        assert ok is False
        assert err is not None
