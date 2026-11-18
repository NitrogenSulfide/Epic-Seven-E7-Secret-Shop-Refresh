"""Foreground control of Epic Seven's iPad app on Apple silicon Macs.

Capture uses ScreenCaptureKit; input uses real, system-wide pointer events
(CGEventPost to the HID tap), so the game must be the frontmost, uncovered
window while input is sent. Events posted to the game's process alone are
ignored by the iPad app (probed on macOS 26.6, 2026-11-15). The transport
mirrors WindowsMouse: screenshot/click/move/drag in 1920 x 1080 game space,
guarded before every capture and every input event.

All macOS calls go through QuartzBackend so tests can use fakes; pyobjc is
imported only when the real back end is created.
"""
from dataclasses import dataclass
import json
import math
import time

from e7_native_mouse import MouseStopped, MouseRecheckRequired, pointer_glide

GAME_OWNER = 'Epic Seven'
PAUSE_LIMIT = 10
ASPECT_TOLERANCE = .035          # same as normalize_game_frame's 16:9 check
POINTER_TOLERANCE = 3            # points
USER_IDLE = 1.5                  # seconds the pointer must rest before resuming
# System processes whose full-screen, click-through containers sit above
# normal windows. Their small visible windows (a notification banner, the
# Dock itself) still count as coverage; only near-full-screen ones are ignored.
SYSTEM_OVERLAY_OWNERS = frozenset({'Window Server', 'Dock', 'Control Center', 'Notification Center',
                                   'SystemUIServer', 'WindowManager'})


@dataclass(frozen=True)
class MacWindow:
    """One on-screen window from the window server, in global display points."""
    id: int
    pid: int
    owner: str
    layer: int
    bounds: tuple            # (x, y, width, height)
    alpha: float = 1.

    def contains(self, point):
        x, y, w, h = self.bounds
        return x <= point[0] < x+w and y <= point[1] < y+h

    def covers_most_of(self, other):
        x, y, w, h = self.bounds
        ox, oy, ow, oh = other.bounds
        overlap = max(0, min(x+w, ox+ow)-max(x, ox)) * max(0, min(y+h, oy+oh)-max(y, oy))
        return ow*oh > 0 and overlap >= .95*ow*oh


def find_game_window(windows):
    """The single normal-layer Epic Seven window, or a clear refusal."""
    games = [w for w in windows if w.owner == GAME_OWNER and w.layer == 0 and w.bounds[2] > 50 and w.bounds[3] > 50]
    if not games:
        raise ValueError('Epic Seven is not open on this Mac, or its window is minimized or on another Space. '
                         'Open the game, then try again. No input sent.')
    if len(games) > 1:
        raise ValueError('More than one Epic Seven window is open. Close the extra one, then try again. No input sent.')
    return games[0]


def measure_title_bar(image, scale):
    """Height in pixels of the window's title bar, measured from the capture.

    The bar is a flat band (light or dark mode). Traffic lights and the title
    sit at its left and the window's rounded corners at its ends, so only 60%
    to 95% of each row's width is read; there the band is uniform and matches
    its first row. The band ends at the first row that is not, and that row
    must clearly differ from the band (game art has texture; the bar has
    none). A game edge that continues the band is ambiguous and refused
    rather than guessed: a wrong crop would offset every click."""
    gray = image.convert('L')
    width, height = gray.size
    left, right = int(width*.6), int(width*.95)
    def row(y):
        values = gray.crop((left, y, right, y+1)).tobytes()[::2]
        return sum(values)/len(values), max(values)-min(values)
    band, _ = row(1)
    top = None
    for y in range(1, min(height, round(80*scale))):
        mean, spread = row(y)
        if spread > 12 or abs(mean-band) > 6:
            top = y
            break
    lo, hi = round(10*scale), round(60*scale)
    if top is None or not lo <= top <= hi:
        raise MouseStopped('Could not find where the game window\'s title bar ends. Mouse session stopped. No input sent.')
    # The first game row must stand out from the band, not merely drift.
    edge_mean, edge_spread = row(top)
    if abs(edge_mean-band) <= 6 and edge_spread <= 24:
        raise MouseStopped('Could not find where the game window\'s title bar ends. Mouse session stopped. No input sent.')
    return top


