"""The GUI's Background control mode (Steam under Proton), on the non-Windows mode list."""
import hashlib
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock
from unittest.mock import patch

if os.name != "nt" and "winsound" not in sys.modules:
    import e7_sound
    sys.modules["winsound"] = e7_sound

import e7_shop_refresh_gui as gui
from test_e7_shop_refresh_gui import FAKE, PACKAGED_ASSETS

def os_named(name):
    """Patch the GUI's os.name so a test takes one platform's branch on any host."""
    fake = mock.MagicMock(wraps=os); fake.name = name; fake.environ = os.environ
    return patch.object(gui, 'os', fake)


GAME = gui.BackgroundTarget('Epic Seven (Steam)', 'Epic Seven (Steam)', 0xa600005, 0, (0, 0, 3840, 2016))


class BackgroundGuiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = self.root = Path(self.temp.name)
        self.fake = root/'E7ADBShopRefresh.py'
        self.fake.write_text('import sys\nif sys.argv[1:] == ["--verify"]:\n    print("E7 engine: friendship purchases v1"); sys.exit(0)\n'+FAKE)
        (root/'adb-assets/builtin-navigation').mkdir(parents=True)
        assets = root/'assets'; assets.mkdir()
        for name in ('start.wav', 'end.wav', 'friendship-points-heart.png'):
            shutil.copyfile(PACKAGED_ASSETS/name, assets/name)
        self.patches = [patch.object(gui, 'APP_DIR', root), patch.object(gui, 'CONFIG_FILE', root/'ADBconfig.ini'),
                        patch.object(gui, 'GUI_CONFIG_FILE', root/'ShopRefreshGUI.ini'), patch.object(gui, 'ASSET_DIR', assets),
                        patch.object(gui, 'HISTORY_FILE', root/'history.csv'), patch.object(gui, 'ENGINE_EXE', self.fake),
                        patch.object(gui, 'CONTROL_MODES', ('Background',)), patch.object(gui, 'DEFAULT_CONTROL_MODE', 'Background'),
                        patch.object(gui, 'list_background_games', return_value=[GAME]),
                        patch.object(gui.RefreshGui, '_maybe_show_credits', lambda _: None),
                        patch('winsound.PlaySound'), patch.object(gui, 'release_native_button')]
        for p in self.patches:
            p.start()
        self.release = gui.release_native_button
        self.app = gui.RefreshGui()
        self.app.withdraw()

    def tearDown(self):
        self.app.destroy()
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def pump_until(self, predicate, timeout=8):
        deadline = time.monotonic()+timeout
        while time.monotonic() < deadline:
            self.app.update()
            if predicate():
                return
            time.sleep(.01)
        self.fail(f'Timed out: {self.app.status.get()} · {self.app.device_notice.get()}')

    def test_fresh_settings_use_background_and_find_the_steam_game(self):
        self.assertEqual(self.app.control_mode.get(), 'Background')
        self.assertEqual(tuple(self.app.mode_box.cget('values')), ('Background',))
        self.pump_until(lambda: self.app.mouse_target.get() == 'Epic Seven (Steam)')
        self.assertIn('never moves your pointer', self.app.device_notice.get())
        self.assertTrue(self.app.debug_check.instate(['disabled']))
        self.assertEqual(str(self.app.start_button.cget('state')), 'normal')

    def test_start_launches_the_background_engine_without_native_mouse(self):
        self.pump_until(lambda: self.app.mouse_target.get() == 'Epic Seven (Steam)')
        self.app.buy_friendship.set(True)
        (self.root/'e7_wine_input.exe').write_bytes(b'MZ')
        with os_named('posix'), patch.object(gui, 'launch_engine', side_effect=OSError('test: not launched')) as launch:
            self.app.start_button.invoke()
        arguments = launch.call_args.args[0]
        self.assertEqual(arguments[:2], [sys.executable, str(self.fake)])
        self.assertIn('--background-session', arguments)
        self.assertNotIn('--mouse-session', arguments)
        self.assertEqual(arguments[arguments.index('--stop-key')+1], '`')
        self.assertIn('--buy-friendship', arguments)
        self.assertFalse(self.app._native_mouse_run)
        self.assertTrue(self.app._graceful_stop)
        self.release.assert_not_called()

    def test_missing_helper_or_game_never_launches(self):
        self.pump_until(lambda: self.app.mouse_target.get() == 'Epic Seven (Steam)')
        with os_named('posix'), patch.object(gui, 'launch_engine') as launch:
            self.app.start_button.invoke()
        launch.assert_not_called()
        self.assertIn('helper is missing', self.app.connection_warning)
        self.app.mouse_target.set('')
        with patch.object(gui, 'launch_engine') as launch:
            self.app._start_background_refresh()
        launch.assert_not_called()
        self.assertIn('Steam', self.app.connection_warning)

    def windows(self, verify='background session v1'):
        """Run _start_background_refresh down its Windows branch."""
        self.fake.write_text(f'import sys\nif sys.argv[1:] == ["--verify"]:\n    print("E7 engine: {verify}"); sys.exit(0)\n'+FAKE)
        (self.root/'e7_wine_input.exe').write_bytes(b'MZ')
        return os_named('nt')

    def test_windows_elevated_game_offers_the_administrator_restart(self):
        from e7_native_mouse import MouseElevationRequired
        self.pump_until(lambda: self.app.mouse_target.get() == 'Epic Seven (Steam)')
        with self.windows(), patch.object(gui, 'NO_WINDOW', 0), \
                patch('e7_background.require_background_permissions',
                      side_effect=MouseElevationRequired('Restart as administrator. No background input sent.')) as check, \
                patch.object(self.app, '_offer_administrator_restart') as offer, \
                patch.object(gui, 'launch_engine') as launch:
            self.app._start_background_refresh()
        check.assert_called_once_with(GAME.pid)
        offer.assert_called_once()
        self.assertIn('administrator', offer.call_args.kwargs['reason'])
        launch.assert_not_called()

    def test_windows_old_engine_is_refused_before_any_check(self):
        self.pump_until(lambda: self.app.mouse_target.get() == 'Epic Seven (Steam)')
        with self.windows(verify='friendship purchases v1'), patch.object(gui, 'NO_WINDOW', 0), \
                patch('e7_background.require_background_permissions') as check, \
                patch.object(gui, 'launch_engine') as launch:
            self.app._start_background_refresh()
        check.assert_not_called()
        launch.assert_not_called()
        self.assertIn('matching new engine', self.app.connection_warning)

    def test_scan_recovers_when_the_game_window_vanishes(self):
        class BadWindow(Exception):  # stands in for Xlib.error.BadWindow
            pass
        self.app._mouse_scan_busy = False
        with patch.object(gui, 'list_background_games', side_effect=BadWindow('gone')):
            self.app._scan_game_windows()
            self.pump_until(lambda: not self.app._mouse_scan_busy)
        with patch.object(gui, 'list_background_games', return_value=[GAME]) as scan:
            self.app._scan_game_windows()
            self.pump_until(lambda: not self.app._mouse_scan_busy)
        scan.assert_called_once()


