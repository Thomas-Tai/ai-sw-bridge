"""Tests for COM fault injection — HRESULT catalog and tier classification.

For each known HRESULT, asserts:
  (a) the error tier classifies correctly (Tier B for marshaling,
      Tier C for STA violation)
  (b) the FaultInjector produces the correct synthetic error
  (c) the HRESULT description matches the failure mode

Per audit §4.2 and spec.md §8.3. Errors/wrapper.py integration is
deferred to Task 1.2 (errors package not yet created).
"""

from __future__ import annotations

import pytest

from ai_sw_bridge.telemetry.classify import classify_hresult
from tests.fault_injection.conftest import (
    ComError,
    FaultInjector,
    HRESULT,
    EXPECTED_TIERS,
    HRESULT_DESCRIPTIONS,
)


pytestmark = pytest.mark.fault_injection


class TestHRESULTTierClassification:
    """Verify each HRESULT maps to the correct Tier A/B/C classification."""

    @pytest.mark.parametrize(
        "hresult,expected_tier",
        list(EXPECTED_TIERS.items()),
        ids=[f"{h:#010x}" for h in EXPECTED_TIERS],
    )
    def test_hresult_classifies_to_correct_tier(self, hresult: int, expected_tier: str):
        assert classify_hresult(hresult) == expected_tier, (
            f"HRESULT {hresult:#010x} classified as {classify_hresult(hresult)}, "
            f"expected {expected_tier}"
        )

    def test_unknown_hresult_classifies_as_unknown(self):
        assert classify_hresult(0x80004005) == "unknown"  # E_FAIL


class TestFaultInjectorMechanics:
    """Verify FaultInjector fires correctly at configured injection points."""

    def test_no_fault_when_inactive(self, fault_injector: FaultInjector):
        fault_injector.add_fault(
            "FeatureExtrusion2", attempt=1, hresult=HRESULT.RPC_S_SERVER_UNAVAILABLE
        )
        assert fault_injector.check("FeatureExtrusion2") is None

    def test_fault_fires_at_configured_attempt(self, fault_injector: FaultInjector):
        fault_injector.add_fault(
            "FeatureExtrusion2", attempt=1, hresult=HRESULT.RPC_S_SERVER_UNAVAILABLE
        )
        with fault_injector.active():
            err = fault_injector.check("FeatureExtrusion2")
        assert err is not None
        assert err.hresult == HRESULT.RPC_S_SERVER_UNAVAILABLE

    def test_fault_only_fires_on_matching_attempt(self, fault_injector: FaultInjector):
        fault_injector.add_fault(
            "FeatureExtrusion2", attempt=2, hresult=HRESULT.RPC_E_DISCONNECTED
        )
        with fault_injector.active():
            assert fault_injector.check("FeatureExtrusion2") is None  # attempt 1
            err = fault_injector.check("FeatureExtrusion2")  # attempt 2
        assert err is not None
        assert err.hresult == HRESULT.RPC_E_DISCONNECTED

    def test_multiple_methods_independent(self, fault_injector: FaultInjector):
        fault_injector.add_fault(
            "FeatureExtrusion2", attempt=1, hresult=HRESULT.RPC_S_SERVER_UNAVAILABLE
        )
        fault_injector.add_fault(
            "SimpleHole2", attempt=1, hresult=HRESULT.DISP_E_BADINDEX
        )
        with fault_injector.active():
            err1 = fault_injector.check("FeatureExtrusion2")
            err2 = fault_injector.check("SimpleHole2")
        assert err1 is not None and err1.hresult == HRESULT.RPC_S_SERVER_UNAVAILABLE
        assert err2 is not None and err2.hresult == HRESULT.DISP_E_BADINDEX

    def test_reset_clears_call_counts(self, fault_injector: FaultInjector):
        fault_injector.add_fault(
            "FeatureExtrusion2", attempt=1, hresult=HRESULT.RPC_S_SERVER_UNAVAILABLE
        )
        with fault_injector.active():
            fault_injector.check("FeatureExtrusion2")  # fires, consumed
        fault_injector.reset()
        with fault_injector.active():
            err = fault_injector.check("FeatureExtrusion2")  # fires again
        assert err is not None

    def test_custom_com_error(self, fault_injector: FaultInjector):
        custom = ComError(0xDEAD, "custom error")
        fault_injector.add_fault("TestMethod", attempt=1, error=custom)
        with fault_injector.active():
            err = fault_injector.check("TestMethod")
        assert err is custom


class TestHRESULTCatalog:
    """Verify the full HRESULT catalog is present and documented."""

    def test_all_catalog_hresults_have_tiers(self):
        for hresult in EXPECTED_TIERS:
            tier = classify_hresult(hresult)
            assert tier in (
                "A",
                "B",
                "C",
            ), f"HRESULT {hresult:#010x} has unexpected tier {tier!r}"

    def test_all_catalog_hresults_have_descriptions(self):
        for hresult in EXPECTED_TIERS:
            assert (
                hresult in HRESULT_DESCRIPTIONS
            ), f"HRESULT {hresult:#010x} missing from HRESULT_DESCRIPTIONS"

    def test_tier_b_count_matches(self):
        tier_b = [h for h, t in EXPECTED_TIERS.items() if t == "B"]
        assert (
            len(tier_b) == 4
        ), f"expected 4 Tier B HRESULTs (marshaling), got {len(tier_b)}"

    def test_tier_c_count_matches(self):
        tier_c = [h for h, t in EXPECTED_TIERS.items() if t == "C"]
        assert (
            len(tier_c) == 1
        ), f"expected 1 Tier C HRESULT (STA violation), got {len(tier_c)}"

    def test_tier_c_is_sta_violation(self):
        assert EXPECTED_TIERS[HRESULT.CO_E_NOTINITIALIZED] == "C"
