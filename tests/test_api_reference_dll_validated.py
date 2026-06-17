"""Validate docs/api_reference.json structural integrity + W63 target coverage.

Offline-only test (no SOLIDWORKS install required). Asserts:

1. api_reference.json loads with the expected top-level keys.
2. Method count is at or above the pinned minimum (regression guard).
3. Every W63 target interface is represented in the methods section.
4. docs/api_reference.md was regenerated and contains the target interfaces.

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

# Baseline on master (pre-W63): 33 methods found in CHM, 2 missing.
# W63 added 101 input entries; post-regen yield = 134 methods (90 DLL
# arg-count matches + 44 COM-property accessors, 0 absent, 0 mismatch).
# Pinned to actual post-regen count as a regression guard — any drop
# below this indicates pipeline regression or CHM-input shrinkage.
MIN_METHOD_COUNT = 134

W63_TARGET_INTERFACES = frozenset({
    "ISweepFeatureData",
    "IVariableFilletFeatureData2",
    "IGearMateFeatureData",
})

W63_TARGET_METHODS = {
    "IAssemblyDoc.AddMate5",
}


@pytest.fixture(scope="module")
def ref_data() -> dict:
    if not REF_JSON.exists():
        pytest.skip(f"{REF_JSON.name} not generated yet (run chm_extract.py batch first)")
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


def test_w63_target_interfaces_present(ref_data: dict) -> None:
    ifaces_found: set[str] = set()
    for fq in ref_data["methods"]:
        iface = fq.split(".")[0]
        ifaces_found.add(iface)
    for target in W63_TARGET_INTERFACES:
        assert target in ifaces_found, (
            f"W63 target interface {target} absent from api_reference.json methods"
        )


def test_w63_target_methods_present(ref_data: dict) -> None:
    for fq in W63_TARGET_METHODS:
        assert fq in ref_data["methods"], (
            f"W63 target method {fq} absent from api_reference.json"
        )


def test_markdown_exists_and_nonempty() -> None:
    if not REF_MD.exists():
        pytest.skip(f"{REF_MD.name} not generated yet")
    content = REF_MD.read_text(encoding="utf-8")
    assert len(content) > 100, "api_reference.md is suspiciously short"


def test_markdown_contains_w63_targets() -> None:
    if not REF_MD.exists():
        pytest.skip(f"{REF_MD.name} not generated yet")
    content = REF_MD.read_text(encoding="utf-8")
    for target in W63_TARGET_INTERFACES:
        assert target in content, (
            f"W63 target interface {target} absent from api_reference.md"
        )
    for fq in W63_TARGET_METHODS:
        assert fq in content, (
            f"W63 target method {fq} absent from api_reference.md"
        )
