"""W74 — configuration LIFECYCLE (derive + delete), sealing the config axis.

The config subsystem already ships variant generation (``create_all`` /
``materialize_all``, W36) and config-level custom properties (W71 metadata
CRUD).  This module adds the two operations that complete full out-of-process
lifecycle management over SOLIDWORKS configurations:

  * ``create_configuration`` — create a standard OR a DERIVED (parent-linked)
    configuration via ``IConfigurationManager.AddConfiguration2`` (the 7-arg
    form that carries ``ParentConfigName``; the ``IModelDoc2`` overload of the
    same name does NOT).
  * ``delete_configuration`` — permanently remove a configuration via
    ``IModelDoc2.DeleteConfiguration2``.

**Seat-cracked recipe (2026-06-22):**

``AddConfiguration2(Name, Comment, AlternateName, Options:Int32,
ParentConfigName:String, Description:String, Rebuild:Boolean) -> Configuration``
— ``Options`` is a ``swConfigurationOptions2_e`` bitmask.  A DERIVED child uses
``swConfigOption_LinkToParent`` (64) plus a non-empty ``ParentConfigName``;
verified by ``IConfiguration.IsDerived() -> True`` and
``GetParent().Name == parent``.

**The active-config delete wall (the W74 footgun):** ``AddConfiguration2`` makes
the new config ACTIVE, and SW REFUSES to delete the active configuration
(``DeleteConfiguration2`` returns ``False`` with the target still present —
masquerading as a no-op).  So ``delete_configuration`` switches to a safe
fallback config (``ShowConfiguration2``, preferring 'Default') BEFORE deleting
when the target is active.  Fail-closed when the target is missing or is the
only remaining configuration (you cannot delete the last config).

All callable-or-property reads (``GetConfigurationNames``, ``.Name``,
``ActiveConfiguration``) are guarded — late-bound dispatch exposes some as
properties, the typed wrapper as methods.
"""

from __future__ import annotations

import logging
from typing import Any

from ..com.earlybind import typed_qi
from ..com.sw_type_info import wrapper_module

logger = logging.getLogger("ai_sw_bridge.config.lifecycle")

# swConfigurationOptions2_e (swconst 32.1 harvest)
SW_CONFIG_LINK_TO_PARENT = 64  # swConfigOption_LinkToParent


def _val(obj: Any, attr: str) -> Any:
    """Read ``attr``, tolerating method-or-property form for SCALAR returns
    (names tuple, string Name): call it iff callable.

    NOT safe for a property that returns a COM dispatch (e.g.
    ``ActiveConfiguration``) — a CDispatch is itself callable and would be
    wrongly invoked ('Member not found'); read those with plain getattr."""
    v = getattr(obj, attr)
    return v() if callable(v) else v


def _active_config(cm: Any) -> Any:
    """The active ``IConfiguration`` (a dispatch PROPERTY — never call it)."""
    return cm.ActiveConfiguration


def _config_names(doc: Any) -> tuple[str, ...]:
    """The doc's configuration names as a tuple ((). on failure)."""
    try:
        n = _val(doc, "GetConfigurationNames")
    except Exception as e:
        logger.warning("[config.lifecycle] GetConfigurationNames RAISED: %r", e)
        return ()
    return tuple(n) if n else ()


def _active_name(doc: Any) -> str | None:
    """The active configuration name (None on failure)."""
    try:
        cm = doc.ConfigurationManager
        active = _active_config(cm)
        if active is None:
            return None
        return _val(active, "Name")
    except Exception as e:
        logger.warning("[config.lifecycle] active-config read RAISED: %r", e)
        return None


