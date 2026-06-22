"""W74 offline tests — configuration lifecycle (derive + delete).

Covers ``create_configuration`` (standard + derived/parent-linked) and
``delete_configuration`` (including the active-config switch-then-delete
recipe and the fail-closed guards: missing target, only-config, switch
failure, SW-returns-False).

COM seams are patched on the lane module itself (``config.lifecycle``).  A
stateful fake doc models GetConfigurationNames + the active config so the
switch-away-before-delete flow is genuinely exercised.
"""

from __future__ import annotations

import pytest

from ai_sw_bridge.config import lifecycle as lc
from ai_sw_bridge.config.lifecycle import create_configuration, delete_configuration


# ---------------------------------------------------------------------------
# Stateful fake COM objects
# ---------------------------------------------------------------------------

class _FakeConfig:
    def __init__(self, name, *, parent=None):
        self.Name = name
        self._parent = parent

    def IsDerived(self):
        return self._parent is not None

    def GetParent(self):
        return _FakeConfig(self._parent) if self._parent else None


class _FakeCM:
    def __init__(self, doc):
        self._doc = doc

    @property
    def ActiveConfiguration(self):
        return _FakeConfig(self._doc.active)

    def AddConfiguration2(self, name, comment, alt, options, parent, desc, rebuild):
        if self._doc.add_returns_none:
            return None
        if self._doc.add_raises:
            raise RuntimeError("boom-add")
        self._doc.names.append(name)
        self._doc.parents[name] = parent or None
        self._doc.active = name  # new config becomes active (the W74 footgun)
        return _FakeConfig(name, parent=parent or None)


class _FakeDoc:
    def __init__(self, names=("Default",), *, active=None,
                 add_returns_none=False, add_raises=False,
                 show_returns=True, delete_returns=True, delete_really=True):
        self.names = list(names)
        self.parents = {}
        self.active = active if active is not None else self.names[0]
        self.add_returns_none = add_returns_none
        self.add_raises = add_raises
        self.show_returns = show_returns
        self.delete_returns = delete_returns
        self.delete_really = delete_really
        self.ConfigurationManager = _FakeCM(self)
        self.shown = []

    def GetConfigurationNames(self):
        return tuple(self.names)

    def GetConfigurationByName(self, name):
        return _FakeConfig(name, parent=self.parents.get(name))

    def ShowConfiguration2(self, name):
        if self.show_returns:
            self.active = name
            self.shown.append(name)
        return self.show_returns

    def DeleteConfiguration2(self, name):
        if self.delete_returns and self.delete_really and name in self.names:
            self.names.remove(name)
        return self.delete_returns


@pytest.fixture(autouse=True)
def _identity_typed_qi(monkeypatch):
    # GetConfigurationByName already returns a usable fake config
    monkeypatch.setattr(lc, "typed_qi", lambda obj, iface, module=None: obj)


# ---------------------------------------------------------------------------
# create_configuration
# ---------------------------------------------------------------------------

class TestCreate:
    def test_empty_name(self):
        ok, err = create_configuration(_FakeDoc(), "")
        assert ok is False and "name" in err

    def test_bad_parent_type(self):
        ok, err = create_configuration(_FakeDoc(), "X", parent=123)
        assert ok is False and "parent" in err

    def test_duplicate_name(self):
        ok, err = create_configuration(_FakeDoc(names=("Default", "X")), "X")
        assert ok is False and "already exists" in err

    def test_parent_missing(self):
        ok, err = create_configuration(_FakeDoc(), "Child", parent="Nope")
        assert ok is False and "does not exist" in err

    def test_standard_create_green(self):
        doc = _FakeDoc()
        ok, note = create_configuration(doc, "Base_W72")
        assert ok is True and "created" in note
        assert "Base_W72" in doc.names

    def test_derived_create_green(self):
        doc = _FakeDoc(names=("Default", "Base_W72"))
        ok, note = create_configuration(doc, "Child_W72", parent="Base_W72")
        assert ok is True and "derived" in note.lower()
        assert doc.parents["Child_W72"] == "Base_W72"

    def test_derived_passes_link_to_parent_option(self):
        """A derived config sends LinkToParent (64) + ParentConfigName."""
        doc = _FakeDoc(names=("Default", "Base"))
        captured = {}
        orig = doc.ConfigurationManager.AddConfiguration2

        def spy(name, comment, alt, options, parent, desc, rebuild):
            captured["options"] = options
            captured["parent"] = parent
            return orig(name, comment, alt, options, parent, desc, rebuild)

        doc.ConfigurationManager.AddConfiguration2 = spy
        create_configuration(doc, "Child", parent="Base")
        assert captured["options"] == lc.SW_CONFIG_LINK_TO_PARENT
        assert captured["parent"] == "Base"

    def test_addconfiguration_returns_none(self):
        ok, err = create_configuration(_FakeDoc(add_returns_none=True), "X")
        assert ok is False and "None" in err

    def test_addconfiguration_raises(self):
        ok, err = create_configuration(_FakeDoc(add_raises=True), "X")
        assert ok is False and "raised" in err


# ---------------------------------------------------------------------------
# delete_configuration
# ---------------------------------------------------------------------------

class TestDelete:
    def test_empty_name(self):
        ok, err = delete_configuration(_FakeDoc(), "")
        assert ok is False and "name" in err

    def test_not_present(self):
        ok, err = delete_configuration(_FakeDoc(names=("Default",)), "Nope")
        assert ok is False and "not present" in err

    def test_only_config_fail_closed(self):
        ok, err = delete_configuration(_FakeDoc(names=("Default",)), "Default")
        assert ok is False and "only configuration" in err

    def test_delete_nonactive_green(self):
        doc = _FakeDoc(names=("Default", "ToDelete"), active="Default")
        ok, note = delete_configuration(doc, "ToDelete")
        assert ok is True and "deleted" in note
        assert "ToDelete" not in doc.names
        assert doc.shown == []  # no switch needed

    def test_delete_active_switches_first(self):
        """The W74 footgun: deleting the ACTIVE config switches away first."""
        doc = _FakeDoc(names=("Default", "ToDelete"), active="ToDelete")
        ok, note = delete_configuration(doc, "ToDelete")
        assert ok is True
        assert doc.shown == ["Default"]  # switched to Default before delete
        assert "ToDelete" not in doc.names

    def test_delete_active_prefers_default_fallback(self):
        doc = _FakeDoc(names=("Default", "A", "ToDelete"), active="ToDelete")
        delete_configuration(doc, "ToDelete")
        assert doc.shown == ["Default"]

    def test_switch_failure_fails_closed(self):
        doc = _FakeDoc(names=("Default", "ToDelete"), active="ToDelete",
                       show_returns=False)
        ok, err = delete_configuration(doc, "ToDelete")
        assert ok is False and "switch" in err
        assert "ToDelete" in doc.names

    def test_delete_returns_false(self):
        doc = _FakeDoc(names=("Default", "ToDelete"), active="Default",
                       delete_returns=False)
        ok, err = delete_configuration(doc, "ToDelete")
        assert ok is False and "False" in err

    def test_still_present_after_delete(self):
        """DeleteConfiguration2 claims True but the config persists -> fail."""
        doc = _FakeDoc(names=("Default", "ToDelete"), active="Default",
                       delete_really=False)
        ok, err = delete_configuration(doc, "ToDelete")
        assert ok is False and "still present" in err
