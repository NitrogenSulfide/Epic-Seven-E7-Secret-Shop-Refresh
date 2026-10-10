"""Bounded ADB connection checks. No screenshots, input, or server shutdowns."""
from dataclasses import dataclass
import subprocess
import os
import re
from pathlib import Path

NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


@dataclass(frozen=True)
class AdbEndpoint:
    name: str
    address: str


def endpoint_key(address):
    """Deduplicate loopback spellings without changing other device serials."""
    match = re.fullmatch(r'(?:localhost|127\.0\.0\.1):(\d+)', address)
    return '127.0.0.1:' + match[1] if match else address


def bluestacks_endpoints(config, titles):
    """Only suggest enabled instances whose named player window is open."""
    values = dict(re.findall(r'^([^=\r\n]+)="([^"\r\n]*)"\s*$', config, re.M))
    if values.get('bst.enable_adb_access') != '1':
        return ()
    endpoints = []
    for key, name in values.items():
        match = re.fullmatch(r'bst\.instance\.([^.]+)\.display_name', key)
        if not match or name not in titles:
            continue
        prefix = 'bst.instance.' + match[1] + '.'
        if values.get(prefix + 'enable_adb_access', '1') != '1':
            continue
        # status.adb_port is the running instance's port; adb_port can still
        # say 5555 for several instances. Do not fall back from invalid status.
        port = values.get(prefix + 'status.adb_port', values.get(prefix + 'adb_port', ''))
        if port.isascii() and port.isdigit() and 1 <= int(port) <= 65535:
            endpoints.append(AdbEndpoint(name, f'127.0.0.1:{int(port)}'))
    return tuple(dict.fromkeys(endpoints))


