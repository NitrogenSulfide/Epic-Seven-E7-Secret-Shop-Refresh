import json
from pathlib import Path
from collections import Counter
from string import Formatter
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import e7_i18n
from e7_i18n import t
import e7_shop_refresh_gui as gui
from e7_tracker import short_remaining


class EnglishCatalogTests(unittest.TestCase):
    def test_original_english_text_and_number_format(self):
        self.assertEqual(t('session.start'), 'Start Refresh')
        self.assertEqual(t('budget.estimated_gold', amount=184000), 'Gold needed ≈ 184,000')
        self.assertEqual(t('session.reported_spend', refreshes=1234, amount=3702),
                         '1,234 refreshes · 3,702 skystone spent · engine reported')

    def test_catalog_also_loads_beside_packaged_executable(self):
        bundled_catalog = Path(__file__).resolve().parent / 'locales' / 'en.json'
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary).resolve()
            locales = folder / 'locales'
            locales.mkdir()
            (locales / 'en.json').write_bytes(bundled_catalog.read_bytes())
            e7_i18n._load_catalog.cache_clear()
            self.addCleanup(e7_i18n._load_catalog.cache_clear)
            with patch.object(e7_i18n.sys, 'frozen', True, create=True), \
                    patch.object(e7_i18n.sys, 'executable', str(folder / 'E7 Secret Shop Refresh.exe')):
                self.assertEqual(e7_i18n._locale_directory(), locales)
                self.assertEqual(t('budget.gold_limit'), 'Gold spending limit')


