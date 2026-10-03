"""Supply native Windows window icons at the monitor's actual pixel sizes."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import struct


class WindowIcons:
    def __init__(self, hwnd, ico_data, dpi=None):
        self.handles = []
        self.api = ctypes.WinDLL('user32', use_last_error=True)
        signatures = {
            'GetDpiForWindow': ([wintypes.HWND], wintypes.UINT),
            'GetSystemMetricsForDpi': ([ctypes.c_int, wintypes.UINT], ctypes.c_int),
            'CreateIconFromResourceEx': ([ctypes.c_void_p, wintypes.DWORD, wintypes.BOOL, wintypes.DWORD, ctypes.c_int, ctypes.c_int, wintypes.UINT], wintypes.HANDLE),
            'SendMessageW': ([wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM], wintypes.LPARAM),
            'DestroyIcon': ([wintypes.HANDLE], wintypes.BOOL),
            'GetWindowThreadProcessId': ([wintypes.HWND, ctypes.POINTER(wintypes.DWORD)], wintypes.DWORD),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(self.api, name)
            function.argtypes, function.restype = arguments, result
        import os
        owner = wintypes.DWORD()
        if not self.api.GetWindowThreadProcessId(hwnd, ctypes.byref(owner)) or owner.value != os.getpid():
            raise ValueError('Window icon changes are restricted to this GUI process.')
        self.dpi = dpi or self.api.GetDpiForWindow(hwnd) or 96
        if len(ico_data) < 6:
            raise ValueError('Invalid Windows icon directory.')
        reserved, image_type, count = struct.unpack_from('<HHH', ico_data)
        if reserved or image_type != 1 or not count or len(ico_data) < 6 + count * 16:
            raise ValueError('Invalid Windows icon directory.')
        entries = []
        for index in range(count):
            width, height, _, _, _, _, length, offset = struct.unpack_from('<BBBBHHII', ico_data, 6 + index * 16)
            if offset + length > len(ico_data):
                raise ValueError('Invalid Windows icon image bounds.')
            entries.append((width or 256, height or 256, ico_data[offset:offset+length]))
        self.sizes = []
        try:
            for kind, metric in ((1, 11), (0, 49)):  # ICON_BIG / ICON_SMALL
                size = self.api.GetSystemMetricsForDpi(metric, self.dpi)
                if size <= 0:
                    raise OSError('Windows could not determine the window icon size.')
                entry = min(entries, key=lambda e: (e[0] < size or e[1] < size, abs(e[0]-size) + abs(e[1]-size)))
                pixels = ctypes.create_string_buffer(entry[2])
                icon = self.api.CreateIconFromResourceEx(pixels, len(entry[2]), True, 0x00030000, size, size, 0)
                if not icon:
                    raise ctypes.WinError(ctypes.get_last_error())
                self.handles.append(icon)
                self.sizes.append(size)
            # Install only after both icons have been created successfully.
            for kind, icon in zip((1, 0), self.handles):
                self.api.SendMessageW(hwnd, 0x80, kind, icon)  # WM_SETICON
        except Exception:
            self.close()
            raise

    def close(self):
        for handle in self.handles:
            self.api.DestroyIcon(handle)
        self.handles.clear()
