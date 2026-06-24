"""W68 offline tests — ``fillet_face`` handler (GREEN, seat-proven 2026-06-21).

Fake-COM harness pinning the seat-proven recipe: the face-set wall was a makepy
SAFEARRAY-of-IDispatch marshaling boundary (``SetFaces`` with a bare Python list
silently no-ops; a typed VARIANT array binds — ``GetFaceCount`` readback-guards
the bind), NOT a Parasolid refusal.  Pins:

  * dispatch: Initialize(swFaceFillet=2); SetFaces on WhichFaceList 1 then 2.
  * bind-guard: GetFaceCount(which) must read 1 or the handler fails closed.
  * verify: |d_vol| > VOL_EPS_MM3 (the face delta is unreliable; a fillet
    redistributes material).  CreateFeature's RETURN is NOT the witness — it may
    raise DISP_E_MEMBERNOTFOUND while the solid is already built (swallowed).
  * full_round: SHIPPED 2026-06-21 — Initialize(swFullRoundFillet=3); SetFaces
    on WhichFaceList 3/4/5 (side1/center/side2); same |d_vol| gate (the prior
    slab ghost was a fixture artifact, not a kernel wall).
  * registry: GREEN ⇒ ``fillet_face`` advertised; sibling names are not.

COM seams are patched on the lane module itself (``features.fillet_face_fullround``)
per the registry lane protocol — never on ``mutate``.
"""

from __future__ import annotations

import pytest

from ai_sw_bridge.features import fillet_face_fullround as fn
from ai_sw_bridge.features.fillet_face_fullround import (
    create_fillet_face_fullround,
)


# --- fake COM objects -----------------------------------------------------


class _FakeFD:
    """Fake ISimpleFilletFeatureData2.  Records Initialize(type), DefaultRadius,
    and SetFaces calls; GetFaceCount reflects the bound sets (override to
    simulate a marshaling no-op)."""

    def __init__(self, *, facecount_override: int | None = None) -> None:
        self.initialize_calls: list[int] = []
        self.default_radius_m: float | None = None
        self.setfaces_calls: list[tuple] = []
        self._sets: dict[int, int] = {}
        self._facecount_override = facecount_override

    def Initialize(self, fillet_type: int) -> bool:
        self.initialize_calls.append(int(fillet_type))
        return True

    @property
    def DefaultRadius(self) -> float:
        return self.default_radius_m if self.default_radius_m is not None else 0.0

    @DefaultRadius.setter
    def DefaultRadius(self, value: float) -> None:
        self.default_radius_m = float(value)

    def SetFaces(self, which: int, faces: object) -> None:
        self.setfaces_calls.append((which, faces))
        self._sets[which] = self._sets.get(which, 0) + 1

    def GetFaceCount(self, which: int) -> int:
        if self._facecount_override is not None:
            return self._facecount_override
        return self._sets.get(which, 0)


class _FakeFM:
    """Fake IFeatureManager.  ``CreateDefinition`` returns a sentinel that the
    (monkeypatched) ``typed_qi`` promotes to ``_FakeFD``.  ``CreateFeature``
    returns the supplied value or raises the supplied exception — the handler
    no longer inspects the return (|d_vol| is the witness), but the noise paths
    are still exercised."""

    _SENTINEL_DATA = object()
    _USE_DEFAULT = object()

    def __init__(
        self,
        *,
        create_feature_returns: object = _USE_DEFAULT,
        create_feature_raises: BaseException | None = None,
    ) -> None:
        self.def_calls: list[int] = []
        self.create_calls: list = []
        self._create_feature_raises = create_feature_raises
        if create_feature_returns is self._USE_DEFAULT:
            self._create_feature_returns: object = object()
        else:
            self._create_feature_returns = create_feature_returns

    def CreateDefinition(self, type_id: int):
        self.def_calls.append(type_id)
        return self._SENTINEL_DATA

    def CreateFeature(self, fd):
        self.create_calls.append(fd)
        if self._create_feature_raises is not None:
            raise self._create_feature_raises
        return self._create_feature_returns


