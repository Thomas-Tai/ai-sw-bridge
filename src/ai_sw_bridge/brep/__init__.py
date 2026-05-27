"""B-rep interrogation package (L1 lane, spec.md §2).

Exports the public API for the L1 B-rep lane:

- ``interrogate(feature, ctx)`` — run the interrogation algorithm and
  return a dict describing the feature's topology (faces + normals +
  centroids + role hints). Returns ``None`` when the
  ``brep_interrogation`` flag is OFF.
"""

from __future__ import annotations

from .interrogator import BrepFace, interrogate

__all__ = [
    "BrepFace",
    "interrogate",
]
