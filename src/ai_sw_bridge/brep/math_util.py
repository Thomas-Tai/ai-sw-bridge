"""Math-utility wrapper — E3 (Wave-5).

Thin adapter around ``ISldWorks.GetMathUtility`` → ``IMathUtility``.
Exposes the creation helpers the rest of the bridge needs (point, vector,
transform) so callers do not import ``pywin32`` directly.

Usage::

    mu = MathUtility.from_app(sw)       # sw = ISldWorks dispatch
    pt = mu.create_point((0.01, 0.02, 0.03))   # IMathPoint
    v  = mu.create_vector((0.0, 0.0, 1.0))     # IMathVector
    xf = mu.create_transform(array_data)        # IMathTransform

All methods are pure pass-through; no SW seat needed to mock-test.
"""

from __future__ import annotations

from typing import Any, Sequence


class MathUtility:
    """Wrapper around an ``IMathUtility`` COM dispatch.

    Constructed via :meth:`from_app` (or directly with an existing
    IMathUtility proxy for testing).  Every method is a thin delegation
    that keeps the call-site free of raw ``pywin32`` imports.
    """

    def __init__(self, util: Any) -> None:
        self._util = util

    @classmethod
    def from_app(cls, sw: Any) -> "MathUtility":
        """Obtain an IMathUtility from the running ``ISldWorks`` app."""
        util = sw.GetMathUtility()
        if util is None:
            raise RuntimeError("GetMathUtility returned None")
        return cls(util)

    @property
    def raw(self) -> Any:
        """The underlying IMathUtility dispatch (escape hatch)."""
        return self._util

    def create_point(self, coords: Sequence[float]) -> Any:
        """Create an ``IMathPoint`` from a 3-element (x, y, z) sequence (metres)."""
        if len(coords) != 3:
            raise ValueError(f"point needs 3 coords, got {len(coords)}")
        return self._util.CreatePoint(tuple(float(c) for c in coords))

    def create_vector(self, coords: Sequence[float]) -> Any:
        """Create an ``IMathVector`` from a 3-element (dx, dy, dz) sequence."""
        if len(coords) != 3:
            raise ValueError(f"vector needs 3 coords, got {len(coords)}")
        return self._util.CreateVector(tuple(float(c) for c in coords))

    def create_transform(self, data: Sequence[float]) -> Any:
        """Create an ``IMathTransform`` from a 16-element array (row-major 4x4).

        The SW API expects a ``VARIANT`` carrying a SAFEARRAY of 16 doubles:
        [r00 r01 r02 tx  r10 r11 r12 ty  r20 r21 r22 tz  0 0 0 1].
        """
        if len(data) != 16:
            raise ValueError(f"transform needs 16 elements, got {len(data)}")
        return self._util.CreateTransform(tuple(float(d) for d in data))

    def create_transform_from_moves(self, tx: float, ty: float, tz: float) -> Any:
        """Convenience: build a pure-translation IMathTransform."""
        identity = [
            1.0,
            0.0,
            0.0,
            float(tx),
            0.0,
            1.0,
            0.0,
            float(ty),
            0.0,
            0.0,
            1.0,
            float(tz),
            0.0,
            0.0,
            0.0,
            1.0,
        ]
        return self.create_transform(identity)
