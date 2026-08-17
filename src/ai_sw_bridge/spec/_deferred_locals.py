"""Deferred-dim nominal-locals loader.

Extracted from ``builder.py`` to keep that grandfathered module under the
module-size budget (``tools/module_size_gate.py``); this is the leaf that owns
the "why" of the nominal-vs-placeholder resolution.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


def load_nominal_locals(
    deferred_dim: bool,
    spec: dict[str, Any],
    load_locals_map: Callable[[str], dict[str, float]],
) -> dict[str, float] | None:
    """Resolved name->mm map for deferred_dim geometry, else ``None``.

    In deferred_dim, geometry handlers create ``{rhs}``-bound lengths at their
    NOMINAL size (via ``BuildContext.locals_map``) rather than the placeholder,
    so the later driving dim MATCHES the geometry and does not resize -- and
    thus drift -- it (the demo_bearing_block off-center block). ``no_dim`` has
    already resolved rhs in-spec and inline needs no map, so both return
    ``None``. ``load_locals_map`` is injected to avoid a ``builder`` import
    cycle. Fails safe to ``None`` (logs a warning) so a bad or absent locals
    file never aborts the build.
    """
    if not (deferred_dim and isinstance(spec.get("locals"), str)):
        return None
    try:
        return load_locals_map(spec["locals"])
    except Exception as e:  # noqa: BLE001 -- fail safe, never abort the build
        logger.warning("deferred-dim nominal-locals load failed: %s", e)
        return None
