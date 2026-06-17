"""Per-lane sketch-editing op registry (the W60 parallel-wiring seam).

Why this package exists: sketch-editing ops (Convert/Offset/Trim/Linear
Pattern) are the §6.5 CLI-only Propose-DryRun-Commit surface — they mutate an
existing sketch's segment set, so they belong with the W39 sketch-relations
family, NOT the ``feature_add`` registry and NOT MCP. Each op is one
collision-free lane module exporting an ``OP`` descriptor; W0 registers it
here (one line per lane), exactly like ``features.HANDLER_REGISTRY``.

Lane protocol (W60+):

1. Add ``sketch_editing/<op>.py`` exporting a module-level
   ``OP = SketchEditOp(op="sketch_<x>", schema=..., validate=..., apply=...,
   verify_effect=...)`` (see ``_base.SketchEditOp``). The op operates on the
   OPEN active sketch via ISketchManager; it does NOT open/close/rebuild.
   Verify-the-EFFECT is a sketch-segment COUNT delta (offset/convert/pattern
   add, trim removes/splits) — never a True return (the W21/W42 ghost trap).
2. Register it below its import: ``register(<op>.OP)`` (one line per lane).
3. Ships EMPTY until the first lane lands; the CLI then auto-advertises the
   registered op tokens and dispatches by ``spec["op"]``.
4. Lane tests patch COM seams on the lane module itself (selection /
   SketchManager), not on a shared module.
"""

from __future__ import annotations

from ._base import (
    OP_REGISTRY,
    SketchEditError,
    SketchEditOp,
    apply_sketch_edit,
    clear_selection,
    close_sketch,
    count_segments,
    deg_to_rad,
    get_segments,
    mm_to_m,
    open_sketch_for_edit,
    register,
    select_segment,
    sketch_edit_spec_schema,
    validate_sketch_edit_spec,
)

__all__ = [
    "OP_REGISTRY",
    "SketchEditError",
    "SketchEditOp",
    "apply_sketch_edit",
    "clear_selection",
    "close_sketch",
    "count_segments",
    "deg_to_rad",
    "get_segments",
    "mm_to_m",
    "open_sketch_for_edit",
    "register",
    "select_segment",
    "sketch_edit_spec_schema",
    "validate_sketch_edit_spec",
]

# ---------------------------------------------------------------------------
# Lane registrations — ONE line per op, added by W0 as each lane lands.
# Each is seat-PROVEN (verify-the-effect segment delta survived save->reopen)
# before being wired here, exactly like features.HANDLER_REGISTRY.
#
# Pending lanes (wired as each spike passes on the live seat):
#   from . import convert as _convert          # noqa: E402
#   register(_convert.OP)
#   from . import trim as _trim                # noqa: E402
#   register(_trim.OP)
# ---------------------------------------------------------------------------

from . import offset as _offset  # noqa: E402

register(_offset.OP)

from . import pattern as _pattern  # noqa: E402

register(_pattern.OP)
