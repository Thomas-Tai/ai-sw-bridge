"""Probe ISldWorks for add-in management methods (W7.1-research).

Run with SW open. Prints which of GetEnabledAddIns / EnableAddIn /
LoadAddIn / UnloadAddIn are reachable via late-binding, and what
each returns. NO writes -- observation only.

Spike status: EXPERIMENTAL -- not exercised by CI.
Run manually when a live SOLIDWORKS session is available.

Usage:
    python spikes/v0_13/spike_addin_enumeration.py

Expected output (illustrative, actual names depend on SW install):
    GetEnabledAddIns: tuple ('SOLIDWORKS Toolbox', 'SOLIDWORKS PDM Standard')
    EnableAddIn: present (signature unknown without arg probe)
    LoadAddIn: present (signature unknown without arg probe)
    UnloadAddIn: present (signature unknown without arg probe)

Findings
--------
Record results here after running against a live SW session:

- Does GetEnabledAddIns() return the same names as Tools -> Add-Ins?
  ANSWER: (fill in after running)

- Does UnloadAddIn(name) actually remove the add-in's event hooks,
  or does it return success while subscriptions persist?
  ANSWER: (fill in after running -- behavioral test, not API return code)

- After UnloadAddIn, does a subsequent SaveAs3 exhibit the add-in's
  known interference pattern?
  ANSWER: (fill in after running)

- Are add-in names stable across SW versions? (Case sensitivity,
  "SOLIDWORKS" vs "SolidWorks"?)
  ANSWER: (fill in after running on multiple SW versions)

See Also
--------
- docs/addins_research.md (full research note)
- src/ai_sw_bridge/observe.py :: sw_get_enabled_addins()
- docs/com_failure_modes.md (A-* rows for add-in interference)
"""

from __future__ import annotations

import sys
from typing import Any


def _probe_method(sw: Any, method: str) -> str:
    """Probe a single method on the ISldWorks dispatch object.

    Returns a human-readable description of what was found.
    Never raises -- all exceptions are caught and reported.
    """
    m = getattr(sw, method, None)
    if m is None:
        return "ABSENT"

    if method == "GetEnabledAddIns":
        try:
            result = m()
            return f"{type(result).__name__} {result!r}"
        except Exception as exc:
            return f"REACHED -> {exc!r}"

    # For methods that take arguments, just confirm presence.
    return "present (signature unknown without arg probe)"


def main() -> int:
    """Run the add-in enumeration probe against a live SW session."""
    try:
        import win32com.client
    except ImportError:
        print("ERROR: pywin32 not installed. Run: pip install pywin32")
        return 1

    try:
        sw = win32com.client.Dispatch("SldWorks.Application")
    except Exception as exc:
        print(f"ERROR: Could not acquire SldWorks.Application: {exc!r}")
        print("Ensure SOLIDWORKS is running before executing this spike.")
        return 1

    print(f"SW RevisionNumber: {sw.RevisionNumber}")
    print()

    methods = ("GetEnabledAddIns", "EnableAddIn", "LoadAddIn", "UnloadAddIn")
    for method in methods:
        result = _probe_method(sw, method)
        print(f"  {method}: {result}")

    # Extended probe: if GetEnabledAddIns returned names, try reading
    # each add-in's exposed object via GetAddInObject.
    print()
    print("--- Extended probe: GetAddInObject per loaded add-in ---")
    getter = getattr(sw, "GetEnabledAddIns", None)
    if getter is not None:
        try:
            names = getter()
            if names and isinstance(names, (tuple, list)):
                for name in names:
                    try:
                        obj = sw.GetAddInObject(str(name))
                        obj_type = type(obj).__name__
                        print(f"  GetAddInObject({name!r}): {obj_type}")
                    except Exception as exc:
                        print(f"  GetAddInObject({name!r}): {exc!r}")
            else:
                print("  (no add-ins loaded or unexpected return type)")
        except Exception as exc:
            print(f"  GetEnabledAddIns() failed: {exc!r}")
    else:
        print("  (GetEnabledAddIns not available)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
