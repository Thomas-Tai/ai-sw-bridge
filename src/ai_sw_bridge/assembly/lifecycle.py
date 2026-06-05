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
from .handlers import create_mate, place_components
from .storage import AssemblyManifest, ComponentInstance, sha256_of_file


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


def _load_part_spec(spec_path: str) -> dict[str, Any]:
    """Load + parse a part spec JSON file.

    Raises ``FileNotFoundError`` for a missing file and ``ValueError`` on
    JSON or schema/validation errors. Does NOT touch SW — pure offline
    validation via :func:`ai_sw_bridge.spec.validator.validate`.
    """
    import json

    from ..spec.validator import ValidationError as _SpecValidationError
    from ..spec.validator import validate as _spec_validate

    p = Path(spec_path)
    if not p.is_file():
        raise FileNotFoundError(f"part_spec file not found: {spec_path}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"part_spec {spec_path!r}: invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(
            f"part_spec {spec_path!r}: top-level value must be an object"
        )
    try:
        _spec_validate(data, spec_path=p)
    except _SpecValidationError as exc:
        raise ValueError(
            f"part_spec {spec_path!r}: validation failed: {exc}"
        ) from exc
    return data


def _build_part_spec(
    part_spec: dict[str, Any],
    save_as: str,
) -> dict[str, Any]:
    """Build a validated part spec via ``spec.builder.build`` and SaveAs3.

    The build runs on the live SW session acquired internally by
    :func:`ai_sw_bridge.spec.builder.build` (no SW arg is threaded —
    ``get_sw_app()`` is the canonical seam). Returns a result dict with
    ``ok``, ``save_as``, ``save_as_verified``, and ``error``.
    """
    from ..spec.builder import BuildResult, build as _part_build

    out: dict[str, Any] = {"ok": False, "save_as": save_as}
    try:
        br: BuildResult = _part_build(
            part_spec,
            save_as=save_as,
            save_format="current",
            no_dim=True,
        )
    except Exception as exc:
        out["error"] = f"build raised: {exc!r}"
        return out

    out["build_ok"] = bool(br.ok)
    out["save_as_verified"] = br.save_as_verified
    out["features_built"] = list(br.features_built)
    if br.error:
        out["error"] = br.error
    if not br.ok:
        return out
    if not os.path.isfile(save_as):
        out["error"] = f"build reported ok but {save_as!r} not on disk"
        return out
    out["ok"] = True
    return out


def _temp_part_path(component_id: str) -> str:
    """Stable per-component temp .sldprt path for build-then-place."""
    return os.path.join(
        tempfile.gettempdir(),
        f"asm_parts_{int(time.time())}_{component_id}.SLDPRT",
    )


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
    part_spec_validated: dict[str, str] = {}
    sources: dict[str, str] = {}

    for comp in spec.get("components", []):
        cid = comp["id"]
        part_path = comp.get("part")
        source = "part" if part_path else None
        if part_path is None and part_paths:
            pp = part_paths.get(cid)
            if pp is not None:
                part_path = pp
                source = "part_paths"
        if part_path is None:
            psp = comp.get("part_spec_path")
            if psp is not None:
                part_path = psp
                source = "part_spec_path"

        if part_path is not None:
            if not os.path.isfile(part_path):
                result["error"] = (
                    f"component {cid!r}: file not found: {part_path}"
                )
                return result
            resolved_parts[cid] = part_path
            sources[cid] = source or "part"
            continue

        # No override — the component cites `part_spec`. Validate the
        # spec file offline (no build, no SW).
        spec_path = comp.get("part_spec")
        if spec_path is None:
            result["error"] = f"component {cid!r}: no part path resolved"
            return result
        try:
            _load_part_spec(spec_path)
        except (FileNotFoundError, ValueError) as exc:
            result["error"] = f"component {cid!r}: {exc}"
            return result
        part_spec_validated[cid] = spec_path
        sources[cid] = "part_spec"

    result["resolved_parts"] = resolved_parts
    result["part_spec_validated"] = part_spec_validated
    result["sources"] = sources

    face_checks: list[dict[str, Any]] = []
    known_components = set(resolved_parts) | set(part_spec_validated)
    for i, mate in enumerate(spec.get("mates", [])):
        if mate.get("type") == "width":
            ref_keys = ("width_faces", "tab_faces")
        else:
            ref_keys = ("a", "b")
        for ref_key in ref_keys:
            if mate.get("type") == "width":
                ref_list = mate.get(ref_key, [])
                for j, ref in enumerate(ref_list):
                    cid = ref.get("component")
                    face_ref = ref.get("face_ref", {})
                    if cid not in known_components:
                        result["error"] = (
                            f"mate[{i}].{ref_key}[{j}]: component {cid!r} "
                            f"not in spec"
                        )
                        return result
                    if not face_ref:
                        result["error"] = (
                            f"mate[{i}].{ref_key}[{j}]: empty face_ref"
                        )
                        return result
                    face_checks.append({
                        "mate_index": i,
                        "ref": f"{ref_key}[{j}]",
                        "component": cid,
                        "face_ref_keys": sorted(face_ref.keys()),
                    })
            else:
                ref = mate.get(ref_key, {})
                cid = ref.get("component")
                face_ref = ref.get("face_ref", {})
                if cid not in known_components:
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

    # Resolve part paths. Order: part -> part_paths[cid] -> part_spec_path
    # -> build part_spec to a temp .sldprt.
    resolved: dict[str, str] = {}
    sources: dict[str, str] = {}
    built_specs: dict[str, dict[str, Any]] = {}
    for comp in spec.get("components", []):
        cid = comp["id"]
        pp = comp.get("part")
        source = "part" if pp else None
        if pp is None and part_paths:
            override = part_paths.get(cid)
            if override is not None:
                pp = override
                source = "part_paths"
        if pp is None:
            psp = comp.get("part_spec_path")
            if psp is not None:
                pp = psp
                source = "part_spec_path"
        if pp is not None:
            resolved[cid] = pp
            sources[cid] = source or "part"
            continue

        spec_path = comp.get("part_spec")
        if spec_path is None:
            result["error"] = f"component {cid!r}: no part path resolved"
            return result

        # Load + validate the spec file (offline).
        try:
            part_spec_data = _load_part_spec(spec_path)
        except (FileNotFoundError, ValueError) as exc:
            result["error"] = f"component {cid!r}: {exc}"
            return result

        # Build the part on the live SW session.
        save_to = _temp_part_path(cid)
        build_out = _build_part_spec(part_spec_data, save_to)
        if not build_out.get("ok"):
            result["error"] = (
                f"component {cid!r}: part_spec build failed: "
                f"{build_out.get('error')}"
            )
            return result
        resolved[cid] = save_to
        sources[cid] = "part_spec"
        built_specs[cid] = {
            "spec_path": spec_path,
            "save_as": save_to,
            "features_built": build_out.get("features_built", []),
            "save_as_verified": build_out.get("save_as_verified"),
        }

    result["built_part_specs"] = built_specs
    result["sources"] = sources

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
            mate_feat, mate_err = create_mate(
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

        # L4 (W14): persist a v2 manifest (verbatim spec + runtime overlay)
        # alongside the .sldasm so the assembly is durable and losslessly
        # re-openable. Provenance: when a component was built from a part_spec,
        # record the source path + its content hash.
        manifest = AssemblyManifest(spec=spec, assembly_path=str(output_path))
        for cid, comp in placed.items():
            try:
                sw_name = comp.Name if hasattr(comp, "Name") else str(comp)
            except Exception:
                sw_name = cid
            comp_spec = next(c for c in comp_specs if c["id"] == cid)
            spec_path = built_specs.get(cid, {}).get("spec_path")
            manifest.components.append(ComponentInstance(
                id=cid,
                sw_name=str(sw_name),
                part_path=resolved[cid],
                transform=comp_spec.get("transform", {}),
                part_spec_path=spec_path,
                part_spec_sha256=sha256_of_file(spec_path),
            ))

        manifest_path = str(output_path) + ".manifest.json"
        try:
            manifest.save(Path(manifest_path))
            result["manifest_path"] = manifest_path
        except OSError as exc:
            result["manifest_path"] = None
            result["manifest_save_error"] = f"{type(exc).__name__}: {exc}"

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
