"""Tests for telemetry.counters — Counter primitive and COUNTERS registry."""

from __future__ import annotations

from ai_sw_bridge.telemetry.counters import Counter, COUNTERS
from ai_sw_bridge.telemetry.store import TelemetryStore


def test_counter_inc_records_to_store(tmp_path):
    db = tmp_path / "test.sqlite"
    store = TelemetryStore(db_path=db)
    c = Counter("test_counter", labels=("mode",), store=store)
    c.inc(mode="no_dim")
    rows = store.query("test_counter")
    assert len(rows) == 1
    assert rows[0]["value"] == 1.0
    assert rows[0]["labels"]["mode"] == "no_dim"
    store.close()


def test_counter_inc_with_value(tmp_path):
    db = tmp_path / "test.sqlite"
    store = TelemetryStore(db_path=db)
    c = Counter("test_counter", labels=("mode",), store=store)
    c.inc(value=5, mode="no_dim")
    rows = store.query("test_counter")
    assert rows[0]["value"] == 5.0
    store.close()


def test_counter_wrong_labels_raises(tmp_path):
    db = tmp_path / "test.sqlite"
    store = TelemetryStore(db_path=db)
    c = Counter("test_counter", labels=("mode",), store=store)
    try:
        c.inc(wrong="value")
        assert False, "should have raised TypeError"
    except TypeError:
        pass
    store.close()


def test_counter_no_store_is_noop():
    c = Counter("test_counter", labels=("mode",))
    c.inc(mode="no_dim")  # should not raise


def test_counter_bind(tmp_path):
    db = tmp_path / "test.sqlite"
    store = TelemetryStore(db_path=db)
    c = Counter("test_counter", labels=("mode",))
    bound = c.bind(store)
    bound.inc(mode="no_dim")
    rows = store.query("test_counter")
    assert len(rows) == 1
    store.close()


def test_all_7_mandatory_counters_registered():
    """Audit §1.2 requires these counters. rag_query_seconds is a histogram."""
    expected = {
        "builds_total",
        "com_errors_total",
        "hint_emissions_total",
        "auto_retry_outcomes_total",
        "checkpoint_writes_total",
        "feature_flag_state",
        "com_disconnects_total",
    }
    assert expected.issubset(
        set(COUNTERS.keys())
    ), f"missing counters: {expected - set(COUNTERS.keys())}"


def test_counter_label_keys_match_spec():
    """Verify label keys for each counter match audit §1.2 table."""
    assert COUNTERS["builds_total"]._label_keys == ("mode", "outcome")
    assert COUNTERS["com_errors_total"]._label_keys == ("iface_method", "hresult")
    assert COUNTERS["hint_emissions_total"]._label_keys == ("hint_key", "iface_method")
    assert COUNTERS["auto_retry_outcomes_total"]._label_keys == ("attempt", "outcome")
    assert COUNTERS["checkpoint_writes_total"]._label_keys == ("outcome",)
    assert COUNTERS["feature_flag_state"]._label_keys == ("flag", "state")
    assert COUNTERS["com_disconnects_total"]._label_keys == ("hresult",)
