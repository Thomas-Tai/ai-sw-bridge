"""ai-sw-import CLI — foreign geometry import (STEP / IGES → .SLDPRT).

Wave 40 (FR-1-07 audit gap). v1 is import → body + verify ONLY.

Usage::

    ai-sw-import --source <file.step|.stp|.igs|.iges> --output <part.sldprt>
    ai-sw-import --spec <import_spec.json>
    ai-sw-import --source <...> --output <...> --dry-run
    ai-sw-import --source <...> --output <...> --verify-volume <mm3>

Two-stream discipline:

- **stdout**: a single JSON object describing the outcome (machine stream).
- **stderr**: human-readable lifecycle lines (resolved / imported / verified /
  saved). ``--quiet`` suppresses stderr.

Exit codes:

- 0 — success (``ok:true``).
- 2 — CLI / argument error (missing file, bad flag combo).
- 3 — validation failure (typed :class:`ImportValidationError`).
- 4 — COM / runtime failure (LoadFile4 error, bodyless import, volume
  mismatch, SaveAs3 failure).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ..import_geom import (
    ImportResult,
    ImportValidationError,
    import_part,
    parse_import_spec,
    validate_import_spec,
)
from .stability import add_tier, cli_stability
from .streams import add_quiet_flag, apply_quiet


def _emit(payload: dict[str, Any], code: int) -> int:
    print(json.dumps(payload, indent=2))
    return code


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-sw-import",
        description=(
            "Import a STEP or IGES file into a new SOLIDWORKS .SLDPRT as a "
            "dumb B-rep solid (Wave 40, v1). Fail-closed: unsupported "
            "extension, bodyless reference-feature import, and volume "
            "mismatch all abort before/after the COM call with typed errors."
        ),
    )
    add_tier(parser, "experimental")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--spec",
        dest="spec",
        default=None,
        help=(
            "Path to a kind:'import' spec JSON. When set, --source and "
            "--output are taken from the spec (and override flags are "
            "ignored)."
        ),
    )
    group.add_argument(
        "--source",
        dest="source",
        default=None,
        help="Path to the STEP (.step/.stp) or IGES (.igs/.iges) file.",
    )

    parser.add_argument(
        "--output",
        dest="output",
        default=None,
        help=(
            "Path of the .SLDPRT to write. Required with --source; ignored "
            "with --spec (taken from the spec)."
        ),
    )
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help=(
            "Validate the spec and confirm paths / extensions without "
            "touching SOLIDWORKS. Useful for CI pre-flight."
        ),
    )
    parser.add_argument(
        "--verify-volume",
        dest="verify_volume",
        type=float,
        default=None,
        metavar="MM3",
        help=(
            "Assert the imported solid's volume matches MM3 (in mm³) within "
            "--volume-tol. This is the load-bearing gate for round-trip "
            "verification (export a known box → STEP, re-import, assert)."
        ),
    )
    parser.add_argument(
        "--volume-tol",
        dest="volume_tol",
        type=float,
        default=0.01,
        metavar="REL",
        help="Relative tolerance for --verify-volume (default: 0.01 = 1%%).",
    )
    parser.add_argument(
        "--min-bodies",
        dest="min_bodies",
        type=int,
        default=1,
        metavar="N",
        help=(
            "Minimum number of solid bodies required after import "
            "(default: 1). The E4 bodyless-Reference-feature trap fails "
            "this gate."
        ),
    )
    add_quiet_flag(parser)
    return parser


@cli_stability("experimental")
def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    apply_quiet(args)

    if args.spec is not None:
        spec_path = Path(args.spec)
        try:
            spec = parse_import_spec(spec_path)
        except ImportValidationError as exc:
            return _emit(
                {
                    "ok": False,
                    "error": "validation_failed",
                    "path": exc.path,
                    "message": exc.message,
                },
                3,
            )
    else:
        if args.source is None:
            parser.error("either --spec or --source is required")
        if args.output is None:
            parser.error("--output is required with --source")

        # Synthesize a spec envelope so the validator runs the same
        # fail-closed checks for both input modes.
        envelope: dict[str, Any] = {
            "kind": "import",
            "source": args.source,
            "output": args.output,
        }
        if args.verify_volume is not None or args.min_bodies != 1:
            envelope["verify"] = {}
            if args.verify_volume is not None:
                envelope["verify"]["volume_mm3"] = args.verify_volume
                envelope["verify"]["volume_rel_tol"] = args.volume_tol
            if args.min_bodies != 1:
                envelope["verify"]["min_bodies"] = args.min_bodies

        try:
            spec = validate_import_spec(envelope, spec_path=None)
        except ImportValidationError as exc:
            return _emit(
                {
                    "ok": False,
                    "error": "validation_failed",
                    "path": exc.path,
                    "message": exc.message,
                },
                3,
            )

    if args.dry_run:
        return _emit(
            {
                "ok": True,
                "dry_run": True,
                "source": str(spec.source),
                "output": str(spec.output),
                "source_extension": spec.source_extension(),
                "verify": spec.verify,
            },
            0,
        )

    result: ImportResult = import_part(spec)
    payload = result.to_dict()
    payload["dry_run"] = False
    return _emit(payload, 0 if result.ok else 4)


if __name__ == "__main__":
    sys.exit(main())