class _FakeDoc:
    def __init__(
        self,
        *,
        create_feature_returns: object = _FakeFM._USE_DEFAULT,
        create_feature_raises: BaseException | None = None,
    ) -> None:
        self.FeatureManager = _FakeFM(
            create_feature_returns=create_feature_returns,
            create_feature_raises=create_feature_raises,
        )
        self.cleared = False
        self.rebuilds = 0

    def ClearSelection2(self, flag):
        self.cleared = True

    def ForceRebuild3(self, flag):
        self.rebuilds += 1


# --- fake face_ref dict (handler-consumable manifest-face shape) ----------


def _face_ref(role: str = "face") -> dict:
    return {
        "normal": [0.0, 0.0, 1.0],
        "centroid": [0.0, 0.0, 0.01],
        "area_mm2": 1200.0,
        "role_hint": role,
    }


# --- monkeypatch wiring ----------------------------------------------------


class _ResResult:
    def __init__(self, entity: object, method: str = "persist"):
        self.entity = entity
        self.method = method


_UNSET = object()


def _wire(
    monkeypatch,
    *,
    metrics=((6, 8000.0), (8, 8050.0)),
    resolve_entity: object | None = _UNSET,
    typed_qi_returns=None,
) -> dict:
    """Patch the COM seams on ``features.fillet_face_fullround``.

    Seams: ``verify.solid_metrics`` (driven by ``metrics`` (before),(after)),
    ``resolve_manifest_face`` (returns a live-entity sentinel), ``_face_safearray``
    (identity passthrough — keeps the SetFaces arg inspectable and avoids
    pythoncom offline), and ``com.earlybind.typed_qi`` (returns the fake FD).
    """
    state: dict = {"fake_fd": None}

    seq = list(metrics)
    sstate = {"n": 0}

    def fake_metrics(doc):
        v = seq[min(sstate["n"], len(seq) - 1)]
        sstate["n"] += 1
        return v

    monkeypatch.setattr(fn.verify, "solid_metrics", fake_metrics)

    sentinel_entity: object | None = (
        object() if resolve_entity is _UNSET else resolve_entity
    )

    def fake_resolve(doc, ref):
        return _ResResult(sentinel_entity)

    monkeypatch.setattr(fn, "resolve_manifest_face", fake_resolve)
    # identity SafeArray wrapper so SetFaces records the raw entity (no pythoncom)
    monkeypatch.setattr(fn, "_face_safearray", lambda face: face)

    fake_fd = _FakeFD() if typed_qi_returns is None else typed_qi_returns
    state["fake_fd"] = fake_fd

    import ai_sw_bridge.com.earlybind as eb

    monkeypatch.setattr(eb, "typed_qi", lambda data, iface, module=None: fake_fd)

    return state


# --- SPIKE_STATUS pin -----------------------------------------------------


class TestSpikeStatus:
    def test_green_after_seat_proof(self):
        assert fn.SPIKE_STATUS == "GREEN"


# --- dispatch: face binds two sets; full_round deferred -------------------


