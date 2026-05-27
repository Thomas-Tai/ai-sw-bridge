"""B-rep package (L1 lane, spec.md §2).

Exports the public API for the L1 B-rep lane:

- ``interrogate(feature, ctx)`` — run the interrogation algorithm and
  return a dict describing the feature's topology (faces + normals +
  centroids + role hints). Returns ``None`` when the
  ``brep_interrogation`` flag is OFF.
- ``fingerprint(...)`` — stable 16-hex identity hash for a face, used
  by the manifest and resolver to match faces across builds.
- ``Manifest`` — per-feature brep block accumulator with JSON
  serialization (spec.md §2.5).
- ``resolve_face_role(...)`` — resolve a symbolic ``face_role`` against
  a parent feature's brep block. Raises ``FaceResolutionError`` or
  ``FaceAmbiguityError`` on failure.
"""

from __future__ import annotations

from .fingerprint import fingerprint
from .interrogator import BrepFace, interrogate
from .manifest import Manifest
from .resolver import FaceAmbiguityError, FaceResolutionError, resolve_face_role

__all__ = [
    "BrepFace",
    "FaceAmbiguityError",
    "FaceResolutionError",
    "Manifest",
    "fingerprint",
    "interrogate",
    "resolve_face_role",
]
