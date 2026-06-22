"""Offline unit tests for the W77 tolerance stack-up analyzer.

The seat PAE (spikes/v0_2x/spike_stackup_pae.py) proves the live COM path; these
tests pin the ORCHESTRATION logic — input validation, consecutive-pair
traversal, gap accumulation, the touching→0 mapping, the unmeasurable-pair
fail-closed path, and the endpoint collinearity sanity check — with the
underlying ``read_clearance`` primitive mocked, so no SOLIDWORKS seat is needed.
"""
from __future__ import annotations

from unittest.mock import patch

import ai_sw_bridge.observe_clearance as C


def _clr(dist_mm=None, *, touching=False, errors=None):
    """A read_clearance-shaped result."""
    return {
        "min_distance_mm": dist_mm,
        "components": ["a", "b"],
        "touching": touching,
        "errors": errors or [],
    }


def _run(seq, names, **kwargs):
    """Drive analyze_stackup with read_clearance returning ``seq`` in order."""
    with patch.object(C, "wrapper_module", return_value=object()), \
         patch.object(C, "read_clearance", side_effect=seq) as rc:
        res = C.analyze_stackup(object(), names, **kwargs)
    return res, rc


# ── Input validation ────────────────────────────────────────────────────────

def test_rejects_non_list():
    res = C.analyze_stackup(object(), "base-1")
    assert res["ok"] is False and "list" in res["error"]


def test_rejects_single_component():
    res = C.analyze_stackup(object(), ["only-1"])
    assert res["ok"] is False and ">= 2" in res["error"]


def test_rejects_empty_name():
    res = C.analyze_stackup(object(), ["base-1", "  "])
    assert res["ok"] is False and "non-empty" in res["error"]


# ── Core traversal + accumulation ───────────────────────────────────────────

def test_two_component_single_gap():
    res, rc = _run([_clr(2.0)], ["base-1", "top-1"], check_endpoints=True)
    assert res["ok"] is True
    assert res["accumulated_gap_mm"] == 2.0
    assert res["measured_pairs"] == 1
    assert res["pairs"][0]["components"] == ["base-1", "top-1"]
    # 2 components -> no endpoint check (needs >= 3); read_clearance called once.
    assert rc.call_count == 1
    assert res["endpoint_span_mm"] is None


def test_three_component_chain_accumulates():
    # base|2mm|spacer|3mm|top ; direct base<->top spans the 20mm spacer = 25mm.
    seq = [_clr(2.0), _clr(3.0), _clr(25.0)]
    res, rc = _run(seq, ["base-1", "spacer-1", "top-1"], check_endpoints=True)
    assert res["ok"] is True
    assert [p["gap_mm"] for p in res["pairs"]] == [2.0, 3.0]
    assert res["accumulated_gap_mm"] == 5.0
    assert res["measured_pairs"] == 2
    # endpoint span is the direct first<->last (3rd read_clearance call).
    assert rc.call_count == 3
    assert res["endpoint_span_mm"] == 25.0
    assert res["intervening_span_mm"] == 20.0  # 25 - 5 = the spacer body span
    assert res["linear_consistent"] is True
    assert res["warnings"] == []


def test_touching_pair_counts_as_zero_gap():
    seq = [_clr(touching=True), _clr(3.0), _clr(3.0)]
    res, _ = _run(seq, ["base-1", "spacer-1", "top-1"], check_endpoints=True)
    assert res["ok"] is True
    assert res["pairs"][0]["gap_mm"] == 0.0
    assert res["pairs"][0]["touching"] is True
    assert res["accumulated_gap_mm"] == 3.0


def test_no_endpoints_flag_skips_direct_measure():
    seq = [_clr(2.0), _clr(3.0)]
    res, rc = _run(seq, ["base-1", "spacer-1", "top-1"], check_endpoints=False)
    assert res["ok"] is True
    assert res["accumulated_gap_mm"] == 5.0
    assert rc.call_count == 2  # no endpoint call
    assert res["endpoint_span_mm"] is None
    assert res["linear_consistent"] is None


# ── Fail-closed + sanity flags ──────────────────────────────────────────────

def test_unmeasurable_pair_fails_closed():
    seq = [_clr(2.0), _clr(errors=["component not found: 'spacer-1'"])]
    res, _ = _run(seq, ["base-1", "spacer-1", "top-1"], check_endpoints=False)
    assert res["ok"] is False
    assert res["accumulation_complete"] is False
    assert "unmeasurable pair" in res["error"]
    # The one measurable pair is still summed for telemetry.
    assert res["accumulated_gap_mm"] == 2.0
    assert res["measured_pairs"] == 1


def test_endpoint_shorter_than_gaps_flags_misalignment():
    # A collinear stack can't have its end-to-end span be < the sum of gaps.
    seq = [_clr(2.0), _clr(3.0), _clr(4.0)]  # endpoint 4mm < accumulated 5mm
    res, _ = _run(seq, ["base-1", "spacer-1", "top-1"], check_endpoints=True)
    assert res["ok"] is True  # gaps still measured; consistency is a warning
    assert res["linear_consistent"] is False
    assert any("non-collinear" in w or "misaligned" in w for w in res["warnings"])


def test_unmeasurable_endpoint_leaves_span_none():
    seq = [_clr(2.0), _clr(3.0), _clr(errors=["measure failed"])]
    res, _ = _run(seq, ["base-1", "spacer-1", "top-1"], check_endpoints=True)
    assert res["ok"] is True
    assert res["endpoint_span_mm"] is None
    assert res["linear_consistent"] is None
    assert res["intervening_span_mm"] is None


# ── sw_analyze_stackup doc-type guard ───────────────────────────────────────

def test_sw_wrapper_rejects_non_assembly():
    class _Doc:
        def GetType(self):
            return 1  # swDocPART

    res = C._sw_analyze_stackup_impl(_Doc(), ["a-1", "b-1"])
    assert res["ok"] is False and "assembly" in res["error"]


def test_sw_wrapper_passes_assembly_through():
    class _Doc:
        def GetType(self):
            return C.SW_DOC_ASSEMBLY

    with patch.object(C, "wrapper_module", return_value=object()), \
         patch.object(C, "read_clearance", side_effect=[_clr(2.0)]):
        res = C._sw_analyze_stackup_impl(_Doc(), ["a-1", "b-1"])
    assert res["ok"] is True and res["accumulated_gap_mm"] == 2.0
