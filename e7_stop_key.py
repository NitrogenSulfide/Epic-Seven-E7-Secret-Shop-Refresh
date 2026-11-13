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

X11_NAMED_KEYS = {'esc':'Escape','escape':'Escape','space':'space','enter':'Return','return':'Return',
    'tab':'Tab','backspace':'BackSpace','delete':'Delete','insert':'Insert','home':'Home','end':'End',
    'page up':'Prior','page down':'Next','up':'Up','down':'Down','left':'Left','right':'Right',
    'pause':'Pause','caps lock':'Caps_Lock','num lock':'Num_Lock','scroll lock':'Scroll_Lock',
    'print screen':'Print'}
X11_CHARACTERS = {'`':'grave','/':'slash','.':'period',',':'comma',"'":'apostrophe',';':'semicolon',
    '[':'bracketleft',']':'bracketright','-':'minus','=':'equal','\\':'backslash',' ':'space'}
X11_MODIFIERS = {'ctrl':('Control_L','Control_R'),'control':('Control_L','Control_R'),'alt':('Alt_L','Alt_R'),
    'shift':('Shift_L','Shift_R'),'win':('Super_L','Super_R'),'windows':('Super_L','Super_R')}


def x11_stop_key(key):
    """Return (key keysym names, [modifier keysym-name groups]) for an X11 keyboard."""
    parts=key.lower().strip().split('+') if key!='+' else ['+']
    groups=[]
    for part in parts[:-1]:
        if part.strip() not in X11_MODIFIERS:raise ValueError('Choose a supported Stop key.')
        groups.append(X11_MODIFIERS[part.strip()])
    name=parts[-1].strip() if parts[-1].strip() else parts[-1]
    if name in X11_NAMED_KEYS:return X11_NAMED_KEYS[name],groups
    if re.fullmatch(r'f(?:[1-9]|1\d|2[0-4])',name):return name.upper(),groups
    if len(name)==1:
        if name.isalnum() and name.isascii():return name,groups
        if name in X11_CHARACTERS:return X11_CHARACTERS[name],groups
    raise ValueError('Choose a supported Stop key.')


class X11StopKey:
    """Global Stop key on an X11 desktop.

    The X RECORD extension reports every key press on the display, including
    injected (XTEST) ones, without grabbing the key from other apps; the
    keymap query catches a key that is already held. Nothing is suppressed.
    On Wayland only keys typed into X (XWayland) apps are seen."""

    backend='X11 RECORD key listener'

    def __init__(self,key,*,display=None):
        from Xlib import XK, display as xdisplay
        self.key=key
        name,groups=x11_stop_key(key)
        self._open=display or xdisplay.Display
        try:
            self.control=self._open()
        except Exception as error:
            raise ValueError(f'Could not open the X display for the Stop key ({error}). No refresh input sent.') from error
        def codes(keysym_name):
            keysym=XK.string_to_keysym(keysym_name)
            return {code for code,_ in self.control.keysym_to_keycodes(keysym)} if keysym else set()
        self.codes=codes(name)
        if not self.codes:
            self.control.close()
            raise ValueError('The Stop key is unavailable on this keyboard layout.')
        self.modifier_codes=[set().union(*(codes(n) for n in group)) for group in groups]
        self._down=set();self._detected=False;self.detected_by='';self.injected=False
        self.record=None;self.context=None;self.thread=None;self._error=None

    def __enter__(self):
        import threading
        from Xlib.ext import record
        if not self.control.has_extension('RECORD'):
            self.__exit__()
            raise ValueError('This X server has no RECORD extension, so the global Stop key cannot work. No refresh input sent.')
        self.record=self._open()
        self.context=self.control.record_create_context(0,[record.AllClients],[{
            'core_requests':(0,0),'core_replies':(0,0),'ext_requests':(0,0,0,0),'ext_replies':(0,0,0,0),
            'delivered_events':(0,0),'device_events':(2,3),'errors':(0,0),
            'client_started':False,'client_died':False}])
        self.control.sync()
        keymap=self.control.query_keymap()
        self._down={code for group in self.modifier_codes for code in group if keymap[code//8]>>(code%8)&1}
        # Armed only once the server acknowledges with StartOfData.
        self._armed=threading.Event()
        def listen():
            try:
                self.record.record_enable_context(self.context,self._reply)
            except Exception as error:
                self._error=error
            finally:
                self._armed.set()
        self.thread=threading.Thread(target=listen,name='E7 Stop key',daemon=True)
        self.thread.start()
        if not self._armed.wait(5) or self._error is not None or not self.thread.is_alive():
            error=self._error or 'it did not start'
            self.__exit__()
            raise ValueError(f'The global Stop key listener failed ({error}). No refresh input sent.')
        return self

    def _reply(self,reply):
        from Xlib.ext import record
        from Xlib.protocol import rq
        if reply.category==record.StartOfData:
            self._armed.set();return
        if reply.category!=record.FromServer or reply.client_swapped or not len(reply.data):return
        data=reply.data
        while len(data):
            event,data=rq.EventField(None).parse_binary_value(data,self.record.display,None,None)
            self._event(event.type,event.detail)

    def _event(self,kind,code):
        down=kind==2
        if any(code in group for group in self.modifier_codes):
            (self._down.add if down else self._down.discard)(code)
        if down and code in self.codes and all(self._down&group for group in self.modifier_codes):
            self._detected=True;self.detected_by='keyboard event'

    def pressed(self):
        if self._detected:return True
        if self._error is not None:
            raise ValueError(f'The global Stop key listener failed ({self._error}). Session stopped.')
        keymap=self.control.query_keymap()
        held=lambda codes:any(keymap[c//8]>>(c%8)&1 for c in codes)
        if held(self.codes) and all(held(group) for group in self.modifier_codes):
            self.detected_by='held key state';return True
        return False

    def __exit__(self,*unused):
        if self.context is not None:
            try:
                self.control.record_disable_context(self.context);self.control.sync()
            except Exception:
                pass
            if self.thread is not None:self.thread.join(2)
            try:
                self.control.record_free_context(self.context);self.control.sync()
            except Exception:
                pass
            self.context=None
        for connection in (self.record,self.control):
            if connection is not None:
                try:connection.close()
                except Exception:pass
        self.record=self.control=None


def stop_key_monitor(key):
    if os.name=='nt':return WindowsStopKey(key)
    if os.environ.get('WAYLAND_DISPLAY') or os.environ.get('XDG_SESSION_TYPE','').lower()=='wayland':
        # Under XWayland, RECORD only sees keys typed into X applications.
        raise ValueError('The global Stop key needs an X11 session; Wayland is not supported yet. '
                         'Log in to an X11 session. No refresh input sent.')
    if not os.environ.get('DISPLAY'):
        raise ValueError('The global Stop key needs an X11 desktop (DISPLAY is not set). No refresh input sent.')
    return X11StopKey(key)