def visible_window_titles():
    """Read titles without activating windows or accessing process tokens."""
    if os.name != 'nt':
        return ()
    import ctypes
    from ctypes import wintypes as w
    user = ctypes.WinDLL('user32', use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    user.EnumWindows.argtypes = [callback_type, w.LPARAM]
    user.EnumWindows.restype = w.BOOL
    user.IsWindowVisible.argtypes = [w.HWND]
    user.IsWindowVisible.restype = w.BOOL
    user.GetWindowTextLengthW.argtypes = [w.HWND]
    user.GetWindowTextLengthW.restype = ctypes.c_int
    user.GetWindowTextW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
    titles = []
    @callback_type
    def visit(window, _):
        if user.IsWindowVisible(window):
            title = ctypes.create_unicode_buffer(user.GetWindowTextLengthW(window) + 1)
            user.GetWindowTextW(window, title, len(title))
            titles.append(title.value)
        return True
    return tuple(titles) if user.EnumWindows(visit, 0) else ()


def discover_bluestacks_endpoints():
    """Read local BlueStacks configuration only; never issue adb connect."""
    if os.name != 'nt':
        return ()
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\BlueStacks_nxt') as key:
            directory = winreg.QueryValueEx(key, 'UserDefinedDir')[0]
        path = Path(directory) / 'bluestacks.conf'
        with path.open(encoding='utf-8-sig') as stream:
            config = stream.read(1024 * 1024 + 1)
        if len(config) > 1024 * 1024:
            return ()
        return bluestacks_endpoints(config, visible_window_titles())
    except (OSError, ValueError, TypeError, UnicodeError):
        return ()


@dataclass(frozen=True)
class ConnectionCheck:
    devices: tuple[str, ...]
    warning: str
    diagnostics: str
    ready: bool = False
    endpoints: tuple[AdbEndpoint, ...] = ()


def epic_seven_resumed(text):
    """Use current activity records, never an installed/history package match."""
    top = [line for line in text.splitlines() if re.search(r'\btopResumedActivity\s*=', line)]
    resumed = top or [line for line in text.splitlines() if re.search(r'\bmResumedActivity\s*[:=]', line)]
    return any(re.search(r'\bcom\.stove\.epic7(?:\.[A-Za-z0-9_]+)*/', line) for line in resumed)


def google_play_window_open():
    """Read window visibility without focusing, restoring or closing anything."""
    if os.name != 'nt':
        return None
    import ctypes
    from ctypes import wintypes as w
    user = ctypes.WinDLL('user32', use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    user.EnumWindows.argtypes = [callback_type, w.LPARAM]
    user.EnumWindows.restype = w.BOOL
    user.IsWindowVisible.argtypes = [w.HWND]
    user.IsWindowVisible.restype = w.BOOL
    user.GetWindowTextLengthW.argtypes = [w.HWND]
    user.GetWindowTextLengthW.restype = ctypes.c_int
    user.GetWindowTextW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
    found = False
    @callback_type
    def visit(window, _):
        nonlocal found
        if user.IsWindowVisible(window):
            title = ctypes.create_unicode_buffer(user.GetWindowTextLengthW(window) + 1)
            user.GetWindowTextW(window, title, len(title))
            if 'google play games' in title.value.lower():
                found = True
        return True
    return found if user.EnumWindows(visit, 0) else None


def check_connection(adb, runtime, target=None, *, runner=None, window_probe=None, endpoint_probe=None):
    runner = runner or subprocess.run
    output = []
    endpoints = tuple((endpoint_probe or discover_bluestacks_endpoints)())

    def report(devices, warning, diagnostics, ready=False):
        return ConnectionCheck(devices, warning, diagnostics, ready, endpoints)

    def run(*args):
        result = runner([str(adb), *args], cwd=runtime, capture_output=True,
                        text=True, errors='replace', timeout=5, creationflags=NO_WINDOW)
        output.append(result.stdout + result.stderr)
        return result

    def devices(result):
        return tuple(dict.fromkeys(parts[0] for line in result.stdout.splitlines()
                                  if len(parts := line.split()) >= 2 and parts[1] == 'device'))

    try:
        result = run('devices', '-l')
        if result.returncode:
            return report((), 'ADB check failed. Open your emulator with ADB enabled, then retry.', ''.join(output))
        connected = devices(result)
        # Only an explicit Start attempts the selected network endpoint. Scans
        # never connect, choose other devices, or kill an existing ADB server.
        if target and target not in connected and ':' in target and not target.startswith('-'):
            run('connect', target)
            result = run('devices', '-l')
            connected = devices(result) if result.returncode == 0 else ()
        if target and target not in connected:
            warning = 'Selected emulator is not connected. Open it, enable/authorize ADB, then press Start again.'
        elif not connected:
            warning = ('BlueStacks detected. Select its named endpoint, then press Start to connect.' if endpoints else
                       'No connected emulator detected. Open your emulator with ADB enabled, then press Start.')
        else:
            warning = ''
        if warning:
            return report(connected, warning, ''.join(output))
        available = {endpoint_key(address) for address in connected} | {endpoint_key(endpoint.address) for endpoint in endpoints}
        selected = target or (connected[0] if len(available) == 1 else None)
        if selected is None:
            return report(connected, '', ''.join(output))
        google_device = any(line.split() and line.split()[0] == selected and
                            'model:HPE_device' in line for line in result.stdout.splitlines())
        if google_device:
            visible = (window_probe or google_play_window_open)()
            if visible is not True:
                warning = ('Emulator connected in the background. Open its window and Epic Seven, then press Start.'
                           if visible is False else 'Could not verify the Google Play Games window. Open it and retry.')
                return report(connected, warning, ''.join(output))
        activity = run('-s', selected, 'shell', 'dumpsys', 'activity', 'activities')
        # Activity dumps can contain unrelated app history. Do not store them in
        # Diagnostics; only retain the minimal result of this read-only check.
        output.pop()
        if activity.returncode or not epic_seven_resumed(activity.stdout):
            warning = 'Emulator connected, but Epic Seven is not active. Open Epic Seven in it, then press Start.'
            return report(connected, warning, ''.join(output))
        return report(connected, '', ''.join(output), bool(target))
    except (OSError, subprocess.SubprocessError):
        return report((), 'Could not reach ADB. Open your emulator, enable/authorize ADB, then retry.', ''.join(output))
