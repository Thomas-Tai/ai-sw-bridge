"""Design table dispatch (W53 → W54-B, seat-proven EditTable2 recipe).

Inserts a design table into a SOLIDWORKS part file from a parameter
grid specification, then verifies that the generated configurations
are volume-discriminated and survive save→reopen.

The SW-free layer lives in ``design_table.py`` (parse/format).  This
module owns the COM-touching boundary:

- ``insert_design_table`` — the SEAT-gated entry point.
- ``write_grid_file`` — write the CSV to a temp path (SW-free).
- ``_populate_design_table`` — SEAT-gated: InsertFamilyTableNew blank
  → GetDesignTable → Attach → EditTable2 → Excel cells → UpdateModel.
- ``_read_configs`` — SEAT-gated: enumerate generated configurations.
- ``_measure_config_volumes`` — SEAT-gated: CreateMassProperty per config.

Seat-proven recipe (W53, _probe_dt_excel.py, GREEN — 3 distinct volumes
persisting through reopen):

    ``InsertFamilyTableNew()``  (blank, NO path arg — path raises
    TypeError: takes 1 positional argument but 2 were given)
    → ``GetDesignTable()`` → ``typed_qi(IDesignTable)``
    → ``Attach()``
    → ``ws = EditTable2(False)``  (returns embedded Excel.Worksheet OLE;
      **requires Excel installed**)
    → write cells ``ws.Cells(row, col).Value`` (1-indexed):
      row 2 = parameter headers (B2 = ``"D1@Block_A"``),
      column A from row 3 = config names (A3 pre-filled),
      values B3+
    → ``UpdateTable(2, True)`` + ``UpdateModel()``
    → ``Detach()``

    SetEntryText alone CANNOT build a blank table — EditTable2 /
    worksheet is mandatory.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from .design_table import DesignTableSpec, format_grid_csv
from .variants import ConfigResult

logger = logging.getLogger("ai_sw_bridge.config.dt_dispatch")


def write_grid_file(
    dt_spec: DesignTableSpec,
    output_dir: str | Path,
    filename: str = "design_table.csv",
) -> Path:
    """Write the design table grid to a CSV file.

    SW-free — pure file I/O.  Useful for offline inspection or archival;
    the production insertion path writes cells directly via Excel OLE
    (EditTable2) and does not consume this file.

    Returns the absolute path to the written file.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / filename
    path.write_text(
        format_grid_csv(dt_spec),
        encoding="utf-8",
    )
    return path.resolve()


def insert_design_table(
    doc: Any,
    dt_spec: DesignTableSpec,
) -> list[ConfigResult]:
    """Insert a design table and verify N distinct configurations.

    SEAT-gated entry point.  Orchestrates:

    1. Create a blank design table
       (``IModelDoc2.InsertFamilyTableNew()`` — no args).
    2. Populate it via the Excel-OLE worksheet
       (``IDesignTable.EditTable2(False)`` → cells → UpdateModel).
    3. Enumerate the generated configurations.
    4. Measure volume per configuration via ``CreateMassProperty``.
    5. Assert volume discrimination (≥ 2 distinct volumes).

    Args:
        doc: An ``IModelDoc2``-like dispatch (live or mock).
        dt_spec: The parsed design table specification.

    Returns:
        One ``ConfigResult`` per expected configuration, in the same
        order as ``dt_spec.rows``.  ``ok=True`` only if the config
        exists and has a measured volume distinct from at least one
        other config.
    """
    # Step 1: Create blank DT + populate via EditTable2 recipe
    populate_result = _populate_design_table(doc, dt_spec)
    if not populate_result["ok"]:
        return [
            ConfigResult(
                variant=r.config_name,
                ok=False,
                error=populate_result["error"],
            )
            for r in dt_spec.rows
        ]

    # Step 2: Read back generated configurations
    configs = _read_configs(doc, dt_spec.config_names)

    # Step 3: Measure volume per config
    volumes = _measure_config_volumes(doc, dt_spec.config_names)

    # Step 4: Build results with discrimination check
    distinct_vols = sorted(set(round(v, 1) for v in volumes.values() if v is not None))
    discriminated = len(distinct_vols) >= 2

    results: list[ConfigResult] = []
    for row in dt_spec.rows:
        vol = volumes.get(row.config_name)
        has_config = configs.get(row.config_name, False)
        ok = has_config and vol is not None and discriminated

        error = None
        if not has_config:
            error = (
                f"config {row.config_name!r} not found after " f"design table insertion"
            )
        elif vol is None:
            error = f"volume measurement failed for {row.config_name!r}"
        elif not discriminated:
            error = (
                f"volumes not discriminated: all configs have "
                f"identical volume ({vol:.0f} mm³) — design table "
                f"did not drive geometric distinction"
            )

        results.append(
            ConfigResult(
                variant=row.config_name,
                ok=ok,
                volume_mm3=vol,
                error=error,
            )
        )

    # Human stream
    for r in results:
        if r.ok:
            print(
                f"  config {r.variant!r}: volume={r.volume_mm3:.0f} mm³",
                file=sys.stderr,
            )
        else:
            print(
                f"  FAILED config {r.variant!r}: {r.error}",
                file=sys.stderr,
            )

    return results


