"""Look up GUI text in the JSON catalogs shipped with the application."""

from functools import lru_cache
import json
from pathlib import Path
import re
import sys


def _locale_directory():
    app = Path(sys.executable) if getattr(sys, 'frozen', False) else Path(__file__)
    return app.resolve().parent / 'locales'


def _unique_strings(pairs):
    catalog = {}
    for key, text in pairs:
        if key in catalog or not isinstance(text, str):
            raise ValueError('Expected unique keys with string values')
        catalog[key] = text
    return catalog


@lru_cache(maxsize=16)
def _load_catalog(locale):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', locale):
        return {}
    try:
        data = json.loads((_locale_directory() / f'{locale}.json').read_text(encoding='utf-8-sig'),
                          object_pairs_hook=_unique_strings)
    except (OSError, ValueError, RecursionError):
        return {}
    return data if isinstance(data, dict) else {}


def t(key, locale='en', /, **values):
    """Format text in the requested locale, falling back to English, then to the key."""
    for language in (locale, 'en') if locale != 'en' else ('en',):
        template = _load_catalog(language).get(key)
        if template is not None:
            try:
                return template.format(**values)
            except (AttributeError, IndexError, KeyError, ValueError):
                continue
    return key
