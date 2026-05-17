"""
Spike G - probe user preference toggle IDs to find the right one for
"Modify Dimension popup on AddDimension2".

The hypothesis is that swInputDimValOnCreate is not ID=8 on this SW build,
since SetUserPreferenceToggle(8, False) does NOT suppress the popup in
practice (verified via Spike F and live cylinder build).

Strategy: dump GetUserPreferenceToggle for a range of IDs. Run this spike
twice:
  (a) With "Enable on screen numeric input on entity creation" CHECKED in
      Tools > Options > System Options > Sketch.
  (b) With the same option UNCHECKED.

Diff the two outputs. The ID whose value flips between True and False is
the correct constant for this SW build.

Then we patch builder.py to use that ID.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

from ai_sw_bridge.sw_com import get_sw_app  # noqa: E402


def run() -> dict:
    sw = get_sw_app()
    # The swUserPreferenceToggle enum spans roughly 0..400 in SW 2024.
    # We dump a sweep so we can diff between GUI states.
    values: dict[int, bool] = {}
    errors: dict[int, str] = {}
    for pref_id in range(0, 500):
        try:
            v = sw.GetUserPreferenceToggle(pref_id)
            values[pref_id] = bool(v)
        except Exception as e:
            errors[pref_id] = repr(e)
            # First error often means we've gone past the valid range. Continue
            # a bit more in case of gaps, then stop.
            if pref_id > 50 and len([1 for k in errors if k > pref_id - 10]) > 8:
                break
    return {
        "values": values,
        "errors": errors,
        "max_valid_id": max(values.keys()) if values else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--label",
        default="run",
        help="label for this run (e.g. 'checked' or 'unchecked')",
    )
    parser.add_argument(
        "--out", default=None, help="save JSON to file at this path instead of stdout"
    )
    args = parser.parse_args()

    out = run()
    out["label"] = args.label

    text = json.dumps(out, indent=2, default=str)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
