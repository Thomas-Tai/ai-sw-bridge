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
