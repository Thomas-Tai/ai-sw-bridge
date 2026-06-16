"""W59 / #9 — move_copy_body handler (body op — redirect to face route).

W59 MISSION REDIRECT (2026-06-16) — BOTH OOP ROUTES NOW WALLED:
    ``InsertMoveCopyBody2`` is a definitively characterized OOP wall
    (audit §5 #9, WALLED W58) — the COM boundary silently drops the
    body-pointer SAFEARRAY the finalize needs, and
    ``CreateDefinition(swFmMoveCopyBody)`` QIs E_NOINTERFACE.
    The W59 escape hatch ``InsertMoveFace3`` (surface-topology route)
    was FIRED on the live seat and ALSO WALLED — on a single valid +X
    face with a correct ``[0.03,0,0]`` translation vector the call
    returned ``call_ok=true`` / ``None`` / ΔVol=0 / zero ``GetPartBox``
    shift (the third silent no-op of this class). See
    ``spikes/v0_2x/spike_move_face_translate.py`` for the wall provenance.
    Only escape-hatch #2 (sketch-offset pre-extrude) remains live; this
    module therefore stays DORMANT (``SPIKE_STATUS`` never reached
    "GREEN" for either OOP route).

Two ``feature_add`` kinds wired via the HANDLER_REGISTRY seam — but ONLY
after the seat spike turns GREEN (W0 flips ``SPIKE_STATUS`` below):

    move_body — translate a solid body by (dx, dy, dz) in metres
    copy_body — duplicate a solid body, optionally translated

DORMANT STATE (pre-spike):
    This module imports cleanly but does NOT register either kind in
    ``HANDLER_REGISTRY`` while ``SPIKE_STATUS != "GREEN"``. The registry
    stays empty (the proven-recipe-first rule — W56+), so the advertised
    surface of ``sw_propose_feature_add`` does not claim kinds whose COM
    arg shape has not been proven on a live seat. After W0 fires
    ``spikes/v0_2x/spike_move_copy_body.py`` GREEN and flips
    ``SPIKE_STATUS`` here to ``"GREEN"``, both kinds register atomically
    with proof in hand.

Spike provenance:
    Body route (WALLED): ``spikes/v0_2x/spike_move_copy_body.py`` (W59).
    Face route (WALLED): ``spikes/v0_2x/spike_move_face_translate.py``
    (W59, FIRED 2026-06-16 → silent no-op, ΔVol=0 on a single valid
    face). Both seat-gated COM routes are characterized walls; the
    module stays dormant and fails loud.

Likely TLB-dumped signature (to be confirmed by spike Phase 1)::

    IFeatureManager.InsertMoveCopyBody2(
        Dx: VT_R8,          # translation X (metres)
        Dy: VT_R8,          # translation Y (metres)
        Dz: VT_R8,          # translation Z (metres)
        Rx: VT_R8,          # rotation about X (radians)
        Ry: VT_R8,          # rotation about Y (radians)
        Rz: VT_R8,          # rotation about Z (radians)
        Copy: VT_BOOL,      # True = copy, False = move
        NoOfBodiesToCopyTo: VT_I4  # 0 = new body (default)
    )

Verify-the-effect (the ONLY success signal):
    move_body — centroid delta matches commanded translation after save→reopen
    copy_body — body count +1 after save→reopen

Combine/split are WALLED (audit §4); move_copy_body is now ALSO fully
walled out-of-process (W58 body route + W59 face route both no-op) —
only a sketch-offset pre-extrude transform or an in-process add-in
(Route-D) remains. See [[project_body_ops_epoch]].

SEAT-PENDING (W0): both handlers fail closed with a SEAT-PENDING message
until the spike is GREEN on a live seat and W0 records the proven arg
shape.
"""

from __future__ import annotations

from typing import Any

from . import HANDLER_REGISTRY

SPIKE_ID = "spike_move_copy_body"
SPIKE_STATUS = "UNRUN"

_METHOD_NAME = "InsertMoveCopyBody2"


def _body_count(doc: Any) -> int:
    """Count solid bodies via GetBodies2(type=0, visibleOnly=True)."""
    try:
        bodies = doc.GetBodies2(0, True)
        if bodies is None:
            return 0
        return len(bodies) if isinstance(bodies, (list, tuple)) else 1
    except Exception:
        return 0


def _body_centroid_m(doc: Any) -> tuple[float, float, float] | None:
    """Read part-level centre of mass via Extension.CreateMassProperty."""
    try:
        ext = doc.Extension
        mp = ext.CreateMassProperty()
        if mp is None:
            return None
        cog = mp.CenterOfMass
        if cog is None:
            return None
        if callable(cog):
            cog = cog()
        if cog is None:
            return None
        c = list(cog) if isinstance(cog, (tuple, list)) else [cog]
        if len(c) < 3:
            return None
        return (float(c[0]), float(c[1]), float(c[2]))
    except Exception:
        return None


