# tests/test_coverage_gate.py
from __future__ import annotations

import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "coverage_gate", _ROOT / "tools" / "coverage_gate.py"
)
cg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cg)

_FLOORS = {"src/ai_sw_bridge/spec/": 85.0}


def _cov(total: float, files: dict[str, float]) -> dict:
    return {
        "totals": {"percent_covered": total},
        "files": {p: {"summary": {"percent_covered": v}} for p, v in files.items()},
    }


def test_total_drop_beyond_tolerance_fails() -> None:
    cov = _cov(60.0, {})
    baseline = {"__total__": 64.0}
    violations = cg.evaluate(cov, baseline, tolerance=1.0, package_floors={})
    assert any("total coverage" in v for v in violations)


def test_total_within_tolerance_ok() -> None:
    cov = _cov(63.2, {})
    baseline = {"__total__": 64.0}
    assert cg.evaluate(cov, baseline, tolerance=1.0, package_floors={}) == []


def test_package_below_floor_fails() -> None:
    cov = _cov(64.0, {"src/ai_sw_bridge/spec/builder.py": 80.0})
    violations = cg.evaluate(cov, {"__total__": 64.0}, package_floors=_FLOORS)
    assert any("spec/" in v and "floor" in v for v in violations)


def test_package_meets_floor_ok() -> None:
    cov = _cov(64.0, {"src/ai_sw_bridge/spec/builder.py": 90.0})
    assert cg.evaluate(cov, {"__total__": 64.0}, package_floors=_FLOORS) == []
