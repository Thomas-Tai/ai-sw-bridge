# tests/test_preflight_examples.py
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_sw_bridge.spec.preflight import preflight

ROOT = Path(__file__).resolve().parents[1]
SPECS = sorted(
    p
    for p in ROOT.glob("examples/*/*.json")
    if p.name in ("spec.json", "spec_parametric.json")
)


@pytest.mark.parametrize("spec_path", SPECS, ids=lambda p: p.parent.name + "/" + p.name)
def test_example_preflights_without_warn_or_error(spec_path: Path):
    spec = json.loads(spec_path.read_text())
    bad = [f for f in preflight(spec) if f.severity in ("warning", "error")]
    assert bad == [], (
        f"{spec_path} produced non-info pre-flight findings (false positives): "
        + "; ".join(str(f) for f in bad)
    )


def test_corpus_is_non_empty():
    assert SPECS, "expected example specs under examples/*/"
