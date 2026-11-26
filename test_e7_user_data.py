"""Per-user settings/history folder and the one-time move from `runtime`.

Temporary folders only: never the installed app, its runtime data, the engine or the game.
"""
import datetime
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import e7_user_data as data
from e7_user_data import prepare_data_directory, MARKER, BACKUP_FOLDER

NOW = datetime.datetime(2026, 11, 25, 12, 0, 0)


def snapshot(folder):
    folder = Path(folder)
    return {str(path.relative_to(folder)): path.read_bytes() for path in sorted(folder.rglob('*')) if path.is_file()}


class DefaultFolderTests(unittest.TestCase):
    def test_windows_uses_local_app_data(self):
        folder = data.default_data_directory({'LOCALAPPDATA': r'C:\Users\x\AppData\Local'}, 'nt', home='/home/x')
        self.assertEqual(folder, Path(r'C:\Users\x\AppData\Local') / 'E7 Secret Shop Refresh')

    def test_windows_without_local_app_data_uses_home(self):
        self.assertEqual(data.default_data_directory({}, 'nt', home='/h'),
                         Path('/h') / 'AppData' / 'Local' / 'E7 Secret Shop Refresh')

    def test_linux_follows_xdg_and_ignores_relative(self):
        self.assertEqual(data.default_data_directory({'XDG_DATA_HOME': '/x/share'}, 'posix', home='/h'),
                         Path('/x/share/e7-shop-refresh'))
        self.assertEqual(data.default_data_directory({'XDG_DATA_HOME': 'relative'}, 'posix', home='/h'),
                         Path('/h/.local/share/e7-shop-refresh'))

    def test_override_wins(self):
        self.assertEqual(data.default_data_directory({'E7_DATA_DIR': '/custom', 'LOCALAPPDATA': '/l'}, 'nt'),
                         Path('/custom'))


class MigrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='e7 user data 日本語 ')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.legacy = self.root / 'release' / 'runtime'
        self.legacy.mkdir(parents=True)
        (self.legacy / 'E7ADBShopRefresh.exe').write_bytes(b'fixture only; never execute')
        self.data = self.root / 'LocalAppData' / 'E7 Secret Shop Refresh'

    def old_install(self):
        (self.legacy / 'ADBconfig.ini').write_text('[Settings]\nbudget = 300\n', encoding='utf-8')
        (self.legacy / 'ShopRefreshGUI.ini').write_text('[GUI]\ncontrol_mode = Mouse\n', encoding='utf-8')
        history = self.legacy / 'ShopRefreshHistory'
        (history / 'archive').mkdir(parents=True)
        (history / 'ADB_History.csv').write_text('Duration,Skystone spent\n12,30\n', encoding='utf-8')
        (history / 'archive' / 'old.csv').write_text('Duration\n1\n', encoding='utf-8')
        return snapshot(self.legacy)

    def prepare(self, **kwargs):
        return prepare_data_directory(self.legacy, self.data, now=NOW, **kwargs)

    def test_fresh_install_uses_new_empty_folder(self):
        before = snapshot(self.legacy)
        location = self.prepare()
        self.assertEqual(location.directory, self.data)
        self.assertTrue(self.data.is_dir())
        self.assertFalse(location.migrated or location.fallback)
        self.assertEqual(location.events, [])
        self.assertEqual(list(self.data.iterdir()), [])
        self.assertEqual(snapshot(self.legacy), before)

    def test_migrates_once_with_backup_and_leaves_runtime_untouched(self):
        before = self.old_install()
        location = self.prepare()
        self.assertTrue(location.migrated)
        self.assertEqual(location.directory, self.data)
        self.assertEqual(snapshot(self.legacy), before)  # never changed or deleted
        moved = {name: content for name, content in before.items() if not name.endswith('.exe')}
        current = snapshot(self.data)
        for name, content in moved.items():
            self.assertEqual(current[name], content)
        backups = list((self.data / BACKUP_FOLDER).iterdir())
        self.assertEqual(len(backups), 1)
        self.assertEqual(snapshot(backups[0]), moved)
        marker = json.loads((self.data / MARKER).read_text(encoding='utf-8'))
        self.assertEqual(Path(marker['source']), self.legacy)
        self.assertEqual(sorted(marker['copied']), sorted(data.MIGRATED_ITEMS))
        self.assertTrue(any('moved to' in event for event in location.events))
        self.assertFalse(any(path.name.startswith('.migrating-') for path in self.data.iterdir()))

    def test_rerun_after_migration_changes_nothing(self):
        self.old_install()
        self.prepare()
        (self.data / 'ADBconfig.ini').write_text('[Settings]\nbudget = 900\n', encoding='utf-8')
        (self.legacy / 'ADBconfig.ini').write_text('[Settings]\nbudget = 1\n', encoding='utf-8')
        after_first = snapshot(self.data)
        for _ in range(3):
            location = self.prepare()
            self.assertEqual((location.directory, location.migrated, location.fallback, location.events),
                             (self.data, False, False, []))
        self.assertEqual(snapshot(self.data), after_first)
        self.assertIn('budget = 900', (self.data / 'ADBconfig.ini').read_text(encoding='utf-8'))

    def test_existing_new_files_are_never_overwritten(self):
        self.old_install()
        self.data.mkdir(parents=True)
        (self.data / 'ShopRefreshGUI.ini').write_text('[GUI]\nnewer = yes\n', encoding='utf-8')
        location = self.prepare()
        self.assertTrue(location.migrated)
        self.assertEqual((self.data / 'ShopRefreshGUI.ini').read_text(encoding='utf-8'), '[GUI]\nnewer = yes\n')
        self.assertIn('budget = 300', (self.data / 'ADBconfig.ini').read_text(encoding='utf-8'))
        self.assertTrue(any('Kept the existing ShopRefreshGUI.ini' in event for event in location.events))
        backup = next((self.data / BACKUP_FOLDER).iterdir())
        self.assertIn('control_mode = Mouse', (backup / 'ShopRefreshGUI.ini').read_text(encoding='utf-8'))

    def test_destination_that_cannot_be_created_falls_back_to_runtime(self):
        before = self.old_install()
        blocker = self.root / 'LocalAppData'
        blocker.write_text('a file where the folder should be', encoding='utf-8')
        location = self.prepare()
        self.assertEqual(location.directory, self.legacy)
        self.assertTrue(location.fallback)
        self.assertIn('Could not create', location.events[0])
        self.assertIn('nothing was deleted', location.events[0])
        self.assertEqual(snapshot(self.legacy), before)

    def test_read_only_destination_falls_back_without_touching_runtime(self):
        before = self.old_install()
        with patch.object(data, '_writable', return_value=False):
            location = self.prepare()
        self.assertEqual(location.directory, self.legacy)
        self.assertTrue(location.fallback)
        self.assertIn('read-only', location.events[0])
        self.assertEqual(snapshot(self.legacy), before)
        self.assertFalse((self.data / MARKER).exists())

    def test_read_only_destination_already_holding_data_is_kept_with_warning(self):
        self.data.mkdir(parents=True)
        (self.data / 'ADBconfig.ini').write_text('[Settings]\n', encoding='utf-8')
        with patch.object(data, '_writable', return_value=False):
            location = self.prepare()
        self.assertEqual(location.directory, self.data)
        self.assertFalse(location.fallback)
        self.assertIn('read-only', location.events[0])

    def test_copy_failure_falls_back_cleans_up_and_retries_next_start(self):
        before = self.old_install()
        real_copytree = shutil.copytree
        calls = []

        def failing_copytree(source, target, *args, **kwargs):
            calls.append(target)
            if '.migrating-' in str(target):
                raise OSError(28, 'No space left on device')
            return real_copytree(source, target, *args, **kwargs)

        with patch.object(data.shutil, 'copytree', failing_copytree):
            location = self.prepare()
        self.assertEqual(location.directory, self.legacy)
        self.assertTrue(location.fallback)
        self.assertIn('migration failed', location.events[0])
        self.assertEqual(snapshot(self.legacy), before)
        self.assertFalse((self.data / MARKER).exists())
        self.assertFalse(any(path.name.startswith('.migrating-') for path in self.data.iterdir()))
        # The next start completes the move from the untouched runtime folder.
        location = self.prepare()
        self.assertEqual(location.directory, self.data)
        self.assertTrue(location.migrated)
        self.assertTrue((self.data / MARKER).exists())
        self.assertEqual((self.data / 'ShopRefreshHistory' / 'ADB_History.csv').read_bytes(),
                         before[str(Path('ShopRefreshHistory') / 'ADB_History.csv')])

    def test_mismatched_copy_is_rejected(self):
        before = self.old_install()
        real_copy2 = shutil.copy2

        def corrupting_copy(source, target, *args, **kwargs):
            result = real_copy2(source, target, *args, **kwargs)
            if '.migrating-' in str(target):
                Path(target).write_bytes(b'corrupt')
            return result

        with patch.object(data.shutil, 'copy2', corrupting_copy):
            location = self.prepare()
        self.assertTrue(location.fallback)
        self.assertEqual(location.directory, self.legacy)
        self.assertFalse((self.data / 'ADBconfig.ini').exists())
        self.assertEqual(snapshot(self.legacy), before)

    def test_same_folder_is_a_no_op(self):
        self.old_install()
        location = prepare_data_directory(self.legacy, self.legacy)
        self.assertEqual((location.directory, location.migrated, location.events), (self.legacy, False, []))

    def test_default_folder_comes_from_environment(self):
        self.old_install()
        location = prepare_data_directory(self.legacy, environ={'E7_DATA_DIR': str(self.data)}, now=NOW)
        self.assertEqual(location.directory, self.data)
        self.assertTrue(location.migrated)


