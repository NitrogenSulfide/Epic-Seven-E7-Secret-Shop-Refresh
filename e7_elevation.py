"""User-approved GUI restart through Windows UAC; never starts a game session."""
import ctypes
from ctypes import wintypes as w
from pathlib import Path
import subprocess
import sys


class ElevationCancelled(OSError):
    """The user declined the Windows administrator prompt."""


class ShellExecuteInfo(ctypes.Structure):
    _fields_ = [
        ('cbSize', w.DWORD), ('fMask', w.ULONG), ('hwnd', w.HWND),
        ('lpVerb', w.LPCWSTR), ('lpFile', w.LPCWSTR),
        ('lpParameters', w.LPCWSTR), ('lpDirectory', w.LPCWSTR),
        ('nShow', ctypes.c_int), ('hInstApp', w.HINSTANCE),
        ('lpIDList', w.LPVOID), ('lpClass', w.LPCWSTR),
        ('hkeyClass', w.HKEY), ('dwHotKey', w.DWORD),
        ('hIcon', w.HANDLE), ('hProcess', w.HANDLE),
    ]


def restart_command(engine_directory, *, executable=None, frozen=None, script=None):
    """Explicit paths only: do not replay session/verification CLI arguments."""
    executable = Path(executable or sys.executable).resolve()
    frozen = getattr(sys, 'frozen', False) if frozen is None else frozen
    arguments = []
    if not frozen:
        script = Path(script or Path(__file__).with_name('e7_shop_refresh_gui.py')).resolve()
        windowed_python = executable.with_name('pythonw.exe')
        if windowed_python.is_file():
            executable = windowed_python
        arguments.append(str(script))
        directory = script.parent
    else:
        directory = executable.parent
    arguments += ['--engine-dir', str(Path(engine_directory).resolve())]
    return str(executable), subprocess.list2cmdline(arguments), str(directory)


def restart_as_administrator(engine_directory, *, parent=None, shell=None, kernel=None,
                             last_error=None, command=None):
    """Request runas, raising on cancellation/failure. Close our process handle."""
    executable, parameters, directory = command or restart_command(engine_directory)
    shell = shell or ctypes.WinDLL('shell32', use_last_error=True)
    kernel = kernel or ctypes.WinDLL('kernel32', use_last_error=True)
    last_error = last_error or ctypes.get_last_error
    shell.ShellExecuteExW.argtypes = [ctypes.POINTER(ShellExecuteInfo)]
    shell.ShellExecuteExW.restype = w.BOOL
    kernel.CloseHandle.argtypes = [w.HANDLE]
    kernel.CloseHandle.restype = w.BOOL
    info = ShellExecuteInfo()
    info.cbSize = ctypes.sizeof(info)
    # Keep a process handle for cleanup; complete the launch before returning.
    # NO_UI suppresses redundant launch-error boxes, not Windows' UAC prompt.
    info.fMask = 0x40 | 0x100 | 0x400
    info.hwnd = parent
    info.lpVerb = 'runas'
    info.lpFile = executable
    info.lpParameters = parameters
    info.lpDirectory = directory
    info.nShow = 1
    if not shell.ShellExecuteExW(ctypes.byref(info)):
        error = last_error()
        if error == 1223:
            raise ElevationCancelled('Administrator prompt cancelled. No Mouse input sent.')
        raise OSError(error, 'Windows could not restart the app as administrator.')
    if info.hProcess:
        kernel.CloseHandle(info.hProcess)
