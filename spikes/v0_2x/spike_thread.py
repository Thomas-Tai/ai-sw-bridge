"""W59 / SEAT-AUTHOR — cosmetic thread + cut thread COM-signature sourcing + effect proof.
[authored offline by W2; RUN ON A LIVE SEAT — W0 fires]

Purpose
-------
Characterize BOTH cosmetic and cut thread creation routes in one spike.
Thread is a common mfg feature, never spiked (§B #6).

O1 introspection (runs first, offline-safe on any machine with sldworks.tlb):
  * Walk ``sldworks.tlb::IFeatureManager`` for methods matching "thread" /
    "cosmetic" (case-insensitive), FUNCDESC-dump each candidate's arity.
  * Walk ``sldworks.tlb::IModelDoc2`` for the same tokens.
  * Walk ``swconst.tlb`` for feature-kind constants matching "Thread".

Two thread kinds, likely different routes:
  * **Cosmetic thread** — adds a thread annotation/callout, NO volume change.
    Known: ``swFmCosmeticThread = 29``, interface ``ICosmeticThreadFeatureData``.
    Route: ``CreateDefinition(29) → typed_qi(data, "ICosmeticThreadFeatureData")``
    → set thread params → select cylindrical face → ``CreateFeature(fd)``.
  * **Cut thread** — removes material via helical sweep cut, ΔVol < 0.
    Known: ``swFmSweepThread = 87``.
    Route: ``CreateDefinition(87)`` → probe the returned feature-data interface.
    Fallback: helix + sweep-cut recipe if CreateDefinition(87) yields None.

Fixture
-------
Cylinder (boss-extrude a circle): ⌀20 mm × 30 mm.  Provides cylindrical
faces and circular edges — the canonical thread host geometry.

Verify-the-effect (survives save→reopen):
  * cut thread       → ΔVol < 0 (material removed), persists after reopen.
  * cosmetic thread  → feature-node delta AND thread annotation present after
    reopen (cosmetic adds NO volume — node-count alone is insufficient per the
    edge_flange/draft ghost lesson; annotation check is mandatory).

Verdicts
--------
PASS    — at least one kind succeeded AND survived save→reopen.
PARTIAL — a kind created geometry/node but reopen failed, OR only one of two
          kinds succeeded.
LEAD    — targeted probes at 29/87 failed, BUT the CreateDefinition scan
          (0..130) discovered thread interfaces — retry with the discovered
          IDs (decisive: saves a seat fire).
FAIL    — both kinds failed AND scan found no thread interfaces (typelib
          absence, CreateDefinition None, zero effect, etc.).

Exit codes: PASS=0, PARTIAL=2, LEAD=3, FAIL=1.

Usage
-----
    python spikes/v0_2x/spike_thread.py --out spikes/v0_2x/_results/thread.json
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
_PKG_ROOT = _HERE.parents[2] / "src"
_V15 = _HERE.parents[1] / "v0_15"
_SPIKE_DIR = _HERE.parent
for _p in (str(_PKG_ROOT), str(_V15), str(_SPIKE_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pythoncom  # noqa: E402

from ai_sw_bridge.com.earlybind import typed, typed_qi, EarlyBindError  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.sw_com import get_sw_app  # noqa: E402

from spike_earlybind_persist import ensure_sw_module  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SW_DEFAULT_TEMPLATE_PART = 8
SLDWORKS_TLB = Path(r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\sldworks.tlb")
SWCONST_TLB = Path(r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\swconst.tlb")

FM_THREAD_TOKENS = ("thread", "cosmetic")
DOC_THREAD_TOKENS = ("thread", "cosmetic")
CONST_THREAD_TOKENS = ("Thread", "swFmThread", "swFmCosmetic", "swFmSweep")

SW_FM_COSMETIC_THREAD = 29
SW_FM_SWEEP_THREAD = 87

COSMETIC_THREAD_IFACES = (
    "ICosmeticThreadFeatureData",
    "ICosmeticThreadFeatureData2",
)

CUT_THREAD_IFACES = (
    "ISweepFeatureData",
    "ISweepFeatureData2",
    "ICutThreadFeatureData",
    "IThreadFeatureData",
)

# Full swFeatureNameID_e range ceiling (well under 130 on SW 2024).
_CREATEDEF_ID_MAX = 130

# All interfaces to QI-probe in the CreateDefinition scan.
_THREAD_QI_IFACES = COSMETIC_THREAD_IFACES + CUT_THREAD_IFACES

CYL_RADIUS_M = 0.010  # 10 mm radius → ⌀20 mm
CYL_LENGTH_M = 0.030  # 30 mm extrusion length


# ---------------------------------------------------------------------------
# VT decoder (mirror of spike_rib2 — self-contained)
# ---------------------------------------------------------------------------

_VT_NAMES = {
    0: "VT_EMPTY",
    2: "VT_I2",
    3: "VT_I4",
    4: "VT_R4",
    5: "VT_R8",
    8: "VT_BSTR",
    9: "VT_DISPATCH",
    11: "VT_BOOL",
    12: "VT_VARIANT",
    13: "VT_UNKNOWN",
    16: "VT_I1",
    17: "VT_UI1",
    19: "VT_UI4",
    24: "VT_VOID",
    26: "VT_PTR",
    27: "VT_SAFEARRAY",
}


def _vt(vt: int) -> str:
    base = vt & 0x0FFF
    flags = vt & 0xF000
    s = _VT_NAMES.get(base, f"VT_{base}")
    if flags & 0x2000:
        s = f"VT_ARRAY|{s}"
    if flags & 0x4000:
        s = f"VT_BYREF|{s}"
    return s


def _extract_vt(raw: Any) -> int:
    if isinstance(raw, tuple):
        return raw[0] if isinstance(raw[0], int) else _extract_vt(raw[0])
    return raw


def _funcdesc(info: Any, f_idx: int) -> dict[str, Any]:
    fd = info.GetFuncDesc(f_idx)
    names = info.GetNames(fd.memid)
    mname = names[0] if names else f"<memid={fd.memid}>"
    arg_vts = []
    for elem in fd.args:
        vt_val = _extract_vt(elem[0])
        arg_vts.append(_vt(vt_val))
    ret_vt = _extract_vt(fd.rettype)
    return {
        "name": mname,
        "param_names": list(names[1:]) if len(names) > 1 else [],
        "cParams": len(fd.args),
        "arg_vts": arg_vts,
        "return_vt": _vt(ret_vt),
        "invkind": fd.invkind,
    }


# ---------------------------------------------------------------------------
# O1 typelib walks
# ---------------------------------------------------------------------------


def _walk_sldworks_interface(
    iface_name: str,
    tokens: tuple[str, ...],
) -> dict[str, Any]:
    """Walk sldworks.tlb for *iface_name* and dump FUNCDESCs matching *tokens*."""
    report: dict[str, Any] = {
        "path": str(SLDWORKS_TLB),
        "loadable": False,
        "iface_found": False,
        "matches": {},
    }
    if not SLDWORKS_TLB.exists():
        report["error"] = f"sldworks.tlb not found at {SLDWORKS_TLB}"
        return report
    try:
        tlb = pythoncom.LoadTypeLib(str(SLDWORKS_TLB))
        report["loadable"] = True
    except Exception as e:
        report["error"] = f"{type(e).__name__}: {e}"
        return report

    for i in range(tlb.GetTypeInfoCount()):
        name, *_ = tlb.GetDocumentation(i)
        if name != iface_name:
            continue
        report["iface_found"] = True
        info = tlb.GetTypeInfo(i)
        ta = info.GetTypeAttr()
        for f in range(ta.cFuncs):
            try:
                fd_data = _funcdesc(info, f)
                mname_lower = fd_data["name"].lower()
                if any(t.lower() in mname_lower for t in tokens):
                    report["matches"][fd_data["name"]] = fd_data
            except Exception as e:
                report.setdefault("errors", []).append(f"f={f}: {e}")
        break

    return report


def _walk_swconst_enums(tokens: tuple[str, ...]) -> dict[str, Any]:
    """Walk swconst.tlb for feature-kind constants matching *tokens*."""
    report: dict[str, Any] = {
        "path": str(SWCONST_TLB),
        "loadable": False,
        "matches": {},
    }
    if not SWCONST_TLB.exists():
        report["error"] = f"swconst.tlb not found at {SWCONST_TLB}"
        return report
    try:
        tlb = pythoncom.LoadTypeLib(str(SWCONST_TLB))
        report["loadable"] = True
    except Exception as e:
        report["error"] = f"{type(e).__name__}: {e}"
        return report

    for i in range(tlb.GetTypeInfoCount()):
        name, *_ = tlb.GetDocumentation(i)
        info = tlb.GetTypeInfo(i)
        ta = info.GetTypeAttr()
        if ta.typekind != pythoncom.TKIND_ENUM:
            continue
        for v in range(ta.cVars):
            try:
                vd = info.GetVarDesc(v)
                mname = info.GetNames(vd.memid)[0]
                if any(t.lower() in mname.lower() for t in tokens):
                    report["matches"][mname] = {"enum": name, "value": vd.value}
            except Exception:
                continue

    return report


# ---------------------------------------------------------------------------
# Probe 0 — CreateDefinition scan (side-effect-free discovery)
# ---------------------------------------------------------------------------


def _probe_createdefinition(sw: Any, mod: Any, template: str) -> dict[str, Any]:
    """Scan CreateDefinition(id) for any return that QIs to a thread interface.

    Side-effect-free: CreateDefinition only allocates a definition object;
    CreateFeature (never called here) is what mutates the model.  If the
    expected ids (29/87) are wrong, this scan discovers the real ones.

    Mirrors spike_rib5._probe_createdefinition (W0 proven pattern).
    """
    out: dict[str, Any] = {"scanned_max_id": _CREATEDEF_ID_MAX}
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        out["error"] = "NewDocument returned None"
        return out
    try:
        fm = doc.FeatureManager
        non_none: list[dict[str, Any]] = []
        cosmetic_def_id: int | None = None
        cut_def_id: int | None = None
        for i in range(_CREATEDEF_ID_MAX + 1):
            try:
                obj = fm.CreateDefinition(i)
            except Exception:
                continue
            if obj is None:
                continue
            entry: dict[str, Any] = {"id": i, "type": type(obj).__name__}
            qi_results: dict[str, bool] = {}
            for iface in _THREAD_QI_IFACES:
                try:
                    typed_qi(obj, iface, module=mod)
                    qi_results[iface] = True
                    if iface in COSMETIC_THREAD_IFACES and cosmetic_def_id is None:
                        cosmetic_def_id = i
                    if iface in CUT_THREAD_IFACES and cut_def_id is None:
                        cut_def_id = i
                except EarlyBindError:
                    qi_results[iface] = False
                except Exception:
                    qi_results[iface] = False
            if any(qi_results.values()):
                entry["qi_match"] = {k: v for k, v in qi_results.items() if v}
            non_none.append(entry)
        out["non_none_definitions"] = non_none
        out["cosmetic_definition_id"] = cosmetic_def_id
        out["cut_definition_id"] = cut_def_id
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
    return out


# ---------------------------------------------------------------------------
# Fixture builder — cylinder
# ---------------------------------------------------------------------------


def _build_cylinder(doc: Any) -> dict[str, Any]:
    """Build a cylinder: circle on Front Plane, extruded in Z.

    Geometry: radius=CYL_RADIUS_M, length=CYL_LENGTH_M.
    Provides cylindrical faces + circular edges for thread features.
    """
    result: dict[str, Any] = {}
    try:
        doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
        sk = doc.SketchManager
        sk.InsertSketch(True)
        sk.CreateCircle(0.0, 0.0, 0.0, CYL_RADIUS_M, 0.0, 0.0)
        sk.InsertSketch(True)
        fm = doc.FeatureManager
        feat = fm.FeatureExtrusion2(
            True,
            False,
            False,
            0,
            0,
            CYL_LENGTH_M,
            0.0,
            False,
            False,
            False,
            False,
            0.0,
            0.0,
            False,
            False,
            False,
            False,
            True,
            True,
            True,
            0,
            0.0,
            False,
        )
        if feat is None or isinstance(feat, int):
            result["error"] = "cylinder FeatureExtrusion2 did not materialise"
            return result
        result["built"] = True
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


# ---------------------------------------------------------------------------
# Volume / topology measurement
# ---------------------------------------------------------------------------


def _get_bodies(doc: Any) -> list[Any]:
    try:
        pdoc = (
            doc
            if hasattr(doc, "GetBodies2")
            else typed(doc, "IPartDoc", module=wrapper_module())
        )
        bodies = pdoc.GetBodies2(0, True)
        return list(bodies) if bodies else []
    except Exception:
        return []


def _total_volume(doc: Any) -> float | None:
    bodies = _get_bodies(doc)
    if not bodies:
        return None
    total = 0.0
    for b in bodies:
        try:
            mp = b.GetMassProperties(1.0)
            if callable(mp):
                mp = mp(1.0)
            if mp is not None and len(mp) >= 4:
                total += float(mp[3])
        except Exception:
            continue
    return total if total > 0 else None


def _topo(doc: Any) -> dict[str, Any]:
    """Body count + face count + volume — cheap topology snapshot."""
    bodies = _get_bodies(doc)
    faces = 0
    for b in bodies:
        try:
            fc = b.GetFaceCount()
            faces += int(fc) if fc else 0
        except Exception:
            pass
    return {
        "body_count": len(bodies),
        "face_count": faces,
        "volume_m3": _total_volume(doc),
    }


def _count_annotations(doc: Any) -> int:
    """Count annotation objects in the feature tree."""
    count = 0
    try:
        feat = doc.FirstFeature()
    except Exception:
        return 0
    seen = 0
    while feat is not None and seen < 500:
        seen += 1
        try:
            tname = feat.GetTypeName2()
            if tname and "thread" in str(tname).lower():
                count += 1
        except Exception:
            pass
        try:
            feat = feat.GetNextFeature()
        except Exception:
            break
    return count


# ---------------------------------------------------------------------------
# Feature-node detection (thread ghost detector)
# ---------------------------------------------------------------------------


def _find_thread_feature(doc: Any) -> dict[str, Any] | None:
    """Walk the feature tree for a node whose type name contains 'thread'.

    Presence of a node with zero geometry change is the 'ghost' signature
    (feature created but no effect — per the edge_flange/draft lesson).
    """
    try:
        feat = doc.FirstFeature()
    except Exception:
        return None
    seen = 0
    while feat is not None and seen < 500:
        seen += 1
        try:
            tname = feat.GetTypeName2()
        except Exception:
            tname = None
        if tname and "thread" in str(tname).lower():
            info: dict[str, Any] = {"type_name": str(tname)}
            try:
                info["name"] = str(feat.Name)
            except Exception:
                pass
            try:
                info["suppressed"] = bool(feat.IsSuppressed())
            except Exception:
                pass
            return info
        try:
            feat = feat.GetNextFeature()
        except Exception:
            break
    return None


def _get_feature_names(doc: Any) -> list[str]:
    """Return all feature names in the tree (for delta detection)."""
    names: list[str] = []
    try:
        feat = doc.FirstFeature()
    except Exception:
        return names
    seen = 0
    while feat is not None and seen < 500:
        seen += 1
        try:
            names.append(str(feat.Name))
        except Exception:
            pass
        try:
            feat = feat.GetNextFeature()
        except Exception:
            break
    return names


# ---------------------------------------------------------------------------
# Select a cylindrical face (for thread host)
# ---------------------------------------------------------------------------


def _select_cylindrical_face(doc: Any) -> dict[str, Any]:
    """Find and select a cylindrical face via persist-reference round-trip.

    Thread features need a cylindrical face as the host.  We traverse the
    body's faces, find one whose surface is cylindrical (GetFaceCount > 0),
    and select it via the typed IEntity path.
    """
    result: dict[str, Any] = {}
    bodies = _get_bodies(doc)
    if not bodies:
        result["error"] = "no bodies found"
        return result

    mod = wrapper_module()
    for body in bodies:
        try:
            faces = body.GetFaces()
            if not faces:
                continue
        except Exception:
            continue
        for face in faces:
            try:
                fcount = face.GetFaceCount() if hasattr(face, "GetFaceCount") else None
            except Exception:
                fcount = None
            try:
                pid = face.GetPersistReference3()
                if pid is None:
                    continue
                ext = typed(doc.Extension, "IModelDocExtension", module=mod)
                resolved = ext.GetObjectByPersistReference3(pid)
                if resolved is None or (
                    isinstance(resolved, tuple) and resolved[0] is None
                ):
                    continue
                entity = resolved[0] if isinstance(resolved, tuple) else resolved
                typed_entity = typed(entity, "IEntity", module=mod)
                selected = typed_entity.Select2(False, 1)
                if selected:
                    result["selected"] = True
                    result["method"] = "persist_reference_cylindrical_face"
                    return result
            except Exception as exc:
                result["face_probe_error"] = f"{type(exc).__name__}: {exc}"
                continue

    # Fallback: SelectByID2 with coordinate-based face selection.
    try:
        ext = typed(doc.Extension, "IModelDocExtension", module=mod)
        selected = ext.SelectByID2(
            "",
            "FACE",
            CYL_RADIUS_M,
            0.0,
            CYL_LENGTH_M / 2.0,
            False,
            1,
            None,
            0,
        )
        if selected:
            result["selected"] = True
            result["method"] = "SelectByID2_coord_fallback"
            return result
    except Exception as exc:
        result["fallback_error"] = f"{type(exc).__name__}: {exc}"

    result["error"] = "could not select any cylindrical face"
    return result


# ---------------------------------------------------------------------------
# Cosmetic thread probe — CreateDefinition(29)
# ---------------------------------------------------------------------------


def _probe_cosmetic_thread(doc: Any) -> dict[str, Any]:
    """Attempt cosmetic thread via CreateDefinition(swFmCosmeticThread=29).

    Pipeline:
      1. Select cylindrical face (thread host).
      2. CreateDefinition(29) → probe for ICosmeticThreadFeatureData.
      3. If feature-data acquired: CreateFeature(fd) → check feature node.
      4. If no feature-data: record the None and the interface probe.
    """
    result: dict[str, Any] = {
        "kind": "cosmetic_thread",
        "create_definition_id": SW_FM_COSMETIC_THREAD,
    }

    topo_before = _topo(doc)
    result["topo_before"] = topo_before
    features_before = _get_feature_names(doc)
    result["feature_count_before"] = len(features_before)

    # Select cylindrical face.
    face_sel = _select_cylindrical_face(doc)
    result["face_selection"] = face_sel
    if not face_sel.get("selected"):
        result["error"] = f"face selection failed: {face_sel.get('error')}"
        return result

    fm = doc.FeatureManager
    mod = wrapper_module()

    # CreateDefinition probe.
    try:
        fd = fm.CreateDefinition(SW_FM_COSMETIC_THREAD)
        result["create_definition_return"] = str(type(fd).__name__) if fd else None
    except Exception as exc:
        result["create_definition_error"] = f"{type(exc).__name__}: {exc}"
        fd = None

    if fd is None:
        result["error"] = (
            f"CreateDefinition({SW_FM_COSMETIC_THREAD}) returned None "
            f"— swFmCosmeticThread not reachable"
        )
        return result

    # Probe the returned object's interface.
    for iface in COSMETIC_THREAD_IFACES:
        try:
            typed_fd = typed_qi(fd, iface, module=mod)
            result["typed_qi_success"] = iface
            result["typed_qi_type"] = str(type(typed_fd).__name__)
            break
        except (EarlyBindError, Exception) as exc:
            result.setdefault("typed_qi_failures", {})[iface] = str(exc)
            typed_fd = None

    # Attempt CreateFeature regardless of typed_qi outcome.
    try:
        feat = fm.CreateFeature(fd)
        result["create_feature_return"] = str(type(feat).__name__) if feat else None
    except Exception as exc:
        result["create_feature_error"] = f"{type(exc).__name__}: {exc}"
        feat = None

    doc.ForceRebuild3(False)

    # Diagnostics: feature-node detection + annotation count.
    result["thread_feature_node"] = _find_thread_feature(doc)
    topo_after = _topo(doc)
    result["topo_after"] = topo_after

    features_after = _get_feature_names(doc)
    new_features = [n for n in features_after if n not in features_before]
    result["new_features"] = new_features
    result["feature_count_after"] = len(features_after)
    result["feature_count_delta"] = len(features_after) - len(features_before)

    # Cosmetic thread: volume should NOT change; success = node + annotation.
    vol_before = topo_before["volume_m3"]
    vol_after = topo_after["volume_m3"]
    if vol_before is not None and vol_after is not None:
        delta = vol_after - vol_before
        result["delta_volume_m3"] = delta
        result["delta_volume_mm3"] = round(delta * 1e9, 2)

    result["node_created"] = result["thread_feature_node"] is not None
    result["success"] = result["node_created"] and result["feature_count_delta"] > 0

    return result


# ---------------------------------------------------------------------------
# Cut thread probe — CreateDefinition(87) / helix sweep
# ---------------------------------------------------------------------------


def _probe_cut_thread(doc: Any) -> dict[str, Any]:
    """Attempt cut thread via CreateDefinition(swFmSweepThread=87).

    Pipeline:
      1. Select cylindrical face.
      2. CreateDefinition(87) → probe the returned feature-data interface.
      3. If feature-data acquired: CreateFeature(fd) → check ΔVol < 0.
      4. Fallback: if CreateDefinition(87) → None, try a helix + sweep-cut.
    """
    result: dict[str, Any] = {
        "kind": "cut_thread",
        "create_definition_id": SW_FM_SWEEP_THREAD,
    }

    topo_before = _topo(doc)
    result["topo_before"] = topo_before
    features_before = _get_feature_names(doc)
    result["feature_count_before"] = len(features_before)

    # Select cylindrical face.
    face_sel = _select_cylindrical_face(doc)
    result["face_selection"] = face_sel
    if not face_sel.get("selected"):
        result["error"] = f"face selection failed: {face_sel.get('error')}"
        return result

    fm = doc.FeatureManager
    mod = wrapper_module()

    # CreateDefinition probe.
    try:
        fd = fm.CreateDefinition(SW_FM_SWEEP_THREAD)
        result["create_definition_return"] = str(type(fd).__name__) if fd else None
    except Exception as exc:
        result["create_definition_error"] = f"{type(exc).__name__}: {exc}"
        fd = None

    if fd is None:
        result["create_definition_none"] = True
        result["error"] = (
            f"CreateDefinition({SW_FM_SWEEP_THREAD}) returned None "
            f"— swFmSweepThread not reachable via CreateDefinition"
        )
        # Do NOT attempt a helix+sweep fallback here — that's a separate
        # spike concern.  Record the wall and let W0 decide the route.
        return result

    # Probe the returned object for known interfaces.
    sweep_ifaces = (
        "ISweepFeatureData",
        "ISweepFeatureData2",
        "ICutThreadFeatureData",
        "IThreadFeatureData",
    )
    for iface in sweep_ifaces:
        try:
            typed_fd = typed_qi(fd, iface, module=mod)
            result["typed_qi_success"] = iface
            result["typed_qi_type"] = str(type(typed_fd).__name__)
            break
        except (EarlyBindError, Exception) as exc:
            result.setdefault("typed_qi_failures", {})[iface] = str(exc)
            typed_fd = None

    # Attempt CreateFeature.
    try:
        feat = fm.CreateFeature(fd)
        result["create_feature_return"] = str(type(feat).__name__) if feat else None
    except Exception as exc:
        result["create_feature_error"] = f"{type(exc).__name__}: {exc}"
        feat = None

    doc.ForceRebuild3(False)

    # Diagnostics.
    result["thread_feature_node"] = _find_thread_feature(doc)
    topo_after = _topo(doc)
    result["topo_after"] = topo_after

    features_after = _get_feature_names(doc)
    new_features = [n for n in features_after if n not in features_before]
    result["new_features"] = new_features
    result["feature_count_after"] = len(features_after)
    result["feature_count_delta"] = len(features_after) - len(features_before)

    vol_before = topo_before["volume_m3"]
    vol_after = topo_after["volume_m3"]
    if vol_before is not None and vol_after is not None:
        delta = vol_after - vol_before
        result["delta_volume_m3"] = delta
        result["delta_volume_mm3"] = round(delta * 1e9, 2)
        result["volume_decreased"] = delta < -1e-12

    result["node_created"] = result["thread_feature_node"] is not None
    result["success"] = result.get("volume_decreased", False)

    return result


# ---------------------------------------------------------------------------
# Save → reopen verification
# ---------------------------------------------------------------------------


def _save_reopen(sw: Any, doc: Any, part_path: Path) -> dict[str, Any]:
    """Save the part and reopen; verify the thread feature survives."""
    result: dict[str, Any] = {}
    try:
        err = doc.SaveAs3(str(part_path), 0, 0)
        result["save_err"] = err
    except Exception as exc:
        result["save_exception"] = f"{type(exc).__name__}: {exc}"
        return result

    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass

    try:
        doc2 = sw.OpenDoc6(str(part_path), 1, 1, "", 0, 0)
        if isinstance(doc2, tuple):
            doc2 = doc2[0]
    except Exception as exc:
        result["reopen_exception"] = f"{type(exc).__name__}: {exc}"
        return result

    if doc2 is None:
        result["reopen"] = "None returned from OpenDoc6"
        return result

    result["topo_after_reopen"] = _topo(doc2)
    result["thread_feature_after_reopen"] = _find_thread_feature(doc2)
    result["feature_names_after_reopen"] = _get_feature_names(doc2)
    result["thread_annotation_count_after_reopen"] = _count_annotations(doc2)
    result["bodies_after_reopen"] = len(_get_bodies(doc2))
    result["reopen"] = "ok"

    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass
    return result


# ---------------------------------------------------------------------------
# Main run
# ---------------------------------------------------------------------------


def run() -> dict[str, Any]:
    result: dict[str, Any] = {"spike_id": "W59_thread", "timestamp": time.time()}

    # ── Stage 1: O1 typelib introspection ────────────────────────────────
    fm_walk = _walk_sldworks_interface("IFeatureManager", FM_THREAD_TOKENS)
    result["fm_walk"] = fm_walk

    doc_walk = _walk_sldworks_interface("IModelDoc2", DOC_THREAD_TOKENS)
    result["doc_walk"] = doc_walk

    const_walk = _walk_swconst_enums(CONST_THREAD_TOKENS)
    result["swconst_walk"] = const_walk

    fm_methods = list(fm_walk.get("matches", {}).keys())
    doc_methods = list(doc_walk.get("matches", {}).keys())
    result["fm_candidate_methods"] = fm_methods
    result["doc_candidate_methods"] = doc_methods

    const_matches = const_walk.get("matches", {})
    result["swconst_thread_values"] = {k: v for k, v in const_matches.items()}

    # ── Stage 2: connect to live SW ──────────────────────────────────────
    try:
        sw = get_sw_app()
        try:
            result["sw_revision"] = str(sw.RevisionNumber)
        except Exception:
            result["sw_revision"] = "<unreadable>"
    except Exception as exc:
        result["overall"] = "FAIL"
        result["reason"] = f"could not connect to SW: {exc!r}"
        return result

    mod = wrapper_module()
    if mod is None:
        mod, _ = ensure_sw_module()

    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    tmp_dir = Path(tempfile.gettempdir()) / "ai-sw-bridge"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    # ── Probe 0: CreateDefinition scan (side-effect-free discovery) ───────
    # If the expected ids (29/87) are wrong, this scan discovers the real
    # ones in the same fire.  Mirrors spike_rib5._probe_createdefinition.
    result["probe_0_createdefinition"] = _probe_createdefinition(sw, mod, template)

    # ── Stage 3: cosmetic thread probe (fresh doc) ───────────────────────
    cosmetic_result: dict[str, Any] = {}
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        cosmetic_result["error"] = "NewDocument returned None"
    else:
        try:
            cyl = _build_cylinder(doc)
            cosmetic_result["fixture"] = cyl
            if cyl.get("built"):
                doc.ForceRebuild3(False)
                cosmetic_result = _probe_cosmetic_thread(doc)
                cosmetic_result["fixture"] = cyl
                if cosmetic_result.get("success"):
                    part_path = tmp_dir / "spike_thread_cosmetic.sldprt"
                    cosmetic_result["save_reopen"] = _save_reopen(sw, doc, part_path)
        finally:
            try:
                sw.CloseAllDocuments(True)
            except Exception:
                pass
    result["cosmetic_thread"] = cosmetic_result

    # ── Stage 4: cut thread probe (fresh doc) ────────────────────────────
    cut_result: dict[str, Any] = {}
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        cut_result["error"] = "NewDocument returned None"
    else:
        try:
            cyl = _build_cylinder(doc)
            cut_result["fixture"] = cyl
            if cyl.get("built"):
                doc.ForceRebuild3(False)
                cut_result = _probe_cut_thread(doc)
                cut_result["fixture"] = cyl
                if cut_result.get("success"):
                    part_path = tmp_dir / "spike_thread_cut.sldprt"
                    cut_result["save_reopen"] = _save_reopen(sw, doc, part_path)
        finally:
            try:
                sw.CloseAllDocuments(True)
            except Exception:
                pass
    result["cut_thread"] = cut_result

    # ── Stage 5: overall verdict ─────────────────────────────────────────
    cosmetic_ok = cosmetic_result.get("success", False)
    cut_ok = cut_result.get("success", False)

    cosmetic_reopen = (
        cosmetic_result.get("save_reopen", {}).get("reopen") == "ok"
        and cosmetic_result.get("save_reopen", {}).get("thread_feature_after_reopen")
        is not None
    )
    cut_reopen = (
        cut_result.get("save_reopen", {}).get("reopen") == "ok"
        and cut_result.get("save_reopen", {})
        .get("topo_after_reopen", {})
        .get("volume_m3")
        is not None
    )

    if cosmetic_ok and cut_ok:
        if cosmetic_reopen and cut_reopen:
            result["overall"] = "PASS"
        else:
            result["overall"] = "PARTIAL"
            result["overall_reason"] = (
                "both kinds created features but save→reopen verification "
                f"failed (cosmetic_reopen={cosmetic_reopen}, "
                f"cut_reopen={cut_reopen})"
            )
    elif cosmetic_ok or cut_ok:
        kind = "cosmetic_thread" if cosmetic_ok else "cut_thread"
        reopen_ok = cosmetic_reopen if cosmetic_ok else cut_reopen
        if reopen_ok:
            result["overall"] = "PARTIAL"
            result["overall_reason"] = (
                f"{kind} succeeded and persisted, but the other kind failed"
            )
        else:
            result["overall"] = "PARTIAL"
            result["overall_reason"] = (
                f"{kind} created a feature but save→reopen failed; "
                f"the other kind also failed"
            )
    else:
        # Both targeted probes failed — check the scan for discovered IDs.
        scan = result.get("probe_0_createdefinition", {})
        discovered_cosmetic = scan.get("cosmetic_definition_id")
        discovered_cut = scan.get("cut_definition_id")

        if discovered_cosmetic is not None or discovered_cut is not None:
            result["overall"] = "LEAD"
            parts = []
            if discovered_cosmetic is not None:
                parts.append(f"cosmetic_definition_id={discovered_cosmetic}")
            if discovered_cut is not None:
                parts.append(f"cut_definition_id={discovered_cut}")
            result["overall_reason"] = (
                "targeted probes at 29/87 failed, BUT CreateDefinition scan "
                f"discovered thread interfaces: {', '.join(parts)} "
                "(retry with the discovered IDs)"
            )
        else:
            result["overall"] = "FAIL"
            cosmetic_node = cosmetic_result.get("node_created", False)
            cut_node = cut_result.get("node_created", False)
            cosmetic_def = cosmetic_result.get("create_definition_return")
            cut_def = cut_result.get("create_definition_return")
            if cosmetic_def is None and cut_def is None:
                result["overall_reason"] = (
                    "both CreateDefinition calls returned None AND scan found "
                    "no thread interfaces — thread features unreachable via "
                    "CreateDefinition route (escalate to legacy Insert* or "
                    "FeatureData route)"
                )
            elif cosmetic_node or cut_node:
                result["overall_reason"] = (
                    "feature node created but no geometry/annotation effect "
                    "(ghost — tune parameters or selection)"
                )
            else:
                result["overall_reason"] = (
                    "no thread feature node created by either route AND scan "
                    "found no thread interfaces — both modes fail "
                    "(bidirectional wall doctrine)"
                )

    return result


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------


def _scrub(o: Any) -> Any:
    if isinstance(o, dict):
        return {k: _scrub(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_scrub(v) for v in o]
    return o


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args()

    pythoncom.CoInitialize()
    try:
        result = run()
    finally:
        pythoncom.CoUninitialize()

    payload = json.dumps(
        _scrub(result), indent=2, default=lambda o: f"<{type(o).__name__}>"
    )
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(payload)

    return {"PASS": 0, "PARTIAL": 2, "LEAD": 3, "FAIL": 1}.get(result.get("overall"), 1)


if __name__ == "__main__":
    raise SystemExit(main())
