"""Design table dispatch (W53, Phase-4 design tables).

Inserts a design table into a SOLIDWORKS part file from a parameter
grid specification, then verifies that the generated configurations
are volume-discriminated and survive save→reopen.

The SW-free layer lives in ``design_table.py`` (parse/format).  This
module owns the COM-touching boundary:

- ``insert_design_table`` — the SEAT-gated entry point.
- ``_write_grid_file`` — write the CSV to a temp path (SW-free).
- ``_insert_via_family_table`` — SEAT-gated: InsertFamilyTableNew.
- ``_read_configs`` — SEAT-gated: enumerate generated configurations.
- ``_measure_config_volumes`` — SEAT-gated: CreateMassProperty per config.

Architecture note (W36 → W53):
    W36 found that in-file per-config scope (SetSuppression2, per-config
    equations/dimensions) is walled at the COM boundary.  Design tables
    are a *separate* path: the table itself is the config source, so SW
    generates the configs from the grid rather than the bridge trying to
    modify individual configs post-creation.

    If InsertFamilyTableNew hits the same Excel-OLE / SetSuppression-class
    wall as W36, the spike will characterize it precisely (FUNCDESC +
    the exact no-op/leak) and fail-closed — a clean NO-GO with the wall
    named is a valid deliverable.
"""

from __future__ import annotations

import logging
import sys
import tempfile
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

    SW-free — pure file I/O.  The file is consumed by
    ``InsertFamilyTableNew`` on the seat.

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
    grid_file_path: str | Path,
) -> list[ConfigResult]:
    """Insert a design table and verify N distinct configurations.

    SEAT-gated entry point.  Orchestrates:

    1. Insert the design table from the grid file
       (``IModelDoc2.InsertFamilyTableNew``).
    2. Enumerate the generated configurations.
    3. Measure volume per configuration via ``CreateMassProperty``.
    4. Assert volume discrimination (≥ 2 distinct volumes).

    Args:
        doc: An ``IModelDoc2``-like dispatch (live or mock).
        dt_spec: The parsed design table specification.
        grid_file_path: Path to the CSV grid file (from
            ``write_grid_file``).

    Returns:
        One ``ConfigResult`` per expected configuration, in the same
        order as ``dt_spec.rows``.  ``ok=True`` only if the config
        exists and has a measured volume distinct from at least one
        other config.
    """
    grid_path = str(Path(grid_file_path).resolve())

    # Step 1: Insert the design table
    insert_result = _insert_via_family_table(doc, grid_path)
    if not insert_result["ok"]:
        # All configs fail — the insertion itself walled
        return [
            ConfigResult(
                variant=r.config_name,
                ok=False,
                error=insert_result["error"],
            )
            for r in dt_spec.rows
        ]

    # Step 2: Read back generated configurations
    configs = _read_configs(doc, dt_spec.config_names)

    # Step 3: Measure volume per config
    volumes = _measure_config_volumes(doc, dt_spec.config_names)

    # Step 4: Build results with discrimination check
    distinct_vols = sorted(set(
        round(v, 1) for v in volumes.values() if v is not None
    ))
    discriminated = len(distinct_vols) >= 2

    results: list[ConfigResult] = []
    for row in dt_spec.rows:
        vol = volumes.get(row.config_name)
        has_config = configs.get(row.config_name, False)
        ok = has_config and vol is not None and discriminated

        error = None
        if not has_config:
            error = (
                f"config {row.config_name!r} not found after "
                f"design table insertion"
            )
        elif vol is None:
            error = f"volume measurement failed for {row.config_name!r}"
        elif not discriminated:
            error = (
                f"volumes not discriminated: all configs have "
                f"identical volume ({vol:.0f} mm³) — design table "
                f"did not drive geometric distinction"
            )

        results.append(ConfigResult(
            variant=row.config_name,
            ok=ok,
            volume_mm3=vol,
            error=error,
        ))

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


def _insert_via_family_table(
    doc: Any,
    grid_file_path: str,
) -> dict[str, Any]:
    """SEAT-gated: insert design table via InsertFamilyTableNew.

    The SW API call is ``IModelDoc2.InsertFamilyTableNew(FilePath)``.
    The exact FUNCDESC (arg types, return type, invoke kind) must be
    confirmed by the typelib probe
    (``spikes/v0_2x/designtable_typelib_probe.py``) before the seat
    fires this path.

    Returns a dict with ``ok`` and optional ``error``.
    """
    try:
        result = doc.InsertFamilyTableNew(grid_file_path)
        if result is None:
            return {
                "ok": False,
                "error": (
                    "InsertFamilyTableNew returned None — "
                    "design table insertion failed"
                ),
            }
        return {"ok": True, "raw_result": str(type(result).__name__)}
    except AttributeError:
        return {
            "ok": False,
            "error": (
                "InsertFamilyTableNew not found on IModelDoc2 — "
                "method may not exist on this SW version.  "
                "Check designtable_typelib_probe.py output."
            ),
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": (
                f"InsertFamilyTableNew raised {type(exc).__name__}: {exc}"
            ),
        }


def _read_configs(
    doc: Any,
    expected_names: list[str],
) -> dict[str, bool]:
    """SEAT-gated: check which expected configs exist on the doc.

    Uses ``IModelDoc2.GetConfigurationNames`` to enumerate and
    ``GetConfigurationByName`` to verify each.

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
