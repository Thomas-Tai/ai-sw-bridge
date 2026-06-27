"""Configuration dispatch (Phase 4, FR-4-01, todolist P4.1).

Iterates the ``variants:`` block from a schema-v2 spec, applies each
variant's locals overrides, and creates one SOLIDWORKS configuration per
variant.

Two-stream discipline (``UIUX.md`` §8):
  - **Human stream** (stderr): one line per configuration created.
  - **Machine stream**: ``ConfigResult`` list returned to the caller.

The SW-free layer validates that every override variable exists in the
base locals file, computes the effective locals text for each variant,
and structures the dispatch loop.  The actual COM call
(``ConfigurationManager.AddConfiguration2``) is SEAT-gated — only W0
runs it on a live seat.

Design:

- ``apply_overrides`` is a pure function: base text + overrides -> new
  text.  No file I/O, no COM.  Reuses ``locals_io.parse`` /
  ``locals_io.replace_rhs``.
- ``validate_overrides`` checks variable existence before any dispatch.
  Returns a list of unknown-variable errors (empty = clean).
- ``create_all`` iterates variants, calls ``_create_one`` per variant.
- ``_create_one`` is the seat-gated boundary: the SW-free structure
  computes the override text, then delegates to the SEAT stub.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from ..locals_io import parse, replace_rhs
from ..sw_com import resolve
from .deep_merge import deep_merge
from .variants import (
    ConfigResult,
    ConfigVariant,
    VariantOverride,
)

logger = logging.getLogger("ai_sw_bridge.config")


def apply_overrides(
    base_text: str,
    overrides: list[VariantOverride],
) -> str:
    """Compute the effective locals text after applying variant overrides.

    Pure function — no file I/O, no COM.  Reuses the shipped
    ``locals_io`` parser and replacer.

    For each override:
      - If the variable exists in the base, its RHS is replaced.
      - If it does not exist, the override is appended as a new line.

    Args:
        base_text: The full text of the base ``*_locals.txt`` file.
        overrides: The variant's override set.

    Returns:
        The modified locals text with all overrides applied.
    """
    text = base_text
    entries = parse(text)
    known = {e.name: e for e in entries}

    for ov in overrides:
        entry = known.get(ov.variable)
        if entry is not None:
            text = replace_rhs(text, entry.line_index, ov.expression)
        else:
            if text and not text.endswith("\n"):
                text += "\n"
            text += f'"{ov.variable}" = {ov.expression}\n'

    return text


def validate_overrides(
    base_text: str,
    variants: list[ConfigVariant],
) -> list[str]:
    """Check that all override variables exist in the base locals.

    Returns a list of error strings (empty = all clean).  Does not
    raise — the caller decides whether to fail-stop or warn.
    """
    entries = parse(base_text)
    known = {e.name for e in entries}
    errors: list[str] = []
    for v in variants:
        for ov in v.overrides:
            if ov.variable not in known:
                errors.append(
                    f"variant {v.name!r}: unknown variable {ov.variable!r} "
                    f"(not in base locals)"
                )
    return errors


def create_all(
    doc: Any,
    variants: list[ConfigVariant],
    base_locals_text: str,
) -> list[ConfigResult]:
    """Create one SW configuration per variant.

    Args:
        doc: An ``IModelDoc2``-like dispatch object (live or mock).
        variants: Parsed from the spec's ``variants:`` block.
        base_locals_text: The full text of the base ``*_locals.txt``.

    Returns:
        One ``ConfigResult`` per variant, in the same order.
    """
    results: list[ConfigResult] = []
    for v in variants:
        result = _create_one(doc, v, base_locals_text)
        if result.ok:
            print(
                f"  config {v.name!r} created ({len(v.overrides)} overrides)",
                file=sys.stderr,
            )
        else:
            print(
                f"  FAILED config {v.name!r}: {result.error}",
                file=sys.stderr,
            )
        results.append(result)
    return results


def _create_one(
    doc: Any,
    variant: ConfigVariant,
    base_locals_text: str,
) -> ConfigResult:
    """Create one configuration.  The COM call is SEAT-gated.

    SW-free pre-condition: computes the effective locals text.
    SEAT-gated: ``ConfigurationManager.AddConfiguration2`` — the
    call shape is ``ConfigurationManager.AddConfiguration2(
    name, alternateName, description)``.  The exact arg semantics
    (is ``alternateName`` the duplicate-name suffix? the display
    name?) and the per-configuration equation-link mechanism need
    a live seat to confirm.
    """
    # Validate/compute the per-configuration override text now; wiring it into
    # the configuration (equation-link) is SEAT-gated and deferred (see docstring).
    apply_overrides(base_locals_text, variant.overrides)

    try:
        cm = doc.ConfigurationManager
        config = cm.AddConfiguration2(
            variant.name,
            "",
            variant.description,
        )
    except Exception as exc:
        return ConfigResult(
            variant=variant.name,
            ok=False,
            error=(
                f"AddConfiguration2 is SEAT-gated (P4.1). "
                f"Call raised {type(exc).__name__}: {exc}"
            ),
        )

    if config is None:
        return ConfigResult(
            variant=variant.name,
            ok=False,
            error="AddConfiguration2 returned None",
        )

    return ConfigResult(variant=variant.name, ok=True)


# ---------------------------------------------------------------------------
# Multifile materialization (W36v)
# ---------------------------------------------------------------------------


def materialize_all(
    base_spec: dict[str, Any],
    output_dir: str | Path,
    variants: list[ConfigVariant],
) -> list[ConfigResult]:
    """Materialize one .sldprt per variant via the builder.

    Each variant's ``spec_overrides`` are deep-merged into a copy of
    *base_spec*, then built with ``no_dim=True`` and saved to
    ``output_dir / "{variant.name}.sldprt"``.  After each build the
    file is verified on disk and the volume is measured via COM.

    Args:
        base_spec: The base spec dict.  Never mutated.
        output_dir: Directory for the output .sldprt files.
        variants: Parsed from the spec's ``variants:`` block.

    Returns:
        One ``ConfigResult`` per variant, in the same order.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    results: list[ConfigResult] = []
    for v in variants:
        result = _materialize_variant(base_spec, out, v)
        if result.ok:
            vol_str = (
                f", volume={result.volume_mm3:.0f} mm³"
                if result.volume_mm3 is not None
                else ""
            )
            print(
                f"  variant {v.name!r} -> {result.path}{vol_str}",
                file=sys.stderr,
            )
        else:
            print(
                f"  FAILED variant {v.name!r}: {result.error}",
                file=sys.stderr,
            )
        results.append(result)
    return results


