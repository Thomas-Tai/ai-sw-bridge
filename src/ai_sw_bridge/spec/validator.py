"""
Spec validator: schema + dependency graph + locals.txt reference checks.

Three layers of validation, in order. Each returns ValidationError on the
first failure (fail-fast).

1. Schema check: jsonschema against schema.SCHEMA.
2. Reference check (strict topological): every `sketch`, `of_feature`
   reference must point to a feature already declared *earlier* in the list,
   and the referenced feature must be of an appropriate type.
3. Locals check: every {"rhs": "..."} expression's quoted variable refs must
   exist in the spec's `locals` file (if any).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jsonschema

from .schema import SCHEMA, SKETCH_TYPES, EXTRUDE_TYPES, ALL_TYPES


@dataclass
class ValidationError(Exception):
    """One validation failure. Use `path` to locate it in the spec."""

    message: str
    path: str = ""

    def __str__(self) -> str:
        return f"{self.path}: {self.message}" if self.path else self.message


# Matches a quoted variable reference in an Equation Manager expression.
# E.g. `"S1B_X"` -> capture S1B_X. Same regex used by ai-sw-observe equations.
QUOTED_VAR_RE = re.compile(r'"([A-Za-z_][A-Za-z0-9_]*)"')


def _check_schema(spec: dict[str, Any]) -> None:
    """Raise ValidationError on the first jsonschema violation."""
    try:
        jsonschema.validate(instance=spec, schema=SCHEMA)
    except jsonschema.ValidationError as e:
        path = "/".join(str(p) for p in e.absolute_path)
        raise ValidationError(message=e.message, path=path or "$") from e


def _check_references(spec: dict[str, Any]) -> None:
    """Strict topological check: every reference points to an earlier feature
    of the right kind."""
    seen: dict[str, str] = {}  # name -> type
    for i, feat in enumerate(spec["features"]):
        name = feat["name"]
        ftype = feat["type"]

        if name in seen:
            raise ValidationError(
                message=f"duplicate feature name '{name}'",
                path=f"features/{i}/name",
            )

        # Reference checks per feature type
        if ftype == "sketch_circle_on_face":
            target = feat["of_feature"]
            if target not in seen:
                raise ValidationError(
                    message=f"sketch_circle_on_face references '{target}', "
                    f"which is not an earlier feature",
                    path=f"features/{i}/of_feature",
                )
            if seen[target] not in EXTRUDE_TYPES:
                raise ValidationError(
                    message=f"sketch_circle_on_face requires '{target}' to be "
                    f"an extrusion-type feature; got '{seen[target]}'",
                    path=f"features/{i}/of_feature",
                )
        elif ftype in EXTRUDE_TYPES:
            target = feat["sketch"]
            if target not in seen:
                raise ValidationError(
                    message=f"{ftype} references sketch '{target}', "
                    f"which is not an earlier feature",
                    path=f"features/{i}/sketch",
                )
            if seen[target] not in SKETCH_TYPES:
                raise ValidationError(
                    message=f"{ftype} requires '{target}' to be a sketch; "
                    f"got '{seen[target]}'",
                    path=f"features/{i}/sketch",
                )

        seen[name] = ftype


def _extract_var_refs(value: Any) -> list[str]:
    """If a length value is an {rhs} object, return all quoted var names in it.
    Otherwise []."""
    if isinstance(value, dict) and "rhs" in value:
        return QUOTED_VAR_RE.findall(value["rhs"])
    return []


def _collect_rhs_var_refs(spec: dict[str, Any]) -> dict[str, list[tuple[str, str]]]:
    """Walk all length fields in all features. Return
    {var_name: [(feature_name, field_name), ...]} so error messages can
    point to where each ref appears."""
    refs: dict[str, list[tuple[str, str]]] = {}
    for feat in spec["features"]:
        for field in ("width", "height", "depth", "diameter"):
            if field in feat:
                for v in _extract_var_refs(feat[field]):
                    refs.setdefault(v, []).append((feat["name"], field))
    return refs


def _check_locals(spec: dict[str, Any]) -> None:
    """If any feature uses {rhs}, the spec must declare a `locals` path,
    that file must exist, and every quoted var ref must be defined in it."""
    refs = _collect_rhs_var_refs(spec)
    if not refs:
        return

    locals_path = spec.get("locals")
    if not locals_path:
        # Pick one ref for the error message
        any_var = next(iter(refs))
        feat_name, field = refs[any_var][0]
        raise ValidationError(
            message=(
                f"feature '{feat_name}' field '{field}' uses rhs '\"{any_var}\"' "
                f"but spec has no `locals` path declared"
            ),
            path="$/locals",
        )

    p = Path(locals_path)
    if not p.exists():
        raise ValidationError(
            message=f"locals file not found: {p}",
            path="$/locals",
        )

    # Parse declared names from the file. Reuses locals_io.parse via the
    # established module so the regex stays in one place.
    from ..locals_io import parse

    text = p.read_text(encoding="utf-8")
    declared = {e.name for e in parse(text)}

    for var, sites in refs.items():
        if var not in declared:
            feat_name, field = sites[0]
            raise ValidationError(
                message=(
                    f"feature '{feat_name}' field '{field}' references "
                    f"variable '\"{var}\"' but it is not declared in {p.name}"
                ),
                path=f"$/features (rhs ref to '{var}')",
            )


def validate(spec: dict[str, Any]) -> None:
    """Run all three checks. Raises ValidationError on first failure."""
    _check_schema(spec)
    _check_references(spec)
    _check_locals(spec)
