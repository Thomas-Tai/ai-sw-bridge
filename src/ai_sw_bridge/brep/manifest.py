"""B-rep manifest — per-feature brep block serialization (spec.md §2.5).

A :class:`Manifest` accumulates per-feature brep blocks during a
build. Each feature's interrogator output (from
``brep.interrogator.interrogate``) is passed through
:meth:`Manifest.add_feature`, which:

1. Assigns a stable fingerprint (via ``brep.fingerprint.fingerprint``)
   to every face in the feature's brep block.
2. Strips the session-scoped ``temp_id`` from the serialized output
   (per spec §2.5 — temp_id is intentionally omitted because it's
   session-scoped only and would mislead consumers).
3. Stores the feature's brep block keyed by feature name.

The manifest is append-only within one build. Serialization via
:meth:`Manifest.to_dict` / :meth:`Manifest.to_json` produces the
per-feature ``brep`` block shape described in spec.md §2.5.
Round-trip via :meth:`Manifest.from_dict` preserves all fields.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterator

from .fingerprint import fingerprint as _compute_fingerprint


@dataclass
class Manifest:
    """In-memory per-build brep manifest.

    ``features`` maps ``feature_name -> brep block``. The brep block
    shape matches spec.md §2.5:

    ```
    {
      "feature": "Extrude_Plate",
      "type": "boss_extrude_blind",    # optional, from interrogator
      "faces": [
        {
          "fingerprint": "a3f9...",
          "role_hint": "+z_outboard",
          "normal": [0.0, 0.0, 1.0],
          "centroid": [0.0, 0.0, 0.005],
          "bbox": [[-0.025, -0.025, 0.005], [0.025, 0.025, 0.005]],
          "area_mm2": 2500.0,
          "body_id": 0,
          "face_idx": 0,
          "is_surface": false
        }
      ]
    }
    ```

    ``active_configuration`` records the SW configuration name the
    manifest was generated against (audit §6.2). Configurations carry
    different geometry; downstream consumers that re-run a spec
    against a different configuration must invalidate the manifest.
    The field is ``None`` when the builder couldn't read it (e.g.,
    on a part without explicit configurations).
    """

    features: dict[str, dict[str, Any]] = field(default_factory=dict)
    active_configuration: str | None = None

    # ------------------------------------------------------------------
    # Append API
    # ------------------------------------------------------------------

    def add_feature(
        self,
        interrogation_result: dict[str, Any],
        *,
        feature_type: str | None = None,
    ) -> str:
        """Add one feature's brep block to the manifest.

        ``interrogation_result`` is the dict returned by
        ``brep.interrogator.interrogate``. Each face gets a
        fingerprint assigned here; the session-scoped ``temp_id`` is
        stripped from the output.

        Returns the feature name (the manifest key).
        """
        if interrogation_result is None:
            raise ValueError("interrogation_result must not be None")
        name = interrogation_result.get("feature")
        if not name:
            raise ValueError("interrogation_result missing 'feature' key")

        faces_out: list[dict[str, Any]] = []
        for face in interrogation_result.get("faces", []):
            out = self._serialize_face(face)
            faces_out.append(out)

        block: dict[str, Any] = {
            "feature": name,
            "faces": faces_out,
        }
        if feature_type is not None:
            block["type"] = feature_type
        if "error" in interrogation_result:
            block["error"] = interrogation_result["error"]
        if "status" in interrogation_result:
            # Edge-case markers from P0-8: "suppressed" / "imported".
            # Surface them in the manifest so the resolver knows why
            # the face list is empty.
            block["status"] = interrogation_result["status"]

        self.features[name] = block
        return name

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Return the full manifest as a JSON-serializable dict."""
        out: dict[str, Any] = {
            "schema_version": 1,
            "features": list(self.features.values()),
        }
        if self.active_configuration is not None:
            out["active_configuration"] = self.active_configuration
        return out

    def to_json(self, *, indent: int | None = None) -> str:
        """Return the manifest as a JSON string."""
        return json.dumps(self.to_dict(), sort_keys=False, indent=indent)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Manifest:
        """Round-trip the manifest from a dict produced by :meth:`to_dict`."""
        if not isinstance(data, dict):
            raise TypeError("manifest data must be a dict")
        if data.get("schema_version") != 1:
            raise ValueError(
                f"unsupported manifest schema_version: {data.get('schema_version')!r}"
            )
        features = data.get("features")
        if not isinstance(features, list):
            raise TypeError("manifest 'features' must be a list")
        manifest = cls(active_configuration=data.get("active_configuration"))
        for block in features:
            name = block.get("feature")
            if not name:
                raise ValueError("manifest feature block missing 'feature' key")
            manifest.features[name] = block
        return manifest

    @classmethod
    def from_json(cls, text: str) -> Manifest:
        """Round-trip the manifest from a JSON string."""
        return cls.from_dict(json.loads(text))

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def lookup(self, feature_name: str) -> dict[str, Any] | None:
        """Return the brep block for *feature_name* (or None)."""
        return self.features.get(feature_name)

    def __iter__(self) -> Iterator[str]:
        return iter(self.features)

    def __len__(self) -> int:
        return len(self.features)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _serialize_face(face: dict[str, Any]) -> dict[str, Any]:
        """Assign fingerprint + strip temp_id for one face dict."""
        fp = _compute_fingerprint(face)
        out: dict[str, Any] = {
            "fingerprint": fp,
            "face_idx": face.get("face_idx"),
            "body_id": face.get("body_id"),
            "role_hint": face.get("role_hint"),
            "normal": face.get("normal"),
            "centroid": face.get("centroid"),
            "bbox": face.get("bbox"),
            "area_mm2": face.get("area_mm2"),
            "is_surface": face.get("is_surface", False),
        }
        # temp_id is intentionally omitted from the serialized form
        # per spec §2.5 — it's session-scoped only.
        return out


__all__ = ["Manifest"]