class TestDispatch:
    def test_face_uses_type_2_and_setfaces_1_2(self, monkeypatch):
        state = _wire(monkeypatch)
        doc = _FakeDoc()
        ok, err = create_fillet_face_fullround(
            doc,
            {"fillet_type": "face", "radius_mm": 3.0},
            {"faces": [_face_ref("top"), _face_ref("side")]},
        )
        assert (ok, err) == (True, None)
        assert state["fake_fd"].initialize_calls == [2]  # swFaceFillet
        which = [w for (w, _f) in state["fake_fd"].setfaces_calls]
        assert which == [1, 2]  # WhichFaceList set1 / set2
        assert state["fake_fd"].default_radius_m == pytest.approx(0.003)

    def test_full_round_uses_type_3_and_setfaces_3_4_5(self, monkeypatch):
        # SEAT-PROVEN 2026-06-21: full_round materializes (Δvol -1716.81 exact).
        # center face replaced -> negative vol delta.
        state = _wire(monkeypatch, metrics=((6, 8000.0), (4, 6283.0)))
        ok, err = create_fillet_face_fullround(
            _FakeDoc(),
            {"fillet_type": "full_round"},
            {
                "side1": _face_ref("s1"),
                "center": _face_ref("c"),
                "side2": _face_ref("s2"),
            },
        )
        assert (ok, err) == (True, None)
        assert state["fake_fd"].initialize_calls == [3]  # swFullRoundFillet
        which = [w for (w, _f) in state["fake_fd"].setfaces_calls]
        assert which == [3, 4, 5]  # side1 / center / side2

    def test_full_round_rejects_missing_face_ref(self):
        # a malformed full_round target fails closed at validation
        ok, err = create_fillet_face_fullround(
            _FakeDoc(),
            {"fillet_type": "full_round"},
            {},
        )
        assert ok is False and "face_ref" in err

    def test_full_round_ghost_is_false(self, monkeypatch):
        # binds 1/1/1 but zero vol delta -> fail closed (no fixture is valid)
        _wire(monkeypatch, metrics=((6, 8000.0), (6, 8000.0)))
        ok, err = create_fillet_face_fullround(
            _FakeDoc(),
            {"fillet_type": "full_round"},
            {
                "side1": _face_ref("s1"),
                "center": _face_ref("c"),
                "side2": _face_ref("s2"),
            },
        )
        assert ok is False and "did not redistribute" in err


# --- volume-change gate ---------------------------------------------------


class TestVolumeGate:
    def test_passes_on_positive_vol_delta(self, monkeypatch):
        _wire(monkeypatch, metrics=((6, 8000.0), (8, 8050.0)))
        ok, _ = create_fillet_face_fullround(
            _FakeDoc(),
            {"fillet_type": "face"},
            {"faces": [_face_ref("a"), _face_ref("b")]},
        )
        assert ok is True

    def test_passes_on_negative_vol_delta(self, monkeypatch):
        """A face fillet REMOVES material (rounds a convex edge) — the gate is
        abs(d_vol) > eps, not d_vol > 0 (seat cert: dVol = -57.94)."""
        _wire(monkeypatch, metrics=((6, 8000.0), (7, 7950.0)))
        ok, _ = create_fillet_face_fullround(
            _FakeDoc(),
            {"fillet_type": "face"},
            {"faces": [_face_ref("a"), _face_ref("b")]},
        )
        assert ok is True


# --- ghost trap (|d_vol| <= eps → False) ----------------------------------


class TestGhostTrap:
    def test_zero_vol_delta_is_ghost(self, monkeypatch):
        _wire(monkeypatch, metrics=((6, 8000.0), (8, 8000.0)))
        ok, err = create_fillet_face_fullround(
            _FakeDoc(),
            {"fillet_type": "face"},
            {"faces": [_face_ref("a"), _face_ref("b")]},
        )
        assert ok is False
        assert "did not redistribute" in err

    def test_tiny_vol_delta_is_fp_jitter_ghost(self, monkeypatch):
        _wire(monkeypatch, metrics=((6, 8000.0), (8, 8000.0 + 1e-9)))
        ok, err = create_fillet_face_fullround(
            _FakeDoc(),
            {"fillet_type": "face"},
            {"faces": [_face_ref("a"), _face_ref("b")]},
        )
        assert ok is False
        assert "did not redistribute" in err


# --- bind-guard: GetFaceCount readback ------------------------------------


class TestBindGuard:
    def test_unbound_face_set_fails_closed(self, monkeypatch):
        """If SetFaces silently no-ops (GetFaceCount stays 0 — the bare-list
        makepy trap), the handler must fail closed BEFORE CreateFeature."""
        _wire(monkeypatch, typed_qi_returns=_FakeFD(facecount_override=0))
        ok, err = create_fillet_face_fullround(
            _FakeDoc(),
            {"fillet_type": "face"},
            {"faces": [_face_ref("a"), _face_ref("b")]},
        )
        assert ok is False
        assert "did not bind" in err


