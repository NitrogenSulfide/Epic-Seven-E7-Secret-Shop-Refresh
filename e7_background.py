"""Background control of Epic Seven on Steam (Linux/Proton and Windows) and STOVE (Windows).

Input is posted as window messages by e7_wine_input.exe, so the real pointer
and keyboard focus are never used. On Linux the helper runs inside the game's
Wine session and capture reads the game's own X window. On Windows the helper
runs directly and capture uses PrintWindow; both need administrator rights
because the game runs elevated. Other windows may cover the game. The
transport mirrors WindowsMouse (screenshot/click/move/drag in 1920 x 1080
game space).
"""
from dataclasses import dataclass, field
import json
import math
import os
from pathlib import Path
import queue
import select
import subprocess
import sys
import threading
import time

from e7_native_mouse import MouseStopped, MouseRecheckRequired
from e7_windows_capture import game_view

STEAM_APP_ID = 5019180
GAME_TITLE = 'Epic Seven'
HELPER_NAME = 'e7_wine_input.exe'
# Windows game processes Background accepts, by client. Both draw the same
# GLFW 'Epic Seven' window (checked with STOVE on 2026-11-13).
WINDOWS_GAME_EXES = {'epicseven_steam.exe': 'Steam', 'epicseven.exe': 'STOVE'}
PAUSE_LIMIT = 10


@dataclass(frozen=True)
class ProtonSession:
    """The running game's Wine session, read from its wineserver process."""
    wine: Path
    prefix: Path
    env: dict = field(default_factory=dict)

    def environment(self):
        files = self.wine.parent.parent
        result = dict(os.environ)
        result.update(self.env)
        result['WINEPREFIX'] = str(self.prefix)
        result['WINEDEBUG'] = '-all'
        libs = [str(files/name) for name in ('lib', 'lib64') if (files/name).is_dir()]
        if os.environ.get('LD_LIBRARY_PATH'):
            libs.append(os.environ['LD_LIBRARY_PATH'])
        result['LD_LIBRARY_PATH'] = ':'.join(libs)
        return result


def _read_environ(pid, proc):
    raw = (proc/str(pid)/'environ').read_bytes()
    pairs = (item.split(b'=', 1) for item in raw.split(b'\0') if b'=' in item)
    return {key.decode(errors='replace'): value.decode(errors='replace') for key, value in pairs}


def find_proton_session(app_id=STEAM_APP_ID, *, proc=Path('/proc')):
    """Locate the game's wineserver and the Proton build that started it."""
    marker = f'compatdata/{app_id}'
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            exe = Path(os.readlink(entry/'exe'))
            if exe.name != 'wineserver':
                continue
            env = _read_environ(entry.name, proc)
        except OSError:
            continue
        prefix = env.get('WINEPREFIX', '')
        if marker not in prefix and marker not in env.get('STEAM_COMPAT_DATA_PATH', ''):
            continue
        wine = exe.with_name('wine')
        if not wine.exists():
            raise ValueError(f'The game is running, but its Proton build has no wine program at {wine}.')
        keep = {key: env[key] for key in ('WINEFSYNC', 'WINEESYNC', 'WINE_LARGE_ADDRESS_AWARE') if key in env}
        return ProtonSession(wine, Path(prefix.rstrip('/')), keep)
    raise ValueError('Epic Seven (Steam) is not running. Start the game, then try again.')


def helper_path():
    configured = os.environ.get('E7_WINE_INPUT')
    # A frozen engine EXE ships the helper beside itself, not inside its bundle.
    base = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
    path = Path(configured) if configured else base/HELPER_NAME
    if not path.is_file():
        fix = 'Use the complete player folder.' if os.name == 'nt' else 'Build it with build_wine_input.sh.'
        raise ValueError(f'The background input helper is missing: {path}. {fix}')
    return path


