import subprocess
import unittest
from unittest.mock import Mock
from e7_connection import check_connection, epic_seven_resumed

GAME = 'topResumedActivity=ActivityRecord{a1 u0 com.stove.epic7.google/.MainActivity t1}'
LAUNCHER = 'topResumedActivity=ActivityRecord{a2 u0 com.android.launcher3/.Launcher t2}'


def response(output='', error='', code=0):
    return subprocess.CompletedProcess([], code, output, error)


class ConnectionTests(unittest.TestCase):
    def test_scan_counts_only_authorized_online_devices_and_never_connects(self):
        runner = Mock(side_effect=[response('List of devices attached\na\tdevice\nb\toffline\nc\tunauthorized\na\tdevice\n'), response(GAME)])
        result = check_connection('adb.exe', '.', runner=runner)
        self.assertEqual(result.devices, ('a',))
        self.assertEqual(result.warning, '')
        self.assertEqual(runner.call_count, 2)
        self.assertEqual(runner.call_args_list[0].args[0], ['adb.exe', 'devices', '-l'])
        self.assertNotIn('connect', [argument for call in runner.call_args_list for argument in call.args[0]])

    def test_start_checks_exact_selected_device_without_connect_if_present(self):
        runner = Mock(side_effect=[response('List of devices attached\nlocalhost:6520\tdevice\n'), response(GAME)])
        result = check_connection('adb.exe', '.', 'localhost:6520', runner=runner)
        self.assertTrue(result.ready)
        self.assertEqual(runner.call_count, 2)

    def test_manual_endpoint_connect_then_verify_actual_device_state(self):
        runner = Mock(side_effect=[response('List of devices attached\n'),
                                  response('connected to localhost:6520'),
                                  response('List of devices attached\nlocalhost:6520\tdevice\n'), response(GAME)])
        result = check_connection('adb.exe', '.', 'localhost:6520', runner=runner)
        self.assertTrue(result.ready)
        self.assertEqual([c.args[0][1:] for c in runner.call_args_list],
                         [['devices', '-l'], ['connect', 'localhost:6520'], ['devices', '-l'],
                          ['-s', 'localhost:6520', 'shell', 'dumpsys', 'activity', 'activities']])
        self.assertTrue(all(c.kwargs['timeout'] == 5 for c in runner.call_args_list))

    def test_connect_message_cannot_override_offline_or_unauthorized_state(self):
        for state in ('offline', 'unauthorized'):
            runner = Mock(side_effect=[response(), response('already connected'),
                                      response(f'List of devices attached\nlocalhost:6520\t{state}\n')])
            result = check_connection('adb.exe', '.', 'localhost:6520', runner=runner)
            self.assertFalse(result.ready)
            self.assertIn('enable/authorize ADB', result.warning)

    def test_other_emulator_is_not_used_instead_of_selected_device(self):
        runner = Mock(return_value=response('List of devices attached\nother-device\tdevice\n'))
        result = check_connection('adb.exe', '.', 'selected-device', runner=runner)
        self.assertFalse(result.ready)
        self.assertEqual(result.devices, ('other-device',))
        self.assertEqual(runner.call_count, 1)

    def test_no_device_scan_and_adb_errors_are_actionable(self):
        self.assertIn('No connected emulator', check_connection('adb', '.', runner=Mock(return_value=response())).warning)
        for result in (response(code=1),):
            self.assertFalse(check_connection('adb', '.', 'localhost:6520', runner=Mock(return_value=result)).ready)
        for error in (OSError('missing'), subprocess.TimeoutExpired('adb', 5)):
            result = check_connection('adb', '.', 'localhost:6520', runner=Mock(side_effect=error))
            self.assertFalse(result.ready)
            self.assertIn('ADB', result.warning)

    def test_connected_google_vm_without_window_is_not_ready(self):
        runner = Mock(return_value=response('List of devices attached\nlocalhost:6520 device model:HPE_device\n'))
        for target in (None, 'localhost:6520'):
            result = check_connection('adb', '.', target, runner=runner, window_probe=lambda:False)
            self.assertEqual(result.devices, ('localhost:6520',))
            self.assertFalse(result.ready)
            self.assertIn('background', result.warning)
        self.assertEqual(runner.call_count, 2)

    def test_visible_google_window_and_current_game_are_both_required(self):
        listing = response('List of devices attached\nlocalhost:6520 device model:HPE_device\n')
        for active, expected in ((GAME, True), (LAUNCHER, False)):
            runner = Mock(side_effect=[listing, response(active)])
            result = check_connection('adb', '.', 'localhost:6520', runner=runner, window_probe=lambda:True)
            self.assertEqual(result.ready, expected)
            self.assertNotIn(active, result.diagnostics)
            if not expected:
                self.assertIn('Epic Seven is not active', result.warning)

    def test_installed_or_previous_game_cannot_satisfy_current_activity(self):
        for text in (GAME.replace('topResumedActivity', 'Hist #0'), LAUNCHER + '\n' + GAME.replace('topResumedActivity', 'Hist #1'),
                     'topResumedActivity=null\nmResumedActivity=' + GAME.split('=',1)[1]):
            self.assertFalse(epic_seven_resumed(text))
        self.assertTrue(epic_seven_resumed(GAME))
        self.assertTrue(epic_seven_resumed(GAME.replace('topResumedActivity=', 'mResumedActivity: ')))

    def test_unknown_window_and_activity_errors_fail_without_spending(self):
        runner = Mock(return_value=response('localhost:6520 device model:HPE_device\n'))
        result = check_connection('adb', '.', 'localhost:6520', runner=runner, window_probe=lambda:None)
        self.assertFalse(result.ready)
        self.assertIn('Could not verify', result.warning)
        runner = Mock(side_effect=[response('localhost:6520 device\n'), response(GAME, code=1)])
        result = check_connection('adb', '.', 'localhost:6520', runner=runner)
        self.assertFalse(result.ready)

    def test_other_emulators_do_not_use_google_window_title_check(self):
        runner = Mock(side_effect=[response('other-device device model:OtherEmulator\n'), response(GAME)])
        probe = Mock(return_value=False)
        result = check_connection('adb', '.', 'other-device', runner=runner, window_probe=probe)
        self.assertTrue(result.ready)
        probe.assert_not_called()


if __name__ == '__main__':
    unittest.main()
