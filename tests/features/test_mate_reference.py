"""Offline tests for the mate_reference feature handler (W63 lane 1).

Tests the Mode-A quarantine stub, the Mode-B parametric InsertMateReference2
pipeline (12-arg, entities passed directly — NO selection marks), and the
verify-gate (feature-node delta + GetTypeName2 containing "materef").

Fake-COM pattern mirrors ``test_wave5_handlers.py``: each fake patches the COM
seam on the lane module itself. ``typed`` / ``typed_qi`` / ``wrapper_module``
are patched to identity so the parametric call dispatches against the fake
FeatureManager without touching gen_py.
"""

from __future__ import annotations

from typing import Any

import pytest

from ai_sw_bridge.features import mate_reference as mr


# ---------------------------------------------------------------------------
# Fake COM objects
# ---------------------------------------------------------------------------


class _FakeEntity:
    """Stand-in for a resolved live entity (face/edge), typed to IEntity."""

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
    """Records InsertMateReference2 calls; can add a node / raise on insert."""

    def __init__(self, initial_nodes: list[_FakeFeatureNode] | None = None) -> None:
        self._nodes: list[_FakeFeatureNode] = list(initial_nodes or [])
        self.insert_calls: list[tuple] = []
        self._insert_result: Any = True        # truthy IFeature stand-in
        self._insert_raises: Exception | None = None
        self._node_to_add: _FakeFeatureNode | None = None

    def GetFeatures(self, top_level_only: bool) -> tuple:
        return tuple(self._nodes)

    def add_node(self, node: _FakeFeatureNode) -> None:
        self._nodes.append(node)

    def InsertMateReference2(self, *args: Any) -> Any:
        self.insert_calls.append(args)
        if self._insert_raises is not None:
            raise self._insert_raises
        if self._node_to_add is not None:
            self._nodes.append(self._node_to_add)
        return self._insert_result


class _FakeDoc:
    """Minimal fake ``IModelDoc2`` for mate_reference handler testing."""

    def __init__(self, fm: _FakeFeatureManager | None = None) -> None:
        self._fm = fm or _FakeFeatureManager()
        self._rebuild_calls: list[bool] = []

    @property
    def FeatureManager(self) -> _FakeFeatureManager:
        return self._fm

    def ForceRebuild3(self, verify: bool) -> None:
        self._rebuild_calls.append(verify)


def _seed_nodes(n: int = 5) -> list[_FakeFeatureNode]:
    return [_FakeFeatureNode(f"Feat{i}", "Extrusion") for i in range(n)]


def _patch_com(
    monkeypatch: pytest.MonkeyPatch,
    *,
    resolve_ok: bool = True,
) -> dict[str, list]:
    """Patch the resolver + early-bind seam on the lane module.

    ``typed`` / ``typed_qi`` become identity (no QI, no gen_py); the
    resolved entity flows straight through to the InsertMateReference2 args.
    """
    calls: dict[str, list] = {"resolve_face": [], "resolve_ref": []}

    class _FakeRes:
        def __init__(self, ent: Any, method: str) -> None:
            self.entity = ent
            self.method = method

    def _fake_resolve_face(doc: Any, ref: Any, **kw: Any) -> _FakeRes:
        calls["resolve_face"].append(ref)
        ent = _FakeEntity(str(ref)) if resolve_ok else None
        return _FakeRes(ent, "persist_id" if resolve_ok else "unresolved")

    def _fake_resolve_ref(doc: Any, ref: Any, **kw: Any) -> _FakeRes:
        calls["resolve_ref"].append(ref)
        ent = _FakeEntity(str(ref)) if resolve_ok else None
        return _FakeRes(ent, "persist_id" if resolve_ok else "unresolved")

    monkeypatch.setattr(mr, "resolve_manifest_face", _fake_resolve_face)
    monkeypatch.setattr(mr, "resolve_ref", _fake_resolve_ref)
    monkeypatch.setattr(mr, "typed", lambda obj, iface, **kw: obj)
    monkeypatch.setattr(mr, "typed_qi", lambda obj, iface, **kw: obj)
    monkeypatch.setattr(mr, "wrapper_module", lambda: None)
    return calls


