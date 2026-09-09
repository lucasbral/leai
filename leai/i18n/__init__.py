"""Internationalization (i18n) package for LEAI."""

from leai.i18n.catalog import (
    AVAILABLE_LOCALES,
    DEFAULT_LOCALE,
    EN_MESSAGES,
    PT_MESSAGES,
    get_locale,
    normalize_locale,
    resolve_locale,
    set_locale,
    t,
)

__all__ = [
    "AVAILABLE_LOCALES",
    "DEFAULT_LOCALE",
    "EN_MESSAGES",
    "PT_MESSAGES",
    "get_locale",
    "normalize_locale",
    "resolve_locale",
    "set_locale",
    "t",
]
