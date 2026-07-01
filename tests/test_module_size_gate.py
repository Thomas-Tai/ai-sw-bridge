"""Guardrail-for-the-guardrail: the module-size gate's own logic."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "module_size_gate", _ROOT / "tools" / "module_size_gate.py"
)
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)


def test_new_module_over_ceiling_is_a_violation() -> None:
    scan = {"src/ai_sw_bridge/brand_new_huge.py": 900}
    baseline: dict[str, int] = {}
    violations = gate.check(scan, baseline, ceiling=800)
    assert any("brand_new_huge.py" in v for v in violations)


def test_grandfathered_file_may_not_grow() -> None:
    scan = {"src/ai_sw_bridge/spec/builder.py": 3400}
    baseline = {"src/ai_sw_bridge/spec/builder.py": 3335}
    violations = gate.check(scan, baseline, ceiling=800)
    assert any("builder.py" in v and "grew" in v for v in violations)


def test_grandfathered_file_shrinking_is_ok() -> None:
    scan = {"src/ai_sw_bridge/spec/builder.py": 3000}
    baseline = {"src/ai_sw_bridge/spec/builder.py": 3335}
    assert gate.check(scan, baseline, ceiling=800) == []


def test_new_small_module_is_ok() -> None:
    scan = {"src/ai_sw_bridge/tiny.py": 120}
    assert gate.check(scan, {}, ceiling=800) == []
