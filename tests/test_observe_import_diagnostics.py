"""Offline tests — ``import_diagnostics`` observe lane.

Mock-tests ``_sw_get_import_diagnostics_impl`` without a SW seat. The handler:
  * reads the body breakdown via ``doc.GetBodies2(0|1, False)`` (direct),
  * runs ``IBody2.Check3 -> IFaultEntity`` per body (via late-bound ``resolve``),
    decoding ``ErrorCode`` through ``swFaultEntityErrorCode_e``,
  * calls ``IPartDoc.ImportDiagnosis`` READ-ONLY (all repair flags False),
  * derives a single-bool ``clean`` verdict.

The fakes stand in for that proxy chain. The genuinely-corrupt B-rep case (which
the SW kernel resists manufacturing on a live seat — measure-first finding,
probe_import_diagnostics) is exercised HERE with full control over Check3 faults.
"""

from __future__ import annotations

from typing import Any

import pytest

import ai_sw_bridge.observe_import_diag as idiag
from ai_sw_bridge.observe_import_diag import _sw_get_import_diagnostics_impl as run
from ai_sw_bridge.observe_import_diag import SW_DOC_PART, _fault_code_name


class _FakeFault:
    """IFaultEntity stand-in: Count + indexed ErrorCode."""

    def __init__(self, codes: list[int]) -> None:
        self._codes = codes

    @property
    def Count(self) -> int:
        return len(self._codes)

    def ErrorCode(self, i: int) -> int:
        return self._codes[i]


class _FakeBody:
    """IBody2 stand-in: Check3 is a PROPERTY returning IFaultEntity (real form);
    set ``check3_raises`` to exercise the fail-soft path."""

    def __init__(self, codes: list[int] | None = None, *, check3_raises: bool = False) -> None:
        self._fault = _FakeFault(codes or [])
        self._raises = check3_raises

    @property
    def Check3(self) -> Any:
        if self._raises:
            raise RuntimeError("Check3 boom")
        return self._fault


class _FakeDoc:
    def __init__(
        self,
        *,
        solids: list = None,
        sheets: list = None,
        doc_type: int = SW_DOC_PART,
        import_status: int = 1,
        import_raises: bool = False,
    ) -> None:
        self._solids = solids if solids is not None else []
        self._sheets = sheets if sheets is not None else []
        self._doc_type = doc_type
        self._import_status = import_status
        self._import_raises = import_raises
        self.import_diag_calls: list[tuple] = []

    def GetType(self) -> int:
        return self._doc_type

    def GetPathName(self) -> str:
        return "C:/tmp/imp.sldprt"

    def GetBodies2(self, btype: int, vis: bool) -> Any:
        if btype == 0:
            return tuple(self._solids)
        if btype == 1:
            return tuple(self._sheets)
        return ()

    def ImportDiagnosis(self, close_gaps: bool, remove_faces: bool,
                        fix_faces: bool, options: int) -> int:
        self.import_diag_calls.append((close_gaps, remove_faces, fix_faces, options))
        if self._import_raises:
            raise RuntimeError("ImportDiagnosis boom")
        return self._import_status


def _fake_resolve(obj: Any, name: str) -> Any:
    v = getattr(obj, name)
    return v() if callable(v) else v


@pytest.fixture
def patched(monkeypatch):
    def _apply(doc):
        monkeypatch.setattr(idiag, "get_sw_app", lambda: object())
        monkeypatch.setattr(idiag, "get_active_doc", lambda sw: doc)
        monkeypatch.setattr(idiag, "resolve", _fake_resolve)
    return _apply


class TestHealthy:
    def test_clean_solid(self, patched):
        patched(_FakeDoc(solids=[_FakeBody()]))
        r = run()
        assert r["ok"] is True
        assert r["clean"] is True
        assert r["solid_body_count"] == 1
        assert r["surface_body_count"] == 0
        assert r["total_body_count"] == 1
        assert r["total_fault_count"] == 0
        assert r["faults_by_code"] == {}
        assert r["import_diagnosis_status"] == 1
        assert r["doc_path"] == "C:/tmp/imp.sldprt"
        assert not r["errors"]


