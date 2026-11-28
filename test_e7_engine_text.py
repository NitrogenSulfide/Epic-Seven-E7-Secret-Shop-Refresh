import ast
import json
from pathlib import Path
from string import Formatter
from types import SimpleNamespace
import unittest
import unittest.mock

import e7_i18n
from e7_engine_text import MESSAGE_KEYS, engine_text, navigation_text
from e7_i18n import english_template, t
import e7_shop_refresh_gui as gui

REPO = Path(__file__).resolve().parent
# Engine modules that print Navigation lines or produce pause reasons.
ENGINE_FILES = ('e7_shop_flow.py', 'E7ADBShopRefresh.py', 'e7_background.py',
                'e7_native_mouse.py', 'e7_windows_capture.py')
SAMPLES = {'item': 'Mystic medal', 'operation': 'refresh', 'seconds': '10',
           'what': 'Covenant bookmark purchase', 'x': '12', 'y': '34'}


def navigation_prints(path):
    """Each print('Navigation: ...') in path as English text, f-string parts as 'X'."""
    found = []
    for node in ast.walk(ast.parse((REPO/path).read_text(encoding='utf-8'))):
        if not (isinstance(node, ast.Call) and getattr(node.func, 'id', None) == 'print' and node.args):
            continue
        arg = node.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            text = arg.value
        elif isinstance(arg, ast.JoinedStr):
            text = ''.join(part.value if isinstance(part, ast.Constant) else 'X' for part in arg.values)
        else:
            continue
        if text.startswith('Navigation: '):
            found.append((node.lineno, text[len('Navigation: '):]))
    return found


class EngineTextTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(e7_i18n.set_locale, e7_i18n.current_locale())

    def test_every_navigation_line_the_engine_prints_is_translated(self):
        lines = [(path, line, text) for path in ('e7_shop_flow.py', 'E7ADBShopRefresh.py')
                 for line, text in navigation_prints(path)]
        self.assertGreaterEqual(len(lines), 20)
        for path, line, text in lines:
            with self.subTest(at=f'{path}:{line}', text=text):
                self.assertNotEqual(engine_text(text, 'pt_BR'), text,
                                    'Add an engine.nav.* key to locales/en.json and pt_BR.json')

    def test_english_templates_are_still_what_the_engine_prints(self):
        # Every whole string the engine source contains (adjacent literals are already
        # joined by the parser; f-string parts become 'X'), without a Navigation prefix.
        strings = set()
        for name in ENGINE_FILES:
            for node in ast.walk(ast.parse((REPO/name).read_text(encoding='utf-8'))):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    text = node.value
                elif isinstance(node, ast.JoinedStr):
                    text = ''.join(p.value if isinstance(p, ast.Constant) else 'X' for p in node.values)
                else:
                    continue
                strings.add(text.removeprefix('Navigation: '))
        for key in MESSAGE_KEYS:
            with self.subTest(key=key):
                template = english_template(key)
                self.assertIsNotNone(template)
                sample = t(key, 'en', **{f: 'X' for _l, f, *_ in Formatter().parse(template) if f})
                self.assertIn(sample, strings, 'The engine no longer prints this exact English text')
        values = {t(k, 'en') for k in json.loads((REPO/'locales'/'en.json').read_text(encoding='utf-8'))
                  if k.startswith('engine.value.')}
        for value in values:
            with self.subTest(value=value):
                self.assertTrue(value in strings or value.removesuffix(' purchase') in strings
                                or value.lower() in strings, value)

    def test_round_trip_in_both_languages(self):
        for key in MESSAGE_KEYS:
            fields = {f for _l, f, *_ in Formatter().parse(english_template(key)) if f}
            english = t(key, 'en', **{f: SAMPLES[f] for f in fields})
            with self.subTest(key=key):
                self.assertEqual(engine_text(english, 'en'), english)
                translated = engine_text(english, 'pt_BR')
                self.assertNotEqual(translated, english)
                self.assertNotIn('{', translated)

    def test_placeholders_that_are_engine_words_are_translated(self):
        self.assertEqual(engine_text('The Mystic medal row is greyed out (already bought); skipping it.', 'pt_BR'),
                         'O item Mystics já foi comprado e está indisponível. Indo para o próximo.')
        message = ('A Confirm click for the last refresh may have reached the game just before stopping. '
                   'It is counted, but its result was not seen; check it in the game.')
        self.assertIn('última atualização', engine_text(message, 'pt_BR'))
        self.assertIn('confirmação da atualização', engine_text(
            'The refresh confirmation is open but still blank (the game may be waiting on the server); '
            'waiting up to 10 more seconds.', 'pt_BR'))
        # An unknown value is shown as the engine wrote it.
        self.assertIn('Rare gear', engine_text('The Rare gear row is greyed out (already bought); skipping it.', 'pt_BR'))

    def test_unknown_lines_stay_english(self):
        for message in ('Something new from a later engine.', '', 'Secret Shop screen verified. Extra'):
            self.assertEqual(engine_text(message, 'pt_BR'), message)
        self.assertEqual(navigation_text('Something new.', 'pt_BR'), 'Navegação: Something new.')
        self.assertEqual(navigation_text('Something new.', 'en'), 'Navigation: Something new.')

    def test_a_broken_template_leaves_its_message_in_english(self):
        import e7_engine_text
        real = e7_engine_text.english_template
        broken = {'engine.nav.shop_verified': 'Secret Shop {screen verified.',
                  'engine.nav.opening_shop': '{item} and {item}'}
        e7_engine_text._patterns.cache_clear()
        self.addCleanup(e7_engine_text._patterns.cache_clear)
        with unittest.mock.patch.object(e7_engine_text, 'english_template', lambda k: broken.get(k, real(k))):
            self.assertEqual(engine_text('Secret Shop screen verified.', 'pt_BR'), 'Secret Shop screen verified.')
            self.assertEqual(engine_text('The game window closed.', 'pt_BR'), 'A janela do jogo foi fechada.')

    def test_pointer_pauses_are_told_apart(self):
        linux = 'Move your mouse off the game window; background input pauses while the pointer is over it.'
        windows = ('Move your mouse off the game window; the game cancels background clicks while the '
                   'pointer rests on it. Park it on the compact tracker bar, the taskbar or another screen.')
        self.assertEqual(engine_text(linux, 'pt_BR'), t('engine.pause.pointer_over_game', 'pt_BR'))
        self.assertEqual(engine_text(windows, 'pt_BR'), t('engine.pause.pointer_over_game_windows', 'pt_BR'))


class GuiDisplayTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(e7_i18n.set_locale, e7_i18n.current_locale())

    def handle(self, line, locale):
        e7_i18n.set_locale(locale)
        details, events, hints = [], [], []
        app = SimpleNamespace(detail=SimpleNamespace(set=details.append),
                              _event=lambda text, shown=None: events.append((text, shown)),
                              _set_compact_hint=hints.append, stopping=False, stop_key_pressed=False,
                              status=SimpleNamespace(get=lambda: 'Ready'))
        gui.RefreshGui._handle_line(app, line)
        return details, events, hints

    def test_navigation_shows_the_translation_and_keeps_english_for_colour(self):
        details, events, hints = self.handle('Navigation: The Secret Shop did not open; checking the home screen again.', 'pt_BR')
        self.assertEqual(details, ['A Loja Secreta não abriu; verificando a tela inicial novamente.'])
        self.assertEqual(events, [('Navigation: The Secret Shop did not open; checking the home screen again.',
                                   'Navegação: A Loja Secreta não abriu; verificando a tela inicial novamente.')])
        self.assertEqual(hints, [t('tracker.shop_click_missed')])

    def test_english_display_is_unchanged(self):
        details, events, _ = self.handle('Navigation: Secret Shop screen verified.', 'en')
        self.assertEqual(details, ['Secret Shop screen verified.'])
        self.assertEqual(events, [('Navigation: Secret Shop screen verified.', 'Navigation: Secret Shop screen verified.')])

    def test_activity_row_colour_comes_from_the_english_text(self):
        rows = []
        app = SimpleNamespace(ui_font=SimpleNamespace(measure=len), _dp=lambda n: n,
                              activity=SimpleNamespace(
                                  column=lambda *a, **k: 0 if a[1:] == ('minwidth',) else None,
                                  insert=lambda *a, **k: rows.append(k) or 'i1',
                                  get_children=lambda: ['i1'], delete=lambda *_: None, see=lambda *_: None))
        gui.RefreshGui._event(app, 'The game window is minimized or hidden.', 'A janela do jogo está minimizada ou oculta.')
        self.assertEqual(rows[0]['values'][1], 'A janela do jogo está minimizada ou oculta.')
        self.assertEqual(rows[0]['tags'], ())  # 'minimized' carries no colour word; same as English
        gui.RefreshGui._event(app, 'Navigation: The shop was not recognized on this frame; waiting and checking again.',
                              'Navegação: A loja não foi reconhecida nesta imagem; aguardando e verificando novamente.')
        self.assertEqual(rows[1]['tags'], ('error',))


if __name__ == '__main__':
    unittest.main()
