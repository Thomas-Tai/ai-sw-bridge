"""gettext runtime for the ai-sw-bridge locale scaffold (W4.5).

The translation function ``_(text)`` delegates to a module-level
``gettext.NullTranslations`` instance by default (en_US — strings
pass through unchanged). When :func:`set_locale` is called with a
non-default locale code, the function switches to a
``gettext.GNUTranslations`` loaded from the compiled ``.mo`` catalog
for that locale.

Catalog layout::

    src/ai_sw_bridge/locale/<locale_code>/LC_MESSAGES/ai_sw_bridge.mo

The ``.po`` source files live alongside for contributors::

    src/ai_sw_bridge/locale/<locale_code>/LC_MESSAGES/ai_sw_bridge.po

Compile with ``msgfmt`` or ``python -m msgfmt`` from the CPython
``Tools/i18n`` distribution.
"""

from __future__ import annotations

import gettext
from pathlib import Path

_LOCALE_DIR = Path(__file__).resolve().parent
_DOMAIN = "ai_sw_bridge"
_DEFAULT_LOCALE = "en_US"

_active_locale: str = _DEFAULT_LOCALE
_translations: gettext.NullTranslations = gettext.NullTranslations()


def _(text: str) -> str:
    """Translate *text* using the active locale.

    With the default ``en_US`` locale (or any locale whose catalog
    is missing / empty), returns *text* unchanged.
    """
    return _translations.gettext(text)


def get_locale() -> str:
    """Return the currently active locale code."""
    return _active_locale


def set_locale(code: str) -> None:
    """Switch the active locale to *code*.

    Loads the compiled ``.mo`` catalog from
    ``locale/<code>/LC_MESSAGES/ai_sw_bridge.mo``. Falls back to
    :class:`gettext.NullTranslations` (pass-through) when the catalog
    is absent or unreadable — this means ``en_US`` and any unbuilt
    locale behave identically.
    """
    global _active_locale, _translations
    _active_locale = code
    try:
        _translations = gettext.translation(
            _DOMAIN,
            localedir=str(_LOCALE_DIR),
            languages=[code],
        )
    except FileNotFoundError:
        _translations = gettext.NullTranslations()
