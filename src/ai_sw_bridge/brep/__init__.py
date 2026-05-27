"""B-rep interrogation package (L1 lane, spec.md §2).

Exports the public API for the L1 B-rep lane:

- ``interrogate(feature, ctx)`` — run the interrogation algorithm and
  return a dict describing the feature's topology (faces + normals +
  centroids + role hints). Returns ``None`` when the
  ``brep_interrogation`` flag is OFF.
- ``fingerprint(...)`` — stable 16-hex identity hash for a face, used
  by the manifest and resolver to match faces across builds.
"""

from __future__ import annotations

from .fingerprint import fingerprint
from .interrogator import BrepFace, interrogate

__all__ = [
    "BrepFace",
    "fingerprint",
    "interrogate",
]
