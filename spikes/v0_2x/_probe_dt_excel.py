"""Seat probe (fire 3): populate the design table via the Excel worksheet OLE.

SetEntryText can't build a blank table. The canonical route is EditTable2()
-> the embedded Excel.Worksheet -> write cells -> UpdateModel. This tests
whether the Excel-OLE design-table route works out-of-process (the W36 wall
class) or drives distinct configs.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

ARTIFACTS = Path(__file__).resolve().parent / "_artifacts_w53"
HEADER = "D1@Block_A"
CONFIGS = [("Small", "25"), ("Large", "75")]


def _resolve(obj: Any, name: str) -> Any:
    v = getattr(obj, name)
    return v() if callable(v) else v


def _vol_mm3(mdoc2: Any) -> float | None:
    try:
        mp = mdoc2.Extension.CreateMassProperty
        if callable(mp):
            mp = mp()
        return float(_resolve(mp, "Volume")) * 1e9
    except Exception:
        return None


def _per_config_vol(mdoc2: Any) -> dict:
    out = {}
    for cn in list(mdoc2.GetConfigurationNames() or []):
        try:
            mdoc2.ShowConfiguration2(cn)
        except Exception:
            pass
        mdoc2.ForceRebuild3(True)
        out[cn] = _vol_mm3(mdoc2)
    return out


def main() -> int:
    from ai_sw_bridge.com.earlybind import typed, typed_qi
    from ai_sw_bridge.com.sw_type_info import wrapper_module
    from ai_sw_bridge.sw_com import get_sw_app

    mod = wrapper_module()
    sw = get_sw_app()
    tsw = typed(sw, "ISldWorks", module=mod)

    part = next(iter(ARTIFACTS.glob("W53_dt_test*.SLDPRT")), None)
    ret = tsw.OpenDoc6(str(part), 1, 1, "", 0, 0)
    mdoc2 = typed_qi(
        ret[0] if isinstance(ret, tuple) else ret, "IModelDoc2", module=mod
    )
    mdoc2.ForceRebuild3(True)

    mdoc2.InsertFamilyTableNew()
    dt = typed_qi(mdoc2.GetDesignTable(), "IDesignTable", module=mod)
    print(f"Attach: {dt.Attach()}")

    # --- EditTable2 -> Excel worksheet ---
    try:
        ws = dt.EditTable2(False)
    except Exception as exc:
        print(f"EditTable2 raised: {exc!r}")
        return 1
    print(f"EditTable2 -> {type(ws).__name__} ({'None' if ws is None else 'got'})")
    if ws is None:
        print("=== WALL: EditTable2 returned None (no Excel worksheet o-o-p) ===")
        return 1

    # Dump what SW pre-filled
    try:
        used = ws.UsedRange
        nr = used.Rows.Count
        nc = used.Columns.Count
        print(f"used range: {nr} rows x {nc} cols")
        for r in range(1, min(nr, 8) + 1):
            row = [ws.Cells(r, c).Value for c in range(1, min(nc, 6) + 1)]
            print(f"  excel row {r}: {row}")
    except Exception as exc:
        print(f"used-range dump err: {exc!r}")

    # SW layout (from the dump): A1=title, ROW 2 = parameter header (B2+),
    # column A from row 3 = config names (A3="First Instance"), values B3+.
    try:
        ws.Cells(2, 2).Value = HEADER  # B2 = parameter header
        for i, (cn, val) in enumerate(CONFIGS):
            ws.Cells(3 + i, 1).Value = cn  # A3, A4 = config names
            ws.Cells(3 + i, 2).Value = val  # B3, B4 = values
        print(f"wrote header B2={HEADER!r}, configs at A3+/B3+: {CONFIGS}")
    except Exception as exc:
        print(f"cell write err: {exc!r}")
        return 1

    # Commit: UpdateTable then UpdateModel
    try:
        print(f"UpdateTable -> {dt.UpdateTable(2, True)}")
    except Exception as exc:
        print(f"UpdateTable err: {exc!r}")
    try:
        print(f"UpdateModel -> {dt.UpdateModel()}")
    except Exception as exc:
        print(f"UpdateModel err: {exc!r}")
    try:
        dt.Detach()
    except Exception:
        pass
    mdoc2.ForceRebuild3(True)

    names = list(mdoc2.GetConfigurationNames() or [])
    vols = _per_config_vol(mdoc2)
    distinct = sorted({round(v, 1) for v in vols.values() if v is not None})
    print(f"\nconfigs after: {names}")
    print(f"volumes: {vols}")
    print(f"distinct: {distinct}")
    if len(distinct) < 2 or len(names) < 2:
        print("=== NO-GO: not discriminated ===")
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
        return 2

    save_path = str(ARTIFACTS / "W53_dt_pop.SLDPRT")
    mdoc2.SaveAs3(save_path, 0, 0)
    sw.CloseAllDocuments(True)
    time.sleep(0.5)
    ret2 = tsw.OpenDoc6(save_path, 1, 1, "", 0, 0)
    mdoc2b = typed_qi(
        ret2[0] if isinstance(ret2, tuple) else ret2, "IModelDoc2", module=mod
    )
    names2 = list(mdoc2b.GetConfigurationNames() or [])
    vols2 = _per_config_vol(mdoc2b)
    distinct2 = sorted({round(v, 1) for v in vols2.values() if v is not None})
    print(f"\nreopen configs: {names2}")
    print(f"reopen volumes: {vols2}")
    print(f"reopen distinct: {distinct2}")
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass
    print(
        f"\n=== {'GREEN' if len(distinct2) >= 2 else 'PARTIAL (in-session only)'} ==="
    )
    return 0 if len(distinct2) >= 2 else 3


if __name__ == "__main__":
    raise SystemExit(main())
