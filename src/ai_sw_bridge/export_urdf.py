"""URDF export orchestrator — W78 (static CAD → robotics simulation bridge).

Composes shipped primitives into a single read-only export verb that turns a
SOLIDWORKS assembly into a Unified Robot Description Format (URDF) package for
ROS / dynamic simulation:

  - per-component mass / CoM / inertia tensor  → ``observe_inertia._sw_get_inertia_impl``
    (+ a direct ``IMassProperty2.Mass`` read). Extracts cleanly per component via
    ``IComponent2.GetModelDoc2`` with NO isolate maneuver. The inertia tensor is
    the eigen-safe one (the unreachable ``PrincipalAxesOfInertia`` PROPGET is
    bypassed upstream).
  - per-component collision/visual mesh         → ``export.dispatch.export_all``
    (the shipped STL exporter), one ``meshes/<part>.stl`` per unique part file.
  - per-component placement (joint origin)      → ``observe_bbox._read_component_transform``
    (the W52-B ArrayData→row-major reader, metres).

TWO-PHASE by necessity (W78 co-residency lock, seat-proven): while the parent
assembly is open, ``OpenDoc6`` of a member part returns the shared in-context
instance, which has no standalone tessellation context — ``SaveAs3``-STL writes
a 0-byte ghost. So Phase 1 reads ALL contextual data (mass/transform/path) with
the assembly live; the session is then flushed (``CloseAllDocuments``, COM
handles dropped); Phase 2 reopens each part STANDALONE and exports its mesh into
a fresh tessellation context. Lightweight-resolution and ActivateDoc3 were both
falsified as causes — co-residency was the discriminator.

V1 joint model: a massless ``base_link`` root with one ``fixed`` joint per
component, positioned by the component's assembly transform (a star topology —
valid URDF, no matrix inversion). Kinematic mate→revolute/prismatic mapping is a
deferred V2 lane; the directive explicitly green-lit fixed-for-V1.

READ-ONLY (selection-free interrogation + file writes to an output dir); it does
not mutate the SW model. CLI-exposed; also MCP-eligible, but file-writing export
verbs follow the existing ``ai-sw-export`` CLI convention.
"""

from __future__ import annotations

import gc
import math
from pathlib import Path
from typing import Any

from .com.earlybind import typed
from .com.sw_type_info import wrapper_module
from .observe_bbox import _read_component_transform
from .observe_inertia import _sw_get_inertia_impl
from .sw_com import SW_DOC_ASSEMBLY, SW_DOC_PART, get_sw_app, resolve

# swOpenDocOptions_Silent — open the part standalone without UI prompts.
_SW_OPEN_SILENT = 1

# ── Pure helpers (no COM; fully offline-testable) ───────────────────────────


def _f(v: Any) -> str:
    """Format a float for URDF: fixed enough precision, no needless noise."""
    try:
        return f"{float(v):.10g}"
    except (TypeError, ValueError):
        return "0"


def sanitize_link_name(raw: str, used: set[str] | None = None) -> str:
    """Make a URDF-safe, unique link name from a component name.

    Component names like ``base-1`` / ``arm<2>`` carry chars URDF / ROS dislike;
    map every non-alphanumeric run to ``_`` and de-duplicate against *used*.
    """
    out = []
    for ch in str(raw):
        out.append(ch if (ch.isalnum() or ch == "_") else "_")
    name = "".join(out).strip("_") or "link"
    if name[0].isdigit():
        name = "link_" + name
    if used is not None:
        base, n = name, 1
        while name in used:
            n += 1
            name = f"{base}_{n}"
        used.add(name)
    return name


def rotmat_to_rpy(t: list[float]) -> tuple[float, float, float]:
    """Extract URDF roll-pitch-yaw from a 16-elem row-major transform.

    URDF rpy is the fixed-axis convention ``R = Rz(yaw)·Ry(pitch)·Rx(roll)``.
    """
    r00, _, _ = t[0], t[1], t[2]
    r10, r11, r12 = t[4], t[5], t[6]
    r20, r21, r22 = t[8], t[9], t[10]
    sy = math.sqrt(r00 * r00 + r10 * r10)
    if sy > 1e-9:
        roll = math.atan2(r21, r22)
        pitch = math.atan2(-r20, sy)
        yaw = math.atan2(r10, r00)
    else:  # gimbal lock (pitch ≈ ±90°)
        roll = math.atan2(-r12, r11)
        pitch = math.atan2(-r20, sy)
        yaw = 0.0
    return roll, pitch, yaw


