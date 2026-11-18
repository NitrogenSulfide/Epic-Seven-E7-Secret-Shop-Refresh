import sys
import unittest
from unittest import mock

import e7_macos_stop_key as sk


class FakeTap:
    def __init__(self, *, fail=None):
        self.handler = None
        self.started = self.stopped = False
        self.down = set()
        self.problem = None
        self.fail = fail

    def start(self, handler):
        if self.fail:
            raise ValueError(self.fail)
        self.handler, self.started = handler, True

    def error(self):
        return self.problem

    def held(self, code):
        return code in self.down

    def stop(self):
        self.stopped = True


class KeyNameTest(unittest.TestCase):
    def test_supported_keys(self):
        self.assertEqual(sk.mac_stop_key('esc'), (None, sk.ESCAPE))
        self.assertEqual(sk.mac_stop_key('`'), ('`', 50))
        self.assertEqual(sk.mac_stop_key('Q'), ('q', 12))

    def test_every_gui_character_is_supported(self):
        from e7_shop_refresh_gui import STOP_KEY_CHARACTERS
        for character in STOP_KEY_CHARACTERS:
            self.assertEqual(sk.mac_stop_key(character)[0], character)

    def test_unsupported_keys_refuse(self):
        for key in ('', 'f1', 'ctrl+q', '\\', 'space'):
            with self.assertRaises(ValueError):
                sk.mac_stop_key(key)


class StopKeyTest(unittest.TestCase):
    def test_typed_character_stops(self):
        tap = FakeTap()
        with sk.MacStopKey('`', tap=tap) as monitor:
            self.assertFalse(monitor.pressed())
            tap.handler(12, 'q')                 # another key
            self.assertFalse(monitor.pressed())
            tap.handler(50, '`')
            self.assertTrue(monitor.pressed())
            self.assertEqual(monitor.detected_by, 'keyboard event')
        self.assertTrue(tap.stopped)

    def test_layout_is_followed_by_character_not_key_code(self):
        # On AZERTY the key at US 'q' types 'a': only the typed character counts.
        tap = FakeTap()
        with sk.MacStopKey('a', tap=tap) as monitor:
            tap.handler(12, 'a')
            self.assertTrue(monitor.pressed())

    def test_escape_is_matched_by_key_code(self):
        tap = FakeTap()
        with sk.MacStopKey('esc', tap=tap) as monitor:
            tap.handler(sk.ESCAPE, '\x1b')
            self.assertTrue(monitor.pressed())

    def test_key_already_held_stops(self):
        tap = FakeTap()
        tap.down.add(50)
        with sk.MacStopKey('`', tap=tap) as monitor:
            self.assertTrue(monitor.pressed())
            self.assertEqual(monitor.detected_by, 'held key state')

    def test_listener_failure_stops_the_session(self):
        tap = FakeTap()
        with sk.MacStopKey('`', tap=tap) as monitor:
            tap.problem = 'the listener stopped'
            with self.assertRaisesRegex(ValueError, 'Stop key listener failed'):
                monitor.pressed()

    def test_missing_permission_refuses_to_start(self):
        tap = FakeTap(fail='macOS has not granted Input Monitoring')
        with self.assertRaisesRegex(ValueError, 'Input Monitoring'):
            with sk.MacStopKey('`', tap=tap):
                pass

    def test_engine_picks_the_mac_stop_key_on_macos(self):
        import e7_stop_key
        with mock.patch.object(e7_stop_key.sys, 'platform', 'darwin'), \
                mock.patch.object(e7_stop_key.os, 'name', 'posix'), \
                mock.patch('e7_macos_stop_key.QuartzKeyTap', FakeTap):
            monitor = e7_stop_key.stop_key_monitor('`')
        self.assertIsInstance(monitor, sk.MacStopKey)


@unittest.skipUnless(sys.platform == 'darwin', 'needs macOS')
class RealTapSmokeTest(unittest.TestCase):
    def test_tap_starts_and_stops_when_allowed(self):
        import Quartz
        if not getattr(Quartz, 'CGPreflightListenEventAccess', lambda: False)():
            self.skipTest('Input Monitoring not allowed for this process')
        with sk.MacStopKey('`') as monitor:
            self.assertFalse(monitor.pressed())


if __name__ == '__main__':
    unittest.main()
