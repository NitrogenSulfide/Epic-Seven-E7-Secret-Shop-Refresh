"""Read-only Windows game-window discovery and client-view geometry."""
from dataclasses import dataclass
import ctypes
from ctypes import wintypes as w
import os
import re

@dataclass(frozen=True)
class GameWindow:
    handle: int
    pid: int
    title: str
    rectangle: tuple[int, int, int, int]

    @property
    def label(self):
        return f'{self.title} · {self.pid} / {self.handle:x}'


class WindowsCapture:
    def __init__(self):
        if os.name != 'nt':
            raise RuntimeError('Window preview requires Windows.')
        self.user = u = ctypes.WinDLL('user32', use_last_error=True)
        self.callback_type = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
        signatures = {
            'EnumWindows': ([self.callback_type, w.LPARAM], w.BOOL),
            'IsWindowVisible': ([w.HWND], w.BOOL), 'IsIconic': ([w.HWND], w.BOOL),
            'GetWindowTextLengthW': ([w.HWND], ctypes.c_int),
            'GetWindowTextW': ([w.HWND, w.LPWSTR, ctypes.c_int], ctypes.c_int),
            'GetWindowThreadProcessId': ([w.HWND, ctypes.POINTER(w.DWORD)], w.DWORD),
            'GetClientRect': ([w.HWND, ctypes.POINTER(w.RECT)], w.BOOL),
            'ClientToScreen': ([w.HWND, ctypes.POINTER(w.POINT)], w.BOOL),
            'GetForegroundWindow': ([], w.HWND),
            'WindowFromPoint': ([w.POINT], w.HWND),
            'GetAncestor': ([w.HWND, w.UINT], w.HWND),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(u, name); function.argtypes = arguments; function.restype = result

    def inspect(self, handle):
        u = self.user
        if not u.IsWindowVisible(handle) or u.IsIconic(handle):
            raise ValueError('Open the selected game window and leave it unminimized.')
        pid = w.DWORD(); u.GetWindowThreadProcessId(handle, ctypes.byref(pid))
        if not pid.value or pid.value == os.getpid():
            raise ValueError('Choose the game window, not this tool.')
        title = ctypes.create_unicode_buffer(u.GetWindowTextLengthW(handle)+1)
        u.GetWindowTextW(handle, title, len(title))
        rectangle = w.RECT(); point = w.POINT(0, 0)
        if not u.GetClientRect(handle, ctypes.byref(rectangle)) or not u.ClientToScreen(handle, ctypes.byref(point)):
            raise ValueError('Could not read the game window. Scan and select it again.')
        box = (point.x, point.y, point.x+rectangle.right, point.y+rectangle.bottom)
        if box[2]-box[0] < 640 or box[3]-box[1] < 360:
            raise ValueError('Make the game window at least 640 × 360 pixels.')
        return GameWindow(int(handle), pid.value, title.value, box)

    def list_windows(self):
        windows = []
        @self.callback_type
        def visit(handle, _):
            try:
                target = self.inspect(handle)
                if re.search(r'google play games|epic\s*(seven|7)|mumu|bluestacks|ldplayer|nox', target.title, re.I):
                    windows.append(target)
            except ValueError:
                pass
            return True
        if not self.user.EnumWindows(visit, 0):
            raise OSError('Could not scan game windows.')
        return sorted(windows, key=lambda window: (window.title.lower(), window.pid, window.handle))

    def point_visible(self, target, point):
        return self.user.GetAncestor(self.user.WindowFromPoint(w.POINT(*point)), 2) == target.handle

    def unobstructed(self, target, *, margin=None):
        u = self.user
        self.visibility_problem = ''
        if u.GetAncestor(u.GetForegroundWindow(), 2) != target.handle:
            self.visibility_problem = 'Epic Seven is no longer the foreground window.'
            return False
        left, top, right, bottom = target.rectangle
        inset_x = 8 if margin is None else max(8,round((right-left)*margin))
        inset_y = 8 if margin is None else max(8,round((bottom-top)*margin))
        for x in (left+inset_x, (left+right)//2, right-inset_x-1):
            for y in (top+inset_y, (top+bottom)//2, bottom-inset_y-1):
                if u.GetAncestor(u.WindowFromPoint(w.POINT(x,y)), 2) != target.handle:
                    self.visibility_problem = f'The game view is covered at client point {x-left}, {y-top}.'
                    return False
        return True


def game_view(image, *, google_emulator=False):
    """Preserve the client view; crop observed bars or Google's custom header."""
    width, height = image.size
    if abs(width/height - 16/9) <= .03:
        return image, (0,0,width,height)
    if google_emulator:
        # Google's custom title bar is inside its client rectangle. Identify
        # the mostly black band in pixels; never assume a DPI-specific height.
        gray = image.convert('L')
        top = 0
        for y in range(min(round(height*.09), height)):
            histogram = gray.crop((0,y,width,y+1)).histogram()
            if sum(histogram[:25])/width < .80:
                break
            top = y+1
        if 8 <= top <= height*.09 and height-top >= 360 and abs(width/(height-top)-16/9) <= .03:
            return image.crop((0,top,width,height)), (0,top,width,height)
    bounds = image.convert('L').point(lambda value: 255 if value > 12 else 0).getbbox()
    if bounds:
        left, top, right, bottom = bounds
        view_width, view_height = right-left, bottom-top
        if width/height > 16/9:
            bars = top == 0 and bottom == height and left >= 3 and width-right >= 3
            centered = abs(left-(width-right)) <= max(4,round(width*.005))
        else:
            bars = left == 0 and right == width and top >= 3 and height-bottom >= 3
            centered = abs(top-(height-bottom)) <= max(4,round(height*.005))
        if bars and centered and view_width >= 640 and view_height >= 360 and abs(view_width/view_height - 16/9) <= .03:
            return image.crop(bounds), bounds
    # Native PC clients can fill a wider window without letterboxing. Preview
    # must show that actual image rather than inventing a centered 16:9 crop.
    return image, (0,0,width,height)


