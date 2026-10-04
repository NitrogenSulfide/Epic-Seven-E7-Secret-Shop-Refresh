"""Native mouse transport. Inputs run only inside an explicitly started session."""
import ctypes
import json
import time
from ctypes import wintypes as w
from pathlib import Path
try:
    from PIL import ImageGrab
except ImportError:
    ImageGrab = None
from e7_windows_capture import WindowsCapture, game_view


class MouseStopped(RuntimeError):
    pass


def physical_pixel_coordinates(*, api=None):
    api = api or ctypes.WinDLL('user32',use_last_error=True)
    api.SetThreadDpiAwarenessContext.argtypes = [w.HANDLE]
    api.SetThreadDpiAwarenessContext.restype = w.HANDLE
    if not api.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4)):
        raise ValueError('Could not use physical display coordinates. No Mouse input sent.')


def process_name(pid):
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]; api.OpenProcess.restype = w.HANDLE
    api.QueryFullProcessImageNameW.argtypes = [w.HANDLE,w.DWORD,w.LPWSTR,ctypes.POINTER(w.DWORD)]
    api.QueryFullProcessImageNameW.restype = w.BOOL
    api.CloseHandle.argtypes = [w.HANDLE]
    handle = api.OpenProcess(0x1000, False, pid)
    if not handle:
        raise ValueError('Could not verify the selected game process. Scan again.')
    try:
        name = ctypes.create_unicode_buffer(32768); size = w.DWORD(len(name))
        if not api.QueryFullProcessImageNameW(handle,0,name,ctypes.byref(size)):
            raise ValueError('Could not verify the selected game process. Scan again.')
        return Path(name.value).name
    finally:
        api.CloseHandle(handle)


def verify_native_target(target, *, backend=None, lookup=process_name):
    backend = backend or WindowsCapture()
    current = backend.inspect(target.handle)
    if (current.pid,current.title) != (target.pid,target.title):
        raise ValueError('The selected window changed. Scan and select it again.')
    if lookup(current.pid).lower() != 'epicseven.exe':
        raise ValueError('Real Mouse mode currently supports native STOVE Epic Seven. Use ADB or preview for other clients.')
    return current


def activate_native_target(target):
    backend = WindowsCapture()
    current = verify_native_target(target,backend=backend)
    backend.user.SetForegroundWindow.argtypes = [w.HWND]
    backend.user.SetForegroundWindow.restype = w.BOOL
    # Start is the user's authorization to bring this selected game forward.
    # No window resizing, wake-up click, or repeated focus stealing.
    backend.user.SetForegroundWindow(current.handle)
    return current


class MouseInput(ctypes.Structure):
    _fields_ = [('dx',w.LONG),('dy',w.LONG),('data',w.DWORD),('flags',w.DWORD),
                ('time',w.DWORD),('extra',w.WPARAM)]


class InputUnion(ctypes.Union):
    _fields_ = [('mouse',MouseInput)]


class Input(ctypes.Structure):
    _fields_ = [('kind',w.DWORD),('value',InputUnion)]


