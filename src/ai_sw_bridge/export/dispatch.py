"""Export dispatch (spec.md §6, FR-1-03, todolist P1.1).

Iterates the ``export:`` block from a schema-v2 spec, dispatches each
entry to the correct save path, and collects results.

Two-stream discipline (``UIUX.md`` §8):
  - **Human stream** (stderr): one line per file written, with path.
  - **Machine stream**: ``ExportResult`` list returned to the caller;
    the caller (builder / CLI) folds it into the JSON result.

The SW-free skeleton validates format names, resolves output paths,
and structures the dispatch loop. The actual COM save calls are:

- **SaveAs3-direct** formats (STEP / IGES / Parasolid / STL / 3MF /
  DXF): use the proven ``doc.SaveAs3(path, 0, version)`` call from
  ``builder.py``. The extension in the path selects the exporter.
  SW-free in the sense that the call shape is already proven for
  ``.sldprt``; the per-format extension strings need a seat to confirm.
- **ExportPdfData** (``pdf``): needs ``IExportPdfData`` — SEAT-gated.
- **Flat-pattern DXF** (``dxf_flat``): needs the flat-pattern config
  activated first — SEAT-gated + gated by S-SHEETMETAL.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .formats import (
    EXPORT_FORMATS,
    ExportFormat,
    SaveMethod,
    resolve_format,
)

logger = logging.getLogger("ai_sw_bridge.export")


@dataclass(frozen=True)
class ExportRequest:
    """One entry from the spec's ``export:`` block.

    Attributes:
        format: Format name from ``EXPORT_FORMATS`` (e.g. ``"step214"``).
        output_dir: Directory to write the exported file into.
        filename: Override filename (without extension). When ``None``,
            the part name is used.
    """

    format: str
    output_dir: Path
    filename: str | None = None


@dataclass
class ExportResult:
    """Outcome of one export attempt.

    Attributes:
        format: The format name that was requested.
        path: Resolved absolute path of the output file (set even on
            failure, so the caller knows where it *would* have landed).
        ok: ``True`` if the file was written and verified.
        error: Human-readable error string on failure; ``None`` on
            success.
    """

    format: str
    path: str
    ok: bool
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "format": self.format,
            "path": self.path,
            "ok": self.ok,
        }
        if self.error is not None:
            out["error"] = self.error
        return out


def resolve_output_path(
    request: ExportRequest,
    part_name: str,
    fmt: ExportFormat,
) -> Path:
    """Compute the absolute output path for an export request.

    Uses ``request.filename`` if set, otherwise ``part_name``. Appends
    the format's extension. Creates the output directory if missing.
    """
    stem = request.filename or part_name
    out_path = (request.output_dir / f"{stem}{fmt.extension}").resolve()
    request.output_dir.mkdir(parents=True, exist_ok=True)
    return out_path


def export_all(
    doc: Any,
    requests: list[ExportRequest],
    part_name: str,
) -> list[ExportResult]:
    """Export the open document in every requested format.

    Args:
        doc: An ``IModelDoc2``-like dispatch object (live or mock).
        requests: Parsed entries from the spec's ``export:`` block.
        part_name: The part name, used as the default filename stem.

    Returns:
        One ``ExportResult`` per request, in the same order. Failures
        are captured per-entry (one bad format doesn't abort the rest).

    Side effects:
        Prints each written path to stderr (human stream).
    """
    results: list[ExportResult] = []
    for req in requests:
        result = _export_one(doc, req, part_name)
        if result.ok:
            print(f"  exported {result.format} → {result.path}", file=sys.stderr)
        else:
            print(
                f"  FAILED {result.format} → {result.path}: {result.error}",
                file=sys.stderr,
            )
        results.append(result)
    return results


def _export_one(doc: Any, req: ExportRequest, part_name: str) -> ExportResult:
    """Dispatch one export request to the correct save path."""
    try:
        fmt = resolve_format(req.format)
    except ValueError as exc:
        return ExportResult(
            format=req.format,
            path="",
            ok=False,
            error=str(exc),
        )

    out_path = resolve_output_path(req, part_name, fmt)
    path_str = str(out_path)

    if fmt.save_method == SaveMethod.SAVEAS3_DIRECT:
        return _saveas3_direct(doc, fmt, out_path)
    if fmt.save_method == SaveMethod.EXPORT_PDF:
        return ExportResult(
            format=fmt.name,
            path=path_str,
            ok=False,
            error=(
                "PDF export via IExportPdfData is SEAT-gated (P1.1). "
                "The SaveAs3-direct path may work for single-sheet PDF; "
                "multi-sheet needs a live SW seat to confirm the marshal."
            ),
        )
    if fmt.save_method == SaveMethod.FLAT_PATTERN_DXF:
        return ExportResult(
            format=fmt.name,
            path=path_str,
            ok=False,
            error=(
                "Flat-pattern DXF export is SEAT-gated (P1.1) and gated "
                "by S-SHEETMETAL. Needs the flat-pattern config activated "
                "before ExportToDWG2."
            ),
        )
    return ExportResult(
        format=fmt.name,
        path=path_str,
        ok=False,
        error=f"Unhandled save method: {fmt.save_method}",
    )


def _saveas3_direct(
    doc: Any, fmt: ExportFormat, out_path: Path
) -> ExportResult:
    """SaveAs3-direct export path.

    Uses the same call shape as ``builder._save_as_with_verification``:
    ``doc.SaveAs3(path, 0, version)``. The file extension in the path
    selects the exporter. Post-condition: file exists with non-zero
    size.

    The per-format extension string is 🔴 SEAT — confirmed on a live
    seat per the spike-first law. This skeleton implements the call
    shape; the format strings are not yet confirmed.
    """
    path_str = str(out_path)
    try:
        err = doc.SaveAs3(path_str, 0, fmt.save_version)
    except Exception as exc:
        return ExportResult(
            format=fmt.name,
            path=path_str,
            ok=False,
            error=f"SaveAs3 raised {type(exc).__name__}: {exc}",
        )

    err_code = int(err) if err is not None else 0
    if err_code != 0:
        return ExportResult(
            format=fmt.name,
            path=path_str,
            ok=False,
            error=f"SaveAs3 returned swFileSaveError={err_code}",
        )

    if not out_path.exists() or out_path.stat().st_size == 0:
        return ExportResult(
            format=fmt.name,
            path=path_str,
            ok=False,
            error="SaveAs3 returned NoError but file is missing or empty",
        )

    return ExportResult(format=fmt.name, path=path_str, ok=True)
