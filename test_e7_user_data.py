"""Per-user settings/history folder and the one-time move from `runtime`.

Temporary folders only: never the installed app, its runtime data, the engine or the game.
"""
import datetime
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from types import SimpleNamespace
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
                         Path('/custom').absolute())

    def test_relative_override_becomes_absolute(self):
        folder = data.default_data_directory({'E7_DATA_DIR': 'relative data'}, 'nt')
        self.assertEqual(folder, Path.cwd() / 'relative data')


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

    def leftover_staging(self):
        parent = self.data.parent
        return [path for path in parent.iterdir() if '.migrating-' in path.name] if parent.exists() else []

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
        self.assertTrue(any('backup is in' in event for event in location.events))
        self.assertEqual(self.leftover_staging(), [])

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

    def test_folder_already_in_use_is_never_overwritten_or_merged(self):
        before = self.old_install()
        self.data.mkdir(parents=True)
        (self.data / 'ShopRefreshGUI.ini').write_bytes(b'[GUI]\nnewer = yes\n')
        location = self.prepare()
        self.assertFalse(location.migrated or location.fallback)
        self.assertEqual(location.directory, self.data)
        self.assertEqual(snapshot(self.data)['ShopRefreshGUI.ini'], b'[GUI]\nnewer = yes\n')
        self.assertEqual(sorted(snapshot(self.data)), ['ShopRefreshGUI.ini', MARKER])
        self.assertIn('were not imported', location.events[0])
        self.assertEqual(snapshot(self.legacy), before)
        self.assertEqual(self.prepare().events, [])  # told once, not on every start

    def test_empty_override_variable_uses_the_default(self):
        with patch.dict(os.environ, {'E7_EMPTY_FOR_TEST': ''}):
            folder = data.default_data_directory({'E7_DATA_DIR': '$E7_EMPTY_FOR_TEST', 'LOCALAPPDATA': str(self.root)}, 'nt')
        self.assertEqual(folder, self.root / 'E7 Secret Shop Refresh')

    def test_missing_home_falls_back_without_raising(self):
        self.old_install()
        with patch.object(data, 'default_data_directory', side_effect=RuntimeError('Could not determine home directory')):
            location = prepare_data_directory(self.legacy, now=NOW)
        self.assertEqual(location.directory, self.legacy)
        self.assertTrue(location.fallback)

    def test_read_only_legacy_files_leave_no_staging_behind(self):
        self.old_install()
        os.chmod(self.legacy / 'ADBconfig.ini', 0o444)
        self.addCleanup(os.chmod, self.legacy / 'ADBconfig.ini', 0o666)
        real_write = Path.write_text

        def failing_write(path, *args, **kwargs):
            if path.name == MARKER:
                raise OSError(28, 'No space left on device')
            return real_write(path, *args, **kwargs)

        with patch.object(Path, 'write_text', failing_write):
            self.assertTrue(self.prepare().fallback)
        self.assertEqual(self.leftover_staging(), [])

    def test_empty_folder_from_a_fresh_start_still_migrates(self):
        self.prepare()  # a fresh start creates the empty folder
        self.old_install()
        location = self.prepare()
        self.assertTrue(location.migrated)
        self.assertIn('budget = 300', (self.data / 'ADBconfig.ini').read_text(encoding='utf-8'))

    def test_destination_that_cannot_be_created_falls_back_to_runtime(self):
        before = self.old_install()
        (self.root / 'LocalAppData').write_text('a file where the folder should be', encoding='utf-8')
        location = self.prepare()
        self.assertEqual(location.directory, self.legacy)
        self.assertTrue(location.fallback)
        self.assertIn('failed', location.events[0])
        self.assertIn('nothing was deleted', location.events[0])
        self.assertEqual(snapshot(self.legacy), before)

    def test_fresh_destination_that_cannot_be_created_falls_back(self):
        (self.root / 'LocalAppData').write_text('a file where the folder should be', encoding='utf-8')
        location = self.prepare()
        self.assertTrue(location.fallback)
        self.assertIn('Could not create', location.events[0])

    def test_read_only_destination_falls_back_without_touching_runtime(self):
        before = self.old_install()
        real_mkdir = Path.mkdir

        def denied(path, *args, **kwargs):
            if '.migrating-' in path.name:
                raise PermissionError(13, 'Access is denied', str(path))
            return real_mkdir(path, *args, **kwargs)

        with patch.object(Path, 'mkdir', denied):
            location = self.prepare()
        self.assertEqual(location.directory, self.legacy)
        self.assertTrue(location.fallback)
        self.assertIn('Access is denied', location.events[0])
        self.assertEqual(snapshot(self.legacy), before)
        self.assertFalse(self.data.exists())

    def test_read_only_fresh_destination_falls_back(self):
        with patch.object(data, '_writable', return_value=False):
            location = self.prepare()
        self.assertEqual(location.directory, self.legacy)
        self.assertTrue(location.fallback)
        self.assertIn('read-only', location.events[0])

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

        def failing_copytree(source, target, *args, **kwargs):
            if BACKUP_FOLDER in str(target):
                raise OSError(28, 'No space left on device')
            return real_copytree(source, target, *args, **kwargs)

        with patch.object(data.shutil, 'copytree', failing_copytree):
            location = self.prepare()
        self.assertEqual(location.directory, self.legacy)
        self.assertTrue(location.fallback)
        self.assertIn('migration', location.events[0])
        self.assertEqual(snapshot(self.legacy), before)
        self.assertFalse(self.data.exists())
        self.assertEqual(self.leftover_staging(), [])
        # The next start completes the move from the untouched runtime folder.
        location = self.prepare()
        self.assertEqual(location.directory, self.data)
        self.assertTrue(location.migrated)
        self.assertEqual((self.data / 'ShopRefreshHistory' / 'ADB_History.csv').read_bytes(),
                         before[str(Path('ShopRefreshHistory') / 'ADB_History.csv')])

    def test_marker_write_failure_leaves_no_half_moved_folder(self):
        before = self.old_install()
        real_write = Path.write_text

        def failing_write(path, *args, **kwargs):
            if path.name == MARKER:
                raise OSError(28, 'No space left on device')
            return real_write(path, *args, **kwargs)

        with patch.object(Path, 'write_text', failing_write):
            location = self.prepare()
        self.assertTrue(location.fallback)
        self.assertEqual(location.directory, self.legacy)
        # Saves this run go to runtime; no stale copy waits in the new folder for later.
        self.assertFalse(self.data.exists())
        self.assertEqual(self.leftover_staging(), [])
        self.assertEqual(snapshot(self.legacy), before)

    def test_losing_a_race_to_another_instance_uses_its_result(self):
        self.old_install()
        real_rename = os.rename

        def other_instance_wins(source, target):
            with patch.object(data.os, 'rename', real_rename):
                other = prepare_data_directory(self.legacy, self.data, now=NOW)
            self.assertTrue(other.migrated)
            return real_rename(source, target)

        with patch.object(data.os, 'rename', other_instance_wins):
            location = self.prepare()
        self.assertEqual(location.directory, self.data)
        self.assertFalse(location.fallback)
        self.assertEqual(self.leftover_staging(), [])
        self.assertEqual(len(list((self.data / BACKUP_FOLDER).iterdir())), 1)

    def test_mismatched_copy_is_rejected(self):
        before = self.old_install()
        real_copy2 = shutil.copy2

        def corrupting_copy(source, target, *args, **kwargs):
            result = real_copy2(source, target, *args, **kwargs)
            if BACKUP_FOLDER not in str(target):
                Path(target).write_bytes(b'corrupt')
            return result

        with patch.object(data.shutil, 'copy2', corrupting_copy):
            location = self.prepare()
        self.assertTrue(location.fallback)
        self.assertEqual(location.directory, self.legacy)
        self.assertFalse(self.data.exists())
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


