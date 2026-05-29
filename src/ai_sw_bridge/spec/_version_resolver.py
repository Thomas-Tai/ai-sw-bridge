"""Central version-dispatch resolver for COM calls whose arity/semantics
change across SOLIDWORKS releases (FR-X-04).

Why this exists
---------------
Every handler in ``builder.py`` is GREEN on **SW 2024 SP1 only** (major
``RevisionNumber`` == 32). The SW API breaks roughly yearly: the reference
codebase branches on ``RevisionNumber == 33`` (= SW 2025) because
``FeatureRevolve2`` / ``FeatureCut4`` changed arity. There was previously NO
version abstraction -- every call site hard-coded the 2024 signature.

This module gives a single place to register, per logical COM op, a set of
revision-keyed *arg-builders*. At call time the running major revision selects
the arg-builder via a **newest->older cascade**: pick the highest registered
revision ``<=`` the running revision, else fall back to ``"default"``.

Revision model
--------------
``sw.RevisionNumber`` is a dotted string like ``"32.1.0"`` (see
``sw_com.py``). The **major** component is the release key:

    32 -> SW 2024,  33 -> SW 2025,  34 -> SW 2026, ...

We dispatch on that integer major. The running revision is read **once** via
late-bound attribute access (same idiom as every other COM read in this
package -- ``getattr``, never a typelib call) and is **injectable** for tests
so the resolver does not hard-require a live ``sw``.

Invariant note (#4, late-bound pywin32): the resolver itself performs no COM
*calls*. It only reads the ``RevisionNumber`` attribute late-bound and returns
an arg tuple; the handler in ``builder.py`` makes the actual ``fm.FeatureCut4``
call exactly as before. The dispatch layer is pure-Python and seat-free.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger("ai_sw_bridge.version_resolver")

# Major RevisionNumber of the single proven build (SW 2024 SP1). Mirrors
# SW_VERSION_VERIFIED[0] in sw_com.py; duplicated here as a named constant so
# the "default == 2024" intent reads locally.
SW_2024_MAJOR = 32
SW_2025_MAJOR = 33

# An arg-builder takes whatever keyword payload the handler passes through and
# returns the positional arg tuple to splat into the late-bound COM call.
ArgBuilder = Callable[..., tuple]

# The sentinel revision key for the catch-all variant. Selected when no
# registered integer revision is <= the running revision.
DEFAULT_KEY = "default"


def parse_major_revision(revision: Any) -> int | None:
    """Return the integer *major* of a SW ``RevisionNumber``, or ``None``.

    ``RevisionNumber`` comes back as a dotted string (e.g. ``"32.1.0"``); the
    leading component is the release key (32 == SW 2024). Accepts an ``int``
    directly (tests inject one), a string, or anything ``str()``-able whose
    first dotted token is an integer. Returns ``None`` if it can't be parsed,
    so the caller can fall back to ``"default"`` rather than crash.
    """
    if isinstance(revision, bool):  # bool is an int subclass -- reject explicitly
        return None
    if isinstance(revision, int):
        return revision
    if revision is None:
        return None
    try:
        return int(str(revision).split(".")[0])
    except (ValueError, IndexError):
        return None


def read_running_major(sw: Any) -> int | None:
    """Read ``sw.RevisionNumber`` once (late-bound) and return its major int.

    Late-bound attribute access mirrors ``sw_com.resolve`` / the
    ``_check_sw_version`` read -- pywin32 auto-invokes the zero-arg COM
    property on ``getattr``. Any failure (no seat, unreadable property) is
    logged and reported as ``None`` so dispatch degrades to ``"default"``
    instead of blocking the build.
    """
    if sw is None:
        return None
    try:
        rev = sw.RevisionNumber
    except Exception as exc:  # noqa: BLE001 -- pywintypes.com_error + AttributeError
        logger.warning("could not read SW RevisionNumber (%r); using default", exc)
        return None
    return parse_major_revision(rev)


class VersionedOp:
    """A logical COM op with revision-keyed arg-builders and cascade dispatch.

    Build one per op (e.g. ``FeatureCut4``) and register variants against it.
    Keys are integer majors (32, 33, ...) plus the ``"default"`` catch-all.
    ``resolve()`` picks the right builder for a running major; ``build()``
    resolves and invokes it in one step.
    """

    def __init__(self, op_name: str) -> None:
        self.op_name = op_name
        self._variants: dict[Any, ArgBuilder] = {}

    def register(self, key: Any, builder: ArgBuilder) -> None:
        """Register ``builder`` for revision ``key`` (an int major or
        ``"default"``). Re-registering the same key overwrites."""
        if key != DEFAULT_KEY and parse_major_revision(key) is None:
            raise ValueError(
                f"{self.op_name}: variant key must be an int major or "
                f"{DEFAULT_KEY!r}, got {key!r}"
            )
        self._variants[key] = builder

    def resolve(self, running_major: int | None) -> ArgBuilder:
        """Pick the arg-builder for ``running_major`` via newest->older cascade.

        - Exact registered major wins.
        - Else the highest registered major ``<=`` running_major wins
          (a newer SW runs the newest variant proven *at or below* it).
        - Else fall back to ``"default"``.

        Raises ``KeyError`` if nothing matches and no ``"default"`` is
        registered (a registration bug -- every op must carry a default).
        """
        if running_major is not None:
            int_keys = sorted(
                k for k in self._variants if isinstance(k, int) and not isinstance(k, bool)
            )
            # Highest registered major that is <= the running major.
            chosen: int | None = None
            for k in int_keys:
                if k <= running_major:
                    chosen = k
            if chosen is not None:
                return self._variants[chosen]
        if DEFAULT_KEY in self._variants:
            return self._variants[DEFAULT_KEY]
        raise KeyError(
            f"{self.op_name}: no variant for running major {running_major!r} "
            f"and no {DEFAULT_KEY!r} registered (registered keys: "
            f"{sorted(self._variants, key=str)})"
        )

    def build(self, running_major: int | None, /, *args: Any, **kwargs: Any) -> tuple:
        """Resolve the variant for ``running_major`` and call it, returning the
        positional arg tuple for the late-bound COM call."""
        return self.resolve(running_major)(*args, **kwargs)


# A process-wide registry of versioned ops, keyed by op name. Handlers look up
# their op here (``REGISTRY["FeatureCut4"]``) and resolve against the running
# revision. One registry keeps the "what changed across versions" knowledge in
# a single auditable place.
REGISTRY: dict[str, VersionedOp] = {}


def versioned(op_name: str, key: Any) -> Callable[[ArgBuilder], ArgBuilder]:
    """Decorator registering an arg-builder as the ``key`` variant of ``op_name``.

    Creates the :class:`VersionedOp` in :data:`REGISTRY` on first use. Usage::

        @versioned("FeatureCut4", DEFAULT_KEY)
        def _cut4_2024_args(*, end_cond, depth_m, flip): ...

        @versioned("FeatureCut4", SW_2025_MAJOR)  # 🔴 SEAT: needs a 2025 seat
        def _cut4_2025_args(*, end_cond, depth_m, flip): ...

    Returns the undecorated function so it stays directly unit-testable.
    """

    def _decorate(builder: ArgBuilder) -> ArgBuilder:
        op = REGISTRY.get(op_name)
        if op is None:
            op = VersionedOp(op_name)
            REGISTRY[op_name] = op
        op.register(key, builder)
        return builder

    return _decorate


def resolve_op(op_name: str, sw: Any = None, running_major: int | None = None) -> ArgBuilder:
    """Convenience: resolve ``op_name``'s arg-builder for the running revision.

    Pass ``running_major`` directly (tests/injection) OR pass ``sw`` to have
    the major read late-bound via :func:`read_running_major`. If both are
    omitted, the running major is ``None`` and dispatch falls to ``"default"``.
    """
    op = REGISTRY.get(op_name)
    if op is None:
        raise KeyError(f"no versioned op registered under {op_name!r}")
    if running_major is None:
        running_major = read_running_major(sw)
    return op.resolve(running_major)
