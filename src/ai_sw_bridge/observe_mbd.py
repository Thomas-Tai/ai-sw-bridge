"""Read-only ``mbd`` observe lane — serialize DimXpert / MBD PMI to JSON.

Extracts Product & Manufacturing Information (datums, size dimensions with
tolerances, geometric tolerances) attached to a 3D part via the DimXpert API,
WITHOUT a drawing. Pure-read: opens the schema for reading only, never authors.

Measure-first reconnaissance (``spikes/v0_2x/spike_mbd_read_extract.py`` +
``spike_mbd_probe.py``, live SW2024, 2026-06-24) settled the COM boundary:

  * WRITE walls OOP — ``AutoDimensionScheme`` / ``InsertSizeDimension`` ghost
    (boundary law: kernel must traverse the B-rep to recognize features). So PMI
    cannot be authored out-of-process; this lane only READS what is already there.
  * READ marshals cleanly OOP — ``Extension.DimXpertManager(config, CreateSchema)``
    -> ``IDimXpertManager.DimXpertPart`` -> ``GetFeatures()`` / ``GetAnnotations()``
    (VARIANT SAFEARRAY; ``None`` when empty, no fault). ``CreateSchema=False`` reads
    a part's AUTHORED schema (``True`` would spin up a fresh empty one).
  * The ``swdimxpert.tlb`` sub-objects are NOT makepy-gen'd -> late-bound CDispatch.
  * The extraction contract (50 IDimXpert* interfaces mapped):
      datum label      -> IDimXpertDatum.Identifier (BSTR)
      nominal value    -> IDimXpertDimensionTolerance.GetNominalValue (R8)
      fit code         -> IDimXpertDimensionTolerance.LimitsAndFitsCode (BSTR)
      GTOL value+datums-> IDimXpertTolerance.Tolerance (R8) + Get{Primary,Secondary,
                          Tertiary}Datums (VARIANT)
      attached feature -> IDimXpertFeature/Annotation.GetModelFeature -> IFeature.Name

THE ASYMMETRIC DEVIATION BRIDGE (defensive / best-effort): the DimXpert-native
surface exposes NO independent upper/lower deviation getters (only nominal + a
single symmetric ``Tolerance`` + fit code). Asymmetric +/- (e.g. +0.2 / -0.05)
must bridge ``IDimXpertAnnotation.GetDisplayEntity()`` -> IDisplayDimension ->
IDimension.Tolerance -> ITolerance.{GetMaxValue, GetMinValue}. This bridge is
UNPROVEN live (needs a GUI-authored PMI fixture — see ``docs/pending_gates.md``).
It is wrapped so that on success ``asymmetric_extracted=True`` and the bounds are
populated; on ANY fault it falls back to the symmetric base fields with
``asymmetric_extracted=False`` — the lane never crashes on the bridge.
"""

from __future__ import annotations

from typing import Any

from .com.earlybind import typed_qi
from .com.sw_type_info import wrapper_module
from .sw_com import DOC_TYPE_NAMES, SW_DOC_PART


def _read(obj: Any, name: str, *args: Any) -> Any:
    """Unified late-bound read for swdimxpert CDispatch AND test mocks.

    Real COM: a METHOD resolves (via getattr -> GetIDsOfNames) to a callable we
    invoke; a PROPERTY-GET resolves to the value directly. MagicMock satisfies the
    same shape when tests set methods to callables and properties to plain values.
    Raises if the member is absent — callers use that to DISCRIMINATE annotation
    kind (a datum has ``Identifier`` but not ``GetNominalValue``, etc.).
    """
    v = getattr(obj, name)
    return v(*args) if callable(v) else v


