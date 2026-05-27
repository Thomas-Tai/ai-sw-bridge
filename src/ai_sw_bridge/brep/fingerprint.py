"""B-rep fingerprinting — stable per-face identity (spec.md §2.4).

Derives a 16-hex-char fingerprint from a face's intrinsic geometric
properties (unit normal + centroid + area). The quantization tolerance
is calibrated to be coarser than SW's internal rebuild noise but
finer than any parametric change a variable would induce.

``fingerprint = sha256(
    quantize(normal_vec, 6) || quantize(centroid, 6) || quantize(area_mm2, 3)
).hexdigest()[:16]``

Load-bearing guarantee: the fingerprint is deterministic for a given
input — two calls with identical values produce byte-identical
strings. Perturbations smaller than the quantization step are
collapsed (same fingerprint); perturbations larger than the step
produce a different hash.

The fingerprint is NOT stable across SW service packs in pathological
cases (face enumeration order can change). Re-resolve symbolic
references on every build — never cache across runs.
"""

from __future__ import annotations

import hashlib
import json
from typing import Iterable


# Quantization precision: number of decimal places retained before
# hashing. Chosen to be coarser than SW's observed rebuild noise
# (~1e-8 m on centroid position, ~1e-7 on normal components) but
# finer than any parametric change would induce (~1e-4 m = 0.1 mm).
_NORMAL_DECIMALS = 6
_CENTROID_DECIMALS = 6
_AREA_DECIMALS = 3

# Length of the hex prefix kept from the SHA-256 digest.
# 64 bits of entropy → birthday-bound collision probability at
# n = 1000 faces is ~3e-14 (per spec.md §2.4).
_FINGERPRINT_LEN = 16


def _quantize(value: float, decimals: int) -> float:
    """Round to a fixed decimal precision and strip signed-zero artifacts."""
    rounded = round(float(value), decimals)
    # Collapse -0.0 to 0.0 so quantization is sign-stable at origin.
    if rounded == 0.0:
        return 0.0
    return rounded


def _quantize_vec(vec: Iterable[float], decimals: int) -> list[float]:
    return [_quantize(v, decimals) for v in vec]


def fingerprint(
    face_dict: dict,
    *,
    normal_key: str = "normal",
    centroid_key: str = "centroid",
    area_key: str = "area_mm2",
) -> str:
    """Compute the stable fingerprint for one face dict.

    ``face_dict`` matches the shape produced by
    ``brep.interrogator.BrepFace.to_dict()``: ``normal`` (3-list),
    ``centroid`` (3-list, meters), ``area_mm2`` (float).

    The three quantized vectors are serialized to canonical JSON
    (sort keys, no whitespace) and fed to SHA-256; the first 16 hex
    characters of the digest are returned.
    """
    normal = face_dict.get(normal_key)
    centroid = face_dict.get(centroid_key)
    area_mm2 = face_dict.get(area_key)
    if normal is None or centroid is None or area_mm2 is None:
        raise ValueError(
            "face_dict must contain 'normal', 'centroid', and 'area_mm2'"
        )

    payload = {
        "normal": _quantize_vec(normal, _NORMAL_DECIMALS),
        "centroid": _quantize_vec(centroid, _CENTROID_DECIMALS),
        "area_mm2": _quantize(area_mm2, _AREA_DECIMALS),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(blob).hexdigest()[:_FINGERPRINT_LEN]


__all__ = ["fingerprint"]
