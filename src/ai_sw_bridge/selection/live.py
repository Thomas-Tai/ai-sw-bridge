"""Live-COM bridge for :class:`DurableRef` (spec.md §5, Phase 0).

This is the production wiring of the durable-selection keystone proven by the
S-EARLYBIND spikes. ``DurableRef`` (and ``BrepFingerprint``) are pure data;
this module is the only place in the package that touches a live SOLIDWORKS
document to **capture** a persist token from an entity and **resolve** a token
back to a live entity.

It is deliberately thin and routes every OUT-param / Callout call through the
sanctioned hybrid escape hatch ``com.earlybind`` (late binding by default;
early-bound typed-wrap only where the marshaler needs it — see
``CODESTYLE.md §2.1.1``). The two load-bearing facts from the spikes:

* ``IModelDocExtension.GetObjectByPersistReference3(pid)`` returns
  ``(entity, errCode)`` under an early-bound typed Extension — the ``[out]``
  error code arrives as the 2nd tuple element (late binding cannot marshal it).
* The token survives a real save -> close -> reopen, **but** a freshly opened
  document must be rebuilt (``ForceRebuild3``) before the token resolves, else
  it comes back ``errCode=1`` ("Deleted"). Rebuild-on-open is the *caller's*
  responsibility (the open-existing-doc lane); this module assumes the doc is
  in a resolved state.

Resolution honors the deterministic fallback hierarchy from ``DurableRef``:

1. ``persist_id`` via ``GetObjectByPersistReference3`` (proven).
2. ``fingerprint`` re-match against the live body (a later slice — this module
   reports the need for it as a structured outcome rather than performing it).
3. client-side hand-off (out of bridge core).

Every COM interaction is failure-tolerant: a capture that cannot read a token
returns ``None`` (the first-class "persist unavailable" state, so the manifest
degrades to fingerprint-only with no regression), and a resolve that fails
returns a structured outcome naming why — never a raw exception escaping into
the build loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..com import earlybind

# swPersistReferencedObjectStatus_e — the [out] code from
# GetObjectByPersistReference3. Only ``Ok`` yields a usable entity.
PERSIST_OK = 0
PERSIST_DELETED = 1
PERSIST_SUPPRESSED = 2
PERSIST_AMBIGUOUS = 3
PERSIST_INVALID = 4
PERSIST_STATUS_NAMES: dict[int, str] = {
    PERSIST_OK: "Ok",
    PERSIST_DELETED: "Deleted",
    PERSIST_SUPPRESSED: "Suppressed",
    PERSIST_AMBIGUOUS: "AmbiguousReference",
    PERSIST_INVALID: "InvalidReference",
}


def _is_entity(obj: Any) -> bool:
    """A real COM entity came back (not None, not an int error sentinel)."""
    return obj is not None and not isinstance(obj, int)


@dataclass(frozen=True)
class PersistResolution:
    """Outcome of a single ``GetObjectByPersistReference3`` round-trip.

    * ``entity`` — the resolved COM entity, or ``None`` if it did not resolve.
    * ``status_code`` — the raw ``[out]`` ``swPersistReferencedObjectStatus_e``
      code (``None`` if the call never returned one).
    * ``ok`` — ``True`` iff an entity resolved with an ``Ok`` (or absent) status.
    * ``error`` — a short reason string when the call failed outright.
    """

    entity: Any | None
    status_code: int | None
    ok: bool
    error: str | None = None

    @property
    def status_name(self) -> str | None:
        if self.status_code is None:
            return None
        return PERSIST_STATUS_NAMES.get(self.status_code, f"Unknown({self.status_code})")


@dataclass(frozen=True)
class RefResolution:
    """Outcome of resolving a whole :class:`DurableRef` through the hierarchy.

    * ``entity`` — the resolved entity, or ``None``.
    * ``method`` — ``"persist_id"`` (resolved via the token),
      ``"fingerprint_fallback"`` (persist unavailable/failed — the caller must
      re-match by fingerprint against the live body), or ``"unresolved"``.
    * ``persist`` — the underlying :class:`PersistResolution` when a token was
      attempted, else ``None``.
    * ``note`` — human-readable context.
    """

    entity: Any | None
    method: str
    persist: PersistResolution | None = None
    note: str | None = None


def capture_persist_id(doc: Any, entity: Any) -> bytes | None:
    """Read the durable persist token for *entity* from the live *doc*.

    Returns the raw token bytes, or ``None`` if the token cannot be read for
    any reason (entity has none, the API is unavailable, or the marshaler
    fails). ``None`` is the first-class "persist unavailable" state —
    ``DurableRef`` stores it as ``persist_id=None`` and the manifest omits the
    key, degrading cleanly to fingerprint-only.

    Args:
        doc: the live ``IModelDoc2`` the entity belongs to.
        entity: a face / edge / vertex COM object from that doc's body.
    """
    if doc is None or entity is None:
        return None
    try:
        ext = earlybind.typed_extension(doc)
        pid = ext.GetPersistReference3(entity)
    except earlybind.EarlyBindError:
        return None
    except Exception:  # noqa: BLE001 — any COM failure degrades to None
        return None
    if pid is None:
        return None
    try:
        return bytes(pid)
    except Exception:  # noqa: BLE001 — token shape not coercible -> unavailable
        return None


def resolve_persist_id(doc: Any, persist_id: bytes | None) -> PersistResolution:
    """Resolve a persist token to a live entity on *doc*.

    Routes through an early-bound typed ``IModelDocExtension`` so the
    ``[out]`` status code is marshaled (the whole reason this call needs
    the hybrid escape hatch). Never raises — failures are reported in the
    returned :class:`PersistResolution`.
    """
    if persist_id is None:
        return PersistResolution(None, None, False, error="no persist_id")
    try:
        token = bytes(persist_id)
    except Exception as e:  # noqa: BLE001
        return PersistResolution(None, None, False, error=f"bad token: {e}")
    try:
        ext = earlybind.typed_extension(doc)
        res = ext.GetObjectByPersistReference3(token)
    except earlybind.EarlyBindError as e:
        return PersistResolution(None, None, False, error=f"earlybind: {e}")
    except Exception as e:  # noqa: BLE001
        return PersistResolution(None, None, False, error=f"{type(e).__name__}: {e}")

    if isinstance(res, tuple):
        obj = res[0] if res else None
        code = res[1] if len(res) > 1 and isinstance(res[1], int) else None
    else:
        obj, code = res, None

    resolved = _is_entity(obj) and (code is None or code == PERSIST_OK)
    return PersistResolution(obj if resolved else None, code, resolved)


def resolve_ref(doc: Any, ref: Any) -> RefResolution:
    """Resolve a :class:`DurableRef` to a live entity via the hierarchy.

    Tier 1 (``persist_id``) is performed here. Tier 2 (fingerprint re-match
    against the live body) is **not** performed by this slice — when the token
    is absent or fails to resolve, the result carries
    ``method="fingerprint_fallback"`` so the caller can run the brep re-match.

    Args:
        doc: the live document to resolve against (assumed rebuilt).
        ref: a ``DurableRef`` (uses its ``persist_id`` attribute).
    """
    persist_id = getattr(ref, "persist_id", None)
    if persist_id is not None:
        pr = resolve_persist_id(doc, persist_id)
        if pr.ok:
            return RefResolution(pr.entity, "persist_id", persist=pr)
        return RefResolution(
            None,
            "fingerprint_fallback",
            persist=pr,
            note=(
                f"persist resolve failed (status={pr.status_name}, "
                f"error={pr.error}); fingerprint re-match required"
            ),
        )
    return RefResolution(
        None,
        "fingerprint_fallback",
        persist=None,
        note="no persist_id on ref; fingerprint re-match required",
    )


def select_entity(entity: Any, *, append: bool = False, mark: int = 0) -> bool:
    """Select a resolved entity via an early-bound typed ``IEntity.Select2``.

    The Callout-free ``Select2(Append, Mark)`` form marshals cleanly; this is
    the proven post-resolve selection step (S-EARLYBIND). Returns ``False`` on
    any failure rather than raising, so a resolution that succeeded but whose
    selection failed is distinguishable by the caller.
    """
    if not _is_entity(entity):
        return False
    try:
        ent = earlybind.typed(entity, "IEntity")
        return bool(ent.Select2(append, mark))
    except earlybind.EarlyBindError:
        return False
    except Exception:  # noqa: BLE001
        return False


__all__ = [
    "PERSIST_AMBIGUOUS",
    "PERSIST_DELETED",
    "PERSIST_INVALID",
    "PERSIST_OK",
    "PERSIST_STATUS_NAMES",
    "PERSIST_SUPPRESSED",
    "PersistResolution",
    "RefResolution",
    "capture_persist_id",
    "resolve_persist_id",
    "resolve_ref",
    "select_entity",
]
