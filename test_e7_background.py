import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from PIL import Image

import e7_background as bg
from e7_native_mouse import MouseStopped, MouseRecheckRequired


class FakeWindow:
    def __init__(self, size=(3840, 2016)):
        self._size = size
        self.problems = []
        self.image = Image.new('RGB', size, (40, 40, 40))
        self.image.paste((200, 180, 90), (100, 100, 600, 400))

    def size(self):
        return self._size

    def problem(self):
        return self.problems.pop(0) if self.problems else None

    def capture(self):
        return self.image


class FakeWine:
    def __init__(self, size=(3840, 2016)):
        self.size, self.sent, self.closed = size, [], False

    def find(self):
        return 1234, *self.size

    def request(self, command, **_):
        self.sent.append(command)
        return 'ok'

    def close(self):
        self.closed = True


def make(active=lambda: True, **kw):
    window, wine = kw.pop('window', FakeWindow()), kw.pop('wine', FakeWine())
    return bg.BackgroundGame(active, window=window, wine=wine), window, wine


class BackgroundGameTest(unittest.TestCase):
    def test_click_maps_game_space_to_client_pixels(self):
        game, _, wine = make()
        game.screenshot()
        self.assertEqual(game.click(960, 540), (1920, 1008))
        self.assertEqual(wine.sent, ['click 1920 1008'])

    def test_drag_sends_one_helper_command_with_duration(self):
        game, _, wine = make()
        game.screenshot()
        game.drag(1000, 800, 1000, 300, duration=.32)
        self.assertEqual(wine.sent, ['drag 2000 1493 2000 560 320'])

    def test_input_before_first_capture_is_refused(self):
        game, _, wine = make()
        with self.assertRaises(MouseStopped):
            game.click(10, 10)
        self.assertEqual(wine.sent, [])

    def test_out_of_range_and_bad_duration_are_refused(self):
        game, _, wine = make()
        game.screenshot()
        with self.assertRaises(MouseStopped):
            game.click(1920, 10)
        with self.assertRaises(MouseStopped):
            game.drag(0, 0, 10, 10, duration=2)
        self.assertEqual(wine.sent, [])

    def test_pause_then_resume_rechecks_instead_of_clicking(self):
        game, window, wine = make()
        game.screenshot()
        window.problems = ['Move your mouse off the game window']
        with mock.patch('builtins.print'), mock.patch.object(bg.time, 'sleep'):
            with self.assertRaises(MouseRecheckRequired):
                game.click(100, 100)
        self.assertEqual(wine.sent, [])
        self.assertEqual(game.pause_revision, 1)

    def test_pause_that_never_clears_stops(self):
        game, window, wine = make()
        game.screenshot()
        window.problem = lambda: 'The game window is minimized or hidden.'
        clock = iter(range(0, 100, 5))
        with mock.patch('builtins.print'), mock.patch.object(bg.time, 'sleep'), \
                mock.patch.object(bg.time, 'monotonic', lambda: next(clock)):
            with self.assertRaisesRegex(MouseStopped, 'minimized'):
                game.click(100, 100)
        self.assertEqual(wine.sent, [])

    def test_inactive_session_sends_nothing(self):
        game, _, wine = make(active=lambda: False)
        game.screenshot()  # capture before the session starts is allowed, as in Mouse mode
        with self.assertRaises(MouseStopped):
            game.click(5, 5)
        self.assertEqual(wine.sent, [])

    def test_resize_stops(self):
        game, window, wine = make()
        game.screenshot()
        window._size = (1920, 1080)
        with self.assertRaisesRegex(MouseStopped, 'resized'):
            game.click(5, 5)
        self.assertEqual(wine.sent, [])

    def test_wine_and_x_size_mismatch_is_refused(self):
        wine = FakeWine((1920, 1008))
        with self.assertRaisesRegex(ValueError, 'scaling'):
            make(wine=wine)
        self.assertTrue(wine.closed)

    def test_blank_capture_stops(self):
        window = FakeWindow()
        window.image = Image.new('RGB', window.size(), (0, 0, 0))
        game, _, _ = make(window=window)
        with self.assertRaisesRegex(MouseStopped, 'blank'):
            game.screenshot()

    def test_letterboxed_client_is_cropped_to_16_by_9(self):
        window = FakeWindow((2000, 1080))
        window.image = Image.new('RGB', (2000, 1080), (0, 0, 0))
        window.image.paste((120, 120, 120), (40, 0, 1960, 1080))
        game, _, wine = make(window=window, wine=FakeWine((2000, 1080)))
        self.assertEqual(game.screenshot().size, (1920, 1080))
        game.click(0, 0)
        self.assertEqual(wine.sent, ['click 40 0'])


