"""User-selected Windows capture preview. Contains no mouse/input operations."""
from dataclasses import dataclass
import ctypes
from ctypes import wintypes as w
import json
import os
from pathlib import Path
import re
import subprocess
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageGrab, ImageTk, ImageDraw
from e7_setup import verify_setup_engine


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

    def unobstructed(self, target):
        u = self.user
        if u.GetAncestor(u.GetForegroundWindow(), 2) != target.handle:
            return False
        left, top, right, bottom = target.rectangle
        for x in (left+8, (left+right)//2, right-9):
            for y in (top+8, (top+bottom)//2, bottom-9):
                if u.GetAncestor(u.WindowFromPoint(w.POINT(x,y)), 2) != target.handle:
                    return False
        return True


def capture_selected(target, destination, *, backend=None, grabber=None):
    backend = backend or WindowsCapture()
    before = backend.inspect(target.handle)
    if before.pid != target.pid or before.title != target.title:
        raise ValueError('The selected window changed. Scan and select it again.')
    width, height = before.rectangle[2]-before.rectangle[0], before.rectangle[3]-before.rectangle[1]
    if abs(width/height - 16/9) > .03:
        raise ValueError('Use a 16:9 game view for this preview. Resize the game window and try again.')
    if not backend.unobstructed(before):
        raise ValueError('Click the selected game during the countdown and keep it unobstructed. No screenshot was saved.')
    image = (grabber or ImageGrab.grab)(bbox=before.rectangle, all_screens=True)
    after = backend.inspect(target.handle)
    if before != after or not backend.unobstructed(after):
        raise ValueError('The game moved or lost focus during capture. Try again. No screenshot was saved.')
    if image.size != (width, height):
        raise ValueError('Capture size does not match the game view. Check display scaling.')
    image = image.convert('RGB')
    if max(high-low for low, high in image.getextrema()) < 12:
        raise ValueError('The game capture was blank. This client has not passed capture testing.')
    image.save(destination)
    return before


def analyze_capture(engine, runtime, capture, report, *, runner=None):
    verify_setup_engine(engine)
    completed = (runner or subprocess.run)([str(engine), '--preview-mouse-frame', str(capture), '--output', str(report)],
        cwd=runtime, capture_output=True, text=True, timeout=30,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if completed.returncode:
        raise ValueError('Preview analysis failed. Use the matching new package and a visible English game view.')
    data = json.loads(Path(report).read_text(encoding='utf-8'))
    if not isinstance(data,dict) or data.get('read_only') is not True or data.get('state') not in ('home','shop','unrecognized'):
        raise ValueError('Invalid preview report.')
    if not isinstance(data.get('targets'),list) or not isinstance(data.get('detections'),list):
        raise ValueError('Incomplete preview report.')
    for target in data['targets']:
        point = target.get('point',[]) if isinstance(target,dict) else []
        if not isinstance(point,list) or len(point)!=2 or not isinstance(target.get('label'),str) or not all(isinstance(value,(int,float)) and 0<=value<limit for value,limit in zip(point,(1920,1080))):
            raise ValueError('Invalid preview target.')
    for item in data['detections']:
        box = item.get('box',[]) if isinstance(item,dict) else []
        if not isinstance(box,list) or len(box)!=4 or not isinstance(item.get('label'),str) or not all(isinstance(value,(int,float)) and 0<=value<=limit for value,limit in zip(box,(1920,1080,1920,1080))) or box[2]<=box[0] or box[3]<=box[1]:
            raise ValueError('Invalid preview detection.')
    return data


def annotated_capture(capture, report):
    with Image.open(capture) as source:
        image = source.convert('RGB').resize((1920,1080),Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(image)
    for index, target in enumerate(report.get('targets',[]),1):
        x,y = target['point']
        draw.ellipse((x-24,y-24,x+24,y+24), outline='#fbbf24',width=5)
        draw.line((x-32,y,x+32,y), fill='#fbbf24',width=3)
        draw.line((x,y-32,x,y+32), fill='#fbbf24',width=3)
        draw.text((x+30,y-18),str(index),fill='#fbbf24',stroke_width=1)
    for detection in report.get('detections',[]):
        draw.rectangle(detection['box'],outline='#22d3ee',width=5)
    return image


class MousePreviewDialog(tk.Toplevel):
    def __init__(self, app, capture, report):
        super().__init__(app)
        self.app = app
        self.title('Mouse preview · no clicks or spending')
        self.configure(bg='#111827' if app.dark_mode.get() else '#f3f5f8')
        self.transient(app)
        self.protocol('WM_DELETE_WINDOW',self.close)
        self.bind('<Escape>',lambda _:self.close())
        width,height = app._screen_work_area()[2:]
        image = annotated_capture(capture,report)
        image.thumbnail((min(app._dp(1000),width-app._dp(80)),height-app._dp(230)))
        self.photo = ImageTk.PhotoImage(image,master=self)
        ttk.Label(self,text='PREVIEW ONLY · no mouse movement, clicks or spending',font=app.heading_font).pack(padx=app._dp(16),pady=app._dp(12))
        ttk.Label(self,image=self.photo).pack(padx=app._dp(16))
        names = [f"{index}. {target['label']}" for index,target in enumerate(report['targets'],1)]
        found = [d['label'] for d in report['detections']]
        message = ('Recognized: '+report['state']+'. '+(' · '.join(names) or 'No click targets recognized.'))
        if found: message += '\nCyan boxes: '+', '.join(found)+'.'
        message += '\nThe screenshot stays private in this runtime’s mouse-previews folder.'
        self.message = ttk.Label(self,text=message,wraplength=image.width,justify='left')
        self.message.pack(padx=app._dp(16),pady=app._dp(12))
        ttk.Button(self,text='Close preview',command=self.close).pack(pady=(0,app._dp(12)))

    def close(self):
        self.app.preview_window = None
        self.destroy()
