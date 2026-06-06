"""Export format registry (spec.md §6, FR-1-03).

Maps each declarative format name to the file extension and the
``IModelDoc2.SaveAs3`` call pattern needed to produce it.

The format *names* and *extensions* are SW-free (pure data). The actual
``SaveAs3`` call that writes each file is the SEAT-gated portion — the
dispatch table records which call path each format uses, but the live
COM invocation is confirmed on a seat per the spike-first law.

Format categories:

- **SaveAs3-direct** — extension determines format; the proven
  ``doc.SaveAs3(path, 0, version)`` call writes the file (same call
  already proven for ``.sldprt`` in ``builder.py``). This covers
  STEP / IGES / Parasolid / STL / 3MF.
- **Special** — need a dedicated API path (PDF uses ``IExportPdfData``
  for multi-sheet; flat-pattern DXF activates the flat-pattern config
  then exports). These are SEAT-gated and stubbed here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class SaveMethod(Enum):
    """Which COM call path produces this format.

    SAVEAS3_DIRECT: the proven ``doc.SaveAs3(path, 0, version)`` call
    with the extension in the path selecting the format. Already proven
    for ``.sldprt``; SW uses the extension to pick the exporter.

    EXPORT_PDF: ``IExportPdfData`` for multi-sheet PDF export. Needs a
    seat to confirm the marshal shape.

    FLAT_PATTERN_DXF: activates the flat-pattern configuration, then
    ``ExportToDWG2`` or ``SaveAs3`` with ``.dxf``. Needs S-SHEETMETAL
    to also be GREEN (flat pattern only exists on sheet-metal parts).
    """

    SAVEAS3_DIRECT = "saveas3_direct"
    EXPORT_PDF = "export_pdf"
    FLAT_PATTERN_DXF = "flat_pattern_dxf"


@dataclass(frozen=True)
class ExportFormat:
    """One exportable format.

    Attributes:
        name: The spec-facing format identifier (e.g. ``"step214"``).
            Used in the ``export:`` block's ``format`` field.
        extension: File extension including the dot (e.g. ``".step"``).
        save_method: Which COM call path produces this format.
        save_version: ``SaveAs3`` third arg. 0 = current SW session
            version. Non-zero targets an older format year (only
            meaningful for formats where SW supports version targeting,
            e.g. STEP AP203 vs AP214).
        description: One-line human description for docs / error msgs.
        seat_confirmed: ``False`` until the format string is confirmed
            on a live SW seat (spike-first law). The SW-free skeleton
            ships with all formats unconfirmed.
    """

    name: str
    extension: str
    save_method: SaveMethod
    save_version: int = 0
    description: str = ""
    seat_confirmed: bool = False


EXPORT_FORMATS: dict[str, ExportFormat] = {
    "step214": ExportFormat(
        name="step214",
        extension=".step",
        save_method=SaveMethod.SAVEAS3_DIRECT,
        description="STEP AP-214 (AutoMotive) — the default STEP flavor",
        seat_confirmed=True,
    ),
    "step203": ExportFormat(
        name="step203",
        extension=".step",
        save_method=SaveMethod.SAVEAS3_DIRECT,
        save_version=1,
        description="STEP AP-203 — older STEP, limited PMIs",
        seat_confirmed=True,
    ),
    "iges": ExportFormat(
        name="iges",
        extension=".igs",
        save_method=SaveMethod.SAVEAS3_DIRECT,
        description="IGES — legacy surface exchange",
        seat_confirmed=True,
    ),
    "parasolid": ExportFormat(
        name="parasolid",
        extension=".x_t",
        save_method=SaveMethod.SAVEAS3_DIRECT,
        description="Parasolid text format — Siemens NX / Solid Edge exchange",
        seat_confirmed=True,
    ),
    "stl": ExportFormat(
        name="stl",
        extension=".stl",
        save_method=SaveMethod.SAVEAS3_DIRECT,
        description="STL — tessellated mesh for 3D printing",
        seat_confirmed=True,
    ),
    "3mf": ExportFormat(
        name="3mf",
        extension=".3mf",
        save_method=SaveMethod.SAVEAS3_DIRECT,
        description="3MF — modern 3D print format with color/material",
        seat_confirmed=True,
    ),
    "pdf": ExportFormat(
        name="pdf",
        extension=".pdf",
        save_method=SaveMethod.EXPORT_PDF,
        description="PDF — single-sheet or multi-sheet via IExportPdfData",
        seat_confirmed=True,
    ),
    "dxf": ExportFormat(
        name="dxf",
        extension=".dxf",
        save_method=SaveMethod.SAVEAS3_DIRECT,
        description="DXF — general 2D/3D exchange (Drawing docs only; Part→DXF needs Drawing pipeline)",
        seat_confirmed=True,  # W33 seat-confirmed: SaveAs3(path, 0, 0) with .dxf extension
    ),
    "dxf_flat": ExportFormat(
        name="dxf_flat",
        extension=".dxf",
        save_method=SaveMethod.FLAT_PATTERN_DXF,
        description="DXF flat pattern — sheet-metal unfold (needs S-SHEETMETAL)",
    ),
}

EXPORT_FORMAT_NAMES: frozenset[str] = frozenset(EXPORT_FORMATS)


def resolve_format(name: str) -> ExportFormat:
    """Look up a format by name. Raises ``ValueError`` on unknown names."""
    try:
        return EXPORT_FORMATS[name]
    except KeyError:
        known = ", ".join(sorted(EXPORT_FORMAT_NAMES))
        raise ValueError(
            f"Unknown export format {name!r}. Known formats: {known}"
        ) from None
