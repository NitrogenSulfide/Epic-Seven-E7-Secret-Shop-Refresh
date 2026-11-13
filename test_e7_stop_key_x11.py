import os
import shutil
import subprocess
import time
import unittest
from unittest.mock import patch

from e7_stop_key import x11_stop_key, stop_key_monitor


class X11KeyNameTests(unittest.TestCase):
    def test_gui_keys_map_to_keysyms(self):
        self.assertEqual(x11_stop_key('`'), ('grave', []))
        self.assertEqual(x11_stop_key('esc'), ('Escape', []))
        self.assertEqual(x11_stop_key('f9'), ('F9', []))
        self.assertEqual(x11_stop_key('a'), ('a', []))
        self.assertEqual(x11_stop_key("'"), ('apostrophe', []))
        self.assertEqual(x11_stop_key('ctrl+page down'), ('Next', [('Control_L', 'Control_R')]))

    def test_unknown_keys_are_refused(self):
        for key in ('hyper+a', 'nosuchkey', 'é'):
            with self.assertRaises(ValueError):
                x11_stop_key(key)

    @unittest.skipIf(os.name == 'nt', 'Linux only')
    def test_no_display_is_refused(self):
        env = {k: v for k, v in os.environ.items() if k not in ('DISPLAY', 'WAYLAND_DISPLAY', 'XDG_SESSION_TYPE')}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(ValueError, 'DISPLAY'):
                stop_key_monitor('`')


    @unittest.skipIf(os.name == 'nt', 'Linux only')
    def test_wayland_session_is_refused(self):
        for env in ({'WAYLAND_DISPLAY': 'wayland-0'}, {'XDG_SESSION_TYPE': 'wayland'}):
            with self.subTest(env=env), patch.dict(os.environ, {'DISPLAY': ':0', **env}):
                with self.assertRaisesRegex(ValueError, 'Wayland'):
                    stop_key_monitor('`')


@unittest.skipUnless(os.name != 'nt' and shutil.which('Xvfb'), 'needs Xvfb')
class X11StopKeyLiveTests(unittest.TestCase):
    """Runs against a private Xvfb started here, never the user's display."""

    def setUp(self):
        from Xlib import display
        read, write = os.pipe()
        self.server = subprocess.Popen(['Xvfb', '-displayfd', str(write), '-nolisten', 'tcp', '-screen', '0', '320x240x24'],
                                       pass_fds=(write,), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.close(write)
        with os.fdopen(read) as stream:
            self.name = ':'+stream.readline().strip()
        self.open = lambda: display.Display(self.name)
        self.typist = self.open()

    def tearDown(self):
        self.typist.close()
        self.server.terminate(); self.server.wait(5)

    def type(self, *names, release_last=True):
        from Xlib import X, XK
        from Xlib.ext import xtest
        codes = [self.typist.keysym_to_keycode(XK.string_to_keysym(n)) for n in names]
        for code in codes:
            xtest.fake_input(self.typist, X.KeyPress, code)
        for code in reversed(codes if release_last else codes[:-1]):
            xtest.fake_input(self.typist, X.KeyRelease, code)
        self.typist.sync()

    def wait(self, monitor, expected):
        deadline = time.monotonic()+2
        while time.monotonic() < deadline:
            if monitor.pressed() == expected and expected:
                return True
            time.sleep(.02)
        return monitor.pressed()

    def monitor(self, key):
        from e7_stop_key import X11StopKey
        return X11StopKey(key, display=self.open)

    def test_brief_injected_press_is_latched_after_release(self):
        with self.monitor('`') as monitor:
            self.assertFalse(monitor.pressed())
            self.type('grave')
            self.assertTrue(self.wait(monitor, True))
            self.assertEqual(monitor.detected_by, 'keyboard event')

    def test_other_keys_and_bare_chord_key_do_not_stop(self):
        with self.monitor('ctrl+f9') as monitor:
            self.type('a'); self.type('F9')
            time.sleep(.2)
            self.assertFalse(monitor.pressed())
            self.type('Control_R', 'F9')
            self.assertTrue(self.wait(monitor, True))

    def test_held_key_is_seen_before_listener_events(self):
        self.type('Escape', release_last=False)
        with self.monitor('esc') as monitor:
            self.assertTrue(monitor.pressed())
            self.assertEqual(monitor.detected_by, 'held key state')
        self.type('Escape')

    def test_exit_stops_the_listener(self):
        monitor = self.monitor('`')
        with monitor:
            thread = monitor.thread
        self.assertFalse(thread.is_alive())
        self.assertIsNone(monitor.control)


if __name__ == '__main__':
    unittest.main()
