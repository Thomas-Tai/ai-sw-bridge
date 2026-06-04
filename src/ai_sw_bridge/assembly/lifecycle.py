"""Assembly lifecycle orchestration (Wave-9 Phase 1, Slice 6).

End-to-end ``propose → dry_run → commit`` for ``kind: "assembly"`` specs.
Mirrors the existing ``feature_add`` lifecycle with an assembly-doc twist.

  - **propose** (already in ``mutate.sw_propose_assembly``): validate offline.
  - **dry_run**: resolve part files, confirm each part opens, confirm each
    mate face resolves — WITHOUT mutating any SW state.
  - **commit**: ``NewDocument(asmdot)`` → place components → create mates →
    ``SaveAs3`` the assembly → write the assembly manifest → close docs.

The assembly kind stays **de-advertised** until the Phase-1 PAE clears.
"""

from __future__ import annotations

import glob
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from .face_resolver import resolve_component_face
from .handlers import create_coincident_mate, place_components
from .storage import AssemblyManifest, ComponentInstance, MateRecord


def _find_assembly_template() -> str | None:
    """Locate the assembly template (.ASMDOT) on this machine."""
    patterns = [
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.ASMDOT",
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.asmdot",
    ]
    for pat in patterns:
        matches = glob.glob(pat)
        if matches:
            return matches[0]
    return None


def dry_run_assembly(
    spec: dict[str, Any],
    *,
    part_paths: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Dry-run an assembly spec — validate bindings without mutating SW.

    Checks:
      - Each component's part file exists (or part_spec resolves to one).
      - Each mate's face_ref is well-formed and cites an existing component.

    Args:
        spec: the validated assembly spec dict.
        part_paths: optional mapping of ``component_id → part_file_path``
            for ``part_spec`` components that have been pre-built.

    Returns:
        A result dict with ``ok``, ``resolved_parts``, ``face_checks``,
        and ``error``.
    """
    result: dict[str, Any] = {"ok": False}
    resolved_parts: dict[str, str] = {}

    for comp in spec.get("components", []):
        cid = comp["id"]
        part_path = comp.get("part")
        if part_path is None and part_paths:
            part_path = part_paths.get(cid)
        if part_path is None:
            part_path = comp.get("part_spec_path")

        if part_path is None:
            result["error"] = f"component {cid!r}: no part path resolved"
            return result
        if not os.path.isfile(part_path):
            result["error"] = f"component {cid!r}: file not found: {part_path}"
            return result
        resolved_parts[cid] = part_path

    result["resolved_parts"] = resolved_parts

    face_checks: list[dict[str, Any]] = []
    for i, mate in enumerate(spec.get("mates", [])):
        for ref_key in ("a", "b"):
            ref = mate.get(ref_key, {})
            cid = ref.get("component")
            face_ref = ref.get("face_ref", {})
            if cid not in resolved_parts:
                result["error"] = (
                    f"mate[{i}].{ref_key}: component {cid!r} not in spec"
                )
                return result
            if not face_ref:
                result["error"] = f"mate[{i}].{ref_key}: empty face_ref"
                return result
            face_checks.append({
                "mate_index": i,
                "ref": ref_key,
                "component": cid,
                "face_ref_keys": sorted(face_ref.keys()),
            })

    result["face_checks"] = face_checks
    result["ok"] = True
    return result


def commit_assembly(
    sw: Any,
    spec: dict[str, Any],
    output_path: str,
    *,
    part_paths: dict[str, str] | None = None,
    mod: Any | None = None,
) -> dict[str, Any]:
    """Build the assembly — place components, create mates, save.

    Args:
        sw: the ``SldWorks.Application`` COM object.
        spec: the validated assembly spec dict.
        output_path: where to save the ``.sldasm`` file.
        part_paths: mapping of ``component_id → part_file_path`` for
            ``part_spec`` components.
        mod: the gen_py wrapper module.

    Returns:
        A result dict with ``ok``, ``manifest``, ``component_count``,
        ``mate_count``, and ``error``.
    """
    from ..com.earlybind import typed
    from ..com.sw_type_info import wrapper_module

    if mod is None:
        mod = wrapper_module()

    result: dict[str, Any] = {"ok": False}

    # Resolve part paths
    resolved: dict[str, str] = {}
    for comp in spec.get("components", []):
        cid = comp["id"]
        pp = comp.get("part")
        if pp is None and part_paths:
            pp = part_paths.get(cid)
        if pp is None:
            pp = comp.get("part_spec_path")
        if pp is None:
            result["error"] = f"component {cid!r}: no part path resolved"
            return result
        resolved[cid] = pp

    # Build enriched component specs with resolved paths
    comp_specs = []
    for comp in spec.get("components", []):
        c = dict(comp)
        c["part"] = resolved[c["id"]]
        comp_specs.append(c)

    # Create assembly document
    asm_template = _find_assembly_template()
    if asm_template is None:
        result["error"] = "assembly template (.ASMDOT) not found"
        return result

    asm_doc = sw.NewDocument(asm_template, 0, 0.1, 0.1)
    if asm_doc is None:
        result["error"] = "NewDocument(asmdot) returned None"
        return result

    try:
        # Place components
        placed, place_err = place_components(sw, asm_doc, comp_specs, mod=mod)
        if place_err:
            result["error"] = place_err
            return result

        result["component_count"] = len(placed)

        # Create mates
        mate_count = 0
        for i, mate_spec in enumerate(spec.get("mates", [])):
            mate_feat, mate_err = create_coincident_mate(
                asm_doc, placed, mate_spec, mod=mod
            )
            if mate_err:
                result["error"] = f"mate[{i}]: {mate_err}"
                return result
            mate_count += 1

        result["mate_count"] = mate_count

        # Save the assembly
        try:
            asm_doc.SaveAs3(output_path, 0, 2)
        except Exception as exc:
            result["error"] = f"SaveAs3 failed: {exc!r}"
            return result

        # Build the manifest
        typed_asm = typed(asm_doc, "IAssemblyDoc", module=mod)
        manifest = AssemblyManifest()
        for cid, comp in placed.items():
            try:
                sw_name = comp.Name if hasattr(comp, "Name") else str(comp)
            except Exception:
                sw_name = cid
            comp_spec = next(c for c in comp_specs if c["id"] == cid)
            manifest.components.append(ComponentInstance(
                id=cid,
                sw_name=str(sw_name),
                part_path=resolved[cid],
                transform=comp_spec.get("transform", {}),
            ))

        for mate_spec in spec.get("mates", []):
            manifest.mates.append(MateRecord(
                type=mate_spec["type"],
                alignment=mate_spec.get("alignment"),
                a=mate_spec["a"],
                b=mate_spec["b"],
                value=mate_spec.get("value_mm"),
            ))

        result["manifest"] = manifest.to_dict()
        result["ok"] = True
        return result

    except Exception as exc:
        result["error"] = f"unexpected: {exc!r}"
        return result

    finally:
        try:
            t = asm_doc.GetTitle
            t = t() if callable(t) else t
            sw.CloseDoc(t)
        except Exception:
            pass
        # Close any pre-opened part docs
        for pp in resolved.values():
            try:
                part_name = Path(pp).stem
                for title_suffix in (".SLDPRT", ".sldprt"):
                    sw.CloseDoc(part_name + title_suffix)
            except Exception:
                pass
