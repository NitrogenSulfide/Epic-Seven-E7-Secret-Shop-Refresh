"""Show the engine's English progress and pause messages in the GUI language.

The engine always prints English, and the log, Diagnostics and copied reports
keep that English so bug reports stay readable. Only what the GUI shows on
screen (the line under the banner and the Activity rows) goes through here.

Each message is an `engine.*` key whose English text in locales/en.json is the
exact line the engine prints, with {name} where the engine fills something in.
A message that matches none of them is shown unchanged, in English.
"""

from functools import lru_cache
import re
from string import Formatter

from e7_i18n import current_locale, english_template, t

# Navigation lines, without their 'Navigation: ' prefix (e7_shop_flow.py,
# E7ADBShopRefresh.py), then Background and Mouse pause reasons
# (e7_background.py, e7_native_mouse.py, e7_windows_capture.py).
MESSAGE_KEYS = (
    'engine.nav.shop_already_open',
    'engine.nav.shop_verified',
    'engine.nav.opening_shop',
    'engine.nav.shop_did_not_open',
    'engine.nav.revealing_home_controls',
    'engine.nav.clicking_to_reveal',
    'engine.nav.looking_for_shop',
    'engine.nav.row_greyed_out',
    'engine.nav.blank_confirmation',
    'engine.nav.confirmation_animating',
    'engine.nav.visibility_restored_recheck',
    'engine.nav.visibility_restored_confirmation',
    'engine.nav.pointer_confirm_again',
    'engine.nav.confirm_not_taken',
    'engine.nav.item_moved',
    'engine.nav.buy_dialog_retry',
    'engine.nav.refresh_dialog_retry',
    'engine.nav.confirm_maybe_sent',
    'engine.nav.shop_not_recognized',
    'engine.nav.list_did_not_scroll',
    'engine.nav.list_drag_other_way',
    'engine.pause.window_closed',
    'engine.pause.window_minimized',
    'engine.pause.pointer_over_game',
    'engine.pause.pointer_over_game_windows',
    'engine.pause.focus_lost',
    'engine.pause.mouse_target_covered',
    'engine.pause.not_foreground',
    'engine.pause.view_covered',
)

# Placeholders whose value is itself engine wording (an item or an action);
# a value with no `engine.value.*` entry is shown as the engine wrote it.
TRANSLATED_FIELDS = {'item', 'operation', 'what'}


def _value_key(name, value):
    return f'engine.value.{name}.' + re.sub(r'[^a-z0-9]+', '_', value.lower()).strip('_')


@lru_cache(maxsize=None)
def _patterns():
    patterns = []
    for key in MESSAGE_KEYS:
        template = english_template(key)
        if template is None:
            continue
        regex = ''
        for literal, field, _spec, _conversion in Formatter().parse(template):
            regex += re.escape(literal)
            if field is not None:
                regex += f'(?P<{field}>.+?)'
        patterns.append((key, re.compile(regex)))
    return tuple(patterns)


def _value(name, value, locale):
    if name not in TRANSLATED_FIELDS:
        return value
    key = _value_key(name, value)
    text = t(key, locale)
    return value if text == key else text


def engine_text(message, locale=None):
    """message in the GUI language when it is a known engine line, else unchanged."""
    locale = current_locale() if locale is None else locale
    if locale == 'en':
        return message
    for key, pattern in _patterns():
        match = pattern.fullmatch(message)
        if match:
            values = {name: _value(name, value, locale) for name, value in match.groupdict().items()}
            return t(key, locale, **values)
    return message


def navigation_text(message, locale=None):
    """An Activity row for a Navigation line (message without its prefix)."""
    return t('engine.navigation_line', locale, message=engine_text(message, locale))
