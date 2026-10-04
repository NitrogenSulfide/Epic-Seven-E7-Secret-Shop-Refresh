"""User-selected Windows capture preview. Contains no mouse/input operations."""
from dataclasses import dataclass
import ctypes
from ctypes import wintypes as w
import json
import os
from pathlib import Path
import re
import subprocess
import time
import tkinter as tk
from tkinter import ttk
try:
    from PIL import Image, ImageGrab, ImageTk, ImageDraw
except ImportError:
    Image = None
from e7_setup import verify_setup_engine


from e7_windows_capture import GameWindow, WindowsCapture, game_view


def wait_for_window(target, cancel, *, timeout=20, backend=None, now=time.monotonic):
    """Wait for the user to bring the selected game forward; never activate it."""
    backend = backend or WindowsCapture()
    deadline = now()+timeout
    while not cancel.is_set():
        current = backend.inspect(target.handle)
        if current.pid != target.pid or current.title != target.title:
            raise ValueError('The selected window changed. Scan and select it again.')
        if backend.unobstructed(current):
            return current
        remaining = deadline-now()
        if remaining <= 0:
            raise ValueError('The game window was not ready within 20 seconds. '
                             'Click the selected game and minimize any windows covering it, then retry.')
        cancel.wait(min(.15,remaining))
    raise ValueError('Mouse preview cancelled. No screenshot was saved.')


def capture_selected(target, destination, *, backend=None, grabber=None, cancel=None):
    if Image is None:
        raise ValueError('Mouse preview needs Pillow. Use the bundled player EXE.')
    if cancel is not None and cancel.is_set():
        raise ValueError('Mouse preview cancelled. No screenshot was saved.')
    backend = backend or WindowsCapture()
    before = backend.inspect(target.handle)
    if before.pid != target.pid or before.title != target.title:
        raise ValueError('The selected window changed. Scan and select it again.')
    width, height = before.rectangle[2]-before.rectangle[0], before.rectangle[3]-before.rectangle[1]
    if not backend.unobstructed(before):
        raise ValueError('The selected game is no longer in front or is partly covered. Click it and retry. No screenshot was saved.')
    image = (grabber or ImageGrab.grab)(bbox=before.rectangle, all_screens=True)
    if cancel is not None and cancel.is_set():
        raise ValueError('Mouse preview cancelled. No screenshot was saved.')
    after = backend.inspect(target.handle)
    if before != after or not backend.unobstructed(after):
        raise ValueError('The game moved or lost focus during capture. Try again. No screenshot was saved.')
    if image.size != (width, height):
        raise ValueError('Capture size does not match the game view. Check display scaling.')
    image = image.convert('RGB')
    if max(high-low for low, high in image.getextrema()) < 12:
        raise ValueError('The game capture was blank. This client has not passed capture testing.')
    image.save(Path(destination).with_name('client-capture.png'))
    image, bounds = game_view(image,google_emulator='google play games' in before.title.lower())
    image.save(destination)
    left, top = before.rectangle[:2]
    return GameWindow(before.handle,before.pid,before.title,
                      (left+bounds[0],top+bounds[1],left+bounds[2],top+bounds[3]))


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
        image = source.convert('RGB')
        image.thumbnail((1920,1080),Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(image)
    scale_x, scale_y = image.width/1920, image.height/1080
    for index, target in enumerate(report.get('targets',[]),1):
        x,y = target['point'][0]*scale_x,target['point'][1]*scale_y
        draw.ellipse((x-24,y-24,x+24,y+24), outline='#fbbf24',width=5)
        draw.line((x-32,y,x+32,y), fill='#fbbf24',width=3)
        draw.line((x,y-32,x,y+32), fill='#fbbf24',width=3)
        draw.text((x+30,y-18),str(index),fill='#fbbf24',stroke_width=1)
    for detection in report.get('detections',[]):
        draw.rectangle([value*scale for value,scale in zip(detection['box'],(scale_x,scale_y,scale_x,scale_y))],outline='#22d3ee',width=5)
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
        if report['state'] == 'unrecognized':
            message = ('Game controls were not recognized. If home UI is hidden, click the game once '
                       'to reveal it, or open Secret Shop manually, then try another preview.')
        if found: message += '\nCyan boxes: '+', '.join(found)+'.'
        message += '\nThe screenshot stays private in this runtime’s mouse-previews folder.'
        self.message = ttk.Label(self,text=message,wraplength=image.width,justify='left')
        self.message.pack(padx=app._dp(16),pady=app._dp(12))
        ttk.Button(self,text='Close preview',command=self.close).pack(pady=(0,app._dp(12)))

    def close(self):
        self.app.preview_window = None
        self.destroy()
