"""Global Stop key on macOS: a listen-only keyboard event tap.

Same interface as WindowsStopKey and X11StopKey (context manager, pressed(),
backend, detected_by). The tap only listens: no key is blocked or changed.
macOS requires Input Monitoring permission for the app running this tool;
without it the tap cannot be created and the session refuses to start,
because the Stop key is a safety control.
"""
import threading

# The GUI allows Esc or one of these characters (STOP_KEY_CHARACTERS).
# Typed characters are compared, so any keyboard layout works; this US
# (ANSI) key-code table only backs up the "key already held" check.
ESCAPE = 53
US_KEY_CODES = {
    'a': 0, 's': 1, 'd': 2, 'f': 3, 'h': 4, 'g': 5, 'z': 6, 'x': 7, 'c': 8, 'v': 9, 'b': 11, 'q': 12,
    'w': 13, 'e': 14, 'r': 15, 'y': 16, 't': 17, '1': 18, '2': 19, '3': 20, '4': 21, '6': 22, '5': 23,
    '9': 25, '7': 26, '8': 28, '0': 29, ']': 30, 'o': 31, 'u': 32, '[': 33, 'i': 34, 'p': 35, 'l': 37,
    'j': 38, "'": 39, 'k': 40, ';': 41, ',': 43, '/': 44, 'n': 45, 'm': 46, '.': 47, '`': 50,
}
STOP_CHARACTERS = frozenset(US_KEY_CODES)


def mac_stop_key(key):
    """Return (character or None, key code) for a supported Stop key."""
    name = (key or '').lower().strip()
    if name in ('esc', 'escape'):
        return None, ESCAPE
    if len(name) == 1 and name in STOP_CHARACTERS:
        return name, US_KEY_CODES[name]
    raise ValueError('Choose Esc or a single letter, digit or one of / . , \' ; [ ] ` as the Stop key.')


class MacStopKey:
    backend = 'macOS keyboard event tap (listen only)'

    def __init__(self, key, *, tap=None):
        self.key = key
        self.character, self.code = mac_stop_key(key)
        self.tap = tap or QuartzKeyTap()
        self._detected = False
        self.detected_by = ''
        self.injected = False

    def __enter__(self):
        self.tap.start(self._event)
        return self

    def _event(self, code, characters):
        if self.character is None:
            hit = code == ESCAPE
        else:
            hit = (characters or '').lower() == self.character
        if hit:
            self._detected = True
            self.detected_by = 'keyboard event'

    def pressed(self):
        if self._detected:
            return True
        error = self.tap.error()
        if error is not None:
            raise ValueError(f'The global Stop key listener failed ({error}). Session stopped.')
        if self.tap.held(self.code):
            self.detected_by = 'held key state'
            return True
        return False

    def __exit__(self, *unused):
        self.tap.stop()


class QuartzKeyTap:
    """The real event tap on its own run-loop thread (pyobjc)."""

    def __init__(self):
        import Quartz
        self.Q = Quartz
        self._thread = None
        self._loop = None
        self._tap = None
        self._error = None

    def start(self, handler):
        Q = self.Q
        preflight = getattr(Q, 'CGPreflightListenEventAccess', None)
        if preflight is not None and not preflight():
            raise ValueError('macOS has not granted Input Monitoring to the app running this tool, so the global '
                             'Stop key cannot work. Allow it in System Settings > Privacy & Security > Input '
                             'Monitoring, then restart this tool. No refresh input sent.')
        armed = threading.Event()

        def callback(proxy, kind, event, refcon):
            if kind in (Q.kCGEventTapDisabledByTimeout, Q.kCGEventTapDisabledByUserInput):
                Q.CGEventTapEnable(self._tap, True)     # macOS paused the tap; resume listening
                return event
            if kind == Q.kCGEventKeyDown:
                try:
                    code = Q.CGEventGetIntegerValueField(event, Q.kCGKeyboardEventKeycode)
                    _, characters = Q.CGEventKeyboardGetUnicodeString(event, 4, None, None)
                    handler(int(code), characters)
                except Exception as error:  # never let a callback error kill the tap silently
                    self._error = error
            return event

        def run():
            try:
                self._tap = Q.CGEventTapCreate(Q.kCGSessionEventTap, Q.kCGHeadInsertEventTap,
                                               Q.kCGEventTapOptionListenOnly,
                                               Q.CGEventMaskBit(Q.kCGEventKeyDown), callback, None)
                if self._tap is None:
                    raise ValueError('macOS refused the keyboard listener (Input Monitoring not allowed?)')
                source = Q.CFMachPortCreateRunLoopSource(None, self._tap, 0)
                self._loop = Q.CFRunLoopGetCurrent()
                Q.CFRunLoopAddSource(self._loop, source, Q.kCFRunLoopCommonModes)
                Q.CGEventTapEnable(self._tap, True)
                armed.set()
                Q.CFRunLoopRun()
            except Exception as error:
                self._error = error
            finally:
                armed.set()

        self._thread = threading.Thread(target=run, name='E7 Stop key', daemon=True)
        self._thread.start()
        if not armed.wait(5) or self._error is not None or not self._thread.is_alive():
            error = self._error or 'it did not start'
            self.stop()
            raise ValueError(f'The global Stop key listener failed ({error}). No refresh input sent.')

    def error(self):
        if self._error is not None:
            return self._error
        if self._thread is not None and not self._thread.is_alive():
            return 'the listener stopped'
        return None

    def held(self, code):
        Q = self.Q
        return bool(Q.CGEventSourceKeyState(Q.kCGEventSourceStateHIDSystemState, code))

    def stop(self):
        Q = self.Q
        if self._tap is not None:
            Q.CGEventTapEnable(self._tap, False)
        if self._loop is not None:
            Q.CFRunLoopStop(self._loop)
        if self._thread is not None:
            self._thread.join(2)
        self._tap = self._loop = None