def _try(fn: Any, default: Any = None) -> Any:
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def _model_feature_name(node: Any) -> Any:
    """``GetModelFeature() -> IFeature``; return its ``.Name`` (the attached B-rep
    feature). Fail-soft to ``None``."""
    mod = _try(wrapper_module)
    mf = _try(lambda: _read(node, "GetModelFeature"))
    if mf is None:
        return None
    try:
        tf = typed_qi(mf, "IFeature", module=mod)
        nm = tf.Name
        return nm() if callable(nm) else nm
    except Exception:  # noqa: BLE001
        return None


def _datum_labels(node: Any, getter: str) -> list[str]:
    """``Get{Primary,Secondary,Tertiary}Datums() -> VARIANT[IDimXpertDatum]``;
    return each datum's ``Identifier`` label."""
    arr = _try(lambda: _read(node, getter))
    if arr is None:
        return []
    seq = arr if isinstance(arr, (list, tuple)) else [arr]
    labels: list[str] = []
    for d in seq:
        lab = _try(lambda d=d: _read(d, "Identifier"))
        if lab is not None:
            labels.append(str(lab))
    return labels


def _asymmetric_bridge(anno: Any) -> dict[str, Any]:
    """Best-effort: bridge to the standard annotation tolerance to recover
    asymmetric +/- deviations the DimXpert-native surface omits.

    ``GetDisplayEntity()`` -> IDisplayDimension -> ``GetDimension[2]()`` ->
    IDimension.Tolerance -> ITolerance.{GetMaxValue, GetMinValue}. On ANY fault,
    returns ``{"asymmetric_extracted": False}`` — never raises.
    """
    out = {
        "asymmetric_extracted": False,
        "upper_deviation": None,
        "lower_deviation": None,
    }
    try:
        mod = _try(wrapper_module)
        de = _read(anno, "GetDisplayEntity")
        if de is None:
            return out
        dd = typed_qi(de, "IDisplayDimension", module=mod)
        # SW exposes GetDimension2(index) on most builds; fall back to GetDimension.
        if hasattr(dd, "GetDimension2"):
            dim = dd.GetDimension2(0)
        else:
            dim = _read(dd, "GetDimension")
        tdim = typed_qi(dim, "IDimension", module=mod)
        tol = tdim.Tolerance
        tol = tol() if callable(tol) else tol
        ttol = typed_qi(tol, "ITolerance", module=mod)
        upper = _read(ttol, "GetMaxValue")
        lower = _read(ttol, "GetMinValue")
        if upper is None and lower is None:
            return out
        out["asymmetric_extracted"] = True
        out["upper_deviation"] = float(upper) if upper is not None else None
        out["lower_deviation"] = float(lower) if lower is not None else None
    except Exception:  # noqa: BLE001
        return {
            "asymmetric_extracted": False,
            "upper_deviation": None,
            "lower_deviation": None,
        }
    return out


def _classify_and_extract(anno: Any, errors: list[str]) -> dict[str, Any] | None:
    """Discriminate one annotation and extract its category-specific fields.

    Returns a tagged dict ``{"_bucket": "datums"|"dimensions"|"geometric_tolerances",
    ...}`` or ``None`` if the annotation answers no known witness getter.
    """
    name = _try(lambda: _read(anno, "Name"))
    attached = _model_feature_name(anno)

    # Datum: has Identifier (BSTR label).
    try:
        ident = _read(anno, "Identifier")
        if ident is not None:
            return {
                "_bucket": "datums",
                "label": str(ident),
                "attached_feature": attached,
                "name": str(name) if name is not None else None,
            }
    except Exception:  # noqa: BLE001
        pass

    # Size/location dimension: has GetNominalValue (R8).
    try:
        nominal = _read(anno, "GetNominalValue")
        if nominal is not None:
            rec: dict[str, Any] = {
                "_bucket": "dimensions",
                "type": str(name) if name is not None else "dimension",
                "nominal": float(nominal),
                "symmetric_tolerance": _try(lambda: float(_read(anno, "Tolerance"))),
                "fit_code": _try(lambda: _read(anno, "LimitsAndFitsCode")),
                "attached_feature": attached,
            }
            rec.update(_asymmetric_bridge(anno))
            return rec
    except Exception:  # noqa: BLE001
        pass

    # Geometric tolerance: has Tolerance (R8) + datum-reference arrays.
    try:
        tol_val = _read(anno, "Tolerance")
        if tol_val is not None:
            primary = _datum_labels(anno, "GetPrimaryDatums")
            secondary = _datum_labels(anno, "GetSecondaryDatums")
            tertiary = _datum_labels(anno, "GetTertiaryDatums")
            return {
                "_bucket": "geometric_tolerances",
                "symbol": str(name) if name is not None else None,
                "tolerance_value": float(tol_val),
                "primary_datum": primary[0] if primary else None,
                "secondary_datum": secondary[0] if secondary else None,
                "tertiary_datum": tertiary[0] if tertiary else None,
            }
    except Exception as exc:  # noqa: BLE001
        errors.append(f"classify: {exc!r}")
    return None


