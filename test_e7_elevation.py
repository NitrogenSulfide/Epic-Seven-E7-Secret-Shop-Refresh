import ctypes
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock

from e7_elevation import (ElevationCancelled, ShellExecuteInfo,
                          restart_as_administrator, restart_command)


class ElevationTests(unittest.TestCase):
    def test_frozen_restart_uses_same_exe_and_explicit_runtime_only(self):
        with tempfile.TemporaryDirectory(prefix='E7 日本語 ') as folder:
            executable = Path(folder) / 'E7 Secret Shop Refresh.exe'
            runtime = Path(folder) / 'runtime'
            command = restart_command(runtime, executable=executable, frozen=True)
            self.assertEqual(command, (str(executable.resolve()),
                subprocess.list2cmdline(['--engine-dir', str(runtime.resolve())]),
                str(executable.parent.resolve())))
            self.assertNotIn('--mouse-session', command[1])
            self.assertNotIn('--verify', command[1])

    def test_source_restart_prefers_adjacent_pythonw_and_quotes_script(self):
        with tempfile.TemporaryDirectory(prefix='E7 日本語 ') as folder:
            root = Path(folder)
            python = root / 'python.exe'
            script = root / 'source code' / 'e7_shop_refresh_gui.py'
            for windowed in (False, True):
                if windowed:
                    (root / 'pythonw.exe').touch()
                command = restart_command(root/'runtime', executable=python, frozen=False, script=script)
                self.assertEqual(command[0], str(root / ('pythonw.exe' if windowed else 'python.exe')))
                self.assertEqual(command[1], subprocess.list2cmdline(
                    [str(script), '--engine-dir', str(root/'runtime')]))
                self.assertEqual(command[2], str(script.parent))

    def launch(self, callback, error=0):
        shell, kernel = Mock(), Mock()
        shell.ShellExecuteExW.side_effect = callback
        restart_as_administrator('.', parent=987, shell=shell, kernel=kernel,
            last_error=lambda: error, command=('C:\\E7 app\\GUI.exe', '--engine-dir "C:\\E7 app\\runtime"', 'C:\\E7 app'))
        return shell, kernel

    def test_runas_uses_unicode_api_and_closes_owned_handle_without_wait_or_input(self):
        def execute(pointer):
            info = ctypes.cast(pointer, ctypes.POINTER(ShellExecuteInfo)).contents
            self.assertEqual(info.cbSize, ctypes.sizeof(ShellExecuteInfo))
            self.assertEqual(info.lpVerb, 'runas')
            self.assertEqual(info.hwnd, 987)
            self.assertEqual(info.lpFile, 'C:\\E7 app\\GUI.exe')
            self.assertEqual(info.lpDirectory, 'C:\\E7 app')
            self.assertEqual(info.lpParameters, '--engine-dir "C:\\E7 app\\runtime"')
            self.assertEqual(info.nShow, 1)
            self.assertEqual(info.fMask, 0x540)
            info.hProcess = 123
            return True
        shell, kernel = self.launch(execute)
        shell.ShellExecuteExW.assert_called_once()
        kernel.CloseHandle.assert_called_once_with(123)
        self.assertEqual([call[0] for call in kernel.method_calls], ['CloseHandle'])

    def test_success_without_process_handle_does_not_close_an_unowned_handle(self):
        _, kernel = self.launch(lambda _: True)
        kernel.CloseHandle.assert_not_called()

    def test_uac_cancellation_is_distinct_from_a_failed_launch(self):
        with self.assertRaises(ElevationCancelled):
            self.launch(lambda _: False, 1223)
        with self.assertRaises(OSError) as result:
            self.launch(lambda _: False, 2)
        self.assertNotIsInstance(result.exception, ElevationCancelled)
        self.assertEqual(result.exception.errno, 2)


if __name__ == '__main__':
    unittest.main()
