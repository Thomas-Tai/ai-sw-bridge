"""Per-lane ``feature_add`` handler registry (the W56 parallel-wiring seam).

Why this package exists: every shipped ``_create_*`` handler lives in
``ai_sw_bridge.mutate`` and STAYS there — their offline tests monkeypatch
the COM seams (``typed_qi`` / ``select_entity`` / ``get_sw_app`` / ...) on
the ``mutate`` module namespace, so relocating them would break that
resolution for the whole suite. NEW feature_add kinds land here instead:
one module per lane, one registry entry, so parallel waves never collide
inside ``mutate.py`` (the single-file constraint that forced W56 wiring to
be sequenced one-lane-at-a-time).

Lane protocol (W56+):

1. Add ``features/<kind>.py`` defining a handler with the uniform
   ``_apply_feature`` contract::

       def create_<kind>(doc, feature, target) -> tuple[bool, str | None]

   (shared by dry-run and commit; return ``(False, <reason>)`` rather than
   raising). Verify-the-EFFECT inside the handler — volume/face/scalar
   delta, never count+name+"no error" (the W21/W42 ghost trap).
2. Register it below its module: ``HANDLER_REGISTRY["<kind>"] = create_<kind>``
   (imported and merged here, one line per lane).
3. Registry kinds are auto-advertised by ``sw_propose_feature_add`` and
   dispatched by ``_apply_feature`` after the built-in chain; built-in
   kinds win on a name collision, so keep keys disjoint from
   ``mutate._SUPPORTED_FEATURE_TYPES``.
4. Propose-time parameter validation does NOT run for registry kinds —
   the handler must fail closed at dry-run on bad parameters.
5. Lane tests patch COM seams on the lane module itself (e.g.
   ``monkeypatch.setattr(features.rib, "typed_qi", ...)``), not on
   ``mutate``.
"""

from __future__ import annotations

from typing import Any, Callable

Handler = Callable[[Any, dict, dict], "tuple[bool, str | None]"]

# kind -> handler. Populated by per-lane modules; ships empty until W56
# wires the first proven W55 recipe in.
HANDLER_REGISTRY: dict[str, Handler] = {}

# W59 — sheet-metal hem via legacy InsertSheetMetalHem. CreateDefinition is
# E_NOINTERFACE for hem (W55-C), but the legacy route is GENERATIVE: seat-
# proven 2026-06-16 (spike_hem_v5, faces +8 / vol +1103.84 mm³ / survives
# reopen) via VARIANT(VT_DISPATCH,None) PCBA-null + a boundary edge_ref.
from .hem import create_hem  # noqa: E402

HANDLER_REGISTRY["hem"] = create_hem

# W59 — move_copy_body. Imports DORMANT and stays that way: both OOP routes
# are characterized walls (W58 InsertMoveCopyBody2 + CreateDefinition,
# W59 InsertMoveFace3 — all silent no-ops). The module's _register() gate
# never fires (SPIKE_STATUS != "GREEN"), so the registry advertises nothing;
# the move/copy intent is covered by the sketch-offset workaround (author
# geometry at the target coords via boss_extrude). Kept for fail-loud + the
# wall provenance.
from . import move_copy_body as _move_copy_body  # noqa: E402,F401

# W62 — composite curve (curves group, lane 1). Mode-A QUARANTINED on this
# SW build: the swconst harvest (docs/sw_api_full.json @ 32.1.0.123) exposes
# only two curve enums (14/61), neither yields a CreateDefinition object
# that accepts ICompositeCurveFeatureData (QI E_NOINTERFACE on the live
# seat). The interface is edit-only via IFeature.GetDefinition. Mode-B
# fires generative via legacy InsertCompositeCurve with mark=1 selection
# (the "Edges to join" PropertyManager list-box mark) and the callable-OR-
# property invocation guard (auto-invoked dispid trap). Seat-proven 2026-06-17
# (spike_composite, nodes +1 on a 40×30×10 block, survives save→reopen).
from .composite import SPIKE_STATUS as _composite_status  # noqa: E402
from .composite import create_composite  # noqa: E402

if _composite_status == "GREEN":
    HANDLER_REGISTRY["composite"] = create_composite
