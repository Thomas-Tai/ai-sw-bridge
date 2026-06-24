"""``intersect`` feature-add handler (registry seam) — the boundary-law refinement.

The Intersect feature resolves overlapping solid bodies (and, in a future scope,
surfaces/planes) into their mutual **regions** and commits a selected subset.
The post-GA singleton probe (``spikes/v0_2x/probe_intersect_feature.py``, live
SW2024 SP1, 2026-06-24) FALSIFIED the prediction that Intersect joins the
combine/split ``ret=None`` dead zone:

    PreIntersect2(False, 0)      -> 3 regions (tuple, non-null)  [OOP hand-back]
    PostIntersect(None, F, F)    -> real 'Sculpt' Feature, solid bodies 2 -> 3

**Why it materializes (the law refinement, not a break):** combine/split are
SINGLE-CALL — the kernel solves the region topology internally and commits in one
shot, handing nothing back -> ``ret=None`` wall.  Intersect is TWO-PHASE:
``PreIntersect2`` *returns the computed region list to the caller*, then
``PostIntersect`` takes the caller's exclusion subset.  That explicit hand-back is
the materialize-class "explicit-input" signature.  **The two-phase API contract is
the discriminator, not the boolean nature of the op.**

**Reflected sig** (docs/sw_api_full.md, IFeatureManager @ 32.1.0.123)::

    PreIntersect2(CapPlanar:Boolean, RegionType:swRegionType_e) -> Object  (regions)
    PostIntersect(IntersectionsToExclude:Object, Merge:Boolean,
                  Consume:Boolean) -> Feature

``swRegionType_e``: Margins=0 (used here), Sheet=1.

**Binding:** unlike spiral/helix, NONE of these calls carry a
``VARIANT(VT_DISPATCH, None)`` ICallout, so the typed transaction proxy
(``mutate._open_doc_typed``) marshals them natively — the probe drove a
``typed(FeatureManager, 'IFeatureManager')`` proxy directly.  No ``_latebound``
re-wrap is needed (that seam exists only for the SelectByID2 callout trap).  The
typed ``IFeatureManager`` is the InsertScale-proven caller.

**Selection (IBody2.Select doctrine):** each target body is selected with the
body's OWN native ``IBody2.Select(Append, 0)`` — IBody2 is NOT IEntity
(``select_entity``/``IEntity.Select2`` return False on a body; W68 seat finding).
First body ``Append=False``, the rest ``Append=True``.

**Verify-the-EFFECT (BOOLEAN_INTERSECT gate):** success = a real ``Sculpt`` node
materialized AND the solid topology changed (body-count delta OR
total-volume delta).  A non-None Feature ALONE is the W21/W42 ghost trap.  Volume
is read PER-BODY (``IBody2.GetMassProperties[3]`` via ``verify.solid_volume_mm3``),
NOT the doc-level ``Extension.CreateMassProperty`` that returned null in the probe.

**v1 scope:** multibody solid intersect (>=2 solid bodies), ``merge`` flag, and an
``exclude_regions`` index list (indices into the kernel-computed region list).
Surfaces/planes as intersect tools, and the ``consume`` knob, are future scope
(``consume`` is held at the probe-proven ``False``).
"""

from __future__ import annotations

import logging
from typing import Any

import pythoncom
from win32com.client import VARIANT

from ..com.earlybind import typed, typed_qi
from ..com.sw_type_info import wrapper_module
from ..sw_com import resolve
from . import verify

logger = logging.getLogger("ai_sw_bridge.features.intersect")

# seat-proven 2026-06-24 (spike_intersect_pae GREEN): 2 overlapping boxes ->
# PreIntersect2 returns 3 regions, PostIntersect materializes a 'Sculpt' feature,
# solid bodies 2 -> 3, total volume 48000 -> 40000 mm3 (Δ = -8000, the de-double-
# counted overlap); merge=True fuses 2 -> 1 at the union volume. Two-phase
# Pre->Post = boundary-law MATERIALIZE (not the combine/split ret=None wall).
SPIKE_STATUS = "GREEN"

VERIFY_CLASS = verify.FeatureClass.BOOLEAN_INTERSECT