class BrazilianPortugueseTests(unittest.TestCase):
    def tearDown(self):
        e7_i18n.set_locale('en')

    def test_catalog_keys_and_placeholders_match(self):
        directory = Path(__file__).resolve().parent / 'locales'
        def read(locale):
            return json.loads((directory / f'{locale}.json').read_text(encoding='utf-8'),
                              object_pairs_hook=e7_i18n._unique_strings)

        english, portuguese = read('en'), read('pt_BR')
        self.assertEqual(english.keys(), portuguese.keys())
        for key, source in english.items():
            with self.subTest(key=key):
                def fields(value):
                    return Counter((name, spec, conversion)
                                   for _, name, spec, conversion in Formatter().parse(value)
                                   if name is not None)
                self.assertEqual(fields(source), fields(portuguese[key]))
        self.assertIn(
            'Mesmo utilizando o aplicativo em português, mantenha o Epic Seven em inglês '
            'para que o reconhecimento de itens funcione.',
            portuguese['about.quickstart'],
        )

    def test_budget_and_diagnostics_localize_only_the_display(self):
        root = gui.tk.Tcl()
        app = SimpleNamespace(
            budget=gui.tk.StringVar(root, value='12'),
            ev=gui.tk.StringVar(root), budget_summary=gui.tk.StringVar(root),
            buy_covenant=gui.tk.BooleanVar(root, value=True),
            buy_mystic=gui.tk.BooleanVar(root, value=True),
            buy_friendship=gui.tk.BooleanVar(root, value=True),
            covenant=gui.tk.StringVar(root, value='1'),
            mystic=gui.tk.StringVar(root, value='2'),
            friendship=gui.tk.StringVar(root, value='3'),
            run_settings=SimpleNamespace(buy_covenant=True, buy_mystic=False, buy_friendship=True),
            diagnostics_summary=gui.tk.StringVar(root),
            _update_spent_display=lambda: None,
        )
        for locale, gold, decimal, enabled, disabled in (
            ('en', '20,292', '0.1', 'on', 'off'),
            ('pt_BR', '20.292', '0,1', 'ativado', 'desativado'),
        ):
            with self.subTest(locale=locale):
                e7_i18n.set_locale(locale)
                gui.RefreshGui._update_ev(app)
                self.assertIn(gold, app.ev.get())
                self.assertIn(decimal, app.ev.get())
                self.assertIn(gold, app.budget_summary.get())
                self.assertIn(decimal, app.budget_summary.get())
                gui.RefreshGui._update_diagnostics_summary(app)
                self.assertIn(f'1 ({enabled})', app.diagnostics_summary.get())
                self.assertIn(f'2 ({disabled})', app.diagnostics_summary.get())
                self.assertIn(f'3 ({enabled})', app.diagnostics_summary.get())
                self.assertEqual(app.budget.get(), '12')
                self.assertFalse(app.run_settings.buy_mystic)
        self.assertIn('18.000', app.ev.get())

    def test_localized_presentation_keeps_engine_markers(self):
        e7_i18n.set_locale('pt_BR')
        self.assertEqual(t('session.start'), 'Iniciar sessão')
        self.assertEqual(gui.mode_title('Background'), 'Segundo plano')
        self.assertTrue(gui.mode_label('Background').startswith('Background ·'))
        self.assertEqual(t('budget.estimated_gold', amount=42), 'Ouro necessário ≈ 42')
        self.assertEqual(short_remaining('Time remaining: ~4m'), 'Restam 4m')
        self.assertEqual(gui.navigation_hint('Waiting for visible game controls.'),
                         t('tracker.close_game_popups'))
        self.assertEqual(t('session.start', 'en'), 'Start Refresh')

    def test_language_persistence_and_application_at_startup(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            preferences = directory / 'ShopRefreshGUI.ini'
            self.assertEqual(gui.load_language(preferences), 'en')
            preferences.write_text('[GUI]\nlanguage = unknown%value\nsound_enabled = False\n'
                                   'gold_cap = 500000\n[Other]\nkeep = yes\n', encoding='utf-8')
            self.assertEqual(gui.load_language(preferences), 'en')
            gui.save_language(preferences, 'pt_BR')
            self.assertEqual(gui.load_language(preferences), 'pt_BR')
            self.assertEqual(t('session.start'), 'Start Refresh')
            for line in ('sound_enabled = False', 'gold_cap = 500000', 'keep = yes'):
                self.assertIn(line, preferences.read_text(encoding='utf-8'))
            with patch.object(gui, 'configure_engine_directory'), patch.object(gui, 'configure_data_directory'), \
                    patch.object(gui, 'prepare_data_directory',
                                 return_value=SimpleNamespace(directory=directory, events=[])), \
                    patch.object(gui, 'needs_import_choice', return_value=False), \
                    patch.object(gui, 'RefreshGui') as window:
                window.side_effect = lambda: self._localized_window()
                self.assertEqual(gui.main([]), 0)

    def _localized_window(self):
        self.assertEqual(t('session.start'), 'Iniciar sessão')
        return SimpleNamespace(mainloop=lambda: None)

    def test_unreadable_preferences_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            preferences = Path(temporary) / 'ShopRefreshGUI.ini'
            preferences.write_bytes(b'invalid ini')
            self.assertEqual(gui.load_language(preferences), 'en')
            with self.assertRaises(gui.configparser.Error):
                gui.save_language(preferences, 'pt_BR')
            self.assertEqual(preferences.read_bytes(), b'invalid ini')


class CatalogFallbackTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        locale_directory = patch.object(e7_i18n, '_locale_directory', return_value=self.directory)
        locale_directory.start()
        self.addCleanup(locale_directory.stop)
        e7_i18n._load_catalog.cache_clear()
        self.addCleanup(e7_i18n._load_catalog.cache_clear)
        self.write_catalog('en', {'session.start': 'Start Refresh',
                                  'budget.limit': 'Limit: {amount:,}'})

    def write_catalog(self, locale, messages):
        (self.directory / f'{locale}.json').write_text(json.dumps(messages), encoding='utf-8')

    def test_partial_catalog_and_named_arguments(self):
        self.write_catalog('sample', {'budget.limit': '[{amount:,}]'})
        self.assertEqual(t('budget.limit', 'sample', amount=1200), '[1,200]')
        self.assertEqual(t('session.start', 'sample'), 'Start Refresh')
        self.assertEqual(t('budget.limit', amount=1200), 'Limit: 1,200')

    def test_missing_catalog_and_unknown_key(self):
        self.assertEqual(t('session.start', 'missing'), 'Start Refresh')
        self.assertEqual(t('session.missing', 'missing'), 'session.missing')

    def test_invalid_catalogs_fall_back_to_english(self):
        invalid = (b'{', b'[]', b'{"session.start":8}',
                   b'{"session.start":"one","session.start":"two"}', b'\xff')
        for number, content in enumerate(invalid):
            locale = f'invalid_{number}'
            with self.subTest(content=content):
                (self.directory / f'{locale}.json').write_bytes(content)
                self.assertEqual(t('session.start', locale), 'Start Refresh')

    def test_invalid_template_falls_back_to_english(self):
        self.write_catalog('sample', {'budget.limit': 'Limit: {unexpected}'})
        self.assertEqual(t('budget.limit', 'sample', amount=1200), 'Limit: 1,200')

    def test_unavailable_english_uses_the_key(self):
        (self.directory / 'en.json').unlink()
        self.assertEqual(t('session.start'), 'session.start')


if __name__ == '__main__':
    unittest.main()
