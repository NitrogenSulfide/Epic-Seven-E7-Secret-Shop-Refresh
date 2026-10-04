"""Offline engine checks. Never contact ADB or install keyboard hooks."""
import contextlib
import io
import json
from pathlib import Path
import sys
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import E7ADBShopRefresh as engine


class StartupSelectionTests(unittest.TestCase):
    def test_existing_device_selection_advances_to_settings(self):
        # Execute the real entry point, with every ADB operation replaced.
        # Stop at the first settings question, before construction/game actions.
        class SettingsReached(Exception):
            pass

        prompts = []
        source = Path(engine.__file__).read_text(encoding='utf-8')
        for device in ('localhost:6520', 'emulator-5554'):
            with self.subTest(device=device):
                prompts.clear()
                def answer(prompt):
                    prompts.append(prompt)
                    if len(prompts) > 3:
                        self.fail('Existing-device selection repeated instead of advancing.')
                    if 'finish reading' in prompt:
                        return ''
                    if prompt == 'Device: ':
                        return device
                    if 'Launch in debug mode?' in prompt:
                        raise SettingsReached
                    self.fail(f'Unexpected startup prompt: {prompt}')

                def fake_adb(arguments, **kwargs):
                    self.assertEqual(arguments[-1], 'devices')
                    return SimpleNamespace(stdout='List of devices attached\nlocalhost:6520\tdevice\nemulator-5554\tdevice\n\n', returncode=0)

                with patch.object(engine.subprocess, 'run', side_effect=fake_adb) as adb, \
                        patch('builtins.input', side_effect=answer), \
                        patch.object(engine.os.path, 'isdir', return_value=True), \
                        patch.object(engine.os.path, 'exists', return_value=False), \
                        patch.object(sys, 'argv', ['E7ADBShopRefresh.py']), \
                        contextlib.redirect_stdout(io.StringIO()), \
                        self.assertRaises(SettingsReached):
                    exec(compile(source, str(engine.__file__), 'exec'),
                         {'__name__':'__main__', '__file__':str(engine.__file__)})
                self.assertEqual(prompts.count('Device: '), 1)
                self.assertEqual(adb.call_count, 2)


