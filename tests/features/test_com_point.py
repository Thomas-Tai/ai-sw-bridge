"""Offline tests for the ``com_point`` feature handler (W63 lane 3).

Tests the Mode-B-only path (``InsertCenterOfMass``) with fake COM objects.
Mode-A is skipped by design — no creation enum exists, so there is no
quarantine class.

Test matrix:
  - Mode-B success: callable InsertCenterOfMass, node delta +1, type match → True
  - Mode-B property form: InsertCenterOfMass resolves as property → True
  - Mode-B ghost trap: call succeeds but no node delta → False
  - Mode-B wrong type: node delta +1 but no CenterOfMass type → False
  - Mode-B exception: InsertCenterOfMass raises → False
"""

from __future__ import annotations


from ai_sw_bridge.features import com_point as cp


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


class _FakeFeatureManager:
    """W63 round-2 retarget: the CoM-reference-point creator lives here, not on the doc."""

    def __init__(self, nodes: list | None = None):
        self._nodes = nodes if nodes is not None else []
        self._pending_post_nodes: list | None = None  # activated by the insert call
        self._insert_com_callable: bool = True
        self._insert_com_raises: bool = False
        self._insert_com_present: bool = True
        self._insert_com_called: bool = False

    def set_post_nodes(self, nodes: list | None):
        """Stage the post-insert tree; only swapped in on InsertCenterOfMass*."""
        self._pending_post_nodes = nodes

    def GetFeatures(self, _top_level: bool):
        return self._nodes

    def _activate_post_nodes(self):
        if self._pending_post_nodes is not None:
            self._nodes = self._pending_post_nodes
            self._pending_post_nodes = None

    def __getattr__(self, name):
        # win32com-style: missing typelib members raise AttributeError. We
        # consult _insert_com_present (default True) to simulate a typelib
        # that omits InsertCenterOfMassReferencePoint.
        if name == "InsertCenterOfMassReferencePoint":
            if not self.__dict__.get("_insert_com_present", True):
                raise AttributeError(name)
            # Property-form (callable=False): auto-invoke now, return value.
            if not self.__dict__.get("_insert_com_callable", True):
                if self.__dict__.get("_insert_com_raises", False):
                    raise RuntimeError(
                        "COM error: InsertCenterOfMassReferencePoint failed"
                    )
                self._activate_post_nodes()
                self._insert_com_called = True
                return True

            # Callable-form: return a bound function the handler can invoke.
            def _called():
                self._insert_com_called = True
                if self._insert_com_raises:
                    raise RuntimeError(
                        "COM error: InsertCenterOfMassReferencePoint failed"
                    )
                self._activate_post_nodes()
                return True

            return _called
        raise AttributeError(name)


class _FakeDoc:
    """Minimal fake ``IModelDoc2`` for the ``com_point`` handler."""

    def __init__(
        self,
        *,
        insert_com_callable: bool = True,
        insert_com_raises: bool = False,
        insert_com_present: bool = True,
        pre_nodes: list | None = None,
        post_nodes: list | None = None,
    ):
        self._fm = _FakeFeatureManager(pre_nodes)
        self._fm._insert_com_callable = insert_com_callable
        self._fm._insert_com_raises = insert_com_raises
        self._fm._insert_com_present = insert_com_present
        self._post_nodes = post_nodes
        # The handler reads post_nodes off the FeatureManager via GetFeatures.
        # The fm stages the swap; only the insert call activates it.
        if post_nodes is not None:
            self._fm.set_post_nodes(post_nodes)
        self._rebuild_count = 0
        # Backwards-compat handles for tests that still inspect these.
        self._insert_com_callable = insert_com_callable
        self._insert_com_raises = insert_com_raises

    @property
    def FeatureManager(self):
        return self._fm

    @property
    def _insert_com_called(self):
        return self._fm._insert_com_called

    def ForceRebuild3(self, _force: bool):
        self._rebuild_count += 1


class _FakeDocPropertyForm:
    """Fake doc where ``InsertCenterOfMassReferencePoint`` resolves as a
    property (auto-invoked on attribute access — the late-bind trap)."""

    def __init__(
        self, *, pre_nodes: list | None = None, post_nodes: list | None = None
    ):
        self._fm = _FakeFeatureManager(pre_nodes)
        self._fm._insert_com_callable = False
        self._post_nodes = post_nodes
        if post_nodes is not None:
            self._fm.set_post_nodes(post_nodes)
        self._rebuild_count = 0

    @property
    def FeatureManager(self):
        return self._fm

    def ForceRebuild3(self, _force: bool):
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
    """Post-insertion tree: baseline + CenterOfMass node."""
    nodes = _make_pre_nodes()
    nodes.append(_FakeFeatureNode("CenterOfMass"))
    return nodes


def _make_post_nodes_folder():
    """Post-insertion tree: baseline + CenterOfMassFolder node."""
    nodes = _make_pre_nodes()
    nodes.append(_FakeFeatureNode("CenterOfMassFolder"))
    return nodes


def _make_post_nodes_wrong_type():
    """Post-insertion tree: baseline + a non-CoM node."""
    nodes = _make_pre_nodes()
    nodes.append(_FakeFeatureNode("SomeOtherFeature"))
    return nodes


