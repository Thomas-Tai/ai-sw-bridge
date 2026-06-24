"""Tests for assembly manifest storage (Wave-9 Slice 2; L4 persistence W14).

Round-trip tests for ComponentInstance, MateRecord, and the schema-v2
AssemblyManifest (verbatim spec + runtime overlay). No SOLIDWORKS required.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_sw_bridge.assembly.storage import (
    AssemblyManifest,
    ComponentInstance,
    MateRecord,
    sha256_of_file,
)


# ---- ComponentInstance -----------------------------------------------------


class TestComponentInstance:
    def test_round_trip(self) -> None:
        ci = ComponentInstance(
            id="housing",
            sw_name="housing-1",
            part_path="/tmp/housing.sldprt",
            transform={"xyz_mm": [0, 0, 0], "rpy_deg": [0, 0, 90]},
        )
        ci2 = ComponentInstance.from_dict(ci.to_dict())
        assert ci2 == ci

    def test_provenance_round_trip(self) -> None:
        ci = ComponentInstance(
            id="shaft",
            sw_name="shaft-1",
            part_path="/tmp/shaft.sldprt",
            part_spec_path="/specs/shaft.aisw.json",
            part_spec_sha256="abc123",
        )
        d = ci.to_dict()
        assert d["part_spec_path"] == "/specs/shaft.aisw.json"
        assert d["part_spec_sha256"] == "abc123"
        assert ComponentInstance.from_dict(d) == ci

    def test_provenance_omitted_when_absent(self) -> None:
        ci = ComponentInstance(id="x", sw_name="x-1", part_path="/p.sldprt")
        d = ci.to_dict()
        assert "part_spec_path" not in d
        assert "part_spec_sha256" not in d

    def test_frozen(self) -> None:
        ci = ComponentInstance(id="x", sw_name="x-1", part_path="/p.sldprt")
        with pytest.raises(AttributeError):
            ci.id = "y"  # type: ignore[misc]


# ---- MateRecord (legacy value object, still exported) ----------------------


class TestMateRecord:
    def test_round_trip_distance(self) -> None:
        mr = MateRecord(
            type="distance",
            alignment="aligned",
            a={"component": "a", "face_ref": {"normal": [1, 0, 0]}},
            b={"component": "b", "face_ref": {"normal": [-1, 0, 0]}},
            value=5.0,
        )
        mr2 = MateRecord.from_dict(mr.to_dict())
        assert mr2.value == 5.0
        assert mr2.a["component"] == "a"

    def test_width_round_trip(self) -> None:
        mr = MateRecord(
            type="width",
            alignment=None,
            width_faces=[
                {"component": "a", "face_ref": {}},
                {"component": "a", "face_ref": {}},
            ],
            tab_faces=[
                {"component": "b", "face_ref": {}},
                {"component": "b", "face_ref": {}},
            ],
        )
        d = mr.to_dict()
        assert "a" not in d and "width_faces" in d
        assert MateRecord.from_dict(d).tab_faces is not None


# ---- sha256 helper ---------------------------------------------------------


class TestSha256:
    def test_hash_of_file(self, tmp_path: Path) -> None:
        f = tmp_path / "spec.json"
        f.write_text('{"a": 1}', encoding="utf-8")
        h = sha256_of_file(f)
        assert isinstance(h, str) and len(h) == 64

    def test_none_path(self) -> None:
        assert sha256_of_file(None) is None

    def test_missing_file(self, tmp_path: Path) -> None:
        assert sha256_of_file(tmp_path / "nope.json") is None


# ---- AssemblyManifest v2 ---------------------------------------------------


def _sample_spec() -> dict:
    """A realistic verbatim authoring spec exercising several mate shapes."""
    return {
        "kind": "assembly",
        "name": "gearbox",
        "components": [
            {
                "id": "housing",
                "part": "parts/housing.sldprt",
                "transform": {"xyz_mm": [0, 0, 0]},
            },
            {
                "id": "shaft",
                "part_spec": "specs/shaft.aisw.json",
                "transform": {"xyz_mm": [0, 0, 40], "rpy_deg": [0, 0, 90]},
            },
        ],
        "mates": [
            {
                "type": "distance",
                "alignment": "aligned",
                "value_mm": 5.0,
                "a": {"component": "housing", "face_ref": {"normal": [0, 0, 1]}},
                "b": {"component": "shaft", "face_ref": {"normal": [0, 0, -1]}},
            },
            {
                "type": "angle",
                "value_deg": 45.0,
                "a": {"component": "housing", "face_ref": {"normal": [1, 0, 0]}},
                "b": {"component": "shaft", "face_ref": {"normal": [0, 1, 0]}},
            },
            {
                "type": "width",
                "width_faces": [
                    {"component": "housing", "face_ref": {"normal": [1, 0, 0]}},
                    {"component": "housing", "face_ref": {"normal": [-1, 0, 0]}},
                ],
                "tab_faces": [
                    {"component": "shaft", "face_ref": {"normal": [1, 0, 0]}},
                    {"component": "shaft", "face_ref": {"normal": [-1, 0, 0]}},
                ],
            },
        ],
    }


def _sample_manifest(spec: dict | None = None) -> AssemblyManifest:
    spec = spec or _sample_spec()
    return AssemblyManifest(
        spec=spec,
        assembly_path="gearbox.sldasm",
        components=[
            ComponentInstance(
                id="housing", sw_name="housing-1", part_path="parts/housing.sldprt"
            ),
            ComponentInstance(
                id="shaft",
                sw_name="shaft-1",
                part_path="parts/shaft.sldprt",
                part_spec_path="specs/shaft.aisw.json",
                part_spec_sha256="deadbeef",
            ),
        ],
    )


class TestAssemblyManifestV2:
    def test_to_dict_shape(self) -> None:
        d = _sample_manifest().to_dict()
        assert d["schema_version"] == 2
        assert d["spec"]["name"] == "gearbox"
        assert d["runtime"]["assembly_path"] == "gearbox.sldasm"
        assert len(d["runtime"]["components"]) == 2

    def test_to_spec_returns_verbatim(self) -> None:
        spec = _sample_spec()
        m = _sample_manifest(spec)
        assert m.to_spec() == spec

    def test_to_spec_raises_on_empty(self) -> None:
        with pytest.raises(ValueError, match="no stored spec"):
            AssemblyManifest().to_spec()

    def test_round_trip_dict(self) -> None:
        m = _sample_manifest()
        m2 = AssemblyManifest.from_dict(m.to_dict())
        assert m2.spec == m.spec
        assert len(m2.components) == 2
        assert m2.component_by_id("shaft").part_spec_sha256 == "deadbeef"

    def test_round_trip_json(self) -> None:
        m = _sample_manifest()
        m2 = AssemblyManifest.from_json(m.to_json())
        assert m2.to_spec() == m.spec
        assert m2.component_by_id("housing") is not None

    def test_json_is_valid_json(self) -> None:
        parsed = json.loads(_sample_manifest().to_json())
        assert parsed["schema_version"] == 2
        assert "spec" in parsed and "runtime" in parsed


class TestLosslessRoundTrip:
    """The load-bearing L4 guarantee: spec -> manifest -> save -> load ->
    to_spec() equals the original spec exactly."""

    def test_spec_survives_save_load(self, tmp_path: Path) -> None:
        spec = _sample_spec()
        m = _sample_manifest(spec)
        path = tmp_path / "gearbox.sldasm.manifest.json"
        m.save(path)
        assert path.exists()
        reloaded = AssemblyManifest.load(path)
        assert reloaded.to_spec() == spec  # lossless, byte-for-byte structure

    def test_provenance_survives_save_load(self, tmp_path: Path) -> None:
        path = tmp_path / "m.manifest.json"
        _sample_manifest().save(path)
        reloaded = AssemblyManifest.load(path)
        shaft = reloaded.component_by_id("shaft")
        assert shaft.part_spec_sha256 == "deadbeef"
        assert shaft.part_spec_path is not None


class TestRelativePathPortability:
    """Runtime paths are stored relative to the manifest dir, so moving the
    whole bundle keeps them resolvable."""

    def test_paths_stored_relative_on_disk(self, tmp_path: Path) -> None:
        m = AssemblyManifest(
            spec=_sample_spec(),
            assembly_path=str(tmp_path / "gearbox.sldasm"),
            components=[
                ComponentInstance(
                    id="housing",
                    sw_name="housing-1",
                    part_path=str(tmp_path / "parts" / "housing.sldprt"),
                ),
            ],
        )
        path = tmp_path / "gearbox.sldasm.manifest.json"
        m.save(path)
        raw = json.loads(path.read_text(encoding="utf-8"))
        # On-disk paths are relative (no drive/anchor), spec is untouched.
        comp = raw["runtime"]["components"][0]
        assert not Path(comp["part_path"]).is_absolute()
        assert raw["runtime"]["assembly_path"] == "gearbox.sldasm"

    def test_load_resolves_relative_against_manifest_dir(self, tmp_path: Path) -> None:
        # Save in dir A, then physically move the manifest to dir B and confirm
        # load resolves paths against B (the bundle moved together).
        dir_a = tmp_path / "a"
        dir_a.mkdir()
        m = AssemblyManifest(
            spec=_sample_spec(),
            assembly_path=str(dir_a / "gearbox.sldasm"),
            components=[
                ComponentInstance(
                    id="housing",
                    sw_name="housing-1",
                    part_path=str(dir_a / "parts" / "x.sldprt"),
                )
            ],
        )
        path_a = dir_a / "m.manifest.json"
        m.save(path_a)

        dir_b = tmp_path / "b"
        dir_b.mkdir()
        path_b = dir_b / "m.manifest.json"
        path_b.write_text(path_a.read_text(encoding="utf-8"), encoding="utf-8")

        reloaded = AssemblyManifest.load(path_b)
        resolved = Path(reloaded.component_by_id("housing").part_path)
        assert resolved.is_absolute()
        # Resolves under dir_b, not the original dir_a.
        assert dir_b in resolved.parents


class TestV1BackCompat:
    """Pre-L4 (schema v1) manifests still load read-only."""

    def test_v1_loads_components_and_mates(self) -> None:
        v1 = {
            "schema_version": 1,
            "components": [
                {
                    "id": "housing",
                    "sw_name": "housing-1",
                    "part_path": "/parts/housing.sldprt",
                    "transform": {},
                },
            ],
            "mates": [
                {
                    "type": "coincident",
                    "alignment": "aligned",
                    "a": {"component": "housing", "face_ref": {}},
                    "b": {"component": "shaft", "face_ref": {}},
                },
            ],
        }
        m = AssemblyManifest.from_dict(v1)
        assert m.schema_version == 1
        assert m.component_by_id("housing") is not None
        assert len(m.legacy_mates) == 1
        assert m.legacy_mates[0].type == "coincident"

    def test_v1_to_spec_raises(self) -> None:
        m = AssemblyManifest.from_dict(
            {"schema_version": 1, "components": [], "mates": []}
        )
        with pytest.raises(ValueError, match="no stored spec"):
            m.to_spec()