def _is_real_entity(arg: Any) -> bool:
    """An InsertMateReference2 positional arg holds a real entity (not a null VARIANT)."""
    return isinstance(arg, _FakeEntity)


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
        assert doc.FeatureManager.insert_calls == []
        assert not doc._rebuild_calls


# ---------------------------------------------------------------------------
# Mode-B success path — parametric 12-arg InsertMateReference2
# ---------------------------------------------------------------------------


class TestModeBSuccess:
    def test_single_entity_primary(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fm = _FakeFeatureManager(_seed_nodes(5))
        doc = _FakeDoc(fm)
        _patch_com(monkeypatch)

        feature = {
            "type": "mate_reference",
            "entities": [{"ref": {"face": "F1"}, "role": "primary"}],
        }
        result = mr._try_mode_b(doc, feature, {})
        assert result is True
        assert len(fm.insert_calls) == 1
        args = fm.insert_calls[0]
        assert len(args) == 12
        assert args[0] == "Default"        # name (none supplied)
        assert _is_real_entity(args[1])    # primary entity present
        assert args[2] == 0 and args[3] == 0 and args[4] is False
        assert not _is_real_entity(args[5])   # secondary nulled
        assert not _is_real_entity(args[9])   # tertiary nulled

    def test_three_entities_all_slots(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fm = _FakeFeatureManager(_seed_nodes(5))
        doc = _FakeDoc(fm)
        _patch_com(monkeypatch)

        feature = {
            "type": "mate_reference",
            "name": "Tri",
            "entities": [
                {"ref": {"face": "F1"}, "role": "primary"},
                {"ref": {"face": "F2"}, "role": "secondary"},
                {"ref": {"face": "F3"}, "role": "tertiary"},
            ],
        }
        result = mr._try_mode_b(doc, feature, {})
        assert result is True
        args = fm.insert_calls[0]
        assert args[0] == "Tri"
        assert _is_real_entity(args[1])   # primary  @ 1
        assert _is_real_entity(args[5])   # secondary @ 5
        assert _is_real_entity(args[9])   # tertiary  @ 9

    def test_two_entities_primary_secondary(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fm = _FakeFeatureManager(_seed_nodes(3))
        doc = _FakeDoc(fm)
        _patch_com(monkeypatch)

        feature = {
            "type": "mate_reference",
            "entities": [
                {"ref": {"face": "F1"}, "role": "primary"},
                {"ref": {"face": "F2"}, "role": "secondary"},
            ],
        }
        result = mr._try_mode_b(doc, feature, {})
        assert result is True
        args = fm.insert_calls[0]
        assert _is_real_entity(args[1])
        assert _is_real_entity(args[5])
        assert not _is_real_entity(args[9])  # tertiary nulled

    def test_force_rebuild_called(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fm = _FakeFeatureManager(_seed_nodes(3))
        doc = _FakeDoc(fm)
        _patch_com(monkeypatch)
        feature = {
            "type": "mate_reference",
            "entities": [{"ref": {"face": "F1"}, "role": "primary"}],
        }
        mr._try_mode_b(doc, feature, {})
        assert doc._rebuild_calls == [False]


# ---------------------------------------------------------------------------
# Mode-B failure paths
# ---------------------------------------------------------------------------


class TestModeBFailure:
    def test_no_entities_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_com(monkeypatch)
        doc = _FakeDoc()
        result = mr._try_mode_b(doc, {"type": "mate_reference"}, {})
        assert result is None

    def test_empty_entities_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_com(monkeypatch)
        doc = _FakeDoc()
        result = mr._try_mode_b(doc, {"type": "mate_reference", "entities": []}, {})
        assert result is None

    def test_entity_without_ref_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_com(monkeypatch)
        doc = _FakeDoc()
        feature = {"type": "mate_reference", "entities": [{"role": "primary"}]}
        result = mr._try_mode_b(doc, feature, {})
        assert result is None

    def test_unresolved_entity_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_com(monkeypatch, resolve_ok=False)
        doc = _FakeDoc()
        feature = {
            "type": "mate_reference",
            "entities": [{"ref": {"face": "F1"}, "role": "primary"}],
        }
        result = mr._try_mode_b(doc, feature, {})
        assert result is None

    def test_no_primary_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Secondary-only spec (no primary entity) must fail before the call."""
        fm = _FakeFeatureManager(_seed_nodes(3))
        doc = _FakeDoc(fm)
        _patch_com(monkeypatch)
        feature = {
            "type": "mate_reference",
            "entities": [{"ref": {"face": "F2"}, "role": "secondary"}],
        }
        result = mr._try_mode_b(doc, feature, {})
        assert result is None
        assert fm.insert_calls == []

    def test_insert_exception_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_com(monkeypatch)
        fm = _FakeFeatureManager(_seed_nodes(3))
        fm._insert_raises = RuntimeError("COM error")
        doc = _FakeDoc(fm)
        feature = {
            "type": "mate_reference",
            "entities": [{"ref": {"face": "F1"}, "role": "primary"}],
        }
        result = mr._try_mode_b(doc, feature, {})
        assert result is None

    def test_unknown_role_skipped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fm = _FakeFeatureManager(_seed_nodes(3))
        doc = _FakeDoc(fm)
        _patch_com(monkeypatch)
        feature = {
            "type": "mate_reference",
            "entities": [{"ref": {"face": "F1"}, "role": "quarternary"}],
        }
        result = mr._try_mode_b(doc, feature, {})
        assert result is None
        assert fm.insert_calls == []


# ---------------------------------------------------------------------------
# Entity-resolution dispatch (dict vs DurableRef)
# ---------------------------------------------------------------------------


class TestEntityResolution:
    def test_dict_ref_uses_resolve_manifest_face(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = _patch_com(monkeypatch)
        fm = _FakeFeatureManager(_seed_nodes(3))
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
        calls = _patch_com(monkeypatch)
        fm = _FakeFeatureManager(_seed_nodes(3))
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
        fm = _FakeFeatureManager(_seed_nodes(5))
        doc = _FakeDoc(fm)
        ok, msg = mr._verify(doc, before=5)
        assert ok is False
        assert "no feature-node delta" in msg

    def test_delta_with_correct_type_succeeds(self) -> None:
        nodes = _seed_nodes(5)
        nodes.append(_FakeFeatureNode("MateRef1", "MateReference"))
        doc = _FakeDoc(_FakeFeatureManager(nodes))
        ok, msg = mr._verify(doc, before=5)
        assert ok is True
        assert "mode_b" in msg

    def test_delta_with_real_kernel_type_succeeds(self) -> None:
        """The kernel's ACTUAL GetTypeName2 is 'MateReferenceGroupFolder'
        (seat-proven W63), not the guessed 'MateReference' — the substring
        'materef' (case-insensitive) catches it (bbox/com_point doctrine)."""
        nodes = _seed_nodes(5)
        nodes.append(_FakeFeatureNode("MR1", "MateReferenceGroupFolder"))
        doc = _FakeDoc(_FakeFeatureManager(nodes))
        ok, msg = mr._verify(doc, before=5)
        assert ok is True

    def test_delta_without_correct_type_fails(self) -> None:
        nodes = _seed_nodes(5)
        nodes.append(_FakeFeatureNode("SomethingElse", "Extrusion"))
        doc = _FakeDoc(_FakeFeatureManager(nodes))
        ok, msg = mr._verify(doc, before=5)
        assert ok is False
        assert "no MateReference node found" in msg


# ---------------------------------------------------------------------------
# End-to-end handler tests
# ---------------------------------------------------------------------------


class TestCreateMateReference:
    def test_full_pipeline_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fm = _FakeFeatureManager(_seed_nodes(5))
        fm._node_to_add = _FakeFeatureNode("MateRef1", "MateReference")
        doc = _FakeDoc(fm)
        _patch_com(monkeypatch)

        feature = {
            "type": "mate_reference",
            "name": "MateRef-1",
            "entities": [
                {"ref": {"face": "F1"}, "role": "primary"},
                {"ref": {"face": "F2"}, "role": "secondary"},
            ],
        }
        ok, note = mr.create_mate_reference(doc, feature, {})
        assert ok is True
        assert note is not None and "mode_b" in note

    def test_full_pipeline_verify_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Insert call succeeds but no node materializes — ghost trap → False."""
        fm = _FakeFeatureManager(_seed_nodes(5))  # no _node_to_add
        doc = _FakeDoc(fm)
        _patch_com(monkeypatch)

        feature = {
            "type": "mate_reference",
            "entities": [{"ref": {"face": "F1"}, "role": "primary"}],
        }
        ok, err = mr.create_mate_reference(doc, feature, {})
        assert ok is False
        assert err is not None

    def test_all_modes_fail(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_com(monkeypatch, resolve_ok=False)
        fm = _FakeFeatureManager(_seed_nodes(3))
        doc = _FakeDoc(fm)
        feature = {
            "type": "mate_reference",
            "entities": [{"ref": {"face": "F1"}, "role": "primary"}],
        }
        ok, err = mr.create_mate_reference(doc, feature, {})
        assert ok is False
        assert "all modes failed" in err


# ---------------------------------------------------------------------------
# CDispatch / typed_qi fallback
# ---------------------------------------------------------------------------


class TestTypedQiFallback:
    """If typed_qi(IFeatureManager) fails, the raw FeatureManager is used."""

    def test_raw_fm_fallback_when_typed_qi_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fm = _FakeFeatureManager(_seed_nodes(3))
        doc = _FakeDoc(fm)
        _patch_com(monkeypatch)

        def _boom(obj: Any, iface: str, **kw: Any) -> Any:
            raise mr.EarlyBindError("E_NOINTERFACE")

        monkeypatch.setattr(mr, "typed_qi", _boom)
        feature = {
            "type": "mate_reference",
            "entities": [{"ref": {"face": "F1"}, "role": "primary"}],
        }
        result = mr._try_mode_b(doc, feature, {})
        # Falls back to the raw fm (the fake), which still records the call.
        assert result is True
        assert len(fm.insert_calls) == 1


# ---------------------------------------------------------------------------
# SPIKE_STATUS sentinel
# ---------------------------------------------------------------------------


class TestSpikeStatus:
    def test_spike_status_is_green(self) -> None:
        assert mr.SPIKE_STATUS == "GREEN"


# ---------------------------------------------------------------------------
# Never-raise contract (§0 HARD RULE)
# ---------------------------------------------------------------------------


class TestNeverRaise:
    """§0: Return (False, reason) on any failure — NEVER raise."""

    def test_unexpected_exception_in_count_nodes(self) -> None:
        class _BrokenFM:
            def GetFeatures(self, top_level: bool):
                raise RuntimeError("COM link severed")

        class _BrokenDoc:
            FeatureManager = _BrokenFM()

        doc = _BrokenDoc()
        ok, err = mr.create_mate_reference(doc, {"type": "mate_reference", "entities": []}, {})
        assert ok is False
        assert "unexpected error" in err

    def test_unexpected_exception_type_error(self) -> None:
        ok, err = mr.create_mate_reference(None, None, None)  # type: ignore[arg-type]
        assert ok is False
        assert err is not None