# --- CreateFeature return-marshaling noise --------------------------------


class TestCreateFeatureNoise:
    def test_member_not_found_swallowed_when_volume_moves(self, monkeypatch):
        """CreateFeature may raise DISP_E_MEMBERNOTFOUND on its return while the
        solid is already built — swallowed; the volume delta decides."""
        _wire(monkeypatch, metrics=((6, 8000.0), (8, 8050.0)))
        exc = Exception()
        exc.args = (-2147352573, "Member not found.", None, None)
        doc = _FakeDoc(create_feature_raises=exc)
        ok, _ = create_fillet_face_fullround(
            doc,
            {"fillet_type": "face"},
            {"faces": [_face_ref("a"), _face_ref("b")]},
        )
        assert ok is True

    def test_unexpected_com_error_fails_closed(self, monkeypatch):
        _wire(monkeypatch, metrics=((6, 8000.0), (8, 8050.0)))
        exc = Exception()
        exc.args = (-2147467259, "Unspecified error", None, None)  # E_FAIL
        doc = _FakeDoc(create_feature_raises=exc)
        ok, err = create_fillet_face_fullround(
            doc,
            {"fillet_type": "face"},
            {"faces": [_face_ref("a"), _face_ref("b")]},
        )
        assert ok is False
        assert "CreateFeature raised" in err


# --- wrong face count → fail closed ---------------------------------------


class TestFaceCount:
    def test_face_with_one_face_rejected(self):
        ok, err = create_fillet_face_fullround(
            _FakeDoc(),
            {"fillet_type": "face"},
            {"faces": [_face_ref("only")]},
        )
        assert ok is False
        assert "2" in err or "face refs" in err

    def test_face_with_three_faces_rejected(self):
        ok, err = create_fillet_face_fullround(
            _FakeDoc(),
            {"fillet_type": "face"},
            {"faces": [_face_ref("a"), _face_ref("b"), _face_ref("c")]},
        )
        assert ok is False
        assert "2" in err or "face refs" in err


# --- validation (fail-closed) ---------------------------------------------


class TestValidation:
    def test_unknown_fillet_type_rejected(self):
        ok, err = create_fillet_face_fullround(
            _FakeDoc(),
            {"fillet_type": "edge"},
            {"faces": [_face_ref("a"), _face_ref("b")]},
        )
        assert ok is False and "fillet_type" in err

    def test_missing_fillet_type_rejected(self):
        ok, err = create_fillet_face_fullround(
            _FakeDoc(),
            {},
            {"faces": [_face_ref("a"), _face_ref("b")]},
        )
        assert ok is False and "fillet_type" in err

    def test_feature_not_dict_rejected(self):
        ok, err = create_fillet_face_fullround(
            _FakeDoc(),
            "bad",
            {"faces": [_face_ref("a"), _face_ref("b")]},
        )
        assert ok is False and "feature must be a dict" in err

    def test_target_not_dict_rejected(self):
        ok, err = create_fillet_face_fullround(
            _FakeDoc(),
            {"fillet_type": "face"},
            "bad",
        )
        assert ok is False and "target must be a dict" in err

    def test_face_target_not_list_rejected(self):
        ok, err = create_fillet_face_fullround(
            _FakeDoc(),
            {"fillet_type": "face"},
            {"faces": "not_a_list"},
        )
        assert ok is False and "list" in err

    def test_non_positive_radius_rejected(self, monkeypatch):
        _wire(monkeypatch)
        ok, err = create_fillet_face_fullround(
            _FakeDoc(),
            {"fillet_type": "face", "radius_mm": 0},
            {"faces": [_face_ref("a"), _face_ref("b")]},
        )
        assert ok is False and "radius_mm" in err

    def test_non_numeric_radius_rejected(self, monkeypatch):
        _wire(monkeypatch)
        ok, err = create_fillet_face_fullround(
            _FakeDoc(),
            {"fillet_type": "face", "radius_mm": "big"},
            {"faces": [_face_ref("a"), _face_ref("b")]},
        )
        assert ok is False and "radius_mm" in err

    def test_unresolved_face_fails_closed(self, monkeypatch):
        _wire(monkeypatch, resolve_entity=None)
        ok, err = create_fillet_face_fullround(
            _FakeDoc(),
            {"fillet_type": "face"},
            {"faces": [_face_ref("a"), _face_ref("b")]},
        )
        assert ok is False and ("did not resolve" in err or "resolve" in err)


