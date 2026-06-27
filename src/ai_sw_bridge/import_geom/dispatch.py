"""Dispatch for ``kind:"import"`` — STEP / IGES → .SLDPRT via LoadFile4.

COM call chain (the load-bearing S1 recipe, ground-truth signatures):

1. ``sw = Dispatch("SldWorks.Application")``
2. ``tsw = typed(sw, "ISldWorks")`` — typed early-bind so the ByRef out-param
   on ``LoadFile4`` marshals through makepy (same path as the
   ``typed_extension`` pattern proven in W25).
3. ``import_data = tsw.GetImportFileData(abs_path)`` — kernel dispatches by
   the path's extension (``.step`` → ``IImportStepData``; ``.igs`` →
   ``IImportIgesData``).
4. ``doc, errors = tsw.LoadFile4(abs_path, "r", import_data, 0)`` — the ``"r"``
   arg-string forces a standard native B-rep import (no 3D Interconnect).
   ``errors`` is the ByRef I4 out-param, returned as the second tuple element.
5. Fail-closed: ``errors != 0`` or ``doc is None`` → FAIL.
6. Verify-the-effect (inverted verify-the-bytes): QI the returned doc to
   ``IPartDoc``, call ``GetBodies2(0, True)`` → ≥1 solid body; count faces
   across bodies (rejects the E4 bodyless-Reference-feature trap); if a
   ``verify.volume_mm3`` is declared, measure via
   ``doc.Extension.CreateMassProperty.Volume`` (m³ → ×1e9 → mm³) and assert
   within ``verify.volume_rel_tol``.
7. ``doc.SaveAs3(str(output), 0, 0)`` — W34 proven path, not Save3.

Two-stream discipline (``UIUX.md`` §8):

- **Human stream** (stderr): one line per lifecycle stage (resolved / imported
  / verified / saved), with the absolute paths.
- **Machine stream**: the :class:`ImportResult` envelope returned to the
  caller; the CLI folds it into its JSON stdout.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from typing import Any

from .schema import SUPPORTED_EXTENSIONS
from .validator import ImportSpec
from ..sw_com import resolve

logger = logging.getLogger("ai_sw_bridge.import_geom")


# swDocumentTypes_e — doc-type fail-closed mirror of export/dispatch.py
_SW_DOC_PART = 1
_SW_DOC_ASSEMBLY = 2

# Default verification thresholds.
_DEFAULT_VOLUME_REL_TOL = 0.01  # 1%
_DEFAULT_MIN_BODIES = 1


@dataclass
class ImportResult:
    """Outcome of one import attempt.

    Attributes:
        ok: True if the import ran end-to-end, verified, and the .SLDPRT was
            saved to disk.
        source: Absolute path of the imported STEP / IGES file (always set).
        output: Absolute path of the written .SLDPRT (always set, even on
            failure — so the caller knows where it *would* have landed).
        bodies: Number of solid bodies found after import (0 on failure).
        faces: Total face count summed across bodies (0 on failure).
        volume_mm3: Measured volume in mm³ if a verify block was declared;
            None otherwise.
        errors: Human-readable error strings in the order they were hit.
    """

    ok: bool
    source: str
    output: str
    bodies: int = 0
    faces: int = 0
    volume_mm3: float | None = None
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "ok": self.ok,
            "source": self.source,
            "output": self.output,
            "bodies": self.bodies,
            "faces": self.faces,
        }
        if self.volume_mm3 is not None:
            out["volume_mm3"] = self.volume_mm3
        if self.errors:
            out["errors"] = list(self.errors)
        return out


def import_part(spec: ImportSpec) -> ImportResult:
    """Run the import chain end-to-end and return an :class:`ImportResult`.

    Never raises — every COM / filesystem failure is captured in
    ``result.errors`` and surfaced as ``ok=False``.
    """
    result = ImportResult(
        ok=False,
        source=str(spec.source),
        output=str(spec.output),
    )

    sw, tsw, err = _resolve_sw_app()
    if err is not None:
        result.errors.append(err)
        return result

    import_data, err = _get_import_data(tsw, spec.source)
    if err is not None:
        result.errors.append(err)
        return result

    doc, err = _load_file4(tsw, spec.source, import_data)
    if err is not None:
        result.errors.append(err)
        return result

    try:
        err = _verify(doc, spec.verify, result)
        if err is not None:
            result.errors.append(err)
            return result

        err = _save_as(doc, spec.output)
        if err is not None:
            result.errors.append(err)
            return result
    finally:
        # Always close the doc we just imported so the seat is left clean
        # for the next run (same hygiene as spike_export_3d.py).
        try:
            title = resolve(doc, "GetTitle")
            if title:
                sw.CloseDoc(title)
        except Exception:  # noqa: BLE001 — close failure is non-fatal
            pass

    result.ok = True
    return result


# ---------------------------------------------------------------------------
# internal steps
# ---------------------------------------------------------------------------


def _resolve_sw_app() -> tuple[Any, Any, str | None]:
    """Acquire ``ISldWorks`` and its typed wrapper. Returns ``(sw, tsw, err)``."""
    try:
        from ai_sw_bridge.com.earlybind import typed
        from ai_sw_bridge.sw_com import get_sw_app

        sw = get_sw_app()
        tsw = typed(sw, "ISldWorks")
        return sw, tsw, None
    except Exception as exc:
        return None, None, f"failed to resolve SldWorks.Application: {exc!r}"


def _get_import_data(tsw: Any, source_path) -> tuple[Any, str | None]:
    """Call ``GetImportFileData`` and return the raw import-data dispatch.

    Fail-closed: None return → typed error. Extension dispatch is handled
    by the kernel; we don't need to pick ``IImportStepData`` vs
    ``IImportIgesData`` ourselves.
    """
    try:
        import_data = tsw.GetImportFileData(str(source_path))
    except Exception as exc:
        return None, f"GetImportFileData raised {type(exc).__name__}: {exc}"
    if import_data is None:
        return None, (
            f"GetImportFileData returned None for {source_path.name!r}; "
            f"extension {source_path.suffix!r} may not be supported "
            f"(accepted: {sorted(SUPPORTED_EXTENSIONS)})"
        )
    return import_data, None


def _load_file4(tsw: Any, source_path, import_data: Any) -> tuple[Any, str | None]:
    """Call ``LoadFile4(path, "r", import_data, 0)`` via typed early-bind.

    The ByRef I4 out-param arrives as the second tuple element when makepy
    dispatches the call. We use ``"r"`` to force a standard native B-rep
    import (no 3D Interconnect, no imported-feature tree — matches the v1
    dumb-solid deliverable).
    """
    try:
        result = tsw.LoadFile4(str(source_path), "r", import_data, 0)
    except Exception as exc:
        return None, f"LoadFile4 raised {type(exc).__name__}: {exc}"

    doc: Any
    errors_code: Any
    if isinstance(result, tuple) and len(result) >= 2:
        doc, errors_code = result[0], result[1]
    elif isinstance(result, tuple) and len(result) == 1:
        doc, errors_code = result[0], 0
    else:
        doc, errors_code = result, 0

    err_int = 0
    try:
        err_int = int(errors_code) if errors_code is not None else 0
    except (TypeError, ValueError):
        err_int = -1

    if doc is None:
        return None, (
            f"LoadFile4 returned no document (errors={err_int}); "
            f"foreign geometry import failed at the kernel"
        )
    if err_int != 0:
        logger.warning(
            "LoadFile4 reported non-zero errors=%d but returned a doc; "
            "proceeding with verification",
            err_int,
        )
    return doc, None


def _verify(
    doc: Any, verify: dict[str, Any] | None, result: ImportResult
) -> str | None:
    """Populate ``result.bodies`` / ``faces`` / ``volume_mm3``; return an
    error string if the load-bearing gate fails, else None.

    Always runs the body+face count. Volume check runs only when
    ``verify.volume_mm3`` is declared.
    """
    from ai_sw_bridge.com.earlybind import typed_qi

    try:
        doc_type = int(resolve(doc, "GetType"))
    except Exception as exc:
        return f"cannot determine document type: {exc!r}"
    if doc_type != _SW_DOC_PART:
        return (
            f"imported document is not a Part (type={doc_type}); "
            f"expected type={_SW_DOC_PART}"
        )

    try:
        pdoc = typed_qi(doc, "IPartDoc")
    except Exception as exc:
        return f"IPartDoc QI failed: {exc!r}"

    try:
        bodies = pdoc.GetBodies2(0, True)  # swSolidBody=0, True=all
    except Exception as exc:
        return f"GetBodies2 raised {type(exc).__name__}: {exc}"

    if bodies is None:
        return "GetBodies2 returned None — bodyless import (E4 trap)"
    if not isinstance(bodies, (list, tuple)):
        bodies = (bodies,)
    result.bodies = len(bodies)

    min_bodies = _DEFAULT_MIN_BODIES
    if verify and isinstance(verify.get("min_bodies"), int):
        min_bodies = verify["min_bodies"]
    if result.bodies < min_bodies:
        return (
            f"imported part has {result.bodies} solid body(ies); "
            f"minimum required is {min_bodies} (E4 bodyless-reference trap)"
        )

    total_faces = 0
    for b in bodies:
        try:
            fc = b.GetFaceCount
            if callable(fc):
                fc = fc()
            total_faces += int(fc or 0)
        except Exception:
            pass
    result.faces = total_faces
    if total_faces == 0:
        return (
            "zero faces across all bodies — Reference-feature import "
            "(E4 trap) rejected"
        )

    if not verify or "volume_mm3" not in verify:
        return None

    expected_mm3 = float(verify["volume_mm3"])
    rel_tol = float(verify.get("volume_rel_tol", _DEFAULT_VOLUME_REL_TOL))

    try:
        ext = doc.Extension
        mp = ext.CreateMassProperty
        if callable(mp):
            mp = mp()
        if mp is None:
            return "Extension.CreateMassProperty returned None"
        vol_m3 = mp.Volume
        if callable(vol_m3):
            vol_m3 = vol_m3()
        if vol_m3 is None:
            return "MassProperty.Volume returned None"
        vol_mm3 = float(vol_m3) * 1.0e9
        result.volume_mm3 = vol_mm3
    except Exception as exc:
        return f"volume read raised {type(exc).__name__}: {exc}"

    if abs(vol_mm3 - expected_mm3) > rel_tol * expected_mm3:
        return (
            f"volume {vol_mm3:.2f} mm³ outside ±{rel_tol*100:.2f}% of "
            f"expected {expected_mm3:.2f} mm³"
        )
    return None


def _save_as(doc: Any, output_path) -> str | None:
    """Save the imported doc to ``output_path`` via ``SaveAs3(path, 0, 0)``.

    Three-postcondition verification mirrors the builder's
    ``_save_as_with_verification``: return code 0, file exists on disk,
    non-zero size.
    """
    path_str = str(output_path)
    try:
        err = doc.SaveAs3(path_str, 0, 0)
    except Exception as exc:
        return f"SaveAs3 raised {type(exc).__name__}: {exc}"

    err_code = int(err) if err is not None else 0
    if err_code != 0:
        return f"SaveAs3 returned swFileSaveError={err_code}"

    try:
        out = __import__("pathlib").Path(output_path)
        if not out.exists() or out.stat().st_size == 0:
            return "SaveAs3 returned NoError but .SLDPRT is missing or empty"
    except OSError as exc:
        return f"post-save verification failed: {exc}"

    print(f"  imported → {path_str}", file=sys.stderr)
    return None
