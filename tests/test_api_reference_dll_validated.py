"""Validate docs/api_reference.json structural integrity + coverage.

Offline-only test (no SOLIDWORKS install required). Asserts:

1. api_reference.json loads with the expected top-level keys.
2. Method count is at or above the pinned minimum (regression guard).
3. docs/api_reference.md was regenerated and is non-trivial.

DLL-arg-count validation lives in tools/verify_api_reference_against_dll.ps1
(requires .NET reflection over the interop DLLs — not portable to pytest).
This test complements it with structural and coverage assertions.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
REF_JSON = REPO_ROOT / "docs" / "api_reference.json"
REF_MD = REPO_ROOT / "docs" / "api_reference.md"

# Post-W58-reconciliation regen yield: 208 methods from 211 input entries
# (3 known absent: InsertSplitBody, GetCustomInfoValue2, SendKeys).
# Pinned as a regression guard — any drop indicates pipeline regression
# or CHM-input shrinkage.
MIN_METHOD_COUNT = 208


@pytest.fixture(scope="module")
def ref_data() -> dict:
    if not REF_JSON.exists():
        pytest.skip(
            f"{REF_JSON.name} not generated yet (run chm_extract.py batch first)"
        )
    return json.loads(REF_JSON.read_text(encoding="utf-8"))


def test_json_top_level_keys(ref_data: dict) -> None:
    assert "methods" in ref_data
    assert "enums" in ref_data


def test_method_count_floor(ref_data: dict) -> None:
    count = len(ref_data["methods"])
    assert count >= MIN_METHOD_COUNT, (
        f"method count {count} < pinned floor {MIN_METHOD_COUNT}; "
        "CHM extraction may have regressed"
    )


def test_markdown_exists_and_nonempty() -> None:
    if not REF_MD.exists():
        pytest.skip(f"{REF_MD.name} not generated yet")
    content = REF_MD.read_text(encoding="utf-8")
    assert len(content) > 100, "api_reference.md is suspiciously short"
