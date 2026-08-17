"""Regression guard: demo renderers must not bake a phantom `ai-sw-export` CLI
into their burned-in captions.

`check_launch_kit.py` only scans `site/` + `launch-kit/`, so it cannot see the
`tools/demo_render_*.py` sources -- which is exactly how the phantom
`ai-sw-export` lower-third survived in `demo_export.gif` (spec
2026-08-14-index-enhancement-design §13-F2). The real export capability is the
spec `export:` block (STEP/STL/3MF) plus the one real DXF CLI
`ai-sw-export-dxf-flat`; no bare `ai-sw-export` console script exists
(`pyproject.toml`). `honesty_gate.py`'s banned-token check now scans
`tools/demo_*.py` as one of its surfaces, so this test asserts cleanliness by
running the real gate over the real repo root -- the single source for
"phantom export CLI" detection.
"""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import honesty_gate as hg  # noqa: E402


def _demo_sources() -> list[pathlib.Path]:
    return sorted((ROOT / "tools").glob("demo_*.py"))


def test_demo_sources_exist_to_scan():
    assert _demo_sources(), "expected tools/demo_*.py renderers to scan"


def test_demo_captions_name_no_phantom_export_cli():
    violations = hg.scan(ROOT)
    offenders = {
        surface: detail
        for surface, kind, detail in violations
        if kind == hg.KIND_BANNED_TOKEN and surface.startswith("tools/demo_")
    }
    assert not offenders, f"phantom `ai-sw-export` CLI in demo sources: {offenders}"
