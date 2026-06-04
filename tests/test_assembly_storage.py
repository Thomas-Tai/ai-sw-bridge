"""Tests for assembly manifest storage (Wave-9 Slice 2).

Round-trip tests for ComponentInstance, MateRecord, AssemblyManifest.
No SOLIDWORKS required.
"""

from __future__ import annotations

import json
from pathlib import Path

from ai_sw_bridge.assembly.storage import (
    AssemblyManifest,
    ComponentInstance,
    MateRecord,
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
        d = ci.to_dict()
        ci2 = ComponentInstance.from_dict(d)
        assert ci2.id == ci.id
        assert ci2.sw_name == ci.sw_name
        assert ci2.part_path == ci.part_path
        assert ci2.transform == ci.transform

    def test_default_transform(self) -> None:
        ci = ComponentInstance(id="x", sw_name="x-1", part_path="/p.sldprt")
        assert ci.transform == {}
        d = ci.to_dict()
        assert d["transform"] == {}

    def test_frozen(self) -> None:
        ci = ComponentInstance(id="x", sw_name="x-1", part_path="/p.sldprt")
        import pytest
        with pytest.raises(AttributeError):
            ci.id = "y"  # type: ignore[misc]


# ---- MateRecord ------------------------------------------------------------


class TestMateRecord:
    def test_round_trip_coincident(self) -> None:
        mr = MateRecord(
            type="coincident",
            alignment="aligned",
            a={"component": "housing", "face_ref": {"normal": [0, 0, 1]}},
            b={"component": "shaft", "face_ref": {"normal": [0, 0, -1]}},
        )
        d = mr.to_dict()
        mr2 = MateRecord.from_dict(d)
        assert mr2.type == "coincident"
        assert mr2.alignment == "aligned"
        assert mr2.a["component"] == "housing"
        assert mr2.b["face_ref"]["normal"] == [0, 0, -1]
        assert mr2.value is None

    def test_round_trip_distance(self) -> None:
        mr = MateRecord(
            type="distance",
            alignment="aligned",
            a={"component": "a", "face_ref": {"normal": [1, 0, 0]}},
            b={"component": "b", "face_ref": {"normal": [-1, 0, 0]}},
            value=5.0,
        )
        d = mr.to_dict()
        assert d["value"] == 5.0
        mr2 = MateRecord.from_dict(d)
        assert mr2.value == 5.0

    def test_no_value_omitted(self) -> None:
        mr = MateRecord(
            type="coincident",
            alignment="closest",
            a={"component": "a", "face_ref": {}},
            b={"component": "b", "face_ref": {}},
        )
        d = mr.to_dict()
        assert "value" not in d


# ---- AssemblyManifest ------------------------------------------------------


class TestAssemblyManifest:
    def _sample_manifest(self) -> AssemblyManifest:
        return AssemblyManifest(
            components=[
                ComponentInstance(
                    id="housing",
                    sw_name="housing-1",
                    part_path="/parts/housing.sldprt",
                    transform={"xyz_mm": [0, 0, 0]},
                ),
                ComponentInstance(
                    id="shaft",
                    sw_name="shaft-1",
                    part_path="/parts/shaft.sldprt",
                    transform={"xyz_mm": [0, 0, 40]},
                ),
            ],
            mates=[
                MateRecord(
                    type="coincident",
                    alignment="aligned",
                    a={
                        "component": "housing",
                        "face_ref": {"normal": [0, 0, 1], "centroid": [0, 0, 20]},
                    },
                    b={
                        "component": "shaft",
                        "face_ref": {"normal": [0, 0, -1], "centroid": [0, 0, 20]},
                    },
                ),
            ],
        )

    def test_round_trip_dict(self) -> None:
        m = self._sample_manifest()
        d = m.to_dict()
        m2 = AssemblyManifest.from_dict(d)
        assert len(m2.components) == 2
        assert len(m2.mates) == 1
        assert m2.components[0].id == "housing"
        assert m2.mates[0].type == "coincident"

    def test_round_trip_json(self) -> None:
        m = self._sample_manifest()
        text = m.to_json()
        m2 = AssemblyManifest.from_json(text)
        assert len(m2.components) == 2
        assert m2.components[1].sw_name == "shaft-1"

    def test_save_load(self, tmp_path: Path) -> None:
        m = self._sample_manifest()
        path = tmp_path / "manifest.json"
        m.save(path)
        assert path.exists()
        m2 = AssemblyManifest.load(path)
        assert m2.schema_version == 1
        assert m2.component_by_id("housing") is not None
        assert m2.component_by_id("shaft") is not None
        assert m2.component_by_id("ghost") is None

    def test_empty_manifest(self) -> None:
        m = AssemblyManifest()
        d = m.to_dict()
        assert d["schema_version"] == 1
        assert d["components"] == []
        assert d["mates"] == []
        m2 = AssemblyManifest.from_dict(d)
        assert len(m2.components) == 0

    def test_component_by_id(self) -> None:
        m = self._sample_manifest()
        c = m.component_by_id("shaft")
        assert c is not None
        assert c.part_path == "/parts/shaft.sldprt"

    def test_json_is_valid_json(self) -> None:
        m = self._sample_manifest()
        parsed = json.loads(m.to_json())
        assert parsed["schema_version"] == 1
        assert len(parsed["components"]) == 2