class EngineTests(unittest.TestCase):
    def make_engine(self):
        app = engine.E7ADBShopRefresh.__new__(engine.E7ADBShopRefresh)
        app.loop_active, app.end_of_refresh = True, False
        app.stop_refresh_key, app.refresh_count = '`', 0
        app.tap_sleep, app.debug, app.budget = .3, False, 12
        app.screenwidth, app.screenheight = 1920, 1080
        app.adb_path, app.device_args = 'NEVER-RUN-ADB', []
        app.storage = engine.E7Inventory()
        app.storage.inventory = {'Covenant bookmark': engine.E7Item(count=0), 'Mystic medal': engine.E7Item(count=0)}
        app.generateOffset = lambda: (0, 0)
        app.navigation = Mock()
        app.navigation.verification_details.return_value = 'title=0.500 (unverified); refresh=0.400 (unverified)'
        app.takeScreenshot = lambda: 'fake'
        return app

    def test_key_poll_yields_and_detects_stop(self):
        app = self.make_engine()
        with patch.object(engine.keyboard, 'is_pressed', side_effect=[False, False, True]) as key, patch.object(engine.time, 'sleep') as sleep, contextlib.redirect_stdout(io.StringIO()) as output:
            app.checkKeyPress()
        self.assertEqual(key.call_count, 3)
        self.assertEqual(sleep.call_args_list, [unittest.mock.call(.02)] * 2)
        self.assertFalse(app.loop_active)
        self.assertIn('Shop refresh terminated!', output.getvalue())

    def test_normal_end_does_not_claim_stop_key(self):
        app = self.make_engine()
        app.end_of_refresh = True
        with patch.object(engine.keyboard, 'is_pressed') as key, contextlib.redirect_stdout(io.StringIO()) as output:
            app.checkKeyPress()
        key.assert_not_called()
        self.assertEqual(output.getvalue(), '')

    def test_live_stats_after_each_purchase_and_refresh(self):
        app = self.make_engine()
        app.budget = 3  # Single-refresh boundary case; no live game actions.
        positions = iter([(10, 10), (20, 20), None, None, None, None, None, None])
        with patch.object(app, 'clickShop'), patch.object(app, 'takeScreenshot', return_value='fake'), patch.object(app, 'findItemPosition', side_effect=lambda *_: next(positions)), patch.object(app, 'clickBuy', return_value=True), patch.object(app, 'clickRefresh', return_value=True), patch.object(app, 'printResult'), patch.object(app.storage, 'writeToCSV'), patch.object(engine.subprocess, 'run'), patch.object(engine.time, 'sleep'), contextlib.redirect_stdout(io.StringIO()) as output:
            app.refreshShop()
        stats = [json.loads(line.split(' ', 1)[1]) for line in output.getvalue().splitlines() if line.startswith('E7GUI_STATS ')]
        self.assertEqual([(s['covenant'], s['mystic'], s['skystone_spent']) for s in stats], [(0, 0, 0), (1, 0, 0), (1, 1, 0), (1, 1, 3), (1, 1, 3)])

    def test_stop_between_refresh_taps_does_not_count(self):
        app = self.make_engine()
        def stop_after_tap(*args, **kwargs):
            app.loop_active = False
        with patch.object(engine.subprocess, 'run', side_effect=stop_after_tap) as adb, patch.object(engine.time, 'sleep'):
            self.assertFalse(app.clickRefresh())
        self.assertEqual(adb.call_count, 1)
        self.assertEqual(app.refresh_count, 0)

    def test_buy_checks_both_adb_taps_and_stop(self):
        app = self.make_engine()
        with patch.object(engine.subprocess, 'run') as adb, patch.object(engine.time, 'sleep'):
            self.assertTrue(app.clickBuy((10, 10)))
        self.assertEqual(adb.call_count, 2)
        self.assertTrue(all(call.kwargs['check'] for call in adb.call_args_list))
        app.loop_active = False
        with patch.object(engine.subprocess, 'run') as adb:
            self.assertFalse(app.clickBuy((10, 10)))
        adb.assert_not_called()

    def test_adb_failure_does_not_count_purchase(self):
        app = self.make_engine()
        error = engine.subprocess.CalledProcessError(1, 'fake adb')
        with patch.object(engine.subprocess, 'run', side_effect=error), patch.object(engine.time, 'sleep'):
            with self.assertRaises(engine.subprocess.CalledProcessError):
                app.clickBuy((10, 10))
        self.assertEqual(app.storage.inventory['Covenant bookmark'].count, 0)

    def test_start_cleans_up_poll_thread_after_failure(self):
        app = self.make_engine()
        app.keyboard_thread = threading.Thread(target=app.checkKeyPress)
        with patch.object(engine.keyboard, 'is_pressed', return_value=False), patch.object(app, 'refreshShop', side_effect=RuntimeError('fake failure')):
            with self.assertRaises(RuntimeError):
                app.start()
        self.assertTrue(app.end_of_refresh)
        self.assertFalse(app.keyboard_thread.is_alive())

    def test_shop_already_open_sends_no_navigation_tap(self):
        app = self.make_engine()
        app.navigation.shop_visible.return_value = True
        with patch.object(engine.subprocess, 'run') as adb:
            self.assertTrue(app.clickShop())
        adb.assert_not_called()

    def test_home_navigation_taps_matched_target_once_then_verifies(self):
        app = self.make_engine()
        app.navigation.shop_visible.side_effect = [False, False, True]
        app.navigation.menu_target.return_value = (86, 548)
        with patch.object(engine.subprocess, 'run') as adb, patch.object(engine.time, 'sleep'):
            self.assertTrue(app.clickShop())
        adb.assert_called_once_with(['NEVER-RUN-ADB','shell','input','tap','86','548'],check=True)

    def test_unknown_home_never_taps(self):
        app = self.make_engine()
        app.navigation.shop_visible.return_value = False
        app.navigation.menu_target.return_value = None
        with patch.object(engine.subprocess, 'run') as adb, patch.object(engine.time, 'monotonic', side_effect=[0, 61]):
            with self.assertRaisesRegex(RuntimeError, 'No navigation tap'):
                app.clickShop()
        adb.assert_not_called()

    def test_recognition_failure_reports_setup_without_refresh_or_traceback(self):
        failure = engine.NavigationSetupRequired('No navigation tap sent. Use setup.')
        with patch.object(engine, 'E7ADBShopRefresh', side_effect=failure), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertFalse(engine.run_refresh_engine(budget=12))
        self.assertIn('E7GUI_SETUP_REQUIRED ',output.getvalue())
        self.assertNotIn('Traceback',output.getvalue())
        with patch.object(engine, 'E7ADBShopRefresh', side_effect=RuntimeError('other failure')):
            with self.assertRaisesRegex(RuntimeError,'other failure'):
                engine.run_refresh_engine(budget=12)

    def test_hidden_ui_waits_then_follows_recognized_menu(self):
        app = self.make_engine()
        app.navigation.shop_visible.side_effect = [False, False, True]
        app.navigation.menu_target.side_effect = [None, (86,548)]
        with patch.object(engine.subprocess, 'run') as adb, patch.object(engine.time, 'sleep') as sleep, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertTrue(app.clickShop())
        self.assertIn('Waiting for visible game controls.', output.getvalue())
        self.assertEqual(sleep.call_args_list, [unittest.mock.call(1.0), unittest.mock.call(.25)])
        adb.assert_called_once_with(['NEVER-RUN-ADB','shell','input','tap','86','548'],check=True)

    def test_user_opens_shop_during_wait_without_navigation_tap(self):
        app = self.make_engine()
        app.navigation.shop_visible.side_effect = [False, True]
        app.navigation.menu_target.return_value = None
        with patch.object(engine.subprocess, 'run') as adb, patch.object(engine.time, 'sleep'):
            self.assertTrue(app.clickShop())
        adb.assert_not_called()

    def test_stop_during_ui_wait_sends_no_taps_or_extra_capture(self):
        app = self.make_engine()
        app.navigation.shop_visible.return_value = False
        app.navigation.menu_target.return_value = None
        def stop(_): app.loop_active = False
        with patch.object(engine.subprocess, 'run') as adb, patch.object(engine.time, 'sleep', side_effect=stop), patch.object(app, 'takeScreenshot', return_value='fake') as capture:
            self.assertFalse(app.clickShop())
        adb.assert_not_called()
        capture.assert_called_once()

    def test_wrong_page_after_navigation_aborts_without_retry(self):
        app = self.make_engine()
        app.navigation.shop_visible.return_value = False
        app.navigation.menu_target.return_value = (86, 548)
        with patch.object(engine.subprocess, 'run') as adb, patch.object(engine.time, 'sleep'), patch.object(engine.time, 'monotonic', side_effect=[0,0,9]):
            with self.assertRaisesRegex(RuntimeError, 'Stopped before purchasing'):
                app.clickShop()
        self.assertEqual(adb.call_count, 1)

    def test_buy_and_refresh_reject_wrong_screen_before_tap(self):
        app = self.make_engine()
        app.navigation.require_shop.side_effect = RuntimeError('Wrong screen')
        with patch.object(engine.subprocess, 'run') as adb:
            with self.assertRaisesRegex(RuntimeError, 'Wrong screen'):
                app.clickBuy((10,10))
            with self.assertRaisesRegex(RuntimeError, 'Wrong screen'):
                app.clickRefresh()
        adb.assert_not_called()


if __name__ == '__main__':
    unittest.main()
