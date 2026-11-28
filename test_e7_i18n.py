from contextlib import ExitStack, contextmanager
import csv
import json
from pathlib import Path
from collections import Counter
from string import Formatter
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from xml.etree import ElementTree
from zipfile import ZipFile

import e7_history
import e7_i18n
from e7_i18n import t
import e7_shop_refresh_gui as gui
from e7_tracker import short_remaining


class EnglishCatalogTests(unittest.TestCase):
    def test_original_english_text_and_number_format(self):
        self.assertEqual(t('session.start'), 'Start Refresh')
        self.assertEqual(t('budget.estimated_gold', amount=184000), 'Gold needed ≈ 184,000')

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
                self.assertEqual(t('budget.gold_limit'), 'Gold budget')


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


class LocalizationPolishTests(unittest.TestCase):
    @contextmanager
    def window(self, language):
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            folder = Path(temporary)
            for name, path in {'APP_DIR': folder, 'CONFIG_FILE': folder / 'engine.ini',
                               'GUI_CONFIG_FILE': folder / 'gui.ini', 'HISTORY_FILE': folder / 'history.csv'}.items():
                stack.enter_context(patch.object(gui, name, path))
            for method in ('refresh_devices', '_change_control_mode', '_maybe_show_credits', '_play_session_sound'):
                stack.enter_context(patch.object(gui.RefreshGui, method))
            stack.callback(e7_i18n.set_locale, e7_i18n.current_locale())
            e7_i18n.set_locale(language)
            app = gui.RefreshGui()
            stack.callback(app.destroy)
            app.withdraw()
            yield app, folder

    def test_numeric_controls_estimates_and_live_progress(self):
        for language, thousands in (('en', ','), ('pt_BR', '.')):
            with self.subTest(language=language), self.window(language) as (app, _):
                pt = language == 'pt_BR'
                app.tap_jitter.set(.03)
                app.random_offset.set(True)
                app.tap_sleep.set('.01')
                app._update_tap_jitter()
                self.assertEqual(app.tap_jitter_text.get(), 'Variação do intervalo: ±0,005 s' if pt
                                 else 'Timing variation: ±0.005s')
                self.assertEqual(app.tap_jitter.get(), .03)
                app.tap_sleep.set('.30')
                self.assertEqual(app.tap_jitter_text.get(), 'Variação do intervalo: ±0,03 s' if pt
                                 else 'Timing variation: ±0.03s')
                delay_hint = ('De 0,30 a 2,00 segundos · valores menores são ajustados para 0,30' if pt
                              else '0.30 to 2.00 seconds · lower values are raised to 0.30')
                self.assertTrue(app.delay_hint.text().startswith(delay_hint))

                app.budget.set('3000')
                self.assertIn(f'1{thousands}000 ', app.budget_summary.get())
                app.budget.set('750')
                app.buy_mystic.set(True)
                app.buy_covenant.set(False)
                self.assertIn('cerca de 1,3 compras de Mystics' if pt else 'expect about 1.3 Mystic',
                              app.budget_summary.get())
                app.buy_covenant.set(True)
                self.assertIn('5,0 compras de Bookmarks e 1,3 compras de Mystics' if pt
                              else '5.0 Covenant and 1.3 Mystic', app.budget_summary.get())

                app.buy_friendship.set(True)
                app.run_settings = gui.validate_settings('fixture', '6000', '.3', '`', True, False,
                                                         buy_friendship=True)
                stats = dict(refreshes=1500, skystone_spent=4500, covenant=12, mystic=3, friendship=1200)
                protocol = 'E7GUI_STATS ' + json.dumps(stats) + '\n'
                app._handle_output_batch([(protocol, None)])
                progress = ('1.500 atualizações · 4.500 Skystones gastas · dados da engine · Compras de amizade: 1.200'
                            if pt else '1,500 refreshes · 4,500 skystone spent · engine reported · Friendship buys: 1,200')
                self.assertEqual(app.progress_text.get(), progress)
                self.assertEqual((app.progress['value'], app.spent.get(), app.friendship.get()), (75, '4,500', '1,200'))
                self.assertEqual(app.raw_output, protocol)

    def test_finish_details_preserve_status_activity_and_reports(self):
        cases = (
            (0, True, False, None, 'Finished', 'Session finished. Results are shown below.',
             'Sessão concluída. Veja os resultados abaixo.'),
            (0, False, True, None, 'Stopped', 'Session stopped. History contains only runs recorded by the engine.',
             'Sessão interrompida. O histórico inclui apenas as sessões registradas pela engine.'),
            (7, False, False, None, 'Needs attention', 'Engine exited (code 7). Check Diagnostics before retrying.',
             'A engine foi encerrada (código 7). Consulte Diagnóstico antes de tentar novamente.'),
            (0, True, False, 'Gold limit reached: 1,000', 'Stopped', 'Gold limit reached: 1,000', 'Gold limit reached: 1,000'),
        )
        for language in ('en', 'pt_BR'):
            with self.window(language) as (app, _):
                app._update_diagnostics_summary()
                self.assertIn('Nenhuma sessão ativa' if language == 'pt_BR' else 'No active session',
                              app.diagnostics_summary.get())
                with patch.object(app, 'clipboard_clear'), patch.object(app, 'clipboard_append') as clipboard:
                    app._copy_diagnostics()
                    self.assertIn('Stop key: No active session', clipboard.call_args.args[0])
                for code, finished, stopping, gold, status, english, portuguese in cases:
                    with self.subTest(language=language, status=status, gold=gold):
                        app.run_id += 1
                        app.finished, app.stopping = finished, stopping
                        app._gold_stop_reason = gold
                        app.process = SimpleNamespace(returncode=code, poll=lambda: code)
                        app._finish_process()
                        self.assertEqual(app.status.get(), status)
                        self.assertEqual(app.detail.get(), portuguese if language == 'pt_BR' else english)
                        item = app.activity.get_children()[-1]
                        self.assertEqual(app.activity.item(item, 'values')[1], english)
                        if status == 'Needs attention':
                            self.assertIn(english, app._report_text())

    def test_history_headings_are_independent_of_csv_and_excel(self):
        ids = ('mode', 'duration', 'skystone', 'gold', 'cov', 'mys', 'friend', 'started', 'control', 'outcome')
        headers = ('Session ID', 'Started at', 'Control mode', 'Mode', 'Outcome', 'Reason', 'Duration',
                   'Skystone spent', 'Gold spent', 'Covenant bookmark', 'Mystic medal', 'Friendship points',
                   'Friendship bookmark', 'Legacy extra fields')
        for language, labels in (
            ('en', ('Mode', 'Duration', 'Skystone', 'Gold', 'Covenant buys', 'Mystic buys', 'Friendship buys',
                    'Started (UTC)', 'Control', 'Outcome')),
            ('pt_BR', ('Modo', 'Duração', 'Skystones', 'Ouro', 'Compras de Bookmarks', 'Compras de Mystics',
                       'Compras de amizade', 'Início (UTC)', 'Controle', 'Resultado')),
        ):
            with self.subTest(language=language), self.window(language) as (app, folder):
                self.assertEqual(app.history['columns'], ids)
                self.assertEqual(tuple(app.history.heading(key, 'text') for key in ids), labels)
                for key, label in zip(ids, labels):
                    self.assertGreaterEqual(app.history.column(key, 'minwidth'), app.heading_font.measure(label))

                legacy = (b'Duration,Skystone spent,Gold spent,Covenant bookmark,Mystic medal\n'
                          b'10.25,2799,7656000,1500.25,\n')
                gui.HISTORY_FILE.write_bytes(legacy)
                app.refresh_history()
                row, = app.history.get_children()
                counts = ('2.799', '7.656.000', '1.500') if language == 'pt_BR' else ('2,799', '7,656,000', '1,500')
                self.assertEqual(app.history.item(row, 'values'), (
                    'Normal', '0m 10s', *counts, '—', '—', '', 'Unknown', 'Unknown (legacy)'))
                self.assertEqual(gui.HISTORY_FILE.read_bytes(), legacy)
                e7_history.append_session(gui.HISTORY_FILE, {'Session ID': 'fixture', 'Mode': 'Normal'})
                with gui.HISTORY_FILE.open(newline='', encoding='utf-8') as source:
                    reader = csv.DictReader(source)
                    self.assertEqual(tuple(reader.fieldnames), headers)
                    recorded = next(reader)
                    self.assertEqual(tuple(recorded[field] for field in headers[6:12]),
                                     ('10.25', '2799', '7656000', '1500.25', '', ''))

                workbook = folder / 'history.xlsx'
                with patch.object(gui.filedialog, 'asksaveasfilename', return_value=str(workbook)):
                    app._export_history()
                with ZipFile(workbook) as package:
                    sheet = ElementTree.fromstring(package.read('xl/worksheets/sheet1.xml'))
                self.assertEqual(tuple(node.text for node in sheet.findall('.//{*}row[@r="1"]/{*}c/{*}is/{*}t')), (
                    'Session ID', 'Started at (UTC)', 'Control mode', 'Mode', 'Outcome', 'Reason', 'Duration (seconds)',
                    'Skystone spent', 'Gold spent', 'Covenant buys', 'Mystic buys', 'Friendship buys',
                    'Friendship points gained', 'Legacy Friendship bookmarks', 'Legacy extra fields',
                ))
                for column, value in zip('GHIJ', ('10.25', '2799.0', '7656000.0', '1500.25')):
                    self.assertEqual(sheet.findtext(f'.//{{*}}c[@r="{column}2"][@t="n"]/{{*}}v'), value)

    def test_recent_sessions_notice_for_empty_singular_and_plural_history(self):
        for language, empty, singular, plural, suffix in (
            ('en', 'No recorded sessions yet.', 'Showing the latest session', 'Showing latest {count} sessions',
             ' · Excel exports all recorded sessions · select a row for its end reason'),
            ('pt_BR', 'Nenhuma sessão registrada.', 'Última sessão', 'Últimas {count} sessões',
             ' · O Excel inclui todas · Selecione uma linha para ver por que a sessão terminou'),
        ):
            with self.window(language) as (app, _):
                app.refresh_history()
                self.assertEqual(app.history_notice.get(), empty)
                for count, notice in ((1, singular), (2, plural.format(count=2)), (5, plural.format(count=5))):
                    with self.subTest(language=language, count=count):
                        gui.HISTORY_FILE.write_text('Duration,Skystone spent,Gold spent,Covenant bookmark,Mystic medal\n'
                                                    + '10,9,0,0,0\n' * count, encoding='utf-8')
                        app.refresh_history()
                        self.assertEqual(len(app.history.get_children()), count)
                        self.assertEqual(app.history_notice.get(), notice + suffix)


if __name__ == '__main__':
    unittest.main()
