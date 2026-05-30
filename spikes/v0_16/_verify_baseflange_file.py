"""Reopen a committed part (via the bridge's typed OpenDoc6) and confirm the
base flange persisted: (1) select it by name, (2) walk the feature tree with
full exception reporting. Pass the .sldprt path as argv[1]."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
_V15 = Path(__file__).resolve().parents[1] / "v0_15"
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(_V15))

import pythoncom  # noqa: E402
from spike_earlybind_persist import connect_running_sw  # noqa: E402
from ai_sw_bridge import mutate  # noqa: E402


def _name(feat: Any) -> str:
    n = feat.Name
    nm = n() if callable(n) else n
    try:
        t = feat.GetTypeName2
        tn = t() if callable(t) else t
    except Exception:  # noqa: BLE001
        tn = "?"
    return f"{nm} [{tn}]"


def main() -> int:
    path = sys.argv[1]
    pythoncom.CoInitialize()
    try:
        sw = connect_running_sw()
        doc = mutate._open_doc_typed(path)
        if doc is None:
            print("FAILED TO OPEN")
            return 1

        # (1) Name-based selection — robust existence test.
        sel = False
        for sel_type in ("BODYFEATURE", "SHEETMETAL", "REFSURFACE"):
            try:
                if doc.SelectByID("Base-Flange1", sel_type, 0, 0, 0):
                    sel = True
                    print(f"SelectByID('Base-Flange1', {sel_type!r}) -> True")
                    break
            except Exception as e:  # noqa: BLE001
                print(f"SelectByID {sel_type}: {type(e).__name__}: {str(e)[:80]}")
        try:
            doc.ClearSelection2(True)
        except Exception:  # noqa: BLE001
            pass

        # (2) Feature-tree walk with explicit error reporting.
        names: list[str] = []
        try:
            f = doc.FirstFeature()
            guard = 0
            while f is not None and guard < 200:
                guard += 1
                names.append(_name(f))
                f = f.GetNextFeature()
        except Exception as e:  # noqa: BLE001
            names.append(f"<walk stopped: {type(e).__name__}: {str(e)[:80]}>")
        print(f"\n{len(names)} features walked:")
        for n in names:
            print("   ", n)

        has = sel or any("Base-Flange" in n or "SMBaseFlange" in n for n in names)
        print(f"\nHAS BASE FLANGE: {has}")
        title = doc.GetTitle
        sw.CloseDoc(title() if callable(title) else title)
        return 0 if has else 2
    finally:
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    raise SystemExit(main())
