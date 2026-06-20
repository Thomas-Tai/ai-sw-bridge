"""W68 offline tests — ``fillet_face_fullround`` handler (UNFIRED contract).

Fake-COM harness pinning the dispatch matrix (face vs full_round), the
volume-change anti-ghost gate (the W65/W66 doctrine inverse — face delta is
UNRELIABLE because full-round fillets CONSUME the center face), the mark-
routing spy (1/2 for face, 3/4/5 for full-round), the FilletType→Initialize
arg spy (2 for face / 3 for full_round), fail-closed validation, never-
raise, and the UNFIRED registry gate.

COM seams are patched on the lane module itself
(``features.fillet_face_fullround``) per the registry lane protocol — never
on ``mutate``.

The brief names the volume-change gate as THE anti-ghost witness:
``verify.gate_additive_solid`` (which requires ``d_faces > 0``) would
false-fail a successful full-round (the inverse of the W65 sketched_bend
trap — there the fold gate required volume change; here the additive gate
would require face delta).  The handler gates inline on
``abs(d_vol) > verify.VOL_EPS_MM3``; ``d_faces`` is logged as corroboration.
"""

from __future__ import annotations

import pythoncom
import pytest

from ai_sw_bridge.features import fillet_face_fullround as fn
from ai_sw_bridge.features.fillet_face_fullround import (
    create_fillet_face_fullround,
)


# --- fake COM objects -----------------------------------------------------

class _FakeFD:
    """Fake ISimpleFilletFeatureData2.  Records Initialize(type) + DefaultRadius
    assignments so the spy tests can assert the FilletType arg."""
    def __init__(self) -> None:
        self.initialize_calls: list[int] = []
        self.default_radius_m: float | None = None
        self.setfaces_calls: list[tuple] = []

    def Initialize(self, fillet_type: int) -> bool:
        self.initialize_calls.append(int(fillet_type))
        return True

    # DefaultRadius is a setter PROPERTY on the real interface.
    @property
    def DefaultRadius(self) -> float:
        return self.default_radius_m if self.default_radius_m is not None else 0.0

    @DefaultRadius.setter
    def DefaultRadius(self, value: float) -> None:
        self.default_radius_m = float(value)

    def SetFaces(self, which: int, faces: object) -> None:
        self.setfaces_calls.append((which, faces))


class _FakeFM:
    """Fake IFeatureManager.  ``CreateDefinition`` returns a sentinel that
    ``typed_qi`` (monkeypatched on the lane module) promotes to ``_FakeFD``.
    ``CreateFeature`` returns the value supplied at construction time —
    including an explicit ``None`` (the ghost-trap test path)."""

    _SENTINEL_DATA = object()
    _USE_DEFAULT = object()  # distinguishes "no value" from "explicit None"

    def __init__(self, *, create_feature_returns: object = _USE_DEFAULT) -> None:
        self.def_calls: list[int] = []
        self.create_calls: list = []
        if create_feature_returns is self._USE_DEFAULT:
            self._create_feature_returns: object = object()
        else:
            self._create_feature_returns = create_feature_returns

    def CreateDefinition(self, type_id: int):
        self.def_calls.append(type_id)
        return self._SENTINEL_DATA

    def CreateFeature(self, fd):
        self.create_calls.append(fd)
        return self._create_feature_returns


class _FakeDoc:
    def __init__(self, *, create_feature_returns: object = _FakeFM._USE_DEFAULT) -> None:
        self.FeatureManager = _FakeFM(create_feature_returns=create_feature_returns)
        self.cleared = False
        self.rebuilds = 0

    def ClearSelection2(self, flag):
        self.cleared = True

    def ForceRebuild3(self, flag):
        self.rebuilds += 1


# --- fake face_ref dict (handler-consumable manifest-face shape) ----------

def _face_ref(role: str = "face") -> dict:
    """A minimal manifest-face dict that ``resolve_manifest_face`` can accept
    through ``DurableRef.from_manifest_face`` — the handler's resolve path."""
    return {
        "normal": [0.0, 0.0, 1.0],
        "centroid": [0.0, 0.0, 0.01],
        "area_mm2": 1200.0,
        "role_hint": role,
    }


# --- monkeypatch wiring ----------------------------------------------------


class _ResResult:
    """Stand-in for ``RefResolution`` returned by the fake resolve_manifest_face."""
    def __init__(self, entity: object, method: str = "persist"):
        self.entity = entity
        self.method = method


_UNSET = object()


