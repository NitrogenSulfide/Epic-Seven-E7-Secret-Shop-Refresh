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
LIST_BACKGROUND_GAMES = gui.list_background_games


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
        label = gui.mode_label('Background')
        self.assertIn('Steam', label)
        self.assertEqual(tuple(self.app.mode_box.cget('values')), (label,))
        self.assertEqual(self.app.mode_label.get(), label)
        self.pump_until(lambda: self.app.mouse_target.get() == 'Epic Seven (Steam)')
        self.assertIn('never moves your pointer', self.app.device_notice.get())
        self.assertTrue(self.app.debug_check.instate(['disabled']))
        self.assertEqual(str(self.app.start_button.cget('state')), 'normal')

    @unittest.skipUnless(os.name == 'nt', 'Windows background scanner')
    def test_missing_windows_game_is_localized_in_both_notices(self):
        self.addCleanup(gui.set_locale, gui.current_locale())
        english = 'Epic Seven (Steam or STOVE) is not running. Start the game, then try again.'
        other_error = 'More than one Epic Seven game window is open. Close the extra one, then try again.'
        self.pump_until(lambda: not self.app._mouse_scan_busy)
        with patch.object(gui, 'list_background_games', LIST_BACKGROUND_GAMES), \
                patch('e7_background.WinGameWindow') as window, \
                patch.object(gui.WindowsCapture, 'list_windows', return_value=[]), \
                patch.object(gui, 'suggested_mode', wraps=gui.suggested_mode) as suggested_mode:
            for locale, error, expected in (
                ('en', ValueError(english), english),
                ('pt_BR', ValueError(english),
                 'O Epic Seven (Steam ou STOVE) não está em execução. Abra o jogo e tente novamente.'),
                ('pt_BR', ValueError(other_error), other_error),
                ('pt_BR', RuntimeError(english), english),
            ):
                with self.subTest(locale=locale, error=repr(error)):
                    gui.set_locale(locale)
                    window.side_effect = error
                    self.app._scan_game_windows()
                    self.pump_until(lambda: not self.app._mouse_scan_busy)
                    self.assertEqual(self.app.home_ui_hint.get(), expected)
                    self.assertEqual(self.app.device_notice.get(), expected)
                    suggested_mode.assert_called_with(True, [], str(error))
                    self.assertIsNone(self.app.mode_suggestion)
                    self.assertTrue(self.app.start_button.instate(['disabled']))

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
        self.assertNotIn('--skip-covenant', arguments)
        self.assertNotIn('--skip-mystic', arguments)
        self.assertFalse(self.app._native_mouse_run)
        self.assertTrue(self.app._graceful_stop)
        self.release.assert_not_called()

    def test_item_choice_reaches_the_engine_and_needs_one_item(self):
        self.pump_until(lambda: self.app.mouse_target.get() == 'Epic Seven (Steam)')
        (self.root/'e7_wine_input.exe').write_bytes(b'MZ')
        self.app.buy_covenant.set(False)
        # The fake engine predates item choice, so Start must refuse before launching.
        with os_named('posix'), patch.object(gui, 'launch_engine', side_effect=OSError('test: not launched')) as launch:
            self.app.start_button.invoke()
        launch.assert_not_called()
        self.assertIn('matching new engine', self.app.connection_warning)
        self.fake.write_text(self.fake.read_text().replace('friendship purchases v1', 'friendship purchases v1; item choice v1'))
        with os_named('posix'), patch.object(gui, 'launch_engine', side_effect=OSError('test: not launched')) as launch:
            self.app.start_button.invoke()
        arguments = launch.call_args.args[0]
        self.assertIn('--skip-covenant', arguments)
        self.assertNotIn('--skip-mystic', arguments)
        self.app.buy_mystic.set(False)
        with self.assertRaisesRegex(ValueError, 'at least one item'):
            self.app._settings()
        self.assertNotIn('Covenant buys', self.app.ev.get())
        self.app._write_sound_preference()
        text = gui.GUI_CONFIG_FILE.read_text()
        self.assertIn('buy_covenant = False', text)
        self.assertIn('buy_mystic = False', text)

    def test_old_custom_timing_is_reset_once_then_kept(self):
        self.app.destroy()
        gui.CONFIG_FILE.write_text('[Settings]\ntap_sleep = 0.8\nbudget = 300\nstop_refresh_key = `\nrandom_offset = False\n')
        gui.GUI_CONFIG_FILE.write_text('[GUI]\ntap_jitter = 0.08\n')
        self.app = gui.RefreshGui(); self.app.withdraw()
        self.assertEqual((self.app.tap_sleep.get(), self.app.random_offset.get(), round(self.app.tap_jitter.get(), 2)), ('0.3', True, 0.03))
        self.assertEqual(self.app.budget.get(), '300')
        self.assertIn('recommended values for this version', self.app.setting_notice.get())
        self.assertIn('tap_sleep = 0.3', gui.CONFIG_FILE.read_text())
        self.assertIn('settings_version = 2', gui.GUI_CONFIG_FILE.read_text())
        # A later Advanced edit sticks across restarts.
        self.app.tap_sleep.set('0.5'); self.app._write_engine_timing(); self.app.destroy()
        self.app = gui.RefreshGui(); self.app.withdraw()
        self.assertEqual(self.app.tap_sleep.get(), '0.5')
        self.app.tap_sleep.set('0.9'); self.app.random_offset.set(False)
        self.assertTrue(self.app._reset_recommended_timing())
        self.assertEqual((self.app.tap_sleep.get(), self.app.random_offset.get()), ('0.3', True))

    def test_failed_timing_reset_is_retried_on_next_start(self):
        self.app.destroy()
        gui.CONFIG_FILE.write_text('[Settings]\ntap_sleep = 0.8\nbudget = 300\nstop_refresh_key = `\nrandom_offset = False\n')
        gui.GUI_CONFIG_FILE.write_text('[GUI]\ntap_jitter = 0.08\n')
        with patch.object(gui.RefreshGui, '_write_engine_timing', side_effect=PermissionError('locked')):
            self.app = gui.RefreshGui(); self.app.withdraw()
        self.assertIn('could not be saved', self.app.setting_notice.get())
        self.app._write_sound_preference()  # an unrelated preference save
        self.assertIn('settings_version = 0', gui.GUI_CONFIG_FILE.read_text())
        self.app.destroy()
        self.app = gui.RefreshGui(); self.app.withdraw()
        self.assertEqual(self.app.tap_sleep.get(), '0.3')
        self.assertIn('tap_sleep = 0.3', gui.CONFIG_FILE.read_text())
        self.assertIn('settings_version = 2', gui.GUI_CONFIG_FILE.read_text())

    def test_malformed_tap_delay_still_loads_items_and_migrates(self):
        self.app.destroy()
        gui.CONFIG_FILE.write_text('[Settings]\ntap_sleep = 0,3\nbudget = 300\nstop_refresh_key = `\nrandom_offset = False\n')
        gui.GUI_CONFIG_FILE.write_text('[GUI]\nbuy_mystic = False\n')
        self.app = gui.RefreshGui(); self.app.withdraw()
        self.assertFalse(self.app.buy_mystic.get())
        self.assertEqual(self.app.tap_sleep.get(), '0.3')
        self.assertIn('settings_version = 2', gui.GUI_CONFIG_FILE.read_text())

    def test_unreadable_engine_config_is_never_overwritten(self):
        original = '[Settings]\ntap_sleep = 0.8\nbudget = 300\nstop_refresh_key = `\nrandom_offset = False\n'
        gui.CONFIG_FILE.write_text(original)
        real_open = Path.open
        def locked(path, *args, **kwargs):
            if path == gui.CONFIG_FILE and 'w' not in (args[0] if args else kwargs.get('mode', 'r')):
                raise PermissionError('locked')
            return real_open(path, *args, **kwargs)
        self.app.tap_sleep.set('0.9')
        with patch.object(Path, 'open', locked):
            self.app._reset_recommended_timing()
        self.assertIn('could not be saved', self.app.setting_notice.get())
        self.assertEqual(gui.CONFIG_FILE.read_text(), original)

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

    def all_modes(self):
        return patch.object(gui, 'CONTROL_MODES', ('ADB', 'Mouse', 'Background'))

    def test_other_client_offers_a_one_click_switch_to_mouse(self):
        app = self.app
        with self.all_modes(), patch.object(gui.RefreshGui, 'refresh_devices'):
            app._apply_mouse_windows([], 'Background mode supports Epic Seven on Steam and STOVE. Use Mouse mode for this game client.', 'Mouse')
            self.assertIn('STOVE', app.home_ui_hint.get())
            self.assertEqual(app.home_ui_action.winfo_manager(), 'grid')
            self.assertEqual(app.home_ui_action.cget('text'), 'Switch to Mouse')
            self.assertEqual(str(app.start_button.cget('state')), 'disabled')
            app.home_ui_action.invoke()
        self.assertEqual(app.control_mode.get(), 'Mouse')
        self.assertIn('control_mode = Mouse', gui.GUI_CONFIG_FILE.read_text())
        self.assertIsNone(app.mode_suggestion)
        self.assertEqual(app.home_ui_action.winfo_manager(), '')

    def test_steam_seen_in_mouse_mode_suggests_background_without_switching(self):
        app = self.app
        with self.all_modes(), patch.object(gui.RefreshGui, 'refresh_devices'):
            app.control_mode.set('Mouse'); app._change_control_mode()
            app._apply_mouse_windows([GAME], '', 'Background')
            self.assertEqual(app.control_mode.get(), 'Mouse')
            self.assertEqual(app.connection_warning, '')
            self.assertIn('Steam or STOVE found', app.home_ui_hint.get())
            self.assertEqual(app.home_ui_action.cget('text'), 'Switch to Background')
            # A dismissed suggestion stays dismissed on the next idle scan.
            app.home_ui_dismiss.invoke()
            app._apply_mouse_windows([GAME], '', 'Background')
            self.assertEqual(app.home_ui_banner.winfo_manager(), '')
            app.home_ui_action.invoke()
        self.assertEqual(app.control_mode.get(), 'Background')
        self.assertIn('control_mode = Background', gui.GUI_CONFIG_FILE.read_text())

    def test_suggestion_for_a_missing_or_current_mode_is_ignored(self):
        app = self.app  # this platform offers Background only
        for suggestion in ('Mouse', 'Background', None):
            app._apply_mouse_windows([GAME], '', suggestion)
            self.assertIsNone(app.mode_suggestion)
            self.assertEqual(app.home_ui_action.winfo_manager(), '')

    def test_mode_list_shows_labels_but_saves_plain_mode_names(self):
        app = self.app
        with self.all_modes(), patch.object(gui.RefreshGui, 'refresh_devices'):
            app.mode_box.configure(values=[gui.mode_label(mode) for mode in gui.CONTROL_MODES])
            app.mode_label.set('Mouse · emulators, takes over your pointer')
            app._select_control_mode()
            self.assertEqual(app.control_mode.get(), 'Mouse')
            app.control_mode.set('ADB')  # e.g. a loaded setting or a Switch button
            self.assertEqual(app.mode_label.get(), 'ADB · emulators')
            app.process = mock.Mock(); app.process.poll.return_value = None
            app.mode_label.set(gui.mode_label('Background'))
            app._select_control_mode()
            app.process = None
        self.assertEqual(app.control_mode.get(), 'ADB')
        self.assertEqual(app.mode_label.get(), 'ADB · emulators')
        with os_named('nt'):
            self.assertEqual(gui.mode_label('Background'), 'Background · Steam / STOVE (recommended)')

    def test_switch_is_refused_while_a_session_runs(self):
        app = self.app
        with self.all_modes():
            app.mode_suggestion = 'Mouse'
            app.process = mock.Mock(); app.process.poll.return_value = None
            app._take_mode_suggestion()
            app.process = None
        self.assertEqual(app.control_mode.get(), 'Background')


    WINDOWS_POINTER = ('The pointer is moving over the game window; background input waits until it stays still. '
                       'Leave it still, or park it on the taskbar.')

    def pause(self, reason, observed_at=None):
        self.app._handle_line('E7GUI_MOUSE_PAUSED '+gui.json.dumps({'reason': reason}), observed_at=observed_at)

    def alert_shown(self):
        return (self.app.pointer_alert_label.winfo_manager() == 'grid', self.app.tracker.alert.winfo_manager() == 'grid')

    def test_pointer_pause_shows_red_countdown_in_both_views_until_resumed(self):
        self.app._background_run = True
        self.pause(self.WINDOWS_POINTER, observed_at=time.monotonic()-7.2)
        self.assertEqual(self.app.status.get(), 'Paused')
        self.assertEqual(self.app.pointer_alert.get(), 'Mouse moving over the game · paused · stops in 3 s')
        self.assertEqual(self.alert_shown(), (True, True))
        self.assertEqual(self.app.progress_text.get(), 'Paused · no input while the pointer is over the game')
        self.app._handle_line('E7GUI_MOUSE_RESUMED')
        self.assertEqual(self.app.status.get(), 'Running')
        self.assertEqual(self.app.pointer_alert.get(), '')
        self.assertEqual(self.alert_shown(), (False, False))
        self.assertIsNone(self.app._pointer_job)

    def test_pointer_countdown_ticks_down_and_never_goes_negative(self):
        self.app._background_run = True
        self.pause(self.WINDOWS_POINTER)
        self.assertTrue(self.app.pointer_alert.get().endswith('stops in 10 s'))
        self.app._pointer_deadline = time.monotonic()-5
        self.app._tick_pointer_alert()
        self.assertTrue(self.app.pointer_alert.get().endswith('stops in 0 s'))

    def test_linux_pointer_pause_says_over_not_moving(self):
        self.app._background_run = True
        self.pause('Move your mouse off the game window; background input pauses while the pointer is over it.')
        self.assertTrue(self.app.pointer_alert.get().startswith('Mouse over the game · paused · stops in '))

    def test_other_background_pauses_show_no_pointer_alert(self):
        self.app._background_run = True
        self.pause('The game window is minimized or hidden.')
        self.assertEqual(self.app.pointer_alert.get(), '')
        self.assertEqual(self.alert_shown(), (False, False))
        self.assertEqual(self.app.progress_text.get(), 'Paused · see the reason above')

    def test_session_stop_clears_pointer_alert(self):
        self.app._background_run = True
        self.pause(self.WINDOWS_POINTER)
        self.app._handle_line('E7GUI_MOUSE_STOPPED '+gui.json.dumps({'reason': 'Stopped after 10 seconds.'}))
        self.assertEqual(self.app.status.get(), 'Needs attention')
        self.assertEqual(self.app.pointer_alert.get(), '')

    def hint_shown(self):
        return self.app.tracker.hint.winfo_manager() == 'grid'

    def test_compact_hint_says_what_to_do_while_paused_and_after(self):
        self.app._background_run = True
        self.pause(self.WINDOWS_POINTER)
        self.assertEqual(self.app.compact_hint.get(), 'Leave the mouse still, or park it on the taskbar. It resumes by itself.')
        self.assertTrue(self.hint_shown())
        self.app._handle_line('E7GUI_MOUSE_RESUMED')
        self.assertTrue(self.app.compact_hint.get().startswith('Resumed · checking the screen'))
        self.app._handle_line('Navigation: The Secret Shop did not open; checking the home screen again.')
        self.assertTrue(self.app.compact_hint.get().startswith('Shop didn’t open (click missed)'))
        self.app._handle_line('Navigation: Revealing the recognized home screen controls.')
        self.assertTrue(self.app.compact_hint.get().startswith('Shop didn’t open'))  # unrelated lines keep it
        self.app._handle_line('Navigation: Secret Shop screen verified.')
        self.assertEqual(self.app.compact_hint.get(), '')
        self.assertFalse(self.hint_shown())

    def test_compact_hint_for_linux_pointer_minimized_game_and_missed_confirm(self):
        self.app._background_run = True
        self.pause('Move your mouse off the game window; background input pauses while the pointer is over it.')
        self.assertTrue(self.app.compact_hint.get().startswith('Move the mouse onto the compact bar'))
        self.pause('The game window is minimized or hidden.')
        self.assertEqual(self.app.compact_hint.get(), 'Restore the game window. It resumes by itself.')
        self.app._handle_line('E7GUI_MOUSE_RESUMED')
        self.app._handle_line('Navigation: The pointer passed over the game and the same confirmation is still open; confirming once more.')
        self.assertTrue(self.app.compact_hint.get().startswith('Confirm click was missed'))
        self.app._handle_line('Navigation: The game did not take the Confirm click and the same confirmation is still open; confirming once more.')
        self.assertTrue(self.app.compact_hint.get().startswith('Game missed the Confirm click'))
        self.app._handle_line('Navigation: The game did not open the Refresh dialog; clicking Refresh once more.')
        self.assertTrue(self.app.compact_hint.get().startswith('Game missed the Refresh click'))

    def test_copy_report_after_a_stop_has_setup_reason_failure_and_tail(self):
        self.assertEqual(self.app.report_actions.winfo_manager(), '')
        self.app.mouse_target.set('Epic Seven (Steam)')
        self.app._report_since = time.time()-1
        failure = self.root/'mouse-failures'/'abc123'
        failure.mkdir(parents=True)
        (failure/'failure.json').write_text('{"operation": "refresh", "confirmation_clicked": false}')
        (failure/'before.png').write_bytes(b'')
        home = str(Path.home())
        self.app.raw_output = ('Game window: 1920 x 1009, windowed, display scale 100%\n'
                               + ''.join(f'Navigation: step {i}\n' for i in range(100))
                               + f'Engine: {home}/E7/engine.exe\n')
        self.app._handle_line('E7GUI_MOUSE_STOPPED {"reason": "The Secret Shop did not open after selecting its menu."}')
        self.assertEqual(self.app.report_actions.winfo_manager(), 'grid')
        self.assertEqual(self.app.open_failure_button.winfo_manager(), 'pack')
        with patch.object(self.app, 'clipboard_clear'), patch.object(self.app, 'clipboard_append') as copy:
            self.app._copy_report()
        report = copy.call_args.args[0]
        self.assertIn(f'v{gui.APP_VERSION} (beta) report', report)
        self.assertIn('- Mode: Background · Epic Seven (Steam)', report)
        self.assertIn('- Game window: 1920 x 1009, windowed, display scale 100%', report)
        self.assertIn('- Result: Needs attention · The Secret Shop did not open', report)
        self.assertIn('mouse-failures/abc123 {"operation": "refresh"', report)
        self.assertIn('Pictures to attach from that folder: before.png', report)
        self.assertIn('Last 60 log lines:', report)
        self.assertIn('    Navigation: step 99', report)
        self.assertNotIn('step 39\n', report)
        self.assertNotIn(home, report)
        self.assertEqual(self.app.copy_report_button.cget('text'), 'Copied ✓')

    def test_tap_delay_below_the_floor_is_raised_in_the_box(self):
        self.app.tap_sleep.set('0.05')
        self.assertEqual(self.app._settings().tap_sleep, .3)
        self.assertEqual(self.app.tap_sleep.get(), '0.3')

    def test_copy_report_appears_after_a_launch_failure_logs_its_error(self):
        # The launch-error handler sets Failed before the error reaches the log.
        self.app.raw_output = ''
        self.app.status.set('Failed')
        self.assertEqual(self.app.report_actions.winfo_manager(), '')
        self.app._append_log('Engine could not start: file not found\n')
        self.assertEqual(self.app.report_actions.winfo_manager(), 'grid')

    def test_copy_report_ignores_failure_records_from_earlier_sessions(self):
        old = self.root/'mouse-failures'/'old'
        old.mkdir(parents=True)
        os.utime(old, (time.time()-3600,)*2)
        self.app._report_since = time.time()-1
        self.app.raw_output = 'Navigation: x\n'
        self.app._handle_line('E7GUI_MOUSE_STOPPED {"reason": "Stopped."}')
        self.assertEqual(self.app.open_failure_button.winfo_manager(), '')
        self.assertNotIn('Failure record', self.app._report_text())

    def test_mouse_mode_keeps_the_full_window_instead_of_the_always_on_top_bar(self):
        # Mouse mode reads the real screen; the always-on-top bar over the game
        # hid the shop title (W11 STOVE, 2026-11-14). Background is unaffected.
        self.app.compact_tracker.set(True)
        for native, entered in ((True, False), (False, True)):
            with self.subTest(native=native):
                self.app.tracker = mock.Mock()
                self.app.run_settings = mock.Mock(debug=False, trace_input=False, buy_friendship=False)
                self.app._session_started = self.app.stopping = False
                self.app._finalized_run_id = None
                self.app._native_mouse_run = native
                with patch.object(self.app, '_update_remaining_time'), patch.object(self.app, '_play_session_sound'):
                    self.app._engine_started()
                    self.app._enter_compact()
                self.assertEqual(self.app.tracker.enter.called, entered)
                self.assertEqual(self.app.tracker.enter.call_count, 2 if entered else 0)

    def test_compact_hint_expires_unless_still_paused_and_clears_on_stop(self):
        self.app._background_run = True
        self.app._handle_line('E7GUI_MOUSE_RESUMED')
        self.app._expire_compact_hint()
        self.assertEqual(self.app.compact_hint.get(), '')
        self.pause(self.WINDOWS_POINTER)
        self.app._expire_compact_hint()
        self.assertNotEqual(self.app.compact_hint.get(), '')
        self.app._handle_line('E7GUI_MOUSE_STOPPED '+gui.json.dumps({'reason': 'Stopped after 10 seconds.'}))
        self.assertEqual(self.app.compact_hint.get(), '')
        self.assertIsNone(self.app._hint_job)

    def test_navigation_hints_match_the_engine(self):
        source = Path('e7_shop_flow.py').read_text(encoding='utf-8')
        for prefix, _ in gui.NAVIGATION_HINTS[1:]+tuple((p, '') for p in gui.CLEAR_HINT_NAVIGATION):
            self.assertIn('Navigation: '+prefix, source)

    def test_pointer_alert_matches_the_engine(self):
        import e7_background
        self.assertEqual(gui.POINTER_PAUSE_LIMIT, e7_background.PAUSE_LIMIT)
        source = Path(e7_background.__file__).read_text(encoding='utf-8')
        # [0] is only sent by engines before 0.2.4; the current engine sends [1].
        self.assertIn(gui.POINTER_PAUSE_REASONS[1], source)
        self.assertNotIn(gui.POINTER_PAUSE_REASONS[0], source)


