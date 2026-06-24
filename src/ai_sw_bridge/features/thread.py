"""W59 — ``cosmetic_thread`` + ``cut_thread`` feature-add handlers (registry seam).

Cosmetic thread
~~~~~~~~~~~~~~~
Add a thread annotation on a cylindrical face — NO volume change.
Expected route (spike W59_thread pending seat-run):
    CreateDefinition(swFmCosmeticThread=29)
    → typed_qi(data, "ICosmeticThreadFeatureData")
    → set thread params (standard, size, pitch)
    → select cylindrical face
    → CreateFeature(fd)
Effect verification: feature-node delta AND thread annotation present
after save→reopen (cosmetic adds NO volume, so node-count alone is
insufficient per the edge_flange/draft ghost lesson).

Cut thread
~~~~~~~~~~
Remove material via helical sweep cut — ΔVol < 0.
Expected route (spike W59_thread pending seat-run):
    CreateDefinition(swFmSweepThread=87)
    → probe the returned feature-data interface
    → set thread params
    → select cylindrical face
    → CreateFeature(fd)
Effect verification: ΔVol < 0 (material removed), persists after reopen.

SEAT-PENDING (W0): both handlers are stubbed behind spike W59_thread.
The exact CreateDefinition pipeline args, the ICosmeticThreadFeatureData
interface shape, and the selection mark values are all unspiked — do NOT
fabricate them.  When W0 runs the spike and it returns GREEN, replace
the ``_STUB`` body with the proven recipe.
"""

from __future__ import annotations

from typing import Any

# Flipped to "GREEN" by W0 after spike W59_thread returns PASS on the seat.
# While "UNRUN", this module is dormant: handlers exist but are NOT registered.
SPIKE_STATUS = "UNRUN"

_COSMETIC_STUB = (
    "cosmetic_thread: SEAT-PENDING — spike W59_thread not yet run; "
    "CreateDefinition(29) pipeline args unspiked"
)
_CUT_STUB = (
    "cut_thread: SEAT-PENDING — spike W59_thread not yet run; "
    "CreateDefinition(87) pipeline args unspiked"
)


def create_cosmetic_thread(
    doc: Any,
    feature: dict,
    target: dict,
) -> tuple[bool, str | None]:
    """Insert a cosmetic thread annotation on a cylindrical face.

    .. seat-pending:: spike W59_thread

    ``feature`` keys (expected, pending spike):
        thread_standard : str — e.g. "Metric", "UNC"
        thread_size : str — e.g. "M10"
        thread_pitch_mm : float — e.g. 1.5
        thread_depth_mm : float — e.g. 15.0

    ``target`` keys (expected, pending spike):
        face_ref : dict — durable face reference for the cylindrical host
    """
    return False, _COSMETIC_STUB


def create_cut_thread(
    doc: Any,
    feature: dict,
    target: dict,
) -> tuple[bool, str | None]:
    """Insert a cut thread (helical sweep cut) on a cylindrical face.

    .. seat-pending:: spike W59_thread

    ``feature`` keys (expected, pending spike):
        thread_standard : str — e.g. "Metric", "UNC"
        thread_size : str — e.g. "M10"
        thread_pitch_mm : float — e.g. 1.5
        thread_depth_mm : float — e.g. 15.0
        direction : str — "right_hand" (default) or "left_hand"

    ``target`` keys (expected, pending spike):
        face_ref : dict — durable face reference for the cylindrical host
    """
    return False, _CUT_STUB


# ---------------------------------------------------------------------------
# Gated self-registration (W0 flips SPIKE_STATUS + adds import in __init__)
# ---------------------------------------------------------------------------

if SPIKE_STATUS == "GREEN":
    from . import HANDLER_REGISTRY

    HANDLER_REGISTRY["cosmetic_thread"] = create_cosmetic_thread
    HANDLER_REGISTRY["cut_thread"] = create_cut_thread