# ---------------------------------------------------------------------------
# Tests — Mode-B success
# ---------------------------------------------------------------------------


class TestModeBSuccess:
    def test_callable_insert_returns_true(self):
        doc = _FakeDoc(
            pre_nodes=_make_pre_nodes(),
            post_nodes=_make_post_nodes_success(),
        )
        ok, note = cp.create_com_point(doc, {"kind": "com_point"}, {})
        assert ok is True
        assert "mode_b" in (note or "")
        assert doc._insert_com_called is True

    def test_property_form_insert_returns_true(self):
        doc = _FakeDocPropertyForm(
            pre_nodes=_make_pre_nodes(),
            post_nodes=_make_post_nodes_success(),
        )
        ok, note = cp.create_com_point(doc, {"kind": "com_point"}, {})
        assert ok is True
        assert "mode_b" in (note or "")

    def test_folder_type_name_also_accepted(self):
        doc = _FakeDoc(
            pre_nodes=_make_pre_nodes(),
            post_nodes=_make_post_nodes_folder(),
        )
        ok, _ = cp.create_com_point(doc, {"kind": "com_point"}, {})
        assert ok is True

    def test_force_rebuild_called(self):
        doc = _FakeDoc(
            pre_nodes=_make_pre_nodes(),
            post_nodes=_make_post_nodes_success(),
        )
        cp.create_com_point(doc, {"kind": "com_point"}, {})
        assert doc._rebuild_count >= 1


# ---------------------------------------------------------------------------
# Tests — Mode-B ghost trap (no node delta)
# ---------------------------------------------------------------------------


class TestModeBGhostTrap:
    def test_no_node_delta_returns_false(self):
        doc = _FakeDoc(
            insert_com_callable=True,
            pre_nodes=_make_pre_nodes(),
            post_nodes=_make_pre_nodes(),  # same count
        )
        ok, reason = cp.create_com_point(doc, {"kind": "com_point"}, {})
        assert ok is False
        assert "did not add a feature node" in (reason or "")

    def test_ghost_trap_message_includes_counts(self):
        doc = _FakeDoc(
            pre_nodes=_make_pre_nodes(),
            post_nodes=_make_pre_nodes(),
        )
        ok, reason = cp.create_com_point(doc, {"kind": "com_point"}, {})
        assert ok is False
        assert "5 -> 5" in (reason or "")


# ---------------------------------------------------------------------------
# Tests — Mode-B wrong type name
# ---------------------------------------------------------------------------


class TestModeBWrongType:
    def test_node_added_but_no_com_type_returns_false(self):
        doc = _FakeDoc(
            pre_nodes=_make_pre_nodes(),
            post_nodes=_make_post_nodes_wrong_type(),
        )
        ok, reason = cp.create_com_point(doc, {"kind": "com_point"}, {})
        assert ok is False
        assert "no CenterOfMass" in (reason or "")


# ---------------------------------------------------------------------------
# Tests — Mode-B exception path
# ---------------------------------------------------------------------------


class TestModeBException:
    def test_insert_raises_returns_false(self):
        doc = _FakeDoc(
            insert_com_raises=True,
            pre_nodes=_make_pre_nodes(),
        )
        ok, reason = cp.create_com_point(doc, {"kind": "com_point"}, {})
        assert ok is False
        assert "raised" in (reason or "")

    def test_handler_never_raises(self):
        """The handler contract: never raise, always return (False, reason)."""

        class _BadDoc:
            """Every attribute access raises."""

            @property
            def FeatureManager(self):
                raise RuntimeError("COM unavailable")

            def __getattr__(self, name):
                raise RuntimeError("COM unavailable")

        doc = _BadDoc()
        # Must not raise — must return (False, reason).
        ok, reason = cp.create_com_point(doc, {"kind": "com_point"}, {})
        assert ok is False
        assert reason is not None


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

        assert cp._count_feature_nodes(_Doc()) == 0

    def test_returns_zero_when_get_features_raises(self):
        class _FM:
            def GetFeatures(self, _):
                raise RuntimeError("no COM")

        class _Doc:
            FeatureManager = _FM()

        assert cp._count_feature_nodes(_Doc()) == 0

    def test_returns_correct_count(self):
        class _FM:
            def GetFeatures(self, _):
                return [1, 2, 3, 4, 5]

        class _Doc:
            FeatureManager = _FM()

        assert cp._count_feature_nodes(_Doc()) == 5


# ---------------------------------------------------------------------------
# Tests — handler signature and SPIKE_STATUS
# ---------------------------------------------------------------------------


class TestHandlerContract:
    def test_handler_signature(self):
        import inspect

        sig = inspect.signature(cp.create_com_point)
        params = list(sig.parameters)
        assert params == ["doc", "feature", "target"]

    def test_spike_status_is_green(self):
        assert cp.SPIKE_STATUS == "GREEN"

    def test_target_is_unused(self):
        """target is ignored — CoM requires no entity selection."""
        doc = _FakeDoc(
            pre_nodes=_make_pre_nodes(),
            post_nodes=_make_post_nodes_success(),
        )
        ok, _ = cp.create_com_point(doc, {"kind": "com_point"}, {"ignored": True})
        assert ok is True
