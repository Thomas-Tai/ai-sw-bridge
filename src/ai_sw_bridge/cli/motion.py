"""ai-sw-motion: Dynamic Kinematic Verification CLI (W49) — Motion Audit.

CLI-ONLY (never MCP, §6.5): the audit DRIVES a mate through its DOF, which is a
transient model mutation. ``motion_sweep`` restores the original driver value and
never saves, so the audit is net non-destructive — but driving the model is a
mutation, so this surface is CLI-gated like the other mutators.

Subcommand:
  audit --spec <motion_audit.json>
      Open the assembly, drive the named mate from ``from`` to ``to`` over
      ``steps``, report interference + min-clearance at each position, and the
      collision envelope. Prints one JSON object to stdout; exits 0 if ok.

Spec (kind: "motion_audit"):
  {
    "kind": "motion_audit",
    "assembly": "C:/path/mech.SLDASM",
    "driver": {"mate": "DriveArm", "type": "distance", "from": 0, "to": 50, "steps": 6},
    "clearance_pair": ["armA-1", "postB-1"]      // optional
  }
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


def _load_spec(path: str) -> dict[str, Any]:
    text = Path(path).read_text(encoding="utf-8")
    spec = json.loads(text)
    if not isinstance(spec, dict):
        raise ValueError("motion_audit spec must be a JSON object")
    if spec.get("kind") != "motion_audit":
        raise ValueError(f"spec kind must be 'motion_audit', got {spec.get('kind')!r}")
    for key in ("assembly", "driver"):
        if key not in spec:
            raise ValueError(f"motion_audit spec missing required key {key!r}")
    drv = spec["driver"]
    for key in ("mate", "type", "from", "to", "steps"):
        if key not in drv:
            raise ValueError(f"driver missing required key {key!r}")
    if drv["type"] not in ("distance", "angle"):
        raise ValueError(f"driver.type must be 'distance' or 'angle', got {drv['type']!r}")
    return spec


def _run_audit(args: argparse.Namespace) -> dict[str, Any]:
    from ..com.earlybind import typed
    from ..com.sw_type_info import wrapper_module
    from ..motion_audit import motion_sweep
    from ..sw_com import get_sw_app

    result: dict[str, Any] = {"tool": "motion_audit", "ok": False}
    try:
        spec = _load_spec(args.spec)
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"spec load failed: {exc}"
        return result
    result["spec"] = spec

    asm_path = spec["assembly"]
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

    drv = spec["driver"]
    pair = spec.get("clearance_pair")
    clearance_pair = tuple(pair) if isinstance(pair, list) and len(pair) == 2 else None

    try:
        sweep = motion_sweep(
            doc,
            mate_name=drv["mate"],
            kind=drv["type"],
            start=float(drv["from"]),
            stop=float(drv["to"]),
            steps=int(drv["steps"]),
            clearance_pair=clearance_pair,
            mod=mod,
        )
        result.update(sweep)
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"motion_sweep failed: {exc!r}"
        return result
    finally:
        # Leave docs open (Close() corrupts the COM channel mid-session); the
        # sweep already restored the driver value and did not save.
        pass

    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-sw-motion",
        description=(
            "Dynamic kinematic verification — drive a named mate through its DOF "
            "and report collision-in-motion + clearance envelope. CLI-only."
        ),
    )
    subs = parser.add_subparsers(dest="tool", required=True, metavar="tool")
    p = subs.add_parser("audit", help="Run a motion audit from a spec JSON.")
    p.add_argument("--spec", required=True, help="Path to a kind:'motion_audit' spec JSON.")
    p.add_argument(
        "--output-dir", dest="output_dir", default="_results",
        help="Directory for the result JSON (default: _results).",
    )
    p.set_defaults(func=_run_audit)
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
    (output_dir / "motion_audit.json").write_text(
        json.dumps(result, indent=2, default=str), encoding="utf-8"
    )
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
