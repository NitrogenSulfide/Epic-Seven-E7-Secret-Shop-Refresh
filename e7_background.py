"""Background control of the Steam (Proton) game on Linux.

Capture reads the game's own X window, so other windows may cover it. Input is
posted as window messages by e7_wine_input.exe running inside the game's Wine
session, so the real pointer and keyboard focus are never used. The transport
mirrors WindowsMouse (screenshot/click/move/drag in 1920 x 1080 game space).
"""
from dataclasses import dataclass, field
import json
import math
import os
from pathlib import Path
import select
import subprocess
import time

from e7_native_mouse import MouseStopped, MouseRecheckRequired
from e7_windows_capture import game_view

STEAM_APP_ID = 5019180
GAME_TITLE = 'Epic Seven'
HELPER_NAME = 'e7_wine_input.exe'
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
    path = Path(configured) if configured else Path(__file__).resolve().with_name(HELPER_NAME)
    if not path.is_file():
        raise ValueError(f'The background input helper is missing: {path}. Build it with build_wine_input.sh.')
    return path


class WineInput:
    """Persistent e7_wine_input.exe inside the game's Wine session."""

    def __init__(self, session, *, helper=None, timeout=10, popen=subprocess.Popen):
        self.timeout = timeout
        self.process = popen([str(session.wine), str(helper or helper_path())],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             env=session.environment(), text=True, bufsize=1)

    def request(self, command, *, timeout=None):
        if self.process.poll() is not None:
            raise MouseStopped('The background input helper exited. No input sent.')
        self.process.stdin.write(command+'\n')
        self.process.stdin.flush()
        ready, _, _ = select.select([self.process.stdout], [], [], timeout or self.timeout)
        if not ready:
            raise MouseStopped(f'The background input helper did not answer "{command.split()[0]}".')
        reply = self.process.stdout.readline().strip()
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
        stack = [self.root]
        while stack:
            window = stack.pop()
            try:
                cls = window.get_wm_class() or ()
                if self.app_class in cls and window.get_wm_name() == GAME_TITLE:
                    return window
                stack.extend(window.query_tree().children)
            except Exception:
                continue
        raise ValueError('The Epic Seven game window was not found on this X display.')

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
        self.window = window or XGameWindow()
        self.wine = wine or WineInput(session or find_proton_session())
        _, width, height = self.wine.find()
        if (width, height) != self.window.size():
            self.close()
            raise ValueError(f'Wine reports a {width} x {height} game client but X reports '
                             f'{self.window.size()[0]} x {self.window.size()[1]}. Display scaling is not supported yet.')
        self.client = (width, height)
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
