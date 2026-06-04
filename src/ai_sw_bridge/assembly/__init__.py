"""Assembly spec support — schema, validation, handlers (Wave-9 Phase 1).

This package provides the ``kind: "assembly"`` spec support, sibling to the
existing part spec. It covers component placement (from saved ``.sldprt`` files
or from ``part_spec`` build-then-place) and coincident mating.

The assembly kind stays **de-advertised** (fail-closed in propose) until the
Phase-1 PAE clears.
"""

from .schema import ASSEMBLY_SCHEMA, MATE_TYPES, MATE_ALIGNMENTS
from .validator import validate_assembly, AssemblyValidationError
from .storage import AssemblyManifest, ComponentInstance, MateRecord
from .face_resolver import resolve_component_face, ComponentFaceResolution

__all__ = [
    "ASSEMBLY_SCHEMA",
    "AssemblyManifest",
    "AssemblyValidationError",
    "ComponentFaceResolution",
    "ComponentInstance",
    "MATE_ALIGNMENTS",
    "MATE_TYPES",
    "MateRecord",
    "resolve_component_face",
    "validate_assembly",
]
