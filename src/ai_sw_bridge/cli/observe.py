"""ai-sw-observe: read-only inspection CLI.

Subcommands:
  active_doc          -> sw_get_active_doc()
  feature_errors      -> sw_get_feature_errors()
  equations           -> sw_get_equations()
  bbox                -> sw_get_bbox()             [part only, legacy]
  bounding_box        -> bounding_box()            [part only, W30]
  assembly_bbox       -> assembly_bounding_box()   [assembly only, W52]
  volume              -> sw_get_volume()           [part only]
  screenshot          -> sw_screenshot(width, height, fit_view, filename)
  measure             -> sw_measure(entity_a, entity_b)  [legacy]
  measure_selection   -> measure_selection()      [W30, pre-selected entities]
  measure_durable_pair -> measure_durable_pair(ref_a, ref_b)  [W52, durable refs]
  measure_angle       -> measure_angle()           [W52, pre-selected]
  measure_area        -> measure_area()            [W52, pre-selected]
  mate_errors         -> sw_get_mate_errors()  [assembly only]
  interference        -> sw_get_interference()  [assembly only, W27/E4]
  clearance           -> sw_get_clearance()    [assembly only, W35]
  face_clearance      -> face_clearance(face_a, face_b)  [W52, named faces]
  draft               -> sw_get_draft_analysis() [part only, W37]
  inertia             -> inertia()               [part only, W5 E1]
  custom_props        -> sw_get_custom_props()  [experimental]
  addins              -> sw_get_enabled_addins()  [experimental, W7.1]
  selection           -> selection()              [any doc, W43]
  undercut            -> sw_undercut_faces(pull_x, pull_y, pull_z)  [experimental, DFM]
  min_wall            -> sw_min_wall_thickness(samples_per_face)  [experimental, DFM]
  section_props       -> sw_get_section_props()  [W58, pre-selected face, experimental]

Each subcommand prints a single JSON object to stdout and exits 0 if the
underlying tool returned ok=True, else 1. Both --key=value and --key value
syntax are accepted (argparse-standard).
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from ..observe import SolidWorksObserver
from ..observe_section import sw_get_section_props
from ..sw_com import get_active_doc, get_sw_app
from .stability import add_subcommand_tier, add_tier, cli_stability
from .streams import add_quiet_flag, apply_quiet


def _run_active_doc(_args: argparse.Namespace) -> dict[str, Any]:
    return SolidWorksObserver().active_doc()


def _run_feature_errors(_args: argparse.Namespace) -> dict[str, Any]:
    return SolidWorksObserver().feature_errors()


def _run_equations(_args: argparse.Namespace) -> dict[str, Any]:
    return SolidWorksObserver().equations()


def _run_mate_errors(_args: argparse.Namespace) -> dict[str, Any]:
    return SolidWorksObserver().mate_errors()


def _run_bbox(_args: argparse.Namespace) -> dict[str, Any]:
    return SolidWorksObserver().bbox()


def _run_bounding_box(_args: argparse.Namespace) -> dict[str, Any]:
    return SolidWorksObserver().bounding_box()


def _run_volume(_args: argparse.Namespace) -> dict[str, Any]:
    return SolidWorksObserver().volume()


def _run_screenshot(args: argparse.Namespace) -> dict[str, Any]:
    return SolidWorksObserver().screenshot(
        width=args.width,
        height=args.height,
        fit_view=args.fit_view,
        filename=args.filename,
    )


def _run_measure(args: argparse.Namespace) -> dict[str, Any]:
    return SolidWorksObserver().measure(entity_a=args.entity_a, entity_b=args.entity_b)


def _run_measure_selection(_args: argparse.Namespace) -> dict[str, Any]:
    return SolidWorksObserver().measure_selection()


def _run_inertia(_args: argparse.Namespace) -> dict[str, Any]:
    return SolidWorksObserver().inertia()


def _run_custom_props(_args: argparse.Namespace) -> dict[str, Any]:
    return SolidWorksObserver().custom_props()


def _run_addins(_args: argparse.Namespace) -> dict[str, Any]:
    return SolidWorksObserver().enabled_addins()


def _run_interference(_args: argparse.Namespace) -> dict[str, Any]:
    return SolidWorksObserver().interference()


def _run_clearance(args: argparse.Namespace) -> dict[str, Any]:
    return SolidWorksObserver().clearance(comp_a=args.comp_a, comp_b=args.comp_b)


def _run_draft(args: argparse.Namespace) -> dict[str, Any]:
    return SolidWorksObserver().draft_analysis(
        pull_direction=args.pull_direction,
        min_angle_deg=args.min_angle,
    )


def _run_selection(_args: argparse.Namespace) -> dict[str, Any]:
    return SolidWorksObserver().selection()


def _run_undercut(args: argparse.Namespace) -> dict[str, Any]:
    return SolidWorksObserver().undercut_faces(
        pull_x=args.pull_x, pull_y=args.pull_y, pull_z=args.pull_z
    )


def _run_min_wall(args: argparse.Namespace) -> dict[str, Any]:
    return SolidWorksObserver().min_wall_thickness(
        samples_per_face=args.samples_per_face
    )


def _run_assembly_bbox(_args: argparse.Namespace) -> dict[str, Any]:
    return SolidWorksObserver().assembly_bounding_box()


def _run_measure_durable_pair(args: argparse.Namespace) -> dict[str, Any]:
    return SolidWorksObserver().measure_durable_pair(
        durable_ref_a=args.ref_a, durable_ref_b=args.ref_b
    )


def _run_measure_angle(_args: argparse.Namespace) -> dict[str, Any]:
    return SolidWorksObserver().measure_angle()


def _run_measure_area(_args: argparse.Namespace) -> dict[str, Any]:
    return SolidWorksObserver().measure_area()


def _run_face_clearance(args: argparse.Namespace) -> dict[str, Any]:
    return SolidWorksObserver().face_clearance(
        face_a=args.face_a, face_b=args.face_b
    )


def _run_section_props(_args: argparse.Namespace) -> dict[str, Any]:
    doc = get_active_doc(get_sw_app())
    if doc is None:
        return {"ok": False, "error": "no_active_doc"}
    return sw_get_section_props(doc)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-sw-observe",
        description=(
            "Read-only inspection of the running SOLIDWORKS session. Each "
            "subcommand runs a single observation tool and prints a JSON "
            "object to stdout."
        ),
    )
    subs = parser.add_subparsers(dest="tool", required=True, metavar="tool")

    p = subs.add_parser("active_doc", help="Report metadata on the active document.")
    p.set_defaults(func=_run_active_doc)

    p = subs.add_parser(
        "feature_errors",
        help="Walk the active doc's feature tree and report non-OK features.",
    )
    p.set_defaults(func=_run_feature_errors)

    p = subs.add_parser(
        "equations",
        help="Dump every equation in the active doc with value and status.",
    )
    p.set_defaults(func=_run_equations)

    p = subs.add_parser(
        "bbox",
        help="Report the active part's axis-aligned bounding box (part only, legacy).",
        description=(
            "Read the active part's bounding box via IPartDoc.GetPartBox. "
            "Reports min/max corners and spans in BOTH mm and m. Part docs "
            "only -- returns a typed error result for assemblies/drawings."
            "Legacy method -- for W30-style mm-only report, use bounding_box."
        ),
    )
    p.set_defaults(func=_run_bbox)

    p = subs.add_parser(
        "bounding_box",
        help="Report the active part's bounding box (part only, W30).",
        description=(
            "Wave-30 perception axis — read the active part's bounding box "
            "via IPartDoc.GetPartBox(True). Reports mm values only: "
            "{x_min_mm, x_max_mm, y_min_mm, y_max_mm, z_min_mm, z_max_mm, "
            "dx_mm, dy_mm, dz_mm}. Part docs only."
        ),
    )
    p.set_defaults(func=_run_bounding_box)

    p = subs.add_parser(
        "volume",
        help="Report the active part's volume, surface area, and mass (part only).",
        description=(
            "Read the active part's mass properties via "
            "IModelDocExtension.CreateMassProperty. Reports volume in mm^3 "
            "and m^3, surface area, mass (only meaningful with an assigned "
            "material; see density_kg_m3), and center of mass. The "
            "volume_mm3 field is the oracle compared against per-feature "
            "spec _expect.mass_delta_mm3 in the upcoming P0.5 verifier."
        ),
    )
    p.set_defaults(func=_run_volume)

    p = subs.add_parser(
        "screenshot",
        help="Capture the active SW viewport to a PNG file.",
        description=(
            "Capture the active SW viewport to a PNG on disk. Output goes to "
            "AI_SW_BRIDGE_CAPTURES env var if set, else ./captures relative "
            "to the current working directory."
        ),
    )
    p.add_argument("--width", type=int, default=640, help="Image width (default 640)")
    p.add_argument("--height", type=int, default=360, help="Image height (default 360)")
    p.add_argument(
        "--fit-view",
        dest="fit_view",
        action="store_true",
        help="Call ViewZoomtofit2 before capture.",
    )
    p.add_argument(
        "--filename",
        default=None,
        help="Output filename (auto-derived from doc title if omitted).",
    )
    p.set_defaults(func=_run_screenshot)

    p = subs.add_parser(
        "measure",
        help="Measure entities in the active document (legacy).",
        description=(
            "Measure entities in the active document. With no args, measures "
            "whatever is currently selected in the SW UI. With --entity-a, "
            "programmatically selects that entity and reports area/perimeter."
            "Legacy method -- for W30-style pre-selected measurement, use measure_selection."
        ),
    )
    p.add_argument(
        "--entity-a",
        dest="entity_a",
        default=None,
        help="Name of the first entity to select.",
    )
    p.add_argument(
        "--entity-b",
        dest="entity_b",
        default=None,
        help="Name of the second entity (note: two-entity named selection is unsupported).",
    )
    p.set_defaults(func=_run_measure)

    p = subs.add_parser(
        "measure_selection",
        help="Measure currently selected entities (W30).",
        description=(
            "Wave-30 perception axis — measure whatever entities are "
            "currently selected in SW via IMeasure.Calculate. Returns "
            "{distance_mm, delta_x_mm, delta_y_mm, delta_z_mm}. "
            "Pre-select entities via select_entity or SW UI before calling."
        ),
    )
    p.set_defaults(func=_run_measure_selection)

    p = subs.add_parser(
        "mate_errors",
        help="Walk an assembly's mate set and report per-mate status (assembly only).",
    )
    p.set_defaults(func=_run_mate_errors)

    p = subs.add_parser(
        "interference",
        help="Detect physical interferences in the active assembly (W27/E4).",
        description=(
            "Wave-27 E4 — detect component clashes via "
            "IAssemblyDoc.InterferenceDetectionManager. Reports "
            "interference_count and a list of interferences with "
            "component names and volumes (mm³). Assembly docs only."
        ),
    )
    p.set_defaults(func=_run_interference)

    p = subs.add_parser(
        "clearance",
        help="Measure minimum distance between two assembly components (W35).",
        description=(
            "Wave-35 perception axis — measure the minimum gap between two "
            "named components via IModelDocExtension.CreateMeasure → "
            "IMeasure.Distance after selecting both with IComponent2.Select2. "
            "Reports {min_distance_mm, components: [a, b], touching: bool}. "
            "Assembly docs only."
        ),
    )
    p.add_argument(
        "--comp-a",
        dest="comp_a",
        required=True,
        help="Name of the first component (IComponent2.Name2, e.g. 'block_20mm-1').",
    )
    p.add_argument(
        "--comp-b",
        dest="comp_b",
        required=True,
        help="Name of the second component (IComponent2.Name2, e.g. 'block_20mm-2').",
    )
    p.set_defaults(func=_run_clearance)

    p = subs.add_parser(
        "draft",
        help="DFM draft analysis of the active part (W37).",
        description=(
            "Wave-37 perception axis — classify every face of the active "
            "part as positive/negative/vertical draft relative to a pull "
            "direction. Uses first-principles face-normal sweep "
            "(GetBodies2 → GetFaces → IFace2.Normal vs pull vector). "
            "Reports {pull_direction, faces_total, faces_positive, "
            "faces_negative, faces_vertical, min_draft_deg, "
            "faces_below_threshold}. Part docs only."
        ),
    )
    p.add_argument(
        "--pull-direction",
        dest="pull_direction",
        required=True,
        help=(
            "Mould pull direction: front, back, top, bottom, right, left, "
            "or axis shorthand (+x, -x, +y, -y, +z, -z)."
        ),
    )
    p.add_argument(
        "--min-angle",
        dest="min_angle",
        type=float,
        default=1.0,
        help="Threshold in degrees below which a face is flagged as vertical (default 1.0).",
    )
    p.set_defaults(func=_run_draft)

    p = subs.add_parser(
        "inertia",
        help="Report inertia tensor of the active part (W5 E1).",
        description=(
            "Wave-5 E1 — read the full 3x3 inertia tensor via "
            "IMassProperty2.GetMomentOfInertia(0). Reports "
            "center_of_mass_mm, inertia_tensor_kg_m2, "
            "principal_moments_kg_m2, principal_axes. Part docs only."
        ),
    )
    p.set_defaults(func=_run_inertia)

    p = subs.add_parser(
        "custom_props",
        help="Read every custom property from the active document.",
        description=(
            "Read custom properties via IModelDoc2.GetCustomInfoNames3 and "
            "GetCustomInfoValue2. Works on parts, assemblies, and drawings. "
            "Returns an empty properties dict when no custom props are set."
        ),
    )
    add_subcommand_tier(p, "experimental")
    p.set_defaults(func=_run_custom_props)

    p = subs.add_parser(
        "addins",
        help="List currently-loaded SOLIDWORKS add-ins (W7.1).",
        description=(
            "W7.1 — enumerate add-ins via ISldWorks::GetEnabledAddIns. "
            "Reports every loaded add-in name and flags those in the "
            "curated KNOWN_PROBLEMATIC_ADDINS list "
            "(docs/addins_research.md §5). Two-stream contract: stdout "
            "JSON, stderr diagnostics."
        ),
    )
    add_subcommand_tier(p, "experimental")
    p.set_defaults(func=_run_addins)

    p = subs.add_parser(
        "selection",
        help="Report the active document's current selection (W43).",
        description=(
            "Wave-43 perception axis — read whatever entities are currently "
            "selected in SW via SelectionManager.GetSelectedObjectCount2 / "
            "GetSelectedObjectType3 / GetSelectedObject6. Reports per-entity "
            "type (swSelectType_e), name, and a durable persist-reference "
            "token (GetPersistReference3, base64url-encoded) when obtainable. "
            "Works on any document type. Empty selection is valid (count=0)."
        ),
    )
    p.set_defaults(func=_run_selection)

    p = subs.add_parser(
        "undercut",
        help="Report faces that block mold/tool withdrawal along a pull direction (DFM).",
        description=(
            "Read-only DFM probe (cousin of draft analysis). Enumerates "
            "every solid face of the active part via GetBodies2/GetFaces, "
            "reads each IFace2.Normal, and classifies it as undercut / "
            "releasable / side-wall vs the pull direction (default +Y). A "
            "back-facing (negative-dot) face is flagged as an undercut. "
            "Part docs only."
        ),
    )
    p.add_argument(
        "--pull-x", dest="pull_x", type=float, default=0.0, help="Pull dir X (default 0)"
    )
    p.add_argument(
        "--pull-y", dest="pull_y", type=float, default=1.0, help="Pull dir Y (default 1)"
    )
    p.add_argument(
        "--pull-z", dest="pull_z", type=float, default=0.0, help="Pull dir Z (default 0)"
    )
    add_subcommand_tier(p, "experimental")
    p.set_defaults(func=_run_undercut)

    p = subs.add_parser(
        "min_wall",
        help="Report the minimum wall thickness of the active solid part (DFM).",
        description=(
            "Read-only DFM probe -- the thin-region risk metric for "
            "molding/casting/printing. Samples each solid face and measures "
            "the through-material distance to the nearest opposite face via "
            "IFace2.GetClosestPointOn; the smallest is the min wall. Part "
            "docs only. EXPERIMENTAL: the closest-point estimate is an upper "
            "bound on the true normal-ray wall for non-planar faces."
        ),
    )
    p.add_argument(
        "--samples-per-face",
        dest="samples_per_face",
        type=int,
        default=4,
        help="On-face sample points per face (default 4).",
    )
    add_subcommand_tier(p, "experimental")
    p.set_defaults(func=_run_min_wall)

    p = subs.add_parser(
        "assembly_bbox",
        help="Report the combined bounding-box of all assembly components (W52).",
        description=(
            "Wave-52 — walk every component in the assembly, read each "
            "part box via IPartDoc.GetPartBox, transform corners through "
            "the component placement matrix (IComponent2.Transform2), and "
            "union into a single AABB. Reports mm values. Assembly docs only."
        ),
    )
    p.set_defaults(func=_run_assembly_bbox)

    p = subs.add_parser(
        "measure_durable_pair",
        help="Measure between two durable-reference entities (W52).",
        description=(
            "Wave-52 — resolve two base64url-encoded persist tokens via "
            "GetObjectByPersistReference3, select both entities, then "
            "measure via IMeasure.Calculate(None). Returns "
            "{distance_mm, delta_x_mm, delta_y_mm, delta_z_mm}."
        ),
    )
    p.add_argument(
        "--ref-a", dest="ref_a", required=True,
        help="Base64url-encoded persist reference for the first entity.",
    )
    p.add_argument(
        "--ref-b", dest="ref_b", required=True,
        help="Base64url-encoded persist reference for the second entity.",
    )
    p.set_defaults(func=_run_measure_durable_pair)

    p = subs.add_parser(
        "measure_angle",
        help="Measure the angle of currently selected entities (W52).",
        description=(
            "Wave-52 — pre-select two edges or faces, then measure via "
            "IMeasure.Angle. Returns angle in degrees."
        ),
    )
    p.set_defaults(func=_run_measure_angle)

    p = subs.add_parser(
        "measure_area",
        help="Measure the area of the currently selected face (W52).",
        description=(
            "Wave-52 — pre-select a face, then measure via IMeasure.Area. "
            "Returns area in mm²."
        ),
    )
    p.set_defaults(func=_run_measure_area)

    p = subs.add_parser(
        "face_clearance",
        help="Measure min distance between two named faces (W52).",
        description=(
            "Wave-52 — select two faces by name via SelectByID2, then "
            "measure the minimum distance via IMeasure.Distance. Reports "
            "{min_distance_mm, faces: [a, b], touching: bool}."
        ),
    )
    p.add_argument(
        "--face-a", dest="face_a", required=True,
        help="Name of the first face (e.g. 'Face<1>').",
    )
    p.add_argument(
        "--face-b", dest="face_b", required=True,
        help="Name of the second face (e.g. 'Face<2>').",
    )
    p.set_defaults(func=_run_face_clearance)

    # section_props (W58) — cross-section properties of a pre-selected face.
    p = subs.add_parser(
        "section_props",
        description=(
            "Return cross-section properties of the currently selected planar "
            "face via IModelDocExtension.GetSectionProperties2.  Caller must "
            "pre-select a planar face.  Returns area, centroid, moments of "
            "inertia (Ixx, Iyy, Izz), products (Ixy, Izx, Iyz), polar moment "
            "(Jp), and principal axes."
        ),
    )
    add_subcommand_tier(p, "experimental")
    p.set_defaults(func=_run_section_props)

    return parser


@cli_stability("stable")
def main() -> int:
    parser = _build_parser()
    add_tier(parser, "stable")
    add_quiet_flag(parser)
    args = parser.parse_args()
    apply_quiet(args)
    result = args.func(args)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
