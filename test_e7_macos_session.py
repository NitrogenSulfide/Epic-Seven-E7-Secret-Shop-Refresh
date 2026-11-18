"""Mac session entry (e7_macos_refresh) and the GUI's Mac mode. No real input."""
import io
from contextlib import redirect_stdout
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

import e7_macos_refresh as mr
import e7_shop_refresh_gui as gui
from test_e7_macos import make
from test_e7_shop_refresh_gui import FAKE, PACKAGED_ASSETS

ARGS = ['--macos-session', '--budget', '30', '--delay', '1.0', '--stop-key', '`', '--random-offset', 'no']


class SessionEntryTest(unittest.TestCase):
    def run_session(self, arguments):
        out = io.StringIO()
        with redirect_stdout(out):
            code = mr.run_macos_session(arguments)
        return code, out.getvalue()

    def test_missing_tesseract_refuses_before_any_transport(self):
        with patch.object(mr.shutil, 'which', return_value=None), patch.object(mr, 'MacMouse') as transport:
            code, out = self.run_session(ARGS)
        self.assertEqual(code, 3)
        self.assertIn('brew install tesseract', out)
        self.assertIn('No input sent', out)
        transport.assert_not_called()

    def test_missing_game_or_permission_stops_cleanly(self):
        with patch.object(mr.shutil, 'which', return_value='/opt/homebrew/bin/tesseract'), \
                patch.object(mr, 'MacMouse', side_effect=ValueError('Epic Seven is not open on this Mac. No input sent.')):
            code, out = self.run_session(ARGS)
        self.assertEqual(code, 3)
        self.assertIn('E7GUI_MOUSE_STOPPED', out)
        self.assertIn('Mac session stopped', out)
        self.assertNotIn('E7GUI_STARTED', out)

    def test_invalid_arguments_are_rejected(self):
        for bad in (['--budget', '2'], ['--delay', 'nan']):
            arguments = list(ARGS)
            index = arguments.index(bad[0])
            arguments[index+1] = bad[1]
            with self.assertRaises(SystemExit), redirect_stdout(io.StringIO()), patch('sys.stderr', io.StringIO()):
                mr.run_macos_session(arguments)

    def test_engine_switch_reaches_the_mac_session(self):
        source = (Path(__file__).resolve().parent/'E7ADBShopRefresh.py').read_text(encoding='utf-8')
        self.assertIn("if sys.argv[1:2] == ['--macos-session']:", source)

    def test_dry_run_is_labelled_and_uses_the_given_transport(self):
        transport, _, _ = make()
        app = mr.E7MacShopRefresh.__new__(mr.E7MacShopRefresh)
        with patch.object(mr.E7BackgroundShopRefresh, '__init__', lambda self, **kw: setattr(self, 'kw', kw)
                          or setattr(self, '_session_metadata', {})):
            mr.E7MacShopRefresh.__init__(app, transport=transport, dry_run=True, budget=30)
        self.assertIs(app.kw['transport'], transport)
        self.assertTrue(app.kw['dry_run'])
        self.assertEqual(app._session_metadata['Control mode'], 'Mac (dry run)')


MAC_GAME = gui.BackgroundTarget('Epic Seven (Mac)', 'Epic Seven (Mac)', 7561, 86053, (0, 0, 1680, 977))