def link_xml(
    name: str,
    mass_kg: float,
    com_m: list[float],
    tensor: list[list[float]],
    mesh_rel: str,
) -> str:
    """Build a URDF ``<link>`` with inertial + visual + collision.

    ``com_m`` and ``tensor`` are in the link (= component part) frame; the mesh
    is exported in that same frame, so visual/collision origins are identity and
    the inertial origin carries the CoM offset. Inertia (kg·m²) is about the CoM.
    """
    cx, cy, cz = (com_m + [0.0, 0.0, 0.0])[:3]
    ixx, ixy, ixz = tensor[0][0], tensor[0][1], tensor[0][2]
    iyy, iyz = tensor[1][1], tensor[1][2]
    izz = tensor[2][2]
    return (
        f'  <link name="{name}">\n'
        f"    <inertial>\n"
        f'      <origin xyz="{_f(cx)} {_f(cy)} {_f(cz)}" rpy="0 0 0"/>\n'
        f'      <mass value="{_f(mass_kg)}"/>\n'
        f'      <inertia ixx="{_f(ixx)}" ixy="{_f(ixy)}" ixz="{_f(ixz)}"'
        f' iyy="{_f(iyy)}" iyz="{_f(iyz)}" izz="{_f(izz)}"/>\n'
        f"    </inertial>\n"
        f"    <visual>\n"
        f'      <origin xyz="0 0 0" rpy="0 0 0"/>\n'
        f'      <geometry><mesh filename="{mesh_rel}"/></geometry>\n'
        f"    </visual>\n"
        f"    <collision>\n"
        f'      <origin xyz="0 0 0" rpy="0 0 0"/>\n'
        f'      <geometry><mesh filename="{mesh_rel}"/></geometry>\n'
        f"    </collision>\n"
        f"  </link>\n"
    )


def joint_xml(
    name: str,
    parent: str,
    child: str,
    xyz: tuple[float, float, float],
    rpy: tuple[float, float, float],
) -> str:
    """Build a V1 ``fixed`` URDF ``<joint>`` placing *child* at *xyz/rpy*."""
    x, y, z = xyz
    r, p, yw = rpy
    return (
        f'  <joint name="{name}" type="fixed">\n'
        f'    <parent link="{parent}"/>\n'
        f'    <child link="{child}"/>\n'
        f'    <origin xyz="{_f(x)} {_f(y)} {_f(z)}" rpy="{_f(r)} {_f(p)} {_f(yw)}"/>\n'
        f"  </joint>\n"
    )


def assemble_urdf(robot_name: str, links_xml: list[str], joints_xml: list[str]) -> str:
    """Wrap link + joint fragments into a complete URDF document."""
    body = "".join(links_xml) + "".join(joints_xml)
    return (
        '<?xml version="1.0"?>\n'
        f'<robot name="{robot_name}">\n'
        f"{body}"
        f"</robot>\n"
    )


# ── Seat-bound extraction ───────────────────────────────────────────────────


def _model_doc_of(comp: Any, mod: Any) -> Any | None:
    """IComponent2.GetModelDoc2 — late-bound first, typed fallback (W52-B)."""
    try:
        return comp.GetModelDoc2()
    except Exception:
        try:
            return typed(comp, "IComponent2", module=mod).GetModelDoc2()
        except Exception:
            return None


def _read_mass_kg(part_doc: Any, mod: Any) -> float | None:
    """Read Mass (kg) off the part-doc's IMassProperty2 (late-bound proxy)."""
    try:
        ext = part_doc.Extension
        mp = typed(ext, "IModelDocExtension", module=mod).CreateMassProperty
        if callable(mp):
            mp = mp()
        if mp is None:
            return None
        return float(resolve(mp, "Mass"))
    except Exception:
        return None