class WindowsMouse:
    def __init__(self, target, active, *, backend=None, grabber=None, lookup=process_name, sender=None):
        if ImageGrab is None and grabber is None:
            raise ValueError('Mouse mode needs Pillow. Use the bundled player EXE.')
        if backend is None:
            # This owned engine thread uses physical pixels across monitor scales.
            # Pillow capture and Win32 input must use the same coordinate space.
            physical_pixel_coordinates()
        self.backend = backend or WindowsCapture()
        self.target = verify_native_target(target,backend=self.backend,lookup=lookup)
        self.active = active
        self.grabber = grabber or ImageGrab.grab
        self.sender = sender or self._send
        self.view = None
        self.session_active = False

    def guard(self, *, action=False, point=None):
        deadline = None
        while True:
            active = self.active()
            self.session_active = self.session_active or active
            if (action or self.session_active) and not active:
                raise MouseStopped('Mouse session stopped.')
            current = self.backend.inspect(self.target.handle)
            if current != self.target:
                raise MouseStopped('The game moved, resized or changed identity. Mouse session stopped.')
            # Native clients can extend beneath a taskbar or have border overlays.
            # Sample the interior and separately check the exact action target.
            visible = self.backend.unobstructed(current,margin=.06)
            target_visible = point is None or self.backend.point_visible(current,point)
            if visible and target_visible:
                if deadline is not None:
                    if action:
                        raise MouseStopped('Focus or target visibility changed after preparing this click. No input sent; restart to recognize the current screen.')
                    print('E7GUI_MOUSE_RESUMED',flush=True)
                return current
            reason = ('The selected game lost focus or its view is covered.' if not visible else
                      'The mouse target is covered by another window.')
            problem = getattr(self.backend,'visibility_problem','')
            if not visible and isinstance(problem,str) and problem:
                reason = problem
            if deadline is None:
                print('E7GUI_MOUSE_PAUSED '+json.dumps({'reason':reason}),flush=True)
                deadline = time.monotonic()+10
            if time.monotonic() >= deadline:
                raise MouseStopped(reason+' No input sent while paused; focus did not return within 10 seconds.')
            time.sleep(.1)

    def screenshot(self):
        before = self.guard()
        image = self.grabber(bbox=before.rectangle,all_screens=True).convert('RGB')
        self.guard()
        width,height = before.rectangle[2]-before.rectangle[0],before.rectangle[3]-before.rectangle[1]
        if image.size != (width,height) or max(hi-lo for lo,hi in image.getextrema()) < 12:
            raise MouseStopped('The client capture is blank or has the wrong size. Mouse session stopped.')
        image,bounds = game_view(image)
        left,top = before.rectangle[:2]
        view = (left+bounds[0],top+bounds[1],left+bounds[2],top+bounds[3])
        if self.view is not None and self.view != view:
            raise MouseStopped('The game viewport changed. Mouse session stopped.')
        self.view = view
        return image

    def _point(self,x,y):
        if self.view is None or not (0 <= x < 1920 and 0 <= y < 1080):
            raise MouseStopped('Invalid Mouse target. No input sent.')
        left,top,right,bottom = self.view
        return round(left+x*(right-left)/1920),round(top+y*(bottom-top)/1080)

    def click(self,x,y):
        point = self._point(x,y)
        self.guard(action=True,point=point)
        self.sender(point,'click',0)

    def move(self,x,y):
        point = self._point(x,y)
        self.guard(action=True,point=point)
        self.sender(point,'move',0)

    def scroll(self,x,y):
        point = self._point(x,y)
        self.guard(action=True,point=point)
        # A wheel event avoids leaving a held drag button if Stop kills the job.
        self.sender(point,'wheel',-1200)

    def _send(self,point,kind,data):
        api = self.backend.user
        api.GetSystemMetrics.argtypes = [ctypes.c_int]; api.GetSystemMetrics.restype = ctypes.c_int
        api.SendInput.argtypes = [w.UINT,ctypes.POINTER(Input),ctypes.c_int]; api.SendInput.restype = w.UINT
        left,top,width,height = [api.GetSystemMetrics(key) for key in (76,77,78,79)]
        x,y = point
        if width < 2 or height < 2 or not (left <= x < left+width and top <= y < top+height):
            raise MouseStopped('Mouse target is outside the desktop. No input sent.')
        move = MouseInput(round((x-left)*65535/(width-1)),round((y-top)*65535/(height-1)),0,0xC001,0,0)
        events = [Input(0,InputUnion(mouse=move))]
        if kind == 'click':
            events.extend(Input(0,InputUnion(mouse=MouseInput(0,0,0,flag,0,0))) for flag in (2,4))
        elif kind == 'wheel':
            events.append(Input(0,InputUnion(mouse=MouseInput(0,0,data & 0xffffffff,0x800,0,0))))
        self.guard(action=True,point=point)
        batch = (Input*len(events))(*events)
        if api.SendInput(len(events),batch,ctypes.sizeof(Input)) != len(events):
            # Release after a partial click insertion; never leave the button held.
            release = Input(0,InputUnion(mouse=MouseInput(0,0,0,4,0,0)))
            api.SendInput(1,ctypes.byref(release),ctypes.sizeof(Input))
            raise MouseStopped('Windows did not accept the Mouse input. Session stopped.')
