"""ai-sw-solver: Autonomous clearance solver CLI (W76) — "make it fit".

CLI-ONLY (never MCP, §6.5): ``resolve-clearance`` DRIVES a distance mate to
remove an interference, which is a model mutation — so this surface is CLI-gated
like ``ai-sw-motion`` and the other mutators.

Subcommand:
  resolve-clearance --assembly <path> --mate <name>
      Open the assembly, drive the named distance mate monotonically by
      ``--step-mm`` until clash-free (count==0 AND volume==0), or fail-closed and
      revert the mate to its original value at the ``--max-iters`` ceiling.
      Prints one JSON object to stdout; exits 0 iff fully resolved.

Fail-state contract: atomic. On success the mate is left at the resolved value
(and saved iff ``--save``); on failure it is reverted to its original value and
``ok`` is False, with ``best_state`` reporting the closest the solver got.
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


def _run_resolve(args: argparse.Namespace) -> dict[str, Any]:
    from ..com.earlybind import typed
    from ..com.sw_type_info import wrapper_module
    from ..solver import resolve_clearance
    from ..sw_com import get_sw_app

    result: dict[str, Any] = {"tool": "auto_resolve_clearance", "ok": False}

    asm_path = args.assembly
    if not Path(asm_path).exists():
        result["error"] = f"assembly not found: {asm_path}"
        return result
    if args.step_mm <= 0:
        result["error"] = f"--step-mm must be > 0 (got {args.step_mm})"
        return result
    if args.max_iters < 1:
        result["error"] = f"--max-iters must be >= 1 (got {args.max_iters})"
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
        report = resolve_clearance(
            doc,
            args.mate,
            step_mm=float(args.step_mm),
            max_iters=int(args.max_iters),
            direction=args.direction,
            save=bool(args.save),
            mod=mod,
        )
        result.update(report)
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"resolve_clearance failed: {exc!r}"
        result["ok"] = False
    finally:
        # Leave docs open (Close() corrupts the COM channel mid-session); the
        # solver already reverted on failure / left the resolved value on success.
        pass

    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-sw-solver",
        description=(
            "Autonomous clearance solver — drive a distance mate until the "
            "assembly is clash-free, or fail-closed and revert. CLI-only."
        ),
    )
    subs = parser.add_subparsers(dest="tool", required=True, metavar="tool")
    p = subs.add_parser(
        "resolve-clearance",
        help="Drive a distance mate to remove an interference.",
    )
    p.add_argument("--assembly", required=True, help="Path to the .SLDASM.")
    p.add_argument("--mate", required=True, help="Name of the distance mate to drive.")
    p.add_argument(
        "--step-mm",
        dest="step_mm",
        type=float,
        default=2.0,
        help="Monotonic step-out increment in mm (default: 2.0).",
    )
    p.add_argument(
        "--max-iters",
        dest="max_iters",
        type=int,
        default=20,
        help="Iteration ceiling before fail-closed revert (default: 20).",
    )
    p.add_argument(
        "--direction",
        choices=("out", "in"),
        default="out",
        help="'out' increases the mate value (default), 'in' decreases it.",
    )
    p.add_argument(
        "--save",
        action="store_true",
        help="Persist the model on success (default: dry-run, no save).",
    )
    p.add_argument(
        "--output-dir",
        dest="output_dir",
        default="_results",
        help="Directory for the result JSON (default: _results).",
    )
    p.set_defaults(func=_run_resolve)
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

    output_dir = Path(getattr(args, "output_dir", None) or "_results").resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "auto_resolve_clearance.json").write_text(
        json.dumps(result, indent=2, default=str), encoding="utf-8"
    )
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
