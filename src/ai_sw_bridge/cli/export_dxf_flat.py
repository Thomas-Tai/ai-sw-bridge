"""ai-sw-export-dxf-flat: Sheet-metal flat-pattern DXF export S1 PAE CLI.

The §6.5-consistent surface for flat-pattern DXF export characterization —
CLI-only, never MCP. Builds a sheet-metal fixture (base-flange), exports
the flat pattern via ExportToDWG2, parses the DXF ENTITIES section, and
reports to ``_results/export_dxf_flat.json``.

Subcommands:
  export
      Build a base-flange fixture, export flat-pattern DXF, verify
      entities (outline LINEs/ARCs + bend layer), write PAE result.

Each subcommand prints a single JSON object to stdout and exits 0 if ok.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import tempfile
from pathlib import Path
from typing import Any

from .stability import add_tier, cli_stability
from .streams import add_quiet_flag, apply_quiet

logger = logging.getLogger("ai_sw_bridge.cli.export_dxf_flat")

PART_NAME = "W42_sheet_metal_fixture"
THICKNESS_MM = 2.0
BEND_RADIUS_MM = 3.0
FLANGE_WIDTH_MM = 100.0
FLANGE_HEIGHT_MM = 50.0


def _find_latest_sketch_name(doc: Any) -> str | None:
    """Return the name of the most recently created sketch feature.

    Uses ``FeatureByPositionReverse(0)`` (the newest feature) to find a
    ``ProfileFeature`` or ``Sketch`` type. Falls back to a full walk if
    position 0 isn't a sketch.
    """
    try:
        raw_count = doc.GetFeatureCount
        count = raw_count(True) if callable(raw_count) else int(raw_count)
    except Exception:
        return None

    sketch_types = {"ProfileFeature", "OriginProfileFeature", "Sketch"}
    for i in range(count):
        try:
            feat = doc.FeatureByPositionReverse(i)
        except Exception:
            break
        if feat is None:
            break
        try:
            type_name = feat.GetTypeName
            type_name = type_name() if callable(type_name) else str(type_name)
        except Exception:
            continue
        if type_name in sketch_types:
            try:
                name = feat.Name
                return name() if callable(name) else str(name)
            except Exception:
                pass
    return None


def _build_sheet_metal_fixture(sw: Any) -> tuple[Any, str, str]:
    """Create a base-flange sheet-metal part and return (doc, source_path, sketch_name).

    Uses the proven COM route from mutate._create_base_flange:
      CreateDefinition(34) → typed_qi(IBaseFlangeFeatureData) →
      set Thickness/BendRadius → CreateFeature.
    """
    from ..spec.builder import create_blank_part
    from ..mutate import _create_base_flange

    doc = create_blank_part(sw)

    PLANE_FULL_NAME = {
        "Front": "Front Plane",
        "Top": "Top Plane",
        "Right": "Right Plane",
    }
    plane_name = PLANE_FULL_NAME["Front"]
    ok = doc.SelectByID(plane_name, "PLANE", 0.0, 0.0, 0.0)
    if not ok:
        raise RuntimeError(f"could not select {plane_name}")

    doc.SketchManager.InsertSketch(True)

    w_m = FLANGE_WIDTH_MM / 1000.0
    h_m = FLANGE_HEIGHT_MM / 1000.0
    doc.SketchManager.CreateCenterRectangle(0.0, 0.0, 0.0, w_m / 2.0, h_m / 2.0, 0.0)

    doc.SketchManager.InsertSketch(True)
    doc.ClearSelection2(True)

    sketch_name = _find_latest_sketch_name(doc)
    if not sketch_name:
        raise RuntimeError("could not find the created sketch name")

    ok_bf, bf_err = _create_base_flange(
        doc,
        {"sketch": sketch_name},
        thickness_mm=THICKNESS_MM,
        bend_radius_mm=BEND_RADIUS_MM,
    )
    if not ok_bf:
        raise RuntimeError(f"base-flange creation failed: {bf_err}")

    doc.ForceRebuild3(False)

    tmp_dir = Path(tempfile.mkdtemp(prefix="w42_dxf_flat_"))
    part_path = tmp_dir / f"{PART_NAME}.SLDPRT"
    err = doc.SaveAs3(str(part_path), 0, 0)
    err_code = int(err) if err is not None else 0
    if err_code != 0:
        raise RuntimeError(f"SaveAs3 returned error {err_code}")

    return doc, str(part_path), sketch_name


def _parse_dxf_entities(dxf_text: str) -> dict[str, Any]:
    """Parse the ENTITIES section of a DXF file.

    Returns counts of entity types and layer names. DXF is a text format
    with group-code/value pairs. The ENTITIES section starts with
    ``SECTION\\n  2\\nENTITIES`` and ends with ``ENDSEC``.
    """
    lines = dxf_text.splitlines()

    entities_start = -1
    entities_end = len(lines)
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "ENTITIES":
            if i > 0 and lines[i - 1].strip() == "2":
                entities_start = i + 1
                break

    if entities_start < 0:
        return {
            "entities_section_found": False,
            "entity_count": 0,
            "entity_types": {},
            "layers": set(),
            "has_bend_layer": False,
        }

    for i in range(entities_start, len(lines)):
        if lines[i].strip() == "ENDSEC":
            entities_end = i
            break

    entity_types: dict[str, int] = {}
    layers: set[str] = set()
    current_entity = ""
    in_entity = False

    i = entities_start
    while i < entities_end - 1:
        code = lines[i].strip()
        value = lines[i + 1].strip() if i + 1 < entities_end else ""

        if code == "0" and value != "SECTION":
            if in_entity and current_entity:
                entity_types[current_entity] = entity_types.get(current_entity, 0) + 1
            current_entity = value
            in_entity = True

        if code == "8" and in_entity:
            layers.add(value)

        i += 2

    if in_entity and current_entity:
        entity_types[current_entity] = entity_types.get(current_entity, 0) + 1

    bend_layer_names = {"BEND", "IV_BEND", "IGES_BEND", "AM_BEND", "BEND-LINE"}
    has_bend = bool(layers & bend_layer_names) or any(
        "BEND" in layer.upper() for layer in layers
    )

    return {
        "entities_section_found": True,
        "entity_count": sum(entity_types.values()),
        "entity_types": entity_types,
        "layers": sorted(layers),
        "has_bend_layer": has_bend,
    }


def parse_dxf_outline_bbox(dxf_text: str) -> dict[str, Any]:
    """Bounding box (mm) of the LINE entities in the ENTITIES section.

    This is the LOAD-BEARING proof that ``dxf_flat`` actually UNFOLDS a bent
    part (W42): the developed (unrolled) long span of a single-bend bracket is
    distinct from its largest folded face. SOLIDWORKS flat-pattern DXF emits
    coordinates in document units (mm); spans are computed directly. Group codes
    10/11 = X of a LINE's two endpoints, 20/21 = Y.

    Returns ``{found, span_long_mm, span_short_mm}``; ``found=False`` if no LINE
    coordinates are present.
    """
    lines = dxf_text.splitlines()
    xs: list[float] = []
    ys: list[float] = []
    in_line = False
    i = 0
    while i < len(lines) - 1:
        code = lines[i].strip()
        val = lines[i + 1].strip()
        if code == "0":
            in_line = val == "LINE"
        elif in_line and code in ("10", "11"):
            try:
                xs.append(float(val))
            except ValueError:
                pass
        elif in_line and code in ("20", "21"):
            try:
                ys.append(float(val))
            except ValueError:
                pass
        i += 2
    if not xs or not ys:
        return {"found": False}
    span_x = max(xs) - min(xs)
    span_y = max(ys) - min(ys)
    return {
        "found": True,
        "span_long_mm": round(max(span_x, span_y), 2),
        "span_short_mm": round(min(span_x, span_y), 2),
    }


# The geometric classifier + segment parser live in the export module (their
# canonical home, W48); re-exported here for back-compat with the W46 offline
# tests and the drawing-view spike that import them from this CLI namespace.
from ..export.dxf_bend_layers import (  # noqa: E402
    _parse_dxf_line_segments,
    classify_bend_lines_geometric,
    rewrite_dxf_with_bend_layer,
)

__all__ = [
    "_parse_dxf_line_segments",
    "classify_bend_lines_geometric",
    "rewrite_dxf_with_bend_layer",
    "parse_dxf_outline_bbox",
]


def _run_export(args: argparse.Namespace) -> dict[str, Any]:
    """Build fixture, export flat-pattern DXF, verify, report."""
    from ..export.dispatch import (
        ExportRequest,
        _flat_pattern_dxf,
        _get_doc_type,
    )
    from ..export.formats import EXPORT_FORMATS
    from ..sw_com import get_sw_app

    output_dir = Path(args.output_dir) if args.output_dir else Path("_results")
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    result: dict[str, Any] = {
        "wave": "W42",
        "step": "S1",
        "format": "dxf_flat",
        "ok": False,
    }

    try:
        sw = get_sw_app()
    except Exception as exc:
        result["error"] = f"Cannot connect to SOLIDWORKS: {exc}"
        return result

    # --- Step 1: Build sheet-metal fixture ---
    try:
        doc, source_path, sketch_name = _build_sheet_metal_fixture(sw)
        result["fixture"] = {
            "part_path": source_path,
            "sketch_name": sketch_name,
            "thickness_mm": THICKNESS_MM,
            "bend_radius_mm": BEND_RADIUS_MM,
            "width_mm": FLANGE_WIDTH_MM,
            "height_mm": FLANGE_HEIGHT_MM,
        }
    except Exception as exc:
        result["error"] = f"Fixture build failed: {exc}"
        return result

    # --- Step 2: Export flat-pattern DXF ---
    dxf_path = output_dir / f"{PART_NAME}_flat.dxf"
    fmt = EXPORT_FORMATS["dxf_flat"]
    export_result = _flat_pattern_dxf(doc, fmt, dxf_path)

    result["export"] = export_result.to_dict()
    if not export_result.ok:
        result["error"] = f"Export failed: {export_result.error}"
        return result

    # --- Step 3: Verify-the-BYTES ---
    try:
        dxf_text = dxf_path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        result["error"] = f"Cannot read DXF file: {exc}"
        return result

    entities = _parse_dxf_entities(dxf_text)
    result["dxf_verify"] = {
        "entities_section_found": entities["entities_section_found"],
        "entity_count": entities["entity_count"],
        "entity_types": entities["entity_types"],
        "layers": entities["layers"],
        "has_bend_layer": entities["has_bend_layer"],
        "file_size_bytes": dxf_path.stat().st_size if dxf_path.exists() else 0,
    }

    has_outline = entities["entity_count"] > 0 and (
        entities["entity_types"].get("LINE", 0) > 0
        or entities["entity_types"].get("ARC", 0) > 0
        or entities["entity_types"].get("LWPOLYLINE", 0) > 0
    )
    has_bend = entities["has_bend_layer"]

    if not entities["entities_section_found"]:
        result["error"] = "DXF has no ENTITIES section"
        return result

    if not has_outline:
        result["error"] = (
            f"No outline entities found in DXF ENTITIES section. "
            f"Entity types: {entities['entity_types']}"
        )
        return result

    if not has_bend:
        logger.info(
            "No explicit bend layer found (layers: %s). "
            "A base-flange-only part has no bend lines; this is expected.",
            entities["layers"],
        )

    result["ok"] = True
    result["verification"] = {
        "outline_entities": has_outline,
        "bend_layer_detected": has_bend,
        "entity_count": entities["entity_count"],
        "file_size_bytes": dxf_path.stat().st_size,
    }

    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-sw-export-dxf-flat",
        description=(
            "Sheet-metal flat-pattern DXF export for SOLIDWORKS. "
            "Builds a base-flange fixture, exports via ExportToDWG2, "
            "and verifies the developed flat-pattern outline (bend lines are a "
            "deferred sub-scope; see docs/DEFERRED.md Wave-42)."
        ),
    )
    subs = parser.add_subparsers(dest="tool", required=True, metavar="tool")

    p = subs.add_parser(
        "export",
        help=(
            "Build fixture, export flat-pattern DXF, verify entities, "
            "write PAE result."
        ),
    )
    p.add_argument(
        "--output-dir",
        dest="output_dir",
        default="_results",
        help="Directory for output files (default: _results).",
    )
    p.set_defaults(func=_run_export)

    return parser


@cli_stability("experimental")
def main() -> int:
    parser = _build_parser()
    add_tier(parser, "experimental")
    add_quiet_flag(parser)
    args = parser.parse_args()
    apply_quiet(args)

    result = args.func(args)
    print(json.dumps(result, indent=2, default=str))

    output_dir = (
        Path(args.output_dir)
        if hasattr(args, "output_dir") and args.output_dir
        else Path("_results")
    )
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / "export_dxf_flat.json"
    result_path.write_text(
        json.dumps(result, indent=2, default=str), encoding="utf-8"
    )
    print(f"Result written to {result_path}", file=sys.stderr)

    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