def _extract_link_data(comp: Any, used: set[str], mod: Any) -> dict[str, Any]:
    """PHASE 1 (assembly OPEN): read a component's contextual data — no mesh.

    Captures everything that only exists while the assembly is live: the
    component name, mass / CoM / inertia tensor (the eigen-safe one), the world
    transform (joint origin), and the absolute ``.sldprt`` path. The STL mesh is
    deliberately NOT exported here — see ``_export_part_stl`` and the two-phase
    note on ``export_urdf``. Returns a pure-data record (no live COM handles) so
    the caller can drop the assembly context cleanly before Phase 2.
    """
    try:
        raw_name = resolve(comp, "Name2")
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"Name2 failed: {exc!r}"}
    name = sanitize_link_name(str(raw_name), used)
    rec: dict[str, Any] = {"ok": False, "name": name, "raw_name": str(raw_name)}

    part_doc = _model_doc_of(comp, mod)
    if part_doc is None:
        rec["error"] = "GetModelDoc2 returned None (suppressed?)"
        return rec

    inert = _sw_get_inertia_impl(part_doc)
    if not inert.get("ok") or inert.get("inertia_tensor_kg_m2") is None:
        rec["error"] = f"inertia read failed: {inert.get('error')}"
        return rec
    mass = _read_mass_kg(part_doc, mod)
    if mass is None:
        rec["error"] = "mass read failed"
        return rec

    part_path = None
    try:
        part_path = resolve(part_doc, "GetPathName")
    except Exception:  # noqa: BLE001
        part_path = None
    if not part_path:
        rec["error"] = "GetPathName empty (unsaved part?)"
        return rec

    transform = _read_component_transform(comp, mod) or [
        1,
        0,
        0,
        0,
        0,
        1,
        0,
        0,
        0,
        0,
        1,
        0,
        0,
        0,
        0,
        1,
    ]
    com_mm = inert.get("center_of_mass_mm") or [0.0, 0.0, 0.0]
    rec.update(
        {
            "ok": True,
            "mass_kg": mass,
            "com_m": [float(c) / 1000.0 for c in com_mm],
            "tensor": inert["inertia_tensor_kg_m2"],
            "xyz": (transform[3], transform[7], transform[11]),
            "rpy": rotmat_to_rpy(transform),
            "part_path": str(part_path),
        }
    )
    return rec


def _export_part_stl(
    sw: Any,
    part_path: str,
    stl_name: str,
    meshes_dir: Path,
    binary_stl: bool,
    mod: Any,
) -> tuple[bool, str | None]:
    """PHASE 2 (assembly CLOSED): export one part file's mesh, standalone.

    Co-residency lock (seat-proven, W78): while the parent assembly is open,
    ``OpenDoc6`` of a member part returns the shared in-context instance, which
    has no standalone tessellation context — ``SaveAs3``-STL silently writes a
    0-byte ghost (NoError). Once the assembly is closed, a FRESH standalone open
    tessellates cleanly. Lightweight-resolution and ActivateDoc3 were both
    falsified as causes; co-residency was the discriminator. So this runs only
    after the caller has flushed the session. Each part is flushed again on the
    way out so the next iteration opens fresh.
    """
    from .client import SolidWorksClient
    from .export.dispatch import ExportRequest

    if not Path(str(part_path)).exists():
        return False, f"part file missing on disk: {part_path!r}"
    try:
        tsw = typed(sw, "ISldWorks", module=mod)
        opened_doc = tsw.OpenDoc6(
            str(part_path), SW_DOC_PART, _SW_OPEN_SILENT, "", 0, 0
        )
        opened_doc = opened_doc[0] if isinstance(opened_doc, tuple) else opened_doc
    except Exception as exc:  # noqa: BLE001
        return False, f"standalone OpenDoc6 raised: {exc!r}"
    if opened_doc is None:
        return False, f"standalone OpenDoc6 returned None for {part_path}"

    reqs = [
        ExportRequest(
            format="stl", output_dir=meshes_dir, filename=stl_name, binary=binary_stl
        )
    ]
    try:
        exp = SolidWorksClient().export.run(opened_doc, reqs, stl_name)
    except Exception as exc:  # noqa: BLE001
        exp = None
        err = f"export raised: {exc!r}"
    else:
        err = (
            None
            if (exp and exp[0].ok)
            else (exp[0].error if exp else "no export result")
        )
    finally:
        # Flush this part so the next standalone open is fresh; CloseAllDocuments
        # (not CloseDoc) — single-doc close mid-session corrupts the COM channel.
        try:
            sw.CloseAllDocuments(True)
        except Exception:  # noqa: BLE001
            pass

    return (err is None), err