def _wire(
    monkeypatch,
    *,
    metrics=((6, 8000.0), (8, 8050.0)),
    select_ok: bool = True,
    resolve_entity: object | None = _UNSET,
    typed_qi_returns=None,
) -> dict:
    """Patch the COM seams on ``features.fillet_face_fullround``.

    Seams patched:
      * ``fn.verify.solid_metrics``    — driven by ``metrics`` ((before),(after))
      * ``fn.resolve_manifest_face``   — returns a live entity (the fake
        sentinel ``resolve_entity`` by default) for every face_ref
      * ``fn.select_entity``           — returns ``select_ok``; records every call
      * ``ai_sw_bridge.com.earlybind.typed_qi`` — returns ``typed_qi_returns``
        (default a fresh ``_FakeFD``).  The handler imports typed_qi locally
        inside the function body, so the patch must live on the source
        module — lane-namespace patches would not be observed.

    Returns a state dict the caller can inspect after the handler returns:
      {"selects": [(entity, append, mark), ...], "fake_fd": _FakeFD}
    """
    state: dict = {"selects": [], "fake_fd": None}

    seq = list(metrics)
    sstate = {"n": 0}

    def fake_metrics(doc):
        v = seq[min(sstate["n"], len(seq) - 1)]
        sstate["n"] += 1
        return v

    monkeypatch.setattr(fn.verify, "solid_metrics", fake_metrics)

    # ``resolve_entity`` defaults to ``_UNSET`` so callers can distinguish
    # "use a fresh live-entity sentinel" (no arg) from "simulate an unresolved
    # face" (explicit ``None``).  An unresolved face MUST propagate entity=None
    # through the handler's resolve_manifest_face call.
    if resolve_entity is _UNSET:
        sentinel_entity: object | None = object()
    else:
        sentinel_entity = resolve_entity

    def fake_resolve(doc, ref):
        return _ResResult(sentinel_entity)

    monkeypatch.setattr(fn, "resolve_manifest_face", fake_resolve)

    def fake_select(entity, append=False, mark=0):
        state["selects"].append((entity, append, mark))
        return select_ok

    monkeypatch.setattr(fn, "select_entity", fake_select)

    fake_fd = _FakeFD() if typed_qi_returns is None else typed_qi_returns
    state["fake_fd"] = fake_fd

    import ai_sw_bridge.com.earlybind as eb
    monkeypatch.setattr(eb, "typed_qi", lambda data, iface, module=None: fake_fd)

    return state


# --- SPIKE_STATUS pin -----------------------------------------------------

class TestSpikeStatus:
    def test_unfired_before_seat_proof(self):
        assert fn.SPIKE_STATUS == "UNFIRED"


# --- dispatch matrix: face vs full_round ---------------------------------

class TestDispatch:
    def test_face_uses_type_2_and_marks_1_2(self, monkeypatch):
        state = _wire(monkeypatch)
        doc = _FakeDoc()
        ok, err = create_fillet_face_fullround(
            doc,
            {"fillet_type": "face", "radius_mm": 3.0},
            {"faces": [_face_ref("top"), _face_ref("side")]},
        )
        assert (ok, err) == (True, None)
        assert state["fake_fd"].initialize_calls == [2]  # swFaceFillet
        marks = [m for (_e, _a, m) in state["selects"]]
        assert marks == [1, 2]  # set1 / set2
        appends = [a for (_e, a, _m) in state["selects"]]
        assert appends == [False, True]
        # radius is set (in metres)
        assert state["fake_fd"].default_radius_m == pytest.approx(0.003)

    def test_full_round_uses_type_3_and_marks_3_4_5(self, monkeypatch):
        state = _wire(monkeypatch)
        doc = _FakeDoc()
        ok, err = create_fillet_face_fullround(
            doc,
            {"fillet_type": "full_round"},
            {
                "side1": _face_ref("side1"),
                "center": _face_ref("center"),
                "side2": _face_ref("side2"),
            },
        )
        assert (ok, err) == (True, None)
        assert state["fake_fd"].initialize_calls == [3]  # swFullRoundFillet
        marks = [m for (_e, _a, m) in state["selects"]]
        assert marks == [3, 4, 5]
        appends = [a for (_e, a, _m) in state["selects"]]
        assert appends == [False, True, True]


# --- volume-change gate (the WHY-NOT-additive rationale) -----------------

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
        """A fillet can remove material (a blend that cuts a sliver) — the
        gate is abs(d_vol) > eps, not d_vol > 0."""
        _wire(monkeypatch, metrics=((6, 8000.0), (7, 7950.0)))
        ok, _ = create_fillet_face_fullround(
            _FakeDoc(),
            {"fillet_type": "face"},
            {"faces": [_face_ref("a"), _face_ref("b")]},
        )
        assert ok is True

    def test_full_round_zero_face_delta_still_passes(self, monkeypatch):
        """Full-round may CONSUME the center face (d_faces ≤ 0).  The additive
        gate (d_faces > 0) would false-fail here — the W65 inverse trap.
        Volume delta alone decides."""
        _wire(monkeypatch, metrics=((10, 8000.0), (9, 8120.0)))
        ok, _ = create_fillet_face_fullround(
            _FakeDoc(),
            {"fillet_type": "full_round"},
            {
                "side1": _face_ref("s1"),
                "center": _face_ref("c"),
                "side2": _face_ref("s2"),
            },
        )
        assert ok is True

    def test_full_round_negative_face_delta_passes(self, monkeypatch):
        """Center-face consumed, volume barely moved — still a real fillet."""
        _wire(monkeypatch, metrics=((12, 9000.0), (10, 9005.0)))
        ok, _ = create_fillet_face_fullround(
            _FakeDoc(),
            {"fillet_type": "full_round"},
            {
                "side1": _face_ref("s1"),
                "center": _face_ref("c"),
                "side2": _face_ref("s2"),
            },
        )
        assert ok is True


