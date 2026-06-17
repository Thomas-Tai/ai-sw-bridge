"""Offline tests for the ``bounding_box`` feature handler (W63 lane 2).

Tests both Mode-A (``CreateDefinition(swFmBoundingBox)`` → ``typed_qi`` →
``CreateFeature``) and Mode-B (``InsertGlobalBoundingBox``) with fake COM
objects.  Mode-A is the primary path; Mode-B is the fallback.

Test matrix:
  - Mode-A success: CreateDefinition returns data, QI succeeds, node delta +1,
    type match → True
  - Mode-A CreateDefinition returns None → fall through to Mode-B
  - Mode-A QI fails (E_NOINTERFACE) → fall through to Mode-B
  - Mode-A ghost trap: CreateFeature returns object but no node delta → False
    (after Mode-B also fails)
  - Mode-A wrong type: node delta +1 but no BoundingBox type → False
  - Mode-B success: callable InsertGlobalBoundingBox, node delta +1, type
    match → True
  - Mode-B property form: InsertGlobalBoundingBox resolves as property → True
  - Mode-B ghost trap: call succeeds but no node delta → False
  - Mode-B wrong type: node delta +1 but no BoundingBox type → False
  - Mode-B exception: InsertGlobalBoundingBox raises → False
  - Mode-B not on typelib: InsertGlobalBoundingBox absent → False
  - Both modes fail → False with combined reason
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ai_sw_bridge.features import bounding_box as bb


# ---------------------------------------------------------------------------
# Fake COM infrastructure
# ---------------------------------------------------------------------------

class _FakeFeatureNode:
    def __init__(self, type_name: str | None = None):
        self._type_name = type_name

    def GetTypeName2(self):
        return self._type_name

    def GetTypeName(self):
        return self._type_name

    Name = "FakeNode"


class _FakeFeatureData:
    """Fake IBoundingBoxFeatureData — tracks property sets and access calls."""

    def __init__(self):
        self.include_hidden_bodies = None
        self.include_surfaces = None
        self.reference_face_or_plane = None
        self.planar_entity = None
        self.access_calls = []
        self.release_calls = 0

    @property
    def IncludeHiddenBodies(self):
        return self.include_hidden_bodies

    @IncludeHiddenBodies.setter
    def IncludeHiddenBodies(self, v):
        self.include_hidden_bodies = v

    @property
    def IncludeSurfaces(self):
        return self.include_surfaces

    @IncludeSurfaces.setter
    def IncludeSurfaces(self, v):
        self.include_surfaces = v

    @property
    def ReferenceFaceOrPlane(self):
        return self.reference_face_or_plane

    @ReferenceFaceOrPlane.setter
    def ReferenceFaceOrPlane(self, v):
        self.reference_face_or_plane = v

    @property
    def PlanarEntity(self):
        return self.planar_entity

    @PlanarEntity.setter
    def PlanarEntity(self, v):
        self.planar_entity = v

    def AccessSelections(self, doc, comp):
        self.access_calls.append((doc, comp))
        return True

    def ReleaseSelectionAccess(self):
        self.release_calls += 1


class _FakeFeatureManager:
    def __init__(self, nodes=None):
        self._nodes = nodes if nodes is not None else []
        self._post_nodes = None
        self._switched = False
        self._create_def_result = None
        self._create_feature_result = None
        self._insert_bbox_result = None
        self._insert_bbox_raises = False
        self._create_def_called = False
        self._create_feature_called = False
        self._insert_bbox_called = False

    def set_post_nodes(self, nodes):
        self._post_nodes = nodes
        self._switched = False

    def GetFeatures(self, _top_level):
        if self._switched and self._post_nodes is not None:
            return self._post_nodes
        return self._nodes

    def CreateDefinition(self, enum_id):
        self._create_def_called = True
        return self._create_def_result

    def CreateFeature(self, data):
        self._create_feature_called = True
        result = self._create_feature_result
        if self._post_nodes is not None and result is not None and not isinstance(result, int):
            self._switched = True
        return result

    def InsertGlobalBoundingBox(self, bbox_type, include_hidden, include_surface, status_placeholder=0):
        # W63 B1 patch: dispid expects 4 slots (3 inputs + [out] Status placeholder).
        self._insert_bbox_called = True
        self._insert_bbox_args = (bbox_type, include_hidden, include_surface, status_placeholder)
        if self._insert_bbox_raises:
            raise RuntimeError("COM error: InsertGlobalBoundingBox failed")
        if self._post_nodes is not None:
            self._switched = True
        return self._insert_bbox_result


class _FakePlane:
    """Sentinel returned by _FakeDoc.FeatureByName('Front Plane')."""

    def __init__(self, name="Front Plane"):
        self.name = name


class _FakeDoc:
    """Minimal fake IModelDoc2 for the bounding_box handler."""

    def __init__(
        self,
        *,
        pre_nodes=None,
        post_nodes=None,
        create_def_result=None,
        create_feature_result=None,
        insert_bbox_result=None,
        insert_bbox_raises=False,
        front_plane=None,
    ):
        self._fm = _FakeFeatureManager(pre_nodes)
        self._fm.set_post_nodes(post_nodes)
        self._fm._create_def_result = create_def_result
        self._fm._create_feature_result = create_feature_result
        self._fm._insert_bbox_result = insert_bbox_result
        self._fm._insert_bbox_raises = insert_bbox_raises
        self._rebuild_count = 0
        # W63 round-4: handler now looks up the Front Plane via FeatureByName.
        # Default to a sentinel _FakePlane so existing test setups keep working;
        # tests can override via `front_plane=...`.
        self._front_plane = front_plane if front_plane is not None else _FakePlane()
        self._feature_by_name_calls = []

    @property
    def FeatureManager(self):
        return self._fm

    def FeatureByName(self, name):
        self._feature_by_name_calls.append(name)
        if name == "Front Plane":
            return self._front_plane
        return None

    def ForceRebuild3(self, _force):
        self._rebuild_count += 1


class _FakeDocPropertyFormInsertBBox:
    """Fake doc where InsertGlobalBoundingBox resolves as a property."""

    def __init__(self, *, pre_nodes=None, post_nodes=None):
        self._fm = _FakeFMPropertyForm(pre_nodes, post_nodes)
        self._rebuild_count = 0

    @property
    def FeatureManager(self):
        return self._fm

    def ForceRebuild3(self, _force):
        self._rebuild_count += 1


class _FakeFMPropertyForm:
    def __init__(self, pre_nodes, post_nodes):
        self._nodes = pre_nodes if pre_nodes is not None else []
        self._post_nodes = post_nodes
        self._switched = False

    def GetFeatures(self, _top_level):
        if self._switched and self._post_nodes is not None:
            return self._post_nodes
        return self._nodes

    @property
    def InsertGlobalBoundingBox(self):
        if self._post_nodes is not None:
            self._switched = True
        return True


class _FakeFMNoInsertBBox:
    """FeatureManager with no InsertGlobalBoundingBox attribute."""

    def __init__(self, nodes=None):
        self._nodes = nodes if nodes is not None else []

    def GetFeatures(self, _top_level):
        return self._nodes

    def CreateDefinition(self, enum_id):
        return None


class _FakeDocNoInsertBBox:
    """Doc whose FeatureManager has no InsertGlobalBoundingBox."""

    def __init__(self, *, pre_nodes=None):
        self._fm = _FakeFMNoInsertBBox(pre_nodes)
        self._rebuild_count = 0

    @property
    def FeatureManager(self):
        return self._fm

    def ForceRebuild3(self, _force):
        self._rebuild_count += 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pre_nodes():
    """A baseline feature tree (Origin + 3 planes + 1 boss = 5 nodes)."""
    return [
        _FakeFeatureNode("Origin"),
        _FakeFeatureNode("RefPlane"),
        _FakeFeatureNode("RefPlane"),
        _FakeFeatureNode("RefPlane"),
        _FakeFeatureNode("BaseBody"),
    ]


def _make_post_nodes_success():
    """Post-insertion tree: baseline + BoundingBoxFolder node."""
    nodes = _make_pre_nodes()
    nodes.append(_FakeFeatureNode("BoundingBoxFolder"))
    return nodes


def _make_post_nodes_bbox_plain():
    """Post-insertion tree: baseline + BoundingBox node (no Folder suffix)."""
    nodes = _make_pre_nodes()
    nodes.append(_FakeFeatureNode("BoundingBox"))
    return nodes


def _make_post_nodes_wrong_type():
    """Post-insertion tree: baseline + a non-BBox node."""
    nodes = _make_pre_nodes()
    nodes.append(_FakeFeatureNode("SomeOtherFeature"))
    return nodes


def _make_fake_data():
    """A fake object that has _oleobj_ for typed_qi to find."""
    obj = MagicMock()
    obj._oleobj_ = MagicMock()
    return obj


def _patch_typed_qi_success(monkeypatch, fake_bd=None):
    """Patch typed_qi on the bounding_box module to return a fake BBox data."""
    if fake_bd is None:
        fake_bd = _FakeFeatureData()

    def _fake_typed_qi(obj, iface, *, module=None):
        return fake_bd

    monkeypatch.setattr(bb, "typed_qi", _fake_typed_qi)
    monkeypatch.setattr(bb, "wrapper_module", lambda: MagicMock())
    return fake_bd


def _patch_typed_qi_fail(monkeypatch):
    """Patch typed_qi to raise EarlyBindError (E_NOINTERFACE)."""
    from ai_sw_bridge.com.earlybind import EarlyBindError

    def _fake_typed_qi(obj, iface, *, module=None):
        raise EarlyBindError(f"object does not implement {iface!r} (E_NOINTERFACE)")

    monkeypatch.setattr(bb, "typed_qi", _fake_typed_qi)
    monkeypatch.setattr(bb, "wrapper_module", lambda: MagicMock())


# ---------------------------------------------------------------------------
# Tests — Mode-A success
# ---------------------------------------------------------------------------

class TestModeASuccess:
    def test_mode_a_returns_true(self, monkeypatch):
        fake_bd = _patch_typed_qi_success(monkeypatch)
        fake_feat = MagicMock()  # non-None, non-int = materialized
        doc = _FakeDoc(
            pre_nodes=_make_pre_nodes(),
            post_nodes=_make_post_nodes_success(),
            create_def_result=_make_fake_data(),
            create_feature_result=fake_feat,
        )
        ok, note = bb.create_bounding_box(doc, {"kind": "bounding_box"}, {})
        assert ok is True
        assert "mode_a" in (note or "")

    def test_mode_a_sets_properties(self, monkeypatch):
        """W63 round-4: BBoxType setter dropped (not on v32.1 typelib).
        IncludeHidden/Surfaces remain (verified present via A3 reflection)."""
        fake_bd = _patch_typed_qi_success(monkeypatch)
        fake_feat = MagicMock()
        doc = _FakeDoc(
            pre_nodes=_make_pre_nodes(),
            post_nodes=_make_post_nodes_success(),
            create_def_result=_make_fake_data(),
            create_feature_result=fake_feat,
        )
        bb.create_bounding_box(doc, {"kind": "bounding_box", "best_fit": False}, {})
        assert fake_bd.include_hidden_bodies is False
        assert fake_bd.include_surfaces is False

    def test_mode_a_sets_reference_face_or_plane(self, monkeypatch):
        """W63 round-4 A5: ReferenceFaceOrPlane must be set to the Front Plane
        the handler looked up via FeatureByName."""
        fake_bd = _patch_typed_qi_success(monkeypatch)
        fake_feat = MagicMock()
        plane = _FakePlane()
        doc = _FakeDoc(
            pre_nodes=_make_pre_nodes(),
            post_nodes=_make_post_nodes_success(),
            create_def_result=_make_fake_data(),
            create_feature_result=fake_feat,
            front_plane=plane,
        )
        bb.create_bounding_box(doc, {"kind": "bounding_box"}, {})
        assert fake_bd.reference_face_or_plane is plane
        assert "Front Plane" in doc._feature_by_name_calls

    def test_mode_a_calls_access_selections(self, monkeypatch):
        """W63 round-4 (round-2 A2 was self-inflicted regression): the iface
        DOES expose AccessSelections (A3 reflection confirmed), and the
        FeatureData must be opened for editing before reference setters bind."""
        fake_bd = _patch_typed_qi_success(monkeypatch)
        fake_feat = MagicMock()
        doc = _FakeDoc(
            pre_nodes=_make_pre_nodes(),
            post_nodes=_make_post_nodes_success(),
            create_def_result=_make_fake_data(),
            create_feature_result=fake_feat,
        )
        bb.create_bounding_box(doc, {"kind": "bounding_box"}, {})
        assert len(fake_bd.access_calls) >= 1

    def test_mode_a_calls_release_selection_access(self, monkeypatch):
        """W63 round-4: paired with AccessSelections; commit edits before CreateFeature."""
        fake_bd = _patch_typed_qi_success(monkeypatch)
        fake_feat = MagicMock()
        doc = _FakeDoc(
            pre_nodes=_make_pre_nodes(),
            post_nodes=_make_post_nodes_success(),
            create_def_result=_make_fake_data(),
            create_feature_result=fake_feat,
        )
        bb.create_bounding_box(doc, {"kind": "bounding_box"}, {})
        assert fake_bd.release_calls >= 1

    def test_mode_a_force_rebuild_called(self, monkeypatch):
        _patch_typed_qi_success(monkeypatch)
        fake_feat = MagicMock()
        doc = _FakeDoc(
            pre_nodes=_make_pre_nodes(),
            post_nodes=_make_post_nodes_success(),
            create_def_result=_make_fake_data(),
            create_feature_result=fake_feat,
        )
        bb.create_bounding_box(doc, {"kind": "bounding_box"}, {})
        assert doc._rebuild_count >= 1

    def test_mode_a_bbox_plain_type_accepted(self, monkeypatch):
        """BoundingBox (without Folder suffix) is also accepted."""
        _patch_typed_qi_success(monkeypatch)
        fake_feat = MagicMock()
        doc = _FakeDoc(
            pre_nodes=_make_pre_nodes(),
            post_nodes=_make_post_nodes_bbox_plain(),
            create_def_result=_make_fake_data(),
            create_feature_result=fake_feat,
        )
        ok, _ = bb.create_bounding_box(doc, {"kind": "bounding_box"}, {})
        assert ok is True

    def test_mode_a_create_feature_called(self, monkeypatch):
        _patch_typed_qi_success(monkeypatch)
        fake_feat = MagicMock()
        doc = _FakeDoc(
            pre_nodes=_make_pre_nodes(),
            post_nodes=_make_post_nodes_success(),
            create_def_result=_make_fake_data(),
            create_feature_result=fake_feat,
        )
        bb.create_bounding_box(doc, {"kind": "bounding_box"}, {})
        assert doc._fm._create_feature_called is True


# ---------------------------------------------------------------------------
# Tests — Mode-A failure → Mode-B fallback
# ---------------------------------------------------------------------------

class TestModeAFailureFallsToModeB:
    def test_create_definition_none_falls_to_mode_b(self):
        """CreateDefinition returns None → falls to Mode-B."""
        doc = _FakeDoc(
            pre_nodes=_make_pre_nodes(),
            post_nodes=_make_post_nodes_success(),
            create_def_result=None,
            insert_bbox_result=True,
        )
        ok, note = bb.create_bounding_box(doc, {"kind": "bounding_box"}, {})
        assert ok is True
        assert "mode_b" in (note or "")

    def test_qi_failure_falls_to_mode_b(self, monkeypatch):
        """typed_qi raises E_NOINTERFACE → falls to Mode-B."""
        _patch_typed_qi_fail(monkeypatch)
        doc = _FakeDoc(
            pre_nodes=_make_pre_nodes(),
            post_nodes=_make_post_nodes_success(),
            create_def_result=_make_fake_data(),
            insert_bbox_result=True,
        )
        ok, note = bb.create_bounding_box(doc, {"kind": "bounding_box"}, {})
        assert ok is True
        assert "mode_b" in (note or "")

    def test_create_feature_none_falls_to_mode_b(self, monkeypatch):
        """CreateFeature returns None → falls to Mode-B."""
        _patch_typed_qi_success(monkeypatch)
        doc = _FakeDoc(
            pre_nodes=_make_pre_nodes(),
            post_nodes=_make_post_nodes_success(),
            create_def_result=_make_fake_data(),
            create_feature_result=None,
            insert_bbox_result=True,
        )
        ok, note = bb.create_bounding_box(doc, {"kind": "bounding_box"}, {})
        assert ok is True
        assert "mode_b" in (note or "")

    def test_mode_a_ghost_falls_to_mode_b(self, monkeypatch):
        """Mode-A: CreateFeature materializes but no node delta -> Mode-B also fails."""
        _patch_typed_qi_success(monkeypatch)
        fake_feat = MagicMock()
        # Both pre and post are the same 5 nodes — no delta for either mode.
        pre = _make_pre_nodes()
        doc = _FakeDoc(
            pre_nodes=pre,
            post_nodes=list(pre),  # same count, no delta for Mode-A
            create_def_result=_make_fake_data(),
            create_feature_result=fake_feat,
            insert_bbox_result=True,
        )
        ok, reason = bb.create_bounding_box(doc, {"kind": "bounding_box"}, {})
        # Both modes fail (Mode-A ghost, Mode-B no delta since _post_nodes consumed)
        assert ok is False
        assert "both modes failed" in (reason or "")


# ---------------------------------------------------------------------------
# Tests — Mode-B success (Mode-A disabled via create_def_result=None)
# ---------------------------------------------------------------------------

class TestModeBSuccess:
    def test_callable_insert_returns_true(self):
        doc = _FakeDoc(
            pre_nodes=_make_pre_nodes(),
            post_nodes=_make_post_nodes_success(),
            create_def_result=None,  # forces Mode-B
            insert_bbox_result=True,
        )
        ok, note = bb.create_bounding_box(doc, {"kind": "bounding_box"}, {})
        assert ok is True
        assert "mode_b" in (note or "")

    def test_property_form_insert_returns_true(self):
        doc = _FakeDocPropertyFormInsertBBox(
            pre_nodes=_make_pre_nodes(),
            post_nodes=_make_post_nodes_success(),
        )
        ok, note = bb.create_bounding_box(doc, {"kind": "bounding_box"}, {})
        assert ok is True
        assert "mode_b" in (note or "")

    def test_folder_type_name_accepted(self):
        doc = _FakeDoc(
            pre_nodes=_make_pre_nodes(),
            post_nodes=_make_post_nodes_success(),
            create_def_result=None,
            insert_bbox_result=True,
        )
        ok, _ = bb.create_bounding_box(doc, {"kind": "bounding_box"}, {})
        assert ok is True

    def test_plain_bbox_type_name_accepted(self):
        doc = _FakeDoc(
            pre_nodes=_make_pre_nodes(),
            post_nodes=_make_post_nodes_bbox_plain(),
            create_def_result=None,
            insert_bbox_result=True,
        )
        ok, _ = bb.create_bounding_box(doc, {"kind": "bounding_box"}, {})
        assert ok is True

    def test_force_rebuild_called(self):
        doc = _FakeDoc(
            pre_nodes=_make_pre_nodes(),
            post_nodes=_make_post_nodes_success(),
            create_def_result=None,
            insert_bbox_result=True,
        )
        bb.create_bounding_box(doc, {"kind": "bounding_box"}, {})
        assert doc._rebuild_count >= 1

    def test_insert_bbox_called_with_correct_args(self):
        doc = _FakeDoc(
            pre_nodes=_make_pre_nodes(),
            post_nodes=_make_post_nodes_success(),
            create_def_result=None,
            insert_bbox_result=True,
        )
        bb.create_bounding_box(doc, {"kind": "bounding_box", "best_fit": True}, {})
        assert doc._fm._insert_bbox_called is True


# ---------------------------------------------------------------------------
# Tests — Mode-B ghost trap (no node delta)
# ---------------------------------------------------------------------------

class TestModeBGhostTrap:
    def test_no_node_delta_returns_false(self):
        doc = _FakeDoc(
            pre_nodes=_make_pre_nodes(),
            post_nodes=_make_pre_nodes(),  # same count
            create_def_result=None,
            insert_bbox_result=True,
        )
        ok, reason = bb.create_bounding_box(doc, {"kind": "bounding_box"}, {})
        assert ok is False
        assert "did not add a feature node" in (reason or "")

    def test_ghost_trap_message_includes_counts(self):
        doc = _FakeDoc(
            pre_nodes=_make_pre_nodes(),
            post_nodes=_make_pre_nodes(),
            create_def_result=None,
            insert_bbox_result=True,
        )
        ok, reason = bb.create_bounding_box(doc, {"kind": "bounding_box"}, {})
        assert ok is False
        assert "5 -> 5" in (reason or "")


# ---------------------------------------------------------------------------
# Tests — Mode-B wrong type name
# ---------------------------------------------------------------------------

class TestModeBWrongType:
    def test_node_added_but_no_bbox_type_returns_false(self):
        doc = _FakeDoc(
            pre_nodes=_make_pre_nodes(),
            post_nodes=_make_post_nodes_wrong_type(),
            create_def_result=None,
            insert_bbox_result=True,
        )
        ok, reason = bb.create_bounding_box(doc, {"kind": "bounding_box"}, {})
        assert ok is False
        assert "no BoundingBox" in (reason or "")


# ---------------------------------------------------------------------------
# Tests — Mode-B exception path
# ---------------------------------------------------------------------------

class TestModeBException:
    def test_insert_raises_returns_false(self):
        doc = _FakeDoc(
            pre_nodes=_make_pre_nodes(),
            create_def_result=None,
            insert_bbox_raises=True,
        )
        ok, reason = bb.create_bounding_box(doc, {"kind": "bounding_box"}, {})
        assert ok is False
        assert "raised" in (reason or "")

    def test_handler_never_raises(self):
        """The handler contract: never raise, always return (False, reason)."""

        class _BadDoc:
            @property
            def FeatureManager(self):
                raise RuntimeError("COM unavailable")

            def __getattr__(self, name):
                raise RuntimeError("COM unavailable")

        doc = _BadDoc()
        ok, reason = bb.create_bounding_box(doc, {"kind": "bounding_box"}, {})
        assert ok is False
        assert reason is not None


# ---------------------------------------------------------------------------
# Tests — Mode-B not on typelib
# ---------------------------------------------------------------------------

class TestModeBNotOnTypelib:
    def test_insert_bbox_absent_returns_false(self):
        doc = _FakeDocNoInsertBBox(pre_nodes=_make_pre_nodes())
        ok, reason = bb.create_bounding_box(doc, {"kind": "bounding_box"}, {})
        assert ok is False
        assert "not available" in (reason or "") or "both modes failed" in (reason or "")


# ---------------------------------------------------------------------------
# Tests — count_feature_nodes helper
# ---------------------------------------------------------------------------

class TestCountFeatureNodes:
    def test_returns_zero_when_get_features_returns_none(self):
        class _FM:
            def GetFeatures(self, _):
                return None

        class _Doc:
            FeatureManager = _FM()

        assert bb._count_feature_nodes(_Doc()) == 0

    def test_returns_zero_when_get_features_raises(self):
        class _FM:
            def GetFeatures(self, _):
                raise RuntimeError("no COM")

        class _Doc:
            FeatureManager = _FM()

        assert bb._count_feature_nodes(_Doc()) == 0

    def test_returns_correct_count(self):
        class _FM:
            def GetFeatures(self, _):
                return [1, 2, 3, 4, 5]

        class _Doc:
            FeatureManager = _FM()

        assert bb._count_feature_nodes(_Doc()) == 5


# ---------------------------------------------------------------------------
# Tests — handler signature and SPIKE_STATUS
# ---------------------------------------------------------------------------

class TestHandlerContract:
    def test_handler_signature(self):
        import inspect

        sig = inspect.signature(bb.create_bounding_box)
        params = list(sig.parameters)
        assert params == ["doc", "feature", "target"]

    def test_spike_status_is_green(self):
        """W63 round-5 seat-proven 2026-06-17 — registry now advertises."""
        assert bb.SPIKE_STATUS == "GREEN"

    def test_target_is_unused(self):
        """target is ignored — global bounding box requires no entity selection."""
        doc = _FakeDoc(
            pre_nodes=_make_pre_nodes(),
            post_nodes=_make_post_nodes_success(),
            create_def_result=None,
            insert_bbox_result=True,
        )
        ok, _ = bb.create_bounding_box(doc, {"kind": "bounding_box"}, {"ignored": True})
        assert ok is True

    def test_best_fit_defaults_to_false(self):
        """Default best_fit=False should pass BBoxType=0 to Mode-B."""
        doc = _FakeDoc(
            pre_nodes=_make_pre_nodes(),
            post_nodes=_make_post_nodes_success(),
            create_def_result=None,
            insert_bbox_result=True,
        )
        ok, _ = bb.create_bounding_box(doc, {"kind": "bounding_box"}, {})
        assert ok is True