class TestFaultEnumeration:
    def test_corrupt_brep_enumerated_and_decoded(self, patched):
        # 1 solid carrying two topology faults the kernel won't make on a seat.
        body = _FakeBody([21, 3])  # swFaceSelfIntersecting, swBodyInsideOut
        patched(_FakeDoc(solids=[body]))
        r = run()
        assert r["ok"] is True
        assert r["clean"] is False
        assert r["total_fault_count"] == 2
        assert r["faults_by_code"] == {
            "swFaceSelfIntersecting": 1, "swBodyInsideOut": 1,
        }
        assert r["per_body"][0]["body_kind"] == "solid"
        assert r["per_body"][0]["fault_count"] == 2
        assert set(r["per_body"][0]["codes"]) == {"swFaceSelfIntersecting", "swBodyInsideOut"}

    def test_faults_aggregated_across_bodies(self, patched):
        patched(_FakeDoc(solids=[_FakeBody([3]), _FakeBody([3, 21])]))
        r = run()
        assert r["total_fault_count"] == 3
        assert r["faults_by_code"] == {"swBodyInsideOut": 2, "swFaceSelfIntersecting": 1}
        assert r["clean"] is False


class TestSurfaceBodies:
    def test_surface_body_flags_unstitched(self, patched):
        # A valid solid + a stray surface body = not-clean (unstitched-import flag).
        patched(_FakeDoc(solids=[_FakeBody()], sheets=[_FakeBody()]))
        r = run()
        assert r["ok"] is True
        assert r["solid_body_count"] == 1
        assert r["surface_body_count"] == 1
        assert r["total_fault_count"] == 0
        assert r["clean"] is False  # surface body present
        kinds = [e["body_kind"] for e in r["per_body"]]
        assert kinds == ["solid", "surface"]

    def test_no_solid_is_not_clean(self, patched):
        patched(_FakeDoc(solids=[], sheets=[_FakeBody()]))
        r = run()
        assert r["solid_body_count"] == 0
        assert r["clean"] is False


class TestReadOnlyContract:
    def test_import_diagnosis_called_all_flags_false(self, patched):
        """The pure-read contract: ImportDiagnosis must NEVER be called with a
        repair flag True (those mutate). Pin the exact args."""
        doc = _FakeDoc(solids=[_FakeBody()])
        patched(doc)
        run()
        assert doc.import_diag_calls == [(False, False, False, 0)]
        assert all(call[:3] == (False, False, False) for call in doc.import_diag_calls)


class TestFailSoft:
    def test_import_diagnosis_raises_is_soft(self, patched):
        patched(_FakeDoc(solids=[_FakeBody()], import_raises=True))
        r = run()
        # body read is load-bearing; ImportDiagnosis failure must not fail the call
        assert r["ok"] is True
        assert r["import_diagnosis_status"] is None
        assert any("ImportDiagnosis" in e for e in r["errors"])
        assert r["clean"] is True  # bodies still clean

    def test_check3_raises_is_soft(self, patched):
        patched(_FakeDoc(solids=[_FakeBody(check3_raises=True)]))
        r = run()
        assert r["ok"] is True  # body breakdown still read
        assert r["total_fault_count"] is None  # check incomplete
        assert r["clean"] is None  # cannot assert clean without a complete check
        assert any("Check3" in e for e in r["errors"])


class TestValidation:
    def test_no_active_doc(self, patched):
        patched(None)
        r = run()
        assert r["ok"] is False
        assert r["error"] == "no_active_doc"

    def test_non_part_rejected(self, patched):
        patched(_FakeDoc(solids=[_FakeBody()], doc_type=2))  # assembly
        r = run()
        assert r["ok"] is False
        assert "part" in r["error"]


class TestDecode:
    def test_known_codes(self):
        assert _fault_code_name(1) == "swBodyCorrupt"
        assert _fault_code_name(36) == "swEdgeTouchEdge"

    def test_unknown_code(self):
        assert _fault_code_name(999) == "unknown_code_999"

    def test_non_numeric_code(self):
        assert _fault_code_name(None).startswith("unknown_code_")