def create_move_body(
    doc: Any, feature: dict, target: dict
) -> tuple[bool, str | None]:
    """Move a solid body by a commanded translation delta.

    SEAT-PENDING (W0): the ``InsertMoveCopyBody2`` call is stubbed.
    W0 runs ``spikes/v0_2x/spike_move_copy_body.py``, confirms the arg
    shape, replaces the stub, and promotes to wired.

    ``feature`` shape::

        {
            "type": "move_body",
            "dx": 0.005,        # translation X in metres
            "dy": 0.0,
            "dz": 0.0,
            "rx": 0.0,          # optional rotation (radians)
            "ry": 0.0,
            "rz": 0.0,
        }

    ``target`` shape::

        {}                      # no target needed (moves all solid bodies)
        {"body_name": "Body1"}  # optional: move a specific body only
    """
    if SPIKE_STATUS != "GREEN":
        return False, (
            f"move_body is SEAT-PENDING (W0): {SPIKE_ID} is {SPIKE_STATUS}. "
            f"The {_METHOD_NAME} arg shape must be confirmed on a live seat."
        )

    dx = float(feature.get("dx", 0.0))
    dy = float(feature.get("dy", 0.0))
    dz = float(feature.get("dz", 0.0))
    rx = float(feature.get("rx", 0.0))
    ry = float(feature.get("ry", 0.0))
    rz = float(feature.get("rz", 0.0))

    before_centroid = _body_centroid_m(doc)
    if before_centroid is None:
        return False, "could not read body centroid (no solid body?)"

    try:
        fm = doc.FeatureManager
        fm.InsertMoveCopyBody2(dx, dy, dz, rx, ry, rz, False, 0)
        doc.ForceRebuild3(False)
    except Exception as exc:
        return False, f"InsertMoveCopyBody2(move) failed: {exc!r}"

    after_centroid = _body_centroid_m(doc)
    if after_centroid is None:
        return False, "centroid unreadable after move call"

    tolerance = max(abs(dx), abs(dy), abs(dz)) * 0.1 + 1e-9
    actual_dx = after_centroid[0] - before_centroid[0]
    actual_dy = after_centroid[1] - before_centroid[1]
    actual_dz = after_centroid[2] - before_centroid[2]

    if (
        abs(actual_dx - dx) < tolerance
        and abs(actual_dy - dy) < tolerance
        and abs(actual_dz - dz) < tolerance
    ):
        return True, None
    return False, (
        f"centroid delta ({actual_dx:.6f}, {actual_dy:.6f}, {actual_dz:.6f}) "
        f"does not match commanded ({dx:.6f}, {dy:.6f}, {dz:.6f})"
    )


def create_copy_body(
    doc: Any, feature: dict, target: dict
) -> tuple[bool, str | None]:
    """Copy a solid body, optionally translating the copy.

    SEAT-PENDING (W0): the ``InsertMoveCopyBody2`` call is stubbed.
    W0 runs ``spikes/v0_2x/spike_move_copy_body.py``, confirms the arg
    shape, replaces the stub, and promotes to wired.

    ``feature`` shape::

        {
            "type": "copy_body",
            "dx": 0.025,        # optional offset for the copy (metres)
            "dy": 0.0,
            "dz": 0.0,
            "rx": 0.0,
            "ry": 0.0,
            "rz": 0.0,
        }

    ``target`` shape::

        {}                      # copies all solid bodies
        {"body_name": "Body1"}  # optional: copy a specific body only
    """
    if SPIKE_STATUS != "GREEN":
        return False, (
            f"copy_body is SEAT-PENDING (W0): {SPIKE_ID} is {SPIKE_STATUS}. "
            f"The {_METHOD_NAME} arg shape must be confirmed on a live seat."
        )

    dx = float(feature.get("dx", 0.0))
    dy = float(feature.get("dy", 0.0))
    dz = float(feature.get("dz", 0.0))
    rx = float(feature.get("rx", 0.0))
    ry = float(feature.get("ry", 0.0))
    rz = float(feature.get("rz", 0.0))

    before_count = _body_count(doc)
    if before_count < 1:
        return False, "no solid bodies to copy"

    try:
        fm = doc.FeatureManager
        fm.InsertMoveCopyBody2(dx, dy, dz, rx, ry, rz, True, 0)
        doc.ForceRebuild3(False)
    except Exception as exc:
        return False, f"InsertMoveCopyBody2(copy) failed: {exc!r}"

    after_count = _body_count(doc)
    if after_count > before_count:
        return True, None
    return False, (
        f"copy_body did not increase body count ({before_count} -> {after_count})"
    )


def _register() -> None:
    """Register the kinds iff the seat spike is proven GREEN.

    Called once at import. Re-callable from tests after monkeypatching
    ``SPIKE_STATUS`` to ``"GREEN"`` — the dormant-gate test exercises
    this path without resorting to exec/eval (Invariant #3 / R1).
    """
    if SPIKE_STATUS == "GREEN":
        HANDLER_REGISTRY["move_body"] = create_move_body
        HANDLER_REGISTRY["copy_body"] = create_copy_body


_register()
