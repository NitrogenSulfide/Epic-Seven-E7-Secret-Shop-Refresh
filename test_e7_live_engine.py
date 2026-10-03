"""Offline engine checks. Never contact ADB or install keyboard hooks."""
import contextlib
import io
import json
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import E7ADBShopRefresh as engine


class EngineTests(unittest.TestCase):
    def make_engine(self):
        app = engine.E7ADBShopRefresh.__new__(engine.E7ADBShopRefresh)
        app.loop_active, app.end_of_refresh = True, False
        app.stop_refresh_key, app.refresh_count = 'esc', 0
        app.tap_sleep, app.debug, app.budget = .3, False, 3
        app.screenwidth, app.screenheight = 1920, 1080
        app.adb_path, app.device_args = 'NEVER-RUN-ADB', []
        app.storage = engine.E7Inventory()
        app.storage.inventory = {'Covenant bookmark': engine.E7Item(count=0), 'Mystic medal': engine.E7Item(count=0)}
        app.generateOffset = lambda: (0, 0)
        app.navigation = Mock()
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
        with patch.object(engine.subprocess, 'run') as adb:
            with self.assertRaisesRegex(RuntimeError, 'No navigation tap'):
                app.clickShop()
        adb.assert_not_called()

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
