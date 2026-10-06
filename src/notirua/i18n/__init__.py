"""gettext-based translation shared by the core, CLI, and GUI.

The core never formats translated sentences for progress events; it marks
message ids with :func:`N_` and the UI translates them with :func:`_`.
Adding a language only requires dropping ``locales/<lang>/LC_MESSAGES/notirua.po``
into the locales directory: missing ``.mo`` files are compiled in memory.
"""

from __future__ import annotations

import gettext
import io
import locale
import os
import sys
import threading
from pathlib import Path

DOMAIN = "notirua"
SOURCE_LANGUAGE = "en"

_lock = threading.Lock()
_translations: gettext.NullTranslations = gettext.NullTranslations()
_current_language = SOURCE_LANGUAGE
_locales_dir_override: Path | None = None


def locales_dir() -> Path:
    """Return the directory holding ``<lang>/LC_MESSAGES/notirua.{po,mo}``."""
    if _locales_dir_override is not None:
        return _locales_dir_override
    env = os.environ.get("NOTIRUA_LOCALES_DIR")
    if env:
        return Path(env)
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        return Path(bundle_root) / "locales"
    # src/notirua/i18n/__init__.py -> repository root
    return Path(__file__).resolve().parents[3] / "locales"


def set_locales_dir(path: Path | None) -> None:
    """Override the locales directory (used by tests)."""
    global _locales_dir_override
    _locales_dir_override = path


def available_languages() -> list[str]:
    """Languages with a catalog in the locales directory, plus the source language."""
    found = {SOURCE_LANGUAGE}
    root = locales_dir()
    if root.is_dir():
        for child in root.iterdir():
            messages = child / "LC_MESSAGES"
            if (messages / f"{DOMAIN}.po").is_file() or (messages / f"{DOMAIN}.mo").is_file():
                found.add(child.name)
    return sorted(found)


def fallback_chain(language: str) -> list[str]:
    """Expand ``pt_BR`` into ``["pt_BR", "pt"]``; normalizes ``-`` and encodings."""
    tag = language.split(".")[0].split("@")[0].replace("-", "_")
    if not tag:
        return []
    chain = [tag]
    if "_" in tag:
        chain.append(tag.split("_")[0])
    return chain


def os_language() -> str | None:
    """Best-effort OS UI language, e.g. ``ko_KR``."""
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var)
        if value and value not in ("C", "POSIX", "C.UTF-8"):
            return value.split(":")[0]
    try:
        lang, _enc = locale.getlocale()
    except ValueError:
        lang = None
    return lang


def resolve_language(user_setting: str | None, os_lang: str | None = None) -> str:
    """Pick a language: user setting -> OS locale -> English, honoring fallback chains."""
    available = set(available_languages())
    for candidate in (user_setting, os_lang if os_lang is not None else os_language()):
        if not candidate:
            continue
        for tag in fallback_chain(candidate):
            if tag in available:
                return tag
    return SOURCE_LANGUAGE


def _load_catalog(language: str) -> gettext.NullTranslations:
    messages = locales_dir() / language / "LC_MESSAGES"
    mo_path = messages / f"{DOMAIN}.mo"
    po_path = messages / f"{DOMAIN}.po"
    if mo_path.is_file() and (
        not po_path.is_file() or mo_path.stat().st_mtime >= po_path.stat().st_mtime
    ):
        with mo_path.open("rb") as fp:
            return gettext.GNUTranslations(fp)
    if po_path.is_file():
        from babel.messages.mofile import write_mo
        from babel.messages.pofile import read_po

        with po_path.open("rb") as fp:
            catalog = read_po(fp, locale=language)
        buffer = io.BytesIO()
        write_mo(buffer, catalog)
        buffer.seek(0)
        return gettext.GNUTranslations(buffer)
    return gettext.NullTranslations()


def set_language(language: str) -> str:
    """Activate ``language`` (with fallbacks) and return the language actually used."""
    global _translations, _current_language
    resolved = resolve_language(language, os_lang="")
    translations = (
        gettext.NullTranslations() if resolved == SOURCE_LANGUAGE else _load_catalog(resolved)
    )
    with _lock:
        _translations = translations
        _current_language = resolved
    return resolved


def translator(language: str | None) -> gettext.NullTranslations:
    """A translations object for ``language`` without changing the active language.

    Used for PDF labels, which may use a different language than the UI (FR-9).
    """
    if language is None:
        return _translations
    resolved = resolve_language(language, os_lang="")
    if resolved == SOURCE_LANGUAGE:
        return gettext.NullTranslations()
    return _load_catalog(resolved)


def current_language() -> str:
    return _current_language


def _(message: str) -> str:
    return _translations.gettext(message)


def ngettext(singular: str, plural: str, n: int) -> str:
    return _translations.ngettext(singular, plural, n)


def pgettext(context: str, message: str) -> str:
    return _translations.pgettext(context, message)


def N_(message: str) -> str:
    """Mark ``message`` for extraction without translating it now."""
    return message


def translate_message(message_id: str, args: dict[str, object] | None = None) -> str:
    """Translate a deferred message id (from progress events or errors) and fill it."""
    text = _(message_id)
    if args:
        try:
            return text.format(**args)
        except (KeyError, IndexError, ValueError):
            return message_id.format(**args)
    return text


def translate_progress(message_id: str, args: dict[str, object] | None = None) -> str:
    """Like :func:`translate_message`, but string arguments (instrument and component
    names inside progress events) are message ids too."""
    translated = {k: (_(v) if isinstance(v, str) else v) for k, v in (args or {}).items()}
    return translate_message(message_id, translated)
