import subprocess
import unittest
from unittest.mock import Mock
from e7_connection import check_connection


def response(output='', error='', code=0):
    return subprocess.CompletedProcess([], code, output, error)


class ConnectionTests(unittest.TestCase):
    def test_scan_counts_only_authorized_online_devices_and_never_connects(self):
        runner = Mock(return_value=response('List of devices attached\na\tdevice\nb\toffline\nc\tunauthorized\na\tdevice\n'))
        result = check_connection('adb.exe', '.', runner=runner)
        self.assertEqual(result.devices, ('a',))
        self.assertEqual(result.warning, '')
        self.assertEqual(runner.call_count, 1)
        self.assertEqual(runner.call_args.args[0], ['adb.exe', 'devices'])

    def test_start_checks_exact_selected_device_without_connect_if_present(self):
        runner = Mock(return_value=response('List of devices attached\nlocalhost:6520\tdevice\n'))
        result = check_connection('adb.exe', '.', 'localhost:6520', runner=runner)
        self.assertTrue(result.ready)
        self.assertEqual(runner.call_count, 1)

    def test_manual_endpoint_connect_then_verify_actual_device_state(self):
        runner = Mock(side_effect=[response('List of devices attached\n'),
                                  response('connected to localhost:6520'),
                                  response('List of devices attached\nlocalhost:6520\tdevice\n')])
        result = check_connection('adb.exe', '.', 'localhost:6520', runner=runner)
        self.assertTrue(result.ready)
        self.assertEqual([c.args[0][1:] for c in runner.call_args_list],
                         [['devices'], ['connect', 'localhost:6520'], ['devices']])
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


if __name__ == '__main__':
    unittest.main()
