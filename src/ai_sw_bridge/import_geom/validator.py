"""Validator for the ``kind:"import"`` spec envelope.

Fail-closed:

- Unsupported extension → typed error at propose (before any COM call).
- Missing source file → typed error.
- Output without ``.sldprt`` extension → typed error.
- Output parent directory missing → typed error.

The validator is SW-free — it only inspects the spec and the filesystem.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .schema import SUPPORTED_EXTENSIONS


class ImportValidationError(Exception):
    """Raised when an import spec fails validation.

    Attributes:
        path: JSON pointer (e.g. ``"source"``, ``"output"``) identifying the
            offending field, following the ``spec.validator`` convention.
        message: Human-readable description of the failure.
    """

    def __init__(self, path: str, message: str) -> None:
        super().__init__(f"{path}: {message}")
        self.path = path
        self.message = message


@dataclass(frozen=True)
class ImportSpec:
    """A validated import request.

    ``source`` and ``output`` are absolute resolved paths. ``verify`` is the
    raw verify block from the spec (``None`` when omitted).
    """

    source: Path
    output: Path
    verify: dict[str, Any] | None = None

    def source_extension(self) -> str:
        """Lower-cased source extension including the leading dot."""
        return self.source.suffix.lower()


def _load_json(spec_path: Path) -> dict[str, Any]:
    try:
        text = spec_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ImportValidationError(
            "spec", f"spec file not found: {spec_path}"
        ) from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ImportValidationError(
            "spec", f"spec is not valid JSON: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise ImportValidationError(
            "spec", f"spec must be a JSON object, got {type(data).__name__}"
        )
    return data


def _require_str(data: dict[str, Any], key: str) -> str:
    if key not in data:
        raise ImportValidationError(key, "required field is missing")
    val = data[key]
    if not isinstance(val, str):
        raise ImportValidationError(
            key, f"must be a string, got {type(val).__name__}"
        )
    if not val.strip():
        raise ImportValidationError(key, "must be a non-empty string")
    return val


def validate_import_spec(
    data: dict[str, Any],
    spec_path: Path | None = None,
) -> ImportSpec:
    """Validate a parsed spec and return an :class:`ImportSpec`.

    Args:
        data: The parsed JSON envelope.
        spec_path: When provided, relative ``source`` / ``output`` paths are
            resolved against this file's parent directory (matching the
            ``ai-sw-build`` behavior for relative ``locals`` paths).

    Raises:
        ImportValidationError: on any structural / filesystem problem.
    """
    kind = data.get("kind")
    if kind != "import":
        raise ImportValidationError(
            "kind",
            f"must be 'import', got {kind!r}",
        )

    source_raw = _require_str(data, "source")
    output_raw = _require_str(data, "output")

    anchor = spec_path.parent if spec_path is not None else Path.cwd()
    source_path = Path(source_raw)
    if not source_path.is_absolute():
        source_path = (anchor / source_path).resolve()
    output_path = Path(output_raw)
    if not output_path.is_absolute():
        output_path = (anchor / output_path).resolve()

    if not source_path.exists():
        raise ImportValidationError(
            "source", f"file does not exist: {source_path}"
        )

    src_ext = source_path.suffix.lower()
    if src_ext not in SUPPORTED_EXTENSIONS:
        raise ImportValidationError(
            "source",
            f"unsupported extension {src_ext!r}; "
            f"supported: {sorted(SUPPORTED_EXTENSIONS)}",
        )

    if output_path.suffix.lower() != ".sldprt":
        raise ImportValidationError(
            "output",
            f"output must have .sldprt extension, got {output_path.suffix!r}",
        )

    if not output_path.parent.exists():
        raise ImportValidationError(
            "output",
            f"parent directory does not exist: {output_path.parent}",
        )

    verify = data.get("verify")
    if verify is not None:
        if not isinstance(verify, dict):
            raise ImportValidationError(
                "verify", f"must be an object, got {type(verify).__name__}"
            )
        if "volume_mm3" in verify:
            vol = verify["volume_mm3"]
            if not isinstance(vol, (int, float)) or vol <= 0:
                raise ImportValidationError(
                    "verify.volume_mm3",
                    f"must be a positive number, got {vol!r}",
                )
        if "volume_rel_tol" in verify:
            tol = verify["volume_rel_tol"]
            if (
                not isinstance(tol, (int, float))
                or tol <= 0
                or tol > 1
            ):
                raise ImportValidationError(
                    "verify.volume_rel_tol",
                    f"must be in (0, 1], got {tol!r}",
                )
        if "min_bodies" in verify:
            mb = verify["min_bodies"]
            if not isinstance(mb, int) or mb < 1:
                raise ImportValidationError(
                    "verify.min_bodies",
                    f"must be a positive integer, got {mb!r}",
                )

    unknown = set(data) - {"kind", "source", "output", "verify"}
    if unknown:
        raise ImportValidationError(
            "spec", f"unknown top-level field(s): {sorted(unknown)}"
        )

    return ImportSpec(source=source_path, output=output_path, verify=verify)


def parse_import_spec(spec_path: Path) -> ImportSpec:
    """Load ``spec_path`` as JSON and validate. Returns an :class:`ImportSpec`."""
    data = _load_json(spec_path)
    return validate_import_spec(data, spec_path=spec_path)