class ListBackgroundGamesTest(unittest.TestCase):
    def test_windows_reports_the_steam_window(self):
        window = mock.Mock(hwnd=0x5012e, pid=777); window.size.return_value = (3840, 2019)
        with os_named('nt'), patch('e7_background.WinGameWindow', return_value=window):
            games = gui.list_background_games()
        self.assertEqual(games, [gui.BackgroundTarget('Epic Seven (Steam)', 'Epic Seven (Steam)', 0x5012e, 777, (0, 0, 3840, 2019))])


    def test_reports_the_game_window_read_only(self):
        window = mock.Mock(); window.size.return_value = (3840, 2016); window.window.id = 42
        with os_named('posix'), patch('e7_background.find_proton_session'), patch('e7_background.XGameWindow', return_value=window):
            games = gui.list_background_games()
        self.assertEqual(games, [gui.BackgroundTarget('Epic Seven (Steam)', 'Epic Seven (Steam)', 42, 0, (0, 0, 3840, 2016))])
        window.display.close.assert_called_once()

    def test_game_not_running_is_an_error_for_the_scan(self):
        with os_named('posix'), patch('e7_background.find_proton_session', side_effect=ValueError('Epic Seven (Steam) is not running.')):
            with self.assertRaisesRegex(ValueError, 'not running'):
                gui.list_background_games()


if __name__ == '__main__':
    unittest.main()