class SuggestedModeTest(unittest.TestCase):
    def test_background_is_the_default_on_every_platform(self):
        self.assertEqual(gui.DEFAULT_CONTROL_MODE, 'Background')

    def test_windows_suggestions(self):
        steam_only = 'Background mode supports Epic Seven on Steam and STOVE. Use Mouse mode for this game client.'
        missing = 'Epic Seven (Steam or STOVE) is not running. Start the game, then try again.'
        with os_named('nt'):
            self.assertEqual(gui.suggested_mode(True, [], steam_only), 'Mouse')
            self.assertIsNone(gui.suggested_mode(True, [GAME], ''))
            with patch.object(gui, 'WindowsCapture') as capture:
                capture.return_value.list_windows.return_value = [GAME]
                self.assertEqual(gui.suggested_mode(True, [], missing), 'Mouse')
                capture.return_value.list_windows.return_value = []
                self.assertIsNone(gui.suggested_mode(True, [], missing))
                capture.return_value.list_windows.return_value = [GAME]
                for other in ('More than one Epic Seven game window is open. Close the extra one, then try again.',
                              'Could not verify the selected game process. Scan again.'):
                    self.assertIsNone(gui.suggested_mode(True, [], other))
                capture.return_value.list_windows.side_effect = OSError('scan failed')
                self.assertIsNone(gui.suggested_mode(True, [], missing))
            with patch('e7_native_mouse.process_name', side_effect=['LDPlayer.exe', 'EpicSeven_Steam.exe']):
                self.assertEqual(gui.suggested_mode(False, [GAME, GAME], ''), 'Background')
            with patch('e7_native_mouse.process_name', side_effect=ValueError('gone')):
                self.assertIsNone(gui.suggested_mode(False, [GAME], ''))
            with patch('e7_native_mouse.process_name', return_value='EpicSeven.exe'):  # STOVE
                self.assertEqual(gui.suggested_mode(False, [GAME], ''), 'Background')
            with patch('e7_native_mouse.process_name', return_value='HD-Player.exe'):
                self.assertIsNone(gui.suggested_mode(False, [GAME], ''))

    def test_other_platforms_never_suggest(self):
        with os_named('posix'):
            self.assertIsNone(gui.suggested_mode(True, [], 'Background mode supports Epic Seven on Steam.'))


class ListBackgroundGamesTest(unittest.TestCase):
    def test_windows_reports_the_steam_window(self):
        for client in ('Steam', 'STOVE'):
            window = mock.Mock(hwnd=0x5012e, pid=777, game_client=client); window.size.return_value = (3840, 2019)
            with os_named('nt'), patch('e7_background.WinGameWindow', return_value=window):
                games = gui.list_background_games()
            name = f'Epic Seven ({client})'
            self.assertEqual(games, [gui.BackgroundTarget(name, name, 0x5012e, 777, (0, 0, 3840, 2019))])


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