def size_advice(window_pt, title_pt):
    """A window size (points) with a 16:9 game area that surely fits on screen.

    Only one side of the current window shrinks: the current window already
    fits, so a smaller one does too. (The screen's reported usable area was
    wrong on a second display: 1080 pt, though the window could not rise
    above y = 30.)"""
    width, height = round(window_pt[0]), round(window_pt[1])
    game_height = height - title_pt
    if game_height <= 0:
        return width, round(width*9/16 + title_pt)
    if width/game_height > 16/9:
        return math.floor(game_height*16/9), height          # too wide: narrow it
    return width, round(width*9/16 + title_pt)                # too tall: lower it


class PausedGuard:
    """The pause/resume/recheck contract shared with WindowsMouse.guard.

    `problem()` returns why input must wait, or None."""

    def __init__(self, transport):
        self.t = transport

    def run(self, problem, *, action, held):
        t = self.t
        deadline = None
        while True:
            active = t.active()
            t.session_active = t.session_active or active
            if (action or t.session_active) and not active:
                raise MouseStopped('Mouse session stopped.')
            reason, result = problem()
            if reason is None:
                if deadline is not None:
                    print('E7GUI_MOUSE_RESUMED', flush=True)
                    if action:
                        raise MouseRecheckRequired('Focus or target visibility changed before input. '
                                                   'Rechecking the current screen before another action.')
                return result
            if held:
                # Never wait for focus to return while holding a button.
                raise MouseStopped(reason+' Mouse session stopped during a held action.')
            if deadline is None:
                t.pause_revision += 1
                print('E7GUI_MOUSE_PAUSED '+json.dumps({'reason': reason}), flush=True)
                details = getattr(t, 'coverage_details', None)
                if details:
                    print('E7GUI_MOUSE_COVERAGE '+json.dumps(details), flush=True)
                deadline = t.clock()+PAUSE_LIMIT
            if t.clock() >= deadline:
                raise MouseStopped(reason+f' No input sent while paused; it did not clear within {PAUSE_LIMIT} seconds.')
            t.sleep(.1)