def older_install(folder, items=data.MIGRATED_ITEMS, *, budget=300, mtime=None):
    """A fake older release folder: <folder>/runtime with the given user files."""
    runtime = Path(folder) / 'runtime'
    runtime.mkdir(parents=True)
    (runtime / 'E7ADBShopRefresh.exe').write_bytes(b'fixture only; never execute')
    if 'ADBconfig.ini' in items:
        (runtime / 'ADBconfig.ini').write_text(f'[Settings]\nbudget = {budget}\n', encoding='utf-8')
    if 'ShopRefreshGUI.ini' in items:
        (runtime / 'ShopRefreshGUI.ini').write_text('[GUI]\ncontrol_mode = Mouse\n', encoding='utf-8')
    if 'ShopRefreshHistory' in items:
        (runtime / 'ShopRefreshHistory').mkdir()
        (runtime / 'ShopRefreshHistory' / 'ADB_History.csv').write_text('Duration\n12\n', encoding='utf-8')
    if mtime is not None:
        for path in [runtime, *runtime.rglob('*')]:
            os.utime(path, (mtime, mtime))
    return runtime


class SearchTests(unittest.TestCase):
    """Bounded search for older versions; temporary trees stand in for Desktop and Downloads."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='e7 search 日本語 ')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.releases = self.root / 'Games'
        self.app = self.releases / 'E7 Secret Shop Refresh 0.2.8'
        self.own_runtime = self.app / 'runtime'
        self.own_runtime.mkdir(parents=True)
        self.desktop = self.root / 'Desktop'
        self.downloads = self.root / 'Downloads'
        self.desktop.mkdir()
        self.downloads.mkdir()
        self.data = self.root / 'LocalAppData' / 'E7 Secret Shop Refresh'

    def roots(self):
        return [(self.releases, 1), (self.desktop, 2), (self.downloads, 2)]

    def find(self):
        return data.find_older_installs(self.roots(), exclude=(self.own_runtime, self.data))

    def test_none_found(self):
        (self.desktop / 'photos' / 'runtime').mkdir(parents=True)  # a runtime without settings is not an install
        self.assertEqual(self.find(), [])

    def test_one_sibling_found(self):
        older_install(self.releases / 'E7 Secret Shop Refresh 0.2.7')
        found = self.find()
        self.assertEqual([install.name for install in found], ['E7 Secret Shop Refresh 0.2.7'])
        self.assertEqual(found[0].location, self.releases)
        self.assertEqual(found[0].runtime, self.releases / 'E7 Secret Shop Refresh 0.2.7' / 'runtime')
        self.assertEqual(sorted(found[0].items), sorted(data.MIGRATED_ITEMS))

    def test_own_runtime_and_settings_folder_are_not_offered(self):
        (self.own_runtime / 'ShopRefreshGUI.ini').write_text('[GUI]\n', encoding='utf-8')
        self.assertEqual(self.find(), [])

    def test_several_found_newest_history_first(self):
        older_install(self.releases / 'old 0.2.5', mtime=1_700_000_000)
        older_install(self.desktop / 'E7 0.2.7', mtime=1_760_000_000)
        older_install(self.downloads / 'extracted' / 'E7 0.2.6', mtime=1_730_000_000)
        self.assertEqual([install.name for install in self.find()], ['E7 0.2.7', 'E7 0.2.6', 'old 0.2.5'])

    def test_depth_is_bounded(self):
        older_install(self.downloads / 'a' / 'b' / 'too deep')
        older_install(self.releases / 'nested' / 'not a sibling')
        self.assertEqual(self.find(), [])

    def test_partial_runtime_needs_the_gui_settings(self):
        older_install(self.desktop / 'only engine settings', items=('ADBconfig.ini',))
        older_install(self.desktop / 'gui settings only', items=('ShopRefreshGUI.ini',))
        found = self.find()
        self.assertEqual([install.name for install in found], ['gui settings only'])
        self.assertEqual(found[0].items, ('ShopRefreshGUI.ini',))

    def test_chosen_folder_accepts_runtime_or_partial_set(self):
        runtime = older_install(self.desktop / 'only engine settings', items=('ADBconfig.ini',))
        self.assertIsNone(data.describe_install(runtime.parent))
        chosen = data.describe_install(runtime.parent, require_gui_settings=False)
        self.assertEqual((chosen.runtime, chosen.items), (runtime, ('ADBconfig.ini',)))
        self.assertEqual(data.describe_install(runtime, require_gui_settings=False).folder, runtime.parent)
        self.assertIsNone(data.describe_install(self.desktop, require_gui_settings=False))

    def test_unreadable_folders_are_skipped_quietly(self):
        older_install(self.desktop / 'E7 0.2.7')
        real_scandir = os.scandir

        def denied(path):
            if Path(path) == self.downloads:
                raise PermissionError(13, 'Access is denied', str(path))
            return real_scandir(path)

        with patch.object(data.os, 'scandir', denied):
            found = self.find()
        self.assertEqual([install.name for install in found], ['E7 0.2.7'])
        missing = [(self.root / 'no such folder', 2)]
        self.assertEqual(data.find_older_installs(missing), [])

    def test_symlinks_and_loops_are_not_followed(self):
        older_install(self.root / 'elsewhere' / 'E7 linked')
        try:
            os.symlink(self.root / 'elsewhere', self.desktop / 'link', target_is_directory=True)
            os.symlink(self.desktop, self.desktop / 'loop', target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f'symlinks unavailable: {error}')
        self.assertEqual(self.find(), [])

    @unittest.skipUnless(os.name == 'nt', 'junctions are Windows-only')
    def test_junctions_and_junction_loops_are_not_followed(self):
        import subprocess
        older_install(self.root / 'elsewhere' / 'E7 linked')
        links = [(self.desktop / 'junction', self.root / 'elsewhere'), (self.desktop / 'loop', self.desktop)]
        for link, target in links:
            result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(target)], capture_output=True)
            if result.returncode:
                self.skipTest('mklink /J failed')
            self.addCleanup(os.rmdir, link)  # removes the junction only, never its target
        self.assertTrue((self.desktop / 'junction' / 'E7 linked' / 'runtime').exists())
        self.assertEqual(self.find(), [])

    def test_search_limit_keeps_it_bounded(self):
        for index in range(12):
            (self.desktop / f'folder {index:02}').mkdir()
        older_install(self.desktop / 'folder 00' / 'E7 0.2.7')  # one level down: never reached
        with patch.object(data, 'SEARCH_LIMIT', 5):
            self.assertEqual(self.find(), [])
        self.assertEqual(len(self.find()), 1)

    def test_search_limit_stops_the_whole_root(self):
        for index in range(12):
            (self.desktop / f'folder {index:02}' / 'inner').mkdir(parents=True)
        scanned = []
        real_scandir = os.scandir

        def counting(folder):
            scanned.append(Path(folder))
            return real_scandir(folder)

        with patch.object(data, 'SEARCH_LIMIT', 5), patch.object(data.os, 'scandir', counting):
            data.find_older_installs([(self.desktop, 2)])
        self.assertEqual(scanned, [self.desktop])  # budget spent on the first level: no deeper listing

    def test_cloud_placeholder_folders_are_searched_but_links_are_not(self):
        older_install(self.desktop / 'E7 0.2.7')
        real_lstat = os.lstat

        def tagged(tag):
            def fake(path, *args, **kwargs):
                info = real_lstat(path, *args, **kwargs)
                if Path(path).name == 'E7 0.2.7':
                    return SimpleNamespace(st_file_attributes=data.FILE_ATTRIBUTE_REPARSE_POINT | 0x10,
                                           st_reparse_tag=tag, st_mode=info.st_mode)
                return info
            return fake

        with patch.object(data.os, 'lstat', tagged(0x9000601A)):  # OneDrive Files On-Demand
            self.assertEqual([install.name for install in self.find()], ['E7 0.2.7'])
        with patch.object(data.os, 'lstat', tagged(0xA0000003)):  # a junction
            self.assertEqual(self.find(), [])

    def test_linked_runtime_inside_a_folder_is_not_followed(self):
        import subprocess
        if os.name != 'nt':
            self.skipTest('junctions are Windows-only')
        target = older_install(self.root / 'elsewhere' / 'E7 hidden')
        link = self.desktop / 'E7 decoy' / 'runtime'
        link.parent.mkdir()
        result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(target)], capture_output=True)
        if result.returncode:
            self.skipTest('mklink /J failed')
        self.addCleanup(os.rmdir, link)
        self.assertEqual(self.find(), [])

    def test_default_roots_use_known_folders(self):
        known = {'Desktop': self.desktop, 'Downloads': self.downloads}
        roots = data.default_search_roots(self.app, os_name='nt', known_folder=known.__getitem__)
        self.assertEqual(roots, [(self.releases, 1), (self.desktop, 2), (self.downloads, 2)])
        roots = data.default_search_roots(self.app, os_name='posix', home=self.root)
        self.assertEqual(roots, [(self.releases, 1), (self.desktop, 2), (self.downloads, 2)])

        def broken(_name):
            raise OSError('no known folder')
        roots = data.default_search_roots(self.app, os_name='nt', home=self.root, known_folder=broken)
        self.assertEqual(roots[1:], [(self.desktop, 2), (self.downloads, 2)])

    def test_default_roots_drop_duplicates_keeping_the_deeper_search(self):
        app = self.desktop / 'E7 0.2.8'  # extracted straight onto the Desktop
        known = {'Desktop': self.desktop, 'Downloads': self.desktop}
        self.assertEqual(data.default_search_roots(app, os_name='nt', known_folder=known.__getitem__),
                         [(self.desktop, 2)])

    def test_dialog_text_for_none_one_and_several(self):
        from e7_import_dialog import describe
        self.assertIn('No settings from an older version were found', describe([])[0])
        older_install(self.releases / 'E7 0.2.7')
        self.assertEqual(describe(self.find())[0],
                         f'Found settings and history from E7 0.2.7 ({self.releases}). Import them?')
        older_install(self.desktop / 'E7 0.2.6')
        self.assertIn('from 2 older versions', describe(self.find())[0])

    def test_dialog_text_survives_impossible_times(self):
        from e7_import_dialog import describe, _shorten
        for when in (-1e12, 1e15, float('nan')):
            install = data.OlderInstall(self.desktop / 'E7', self.desktop / 'E7' / 'runtime', (), when)
            self.assertIn('date unknown', describe([install])[1])
        self.assertEqual(len(_shorten('x' * 400)), 110)


class ImportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='e7 import 日本語 ')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.old = older_install(self.root / 'Desktop' / 'E7 0.2.7', budget=450)
        self.data = self.root / 'LocalAppData' / 'E7 Secret Shop Refresh'
        self.legacy = self.root / 'E7 0.2.8' / 'runtime'  # the new extract: nothing to move
        self.legacy.mkdir(parents=True)

    def fresh_start(self):
        location = prepare_data_directory(self.legacy, self.data, now=NOW)
        self.assertTrue(location.fresh)
        self.assertTrue(data.needs_import_choice(location))
        return location

    def leftovers(self):
        return [path.name for path in self.data.parent.iterdir() if path.name.startswith('.')]

    def test_import_into_fresh_folder_copies_with_backup_and_leaves_source(self):
        self.fresh_start()
        before = snapshot(self.old)
        events = data.import_older_install(self.old, self.data, now=NOW)
        self.assertEqual(snapshot(self.old), before)
        self.assertIn('budget = 450', (self.data / 'ADBconfig.ini').read_text(encoding='utf-8'))
        self.assertEqual((self.data / 'ShopRefreshHistory' / 'ADB_History.csv').read_bytes(),
                         before[str(Path('ShopRefreshHistory') / 'ADB_History.csv')])
        backup = self.data / BACKUP_FOLDER / 'runtime-20261125-120000'
        self.assertIn('budget = 450', (backup / 'ADBconfig.ini').read_text(encoding='utf-8'))
        marker = json.loads((self.data / MARKER).read_text(encoding='utf-8'))
        self.assertTrue(marker['imported'])
        self.assertEqual(Path(marker['source']), self.old)
        self.assertIn('Imported settings and history', events[0])
        self.assertEqual(self.leftovers(), [])
        # Imported is final: the next start neither asks nor moves anything.
        location = prepare_data_directory(self.legacy, self.data, now=NOW)
        self.assertFalse(location.fresh or location.migrated or data.needs_import_choice(location))

    def test_import_when_the_folder_does_not_exist_yet(self):
        data.import_older_install(self.old, self.data, now=NOW)
        self.assertIn('budget = 450', (self.data / 'ADBconfig.ini').read_text(encoding='utf-8'))

    def test_partial_runtime_imports_what_is_there(self):
        partial = older_install(self.root / 'partial', items=('ShopRefreshGUI.ini',))
        self.fresh_start()
        data.import_older_install(partial, self.data, now=NOW)
        self.assertEqual(data._user_files(self.data), sorted([BACKUP_FOLDER, 'ShopRefreshGUI.ini']))

    def test_start_fresh_is_recorded_and_not_asked_again(self):
        self.fresh_start()
        data.record_fresh_start(self.data, now=NOW)
        for _ in range(2):
            location = prepare_data_directory(self.legacy, self.data, now=NOW)
            self.assertFalse(data.needs_import_choice(location))
            self.assertEqual(location.events, [])
        self.assertFalse(data.has_user_data(self.data))
        # The import stays possible later, from Settings.
        data.import_older_install(self.old, self.data, now=NOW)
        self.assertIn('budget = 450', (self.data / 'ADBconfig.ini').read_text(encoding='utf-8'))

    def test_closing_the_dialog_asks_again(self):
        self.fresh_start()
        self.assertTrue(data.needs_import_choice(prepare_data_directory(self.legacy, self.data, now=NOW)))

    def test_folder_with_settings_is_refused_without_replace(self):
        self.fresh_start()
        (self.data / 'ShopRefreshGUI.ini').write_text('[GUI]\nnewer = yes\n', encoding='utf-8')
        before = snapshot(self.data)
        with self.assertRaises(data.ImportRefused):
            data.import_older_install(self.old, self.data, now=NOW)
        self.assertEqual(snapshot(self.data), before)
        self.assertEqual(self.leftovers(), [])
        self.assertFalse(data.needs_import_choice(prepare_data_directory(self.legacy, self.data, now=NOW)))

    def test_replace_keeps_the_current_settings_in_a_backup(self):
        self.fresh_start()
        (self.data / 'ShopRefreshGUI.ini').write_text('[GUI]\nnewer = yes\n', encoding='utf-8')
        events = data.import_older_install(self.old, self.data, replace=True, now=NOW)
        self.assertIn('budget = 450', (self.data / 'ADBconfig.ini').read_text(encoding='utf-8'))
        replaced = self.data / BACKUP_FOLDER / 'replaced-20261125-120000' / 'ShopRefreshGUI.ini'
        self.assertEqual(replaced.read_text(encoding='utf-8'), '[GUI]\nnewer = yes\n')
        self.assertTrue(any('replaced are in' in event for event in events))
        self.assertEqual(self.leftovers(), [])

    def test_repeated_replace_keeps_backups_flat(self):
        self.fresh_start()
        (self.data / 'ShopRefreshGUI.ini').write_text('[GUI]\nfirst = yes\n', encoding='utf-8')
        data.import_older_install(self.old, self.data, replace=True, now=NOW)
        later = NOW + datetime.timedelta(minutes=5)
        data.import_older_install(self.old, self.data, replace=True, now=later)
        backups = sorted(path.name for path in (self.data / BACKUP_FOLDER).iterdir())
        self.assertEqual(backups, ['replaced-20261125-120000', 'replaced-20261125-120500',
                                   'runtime-20261125-120000', 'runtime-20261125-120500'])
        self.assertFalse((self.data / BACKUP_FOLDER / 'replaced-20261125-120500' / BACKUP_FOLDER).exists())
        self.assertEqual((self.data / BACKUP_FOLDER / 'replaced-20261125-120000' / 'ShopRefreshGUI.ini')
                         .read_text(encoding='utf-8'), '[GUI]\nfirst = yes\n')

    def test_source_and_settings_folder_inside_one_another_are_refused(self):
        self.fresh_start()
        (self.data / 'ShopRefreshGUI.ini').write_text('[GUI]\n', encoding='utf-8')
        data.import_older_install(self.old, self.data, replace=True, now=NOW)
        backup = self.data / BACKUP_FOLDER / 'runtime-20261125-120000'
        before = snapshot(self.data)
        with self.assertRaises(data.ImportRefused):
            data.import_older_install(backup, self.data, replace=True, now=NOW)
        self.assertEqual(snapshot(self.data), before)
        inside = self.old / 'ShopRefreshHistory' / 'nested settings'
        old_before = snapshot(self.old)
        with self.assertRaises(data.ImportRefused):
            data.import_older_install(self.old, inside, replace=True, now=NOW)
        self.assertEqual(snapshot(self.old), old_before)

    def test_failed_rollback_names_where_the_settings_are(self):
        self.fresh_start()
        (self.data / 'ShopRefreshGUI.ini').write_text('[GUI]\nmine\n', encoding='utf-8')
        real_rename = os.rename

        def failing(source, target):
            if '.migrating-' in Path(source).name or '.replaced-' in Path(source).name:
                raise PermissionError(13, 'Access is denied', str(source))
            return real_rename(source, target)

        with patch.object(data.os, 'rename', failing), self.assertRaises(OSError) as raised:
            data.import_older_install(self.old, self.data, replace=True, now=NOW)
        aside = [path for path in self.data.parent.iterdir() if '.replaced-' in path.name]
        self.assertEqual(len(aside), 1)
        self.assertIn(str(aside[0]), str(raised.exception))
        self.assertEqual((aside[0] / 'ShopRefreshGUI.ini').read_text(encoding='utf-8'), '[GUI]\nmine\n')

    def test_cleanup_failure_after_the_swap_does_not_fail_the_import(self):
        self.fresh_start()
        (self.data / 'ShopRefreshGUI.ini').write_text('[GUI]\n', encoding='utf-8')
        real_remove = data._remove_tree

        def failing(folder):
            if '.replaced-' in Path(folder).name:
                raise OSError(32, 'in use')
            return real_remove(folder)

        with patch.object(data, '_remove_tree', failing):
            events = data.import_older_install(self.old, self.data, replace=True, now=NOW)
        self.assertIn('Imported', events[0])
        self.assertIn('budget = 450', (self.data / 'ADBconfig.ini').read_text(encoding='utf-8'))

    def test_edit_inside_an_existing_file_during_import_is_noticed(self):
        self.fresh_start()
        history = self.data / 'ShopRefreshHistory'
        history.mkdir()
        (history / 'ADB_History.csv').write_text('Duration\n1\n', encoding='utf-8')
        real_stage = data._stage

        def append_meanwhile(*args, **kwargs):
            result = real_stage(*args, **kwargs)
            with open(history / 'ADB_History.csv', 'a', encoding='utf-8') as file:
                file.write('2\n')
            return result

        with patch.object(data, '_stage', append_meanwhile), self.assertRaises(data.ImportRefused):
            data.import_older_install(self.old, self.data, replace=True, now=NOW)
        self.assertEqual((history / 'ADB_History.csv').read_text(encoding='utf-8'), 'Duration\n1\n2\n')
        self.assertEqual(self.leftovers(), [])

    def test_copy_failure_leaves_the_folder_as_it_was(self):
        self.fresh_start()
        data.record_fresh_start(self.data, now=NOW)
        before = snapshot(self.data)
        real_copytree = shutil.copytree

        def failing(source, target, *args, **kwargs):
            if BACKUP_FOLDER in str(target):
                raise OSError(28, 'No space left on device')
            return real_copytree(source, target, *args, **kwargs)

        with patch.object(data.shutil, 'copytree', failing), self.assertRaises(OSError):
            data.import_older_install(self.old, self.data, now=NOW)
        self.assertEqual(snapshot(self.data), before)
        self.assertEqual(self.leftovers(), [])

    def test_failed_swap_puts_the_old_folder_back(self):
        self.fresh_start()
        data.record_fresh_start(self.data, now=NOW)
        before = snapshot(self.data)
        real_rename = os.rename

        def failing(source, target):
            if '.migrating-' in Path(source).name:
                raise PermissionError(13, 'Access is denied', str(source))
            return real_rename(source, target)

        with patch.object(data.os, 'rename', failing), self.assertRaises(OSError):
            data.import_older_install(self.old, self.data, now=NOW)
        self.assertEqual(snapshot(self.data), before)
        self.assertEqual(self.leftovers(), [])

    def test_change_during_import_keeps_it_and_imports_nothing(self):
        self.fresh_start()
        real_stage = data._stage

        def save_meanwhile(*args, **kwargs):
            result = real_stage(*args, **kwargs)
            (self.data / 'ShopRefreshGUI.ini').write_text('[GUI]\nsaved meanwhile\n', encoding='utf-8')
            return result

        with patch.object(data, '_stage', save_meanwhile), self.assertRaises(data.ImportRefused):
            data.import_older_install(self.old, self.data, now=NOW)
        self.assertEqual((self.data / 'ShopRefreshGUI.ini').read_text(encoding='utf-8'), '[GUI]\nsaved meanwhile\n')
        self.assertFalse((self.data / 'ADBconfig.ini').exists())
        self.assertEqual(self.leftovers(), [])

    def test_empty_or_same_source_is_refused(self):
        with self.assertRaises(data.ImportRefused):
            data.import_older_install(self.legacy, self.data, now=NOW)
        with self.assertRaises(data.ImportRefused):
            data.import_older_install(self.old, self.old, now=NOW)

    def test_migrated_or_fallback_locations_never_ask(self):
        self.assertFalse(data.needs_import_choice(data.DataLocation(self.legacy, fallback=True, fresh=True)))
        older = older_install(self.root / 'E7 0.2.7 in place')
        location = prepare_data_directory(older, self.data, now=NOW)
        self.assertTrue(location.migrated)
        self.assertFalse(data.needs_import_choice(location))


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
        # No dialog and no search of the real Desktop/Downloads from these tests.
        self.real_offer = gui.offer_older_settings
        offer = patch.object(gui, 'offer_older_settings', return_value=[])
        self.offer = offer.start()
        self.addCleanup(offer.stop)

    def run_main(self, observed=None):
        gui = self.gui

        class FakeGui:
            def __init__(self):
                if observed is not None:
                    observed.append(list(gui.DATA_EVENTS))

            def mainloop(self):
                pass

        with patch.dict(os.environ, {'E7_DATA_DIR': str(self.data)}), patch.object(gui, 'RefreshGui', FakeGui):
            self.assertEqual(gui.main(['--engine-dir', str(self.engine)]), 0)

    def test_fresh_start_offers_older_settings_and_logs_the_result(self):
        (self.engine / 'ADBconfig.ini').unlink()  # a fresh extract: nothing in its own runtime
        self.offer.return_value = ['Imported settings and history from somewhere.']
        observed = []
        self.run_main(observed)
        self.offer.assert_called_once_with(self.data)
        self.assertEqual(observed, [['Imported settings and history from somewhere.']])

    def test_migration_from_own_runtime_does_not_ask(self):
        self.run_main()
        self.offer.assert_not_called()

    def test_apply_choice_start_fresh_is_remembered(self):
        self.data.mkdir()
        events = self.gui.apply_import_choice(('fresh', None), self.data)
        self.assertIn('Import settings from an older version', events[0])
        self.assertFalse(data.needs_import_choice(data.DataLocation(self.data, fresh=True)))

    def test_apply_choice_closed_changes_nothing(self):
        self.data.mkdir()
        self.assertEqual(self.gui.apply_import_choice(None, self.data), [])
        self.assertEqual(list(self.data.iterdir()), [])

    def test_apply_choice_import_failure_is_logged_not_raised(self):
        self.data.mkdir()
        install = data.OlderInstall(self.root / 'empty', self.root / 'empty' / 'runtime', (), 0.0)
        events = self.gui.apply_import_choice(('import', install), self.data)
        self.assertIn('failed', events[0])
        self.assertIn('was not changed', events[0])

    def test_closing_the_startup_question_counts_as_start_fresh(self):
        import e7_import_dialog
        self.data.mkdir()

        class Closed:
            def __init__(self, *args, **kwargs):
                self.choice = None

        with patch.object(self.gui.tk, 'Tk'), patch.object(self.gui, 'enable_dpi_awareness'), \
                patch.object(self.gui, 'older_installs', return_value=[]), \
                patch.object(e7_import_dialog, 'ImportDialog', Closed):
            events = self.real_offer(self.data)
        self.assertIn('Import settings from an older version', events[0])
        self.assertTrue((self.data / MARKER).exists())

    def test_no_display_searches_nothing_and_asks_next_start(self):
        with patch.object(self.gui.tk, 'Tk', side_effect=self.gui.tk.TclError('no display')), \
                patch.object(self.gui, 'enable_dpi_awareness'), \
                patch.object(self.gui, 'older_installs') as search:
            self.assertEqual(self.real_offer(self.data), [])
        search.assert_not_called()

    def test_apply_choice_import_copies(self):
        older = self.root / 'E7 0.2.7' / 'runtime'
        older.mkdir(parents=True)
        (older / 'ShopRefreshGUI.ini').write_text('[GUI]\n', encoding='utf-8')
        install = data.describe_install(older.parent)
        events = self.gui.apply_import_choice(('import', install), self.data)
        self.assertIn('Imported', events[0])
        self.assertTrue((self.data / 'ShopRefreshGUI.ini').exists())

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


    def begin_with_engine(self, verify_output):
        gui = self.gui
        fake = self.root / 'fake_engine.py'
        fake.write_text(f'print({verify_output!r})\n', encoding='utf-8')
        warnings = []
        window = type('FakeWindow', (), {'_set_connection_warning': lambda _, text, reveal=False: warnings.append(text),
                                         'save_settings': lambda _, settings: None})()
        settings = type('Settings', (), dict(buy_covenant=True, buy_mystic=True, buy_friendship=False, debug=False))()
        with patch.object(gui, 'engine_command', lambda: [sys.executable, str(fake)]), \
                patch.multiple(gui, DATA_DIR=self.data, APP_DIR=self.engine):
            gui.RefreshGui._begin_refresh(window, settings)
        return warnings

    def test_older_engine_is_refused_when_data_moved(self):
        warnings = self.begin_with_engine('E7 engine: gui session v1; background session v1; imports OK')
        self.assertEqual(len(warnings), 1)
        self.assertIn('older than the GUI', warnings[0])

    def test_matching_engine_is_accepted(self):
        self.assertEqual(self.begin_with_engine('E7 engine: background session v1; user data folder v1; imports OK'), [])

    def test_shipped_engine_advertises_the_data_folder(self):
        text = (Path(__file__).parent / 'E7ADBShopRefresh.py').read_text(encoding='utf-8')
        self.assertIn('user data folder v1', text)


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