# swRegionType_e.swMargins — the region partition the probe proved (3 regions).
_SW_REGION_MARGINS = 0
# PostIntersect Consume arg — held at the probe-proven value (not yet a knob).
_CONSUME = False
# Sculpt is the kernel's internal type-name for an Intersect feature node.
_SCULPT_TOKEN = ("Sculpt",)


def _fm(doc: Any) -> Any:
    """The typed ``IFeatureManager`` (the Pre/PostIntersect caller).

    The probe drove ``typed(FeatureManager, 'IFeatureManager')`` directly; the
    raw late-bound ``doc.FeatureManager`` is the fallback (and the seam offline
    tests monkeypatch)."""
    try:
        return typed_qi(
            resolve(doc, "FeatureManager"), "IFeatureManager", module=wrapper_module()
        )
    except Exception as e:  # pragma: no cover - exercised only on a live seat
        logger.warning("[intersect] typed FeatureManager QI failed (%r); using raw", e)
        return doc.FeatureManager


def _select_bodies(doc: Any, body_names: list[str] | None) -> tuple[int, str | None]:
    """Select the target solid bodies via ``IBody2.Select`` (first Append=False).

    Returns ``(selected_count, error)``.  ``body_names`` ``None``/empty selects
    ALL solid bodies (the multibody-part default).  IBody2 is NOT IEntity — the
    whole-body select is the body's OWN native ``Select`` (W68 seat finding).
    """
    sols = verify.bodies(doc, verify.SW_SOLID_BODY, False)
    if not sols:
        return 0, "document has no solid bodies to intersect"

    targets: list[Any]
    if body_names:
        by_name: dict[str, Any] = {}
        for b in sols:
            try:
                nm = b.Name
                nm = nm() if callable(nm) else nm
            except Exception:
                nm = None
            if nm is not None:
                by_name[str(nm)] = b
        missing = [n for n in body_names if n not in by_name]
        if missing:
            return 0, f"body_names not found: {missing} (have {sorted(by_name)})"
        targets = [by_name[n] for n in body_names]
    else:
        targets = list(sols)

    try:
        doc.ClearSelection2(True)
    except Exception as e:
        logger.warning("[intersect] ClearSelection2 RAISED: %r", e)

    selected = 0
    for i, body in enumerate(targets):
        try:
            tb = typed(body, "IBody2", module=wrapper_module())
        except Exception:
            tb = body  # raw fallback (scale proves raw IBody2.Select works too)
        try:
            if bool(tb.Select(i != 0, 0)):
                selected += 1
            else:
                logger.warning("[intersect] IBody2.Select(append=%s) -> False", i != 0)
        except Exception as e:
            logger.warning("[intersect] IBody2.Select RAISED: %r", e)
    return selected, None


def _exclusion_arg(regions: Any, exclude_regions: list[int]) -> Any:
    """Build the ``IntersectionsToExclude`` arg for ``PostIntersect``.

    Empty exclusion -> ``None`` (the probe-proven keep-all-regions form).  A
    non-empty list -> a ``VARIANT(VT_ARRAY|VT_DISPATCH, [...])`` of the region
    objects at the requested indices (same marshaling class as the structural-
    weldment segment arrays).  Indices are validated against the region count by
    the caller BEFORE this is reached.
    """
    if not exclude_regions:
        return None
    region_list = list(regions) if isinstance(regions, (list, tuple)) else [regions]
    picked = [region_list[i] for i in exclude_regions]
    return VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, picked)


