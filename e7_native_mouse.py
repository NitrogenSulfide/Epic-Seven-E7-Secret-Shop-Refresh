"""Native mouse transport. Inputs run only inside an explicitly started session."""
import ctypes
import json
import math
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


def pointer_glide(start, end, scale=1, *, duration=None):
    """Physical points with eased timing, scaled to the game's displayed size."""
    distance = math.dist(start,end)/max(scale,.1)
    if distance < 2:
        return [(end,0)]
    duration = min(.38,max(.12,distance/3500)) if duration is None else duration
    steps = math.ceil(duration/.016)
    path = []
    for step in range(1,steps+1):
        t = step/steps
        eased = t*t*t*(10+t*(-15+6*t))
        point = tuple(round(a+(b-a)*eased) for a,b in zip(start,end))
        path.append((point,duration*t))
    return path


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


def process_is_elevated(pid=None, *, kernel=None, security=None):
    kernel = kernel or ctypes.WinDLL('kernel32',use_last_error=True)
    security = security or ctypes.WinDLL('advapi32',use_last_error=True)
    kernel.GetCurrentProcess.restype = w.HANDLE
    kernel.OpenProcess.argtypes = [w.DWORD,w.BOOL,w.DWORD]; kernel.OpenProcess.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    security.OpenProcessToken.argtypes = [w.HANDLE,w.DWORD,ctypes.POINTER(w.HANDLE)]
    security.OpenProcessToken.restype = w.BOOL
    security.GetTokenInformation.argtypes = [w.HANDLE,ctypes.c_int,w.LPVOID,w.DWORD,ctypes.POINTER(w.DWORD)]
    security.GetTokenInformation.restype = w.BOOL
    process = kernel.GetCurrentProcess() if pid is None else kernel.OpenProcess(0x1000,False,pid)
    token = w.HANDLE()
    try:
        elevated,size = w.DWORD(),w.DWORD()
        if not process or not security.OpenProcessToken(process,8,ctypes.byref(token)) or not security.GetTokenInformation(token,20,ctypes.byref(elevated),4,ctypes.byref(size)):
            raise ValueError('Could not verify game/app administrator permissions. No Mouse input sent.')
        return bool(elevated.value)
    finally:
        if token:
            kernel.CloseHandle(token)
        if pid is not None and process:
            kernel.CloseHandle(process)


def require_mouse_permissions(target):
    if process_is_elevated(target.pid) and not process_is_elevated():
        raise ValueError('Epic Seven is running as administrator. Close this app and reopen it with Run as administrator, then press Start. Windows blocks normal apps from controlling an elevated game. No Mouse input sent.')


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
    require_mouse_permissions(current)
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


def release_native_button():
    """Release the owned native session's button after forced engine termination."""
    api = ctypes.WinDLL('user32',use_last_error=True)
    api.SendInput.argtypes = [w.UINT,ctypes.POINTER(Input),ctypes.c_int]
    api.SendInput.restype = w.UINT
    release = Input(0,InputUnion(mouse=MouseInput(0,0,0,4,0,0)))
    return api.SendInput(1,ctypes.byref(release),ctypes.sizeof(Input)) == 1


