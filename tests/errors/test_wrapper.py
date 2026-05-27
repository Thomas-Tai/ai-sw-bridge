"""Tests for the com_error_boundary wrapper (spec.md §3.3)."""

from __future__ import annotations

import io
import json
import sys
from contextlib import contextmanager

import pytest

from ai_sw_bridge.errors.build_error import BuildError
from ai_sw_bridge.errors.hints import HINT_CATALOG
from ai_sw_bridge.errors.wrapper import (
    com_error_boundary,
    emit_envelope_to_stderr,
)
from ai_sw_bridge.telemetry.counters import COUNTERS
from ai_sw_bridge.telemetry.store import TelemetryStore
from ai_sw_bridge.telemetry.trace import clear_trace_id, new_trace_id, set_trace_id

# The synthetic ComError from fault_injection/conftest.py is a plain
# dataclass (not an Exception subclass). For the boundary to catch it
# in tests, we subclass both so it's raisable AND isinstance-usable.
from tests.fault_injection.conftest import ComError as _ComErrorDataclass
from tests.fault_injection.conftest import HRESULT


class SyntheticComError(_ComErrorDataclass, Exception):  # type: ignore[misc]
    """Raisable version of the synthetic ComError for unit tests."""

    def __init__(self, hresult: int, strerror: str, details: tuple = ("", "", "")) -> None:
        _ComErrorDataclass.__init__(self, hresult, strerror, details)
        Exception.__init__(self, strerror)


ComError = SyntheticComError


def _bind_store(tmp_path=None) -> TelemetryStore:
    """Bind a fresh in-memory store to the com_errors_total counter.

    Pass ``tmp_path`` (pytest fixture) to get a per-test SQLite file;
    otherwise the store uses the default user-local path, which
    accumulates rows across runs and breaks exact-count assertions.
    """
    from pathlib import Path

    if tmp_path is None:
        import tempfile

        tmp_path = Path(tempfile.mkdtemp(prefix="e12-test-"))
    db_path = Path(tmp_path) / "metrics.sqlite"
    store = TelemetryStore(db_path=db_path)
    COUNTERS["com_errors_total"]._store = store
    COUNTERS["hint_emissions_total"]._store = store
    return store


@pytest.fixture(autouse=True)
def _isolate_counters(tmp_path):
    """Each test gets a fresh store so counter assertions are isolated."""
    store = _bind_store(tmp_path)
    yield store
    COUNTERS["com_errors_total"]._store = None
    COUNTERS["hint_emissions_total"]._store = None


def test_synthetic_com_error_produces_build_error_envelope() -> None:
    with pytest.raises(BuildError) as excinfo:
        with com_error_boundary(
            feature_name="Extrude_Plate",
            json_path="features[3]",
            iface_method="IFeatureManager.FeatureExtrusion2",
        ):
            raise ComError(
                hresult=HRESULT.RPC_S_SERVER_UNAVAILABLE,
                strerror="server unavailable",
            )
    err = excinfo.value
    envelope = err.to_envelope()["error"]
    assert envelope["feature"] == "Extrude_Plate"
    assert envelope["json_path"] == "features[3]"
    assert envelope["hresult"] == "0x800706BA"
    assert envelope["tier"] == "B"
    # trace_id unset -> no prefix
    assert envelope["diagnosis"]  # non-empty


@pytest.mark.parametrize(
    "hresult,expected_tier",
    [
        (HRESULT.RPC_S_SERVER_UNAVAILABLE, "B"),
        (HRESULT.RPC_E_DISCONNECTED, "B"),
        (HRESULT.DISP_E_MEMBERNOTFOUND, "B"),
        (HRESULT.DISP_E_BADINDEX, "B"),
        (HRESULT.CO_E_NOTINITIALIZED, "C"),
    ],
)
def test_tier_classification_correct_for_all_known_hresults(
    hresult: int, expected_tier: str
) -> None:
    with pytest.raises(BuildError) as excinfo:
        with com_error_boundary(
            feature_name="f",
            json_path="p",
            iface_method="m",
        ):
            raise ComError(hresult=hresult, strerror="injected")
    assert excinfo.value.tier == expected_tier


