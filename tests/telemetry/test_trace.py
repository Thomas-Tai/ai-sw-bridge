"""Tests for telemetry.trace — per-build trace ID generation."""

from __future__ import annotations

import re

from ai_sw_bridge.telemetry.trace import (
    clear_trace_id,
    new_trace_id,
    set_trace_id,
    trace_id,
)


def test_new_trace_id_format():
    tid = new_trace_id()
    assert re.match(r"trace-\d{8}T\d{6}-[0-9a-f]{8}", tid), f"bad format: {tid}"


def test_new_trace_id_binds_to_thread():
    tid = new_trace_id()
    assert trace_id() == tid


def test_set_trace_id():
    set_trace_id("trace-custom")
    assert trace_id() == "trace-custom"
    clear_trace_id()


def test_clear_trace_id():
    new_trace_id()
    clear_trace_id()
    assert trace_id() is None


def test_trace_id_none_before_set():
    clear_trace_id()
    assert trace_id() is None


def test_new_trace_ids_are_unique():
    ids = {new_trace_id() for _ in range(100)}
    assert len(ids) == 100
    clear_trace_id()