@unittest.skipIf(os.name == 'nt', 'Linux/Proton only')
class ProtonSessionTest(unittest.TestCase):
    def make_proc(self, root, pid, exe, env):
        (root/str(pid)).mkdir()
        os.symlink(exe, root/str(pid)/'exe')
        (root/str(pid)/'environ').write_bytes(b'\0'.join(f'{k}={v}'.encode() for k, v in env.items()))

    def test_finds_the_games_wineserver_and_proton_wine(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            files = tmp/'Proton - Experimental'/'files'
            (files/'bin').mkdir(parents=True); (files/'lib').mkdir()
            (files/'bin'/'wine').touch(); (files/'bin'/'wineserver').touch()
            proc = tmp/'proc'; proc.mkdir()
            self.make_proc(proc, 10, '/usr/bin/bash', {})
            self.make_proc(proc, 11, files/'bin'/'wineserver', {'WINEPREFIX': '/x/compatdata/999/pfx/'})
            self.make_proc(proc, 12, files/'bin'/'wineserver',
                           {'WINEPREFIX': '/x/compatdata/5019180/pfx/', 'WINEFSYNC': '1', 'SECRET': 'no'})
            session = bg.find_proton_session(proc=proc)
            self.assertEqual(session.wine, files/'bin'/'wine')
            self.assertEqual(session.prefix, Path('/x/compatdata/5019180/pfx'))
            self.assertEqual(session.env, {'WINEFSYNC': '1'})
            env = session.environment()
            self.assertEqual(env['WINEPREFIX'], '/x/compatdata/5019180/pfx')
            self.assertTrue(env['LD_LIBRARY_PATH'].startswith(str(files/'lib')))

    def test_reports_game_not_running(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, 'not running'):
                bg.find_proton_session(proc=Path(tmp))


class XGameWindowFindTest(unittest.TestCase):
    def tree(self, *names):
        def node(cls=(), name=None, children=()):
            w = mock.Mock(); w.get_wm_class.return_value = cls; w.get_wm_name.return_value = name
            w.query_tree.return_value.children = list(children); return w
        games = [node(('steam_app_5019180',), n) for n in names]
        finder = object.__new__(bg.XGameWindow)
        finder.app_class, finder.root = 'steam_app_5019180', node(children=[node(children=[g]) for g in games])
        return finder, games

    def test_single_game_window_is_found(self):
        finder, games = self.tree('Epic Seven', 'Steam')
        self.assertIs(finder._find(), games[0])

    def test_two_game_windows_are_refused(self):
        finder, _ = self.tree('Epic Seven', 'Epic Seven')
        with self.assertRaisesRegex(ValueError, 'More than one'):
            finder._find()


@unittest.skipIf(os.name == 'nt', 'Linux/Proton only')
class WineInputTest(unittest.TestCase):
    def test_error_replies_become_mouse_stopped(self):
        class Proc:
            def __init__(self, *a, **k):
                import io
                self.stdin, self.stdout = io.StringIO(), None
            def poll(self):
                return None
        wine = bg.WineInput(bg.ProtonSession(Path('/w/bin/wine'), Path('/p')), helper='h.exe', popen=Proc)
        r, w = os.pipe()
        wine.process.stdout = os.fdopen(r)
        os.write(w, b'err game window is minimized\n'); os.close(w)
        with self.assertRaisesRegex(MouseStopped, 'minimized'):
            wine.request('click 1 1')
        wine.process.stdout.close()
        self.assertEqual(wine.process.stdin.getvalue(), 'click 1 1\n')


class BackgroundEngineTest(unittest.TestCase):
    def test_engine_uses_background_transport_without_adb(self):
        import E7ADBShopRefresh as adb_engine
        from e7_background_refresh import E7BackgroundShopRefresh
        transport = mock.Mock()
        frame = Image.new('RGB', (1920, 1080), (60, 60, 60)); frame.paste((200, 160, 80), (100, 100, 900, 600))
        transport.screenshot.return_value = frame
        with mock.patch.object(adb_engine.subprocess, 'run') as adb:
            app = E7BackgroundShopRefresh(transport=transport, budget=12, tap_sleep=.3,
                                          stop_refresh_key='`', random_offset=False)
        adb.assert_not_called()
        self.assertIs(app.mouse, transport)
        self.assertEqual((app.screenwidth, app.screenheight), (1920, 1080))
        self.assertEqual(app._session_metadata['Control mode'], 'Background')
        app.tap(10, 20)
        transport.click.assert_called_once_with(10, 20)
        app.close_transport()
        transport.close.assert_called_once()


class DryRunTest(unittest.TestCase):
    def make(self):
        from e7_background_refresh import E7BackgroundShopRefresh
        transport = mock.Mock()
        frame = Image.new('RGB', (1920, 1080), (60, 60, 60)); frame.paste((200, 160, 80), (100, 100, 900, 600))
        transport.screenshot.return_value = frame
        app = E7BackgroundShopRefresh(transport=transport, dry_run=True, budget=12, tap_sleep=.3,
                                      stop_refresh_key='`', random_offset=False)
        return app, transport

    def test_navigation_clicks_pass_and_spending_clicks_are_never_sent(self):
        from e7_background_refresh import DryRunSkip
        app, transport = self.make()
        app._tap_observed(79, 498, action='open shop')
        app._tap_observed(960, 540, action='reveal home controls')
        self.assertEqual(transport.click.call_count, 2)
        for action in ('buy', 'refresh', 'buy confirm', 'refresh confirm', 'calibration buy', 'navigation'):
            with mock.patch('builtins.print'), self.assertRaises(DryRunSkip):
                app._tap_observed(1700, 460, action=action)
        with self.assertRaisesRegex(MouseStopped, 'blocked'):
            app.tap(1700, 460)
        self.assertEqual(transport.click.call_count, 2)

    def test_buy_is_skipped_and_refresh_ends_the_run(self):
        from e7_background_refresh import DryRunSkip
        from e7_mouse_refresh import E7MouseShopRefresh
        app, transport = self.make()
        with mock.patch.object(E7MouseShopRefresh, 'clickBuy', side_effect=DryRunSkip('buy')), mock.patch('builtins.print'):
            self.assertFalse(app.clickBuy((1700, 460)))
        with mock.patch.object(E7MouseShopRefresh, 'clickRefresh', side_effect=DryRunSkip('refresh')):
            with self.assertRaisesRegex(MouseStopped, 'nothing was spent'):
                app.clickRefresh()
        transport.click.assert_not_called()

    def test_dry_run_writes_no_session_history(self):
        app, _ = self.make()
        with mock.patch.object(app.storage, 'writeToCSV') as write:
            app.record_session('failed', 'Dry run complete')
        write.assert_not_called()
        self.assertEqual(app._session_metadata['Control mode'], 'Background (dry run)')


if __name__ == '__main__':
    unittest.main()