class WineInput:
    """Persistent e7_wine_input.exe: inside the game's Wine session on Linux
    (session given), or run directly on Windows (session None)."""

    # Windows cannot select() on pipes; there one reader thread feeds a queue.
    _use_select = os.name != 'nt'

    def __init__(self, session, *, helper=None, timeout=10, popen=subprocess.Popen):
        self.timeout = timeout
        self._replies = None
        command = [str(helper or helper_path())]
        options = dict(stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
        if session is not None:
            command.insert(0, str(session.wine))
            options['env'] = session.environment()
        else:
            options['creationflags'] = 0x08000000  # CREATE_NO_WINDOW
        self.process = popen(command, **options)

    def _readline(self, timeout):
        if self._use_select:
            ready, _, _ = select.select([self.process.stdout], [], [], timeout)
            return self.process.stdout.readline() if ready else None
        if self._replies is None:
            self._replies = queue.Queue()
            def pump(stream=self.process.stdout, replies=self._replies):
                for line in stream:
                    replies.put(line)
                replies.put('')
            threading.Thread(target=pump, name='E7 input helper', daemon=True).start()
        try:
            return self._replies.get(timeout=timeout)
        except queue.Empty:
            return None

    def request(self, command, *, timeout=None):
        if self.process.poll() is not None:
            raise MouseStopped('The background input helper exited. No input sent.')
        self.process.stdin.write(command+'\n')
        self.process.stdin.flush()
        reply = self._readline(timeout or self.timeout)
        if reply is None:
            # A late answer would desynchronize later requests; stop the helper.
            self.process.kill()
            raise MouseStopped(f'The background input helper did not answer "{command.split()[0]}".')
        reply = reply.strip()
        if not reply:
            raise MouseStopped('The background input helper exited. No input sent.')
        if reply.startswith('err '):
            raise MouseStopped(f'Background input refused: {reply[4:]}.')
        return reply

    def find(self):
        # First start of wine in the session can take several seconds.
        reply = self.request('find', timeout=max(self.timeout, 30))
        kind, handle, width, height = reply.split()
        if kind != 'window':
            raise MouseStopped('Unexpected answer from the background input helper.')
        return int(handle), int(width), int(height)

    def close(self):
        if self.process.poll() is None:
            try:
                self.request('release', timeout=2)
                self.process.stdin.write('quit\n'); self.process.stdin.flush()
                self.process.wait(timeout=3)
            except (MouseStopped, OSError, ValueError, subprocess.TimeoutExpired):
                self.process.kill()


class XGameWindow:
    """The game's X11 window: capture, state and real-pointer checks."""

    def __init__(self, app_id=STEAM_APP_ID, *, display=None):
        from Xlib import display as xdisplay
        self.display = display or xdisplay.Display()
        self.root = self.display.screen().root
        self.app_class = f'steam_app_{app_id}'
        self.window = self._find()
        self.frame = self._top_level(self.window)

    def _find(self):
        stack, found = [self.root], []
        while stack:
            window = stack.pop()
            try:
                cls = window.get_wm_class() or ()
                if self.app_class in cls and window.get_wm_name() == GAME_TITLE:
                    found.append(window)
                    continue
                stack.extend(window.query_tree().children)
            except Exception:
                continue
        if not found:
            raise ValueError('The Epic Seven game window was not found on this X display.')
        if len(found) > 1:
            # Capture and input must reach the same game; refuse to guess.
            raise ValueError('More than one Epic Seven game window is open. Close the extra one, then try again.')
        return found[0]

    def _top_level(self, window):
        while True:
            parent = window.query_tree().parent
            if parent is None or parent.id == self.root.id:
                return window
            window = parent

    def size(self):
        geometry = self.window.get_geometry()
        return geometry.width, geometry.height

    def problem(self):
        """Return why input must wait, or None."""
        from Xlib import X
        try:
            attributes = self.window.get_attributes()
        except Exception:
            return 'The game window closed.'
        if attributes.map_state != X.IsViewable:
            return 'The game window is minimized or hidden.'
        pointer = self.root.query_pointer()
        if pointer.child and pointer.child.id == self.frame.id:
            return 'Move your mouse off the game window; background input pauses while the pointer is over it.'
        return None

    def capture(self):
        from PIL import Image
        from Xlib import X
        width, height = self.size()
        raw = self.window.get_image(0, 0, width, height, X.ZPixmap, 0xffffffff)
        return Image.frombytes('RGB', (width, height), raw.data, 'raw', 'BGRX')


class BackgroundGame:
    """WindowsMouse-compatible transport that never uses the real pointer."""

    native_stove = True

    def __init__(self, active, *, window=None, wine=None, session=None):
        self.active = active
        if os.name == 'nt':
            self.window = window or WinGameWindow()
            if wine is None:
                require_background_permissions(self.window.pid)
            self.wine = wine or WineInput(None)
        else:
            self.window = window or XGameWindow()
            self.wine = wine or WineInput(session or find_proton_session())
        handle, width, height = self.wine.find()
        expected = getattr(self.window, 'hwnd', None)
        if expected is not None and handle != expected:
            self.close()
            raise ValueError('The input helper found a different Epic Seven window than the one captured. '
                             'Close other copies of the game, then try again.')
        if (width, height) != self.window.size():
            self.close()
            raise ValueError(f'Wine reports a {width} x {height} game client but X reports '
                             f'{self.window.size()[0]} x {self.window.size()[1]}. Display scaling is not supported yet.')
        self.client = (width, height)
        # One plain line for reports: problems often depend on the window setup.
        describe = getattr(self.window, 'describe', None)
        extra = describe() if describe else ''
        print(f'Game window: {width} x {height}'+(f', {extra}' if extra else ''), flush=True)
        self.view = None
        self._view_bounds = None
        self.session_active = False
        self.pause_revision = 0

    def guard(self, *, action=False, point=None, held=False):
        deadline = None
        while True:
            active = self.active()
            self.session_active = self.session_active or active
            if (action or self.session_active) and not active:
                raise MouseStopped('Background session stopped.')
            if self.window.size() != self.client:
                raise MouseStopped('The game window was resized. Background session stopped.')
            problem = self.window.problem()
            if problem is None:
                if deadline is not None:
                    print('E7GUI_MOUSE_RESUMED', flush=True)
                    if action:
                        raise MouseRecheckRequired('The game paused before input. Rechecking the current screen before another action.')
                return
            if held:
                raise MouseStopped(problem+' Background session stopped during a held action.')
            if deadline is None:
                self.pause_revision += 1
                print('E7GUI_MOUSE_PAUSED '+json.dumps({'reason': problem}), flush=True)
                deadline = time.monotonic()+PAUSE_LIMIT
            if time.monotonic() >= deadline:
                raise MouseStopped(problem+f' No input sent while paused; it did not clear within {PAUSE_LIMIT} seconds.')
            time.sleep(.1)

    def screenshot(self):
        for _ in range(3):
            self.guard()
            revision = self.pause_revision
            image = self.window.capture().convert('RGB')
            self.guard()
            if revision == self.pause_revision:
                break
        else:
            raise MouseStopped('The game repeatedly paused during capture. No input sent.')
        if image.size != self.client or max(hi-lo for lo, hi in image.getextrema()) < 12:
            raise MouseStopped('The game capture is blank or has the wrong size. Background session stopped.')
        if self._view_bounds is None:
            image, self._view_bounds = game_view(image)
        else:
            image = image.crop(self._view_bounds)
        if self.view is not None and self.view != self._view_bounds:
            raise MouseStopped('The game viewport changed. Background session stopped.')
        self.view = self._view_bounds
        return image

    def _point(self, x, y):
        if self.view is None or not (0 <= x < 1920 and 0 <= y < 1080):
            raise MouseStopped('Invalid background target. No input sent.')
        left, top, right, bottom = self.view
        return round(left+x*(right-left)/1920), round(top+y*(bottom-top)/1080)

    def _trace(self, kind, point):
        print('E7GUI_MOUSE_INPUT '+json.dumps(dict(action=kind, target=list(point), pointer=None)), flush=True)

    def click(self, x, y):
        point = self._point(x, y)
        self.guard(action=True, point=point)
        self._trace('click', point)
        self.wine.request(f'click {point[0]} {point[1]}')
        return point

    def move(self, x, y):
        point = self._point(x, y)
        self.guard(action=True, point=point)
        self.wine.request(f'move {point[0]} {point[1]}')

    def drag(self, x1, y1, x2, y2, *, duration=.32):
        start, end = self._point(x1, y1), self._point(x2, y2)
        if not math.isfinite(duration) or not .2 <= duration <= .5:
            raise MouseStopped('Invalid drag duration. No input sent.')
        self.guard(action=True, point=start)
        self._trace('drag', start)
        # The helper releases the button itself. Do not guard afterwards: a
        # recheck there would make the caller retry a drag that already ran.
        self.wine.request(f'drag {start[0]} {start[1]} {end[0]} {end[1]} {round(duration*1000)}')

    def close(self):
        self.wine.close()


# ---- Windows ---------------------------------------------------------------

def require_background_permissions(pid):
    """The game runs elevated; Windows blocks capture and input from a
    normal app. Raise MouseElevationRequired so the GUI can offer a restart."""
    from types import SimpleNamespace
    from e7_native_mouse import MouseElevationRequired, require_mouse_permissions
    try:
        require_mouse_permissions(SimpleNamespace(pid=pid))
    except MouseElevationRequired as error:
        raise MouseElevationRequired(str(error).replace('No Mouse input sent.', 'No background input sent.')) from error


class WinGameWindow:
    """The game's Win32 window (Steam or STOVE): PrintWindow capture, state and pointer checks."""

    def __init__(self, *, api=None):
        import ctypes
        from ctypes import wintypes as w
        from e7_native_mouse import physical_pixel_coordinates, process_name
        self.ctypes, self.w = ctypes, w
        user = self.user = api or ctypes.WinDLL('user32', use_last_error=True)
        self.gdi = ctypes.WinDLL('gdi32', use_last_error=True)
        physical_pixel_coordinates(api=user)
        self._prototypes()
        found = []
        @ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
        def visit(handle, _):
            title, cls = ctypes.create_unicode_buffer(64), ctypes.create_unicode_buffer(64)
            user.GetWindowTextW(handle, title, 64); user.GetClassNameW(handle, cls, 64)
            if user.IsWindowVisible(handle) and title.value == GAME_TITLE and cls.value.startswith('GLFW'):
                found.append(handle)
            return True
        user.EnumWindows(visit, 0)
        games = []
        for handle in found:
            pid = w.DWORD(); user.GetWindowThreadProcessId(handle, ctypes.byref(pid))
            name = (process_name(pid.value) or '').replace('/', '\\').rsplit('\\', 1)[-1].lower()
            if name in WINDOWS_GAME_EXES:
                games.append((handle, pid.value, WINDOWS_GAME_EXES[name]))
        if not games:
            if found:
                raise ValueError('Background mode supports Epic Seven on Steam and STOVE. Use Mouse mode for this game client.')
            raise ValueError('Epic Seven (Steam or STOVE) is not running. Start the game, then try again.')
        if len(games) > 1:
            raise ValueError('More than one Epic Seven game window is open. Close the extra one, then try again.')
        self.hwnd, self.pid, self.game_client = games[0]

    def _prototypes(self):
        w, ctypes = self.w, self.ctypes
        for name, args, result in (
                ('EnumWindows', [ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM), w.LPARAM], w.BOOL),
                ('GetWindowTextW', [w.HWND, w.LPWSTR, ctypes.c_int], ctypes.c_int),
                ('GetClassNameW', [w.HWND, w.LPWSTR, ctypes.c_int], ctypes.c_int),
                ('IsWindowVisible', [w.HWND], w.BOOL), ('IsWindow', [w.HWND], w.BOOL), ('IsIconic', [w.HWND], w.BOOL),
                ('GetWindowThreadProcessId', [w.HWND, ctypes.POINTER(w.DWORD)], w.DWORD),
                ('GetClientRect', [w.HWND, ctypes.POINTER(w.RECT)], w.BOOL),
                ('GetWindowRect', [w.HWND, ctypes.POINTER(w.RECT)], w.BOOL),
                ('ClientToScreen', [w.HWND, ctypes.POINTER(w.POINT)], w.BOOL),
                ('GetCursorPos', [ctypes.POINTER(w.POINT)], w.BOOL),
                ('WindowFromPoint', [w.POINT], w.HWND), ('GetAncestor', [w.HWND, w.UINT], w.HWND),
                ('GetWindowDC', [w.HWND], w.HDC), ('ReleaseDC', [w.HWND, w.HDC], ctypes.c_int),
                ('MonitorFromWindow', [w.HWND, w.DWORD], w.HMONITOR),
                ('GetMonitorInfoW', [w.HMONITOR, ctypes.c_void_p], w.BOOL),
                ('PrintWindow', [w.HWND, w.HDC, w.UINT], w.BOOL)):
            function = getattr(self.user, name); function.argtypes, function.restype = args, result
        gdi = self.gdi
        gdi.CreateCompatibleDC.argtypes = [w.HDC]; gdi.CreateCompatibleDC.restype = w.HDC
        gdi.CreateCompatibleBitmap.argtypes = [w.HDC, ctypes.c_int, ctypes.c_int]; gdi.CreateCompatibleBitmap.restype = w.HBITMAP
        gdi.SelectObject.argtypes = [w.HDC, w.HGDIOBJ]; gdi.SelectObject.restype = w.HGDIOBJ
        gdi.DeleteObject.argtypes = [w.HGDIOBJ]; gdi.DeleteDC.argtypes = [w.HDC]
        gdi.GetDIBits.argtypes = [w.HDC, w.HBITMAP, w.UINT, w.UINT, ctypes.c_void_p, ctypes.c_void_p, w.UINT]
        gdi.GetDIBits.restype = ctypes.c_int

    def size(self):
        rect = self.w.RECT()
        if not self.user.GetClientRect(self.hwnd, self.ctypes.byref(rect)):
            return (0, 0)
        return rect.right, rect.bottom

    def problem(self):
        """Return why input must wait, or None."""
        if not self.user.IsWindow(self.hwnd):
            return 'The game window closed.'
        if self.user.IsIconic(self.hwnd) or not self.user.IsWindowVisible(self.hwnd):
            return 'The game window is minimized or hidden.'
        # The game cancels a posted click while the real pointer rests anywhere
        # on it except the target, windowed and fullscreen alike (reproduced on
        # Windows 11 STOVE at 1920 x 1009 windowed and 1920 x 1080 fullscreen,
        # 2026-11-14). Any pointer over the game pauses, as on Linux; on one
        # screen the compact tracker bar is a safe place to leave it.
        cursor = self.w.POINT()
        if not self.user.GetCursorPos(self.ctypes.byref(cursor)):
            return None
        hit = self.user.WindowFromPoint(cursor)
        if not hit or self.user.GetAncestor(hit, 2) != self.hwnd:  # GA_ROOT
            return None
        return ('Move your mouse off the game window; the game cancels background clicks while the '
                'pointer rests on it. Park it on the compact tracker bar, the taskbar or another screen.')

    def describe(self):
        """'windowed' or 'fullscreen', plus display scaling, for reports."""
        try:
            parts = ['windowed' if self._windowed() else 'fullscreen']
            dpi = self.user.GetDpiForWindow(self.hwnd) if hasattr(self.user, 'GetDpiForWindow') else 0
            if dpi:
                parts.append(f'display scale {round(dpi*100/96)}%')
            return ', '.join(parts)
        except Exception:
            return ''

    def _windowed(self):
        """True unless the game's client area covers its whole monitor. The
        client area, not the outer frame: a maximized window's frame overhangs
        the screen, but its title bar keeps the client below the top edge.
        If Windows cannot say, keep the fullscreen rule so single-screen
        players can run."""
        ctypes, w = self.ctypes, self.w
        class MONITORINFO(ctypes.Structure):
            _fields_ = [('cbSize', w.DWORD), ('rcMonitor', w.RECT), ('rcWork', w.RECT), ('dwFlags', w.DWORD)]
        client, origin, info = w.RECT(), w.POINT(0, 0), MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        monitor = self.user.MonitorFromWindow(self.hwnd, 2)  # MONITOR_DEFAULTTONEAREST
        if (not monitor or not self.user.GetMonitorInfoW(monitor, ctypes.byref(info))
                or not self.user.GetClientRect(self.hwnd, ctypes.byref(client))
                or not self.user.ClientToScreen(self.hwnd, ctypes.byref(origin))):
            return False
        screen = info.rcMonitor
        return not (origin.x <= screen.left and origin.y <= screen.top
                    and origin.x+client.right >= screen.right and origin.y+client.bottom >= screen.bottom)

    def capture(self):
        from PIL import Image
        ctypes, w, user, gdi = self.ctypes, self.w, self.user, self.gdi
        outer, origin = w.RECT(), w.POINT(0, 0)
        width, height = self.size()
        if not user.GetWindowRect(self.hwnd, ctypes.byref(outer)) or not user.ClientToScreen(self.hwnd, ctypes.byref(origin)):
            raise MouseStopped('The game window closed. Background session stopped.')
        ow, oh = outer.right-outer.left, outer.bottom-outer.top
        if ow <= 0 or oh <= 0 or width <= 0 or height <= 0:
            raise MouseStopped('The game window is minimized or hidden. Background session stopped.')
        window_dc = user.GetWindowDC(self.hwnd)
        memory_dc = gdi.CreateCompatibleDC(window_dc)
        bitmap = gdi.CreateCompatibleBitmap(window_dc, ow, oh)
        previous = gdi.SelectObject(memory_dc, bitmap)
        selected = True
        try:
            printed = user.PrintWindow(self.hwnd, memory_dc, 2)  # PW_RENDERFULLCONTENT
            # GetDIBits requires the bitmap not to be selected into a DC.
            gdi.SelectObject(memory_dc, previous); selected = False
            header = (ctypes.c_uint32*10)(40, ow, (-oh) & 0xffffffff, 1 | (32 << 16), 0, 0, 0, 0, 0, 0)
            pixels = ctypes.create_string_buffer(ow*oh*4)
            rows = gdi.GetDIBits(memory_dc, bitmap, 0, oh, pixels, header, 0)
        finally:
            if selected:
                gdi.SelectObject(memory_dc, previous)
            gdi.DeleteObject(bitmap); gdi.DeleteDC(memory_dc); user.ReleaseDC(self.hwnd, window_dc)
        if not printed or rows != oh:
            raise MouseStopped('Windows could not capture the game window. Run this app as administrator. No input sent.')
        left, top = origin.x-outer.left, origin.y-outer.top
        image = Image.frombuffer('RGB', (ow, oh), pixels.raw, 'raw', 'BGRX', 0, 1)
        return image.crop((left, top, left+width, top+height))
