import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import e7_i18n
from e7_i18n import t


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