class WindowsMouse:
    def __init__(self, target, active, *, backend=None, grabber=None, lookup=process_name, sender=None):
        if ImageGrab is None and grabber is None:
            raise ValueError('Mouse mode needs Pillow. Use the bundled player EXE.')
        if backend is None:
            require_mouse_permissions(target)
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
        self.pause_revision = 0

    def guard(self, *, action=False, point=None, held=False):
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
            if held:
                # Never wait for focus to return while holding a drag button.
                raise MouseStopped('Game focus or drag visibility changed. Mouse session stopped.')
            reason = ('The selected game lost focus or its view is covered.' if not visible else
                      'The mouse target is covered by another window.')
            problem = getattr(self.backend,'visibility_problem','')
            if not visible and isinstance(problem,str) and problem:
                reason = problem
            if deadline is None:
                self.pause_revision += 1
                print('E7GUI_MOUSE_PAUSED '+json.dumps({'reason':reason}),flush=True)
                deadline = time.monotonic()+10
            if time.monotonic() >= deadline:
                raise MouseStopped(reason+' No input sent while paused; focus did not return within 10 seconds.')
            time.sleep(.1)

    def screenshot(self):
        for _ in range(3):
            before = self.guard()
            revision = self.pause_revision
            image = self.grabber(bbox=before.rectangle,all_screens=True).convert('RGB')
            self.guard()
            if revision == self.pause_revision:
                break
        else:
            raise MouseStopped('Game visibility repeatedly changed during capture. No input sent.')
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

    def drag(self,x1,y1,x2,y2, *, duration=.32):
        start,end = self._point(x1,y1),self._point(x2,y2)
        if not math.isfinite(duration) or not .2 <= duration <= .5:
            raise MouseStopped('Invalid Mouse drag duration. No input sent.')
        self.guard(action=True,point=start)
        self.guard(action=True,point=end)
        self.sender(start,'drag',(end,duration))

    def _send(self,point,kind,data):
        api = self.backend.user
        api.GetSystemMetrics.argtypes = [ctypes.c_int]; api.GetSystemMetrics.restype = ctypes.c_int
        api.SendInput.argtypes = [w.UINT,ctypes.POINTER(Input),ctypes.c_int]; api.SendInput.restype = w.UINT
        api.GetCursorPos.argtypes = [ctypes.POINTER(w.POINT)]; api.GetCursorPos.restype = w.BOOL
        api.SetCursorPos.argtypes = [ctypes.c_int,ctypes.c_int]; api.SetCursorPos.restype = w.BOOL
        left,top,width,height = [api.GetSystemMetrics(key) for key in (76,77,78,79)]
        x,y = point
        if width < 2 or height < 2 or not (left <= x < left+width and top <= y < top+height):
            raise MouseStopped('Mouse target is outside the desktop. No input sent.')
        if kind == 'drag':
            end,duration = data
            if not (left <= end[0] < left+width and top <= end[1] < top+height):
                raise MouseStopped('Mouse drag ends outside the desktop. No input sent.')
            self.guard(action=True,point=end)
        self.guard(action=True,point=point)
        cursor = w.POINT()
        if not api.GetCursorPos(ctypes.byref(cursor)):
            raise MouseStopped('Could not read the pointer position. No input sent.')
        scale = (self.view[2]-self.view[0])/1920 if self.view else 1
        def travel(start,target, *, duration=None,held=False):
            started = time.monotonic()
            for destination,elapsed in pointer_glide(start,target,scale,duration=duration):
                remaining = started+elapsed-time.monotonic()
                if remaining > 0:
                    time.sleep(remaining)
                # Unheld approach can begin outside the game. A held drag
                # checks every point and immediately cancels on lost focus.
                self.guard(action=True,point=destination if held else target,held=held)
                px,py = destination
                movement = Input(0,InputUnion(mouse=MouseInput(
                    round((px-left)*65535/(width-1)),round((py-top)*65535/(height-1)),0,0xC001,0,0)))
                if api.SendInput(1,ctypes.byref(movement),ctypes.sizeof(Input)) != 1:
                    raise MouseStopped('Windows did not accept the pointer movement. Session stopped.')
        travel((cursor.x,cursor.y),point)
        # Verify delivery separately from acceptance: Windows can accept a batch
        # without the pointer reaching the intended game location.
        time.sleep(.05)
        positioned = api.GetCursorPos(ctypes.byref(cursor)) and max(abs(cursor.x-x),abs(cursor.y-y)) <= 3
        if not positioned:
            self.guard(action=True,point=point)
            if not api.SetCursorPos(x,y):
                raise MouseStopped(f'Windows accepted the mouse movement but did not move the pointer; direct placement also failed (Windows error {ctypes.get_last_error()}). No click sent.')
            time.sleep(.05)
            if not api.GetCursorPos(ctypes.byref(cursor)) or max(abs(cursor.x-x),abs(cursor.y-y)) > 3:
                raise MouseStopped('Windows did not place the pointer on the game target. No click sent.')
        self.guard(action=True,point=point)
        print('E7GUI_MOUSE_INPUT '+json.dumps(dict(action=kind,target=list(point),pointer=[cursor.x,cursor.y])),flush=True)
        if kind == 'move':
            return
        if kind == 'drag':
            self.guard(action=True,point=end)
        down = Input(0,InputUnion(mouse=MouseInput(0,0,0,2,0,0)))
        up = Input(0,InputUnion(mouse=MouseInput(0,0,0,4,0,0)))
        try:
            if api.SendInput(1,ctypes.byref(down),ctypes.sizeof(Input)) != 1:
                raise MouseStopped('Windows did not accept mouse-down. Session stopped.')
            if kind == 'drag':
                time.sleep(.04)
                travel(point,end,duration=duration,held=True)
                time.sleep(.03)
                self.guard(action=True,point=end,held=True)
                if not api.GetCursorPos(ctypes.byref(cursor)) or max(abs(cursor.x-end[0]),abs(cursor.y-end[1])) > 3:
                    raise MouseStopped('The drag did not reach its endpoint. Mouse session stopped.')
            else:
                # Hold a click across several game frames.
                time.sleep(.08)
        finally:
            released = api.SendInput(1,ctypes.byref(up),ctypes.sizeof(Input)) == 1
            if not released:
                released = api.SendInput(1,ctypes.byref(up),ctypes.sizeof(Input)) == 1
        if not released:
            raise MouseStopped('Windows did not accept mouse-up. Session stopped.')
        self.guard(action=True,point=end if kind == 'drag' else point)
