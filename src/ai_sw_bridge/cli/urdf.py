"""ai-sw-urdf: URDF export CLI (W78) — SOLIDWORKS assembly → ROS robot model.

Subcommand:
  export --assembly <path> --output-dir <dir>
      Open the assembly and write <output_dir>/<robot_name>.urdf plus one
      meshes/<link>.stl per component. Each component becomes a URDF <link>
      (inertial + visual + collision) fixed-jointed to a massless base_link at
      its assembly pose. Prints one JSON object to stdout; exits 0 iff ok.

Read-only with respect to the SW model (it interrogates mass properties and
exports meshes; it does not drive or edit the assembly).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .stability import add_tier, cli_stability
from .streams import add_quiet_flag, apply_quiet

_SW_DOC_ASSEMBLY = 2


def _run_export(args: argparse.Namespace) -> dict[str, Any]:
    from ..client import SolidWorksClient
    from ..com.earlybind import typed
    from ..com.sw_type_info import wrapper_module
    from ..sw_com import get_sw_app

    result: dict[str, Any] = {"tool": "export_urdf", "ok": False}

    asm_path = args.assembly
    if not Path(asm_path).exists():
        result["error"] = f"assembly not found: {asm_path}"
        return result

    try:
        sw = get_sw_app()
        mod = wrapper_module()
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"cannot connect to SOLIDWORKS: {exc}"
        return result

    try:
        typed_sw = typed(sw, "ISldWorks", module=mod)
        opened = typed_sw.OpenDoc6(asm_path, _SW_DOC_ASSEMBLY, 0, "", 0, 0)
        doc = opened[0] if isinstance(opened, tuple) else opened
        if doc is None:
            result["error"] = f"OpenDoc6 returned None for {asm_path}"
            return result
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"OpenDoc6 failed: {exc!r}"
        return result

    try:
        # v0.18 slice: route through the class-based SolidWorksClient.urdf facade
        # (reuses the app + wrapper module we already hold).
        client = SolidWorksClient(app=sw, mod=mod)
        report = client.urdf.export(
            doc,
            args.output_dir,
            robot_name=args.robot_name,
            binary_stl=not args.ascii_stl,
        )
        result.update(report)
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"export_urdf failed: {exc!r}"
        result["ok"] = False
    # Leave docs open (Close() corrupts the COM channel mid-session).
    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-sw-urdf",
        description=(
            "Export a SOLIDWORKS assembly to a URDF robot model (links, "
            "inertial tensors, collision/visual meshes) for ROS / simulation."
        ),
    )
    subs = parser.add_subparsers(dest="tool", required=True, metavar="tool")
    p = subs.add_parser("export", help="Export the assembly to a URDF package.")
    p.add_argument("--assembly", required=True, help="Path to the .SLDASM.")
    p.add_argument(
        "--output-dir", dest="output_dir", required=True,
        help="Directory to write <robot_name>.urdf and meshes/ into.",
    )
    p.add_argument(
        "--robot-name", dest="robot_name", default="robot",
        help="URDF <robot> name and .urdf filename stem (default: robot).",
    )
    p.add_argument(
        "--ascii-stl", dest="ascii_stl", action="store_true",
        help="Write ASCII STL meshes (default: binary).",
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
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
