"""Tests for the brep integration into builder.py (E2.6, spec.md §2.7).

Live-SW regression (the MMP ``--enable-flag brep_interrogation`` golden
snapshot at ``tests/brep/golden/mmp.json``) is deferred to a
solidworks_only marker — it requires a running SOLIDWORKS session and
is gated in CI via ``pytest -m solidworks_only``.

This file covers the COM-free slices: the flag-OFF wire format
preservation (backward-compat guarantee), the sidecar helper, and
the BuildResult.brep_manifest plumbing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ai_sw_bridge.spec.builder import BuildResult, _write_brep_sidecar


# ---------------------------------------------------------------------------
# BuildResult + to_dict
# ---------------------------------------------------------------------------


def _minimal_result(**overrides: Any) -> BuildResult:
    base = dict(
        ok=True,
        features_built=["Extrude_Plate"],
        bindings_added=[],
    )
    base.update(overrides)
    return BuildResult(**base)


def test_to_dict_omits_brep_manifest_when_none() -> None:
    """v0.11 wire-format preservation: brep_manifest field is absent
    from the CLI output when the flag is OFF (default)."""
    result = _minimal_result()
    out = result.to_dict()
    assert "brep_manifest" not in out


def test_to_dict_includes_brep_manifest_when_set() -> None:
    manifest = {
        "schema_version": 1,
        "features": [
            {
                "feature": "Extrude_Plate",
                "type": "boss_extrude_blind",
                "faces": [
                    {
                        "fingerprint": "deadbeef" * 2,
                        "role_hint": "+z_outboard",
                        "normal": [0.0, 0.0, 1.0],
                    }
                ],
            }
        ],
    }
    result = _minimal_result(brep_manifest=manifest)
    out = result.to_dict()
    assert out["brep_manifest"] == manifest


def test_to_dict_brep_manifest_none_explicit_is_omitted() -> None:
    """Explicitly passing brep_manifest=None is equivalent to the default."""
    result = _minimal_result(brep_manifest=None)
    assert "brep_manifest" not in result.to_dict()


# ---------------------------------------------------------------------------
# _write_brep_sidecar helper
# ---------------------------------------------------------------------------


class _FakeManifest:
    """Stand-in for brep.manifest.Manifest with a to_dict() method."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def to_dict(self) -> dict:
        return self._payload


def test_write_brep_sidecar_next_to_save_as(tmp_path: Path) -> None:
    save_as = str(tmp_path / "out" / "part.sldprt")
    manifest = _FakeManifest({"schema_version": 1, "features": []})
    path = _write_brep_sidecar(manifest, save_as=save_as)
    assert path == str(tmp_path / "out" / "build_brep.json")
    assert Path(path).exists()
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    assert data == {"schema_version": 1, "features": []}


def test_write_brep_sidecar_falls_back_to_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    manifest = _FakeManifest({"schema_version": 1, "features": []})
    path = _write_brep_sidecar(manifest, save_as=None)
    assert path == str(tmp_path / "build_brep.json")
    assert Path(path).exists()


def test_write_brep_sidecar_returns_none_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the parent dir can't be created, the helper returns None
    instead of raising (build must not fail on sidecar error)."""
    # Point save_as at a path whose parent is a regular file, not a dir.
    blocker = tmp_path / "blocker"
    blocker.write_text("not a dir", encoding="utf-8")
    save_as = str(blocker / "part.sldprt")
    manifest = _FakeManifest({"schema_version": 1, "features": []})
    path = _write_brep_sidecar(manifest, save_as=save_as)
    assert path is None


# ---------------------------------------------------------------------------
# Flag-OFF preservation (no live SW needed — import-level check)
# ---------------------------------------------------------------------------


def test_builder_module_import_does_not_load_brep() -> None:
    """Flag-OFF builds must not pay the import cost of the brep package.

    The brep modules are imported lazily inside build() only when the
    flag is ON. Importing the builder module alone should leave them
    unloaded.
    """
    import sys

    # Drop any prior brep imports so we can re-observe the load set.
    for name in list(sys.modules):
        if name.startswith("ai_sw_bridge.brep"):
            del sys.modules[name]

    # Re-import the builder (which may already be loaded; this is a
    # no-op if cached). The lazy imports inside build() don't fire on
    # module import.
    import importlib

    from ai_sw_bridge.spec import builder

    importlib.reload(builder)

    brep_modules = [n for n in sys.modules if n.startswith("ai_sw_bridge.brep")]
    assert brep_modules == [], (
        f"builder.py import pulled in brep modules: {brep_modules}"
    )
