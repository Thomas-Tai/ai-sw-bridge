"""W59 — ``hem`` feature-add handler (registry seam).

Insert a sheet-metal hem at a selected edge via the legacy
``IFeatureManager.InsertSheetMetalHem`` method (9-param, v1).

FUNCDESC source (sldworks.tlb via pythoncom.LoadTypeLib, seat-confirmed):
    InsertSheetMetalHem(
        Type: int,              # swHemTypes_e
        Position: int,          # swHemPositionTypes_e (Inside=0, Outside=1)
        Reverse: bool,
        DLength: double,        # hem length (m); open/closed only
        DGap: double,           # gap distance (m); open only
        DAngle: double,         # hem angle (rad); tear-drop/rolled only
        DRad: double,           # hem radius (m); tear-drop/rolled only
        DMiterGap: double,      # miter gap (m)
        PCBA: CustomBendAllowance  # NULL → parent bend allowance
    ) -> Feature

CreateDefinition is E_NOINTERFACE for hem/jog/miter (W55-C proved the
wall); this handler uses the legacy Insert route exclusively.

MODE-B WALL (seat-confirmed W59):
    The legacy ``InsertSheetMetalHem`` is a mode-B wall — the call accepts
    parameters but silently returns None for all edges when PCBA is null.
    makepy mis-assigns PCBA as VT_DISPATCH (type 9) but the tlb says
    VT_PTR→IUnknown (type 26→13), causing a type-mismatch on the typed
    path. The raw ``InvokeTypes`` bypass (VT_UNKNOWN) clears the marshal
    wall but the server still no-ops. This matches the rib spike pattern
    (W53, 108 probes all None). CustomBendAllowance is a user-defined COM
    coclass that cannot be constructed from Python COM without a CLSID.
    DEFERRED until a PCBA construction route is found.

Effect verification follows W21 doctrine: face-count delta on the body
is the success gate — never report success from a non-None feature
return alone.
"""

from __future__ import annotations

from typing import Any

from ..com.earlybind import typed
from ..com.sw_type_info import wrapper_module

_SW_SOLID_BODY = 0
_HEM_V1_MEMID = 91
_HEM_V1_ARGTYPES = (
    (3, 1), (3, 1), (11, 1), (5, 1), (5, 1), (5, 1), (5, 1), (5, 1), (13, 1),
)
_IFEATURE_IID = "{83A33D38-27C5-11CE-BFD4-00400513BB57}"


def _get_bodies(doc: Any) -> list[Any] | None:
    try:
        pdoc = (
            doc if hasattr(doc, "GetBodies2")
            else typed(doc, "IPartDoc", module=wrapper_module())
        )
        bodies = pdoc.GetBodies2(_SW_SOLID_BODY, True)
        return list(bodies) if bodies is not None else []
    except Exception:
        return None


def _count_faces(bodies: list[Any]) -> int:
    total = 0
    for b in bodies:
        try:
            faces = b.GetFaces()
            total += len(list(faces)) if faces is not None else 0
        except Exception:
            pass
    return total


def _select_edge(doc: Any, edge_name: str) -> bool:
    try:
        ext = doc.Extension
        return bool(ext.SelectByID2(edge_name, "EDGE", 0, 0, 0, False, 0, None, 0))
    except Exception:
        return False


def create_hem(
    doc: Any, feature: dict, target: dict
) -> tuple[bool, str | None]:
    """Insert a sheet-metal hem at a selected edge.

    Verifies the geometric effect: face count on the body increases
    after the hem is inserted (W21 doctrine).

    ``feature`` keys
    ----------------
    hem_type : int, optional (default 1 = swHemTypeClosed)
    hem_position : int, optional (default 1 = swHemPositionTypeOutside;
        swHemPositionTypeInside=0 per sldworks.tlb FUNCDESC dump)
    reverse : bool, optional (default False)
    d_length_m : float, optional (default 0.010)
    d_gap_m : float, optional (default 0.0)
    d_angle_rad : float, optional (default 0.0)
    d_rad_m : float, optional (default 0.0)
    d_miter_gap_m : float, optional (default 0.001)

    ``target`` keys
    ---------------
    edge_name : str
        Name of the edge to hem (selected via SelectByID2 "EDGE").
    """
    hem_type = feature.get("hem_type", 1)
    hem_position = feature.get("hem_position", 1)
    reverse = bool(feature.get("reverse", False))
    d_length = float(feature.get("d_length_m", 0.010))
    d_gap = float(feature.get("d_gap_m", 0.0))
    d_angle = float(feature.get("d_angle_rad", 0.0))
    d_rad = float(feature.get("d_rad_m", 0.0))
    d_miter_gap = float(feature.get("d_miter_gap_m", 0.001))

    if not isinstance(hem_type, int) or hem_type < 0:
        return False, f"hem_type must be a non-negative int, got {hem_type!r}"
    if not isinstance(hem_position, int) or hem_position < 0:
        return False, f"hem_position must be a non-negative int, got {hem_position!r}"
    if d_length <= 0:
        return False, f"d_length_m must be positive, got {d_length!r}"

    edge_name = target.get("edge_name")
    if not edge_name:
        return False, "target must contain 'edge_name'"

    bodies_before = _get_bodies(doc)
    if bodies_before is None:
        return False, "GetBodies2 failed"
    if not bodies_before:
        return False, "document has no solid bodies"

    faces_before = _count_faces(bodies_before)

    try:
        doc.ClearSelection2(True)
    except Exception:
        pass

    if not _select_edge(doc, str(edge_name)):
        return False, f"SelectByID2 EDGE failed for {edge_name!r}"

    try:
        fm = doc.FeatureManager
        args = (
            hem_type, hem_position, reverse,
            d_length, d_gap, d_angle, d_rad, d_miter_gap,
            None,
        )
        oleobj = fm._oleobj_
        ret = oleobj.InvokeTypes(
            _HEM_V1_MEMID, 0, 1, (9, 0), _HEM_V1_ARGTYPES, *args)
        if ret is not None:
            try:
                from win32com.client import Dispatch
                feat = Dispatch(ret, "InsertSheetMetalHem", _IFEATURE_IID)
            except Exception:
                feat = ret
        else:
            feat = None
        doc.ForceRebuild3(False)
    except Exception as exc:
        return False, f"InsertSheetMetalHem failed: {exc!r}"

    if feat is None:
        return False, "InsertSheetMetalHem returned None (feature not created)"

    bodies_after = _get_bodies(doc)
    if not bodies_after:
        return False, "GetBodies2 returned nothing after InsertSheetMetalHem"

    faces_after = _count_faces(bodies_after)
    if faces_after > faces_before:
        return True, None

    return False, (
        f"hem: face count did not increase "
        f"(before={faces_before}, after={faces_after})"
    )
