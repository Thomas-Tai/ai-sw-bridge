"""Offline tests — ``mbd`` (DimXpert / MBD PMI) observe lane.

Mock-tests ``_sw_get_mbd_impl`` without a SW seat. The handler walks
``doc.Extension.DimXpertManager("", False) -> DimXpertPart -> GetAnnotations()``
and classifies each annotation into datums / dimensions / geometric_tolerances by
which witness getter it answers (the live swdimxpert objects are late-bound; a
datum has ``Identifier`` but not ``GetNominalValue``, etc.).

The headline coverage is the DUAL-BRANCH asymmetric-deviation bridge (directive
#3): the DimXpert-native surface exposes no independent +/- getters, so the lane
bridges ``GetDisplayEntity -> IDisplayDimension -> IDimension.Tolerance ->
ITolerance.{GetMaxValue, GetMinValue}`` as a BEST-EFFORT enhancement.

  * Case 1 — bridge succeeds: payload carries ``upper_deviation`` /
    ``lower_deviation`` and ``asymmetric_extracted=True``.
  * Case 2 — bridge faults: payload falls back to the symmetric base fields
    (``nominal`` / ``symmetric_tolerance`` / ``fit_code``) with
    ``asymmetric_extracted=False`` and ``None`` bounds. The lane never crashes.

The live-seat PAE (real ``+0.2/-0.05`` against a GUI-authored fixture) is a
documented pending gate — see ``docs/pending_gates.md``.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

import ai_sw_bridge.observe_mbd as mbd
from ai_sw_bridge.observe_mbd import SW_DOC_PART, _sw_get_mbd_impl as run


# ---------------------------------------------------------------------------
# Fakes — plain objects so an ABSENT attribute raises AttributeError, which is
# exactly the signal the lane's _read-based discrimination relies on.
# ---------------------------------------------------------------------------


class _Feature:
    def __init__(self, name: str) -> None:
        self.Name = name


class _Tolerance:
    """ITolerance stand-in for the asymmetric bridge."""

    def __init__(self, max_v: float, min_v: float) -> None:
        self._max = max_v
        self._min = min_v

    def GetMaxValue(self) -> float:
        return self._max

    def GetMinValue(self) -> float:
        return self._min


class _Dim:
    def __init__(self, tol: Any) -> None:
        self.Tolerance = tol


class _DisplayDimension:
    """IDisplayDimension stand-in; ``GetDimension2(i)`` -> IDimension."""

    def __init__(self, dim: Any, *, raises: bool = False) -> None:
        self._dim = dim
        self._raises = raises

    def GetDimension2(self, i: int) -> Any:
        if self._raises:
            raise RuntimeError("display-dim bridge boom")
        return self._dim


class _DatumAnno:
    def __init__(self, label: str, feature: str | None = None) -> None:
        self.Name = f"Datum-{label}"
        self.Identifier = label
        self._feature = _Feature(feature) if feature else None

    def GetModelFeature(self) -> Any:
        return self._feature


class _DimensionAnno:
    """Size dimension. Has GetNominalValue + symmetric Tolerance; optionally a
    display-entity chain for the asymmetric bridge."""

    def __init__(
        self,
        *,
        nominal: float,
        symmetric: float,
        fit_code: str = "",
        display: Any = None,
        feature: str | None = None,
        type_name: str = "Size",
    ) -> None:
        self.Name = type_name
        self._nominal = nominal
        self.Tolerance = symmetric
        self.LimitsAndFitsCode = fit_code
        self._display = display
        self._feature = _Feature(feature) if feature else None

    def GetNominalValue(self) -> float:
        return self._nominal

    def GetDisplayEntity(self) -> Any:
        if self._display is None:
            raise RuntimeError("no display entity")
        return self._display

    def GetModelFeature(self) -> Any:
        return self._feature


class _GTolAnno:
    """Geometric tolerance. Has Tolerance (R8) + datum-reference arrays, but no
    Identifier and no GetNominalValue."""

    def __init__(
        self,
        *,
        symbol: str,
        value: float,
        primary: list | None = None,
        secondary: list | None = None,
        tertiary: list | None = None,
    ) -> None:
        self.Name = symbol
        self.Tolerance = value
        self._primary = [_DatumRef(x) for x in (primary or [])]
        self._secondary = [_DatumRef(x) for x in (secondary or [])]
        self._tertiary = [_DatumRef(x) for x in (tertiary or [])]

    def GetModelFeature(self) -> Any:
        return None

    def GetPrimaryDatums(self) -> list:
        return self._primary

    def GetSecondaryDatums(self) -> list:
        return self._secondary

    def GetTertiaryDatums(self) -> list:
        return self._tertiary


class _DatumRef:
    def __init__(self, label: str) -> None:
        self.Identifier = label


class _Part:
    def __init__(self, annos: list) -> None:
        self._annos = annos

    def GetFeatureCount(self) -> int:
        return 0

    def GetAnnotationCount(self) -> int:
        return len(self._annos)

    def GetAnnotations(self) -> list:
        return self._annos


class _Manager:
    def __init__(self, part: Any, schema: str = "Default") -> None:
        self._part = part
        self.SchemaName = schema

    @property
    def DimXpertPart(self) -> Any:
        return self._part


class _Ext:
    def __init__(self, mgr: Any) -> None:
        self._mgr = mgr
        self.calls: list = []

    def DimXpertManager(self, config: str, create_schema: bool) -> Any:
        self.calls.append((config, create_schema))
        return self._mgr


class _Doc:
    def __init__(
        self,
        annos: list,
        *,
        doc_type: int = SW_DOC_PART,
        path: str = "C:/x/block.SLDPRT",
    ) -> None:
        self._ext = _Ext(_Manager(_Part(annos)))
        self.Extension = self._ext
        self._doc_type = doc_type
        self._path = path

    def GetPathName(self) -> str:
        return self._path

    def GetType(self) -> int:
        return self._doc_type


@pytest.fixture(autouse=True)
def _patch_qi(monkeypatch):
    """typed_qi -> identity (mocks ARE the typed proxy); wrapper_module -> None."""
    monkeypatch.setattr(mbd, "typed_qi", lambda obj, iface, **kw: obj)
    monkeypatch.setattr(mbd, "wrapper_module", lambda: None)


# ---------------------------------------------------------------------------
# Dual-branch asymmetric bridge — the headline coverage
# ---------------------------------------------------------------------------


def test_dimension_asymmetric_bridge_succeeds():
    """Case 1: the IDisplayDimension -> ITolerance bridge yields +0.2 / -0.05."""
    display = _DisplayDimension(_Dim(_Tolerance(0.2, -0.05)))
    anno = _DimensionAnno(
        nominal=100.0,
        symmetric=0.1,
        fit_code="",
        display=display,
        feature="Boss-Extrude1",
    )
    out = run(_Doc([anno]))

    assert out["ok"] is True
    assert len(out["dimensions"]) == 1
    dim = out["dimensions"][0]
    assert dim["nominal"] == 100.0
    assert dim["asymmetric_extracted"] is True
    assert dim["upper_deviation"] == 0.2
    assert dim["lower_deviation"] == -0.05
    assert dim["attached_feature"] == "Boss-Extrude1"


def test_dimension_asymmetric_bridge_faults_falls_back():
    """Case 2: the bridge raises -> graceful fallback to symmetric base fields."""
    display = _DisplayDimension(_Dim(_Tolerance(0.2, -0.05)), raises=True)
    anno = _DimensionAnno(nominal=50.0, symmetric=0.1, fit_code="h7", display=display)
    out = run(_Doc([anno]))

    assert out["ok"] is True
    dim = out["dimensions"][0]
    assert dim["nominal"] == 50.0
    assert dim["symmetric_tolerance"] == 0.1
    assert dim["fit_code"] == "h7"
    assert dim["asymmetric_extracted"] is False
    assert dim["upper_deviation"] is None
    assert dim["lower_deviation"] is None


def test_dimension_no_display_entity_falls_back():
    """A dimension with no display-entity chain at all also falls back cleanly."""
    anno = _DimensionAnno(nominal=25.0, symmetric=0.05, display=None)
    out = run(_Doc([anno]))
    dim = out["dimensions"][0]
    assert dim["asymmetric_extracted"] is False
    assert dim["nominal"] == 25.0


# ---------------------------------------------------------------------------
# Datums + geometric tolerances
# ---------------------------------------------------------------------------


def test_datum_extraction():
    anno = _DatumAnno("A", feature="Face<Bottom>")
    out = run(_Doc([anno]))
    assert len(out["datums"]) == 1
    d = out["datums"][0]
    assert d["label"] == "A"
    assert d["attached_feature"] == "Face<Bottom>"


def test_geometric_tolerance_extraction():
    anno = _GTolAnno(
        symbol="Position", value=0.05, primary=["A"], secondary=["B"], tertiary=["C"]
    )
    out = run(_Doc([anno]))
    assert len(out["geometric_tolerances"]) == 1
    g = out["geometric_tolerances"][0]
    assert g["symbol"] == "Position"
    assert g["tolerance_value"] == 0.05
    assert g["primary_datum"] == "A"
    assert g["secondary_datum"] == "B"
    assert g["tertiary_datum"] == "C"


# ---------------------------------------------------------------------------
# Full payload — schema shape + JSON-serializability
# ---------------------------------------------------------------------------


def test_full_payload_categorizes_and_serializes():
    annos = [
        _DatumAnno("A", feature="Face<Bottom>"),
        _DimensionAnno(
            nominal=100.0,
            symmetric=0.1,
            display=_DisplayDimension(_Dim(_Tolerance(0.2, -0.05))),
        ),
        _DimensionAnno(nominal=50.0, symmetric=0.1),  # symmetric, no bridge
        _GTolAnno(symbol="Flatness", value=0.02, primary=["A"]),
    ]
    out = run(_Doc(annos, path="C:/parts/mbd_block.SLDPRT"))

    assert out["ok"] is True
    assert out["doc_path"] == "C:/parts/mbd_block.SLDPRT"
    assert out["annotation_count"] == 4
    assert len(out["datums"]) == 1
    assert len(out["dimensions"]) == 2
    assert len(out["geometric_tolerances"]) == 1
    # one dimension bridged, one fell back
    flags = sorted(d["asymmetric_extracted"] for d in out["dimensions"])
    assert flags == [False, True]
    # the entire payload must round-trip through json (the wire contract)
    json.dumps(out)


def test_strict_bucket_separation_keys():
    """Each bucket exposes exactly the directive-specified key set."""
    annos = [
        _DatumAnno("A"),
        _DimensionAnno(
            nominal=10.0,
            symmetric=0.1,
            display=_DisplayDimension(_Dim(_Tolerance(0.1, -0.1))),
        ),
        _GTolAnno(symbol="Position", value=0.05, primary=["A"]),
    ]
    out = run(_Doc(annos))
    assert set(out["datums"][0]) == {"label", "attached_feature", "name"}
    assert set(out["dimensions"][0]) == {
        "type",
        "nominal",
        "symmetric_tolerance",
        "fit_code",
        "asymmetric_extracted",
        "upper_deviation",
        "lower_deviation",
        "attached_feature",
    }
    assert set(out["geometric_tolerances"][0]) == {
        "symbol",
        "tolerance_value",
        "primary_datum",
        "secondary_datum",
        "tertiary_datum",
    }


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------


def test_no_active_doc():
    out = run(None)
    assert out["ok"] is False
    assert out["error"] == "no_active_doc"


def test_rejects_non_part():
    out = run(_Doc([], doc_type=2))  # swDocASSEMBLY
    assert out["ok"] is False
    assert "requires a part" in out["error"]


def test_empty_schema_is_ok_not_error():
    """A part with a manager but no annotations is empty PMI, not a failure."""
    out = run(_Doc([]))
    assert out["ok"] is True
    assert out["annotation_count"] == 0
    assert out["datums"] == []
    assert out["dimensions"] == []
    assert out["geometric_tolerances"] == []


def test_manager_called_with_create_schema_false():
    """Read path must NOT spin up a fresh schema (CreateSchema=False)."""
    doc = _Doc([_DatumAnno("A")])
    run(doc)
    assert doc._ext.calls == [("", False)]


def test_part_none_means_empty_pmi():
    """DimXpertPart None (no authored schema) -> empty payload, ok=True."""

    class _MgrNoPart:
        SchemaName = ""
        DimXpertPart = None

    class _ExtNoPart:
        def DimXpertManager(self, c, s):
            return _MgrNoPart()

    class _DocNoPart:
        Extension = _ExtNoPart()

        def GetPathName(self):
            return "x"

        def GetType(self):
            return SW_DOC_PART

    out = run(_DocNoPart())
    assert out["ok"] is True
    assert out["annotation_count"] == 0