class MacMouse:
    """WindowsMouse-compatible transport for the macOS iPad app; uses the real pointer."""

    native_stove = False

    def __init__(self, active, *, backend=None, clock=time.monotonic, sleep=time.sleep):
        self.backend = backend or QuartzBackend()
        missing = self.backend.missing_permissions()
        if missing:
            raise ValueError('macOS has not granted '+' and '.join(missing)+' to the app running this tool. '
                             'Open System Settings > Privacy & Security, allow it, then restart this tool. No input sent.')
        self.target = find_game_window(self.backend.windows())
        # Start is the player's authorization to bring the game forward, as in
        # WindowsMouse. App activation, not a click: nothing reaches the game.
        self.backend.activate(self.target.pid)
        self.active = active
        self.clock, self.sleep = clock, sleep
        self.view = None
        self.title_px = None
        self.session_active = False
        self.pause_revision = 0
        self.coverage_details = None
        self._guard = PausedGuard(self)
        self._placed = None          # where this transport last put the pointer
        self._seen = None            # last pointer position seen, and when it changed
        self._gliding = False
        print(f'Game window: {round(self.target.bounds[2])} x {round(self.target.bounds[3])} pt', flush=True)

    # ---- state ---------------------------------------------------------------

    def _current(self):
        windows = self.backend.windows()
        mine = [w for w in windows if w.id == self.target.id]
        if not mine:
            raise MouseStopped('The game window closed or was minimized. Mouse session stopped.')
        if (mine[0].pid, mine[0].bounds) != (self.target.pid, self.target.bounds):
            raise MouseStopped('The game moved, resized or changed identity. Mouse session stopped.')
        return windows, mine[0]

    def _problem(self, windows, game, point):
        """Why input must wait, or None. `windows` is front-to-back."""
        self.coverage_details = None
        normal = [w for w in windows if w.layer == 0 and w.bounds[2] > 50 and w.bounds[3] > 50 and w.alpha > 0]
        if not normal or normal[0].id != game.id:
            return 'The game is not the active window. Click its title bar to bring it to the front.'
        x, y, wd, ht = game.bounds
        samples = [(x+wd*fx, y+ht*fy) for fx in (.08, .5, .92) for fy in (.12, .5, .92)]
        if point is not None:
            samples.append(point)
        for w in windows:
            if w.id == game.id:
                break
            if w.alpha <= 0 or w.layer < 0:
                continue
            if w.owner in SYSTEM_OVERLAY_OWNERS and w.covers_most_of(game):
                continue          # a click-through system container, not something on top
            hit = next((s for s in samples if w.contains(s)), None)
            if hit is not None:
                self.coverage_details = dict(owner=w.owner, layer=w.layer, bounds=list(w.bounds),
                                             sample=list(hit))
                what = 'The mouse target' if point is not None and hit == point else 'The game view'
                return f'{what} is covered by {w.owner or "another window"}.'
        return self._user_moved()

    def _user_moved(self):
        """Pause while the user moves the pointer instead of fighting them.

        Not checked inside a glide: the cursor can trail the posted events by a
        step. _send checks the pointer after each glide instead."""
        if self._placed is None or self._gliding:
            return None
        now = self.clock()
        here = self.backend.cursor()
        if self._seen is None or math.dist(here, self._seen[0]) > POINTER_TOLERANCE:
            self._seen = (here, now)
        if math.dist(here, self._placed) <= POINTER_TOLERANCE:
            return None
        if now-self._seen[1] < USER_IDLE:
            return 'You are using the mouse. Input waits until it rests for a moment.'
        # The pointer moved but is resting now: continue from where it is.
        self._placed = here
        return None

    def guard(self, *, action=False, point=None, held=False):
        def problem():
            windows, game = self._current()
            return self._problem(windows, game, point), game
        return self._guard.run(problem, action=action, held=held)

    # ---- capture -------------------------------------------------------------

    def _capture_once(self):
        for _ in range(3):
            game = self.guard()
            revision = self.pause_revision
            image = self.backend.capture(game).convert('RGB')
            self.guard()
            if revision == self.pause_revision:
                return game, image
        raise MouseStopped('Game visibility repeatedly changed during capture. No input sent.')

    def screenshot(self):
        game, image = self._capture_once()
        if max(hi-lo for lo, hi in image.getextrema()) < 12:
            # A fade or loading frame can be momentarily blank; look once more.
            self.sleep(.5)
            game, image = self._capture_once()
        x, y, w, h = game.bounds
        scale = image.width/w if w else 0
        if scale <= 0 or abs(image.height-h*scale) > 2 or max(hi-lo for lo, hi in image.getextrema()) < 12:
            raise MouseStopped('The game capture is blank or has the wrong size. Mouse session stopped.')
        if self.title_px is None:
            self.title_px = measure_title_bar(image, scale)
        content = image.crop((0, self.title_px, image.width, image.height))
        aspect = content.width/content.height
        if content.width < 640 or content.height < 360 or abs(aspect-16/9) > ASPECT_TOLERANCE:
            width, height = size_advice((w, h), self.title_px/scale)
            raise MouseStopped(f'Set the game window to a 16:9 shape first, for example {width} x {height} points '
                               f'(now {round(w)} x {round(h)}). Mouse session stopped. No input sent.')
        view = (x, y+self.title_px/scale, x+w, y+h)
        if self.view is not None and self.view != view:
            raise MouseStopped('The game viewport changed. Mouse session stopped.')
        self.view = view
        return content

    # ---- input ---------------------------------------------------------------

    def _point(self, x, y):
        if self.view is None or not all(math.isfinite(v) for v in (x, y)) or not (0 <= x < 1920 and 0 <= y < 1080):
            raise MouseStopped('Invalid Mouse target. No input sent.')
        left, top, right, bottom = self.view
        return (round(left+x*(right-left)/1920, 1), round(top+y*(bottom-top)/1080, 1))

    def click(self, x, y):
        point = self._point(x, y)
        self.guard(action=True, point=point)
        self._send(point, 'click')
        return point

    def move(self, x, y):
        point = self._point(x, y)
        self.guard(action=True, point=point)
        self._send(point, 'move')

    def drag(self, x1, y1, x2, y2, *, duration=.32):
        start, end = self._point(x1, y1), self._point(x2, y2)
        if not math.isfinite(duration) or not .2 <= duration <= .5:
            raise MouseStopped('Invalid Mouse drag duration. No input sent.')
        self.guard(action=True, point=start)
        self.guard(action=True, point=end)
        self._send(start, 'drag', end=end, duration=duration)

    def _travel(self, start, target, kind, *, duration=None, held=False):
        began = self.clock()
        self._gliding = True
        try:
            for destination, elapsed in pointer_glide(start, target, 1, duration=duration):
                wait = began+elapsed-self.clock()
                if wait > 0:
                    self.sleep(wait)
                # Unheld approach can begin outside the game. A held drag checks
                # every point and cancels at once on lost focus.
                self.guard(action=True, point=destination if held else target, held=held)
                self.backend.post(kind, destination)
                self._placed = destination
            if self._placed != target:
                # The shared pointer_glide rounds to whole pixels (Windows);
                # macOS uses fractional points, so finish exactly on target.
                # Kept here so this Mac-only mode changes no shared code.
                self.guard(action=True, point=target, held=held)
                self.backend.post(kind, target)
                self._placed = target
        finally:
            self._gliding = False

    def _arrived(self, start, point):
        """After a glide: on target, or say why not without sending a click."""
        self.sleep(.05)
        here = self.backend.cursor()
        if math.dist(here, point) <= POINTER_TOLERANCE:
            return here
        if math.dist(start, point) > POINTER_TOLERANCE and math.dist(here, start) <= POINTER_TOLERANCE:
            # The pointer never left where it was: macOS dropped the events.
            raise MouseStopped('macOS did not move the pointer onto the game target. No click sent. '
                               'Check that Accessibility is still allowed for this tool.')
        # The pointer went somewhere else: the user moved it. Wait for it to
        # rest, then look at the screen again before any action.
        self._seen = (here, self.clock())
        self.guard(action=True, point=point)
        raise MouseRecheckRequired('The pointer was moved during input. Rechecking the current screen before another action.')

    def _release(self):
        """Mouse-up where the pointer was last put; one retry, like WindowsMouse."""
        for _ in range(2):
            try:
                self.backend.post('up', self._placed)
                return True
            except Exception:
                continue
        return False

    def _send(self, point, kind, *, end=None, duration=None):
        start = self.backend.cursor()
        self._travel(start, point, 'move')
        here = self._arrived(start, point)
        self._placed = point
        self.guard(action=True, point=point)
        print('E7GUI_MOUSE_INPUT '+json.dumps(dict(action=kind, target=list(point), pointer=list(here))), flush=True)
        if kind == 'move':
            return
        if kind == 'drag':
            self.guard(action=True, point=end)
        self.backend.post('down', point)
        released = False
        try:
            if kind == 'drag':
                self.sleep(.04)
                self._travel(point, end, 'dragged', duration=duration, held=True)
                self.sleep(.03)
                self.guard(action=True, point=end, held=True)
                if math.dist(self.backend.cursor(), end) > POINTER_TOLERANCE:
                    raise MouseStopped('The drag did not reach its endpoint. Mouse session stopped.')
            else:
                # Hold a click across several game frames.
                self.sleep(.08)
        finally:
            released = self._release()
            if not released:
                print('E7GUI_MOUSE_STOPPED '+json.dumps({'reason': 'macOS did not accept mouse-up; '
                                                         'the left button may still be held.'}), flush=True)
        if not released:
            raise MouseStopped('macOS did not accept mouse-up. Mouse session stopped.')
        # Input was already delivered. Never retry this action if its
        # visibility changes after mouse-down.
        self.guard(action=True, point=end if kind == 'drag' else point, held=True)

    def release_button(self):
        """Release the left button at the pointer, e.g. after a forced stop."""
        self._placed = self.backend.cursor()
        return self._release()

    def close(self):
        pass