def export_urdf(
    asm_doc: Any,
    output_dir: Any,
    *,
    robot_name: str = "robot",
    binary_stl: bool = True,
    base_link_name: str = "base_link",
    mod: Any = None,
) -> dict[str, Any]:
    """Export a SOLIDWORKS assembly to a URDF package (W78).

    Writes ``<output_dir>/<robot_name>.urdf`` plus one ``meshes/<link>.stl`` per
    component. Each component becomes a URDF ``<link>`` (inertial + visual +
    collision) fixed-jointed to a massless ``base_link`` root at its assembly
    pose. Assembly documents only; fail-closed on parts/drawings.

    Returns ``{ok, error, robot_name, urdf_path, mesh_dir, links:[...],
    joints:[...], warnings:[...]}``.
    """
    result: dict[str, Any] = {
        "ok": False,
        "error": None,
        "robot_name": robot_name,
        "urdf_path": None,
        "mesh_dir": None,
        "links": [],
        "joints": [],
        "warnings": [],
        "opened_parts": [],
    }

    if not str(robot_name).strip():
        result["error"] = "robot_name must be non-empty"
        return result
    try:
        out_dir = Path(output_dir)
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"invalid output_dir: {exc!r}"
        return result

    if mod is None:
        mod = wrapper_module()

    # ── Fail-closed: assembly only ───────────────────────────────────────
    try:
        doc_type = resolve(asm_doc, "GetType")
        if callable(doc_type):
            doc_type = doc_type()
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"doc.GetType failed: {exc!r}"
        return result
    if doc_type != SW_DOC_ASSEMBLY:
        result["error"] = (
            f"URDF export requires an assembly document (got type {doc_type})"
        )
        return result

    try:
        asm_typed = typed(asm_doc, "IAssemblyDoc", module=mod)
        comps = asm_typed.GetComponents(True)
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"GetComponents failed: {exc!r}"
        return result
    if comps is None:
        result["error"] = "assembly has no components"
        return result
    if not isinstance(comps, (list, tuple)):
        comps = (comps,)
    if len(comps) == 0:
        result["error"] = "assembly has no components"
        return result

    meshes_dir = (out_dir / "meshes").resolve()
    meshes_dir.mkdir(parents=True, exist_ok=True)
    result["mesh_dir"] = str(meshes_dir)

    # ── PHASE 1 (assembly OPEN): contextual data acquisition ─────────────
    # Read every component's mass/CoM/inertia, world transform, and .sldprt
    # path while the assembly is live. NO STL here — the part B-rep can't
    # tessellate standalone until the co-residency lock is released (W78).
    used: set[str] = set()
    records = [_extract_link_data(c, used, mod) for c in comps]

    # ── TRANSITION: drop COM handles, then flush the session ─────────────
    # Release every live pointer to the assembly / components so SOLIDWORKS can
    # fully unload the co-residency lock; only then will a standalone part open
    # build a fresh tessellation context.
    del comps, asm_typed
    gc.collect()
    try:
        sw = get_sw_app()
        sw.CloseAllDocuments(True)
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"session flush (CloseAllDocuments) failed: {exc!r}"
        return result
    gc.collect()

    # ── PHASE 2 (assembly CLOSED): isolated mesh generation ──────────────
    # One STL per UNIQUE part file (instances of the same part share a mesh).
    exported: list[str] = []
    mesh_by_path: dict[str, str | None] = {}
    mesh_used: set[str] = set()
    for r in records:
        if not r.get("ok"):
            continue
        pp = r.get("part_path")
        if pp not in mesh_by_path:
            stem = sanitize_link_name(Path(str(pp)).stem, mesh_used)
            ok, err = _export_part_stl(sw, str(pp), stem, meshes_dir, binary_stl, mod)
            mesh_by_path[pp] = f"meshes/{stem}.stl" if ok else None
            if ok:
                exported.append(str(pp))
            else:
                r["stl_err"] = err
        mesh_rel = mesh_by_path[pp]
        if mesh_rel is None:
            r["ok"] = False
            r["error"] = f"STL export failed: {r.get('stl_err')}"
        else:
            r["mesh_rel"] = mesh_rel
            r["stl_ok"] = True
    result["opened_parts"] = exported

    usable = [r for r in records if r.get("ok")]
    for r in records:
        if not r.get("ok"):
            result["warnings"].append(
                f"component {r.get('raw_name', r.get('name'))!r} skipped: {r.get('error')}"
            )
    if not usable:
        result["error"] = "no usable components (all failed mass-props/mesh extraction)"
        return result

    # ── Build URDF: massless base_link + fixed joint per component ────────
    base = sanitize_link_name(base_link_name)
    links_xml = [f'  <link name="{base}"/>\n']
    joints_xml = []
    for r in usable:
        links_xml.append(
            link_xml(r["name"], r["mass_kg"], r["com_m"], r["tensor"], r["mesh_rel"])
        )
        joints_xml.append(
            joint_xml(f"{base}_to_{r['name']}", base, r["name"], r["xyz"], r["rpy"])
        )
        result["links"].append(
            {
                "name": r["name"],
                "mass_kg": r["mass_kg"],
                "com_m": r["com_m"],
                "mesh": r["mesh_rel"],
            }
        )
        result["joints"].append(
            {
                "name": f"{base}_to_{r['name']}",
                "parent": base,
                "child": r["name"],
                "type": "fixed",
                "xyz": list(r["xyz"]),
                "rpy": list(r["rpy"]),
            }
        )

    urdf = assemble_urdf(robot_name, links_xml, joints_xml)
    urdf_path = (out_dir / f"{robot_name}.urdf").resolve()
    try:
        urdf_path.write_text(urdf, encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"failed to write URDF: {exc!r}"
        return result

    result["urdf_path"] = str(urdf_path)
    result["ok"] = True
    return result