# --- ghost trap (|d_vol| ≤ eps → False) ----------------------------------

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
        """Below VOL_EPS_MM3 = 1e-6, d_vol is FP noise (the hem v5 NO_OP)."""
        _wire(monkeypatch, metrics=((6, 8000.0), (8, 8000.0 + 1e-9)))
        ok, err = create_fillet_face_fullround(
            _FakeDoc(),
            {"fillet_type": "face"},
            {"faces": [_face_ref("a"), _face_ref("b")]},
        )
        assert ok is False
        assert "did not redistribute" in err

    def test_non_feature_return_is_ghost(self, monkeypatch):
        _wire(monkeypatch, metrics=((6, 8000.0), (8, 8050.0)))
        # Force CreateFeature to return None (the classic ghost trap).
        doc = _FakeDoc(create_feature_returns=None)
        ok, err = create_fillet_face_fullround(
            doc,
            {"fillet_type": "face"},
            {"faces": [_face_ref("a"), _face_ref("b")]},
        )
        assert ok is False
        assert "non-Feature" in err or "ghost" in err or "rejected" in err


# --- wrong face count → fail closed --------------------------------------

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

    def test_full_round_missing_center_rejected(self):
        ok, err = create_fillet_face_fullround(
            _FakeDoc(),
            {"fillet_type": "full_round"},
            {"side1": _face_ref("s1"), "side2": _face_ref("s2")},
        )
        assert ok is False
        assert "center" in err or "side1/center/side2" in err

    def test_full_round_side1_not_dict_rejected(self):
        ok, err = create_fillet_face_fullround(
            _FakeDoc(),
            {"fillet_type": "full_round"},
            {"side1": "not_a_dict",
             "center": _face_ref("c"), "side2": _face_ref("s2")},
        )
        assert ok is False
        assert "side1" in err


# --- validation (fail-closed) --------------------------------------------

class TestValidation:
    def test_unknown_fillet_type_rejected(self):
        ok, err = create_fillet_face_fullround(
            _FakeDoc(),
            {"fillet_type": "edge"},
            {"faces": [_face_ref("a"), _face_ref("b")]},
        )
        assert ok is False
        assert "fillet_type" in err

    def test_missing_fillet_type_rejected(self):
        ok, err = create_fillet_face_fullround(
            _FakeDoc(), {}, {"faces": [_face_ref("a"), _face_ref("b")]},
        )
        assert ok is False and "fillet_type" in err

    def test_feature_not_dict_rejected(self):
        ok, err = create_fillet_face_fullround(
            _FakeDoc(), "bad", {"faces": [_face_ref("a"), _face_ref("b")]},
        )
        assert ok is False and "feature must be a dict" in err

    def test_target_not_dict_rejected(self):
        ok, err = create_fillet_face_fullround(
            _FakeDoc(), {"fillet_type": "face"}, "bad",
        )
        assert ok is False and "target must be a dict" in err

    def test_face_target_not_list_rejected(self):
        ok, err = create_fillet_face_fullround(
            _FakeDoc(),
            {"fillet_type": "face"},
            {"faces": "not_a_list"},
        )
        assert ok is False and "list" in err

    def test_non_positive_radius_rejected(self):
        ok, err = create_fillet_face_fullround(
            _FakeDoc(),
            {"fillet_type": "face", "radius_mm": 0},
            {"faces": [_face_ref("a"), _face_ref("b")]},
        )
        assert ok is False and "radius_mm" in err

    def test_non_numeric_radius_rejected(self):
        ok, err = create_fillet_face_fullround(
            _FakeDoc(),
            {"fillet_type": "face", "radius_mm": "big"},
            {"faces": [_face_ref("a"), _face_ref("b")]},
        )
        assert ok is False and "radius_mm" in err

    def test_select_failure_fails_closed(self, monkeypatch):
        _wire(monkeypatch, select_ok=False)
        ok, err = create_fillet_face_fullround(
            _FakeDoc(),
            {"fillet_type": "face"},
            {"faces": [_face_ref("a"), _face_ref("b")]},
        )
        assert ok is False
        assert "select_entity" in err or "select" in err

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


# --- recipe pin (CreateDefinition id + unit conversion) -------------------

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
    def test_kind_not_registered_when_unfired(self):
        from ai_sw_bridge.features import HANDLER_REGISTRY
        assert fn.SPIKE_STATUS == "UNFIRED"
        assert "fillet_face" not in HANDLER_REGISTRY
        assert "fillet_full_round" not in HANDLER_REGISTRY
        assert "fillet_face_fullround" not in HANDLER_REGISTRY

    def test_handler_callable_matches_contract(self):
        assert callable(create_fillet_face_fullround)