def _materialize_variant(
    base_spec: dict[str, Any],
    output_dir: Path,
    variant: ConfigVariant,
) -> ConfigResult:
    """Build one variant as a distinct .sldprt file.

    1. Deep-merge ``variant.spec_overrides`` into a copy of *base_spec*.
    2. Call ``build(variant_spec, no_dim=True, save_as=path)``.
    3. Verify the file exists on disk with non-zero size.
    4. Open the part via COM, measure volume, close.
    5. Return ``ConfigResult`` with path + volume_mm3.
    """
    # 1. Deep-merge overrides
    variant_spec = deep_merge(base_spec, variant.spec_overrides)
    variant_spec["name"] = variant.name

    save_path = output_dir / f"{variant.name}.sldprt"

    # 2. Build
    try:
        from ..spec.builder import build as sw_build

        build_result = sw_build(
            variant_spec,
            no_dim=True,
            save_as=str(save_path),
        )
    except Exception as exc:
        return ConfigResult(
            variant=variant.name,
            ok=False,
            error=f"build raised {type(exc).__name__}: {exc}",
        )

    if not build_result.ok:
        return ConfigResult(
            variant=variant.name,
            ok=False,
            error=f"build failed: {build_result.error}",
        )

    # 3. Verify file on disk
    resolved_path = save_path.resolve()
    if not resolved_path.is_file():
        # Builder may have appended .sldprt or saved elsewhere
        if build_result.save_as and Path(build_result.save_as).is_file():
            resolved_path = Path(build_result.save_as)
        else:
            return ConfigResult(
                variant=variant.name,
                ok=False,
                path=str(save_path),
                error=f"output file not found: {save_path}",
            )

    if resolved_path.stat().st_size == 0:
        return ConfigResult(
            variant=variant.name,
            ok=False,
            path=str(resolved_path),
            error="output file is empty (0 bytes)",
        )

    # 4. Measure volume via COM
    volume_mm3 = _measure_part_volume(resolved_path)

    return ConfigResult(
        variant=variant.name,
        ok=True,
        path=str(resolved_path),
        volume_mm3=volume_mm3,
    )


def _measure_part_volume(part_path: Path) -> float | None:
    """Open a part, measure volume via CreateMassProperty, close.

    Returns volume in mm³, or None on failure.  Silently catches
    errors — volume measurement is best-effort and never blocks
    the materialization result.
    """
    try:
        from ..com.earlybind import typed, typed_qi
        from ..com.sw_type_info import wrapper_module
        from ..sw_com import get_sw_app

        sw = get_sw_app()
        mod = wrapper_module()
        tsw = typed(sw, "ISldWorks", module=mod)

        ret = tsw.OpenDoc6(str(part_path), 1, 1, "", 0, 0)
        model_doc = ret[0] if isinstance(ret, tuple) else ret
        if model_doc is None:
            return None

        mdoc2 = typed_qi(model_doc, "IModelDoc2", module=mod)

        ext = mdoc2.Extension
        if callable(ext):
            ext = ext()
        mp = ext.CreateMassProperty
        if callable(mp):
            mp = mp()
        if mp is None:
            title = resolve(mdoc2, "GetTitle")
            sw.CloseDoc(title)
            return None

        vol = mp.Volume
        if callable(vol):
            vol = vol()
        vol_mm3 = float(vol) * 1e9

        title = resolve(mdoc2, "GetTitle")
        sw.CloseDoc(title)

        return vol_mm3

    except Exception:
        return None
