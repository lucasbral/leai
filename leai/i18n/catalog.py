"""Message catalog and translation engine with safe fallback."""

from __future__ import annotations

import os
from typing import Any

from leai.i18n.locales.en_us import MESSAGES as EN_MESSAGES
from leai.i18n.locales.pt_br import MESSAGES as PT_MESSAGES

DEFAULT_LOCALE = "en-US"
AVAILABLE_LOCALES = ("en-US", "pt-BR")

CATALOGS: dict[str, dict[str, str]] = {
    "en-US": EN_MESSAGES,
    "pt-BR": PT_MESSAGES,
}

_CURRENT_LOCALE: str = DEFAULT_LOCALE


def normalize_locale(locale_str: str | None) -> str:
    """Normalizes locale inputs (e.g. 'pt', 'pt_BR', 'pt-br') to canonical 'en-US' or 'pt-BR'."""
    if not locale_str:
        return DEFAULT_LOCALE
    clean = locale_str.strip().lower().replace("_", "-")
    if clean.startswith("pt"):
        return "pt-BR"
    return DEFAULT_LOCALE


def get_locale() -> str:
    """Returns the current active locale."""
    global _CURRENT_LOCALE
    return _CURRENT_LOCALE


def set_locale(locale: str | None) -> str:
    """Sets the active locale and returns the normalized locale name."""
    global _CURRENT_LOCALE
    _CURRENT_LOCALE = normalize_locale(locale)
    return _CURRENT_LOCALE


def resolve_locale(
    cli_lang: str | None = None,
    cfg_lang: str | None = None,
    config_lang: str | None = None,
) -> str:
    """Resolves locale according to precedence: CLI flag > ENV var > config file > default ('en-US')."""
    if cli_lang:
        return normalize_locale(cli_lang)

    env_lang = os.environ.get("LEAI_LANG") or os.environ.get("LEAI_LANGUAGE")
    if env_lang:
        return normalize_locale(env_lang)

    active_cfg = cfg_lang or config_lang
    if active_cfg:
        return normalize_locale(active_cfg)

    return DEFAULT_LOCALE


def t(key: str, locale: str | None = None, **kwargs: Any) -> str:
    """Translates a key into the active locale with safe fallback and interpolation."""
    target_locale = normalize_locale(locale) if locale else _CURRENT_LOCALE
    catalog = CATALOGS.get(target_locale, EN_MESSAGES)
    template = catalog.get(key)

    # Fallback to English if missing in target locale
    if template is None and target_locale != "en-US":
        template = EN_MESSAGES.get(key)

    # If still not found, return key
    if template is None:
        template = key

    if not kwargs:
        return template

    try:
        return template.format(**kwargs)
    except (KeyError, IndexError, ValueError):
        # Fallback to template as-is on formatting error
        return template