class GuiWiringTests(unittest.TestCase):
    def setUp(self):
        import e7_shop_refresh_gui as gui
        self.gui = gui
        temporary = tempfile.TemporaryDirectory(prefix='e7 gui data ')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        names = ('APP_DIR', 'ENGINE_EXE', 'ADB_EXE', 'CONFIG_FILE', 'GUI_CONFIG_FILE', 'HISTORY_FILE',
                 'DATA_DIR', 'DATA_EVENTS')
        saved = patch.multiple(gui, **{name: getattr(gui, name) for name in names})
        saved.start()
        self.addCleanup(saved.stop)
        platform = patch.multiple(gui, ENGINE_NAME='E7ADBShopRefresh.exe', CONTROL_MODES=('ADB', 'Mouse'))
        platform.start()
        self.addCleanup(platform.stop)
        self.engine = self.root / 'runtime'
        adb = self.engine / 'adb-assets' / 'platform-tools' / 'adb.exe'
        adb.parent.mkdir(parents=True)
        adb.write_bytes(b'fixture only; never execute')
        (self.engine / 'E7ADBShopRefresh.exe').write_bytes(b'fixture only; never execute')
        (self.engine / 'ADBconfig.ini').write_text('[Settings]\nbudget = 300\n', encoding='utf-8')
        self.data = self.root / 'user data'

    def test_main_migrates_before_gui_and_logs_the_event(self):
        gui = self.gui
        observed = []

        class FakeGui:
            def __init__(self):
                observed.append((gui.CONFIG_FILE, gui.HISTORY_FILE, list(gui.DATA_EVENTS)))

            def mainloop(self):
                pass

        with patch.dict(os.environ, {'E7_DATA_DIR': str(self.data)}), patch.object(gui, 'RefreshGui', FakeGui):
            self.assertEqual(gui.main(['--engine-dir', str(self.engine)]), 0)
            self.assertEqual(gui.engine_environment()['E7_DATA_DIR'], str(self.data))
        config, history, events = observed[0]
        self.assertEqual(config, self.data / 'ADBconfig.ini')
        self.assertEqual(history, self.data / 'ShopRefreshHistory' / 'ADB_History.csv')
        self.assertIn('budget = 300', config.read_text(encoding='utf-8'))
        self.assertTrue(any('moved to' in event for event in events))
        self.assertTrue((self.engine / 'ADBconfig.ini').exists())

    def test_verify_never_creates_user_data(self):
        with patch.dict(os.environ, {'E7_DATA_DIR': str(self.data)}):
            self.gui.main(['--engine-dir', str(self.engine), '--verify'])
        self.assertFalse(self.data.exists())

    def test_engine_environment_is_inherited_until_configured(self):
        self.gui.DATA_DIR = None
        self.assertIsNone(self.gui.engine_environment())


class EngineHistoryPathTests(unittest.TestCase):
    def test_engine_writes_under_data_folder_when_set(self):
        import E7ADBShopRefresh as engine
        with patch.dict(os.environ, {'E7_DATA_DIR': os.path.join('x', 'data')}):
            self.assertEqual(engine.data_path('ShopRefreshHistory', 'ADB_History.csv'),
                             os.path.join('x', 'data', 'ShopRefreshHistory', 'ADB_History.csv'))
        with patch.dict(os.environ, {'E7_DATA_DIR': ''}):
            self.assertEqual(engine.data_path('ADBconfig.ini'), 'ADBconfig.ini')


if __name__ == '__main__':
    unittest.main()