def create_configuration(
    doc: Any,
    name: str,
    *,
    parent: str | None = None,
    comment: str = "",
    description: str = "",
    options: int | None = None,
) -> tuple[bool, str | None]:
    """Create a standard or derived configuration on *doc*.

    Fail-closed: returns ``(False, reason)`` on any failure; never raises.

    Args
        name        : new configuration name (required, unique)
        parent      : optional parent configuration name — when supplied, the
                      new config is created DERIVED (parent-linked); the parent
                      must already exist.
        comment     : optional config comment.
        description : optional config description (BOM/description field).
        options     : optional ``swConfigurationOptions2_e`` bitmask override;
                      defaults to ``LinkToParent`` when *parent* is set, else 0.
    """
    if not name or not isinstance(name, str):
        return False, "configuration name must be a non-empty string"
    if parent is not None and (not isinstance(parent, str) or not parent):
        return False, "parent must be a non-empty string (or omitted)"

    existing = _config_names(doc)
    if name in existing:
        return False, f"configuration {name!r} already exists"
    if parent is not None and parent not in existing:
        return False, f"parent configuration {parent!r} does not exist"

    if options is None:
        options = SW_CONFIG_LINK_TO_PARENT if parent else 0

    try:
        cm = doc.ConfigurationManager
        cfg = cm.AddConfiguration2(
            name, comment, "", int(options), parent or "", description, True
        )
    except Exception as exc:
        return False, f"AddConfiguration2 raised: {exc!r}"
    if cfg is None:
        return False, f"AddConfiguration2({name!r}) returned None"

    # verify-the-EFFECT: the name now exists
    if name not in _config_names(doc):
        return False, f"configuration {name!r} not present after AddConfiguration2"

    # derived-hierarchy verify
    if parent:
        try:
            child = typed_qi(
                doc.GetConfigurationByName(name), "IConfiguration",
                module=wrapper_module(),
            )
            is_derived = bool(_val(child, "IsDerived"))
            par = _val(child, "GetParent")
            par_name = _val(par, "Name") if par is not None else None
        except Exception as exc:
            return False, f"derived-hierarchy readback raised: {exc!r}"
        if not is_derived or par_name != parent:
            return False, (
                f"configuration {name!r} created but not derived from "
                f"{parent!r} (IsDerived={is_derived}, parent={par_name!r})"
            )
        return True, (
            f"derived configuration {name!r} created (parent={parent!r}, "
            f"IsDerived=True)"
        )

    return True, f"configuration {name!r} created"


def delete_configuration(doc: Any, name: str) -> tuple[bool, str | None]:
    """Permanently delete a configuration from *doc*.

    Fail-closed: returns ``(False, reason)`` on any failure; never raises.

    Handles the active-config wall: SW refuses to delete the ACTIVE config, so
    if *name* is active this switches to a fallback config (preferring
    'Default') first.  Fails closed when *name* is absent or is the only
    remaining configuration.
    """
    if not name or not isinstance(name, str):
        return False, "configuration name must be a non-empty string"

    names = _config_names(doc)
    if name not in names:
        return False, f"configuration {name!r} is not present"
    if len(names) <= 1:
        return False, (
            f"refusing to delete {name!r}: it is the only configuration "
            f"(a document must retain at least one)"
        )

    # If the target is active, SW will reject the delete — switch away first.
    if _active_name(doc) == name:
        fallback = next(
            (n for n in names if n != name and n == "Default"),
            next((n for n in names if n != name), None),
        )
        if fallback is None:
            return False, f"no fallback configuration to switch to before deleting {name!r}"
        try:
            switched = doc.ShowConfiguration2(fallback)
        except Exception as exc:
            return False, f"ShowConfiguration2({fallback!r}) raised: {exc!r}"
        if not switched:
            return False, f"failed to switch active config to {fallback!r} before delete"

    try:
        ok = bool(doc.DeleteConfiguration2(name))
    except Exception as exc:
        return False, f"DeleteConfiguration2 raised: {exc!r}"

    if not ok:
        return False, f"DeleteConfiguration2({name!r}) returned False"
    if name in _config_names(doc):
        return False, f"configuration {name!r} still present after DeleteConfiguration2"

    return True, f"configuration {name!r} deleted"
