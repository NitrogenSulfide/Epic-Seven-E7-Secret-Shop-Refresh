"""Session-owned global Stop key, including streamed/injected keyboard events."""
import ctypes
from ctypes import wintypes as w
import os
import re

WM_HOTKEY = 0x0312
HOTKEY_ID = 0x7E7
MOD_NOREPEAT = 0x4000
WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x100, 0x101, 0x104, 0x105
MODIFIER_KEYS = {1:(18,164,165),2:(17,162,163),4:(16,160,161),8:(91,92)}
HOOKPROC = getattr(ctypes,'WINFUNCTYPE',ctypes.CFUNCTYPE)(ctypes.c_ssize_t,ctypes.c_int,w.WPARAM,w.LPARAM)

class KeyboardEvent(ctypes.Structure):
    _fields_ = [('vkCode',w.DWORD),('scanCode',w.DWORD),('flags',w.DWORD),
                ('time',w.DWORD),('dwExtraInfo',ctypes.c_size_t)]
NAMED_KEYS = {'esc':27,'escape':27,'space':32,'enter':13,'return':13,'tab':9,
    'backspace':8,'delete':46,'insert':45,'home':36,'end':35,'page up':33,
    'page down':34,'up':38,'down':40,'left':37,'right':39,'pause':19,
    'caps lock':20,'num lock':144,'scroll lock':145,'print screen':44}
MODIFIERS = {'ctrl':2,'control':2,'alt':1,'shift':4,'win':8,'windows':8}

def virtual_stop_key(key, scan):
    """Retain single-key settings and legacy manually configured chords."""
    parts=key.lower().strip().split('+') if key!='+' else ['+']
    modifiers=0
    for part in parts[:-1]:
        if part.strip() not in MODIFIERS:raise ValueError('Choose a supported Stop key.')
        modifiers |= MODIFIERS[part.strip()]
    name=parts[-1].strip()
    if name in NAMED_KEYS:vk=NAMED_KEYS[name]
    elif re.fullmatch(r'f(?:[1-9]|1\d|2[0-4])',name):vk=111+int(name[1:])
    elif len(name)==1:
        value=scan(name)
        if value==-1:raise ValueError('The Stop key is unavailable on this keyboard layout.')
        vk=value & 255
        shift=(value>>8)&255
        modifiers |= (4 if shift&1 else 0)|(2 if shift&2 else 0)|(1 if shift&4 else 0)
    else:raise ValueError('Choose a supported Stop key.')
    if vk==123:raise ValueError('F12 is reserved by Windows. Choose another Stop key.')
    return vk,modifiers