def create_intersect(
    doc: Any,
    feature: dict,
    target: dict,
) -> tuple[bool, str | None]:
    """Intersect overlapping solid bodies into their mutual regions.

    Fail-closed: returns ``(False, reason)`` on any failure; never raises.

    ``feature`` keys
        exclude_regions : list[int] — 0-based indices into the kernel-computed
                                      region list to discard (default [] = keep
                                      all regions).
        merge           : bool      — fuse the kept regions into one body
                                      (default False = keep regions separate).
        cap_planar      : bool      — PreIntersect2 CapPlanar arg (default False).

    ``target`` keys
        body_names : list[str] — optional; the solid bodies to intersect
                                 (default: ALL solid bodies in the part).
    """
    if not isinstance(feature, dict):
        return False, "feature must be a dict"
    if not isinstance(target, dict):
        return False, "target must be a dict"

    exclude_regions = feature.get("exclude_regions", [])
    if not isinstance(exclude_regions, (list, tuple)) or any(
        isinstance(i, bool) or not isinstance(i, int) for i in exclude_regions
    ):
        return False, "exclude_regions must be a list of integer indices"
    exclude_regions = list(exclude_regions)

    merge = bool(feature.get("merge", False))
    cap_planar = bool(feature.get("cap_planar", False))

    body_names = target.get("body_names")
    if body_names is not None and (
        not isinstance(body_names, (list, tuple))
        or any(not isinstance(n, str) for n in body_names)
    ):
        return False, "target.body_names must be a list of body-name strings"
    body_names = list(body_names) if body_names else None

    count_before = verify.solid_body_count(doc)
    if count_before < 2:
        return False, (
            f"intersect needs >=2 solid bodies, found {count_before} "
            "(v1 scope = multibody solid intersect)"
        )
    if body_names is not None and len(body_names) < 2:
        return False, "target.body_names must name >=2 bodies for intersect"

    vol_before = verify.solid_volume_mm3(doc)
    sculpt_before = verify.count_nodes_by_type(doc, _SCULPT_TOKEN, match="exact")

    selected, sel_err = _select_bodies(doc, body_names)
    if sel_err:
        return False, sel_err
    if selected < 2:
        return False, (
            f"could not select >=2 target bodies (selected {selected}) — "
            "IBody2.Select doctrine failure"
        )

    fm = _fm(doc)

    # Phase 1: compute the mutual regions (the OOP hand-back witness).
    try:
        regions = fm.PreIntersect2(cap_planar, _SW_REGION_MARGINS)
    except Exception as exc:
        return False, f"PreIntersect2 raised: {exc!r}"
    region_list = (
        list(regions)
        if isinstance(regions, (list, tuple))
        else ([regions] if regions else [])
    )
    if not region_list:
        return False, (
            "PreIntersect2 returned no regions — the bodies do not overlap, or "
            "the kernel refused the partition (no intersect feature to commit)"
        )

    # Validate exclusion indices against the actual region count.
    n_regions = len(region_list)
    bad = [i for i in exclude_regions if not (0 <= i < n_regions)]
    if bad:
        return False, (
            f"exclude_regions {bad} out of range — PreIntersect2 computed "
            f"{n_regions} regions (valid indices 0..{n_regions - 1})"
        )
    if len(exclude_regions) >= n_regions:
        return False, (
            f"exclude_regions discards all {n_regions} regions — nothing would "
            "remain to commit"
        )

    excl = _exclusion_arg(region_list, exclude_regions)

    # Phase 2: commit the selected regions into a Sculpt feature.
    try:
        fm.PostIntersect(excl, merge, _CONSUME)
    except Exception as exc:
        return False, f"PostIntersect raised: {exc!r}"

    try:
        doc.ForceRebuild3(False)
    except Exception:
        pass

    sculpt_after = verify.count_nodes_by_type(doc, _SCULPT_TOKEN, match="exact")
    node_materialized = (sculpt_after - sculpt_before) >= 1
    count_after = verify.solid_body_count(doc)
    vol_after = verify.solid_volume_mm3(doc)
    d_count = count_after - count_before
    d_vol = vol_after - vol_before

    if verify.gate_boolean_intersect(node_materialized, d_count, d_vol):
        return True, (
            f"intersect created ({n_regions} regions, excluded "
            f"{len(exclude_regions)}, merge={merge}; solid bodies "
            f"{count_before}→{count_after}, vol {vol_before:.3f}→{vol_after:.3f} "
            f"mm3, ΔVol={d_vol:+.3f})"
        )
    return False, (
        f"PostIntersect called without exception but no real intersect "
        f"materialized (Sculpt node={node_materialized}, solid bodies "
        f"{count_before}→{count_after}, ΔVol={d_vol:+.3f}) — ghost, not a feature"
    )


# Registration is via the sanctioned ``_register_lane`` gate in
# ``features/__init__.py`` — UNFIRED until the seat PAE flips SPIKE_STATUS=GREEN.
