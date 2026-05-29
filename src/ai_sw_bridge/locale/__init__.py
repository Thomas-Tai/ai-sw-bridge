"""i18n scaffold for ai-sw-bridge (W4.5, UIUX §13).

Provides a ``_(text)`` gettext-style translation function. With the
default ``en_US`` locale, strings pass through unchanged. When a
non-default locale is active, translations are looked up from
compiled ``.mo`` catalogs under this package.

Usage::

    from ai_sw_bridge.locale import _

    print(_("Build complete"))   # → "Build complete" (en_US)

To switch locales at runtime::

    from ai_sw_bridge.locale import set_locale
    set_locale("de_DE")

No strings are translated yet — this is architectural scaffolding.
The en_US catalog is empty; the loader is functional.
"""

from ._runtime import _, get_locale, set_locale

__all__ = ["_", "get_locale", "set_locale"]
