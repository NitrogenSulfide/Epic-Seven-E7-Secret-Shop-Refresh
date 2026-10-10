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
    render_handle: int | None = None

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
            'EnumChildWindows': ([w.HWND, self.callback_type, w.LPARAM], w.BOOL),
            'IsChild': ([w.HWND, w.HWND], w.BOOL),
            'GetParent': ([w.HWND], w.HWND),
            'IsWindowEnabled': ([w.HWND], w.BOOL),
            'IsWindowVisible': ([w.HWND], w.BOOL), 'IsIconic': ([w.HWND], w.BOOL),
            'GetWindowTextLengthW': ([w.HWND], ctypes.c_int),
            'GetWindowTextW': ([w.HWND, w.LPWSTR, ctypes.c_int], ctypes.c_int),
            'GetClassNameW': ([w.HWND,w.LPWSTR,ctypes.c_int],ctypes.c_int),
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
        surface = self._bluestacks_surface(handle, pid.value, box)
        if surface is None and title.value.lower().startswith('bluestacks app player'):
            raise ValueError('BlueStacks game surface is unavailable. Open its player and game, then Scan again.')
        render_handle, box = surface if surface is not None else (None, box)
        return GameWindow(int(handle), pid.value, title.value, box, render_handle)

    def _bluestacks_surface(self, parent, pid, outer):
        """Use BlueStacks' real render child; exclude toolbars and advertising."""
        surfaces = []
        @self.callback_type
        def visit(child, _):
            name = ctypes.create_unicode_buffer(256)
            self.user.GetClassNameW(child, name, len(name))
            if name.value != 'BlueStacksApp' or not self.user.IsWindowVisible(child):
                return True
            child_pid = w.DWORD()
            self.user.GetWindowThreadProcessId(child, ctypes.byref(child_pid))
            if child_pid.value != pid or self.user.GetAncestor(child, 2) != parent:
                return True
            rect, point = w.RECT(), w.POINT()
            if not self.user.GetClientRect(child, ctypes.byref(rect)) or not self.user.ClientToScreen(child, ctypes.byref(point)):
                return True
            box = (point.x, point.y, point.x + rect.right, point.y + rect.bottom)
            if (rect.right >= 640 and rect.bottom >= 360 and
                    outer[0] <= box[0] < box[2] <= outer[2] and outer[1] <= box[1] < box[3] <= outer[3]):
                surfaces.append((int(child), box))
            return True
        self.user.EnumChildWindows(parent, visit, 0)
        if len(surfaces) > 1:
            raise ValueError('BlueStacks has multiple game surfaces. No Mouse input sent; reopen its player and Scan again.')
        return surfaces[0] if surfaces else None

    def list_windows(self):
        windows = []
        @self.callback_type
        def visit(handle, _):
            try:
                target = self.inspect(handle)
                if 'bluestacks' in target.title.lower() and target.render_handle is None:
                    return True
                if re.search(r'google play games|epic\s*(seven|7)|mumu|bluestacks|ldplayer|nox', target.title, re.I):
                    windows.append(target)
            except ValueError:
                pass
            return True
        if not self.user.EnumWindows(visit, 0):
            raise OSError('Could not scan game windows.')
        return sorted(windows, key=lambda window: (window.title.lower(), window.pid, window.handle))

    def point_visible(self, target, point):
        hit=self.user.WindowFromPoint(w.POINT(*point))
        root=self.user.GetAncestor(hit,2)
        surface = target.render_handle
        if root==target.handle and (surface is None or hit == surface or self.user.IsChild(surface, hit)):
            return True
        if root==target.handle and surface is not None and self._render_parent_hit(target,hit,point):
            return True
        self._record_coverage(target,point,hit,root)
        return False

    def _render_parent_hit(self,target,hit,point):
        # BlueStacks disables its render child. WindowFromPoint therefore
        # reports the enabled Qt host which receives the player's mouse input.
        # Accept only that direct parent, with the same verified game bounds;
        # other ancestors, sibling overlays and foreign windows still block.
        u=self.user
        if (hit==target.handle or u.GetParent(target.render_handle)!=hit or
                u.IsWindowEnabled(target.render_handle) or not u.IsWindowEnabled(hit)):
            return False
        name=ctypes.create_unicode_buffer(256);u.GetClassNameW(hit,name,len(name))
        pid=w.DWORD();u.GetWindowThreadProcessId(hit,ctypes.byref(pid))
        if not re.fullmatch(r'Qt\d+QWindowIcon',name.value) or pid.value!=target.pid:
            return False
        rect,origin=w.RECT(),w.POINT()
        if not u.GetClientRect(hit,ctypes.byref(rect)) or not u.ClientToScreen(hit,ctypes.byref(origin)):
            return False
        box=(origin.x,origin.y,origin.x+rect.right,origin.y+rect.bottom)
        return box==target.rectangle and box[0]<=point[0]<box[2] and box[1]<=point[1]<box[3]

    def _record_coverage(self,target,point,hit,root):
        pid=w.DWORD();self.user.GetWindowThreadProcessId(root,ctypes.byref(pid))
        name=ctypes.create_unicode_buffer(256);self.user.GetClassNameW(hit,name,len(name))
        root_name=ctypes.create_unicode_buffer(256);self.user.GetClassNameW(root,root_name,len(root_name))
        self.visibility_details=dict(client_point=[point[0]-target.rectangle[0],point[1]-target.rectangle[1]],
            hit_window=int(hit or 0),root_window=int(root or 0),process_id=pid.value,
            window_class=name.value,root_window_class=root_name.value,target_window=target.handle)

    def unobstructed(self, target, *, margin=None):
        u = self.user
        self.visibility_problem = ''
        self.visibility_details = None
        if u.GetAncestor(u.GetForegroundWindow(), 2) != target.handle:
            self.visibility_problem = 'Epic Seven is no longer the foreground window.'
            return False
        left, top, right, bottom = target.rectangle
        inset_x = 8 if margin is None else max(8,round((right-left)*margin))
        inset_y = 8 if margin is None else max(8,round((bottom-top)*margin))
        for x in (left+inset_x, (left+right)//2, right-inset_x-1):
            for y in (top+inset_y, (top+bottom)//2, bottom-inset_y-1):
                if not self.point_visible(target,(x,y)):
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
        # Restored windows can have a thin light frame above the dark header.
        # Skip only that small edge; a colored toolbar is not a dark header.
        def dark_row(y):
            histogram = gray.crop((0,y,width,y+1)).histogram()
            return sum(histogram[:25])/width >= .80
        start = next((y for y in range(min(8,height)) if dark_row(y)), None)
        top = 0
        for y in range(start if start is not None else 0, min(round(height*.20), height)):
            if start is None or not dark_row(y):
                break
            top = y+1
        if 8 <= top <= height*.20 and height-top >= 360 and abs(width/(height-top)-16/9) <= .03:
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


