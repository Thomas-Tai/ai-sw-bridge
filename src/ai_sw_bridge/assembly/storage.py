"""Assembly manifest storage (Wave-9 Phase 1, Slice 2).

The assembly manifest is a thin JSON record alongside the assembly ``.sldasm``
file. It holds:

  - **Component instances** — ``{id, sw_name, part_path, transform}``
  - **Mate graph** — ``{type, alignment, value, a:{component, face_ref},
    b:{component, face_ref}}``

It does NOT duplicate part B-rep — each component's B-rep manifest lives with
the part file (via the existing ``brep.manifest`` infra). The assembly manifest
references component ``id``s and face_refs that can be resolved against the
per-part manifests at commit time.

Round-trips via ``to_dict`` / ``from_dict`` and ``to_json`` / ``from_json``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ComponentInstance:
    """A placed component in the assembly.

    ``sw_name`` is the SOLIDWORKS-generated instance name (e.g.
    ``housing-1``) recorded at commit time. ``part_path`` is the absolute path
    to the saved ``.sldprt`` on disk. ``transform`` is the placement transform
    (xyz_mm + optional rpy_deg).
    """

    id: str
    sw_name: str
    part_path: str
    transform: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "sw_name": self.sw_name,
            "part_path": self.part_path,
            "transform": dict(self.transform),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ComponentInstance:
        return cls(
            id=data["id"],
            sw_name=data["sw_name"],
            part_path=data["part_path"],
            transform=data.get("transform", {}),
        )


@dataclass(frozen=True)
class MateRecord:
    """A mate between two component faces.

    ``a`` and ``b`` are dicts of ``{component: <id>, face_ref: <manifest-face>}``.
    ``value`` is present for distance/angle mates (Phase 2+).
    """

    type: str
    alignment: str | None
    a: dict[str, Any]
    b: dict[str, Any]
    value: float | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "type": self.type,
            "alignment": self.alignment,
            "a": dict(self.a),
            "b": dict(self.b),
        }
        if self.value is not None:
            out["value"] = self.value
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MateRecord:
        return cls(
            type=data["type"],
            alignment=data.get("alignment"),
            a=data["a"],
            b=data["b"],
            value=data.get("value"),
        )


@dataclass
class AssemblyManifest:
    """Assembly manifest — component instances + mate graph.

    Written as a JSON file alongside the assembly ``.sldasm``. Does not
    duplicate part B-rep; references component ``id``s for resolution.
    """

    schema_version: int = 1
    components: list[ComponentInstance] = field(default_factory=list)
    mates: list[MateRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "components": [c.to_dict() for c in self.components],
            "mates": [m.to_dict() for m in self.mates],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AssemblyManifest:
        return cls(
            schema_version=data.get("schema_version", 1),
            components=[
                ComponentInstance.from_dict(c) for c in data.get("components", [])
            ],
            mates=[MateRecord.from_dict(m) for m in data.get("mates", [])],
        )

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    @classmethod
    def from_json(cls, text: str) -> AssemblyManifest:
        return cls.from_dict(json.loads(text))

    def save(self, path: Path) -> None:
        path.write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> AssemblyManifest:
        return cls.from_json(path.read_text(encoding="utf-8"))

    def component_by_id(self, cid: str) -> ComponentInstance | None:
        for c in self.components:
            if c.id == cid:
                return c
        return None