def test_trace_id_propagates_into_diagnosis() -> None:
    tid = new_trace_id()
    try:
        with pytest.raises(BuildError) as excinfo:
            with com_error_boundary(
                feature_name="f",
                json_path="p",
                iface_method="m",
            ):
                raise ComError(
                    hresult=HRESULT.RPC_S_SERVER_UNAVAILABLE,
                    strerror="x",
                )
        assert tid in excinfo.value.diagnosis
    finally:
        clear_trace_id()


def test_counter_emission_on_com_error() -> None:
    with pytest.raises(BuildError):
        with com_error_boundary(
            feature_name="f",
            json_path="p",
            iface_method="IFeatureManager.FeatureExtrusion2",
        ):
            raise ComError(
                hresult=HRESULT.RPC_S_SERVER_UNAVAILABLE,
                strerror="x",
            )
    rows = COUNTERS["com_errors_total"]._store.query(
        "com_errors_total",
        labels={"iface_method": "IFeatureManager.FeatureExtrusion2"},
    )
    assert len(rows) >= 1
    assert rows[0]["labels"]["hresult"] == "0x800706BA"


def test_hint_resolution_attaches_hint_key() -> None:
    # 0x80004005 on FeatureExtrusion2 -> face_no_longer_exists
    with pytest.raises(BuildError) as excinfo:
        with com_error_boundary(
            feature_name="f",
            json_path="p",
            iface_method="IFeatureManager.FeatureExtrusion2",
        ):
            raise ComError(hresult=0x80004005, strerror="E_FAIL")
    assert excinfo.value.hint_key == "face_no_longer_exists"
    assert "face" in excinfo.value.next_action_hint.lower()


def test_unknown_hresult_uses_default_hint_and_none_key() -> None:
    with pytest.raises(BuildError) as excinfo:
        with com_error_boundary(
            feature_name="f",
            json_path="p",
            iface_method="IFeatureManager.FeatureExtrusion2",
        ):
            raise ComError(hresult=0xDEADBEEF, strerror="weird")
    # hint_key is None (no catalog match)
    assert excinfo.value.hint_key is None
    # diagnosis is still the default hint's summary
    assert "uncatalogued" in excinfo.value.diagnosis.lower()


def test_non_com_error_propagates_untouched() -> None:
    class _CustomError(RuntimeError):
        pass

    with pytest.raises(_CustomError):
        with com_error_boundary("f", "p", iface_method="m"):
            raise _CustomError("not a COM error")


def test_attribute_error_treated_as_cross_thread() -> None:
    with pytest.raises(BuildError) as excinfo:
        with com_error_boundary("f", "p", iface_method="m"):
            raise AttributeError("'NoneType' object has no attribute 'X'")
    err = excinfo.value
    assert err.hresult == "0xCROSS_THREAD"
    assert err.tier == "C"
    assert "STA" in err.diagnosis


def test_emit_envelope_writes_traceback_to_stderr(capsys) -> None:
    err = BuildError(
        feature="f",
        json_path="p",
        hresult="0x800706BA",
        iface_method="m",
        diagnosis="d",
        next_action_hint="h",
        traceback="Traceback (most recent call last):\n  boom",
        tier="B",
    )
    emit_envelope_to_stderr(err)
    captured = capsys.readouterr()
    # stderr carries the human-readable traceback (not JSON)
    assert "Traceback" in captured.err
    assert "boom" in captured.err
    # stdout remains untouched — JSON emission is the CLI layer's job
    assert captured.out == ""


def test_circuit_breaker_still_trips_after_n_consecutive_errors() -> None:
    """Smoke test: the boundary doesn't interfere with circuit-breaker counting.

    The breaker lives in errors.circuit_breaker; this test ensures the
    wrapper increments com_errors_total so a sibling assertion layer can
    observe N consecutive failures.
    """
    store = COUNTERS["com_errors_total"]._store
    for _ in range(5):
        with pytest.raises(BuildError):
            with com_error_boundary(
                feature_name="f",
                json_path="p",
                iface_method="IFeatureManager.FeatureCut4",
            ):
                raise ComError(hresult=0x80020009, strerror="x")
    rows = store.query(
        "com_errors_total",
        labels={"iface_method": "IFeatureManager.FeatureCut4"},
    )
    assert len(rows) == 5
