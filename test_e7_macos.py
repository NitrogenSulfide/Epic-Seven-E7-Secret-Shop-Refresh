import io
from contextlib import redirect_stdout
import unittest

from PIL import Image

import e7_macos as mac
from e7_native_mouse import MouseStopped, MouseRecheckRequired

# A 16:9 game area plus a 32 pt title bar, at 2x: 1680 x 945 pt game.
GAME = mac.MacWindow(7561, 86053, 'Epic Seven', 0, (100., 50., 1680., 977.))
OTHER = mac.MacWindow(42, 500, 'Finder', 0, (0., 0., 800., 600.))
MENU = mac.MacWindow(3, 1, 'Window Server', 24, (0., 0., 1920., 30.))


class Clock:
    def __init__(self):
        self.now = 1000.

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += max(seconds, .001)


class FakeMac:
    def __init__(self, windows=None, *, title_px=64, scale=2, follow=True):
        self.window_sets = [windows or [MENU, GAME, OTHER]]
        self.title_px, self.scale, self.follow = title_px, scale, follow
        self.pointer = (5., 5.)
        self.events = []
        self.permissions = []
        self.title_colour, self.header_colour = 250, (30, 40, 60)
        self.fail_up = 0
        self.activated = []

    def activate(self, pid):
        self.activated.append(pid)

    @property
    def stack(self):
        return self.window_sets[0]

    def missing_permissions(self):
        return self.permissions

    def windows(self):
        # Each call may advance to a queued window arrangement.
        current = self.window_sets[0]
        if len(self.window_sets) > 1:
            self.window_sets.pop(0)
        return current

    def cursor(self):
        return self.pointer

    def post(self, kind, point):
        if kind == 'up' and self.fail_up:
            self.fail_up -= 1
            raise RuntimeError('CGEventPost failed')
        self.events.append((kind, tuple(point)))
        if self.follow:
            self.pointer = tuple(point)

    def capture(self, window):
        w, h = round(window.bounds[2]*self.scale), round(window.bounds[3]*self.scale)
        image = Image.new('RGB', (w, h), self.header_colour)
        # Game art has texture right from its first row.
        for x in range(0, w, 16):
            image.paste((90, 110, 140), (x, self.title_px, x+6, h))
        t = self.title_colour
        image.paste((t, t, t), (0, 0, w, self.title_px))
        image.paste((0, 0, 0), (w-6, 0, w, 12))           # transparent rounded corner
        image.paste((120, 90, 200), (w//4, h//3, w//2, h//2))
        return image


def make(backend=None, active=lambda: True):
    backend = backend or FakeMac()
    clock = Clock()
    with redirect_stdout(io.StringIO()):
        transport = mac.MacMouse(active, backend=backend, clock=clock, sleep=clock.sleep)
    return transport, backend, clock


def quiet(function, *args, **kwargs):
    out = io.StringIO()
    with redirect_stdout(out):
        result = function(*args, **kwargs)
    return result, out.getvalue()


class FindWindowTest(unittest.TestCase):
    def test_single_game_window(self):
        self.assertEqual(mac.find_game_window([MENU, OTHER, GAME]), GAME)

    def test_refuses_missing_or_duplicate_game(self):
        with self.assertRaisesRegex(ValueError, 'not open'):
            mac.find_game_window([MENU, OTHER])
        twin = mac.MacWindow(8000, 86053, 'Epic Seven', 0, (0., 0., 900., 600.))
        with self.assertRaisesRegex(ValueError, 'More than one'):
            mac.find_game_window([GAME, twin])

    def test_start_brings_the_game_forward_without_input(self):
        transport, backend, _ = make()
        self.assertEqual(backend.activated, [GAME.pid])
        self.assertEqual(backend.events, [])

    def test_missing_permission_refuses_before_anything(self):
        backend = FakeMac()
        backend.permissions = ['Accessibility']
        with self.assertRaisesRegex(ValueError, 'Accessibility.*No input sent'):
            make(backend)
        self.assertEqual(backend.events, [])
        self.assertEqual(backend.activated, [], 'nothing is brought forward without permissions')


class CaptureTest(unittest.TestCase):
    def test_title_bar_is_measured_and_cropped(self):
        transport, _, _ = make()
        image, _ = quiet(transport.screenshot)
        self.assertEqual(transport.title_px, 64)
        self.assertEqual(image.size, (3360, 1890))
        self.assertEqual(transport.view, (100., 82., 1780., 1027.))

    def test_title_bar_is_not_assumed(self):
        transport, _, _ = make(FakeMac(title_px=56))
        image, _ = quiet(transport.screenshot)
        self.assertEqual(transport.title_px, 56)
        self.assertEqual(image.height, 1954-56)

    def test_wide_window_is_refused_with_exact_size(self):
        wide = mac.MacWindow(7561, 86053, 'Epic Seven', 0, (0., 30., 1920., 985.))
        transport, _, _ = make(FakeMac([wide]))
        with self.assertRaisesRegex(MouseStopped, r'16:9.*1694 x 985 points.*now 1920 x 985.*No input sent'):
            quiet(transport.screenshot)

    def test_blank_capture_stops(self):
        backend = FakeMac()
        backend.capture = lambda window: Image.new('RGB', (3360, 1954), (0, 0, 0))
        transport, _, _ = make(backend)
        with self.assertRaisesRegex(MouseStopped, 'blank'):
            quiet(transport.screenshot)

    def test_capture_waits_while_covered_then_resumes(self):
        cover = mac.MacWindow(9, 9, 'Notes', 0, (500., 400., 300., 300.))
        backend = FakeMac()
        backend.window_sets = [[cover, GAME], [cover, GAME], [MENU, GAME, OTHER]]
        transport, _, _ = make(backend)
        image, out = quiet(transport.screenshot)
        self.assertIn('E7GUI_MOUSE_PAUSED', out)
        self.assertIn('E7GUI_MOUSE_RESUMED', out)
        self.assertEqual(image.size, (3360, 1890))


class ClickTest(unittest.TestCase):
    def setUp(self):
        self.transport, self.backend, self.clock = make()
        quiet(self.transport.screenshot)

    def test_click_maps_game_space_to_global_points(self):
        point, out = quiet(self.transport.click, 960, 540)
        self.assertEqual(point, (940., 554.5))
        kinds = [k for k, _ in self.backend.events]
        self.assertEqual(kinds[-2:], ['down', 'up'])
        self.assertTrue(all(k == 'move' for k in kinds[:-2]))
        self.assertEqual(self.backend.events[-2][1], (940., 554.5))
        self.assertIn('E7GUI_MOUSE_INPUT', out)

    def test_corners_stay_inside_the_view(self):
        left, top, right, bottom = self.transport.view
        for x, y in ((0, 0), (1919, 1079)):
            px, py = self.transport._point(x, y)
            self.assertTrue(left <= px < right and top <= py < bottom)

    def test_invalid_targets_send_nothing(self):
        for x, y in ((-1, 5), (1920, 5), (5, 1080), (float('nan'), 5)):
            with self.assertRaises(MouseStopped):
                self.transport.click(x, y)
        self.assertEqual(self.backend.events, [])

    def test_no_click_when_pointer_does_not_arrive(self):
        self.backend.follow = False
        with self.assertRaisesRegex(MouseStopped, 'did not move the pointer.*No click sent.*Accessibility'):
            quiet(self.transport.click, 960, 540)
        self.assertNotIn('down', [k for k, _ in self.backend.events])

    def test_not_frontmost_pauses_then_rechecks(self):
        self.backend.window_sets = [[OTHER, GAME], [OTHER, GAME], [GAME, OTHER]]
        with self.assertRaises(MouseRecheckRequired):
            quiet(self.transport.click, 960, 540)
        self.assertEqual(self.backend.events, [])

    def test_lost_focus_for_ten_seconds_stops(self):
        self.backend.window_sets = [[OTHER, GAME]]
        with self.assertRaisesRegex(MouseStopped, 'not the active window.*10 seconds'):
            quiet(self.transport.click, 960, 540)
        self.assertEqual(self.backend.events, [])

    def test_covered_target_pauses(self):
        cover = mac.MacWindow(9, 9, 'Notification Center', 23, (900., 500., 100., 100.))
        self.backend.window_sets = [[cover, MENU, GAME]]
        with self.assertRaisesRegex(MouseStopped, 'covered by Notification Center'):
            quiet(self.transport.click, 960, 540)
        self.assertEqual(self.backend.events, [])

    def test_menu_bar_above_the_game_is_not_coverage(self):
        quiet(self.transport.click, 960, 540)
        self.assertEqual(self.backend.events[-1][0], 'up')

    def test_moved_or_resized_window_stops(self):
        moved = mac.MacWindow(GAME.id, GAME.pid, GAME.owner, 0, (120., 50., 1680., 977.))
        self.backend.window_sets = [[moved]]
        with self.assertRaisesRegex(MouseStopped, 'moved, resized'):
            quiet(self.transport.click, 960, 540)

    def test_closed_window_stops(self):
        self.backend.window_sets = [[OTHER]]
        with self.assertRaisesRegex(MouseStopped, 'closed'):
            quiet(self.transport.click, 960, 540)

    def test_stopped_session_sends_nothing(self):
        running = [True]
        transport, backend, _ = make(active=lambda: running[0])
        quiet(transport.screenshot)
        running[0] = False
        with self.assertRaisesRegex(MouseStopped, 'Mouse session stopped'):
            quiet(transport.click, 10, 10)
        self.assertEqual(backend.events, [])


class TitleBarTest(unittest.TestCase):
    def frame(self, title, header, *, textured=True, title_px=64):
        image = Image.new('RGB', (3360, 1954), header)
        if textured:
            for x in range(0, 3360, 16):
                image.paste((header[0]+40, header[1]+40, header[2]+40), (x, title_px, x+6, 1954))
        image.paste(title, (0, 0, 3360, title_px))
        image.paste((0, 0, 0), (3354, 0, 3360, 12))
        return image

    def test_light_and_dark_title_bars(self):
        self.assertEqual(mac.measure_title_bar(self.frame((250, 250, 250), (30, 40, 60)), 2), 64)
        self.assertEqual(mac.measure_title_bar(self.frame((40, 40, 40), (30, 30, 30)), 2), 64)
        self.assertEqual(mac.measure_title_bar(self.frame((40, 40, 40), (38, 38, 38)), 2), 64)

    def test_band_that_runs_into_a_flat_game_edge_is_refused(self):
        # A dark title bar over a flat header of the same colour has no
        # visible boundary; guessing would offset every click.
        with self.assertRaisesRegex(MouseStopped, 'title bar ends'):
            mac.measure_title_bar(self.frame((40, 40, 40), (40, 40, 40), textured=False), 2)

    def test_band_out_of_range_is_refused(self):
        with self.assertRaisesRegex(MouseStopped, 'title bar ends'):
            mac.measure_title_bar(self.frame((250, 250, 250), (30, 40, 60), title_px=6), 2)

    def test_size_advice_only_shrinks_one_side(self):
        # Too wide (the real full-size window on the second display): narrow it.
        self.assertEqual(mac.size_advice((1920, 1050), 32), (1809, 1050))
        # Already 16:9: unchanged.
        self.assertEqual(mac.size_advice((1680, 977), 32), (1680, 977))
        # Too tall: lower it.
        self.assertEqual(mac.size_advice((1200, 900), 32), (1200, 707))
        for window in ((1920, 1050), (1920, 985), (800, 1000), (2560, 1415), (700, 420)):
            width, height = mac.size_advice(window, 32)
            self.assertLessEqual(width, window[0])
            self.assertLessEqual(height, window[1])
            self.assertAlmostEqual(width/(height-32), 16/9, delta=.035)


class CoverageTest(unittest.TestCase):
    def test_full_screen_system_container_is_not_coverage(self):
        container = mac.MacWindow(5, 2, 'Dock', 20, (0., 0., 1920., 1080.))
        transport, backend, _ = make(FakeMac([container, MENU, GAME]))
        quiet(transport.screenshot)
        quiet(transport.click, 960, 540)
        self.assertEqual(backend.events[-1][0], 'up')

    def test_visible_dock_over_the_game_is_coverage(self):
        dock = mac.MacWindow(5, 2, 'Dock', 20, (500., 900., 900., 80.))
        transport, backend, _ = make(FakeMac([dock, MENU, GAME]))
        with self.assertRaisesRegex(MouseStopped, 'covered by Dock'):
            quiet(transport.screenshot)
        self.assertEqual(backend.events, [])

    def test_coverage_details_are_reported(self):
        # A floating panel: the game stays the frontmost normal window but is covered.
        cover = mac.MacWindow(9, 9, 'Notes', 3, (800., 400., 300., 300.))   # over the game's centre
        backend = FakeMac()
        # The first list is read when the transport starts.
        backend.window_sets = [[GAME], [cover, GAME], [MENU, GAME, OTHER]]
        transport, _, _ = make(backend)
        _, out = quiet(transport.screenshot)
        self.assertIn('E7GUI_MOUSE_COVERAGE', out)
        self.assertIn('"owner": "Notes"', out)


class ReleaseTest(unittest.TestCase):
    def setUp(self):
        self.transport, self.backend, _ = make()
        quiet(self.transport.screenshot)

    def test_mouse_up_is_retried_once(self):
        self.backend.fail_up = 1
        quiet(self.transport.click, 960, 540)
        self.assertEqual(self.backend.events[-1][0], 'up')

    def test_mouse_up_failing_twice_stops_clearly(self):
        self.backend.fail_up = 2
        with self.assertRaisesRegex(MouseStopped, 'mouse-up'):
            quiet(self.transport.click, 960, 540)

    def test_release_failure_does_not_hide_the_original_error(self):
        stacks = iter([[MENU, GAME]]*40 + [[OTHER, GAME]]*200)
        self.backend.windows = lambda: next(stacks)
        self.backend.fail_up = 2
        with self.assertRaisesRegex(MouseStopped, 'held action'):
            quiet(self.transport.drag, 1000, 800, 1000, 300, duration=.32)

    def test_release_button_after_a_forced_stop(self):
        self.assertTrue(self.transport.release_button())
        self.assertEqual(self.backend.events[-1], ('up', self.backend.pointer))


class UserMovementTest(unittest.TestCase):
    def test_nudge_during_the_glide_rechecks_instead_of_stopping(self):
        transport, backend, _ = make()
        quiet(transport.screenshot)
        real_post = backend.post
        def post(kind, point):
            real_post(kind, point)
            if kind == 'move':
                backend.pointer = (point[0]+40, point[1]+25)   # the user's hand on the mouse
        backend.post = post
        with self.assertRaises(MouseRecheckRequired):
            quiet(transport.click, 960, 540)
        self.assertNotIn('down', [k for k, _ in backend.events], 'no click while the user moved the pointer')

    def test_pause_while_user_moves_then_continue_from_rest(self):
        transport, backend, clock = make()
        quiet(transport.screenshot)
        quiet(transport.click, 960, 540)
        sent = len(backend.events)
        moves = iter([(300., 300.), (320., 310.), (340., 320.)])
        def cursor():
            # The user drags the pointer for a moment, then lets it rest.
            backend.pointer = next(moves, backend.pointer)
            return backend.pointer
        backend.cursor = cursor
        with self.assertRaises(MouseRecheckRequired):
            _, out = quiet(transport.click, 100, 100)
        self.assertEqual(len(backend.events), sent, 'no input while the user was moving')
        # Once rested, the next action goes ahead from where the user left it.
        backend.cursor = lambda: backend.pointer
        quiet(transport.click, 100, 100)
        self.assertEqual(backend.events[-1][0], 'up')

    def test_own_glide_is_not_mistaken_for_the_user(self):
        transport, backend, clock = make()
        quiet(transport.screenshot)
        quiet(transport.click, 200, 200)          # the pointer now rests where it was put
        posted = []                              # (time, point) of each posted event
        real_post = backend.post
        def post(kind, point):
            posted.append((clock.now, tuple(point)))
            real_post(kind, point)
        def cursor():
            # The real pointer trails a fresh event by one step for ~30 ms.
            if len(posted) >= 2 and clock.now - posted[-1][0] < .03:
                return posted[-2][1]
            return posted[-1][1] if posted else backend.pointer
        backend.post, backend.cursor = post, cursor
        _, out = quiet(transport.click, 1800, 1000)
        self.assertNotIn('E7GUI_MOUSE_PAUSED', out)
        self.assertEqual(backend.events[-1][0], 'up')


class DragTest(unittest.TestCase):
    def setUp(self):
        self.transport, self.backend, _ = make()
        quiet(self.transport.screenshot)

    def test_drag_presses_moves_and_releases_at_the_end(self):
        quiet(self.transport.drag, 1000, 800, 1000, 300, duration=.32)
        kinds = [k for k, _ in self.backend.events]
        down = kinds.index('down')
        self.assertTrue(all(k == 'move' for k in kinds[:down]))
        self.assertIn('dragged', kinds[down:])
        self.assertEqual(kinds[-1], 'up')
        self.assertEqual(self.backend.events[-1][1], self.transport._point(1000, 300))

    def test_lost_focus_mid_drag_stops_and_still_releases(self):
        stacks = iter([[MENU, GAME]]*40 + [[OTHER, GAME]]*200)
        self.backend.windows = lambda: next(stacks)
        with self.assertRaisesRegex(MouseStopped, 'held action'):
            quiet(self.transport.drag, 1000, 800, 1000, 300, duration=.32)
        self.assertEqual(self.backend.events[-1][0], 'up', 'the button is never left down')

    def test_invalid_duration_sends_nothing(self):
        with self.assertRaises(MouseStopped):
            self.transport.drag(1000, 800, 1000, 300, duration=1)
        self.assertEqual(self.backend.events, [])


class GlideTest(unittest.TestCase):
    def test_fractional_points_end_exactly_on_target(self):
        transport, backend, _ = make()
        quiet(transport.screenshot)
        point, _ = quiet(transport.click, 960, 540)
        self.assertEqual(point, (940., 554.5))
        self.assertEqual(backend.events[-2], ('down', (940., 554.5)))
        moves = [p for k, p in backend.events if k == 'move']
        self.assertEqual(moves[-1], (940., 554.5))


class EngineIntegrationTest(unittest.TestCase):
    def test_shared_engine_accepts_the_transport(self):
        from e7_mouse_refresh import E7MouseShopRefresh
        transport, backend, _ = make()
        app = E7MouseShopRefresh.__new__(E7MouseShopRefresh)
        app.mouse, app.loop_active = transport, True
        gray, _ = quiet(app.takeScreenshot)
        self.assertEqual(gray.shape, (1080, 1920))
        point, _ = quiet(app.tap, 960, 540)
        self.assertEqual(point, (940., 554.5))


if __name__ == '__main__':
    unittest.main()
