"""Assembly manifest storage (Wave-9 Slice 2; L4 persistence Wave-14).

The assembly manifest is a JSON record written alongside the assembly
``.sldasm`` at commit time. Schema **v2** stores the **verbatim authoring spec**
(the lossless source of truth for re-open / edit) plus a **runtime overlay** —
the SOLIDWORKS instance names, resolved part paths, and part-spec provenance
(source path + content hash) gathered at commit:

  - ``spec`` — the exact validated assembly spec, unmodified. Re-opening an
    assembly is just ``manifest.to_spec()`` — there is no field mapping that
    could drift, so the round-trip is lossless by construction.
  - ``runtime.components`` — per component ``{id, sw_name, part_path,
    part_spec_path?, part_spec_sha256?}``.

Paths in the runtime overlay are stored **relative to the manifest file** on
disk (portable across moves) and resolved to absolute on ``load``. The verbatim
``spec`` is left untouched (so it stays lossless); re-resolution should prefer
the runtime overlay's portable ``part_path``. B-rep is NOT duplicated — each
part's B-rep manifest lives with its ``.sldprt``.

Schema **v1** (the pre-L4 ``components[]/mates[]`` form) still loads read-only
via ``from_dict`` (into ``components`` + ``legacy_mates``); ``to_spec`` is
unavailable on a v1 manifest because it has no stored spec.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 2


def sha256_of_file(path: str | Path | None) -> str | None:
    """Hex SHA-256 of a file's bytes, or ``None`` if absent/unreadable."""
    if not path:
        return None
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    return hashlib.sha256(data).hexdigest()


def _relativize(p: str | None, base: Path) -> str | None:
    """Make ``p`` relative to ``base`` for portable on-disk storage. Falls back
    to the original (absolute) value across drives (Windows ``relpath`` raises).
    """
    if not p:
        return p
    try:
        return os.path.relpath(p, base)
    except ValueError:
        return p


def _absolutize(p: str | None, base: Path) -> str | None:
    """Resolve a possibly-relative stored path against the manifest dir."""
    if not p:
        return p
    pp = Path(p)
    if pp.is_absolute():
        return str(pp)
    return str((base / pp).resolve())


@dataclass(frozen=True)
class ComponentInstance:
    """Runtime overlay for one placed component.

    ``sw_name`` is the SOLIDWORKS-generated instance name recorded at commit.
    ``part_path`` is the resolved ``.sldprt``. ``part_spec_path`` /
    ``part_spec_sha256`` capture provenance when the component was built from a
    declarative part spec (both ``None`` for a prebuilt part).
    """

    id: str
    sw_name: str
    part_path: str
    transform: dict[str, Any] = field(default_factory=dict)
    part_spec_path: str | None = None
    part_spec_sha256: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "sw_name": self.sw_name,
            "part_path": self.part_path,
            "transform": dict(self.transform),
        }
        if self.part_spec_path is not None:
            out["part_spec_path"] = self.part_spec_path
        if self.part_spec_sha256 is not None:
            out["part_spec_sha256"] = self.part_spec_sha256
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ComponentInstance:
        return cls(
            id=data["id"],
            sw_name=data["sw_name"],
            part_path=data["part_path"],
            transform=data.get("transform", {}),
            part_spec_path=data.get("part_spec_path"),
            part_spec_sha256=data.get("part_spec_sha256"),
        )


@dataclass(frozen=True)
class MateRecord:
    """A mate between component faces (schema-v1 read-only legacy).

    In schema v2 the mate graph lives verbatim inside the manifest ``spec``;
    this record is retained only to parse pre-L4 (v1) manifests and for the
    public ``assembly`` API surface. Symmetric mates use ``a``/``b``; width
    mates use ``width_faces``/``tab_faces``.
    """

    type: str
    alignment: str | None
    a: dict[str, Any] = field(default_factory=dict)
    b: dict[str, Any] = field(default_factory=dict)
    value: float | None = None
    width_faces: list[dict[str, Any]] | None = None
    tab_faces: list[dict[str, Any]] | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "type": self.type,
            "alignment": self.alignment,
        }
        if self.width_faces is not None:
            out["width_faces"] = [dict(r) for r in self.width_faces]
            out["tab_faces"] = [dict(r) for r in (self.tab_faces or [])]
        else:
            out["a"] = dict(self.a)
            out["b"] = dict(self.b)
        if self.value is not None:
            out["value"] = self.value
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MateRecord:
        return cls(
            type=data["type"],
            alignment=data.get("alignment"),
            a=data.get("a", {}),
            b=data.get("b", {}),
            value=data.get("value"),
            width_faces=data.get("width_faces"),
            tab_faces=data.get("tab_faces"),
        )