class WindowsStopKey:
    def __init__(self,key,*,api=None,last_error=None,module=None):
        self.api=api or ctypes.WinDLL('user32',use_last_error=True)
        if api is None:
            for name,args,result in (
                ('RegisterHotKey',[w.HWND,ctypes.c_int,w.UINT,w.UINT],w.BOOL),
                ('UnregisterHotKey',[w.HWND,ctypes.c_int],w.BOOL),
                ('PeekMessageW',[ctypes.POINTER(w.MSG),w.HWND,w.UINT,w.UINT,w.UINT],w.BOOL),
                ('GetAsyncKeyState',[ctypes.c_int],ctypes.c_short),
                ('VkKeyScanW',[w.WCHAR],ctypes.c_short),
                ('SetWindowsHookExW',[ctypes.c_int,HOOKPROC,w.HINSTANCE,w.DWORD],w.HANDLE),
                ('UnhookWindowsHookEx',[w.HANDLE],w.BOOL),
                ('CallNextHookEx',[w.HANDLE,ctypes.c_int,w.WPARAM,w.LPARAM],ctypes.c_ssize_t),
                ('TranslateMessage',[ctypes.POINTER(w.MSG)],w.BOOL),
                ('DispatchMessageW',[ctypes.POINTER(w.MSG)],ctypes.c_ssize_t)):
                function=getattr(self.api,name);function.argtypes=args;function.restype=result
        self.key=key;self.vk,self.modifiers=virtual_stop_key(key,self.api.VkKeyScanW)
        self.last_error=last_error or ctypes.get_last_error
        self.module=module
        if api is None:
            kernel=ctypes.WinDLL('kernel32',use_last_error=True)
            kernel.GetModuleHandleW.argtypes=[w.LPCWSTR];kernel.GetModuleHandleW.restype=w.HMODULE
            self.module=kernel.GetModuleHandleW(None)
        self.registered=False;self.hook=None;self._down=set();self._detected=False
        self.detected_by='';self.injected=False
        self._hook_callback=HOOKPROC(self._keyboard_event)
        self.backend='Windows global hotkey + injected-key listener'

    def __enter__(self):
        # Register on the engine's polling thread; its queue receives WM_HOTKEY
        # regardless of which ordinary desktop window has keyboard focus.
        if not self.api.RegisterHotKey(None,HOTKEY_ID,self.modifiers|MOD_NOREPEAT,self.vk):
            raise ValueError(f'Could not register global Stop key {self.key!r} (Windows error {self.last_error()}). '
                             'Choose another Stop key. No refresh input sent.')
        self.registered=True
        # A streamed press can be down/up between polls or intercepted before
        # WM_HOTKEY arrives. Latch the event before downstream hooks consume it.
        # This callback never suppresses input or rejects injected events.
        self._down={vk for keys in MODIFIER_KEYS.values() for vk in keys
                    if self.api.GetAsyncKeyState(vk)&0x8000}
        self.hook=self.api.SetWindowsHookExW(WH_KEYBOARD_LL,self._hook_callback,self.module,0)
        if not self.hook:
            error=self.last_error()
            self.__exit__()
            raise ValueError(f'Could not start global Stop key event listener (Windows error {error}). No refresh input sent.')
        return self

    def _keyboard_event(self,code,message,pointer):
        if code==0 and message in (WM_KEYDOWN,WM_SYSKEYDOWN,WM_KEYUP,WM_SYSKEYUP):
            event=ctypes.cast(pointer,ctypes.POINTER(KeyboardEvent)).contents
            vk=event.vkCode;down=message in (WM_KEYDOWN,WM_SYSKEYDOWN)
            for keys in MODIFIER_KEYS.values():
                if vk in keys:
                    # Replace an initial generic modifier state with observed
                    # left/right events; accept either Windows key for chords.
                    self._down.discard(keys[0])
                    if down:self._down.add(vk)
                    else:self._down.discard(vk)
                    break
            if down and vk==self.vk and all(
                    any(key in self._down for key in keys)
                    for flag,keys in MODIFIER_KEYS.items() if self.modifiers&flag):
                self._detected=True;self.injected=bool(event.flags&0x10)
                self.detected_by='injected keyboard event' if self.injected else 'keyboard event'
        return self.api.CallNextHookEx(self.hook,code,message,pointer)

    def pressed(self):
        message=w.MSG()
        # Pump the hook's installing thread too. Bound work so a busy queue
        # cannot delay a latched Stop indefinitely.
        for _ in range(64):
            if not self.api.PeekMessageW(ctypes.byref(message),None,0,0,1):break
            if message.message==WM_HOTKEY and message.wParam==HOTKEY_ID:
                self._detected=True
                if not self.detected_by:self.detected_by='Windows hotkey message'
            else:
                self.api.TranslateMessage(ctypes.byref(message))
                self.api.DispatchMessageW(ctypes.byref(message))
            if self._detected:return True
        if self._detected:return True
        # Catch an already-held key as well. Use only the documented down bit;
        # the "pressed since last query" bit can be consumed by other apps.
        pressed=bool(self.api.GetAsyncKeyState(self.vk)&0x8000) and all(
            any(self.api.GetAsyncKeyState(vk)&0x8000 for vk in keys)
            for flag,keys in MODIFIER_KEYS.items() if self.modifiers&flag)
        if pressed:self.detected_by='held key state'
        return pressed

    def __exit__(self,*unused):
        if self.hook:
            self.api.UnhookWindowsHookEx(self.hook)
            self.hook=None
        if self.registered:
            self.api.UnregisterHotKey(None,HOTKEY_ID)
            self.registered=False

def stop_key_monitor(key):
    if os.name=='nt':return WindowsStopKey(key)
    # Keep the upstream hook implementation available on other platforms.
    from contextlib import contextmanager
    import keyboard
    @contextmanager
    def legacy():
        class Monitor:
            backend='keyboard hook'
            def pressed(self):return keyboard.is_pressed(key)
        yield Monitor()
    return legacy()
