"""JSON Schema fragment for the ``kind:"import"`` spec envelope.

v1 envelope is deliberately narrow:

.. code-block:: json

    {
        "kind": "import",
        "source": "path/to/vendor.step",
        "output": "path/to/imported.sldprt"
    }

Extensions recognized (case-insensitive): ``.step``, ``.stp``, ``.iges``,
``.igs``. Anything else is rejected at validation time (fail-closed —
the spec author gets a typed error before any COM call).
"""

from __future__ import annotations

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({".step", ".stp", ".iges", ".igs"})
"""Lower-cased extensions accepted by the validator."""

IMPORT_SPEC_SCHEMA: dict = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "ai-sw-bridge import spec (v1)",
    "description": (
        "Imports a foreign geometry file (STEP / IGES) into a new SOLIDWORKS "
        ".SLDPRT as a dumb B-rep solid. v1 deliberately excludes feature-tree "
        "reconstruction, healing, and re-parameterization."
    ),
    "type": "object",
    "required": ["kind", "source", "output"],
    "additionalProperties": False,
    "properties": {
        "kind": {"const": "import"},
        "source": {
            "type": "string",
            "minLength": 1,
            "description": "Absolute or CWD-relative path to the STEP / IGES file.",
        },
        "output": {
            "type": "string",
            "minLength": 1,
            "description": (
                "Absolute or CWD-relative path of the .SLDPRT to write. "
                "Parent directory must exist."
            ),
        },
        "verify": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "volume_mm3": {
                    "type": "number",
                    "exclusiveMinimum": 0,
                    "description": (
                        "Expected solid volume in mm³. The import fails if the "
                        "measured volume deviates from this by more than "
                        "volume_rel_tol."
                    ),
                },
                "volume_rel_tol": {
                    "type": "number",
                    "exclusiveMinimum": 0,
                    "maximum": 1,
                    "default": 0.01,
                    "description": "Relative tolerance on the volume check (default 1%).",
                },
                "min_bodies": {
                    "type": "integer",
                    "minimum": 1,
                    "default": 1,
                    "description": "Minimum number of solid bodies required.",
                },
            },
        },
    },
}