def _sw_get_mbd_impl(doc: Any) -> dict[str, Any]:
    """v1 core — serialize DimXpert/MBD PMI on the given (already-open) part doc.

    Payload keys::

        ok, doc_path, schema_name,
        datums:               [{label, attached_feature, name}]
        dimensions:           [{type, nominal, symmetric_tolerance, fit_code,
                                asymmetric_extracted, upper_deviation,
                                lower_deviation, attached_feature}]
        geometric_tolerances: [{symbol, tolerance_value, primary_datum,
                                secondary_datum, tertiary_datum}]
        annotation_count, feature_count, error, errors

    Parts only. Fail-soft: per-annotation faults land in ``errors``; the lane
    returns whatever it could read. ``CreateSchema=False`` — reads the authored
    schema, never spins up a fresh one (and never writes).
    """
    result: dict[str, Any] = {
        "ok": False,
        "doc_path": None,
        "schema_name": None,
        "datums": [],
        "dimensions": [],
        "geometric_tolerances": [],
        "annotation_count": None,
        "feature_count": None,
        "error": None,
        "errors": [],
    }
    try:
        if doc is None:
            result["error"] = "no_active_doc"
            return result
        result["doc_path"] = _try(lambda: str(_read(doc, "GetPathName")))

        doc_type = _try(lambda: int(_read(doc, "GetType")))
        if doc_type is not None and doc_type != SW_DOC_PART:
            result["error"] = (
                f"mbd requires a part (swDocPART={SW_DOC_PART}); active doc is "
                f"type {doc_type} ({DOC_TYPE_NAMES.get(doc_type)})"
            )
            return result

        # Resolve the DimXpert read graph. CreateSchema=False -> authored schema.
        try:
            ext = _read(doc, "Extension")
            mgr = ext.DimXpertManager("", False)
        except Exception as exc:  # noqa: BLE001
            result["error"] = f"DimXpertManager unavailable: {exc!r}"
            return result
        if mgr is None:
            result["error"] = "DimXpertManager returned None"
            return result
        result["schema_name"] = _try(lambda: _read(mgr, "SchemaName"))

        part = _try(lambda: _read(mgr, "DimXpertPart"))
        if part is None:
            # No authored schema on this part — empty PMI, not an error.
            result["annotation_count"] = 0
            result["feature_count"] = 0
            result["ok"] = True
            return result

        result["feature_count"] = _try(
            lambda: int(_read(part, "GetFeatureCount")), default=None
        )
        acount = _try(lambda: int(_read(part, "GetAnnotationCount")), default=None)
        result["annotation_count"] = acount

        annos = _try(lambda: _read(part, "GetAnnotations"))
        seq = (
            annos
            if isinstance(annos, (list, tuple))
            else ([] if annos is None else [annos])
        )
        for anno in seq:
            rec = _classify_and_extract(anno, result["errors"])
            if rec is None:
                continue
            bucket = rec.pop("_bucket")
            result[bucket].append(rec)

        result["ok"] = True
        return result
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"dispatch failed: {exc!r}"
        return result