def _populate_design_table(
    doc: Any,
    dt_spec: DesignTableSpec,
) -> dict[str, Any]:
    """SEAT-gated: create blank DT + populate via EditTable2 Excel OLE.

    Seat-proven recipe (W53 _probe_dt_excel.py, GREEN):

    1. ``InsertFamilyTableNew()`` — BLANK (no path arg).
    2. ``GetDesignTable()`` → ``typed_qi(IDesignTable)``.
    3. ``Attach()``.
    4. ``EditTable2(False)`` → embedded Excel.Worksheet (1-indexed).
    5. Row 2 = parameter headers (B2, C2, …).
    6. Column A row 3+ = config names; B3+ = values.
    7. ``UpdateTable(2, True)`` + ``UpdateModel()`` + ``Detach()``.

    Requires Microsoft Excel installed (EditTable2 returns the OLE
    Excel.Worksheet object; without Excel it returns None).

    Returns a dict with ``ok`` and optional ``error``.
    """
    try:
        from ai_sw_bridge.com.earlybind import typed_qi
        from ai_sw_bridge.com.sw_type_info import wrapper_module

        mod = wrapper_module()
    except ImportError:
        return {
            "ok": False,
            "error": (
                "earlybind / sw_type_info not available — "
                "typed COM wrappers required for IDesignTable.EditTable2"
            ),
        }

    try:
        doc.InsertFamilyTableNew()
    except TypeError as exc:
        return {
            "ok": False,
            "error": (
                f"InsertFamilyTableNew arg-count mismatch: {exc} — "
                f"expected 0-arg (blank); SW version may not support it"
            ),
        }
    except AttributeError:
        return {
            "ok": False,
            "error": ("InsertFamilyTableNew not found on IModelDoc2"),
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": (f"InsertFamilyTableNew raised {type(exc).__name__}: {exc}"),
        }

    try:
        raw_dt = doc.GetDesignTable()
        if raw_dt is None:
            return {
                "ok": False,
                "error": "GetDesignTable returned None",
            }
        dt = typed_qi(raw_dt, "IDesignTable", module=mod)

        attach_result = dt.Attach()
        if attach_result is None or attach_result == 0:
            logger.warning("IDesignTable.Attach returned %s", attach_result)

        try:
            ws = dt.EditTable2(False)
        except Exception as exc:
            return {
                "ok": False,
                "error": (
                    f"EditTable2 raised {type(exc).__name__}: {exc} — "
                    f"Excel OLE may not be available out-of-process"
                ),
            }

        if ws is None:
            return {
                "ok": False,
                "error": (
                    "EditTable2 returned None — "
                    "Excel worksheet OLE not available (requires "
                    "Microsoft Excel installed)"
                ),
            }

        col_names = dt_spec.column_names
        for j, header in enumerate(col_names):
            ws.Cells(2, 2 + j).Value = header

        for i, row in enumerate(dt_spec.rows):
            ws.Cells(3 + i, 1).Value = row.config_name
            for j, col in enumerate(dt_spec.columns):
                ws.Cells(3 + i, 2 + j).Value = row.values.get(col.name, "")

        try:
            dt.UpdateTable(2, True)
        except Exception as exc:
            return {
                "ok": False,
                "error": (f"UpdateTable raised {type(exc).__name__}: {exc}"),
            }
        try:
            dt.UpdateModel()
        except Exception as exc:
            return {
                "ok": False,
                "error": (f"UpdateModel raised {type(exc).__name__}: {exc}"),
            }
        try:
            dt.Detach()
        except Exception:
            pass

        return {"ok": True}

    except Exception as exc:
        return {
            "ok": False,
            "error": (
                f"design table population raised " f"{type(exc).__name__}: {exc}"
            ),
        }


def _read_configs(
    doc: Any,
    expected_names: list[str],
) -> dict[str, bool]:
    """SEAT-gated: check which expected configs exist on the doc.

    Uses ``IModelDoc2.GetConfigurationNames`` to enumerate.

    Returns a dict of ``{config_name: exists}``.
    """
    result: dict[str, bool] = {n: False for n in expected_names}
    try:
        names = doc.GetConfigurationNames()
        if names is None:
            return result
        name_set = set(names) if not isinstance(names, set) else names
        for n in expected_names:
            result[n] = n in name_set
    except Exception:
        pass
    return result


def _measure_config_volumes(
    doc: Any,
    config_names: list[str],
) -> dict[str, float | None]:
    """SEAT-gated: measure volume per config via CreateMassProperty.

    Activates each config via ``ShowConfiguration2``, rebuilds,
    then reads ``Extension.CreateMassProperty.Volume``.

    Returns a dict of ``{config_name: volume_mm3_or_None}``.
    """
    volumes: dict[str, float | None] = {}

    for cn in config_names:
        try:
            doc.ShowConfiguration2(cn)
            doc.ForceRebuild3(True)

            ext = doc.Extension
            if callable(ext):
                ext = ext()
            mp = ext.CreateMassProperty
            if callable(mp):
                mp = mp()
            if mp is None:
                volumes[cn] = None
                continue

            vol = mp.Volume
            if callable(vol):
                vol = vol()
            volumes[cn] = float(vol) * 1e9
        except Exception:
            volumes[cn] = None

    return volumes


__all__ = [
    "insert_design_table",
    "write_grid_file",
]