@dataclass
class AssemblyManifest:
    """Assembly manifest (schema v2): verbatim ``spec`` + runtime overlay.

    Written as ``<assembly>.sldasm.manifest.json`` alongside the assembly. Does
    not duplicate part B-rep. ``to_spec()`` returns the stored authoring spec
    for lossless re-open.
    """

    schema_version: int = SCHEMA_VERSION
    spec: dict[str, Any] = field(default_factory=dict)
    assembly_path: str | None = None
    components: list[ComponentInstance] = field(default_factory=list)
    # v1 read-only legacy: populated only when loading a schema_version==1 doc.
    legacy_mates: list[MateRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "spec": self.spec,
            "runtime": {
                "assembly_path": self.assembly_path,
                "components": [c.to_dict() for c in self.components],
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AssemblyManifest:
        # v2: has a verbatim ``spec`` + ``runtime`` overlay.
        if "spec" in data or "runtime" in data or data.get("schema_version") == 2:
            runtime = data.get("runtime") or {}
            return cls(
                schema_version=data.get("schema_version", SCHEMA_VERSION),
                spec=data.get("spec", {}),
                assembly_path=runtime.get("assembly_path"),
                components=[
                    ComponentInstance.from_dict(c)
                    for c in runtime.get("components", [])
                ],
            )
        # v1 back-compat (read-only): flat components[]/mates[].
        return cls(
            schema_version=1,
            spec={},
            assembly_path=None,
            components=[
                ComponentInstance.from_dict(c) for c in data.get("components", [])
            ],
            legacy_mates=[
                MateRecord.from_dict(m) for m in data.get("mates", [])
            ],
        )

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    @classmethod
    def from_json(cls, text: str) -> AssemblyManifest:
        return cls.from_dict(json.loads(text))

    def save(self, path: Path) -> None:
        """Write the manifest to ``path`` with runtime paths made relative to
        the manifest's directory (portable). The verbatim ``spec`` is untouched.
        """
        path = Path(path)
        base = path.parent
        d = self.to_dict()
        rt = d.get("runtime") or {}
        rt["assembly_path"] = _relativize(rt.get("assembly_path"), base)
        for c in rt.get("components", []):
            c["part_path"] = _relativize(c.get("part_path"), base)
            if c.get("part_spec_path") is not None:
                c["part_spec_path"] = _relativize(c.get("part_spec_path"), base)
        path.write_text(json.dumps(d, indent=2, default=str), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> AssemblyManifest:
        """Load a manifest, resolving runtime paths to absolute against the
        manifest's directory."""
        path = Path(path)
        base = path.parent
        m = cls.from_json(path.read_text(encoding="utf-8"))
        m.assembly_path = _absolutize(m.assembly_path, base)
        m.components = [
            ComponentInstance(
                id=c.id,
                sw_name=c.sw_name,
                part_path=_absolutize(c.part_path, base) or c.part_path,
                transform=c.transform,
                part_spec_path=_absolutize(c.part_spec_path, base),
                part_spec_sha256=c.part_spec_sha256,
            )
            for c in m.components
        ]
        return m

    def to_spec(self) -> dict[str, Any]:
        """Return the verbatim authoring spec for lossless re-open.

        Raises ``ValueError`` on a v1/empty manifest (no stored spec).
        """
        if not self.spec:
            raise ValueError(
                "manifest has no stored spec (schema v1 or empty); cannot "
                "reconstruct the authoring spec"
            )
        return self.spec

    def component_by_id(self, cid: str) -> ComponentInstance | None:
        for c in self.components:
            if c.id == cid:
                return c
        return None