def scan_game_window(backend=None):
    """Read-only, for the GUI's Scan: the game window, or ValueError. No input."""
    return find_game_window((backend or QuartzBackend()).windows())


def release_pointer_button(backend=None):
    """Release the left button at the pointer after a forced engine stop.

    The GUI's macOS stand-in for release_native_button (Windows SendInput)."""
    try:
        backend = backend or QuartzBackend()
        backend.post('up', backend.cursor())
        return True
    except Exception:
        return False


class QuartzBackend:
    """The real macOS calls (pyobjc). Kept thin; logic lives in MacMouse."""

    def __init__(self):
        import Quartz
        import ScreenCaptureKit
        self.Quartz, self.SCK = Quartz, ScreenCaptureKit
        self._filter = None          # (window id, SCContentFilter): enumerating windows is slow

    def missing_permissions(self):
        q = self.Quartz
        missing = []
        if not q.CGPreflightScreenCaptureAccess():
            missing.append('Screen Recording')
        if not q.CGPreflightPostEventAccess():
            missing.append('Accessibility')
        return missing

    def windows(self):
        q = self.Quartz
        infos = q.CGWindowListCopyWindowInfo(
            q.kCGWindowListOptionOnScreenOnly | q.kCGWindowListExcludeDesktopElements, q.kCGNullWindowID)
        result = []
        for info in infos or ():
            b = info.get('kCGWindowBounds') or {}
            result.append(MacWindow(int(info.get('kCGWindowNumber', 0)), int(info.get('kCGWindowOwnerPID', 0)),
                                    str(info.get('kCGWindowOwnerName', '')), int(info.get('kCGWindowLayer', 0)),
                                    (float(b.get('X', 0)), float(b.get('Y', 0)),
                                     float(b.get('Width', 0)), float(b.get('Height', 0))),
                                    float(info.get('kCGWindowAlpha', 1))))
        return result

    def activate(self, pid):
        from AppKit import NSRunningApplication
        app = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
        if app is None:
            raise ValueError('Epic Seven closed. Open the game, then try again. No input sent.')
        app.activateWithOptions_(0)

    def cursor(self):
        point = self.Quartz.CGEventGetLocation(self.Quartz.CGEventCreate(None))
        return (round(point.x, 1), round(point.y, 1))

    def post(self, kind, point):
        q = self.Quartz
        kinds = {'move': q.kCGEventMouseMoved, 'dragged': q.kCGEventLeftMouseDragged,
                 'down': q.kCGEventLeftMouseDown, 'up': q.kCGEventLeftMouseUp}
        event = q.CGEventCreateMouseEvent(None, kinds[kind], q.CGPointMake(*point), q.kCGMouseButtonLeft)
        if event is None:
            raise MouseStopped('macOS could not create a mouse event. No input sent.')
        if kind in ('down', 'up'):
            q.CGEventSetIntegerValueField(event, q.kCGMouseEventClickState, 1)
        q.CGEventPost(q.kCGHIDEventTap, event)

    def _wait(self, start):
        import threading
        done, box = threading.Event(), {}
        def handler(value, error):
            box['value'], box['error'] = value, error
            done.set()
        start(handler)
        if not done.wait(10):
            raise MouseStopped('Screen capture timed out. Check Screen Recording permission. No input sent.')
        if box['error'] is not None:
            raise MouseStopped(f'Screen capture failed: {box["error"]}. No input sent.')
        return box['value']

    def _content_filter(self, window):
        if self._filter is not None and self._filter[0] == window.id:
            return self._filter[1]
        sck = self.SCK
        content = self._wait(lambda h: sck.SCShareableContent
                             .getShareableContentExcludingDesktopWindows_onScreenWindowsOnly_completionHandler_(True, True, h))
        match = next((w for w in content.windows() if int(w.windowID()) == window.id), None)
        if match is None:
            raise MouseStopped('Screen capture cannot see the game window. Mouse session stopped.')
        self._filter = (window.id, sck.SCContentFilter.alloc().initWithDesktopIndependentWindow_(match))
        return self._filter[1]

    def capture(self, window):
        try:
            return self._capture(window, self._content_filter(window))
        except MouseStopped:
            # The cached filter may be stale (window recreated): look it up once more.
            self._filter = None
            return self._capture(window, self._content_filter(window))

    def _capture(self, window, flt):
        from PIL import Image
        q, sck = self.Quartz, self.SCK
        scale = float(flt.pointPixelScale())
        config = sck.SCStreamConfiguration.alloc().init()
        config.setWidth_(round(window.bounds[2]*scale))
        config.setHeight_(round(window.bounds[3]*scale))
        config.setShowsCursor_(False)
        image = self._wait(lambda h: sck.SCScreenshotManager
                           .captureImageWithFilter_configuration_completionHandler_(flt, config, h))
        width, height = q.CGImageGetWidth(image), q.CGImageGetHeight(image)
        context = q.CGBitmapContextCreate(None, width, height, 8, width*4, q.CGColorSpaceCreateDeviceRGB(),
                                          q.kCGImageAlphaNoneSkipLast)
        q.CGContextDrawImage(context, q.CGRectMake(0, 0, width, height), image)
        data = q.CGBitmapContextGetData(context).as_buffer(width*height*4)
        return Image.frombuffer('RGBX', (width, height), bytes(data), 'raw', 'RGBX', 0, 1).convert('RGB')