# --- never-raise ----------------------------------------------------------


class TestNeverRaise:
    def test_resolve_exception_caught(self, monkeypatch):
        _wire(monkeypatch)

        def boom(doc, ref):
            raise RuntimeError("COM wall in resolve")

        monkeypatch.setattr(fn, "resolve_manifest_face", boom)
        ok, err = create_fillet_face_fullround(
            _FakeDoc(),
            {"fillet_type": "face"},
            {"faces": [_face_ref("a"), _face_ref("b")]},
        )
        assert ok is False and "raised" in err

    def test_create_definition_exception_caught(self, monkeypatch):
        _wire(monkeypatch)
        doc = _FakeDoc()

        def boom(type_id):
            raise RuntimeError("COM wall in CreateDefinition")

        doc.FeatureManager.CreateDefinition = boom
        ok, err = create_fillet_face_fullround(
            doc,
            {"fillet_type": "face"},
            {"faces": [_face_ref("a"), _face_ref("b")]},
        )
        assert ok is False and "raised" in err

    def test_initialize_false_fails_closed(self, monkeypatch):
        fake_fd = _FakeFD()

        def init_false(t):
            fake_fd.initialize_calls.append(int(t))
            return False

        fake_fd.Initialize = init_false  # type: ignore[method-assign]
        _wire(monkeypatch, typed_qi_returns=fake_fd)
        ok, err = create_fillet_face_fullround(
            _FakeDoc(),
            {"fillet_type": "face"},
            {"faces": [_face_ref("a"), _face_ref("b")]},
        )
        assert ok is False and "Initialize" in err


# --- recipe pin -----------------------------------------------------------


class TestRecipePin:
    def test_create_definition_id_is_sw_fm_fillet(self, monkeypatch):
        _wire(monkeypatch)
        doc = _FakeDoc()
        ok, _ = create_fillet_face_fullround(
            doc,
            {"fillet_type": "face"},
            {"faces": [_face_ref("a"), _face_ref("b")]},
        )
        assert ok
        assert doc.FeatureManager.def_calls == [1]  # _SW_FM_FILLET

    def test_default_radius_in_metres(self, monkeypatch):
        state = _wire(monkeypatch)
        ok, _ = create_fillet_face_fullround(
            _FakeDoc(),
            {"fillet_type": "face", "radius_mm": 7.5},
            {"faces": [_face_ref("a"), _face_ref("b")]},
        )
        assert ok
        assert state["fake_fd"].default_radius_m == pytest.approx(0.0075)

    def test_default_radius_default_value(self, monkeypatch):
        state = _wire(monkeypatch)
        ok, _ = create_fillet_face_fullround(
            _FakeDoc(),
            {"fillet_type": "face"},  # radius_mm omitted → default 5.0
            {"faces": [_face_ref("a"), _face_ref("b")]},
        )
        assert ok
        assert state["fake_fd"].default_radius_m == pytest.approx(0.005)


# --- registry gate --------------------------------------------------------


class TestRegistryGate:
    def test_fillet_face_registered_when_green(self):
        from ai_sw_bridge.features import HANDLER_REGISTRY

        assert fn.SPIKE_STATUS == "GREEN"
        assert "fillet_face" in HANDLER_REGISTRY
        # full-round did not ship — its sibling names must not be advertised
        assert "fillet_full_round" not in HANDLER_REGISTRY
        assert "full_round" not in HANDLER_REGISTRY
        assert "fillet_face_fullround" not in HANDLER_REGISTRY

    def test_handler_callable_matches_contract(self):
        assert callable(create_fillet_face_fullround)