class MacGuiTest(unittest.TestCase):
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
                        patch.object(gui, 'CONTROL_MODES', ('Mac',)), patch.object(gui, 'DEFAULT_CONTROL_MODE', 'Mac'),
                        patch.object(gui, 'list_mac_games', return_value=[MAC_GAME]),
                        patch.object(gui, 'list_background_games', side_effect=AssertionError('not Background')),
                        patch.object(gui.RefreshGui, '_maybe_show_credits', lambda _: None),
                        patch('winsound.PlaySound'), patch.object(gui, 'release_native_button')]
        for p in self.patches:
            p.start()
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

    def test_mac_mode_finds_the_game_and_warns_about_the_pointer(self):
        self.assertEqual(self.app.control_mode.get(), 'Mac')
        self.assertEqual(tuple(self.app.mode_box.cget('values')), (gui.mode_label('Mac'),))
        self.assertIn('takes over your pointer', gui.mode_label('Mac'))
        self.pump_until(lambda: self.app.mouse_target.get() == 'Epic Seven (Mac)')
        notice = self.app.device_notice.get()
        self.assertIn('takes over your pointer', notice)
        self.assertIn('16:9', notice)
        self.assertNotIn('never moves your pointer', notice)
        self.assertIn('leave the Mac alone', self.app.home_ui_hint.get())

    def test_start_launches_the_mac_engine_as_a_pointer_run(self):
        self.pump_until(lambda: self.app.mouse_target.get() == 'Epic Seven (Mac)')
        with patch.object(gui, 'launch_engine', side_effect=OSError('test: not launched')) as launch:
            self.app.start_button.invoke()
        arguments = launch.call_args.args[0]
        self.assertIn('--macos-session', arguments)
        self.assertNotIn('--background-session', arguments)
        self.assertNotIn('--mouse-session', arguments)
        self.assertEqual(arguments[arguments.index('--stop-key')+1], '`')
        self.assertTrue(self.app._native_mouse_run, 'pointer run: graceful stop, button release, no tracker bar')
        self.assertTrue(self.app._graceful_stop)

    def test_dry_run_switch(self):
        self.pump_until(lambda: self.app.mouse_target.get() == 'Epic Seven (Mac)')
        for value, expected in (('1', True), ('', False)):
            with patch.dict(os.environ, {'E7_DRY_RUN': value}), \
                    patch.object(gui, 'launch_engine', side_effect=OSError('test: not launched')) as launch:
                self.app.start_button.invoke()
            self.assertEqual('--dry-run' in launch.call_args.args[0], expected)
            self.pump_until(lambda: str(self.app.start_button.cget('state')) == 'normal')

    def test_no_game_never_launches(self):
        self.pump_until(lambda: self.app.mouse_target.get() == 'Epic Seven (Mac)')
        self.app.mouse_target.set('')
        with patch.object(gui, 'launch_engine') as launch:
            self.app._start_background_refresh()
        launch.assert_not_called()
        self.assertIn('Open Epic Seven', self.app.connection_warning)
        self.assertNotIn('Steam', self.app.connection_warning)


class MacGuiHelpersTest(unittest.TestCase):
    def test_list_mac_games_reads_the_window_only(self):
        from e7_macos import MacWindow
        window = MacWindow(7561, 86053, 'Epic Seven', 0, (1920., 30., 1680., 977.))
        with patch('e7_macos.scan_game_window', return_value=window):
            games = gui.list_mac_games()
        self.assertEqual(games, [MAC_GAME])

    def test_release_falls_back_quietly(self):
        import e7_macos
        backend = mock.Mock()
        backend.cursor.return_value = (10., 20.)
        self.assertTrue(e7_macos.release_pointer_button(backend))
        backend.post.assert_called_once_with('up', (10., 20.))
        backend.post.side_effect = RuntimeError('no access')
        self.assertFalse(e7_macos.release_pointer_button(backend))

    @unittest.skipUnless(sys.platform == 'darwin', 'macOS module constants')
    def test_macos_constants(self):
        self.assertEqual(gui.CONTROL_MODES, ('Mac',))
        self.assertEqual(gui.release_native_button.__module__, 'e7_macos')
        self.assertIsNone(gui.captured_stop_key('q', 'q', 0x8))      # Command
        self.assertIsNone(gui.captured_stop_key('q', 'q', 0x10))     # Option
        self.assertEqual(gui.captured_stop_key('q', 'q', 0x2), 'q')  # Caps Lock is fine


if __name__ == '__main__':
    unittest.main()
