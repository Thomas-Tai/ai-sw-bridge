"""Autonomous clearance solver (W76) — the closed-loop "make it fit" verb.

A thin, deterministic orchestration over shipped, seat-proven pieces:

  - sense : ``observe_interference._sw_get_interference_impl``  (W27)
  - act   : ``motion_audit.drive_mate_value_si``         (W49 — drives the
            named distance mate's ``D1@<mate>`` dimension + ``EditRebuild3``)

It drives one distance mate monotonically until the assembly is clash-free
(``count == 0`` AND ``volume == 0``), then stops. The capability is the loop:
the LLM proposes an assembly and calls this ONCE instead of hand-rolling a
read -> parse -> edit -> rebuild -> read cycle across its context window.

DESIGN — fixed step, NOT volume-derived. Interference volume is a 3D overlap
integral, not a 1D penetration depth, so volume->distance is non-linear and
geometry-specific; a calculated jump would need a true penetration-depth witness
(likely a derived-position boundary-law lane). The honest, robust solver is
monotonic fixed step-out with an iteration cap.

FAIL-CLOSED with REVERT. On hitting the iteration ceiling (or a wrong-direction
step that increases interference), the solver reverts the mate to its original
value and reports failure. A partially-resolved assembly is a silent-corruption
trap (looks "more correct" but is still invalid); the verb's contract is atomic
— fully resolve, or leave the model exactly as found — while still returning the
best-achieved state so the caller can re-call with a larger step / direction.

This module is a MUTATOR (it drives a mate): CLI-only, never MCP, per §6.5 —
the same gate ``ai-sw-motion`` follows.
"""

from __future__ import annotations

import math
from typing import Any

from .com.earlybind import typed
from .com.sw_type_info import wrapper_module
from .motion_audit import drive_mate_value_si, read_mate_value_si
from .observe_interference import _sw_get_interference_impl as sw_get_interference

_VOL_EPS = 1e-6  # mm³ — below this an overlap reads as "no interference"

_DIRECTIONS = {"out": +1, "in": -1}


def _vol_sum(intf: dict[str, Any]) -> float:
    return sum(
        float(i.get("interference_volume_mm3") or 0.0)
        for i in (intf.get("interferences") or [])
    )


def _save(doc: Any, mod: Any) -> bool:
    try:
        ret = typed(doc, "IModelDoc2", module=mod).Save3(1, 0, 0)
        if isinstance(ret, tuple):
            return bool(ret[0])
        return bool(ret)
    except Exception:  # noqa: BLE001
        return False


def resolve_clearance(
    doc: Any,
    mate_name: str,
    *,
    step_mm: float = 2.0,
    max_iters: int = 20,
    direction: str = "out",
    save: bool = False,
    mod: Any = None,
) -> dict[str, Any]:
    """Drive ``mate_name`` until the assembly is clash-free, or fail-closed.

    Args:
        doc: an open assembly ``IModelDoc2`` (raw dispatch — needs ``.Parameter``
            and ``GetType``).
        mate_name: the distance mate to drive (its driving dim is ``D1@<name>``).
        step_mm: monotonic increment per iteration (must be > 0).
        max_iters: hard ceiling on read/drive iterations (runaway guard).
        direction: ``"out"`` (increase the mate value, default) or ``"in"``.
        save: persist the resolved model on success (default False = dry-run).
        mod: makepy wrapper module (defaults to the cached one).

    Returns a structured report; ``ok`` is True only on full resolution.
    """
    mod = mod or wrapper_module()
    res: dict[str, Any] = {
        "tool": "auto_resolve_clearance",
        "ok": False,
        "mate": mate_name,
        "resolved": False,
        "resolved_mm": None,
        "initial_mm": None,
        "iterations": 0,
        "trajectory": [],
        "reverted": False,
        "saved": False,
        "best_state": None,
        "error": None,
    }

    # ── Input validation (fail fast, no seat mutation) ──────────────────────
    if not isinstance(mate_name, str) or not mate_name:
        res["error"] = "mate_name must be a non-empty string"
        return res
    if not (isinstance(step_mm, (int, float)) and step_mm > 0):
        res["error"] = f"step_mm must be > 0 (got {step_mm!r})"
        return res
    if not (isinstance(max_iters, int) and max_iters >= 1):
        res["error"] = f"max_iters must be a positive int (got {max_iters!r})"
        return res
    sign = _DIRECTIONS.get(direction)
    if sign is None:
        res["error"] = (
            f"direction must be one of {sorted(_DIRECTIONS)} (got {direction!r})"
        )
        return res

    # ── Capture the original value (the revert anchor) ──────────────────────
    orig_si = read_mate_value_si(doc, mate_name)
    if orig_si is None:
        res["error"] = (
            f"no driving dimension 'D1@{mate_name}' — is it a distance mate? "
            "auto_resolve_clearance drives distance mates only"
        )
        return res
    res["initial_mm"] = orig_si * 1000.0
    step_si = sign * (float(step_mm) / 1000.0)

    cur_si = orig_si
    best = {"dist_mm": None, "count": None, "volume_mm3": math.inf}
    solved = False
    drive_err: str | None = None
    worsened = False
    prev_vol: float | None = None

    for it in range(max_iters):
        intf = sw_get_interference(doc)
        if not intf.get("ok", True):
            drive_err = f"sense_error:{intf.get('error')}"
            break
        count = int(intf.get("interference_count", 0))
        vol = _vol_sum(intf)
        res["trajectory"].append(
            {
                "iter": it,
                "dist_mm": round(cur_si * 1000.0, 4),
                "count": count,
                "volume_mm3": round(vol, 4),
            }
        )
        if vol < best["volume_mm3"]:
            best = {
                "dist_mm": round(cur_si * 1000.0, 4),
                "count": count,
                "volume_mm3": round(vol, 4),
            }

        if count == 0 and vol <= _VOL_EPS:
            solved = True
            break

        # Wrong-direction guard: a step that increases interference means we are
        # driving the bodies together. Stop rather than diverge to the cap.
        if prev_vol is not None and vol > prev_vol + _VOL_EPS:
            worsened = True
            break
        prev_vol = vol

        # ACT: step + production rebuild.
        cur_si += step_si
        rc = drive_mate_value_si(doc, mate_name, cur_si, mod)
        if rc.startswith("FAIL"):
            drive_err = rc
            break

    res["iterations"] = len(res["trajectory"])
    res["best_state"] = None if best["dist_mm"] is None else best

    if solved:
        res["ok"] = True
        res["resolved"] = True
        res["resolved_mm"] = round(cur_si * 1000.0, 4)
        if save:
            res["saved"] = _save(doc, mod)
        return res

    # ── FAIL-CLOSED: revert to the original value (atomic contract) ─────────
    rv = drive_mate_value_si(doc, mate_name, orig_si, mod)
    res["reverted"] = not rv.startswith("FAIL")
    if drive_err and drive_err.startswith("sense_error"):
        reason = drive_err
    elif drive_err:
        reason = f"drive_failed ({drive_err})"
    elif worsened:
        reason = "step increased interference; try direction='in'"
    else:
        reason = f"hit max_iters ({max_iters}) without clearing"
    revert_note = (
        f"reverted to {res['initial_mm']:.3f}mm"
        if res["reverted"]
        else "REVERT FAILED — model left mutated"
    )
    res["error"] = f"unresolved: {reason}; {revert_note}"
    return res
