"""Fake BlueStacks config, Win32 windows and input; no emulator or live ADB."""
import ctypes
import os
from ctypes import wintypes as w
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image, ImageDraw
from e7_connection import AdbEndpoint, bluestacks_endpoints, check_connection
from e7_native_mouse import (WindowsMouse, MouseStopped, MouseElevationRequired,
    MousePermissionCheckFailed, process_is_elevated, require_mouse_permissions, verify_native_target)
from e7_windows_capture import GameWindow, WindowsCapture
from e7_window_preview import capture_selected
from e7_frame import normalize_game_frame
from test_e7_connection import response, GAME, LAUNCHER

CONFIG = '''bst.enable_adb_access="1"
bst.instance.Nougat32.display_name="BlueStacks App Player"
bst.instance.Nougat32.adb_port="5555"
bst.instance.Nougat32.status.adb_port="5555"
bst.instance.Tiramisu64.display_name="BlueStacks App Player 2"
bst.instance.Tiramisu64.adb_port="5555"
bst.instance.Tiramisu64.status.adb_port="5556"
'''
PLAYER = 'BlueStacks App Player 2'
ENDPOINT = AdbEndpoint(PLAYER, '127.0.0.1:5556')


class EndpointTests(unittest.TestCase):
    def test_only_open_enabled_player_uses_active_instance_port(self):
        self.assertEqual(bluestacks_endpoints(CONFIG, (PLAYER,)), (ENDPOINT,))
        self.assertEqual(bluestacks_endpoints(CONFIG, ('BlueStacks Multi Instance Manager',)), ())
        self.assertEqual(bluestacks_endpoints(CONFIG.replace('access="1"', 'access="0"'), (PLAYER,)), ())
        for port in ('0', '65536', '-1', '5556;command', 'not-a-port'):
            self.assertEqual(bluestacks_endpoints(CONFIG.replace('port="5556"', f'port="{port}"'), (PLAYER,)), ())
        # Never substitute the default port when an active status is invalid.
        self.assertEqual(bluestacks_endpoints(CONFIG + 'bst.instance.Tiramisu64.enable_adb_access="0"\n', (PLAYER,)), ())

    def test_two_instances_and_changed_port_are_distinct(self):
        endpoints = bluestacks_endpoints(CONFIG, ('BlueStacks App Player', PLAYER))
        self.assertEqual([endpoint.address for endpoint in endpoints], ['127.0.0.1:5555', '127.0.0.1:5556'])
        self.assertEqual(bluestacks_endpoints(CONFIG.replace('port="5556"', 'port="5560"'), (PLAYER,))[0].address, '127.0.0.1:5560')

    def test_scan_suggests_bluestacks_without_connecting_or_probing_other_game(self):
        for listing in ('List of devices attached\n', 'localhost:6520 device model:HPE_device\n'):
            runner = Mock(return_value=response(listing))
            result = check_connection('adb', '.', runner=runner, endpoint_probe=lambda: (ENDPOINT,))
            self.assertEqual(result.endpoints, (ENDPOINT,))
            self.assertFalse(result.ready)
            runner.assert_called_once()
            self.assertEqual(runner.call_args.args[0], ['adb', 'devices', '-l'])

    def test_start_connects_only_selected_instance_and_checks_game(self):
        runner = Mock(side_effect=[response('localhost:6520 device\n'), response('connected'),
            response('localhost:6520 device\n127.0.0.1:5556 device\n'), response(GAME)])
        result = check_connection('adb', '.', ENDPOINT.address, runner=runner, endpoint_probe=lambda: (ENDPOINT,))
        self.assertTrue(result.ready)
        self.assertEqual(runner.call_args_list[1].args[0], ['adb', 'connect', ENDPOINT.address])
        self.assertEqual(runner.call_args_list[-1].args[0][:3], ['adb', '-s', ENDPOINT.address])
        self.assertNotIn(GAME, result.diagnostics)

    def test_selected_google_still_requires_its_window_and_game_with_bluestacks_available(self):
        listing = response('localhost:6520 device model:HPE_device\n127.0.0.1:5556 device\n')
        for visible, activity, ready in ((False, GAME, False), (True, LAUNCHER, False), (True, GAME, True)):
            runner = Mock(side_effect=[listing, response(activity)])
            window = Mock(return_value=visible)
            result = check_connection('adb', '.', 'localhost:6520', runner=runner,
                endpoint_probe=lambda: (ENDPOINT,), window_probe=window)
            self.assertEqual(result.ready, ready)
            window.assert_called_once()
            if visible:
                self.assertEqual(runner.call_args.args[0][:3], ['adb', '-s', 'localhost:6520'])
            else:
                self.assertEqual(runner.call_count, 1)


def fake_windows(children=None, offset=(0, 0)):
    backend = WindowsCapture.__new__(WindowsCapture)
    backend.callback_type = lambda function: function
    backend.user = api = Mock()
    children = children if children is not None else {456: ('BlueStacksApp', (634, 181, 3774, 1947), 100)}
    rectangles = {123: (0, 0, 3840, 2064), **{handle: item[1] for handle, item in children.items()}}
    api.IsWindowVisible.return_value = True
    api.IsIconic.return_value = False
    api.GetWindowTextLengthW.return_value = len(PLAYER)
    api.GetWindowTextW.side_effect = lambda handle, text, size: setattr(text, 'value', PLAYER) or len(PLAYER)
    api.GetClassNameW.side_effect = lambda handle, name, size: setattr(name, 'value', children[handle][0] if handle in children else 'Qt672QWindowIcon') or 1
    api.GetWindowThreadProcessId.side_effect = lambda handle, pid: setattr(pid._obj, 'value', children[handle][2] if handle in children else 100) or 1
    def rect(handle, pointer):
        left, top, right, bottom = rectangles[handle]
        pointer._obj.left = pointer._obj.top = 0
        pointer._obj.right, pointer._obj.bottom = right-left, bottom-top
        return True
    def screen(handle, pointer):
        left, top = rectangles[handle][:2]
        pointer._obj.x, pointer._obj.y = left+offset[0], top+offset[1]
        return True
    api.GetClientRect.side_effect = rect
    api.ClientToScreen.side_effect = screen
    api.GetAncestor.return_value = 123
    api.GetForegroundWindow.return_value = 123
    api.WindowFromPoint.return_value = 456
    api.IsChild.return_value = False
    api.GetParent.return_value = 0
    api.IsWindowEnabled.return_value = True
    def enumerate_children(parent, callback, unused):
        for handle in children:
            callback(handle, 0)
        return True
    api.EnumChildWindows.side_effect = enumerate_children
    return backend


class RenderSurfaceTests(unittest.TestCase):
    def parent_host(self):
        backend=fake_windows({456:('BlueStacksApp',(634,181,3774,1947),100),
                              789:('Qt672QWindowIcon',(634,181,3774,1947),100)})
        backend.user.GetParent.side_effect=lambda handle:789 if handle==456 else 123
        backend.user.IsWindowEnabled.side_effect=lambda handle:handle!=456
        backend.user.WindowFromPoint.return_value=789
        return backend

    def test_disabled_render_child_routes_mouse_to_its_verified_qt_parent(self):
        backend=self.parent_host();target=backend.inspect(123)
        self.assertTrue(backend.unobstructed(target,margin=.06))
        frame=Image.new('RGB',(3140,1766),'gray');ImageDraw.Draw(frame).rectangle((50,50,250,250),fill='white')
        sender=Mock();mouse=WindowsMouse(target,lambda:True,backend=backend,
            grabber=Mock(return_value=frame),lookup=lambda _:'HD-Player.exe',sender=sender)
        mouse.screenshot();mouse.click(960,540)
        sender.assert_called_once_with((2204,1064),'click',0)
        backend.user.SetForegroundWindow.assert_not_called()

    def test_parent_exception_rejects_enabled_render_root_foreign_host_and_overlay(self):
        for condition in ('enabled-render','root','foreign-pid','wrong-class','wrong-bounds','disabled-host','outside'):
            backend=self.parent_host();target=backend.inspect(123);point=(1000,1000)
            if condition=='enabled-render':backend.user.IsWindowEnabled.return_value=True;backend.user.IsWindowEnabled.side_effect=None
            elif condition=='root':backend.user.WindowFromPoint.return_value=123
            elif condition=='foreign-pid':backend.user.GetWindowThreadProcessId.side_effect=lambda handle,pid:setattr(pid._obj,'value',200) or 1
            elif condition=='wrong-class':backend.user.GetClassNameW.side_effect=lambda handle,name,size:setattr(name,'value','OverlayWindow') or 1
            elif condition=='wrong-bounds':backend.user.ClientToScreen.side_effect=lambda handle,point:setattr(point._obj,'x',0) or True
            elif condition=='disabled-host':backend.user.IsWindowEnabled.side_effect=lambda handle:False
            else:point=(633,181)
            with self.subTest(condition=condition):self.assertFalse(backend.point_visible(target,point))
        backend=self.parent_host();target=backend.inspect(123)
        backend.user.WindowFromPoint.return_value=999
        self.assertFalse(backend.point_visible(target,(1000,1000)))

    def test_discovery_capture_and_click_use_same_child_bounds_on_negative_monitor(self):
        backend = fake_windows(offset=(-3840, 0))
        target = backend.inspect(123)
        self.assertEqual(target.rectangle, (-3206, 181, -66, 1947))
        self.assertEqual(target.render_handle, 456)
        frame = Image.new('RGB', (3140, 1766), (80, 120, 160))
        ImageDraw.Draw(frame).rectangle((50, 50, 250, 250), fill='white')
        grabber, sender = Mock(return_value=frame), Mock()
        mouse = WindowsMouse(target, lambda: True, backend=backend, grabber=grabber,
                             lookup=lambda _: 'HD-Player.exe', sender=sender)
        captured = mouse.screenshot()
        self.assertEqual(normalize_game_frame(captured)[0].shape, (1080, 1920, 3))
        grabber.assert_called_once_with(bbox=target.rectangle, all_screens=True)
        mouse.click(960, 540)
        sender.assert_called_once_with((-1636, 1064), 'click', 0)
        with tempfile.TemporaryDirectory() as folder:
            saved = capture_selected(target, Path(folder)/'capture.png', backend=backend, grabber=grabber)
            self.assertEqual(saved, target)
        backend.user.SetForegroundWindow.assert_not_called()

    def test_missing_ambiguous_foreign_or_outside_child_never_falls_back_to_chrome(self):
        for children in ({}, {456: ('BlueStacksApp', (634, 181, 3774, 1947), 200)},
                         {456: ('QtWindow', (634, 181, 3774, 1947), 100)},
                         {456: ('BlueStacksApp', (-10, 181, 3774, 1947), 100)},
                         {456: ('BlueStacksApp', (0, 0, 100, 100), 100)},
                         {456: ('BlueStacksApp', (634, 181, 3774, 1947), 100),
                          457: ('BlueStacksApp', (634, 181, 3774, 1947), 100)}):
            with self.subTest(children=children), self.assertRaises(ValueError):
                fake_windows(children).inspect(123)

    def test_sibling_overlay_in_same_emulator_root_is_not_clickable(self):
        backend = fake_windows()
        target = backend.inspect(123)
        backend.user.WindowFromPoint.return_value = 789
        self.assertFalse(backend.point_visible(target, (1000, 1000)))
        backend.user.IsChild.return_value = True
        self.assertTrue(backend.point_visible(target, (1000, 1000)))

    def test_render_child_replacement_or_movement_stops_before_input(self):
        backend = fake_windows()
        target = backend.inspect(123)
        sender = Mock()
        frame = Image.new('RGB', (3140, 1766), 'gray')
        ImageDraw.Draw(frame).rectangle((50, 50, 250, 250), fill='white')
        mouse = WindowsMouse(target, lambda: True, backend=backend,
            lookup=lambda _: 'HD-Player.exe', sender=sender,
            grabber=Mock(return_value=frame))
        mouse.screenshot()
        for replacement in (GameWindow(123, 100, PLAYER, target.rectangle, 457),
                            GameWindow(123, 100, PLAYER, (635, 181, 3775, 1947), 456)):
            with patch.object(backend, 'inspect', return_value=replacement), self.assertRaises(MouseStopped):
                mouse.click(960, 540)
        with patch.object(backend, 'inspect', return_value=GameWindow(123, 100, PLAYER, target.rectangle, 457)), self.assertRaises(ValueError):
            verify_native_target(target, backend=backend, lookup=lambda _: 'HD-Player.exe')
        sender.assert_not_called()

    def test_stove_and_google_without_bluestacks_child_preserve_existing_client(self):
        for title in ('Epic Seven', 'Google Play Games on PC Emulator'):
            backend = fake_windows({})
            backend.user.GetWindowTextLengthW.return_value = len(title)
            backend.user.GetWindowTextW.side_effect = lambda handle, text, size: setattr(text, 'value', title) or len(title)
            target = backend.inspect(123)
            self.assertEqual(target.rectangle, (0, 0, 3840, 2064))
            self.assertIsNone(target.render_handle)
            # Their existing root-window visibility behavior still applies.
            backend.user.WindowFromPoint.return_value = 789
            self.assertTrue(backend.point_visible(target, (1000, 1000)))


@unittest.skipUnless(os.environ.get('E7_BLUESTACKS_HOME_CROP'),'Private BlueStacks menu crop not supplied')
class PrivateHomeTests(unittest.TestCase):
    def test_saved_failure_and_resampled_menu_find_only_observed_shop(self):
        import cv2, numpy as np
        from e7_shop_flow import native_home_control_target
        crop=np.asarray(Image.open(os.environ['E7_BLUESTACKS_HOME_CROP']).convert('RGB'))
        frame=np.full((1080,1920,3),40,dtype=np.uint8);frame[180:920,:420]=crop
        for width in (1280,1920,3140,3840):
            scaled=cv2.resize(frame,(width,round(width*9/16)),interpolation=cv2.INTER_AREA)
            normalized=normalize_game_frame(Image.fromarray(scaled))[0]
            with self.subTest(width=width):
                point=native_home_control_target(normalized)
                self.assertIsNotNone(point)
                self.assertLess(abs(point[0]-84.5)+abs(point[1]-498.5),8)
        for area in ((45,245,125,300),(45,470,125,525),(45,580,125,650)):
            missing=frame.copy();x1,y1,x2,y2=area;missing[y1:y2,x1:x2]=40
            self.assertIsNone(native_home_control_target(missing))
        self.assertIsNone(native_home_control_target((frame*.4).astype('uint8')))
        duplicate=frame.copy();duplicate[:,176:336]=frame[:,:160]
        self.assertIsNone(native_home_control_target(duplicate))


class PermissionTests(unittest.TestCase):
    def test_actual_token_denial_preserves_error_and_closes_owned_process(self):
        kernel, security = Mock(), Mock()
        kernel.OpenProcess.return_value = 789
        security.OpenProcessToken.return_value = False
        with self.assertRaises(MousePermissionCheckFailed) as caught:
            process_is_elevated(100, kernel=kernel, security=security, last_error=lambda: 5)
        self.assertEqual(caught.exception.winerror, 5)
        kernel.CloseHandle.assert_called_once_with(789)

    def test_access_denied_offers_retry_only_for_non_elevated_gui(self):
        target = GameWindow(123, 100, PLAYER, (0, 0, 1920, 1080), 456)
        with patch('e7_native_mouse.process_is_elevated', side_effect=[MousePermissionCheckFailed(5), False]), self.assertRaises(MouseElevationRequired) as caught:
            require_mouse_permissions(target)
        self.assertIn('denied access', str(caught.exception))
        self.assertNotIn('game is running as administrator', str(caught.exception))
        with patch('e7_native_mouse.process_is_elevated', side_effect=[MousePermissionCheckFailed(5), True]), self.assertRaises(ValueError) as caught:
            require_mouse_permissions(target)
        self.assertNotIsInstance(caught.exception, MouseElevationRequired)
        with patch('e7_native_mouse.process_is_elevated', side_effect=MousePermissionCheckFailed(6)) as probe, self.assertRaises(MousePermissionCheckFailed):
            require_mouse_permissions(target)
        probe.assert_called_once_with(100)


class Value:
    def __init__(self, value=''):
        self.value = value
    def get(self):
        return self.value
    def set(self, value):
        self.value = value


class GuiEndpointTests(unittest.TestCase):
    def setUp(self):
        import e7_shop_refresh_gui as gui
        self.gui = gui
        self.app = SimpleNamespace(device=Value('localhost:6520'), device_labels={},
            connected_devices=[], device_box=Mock(), device_notice=Value(), process=None,
            _checking_connection=False, device_button=Mock(), start_button=Mock(), _append_log=Mock())
        self.app._device_address = lambda: gui.RefreshGui._device_address(self.app)
        self.apply = lambda devices, endpoints=(ENDPOINT,): gui.RefreshGui._apply_devices(self.app, devices, '', '', endpoints)

    def test_google_connected_does_not_hide_unconnected_bluestacks(self):
        self.apply(['localhost:6520'])
        labels = self.app.device_box.configure.call_args.kwargs['values']
        self.assertEqual(labels, [PLAYER+' · 5556', 'localhost:6520'])
        self.assertEqual(self.app._device_address(), 'localhost:6520')
        self.app.device.set(PLAYER+' · 5556')
        self.assertEqual(self.app._device_address(), '127.0.0.1:5556')
        self.apply(['localhost:6520'])
        self.assertEqual(self.app._device_address(), '127.0.0.1:5556')

    def test_switch_from_selected_mouse_player_prefers_same_adb_instance(self):
        self.app._adb_preferred_window = PLAYER
        self.apply(['localhost:6520'])
        self.assertEqual(self.app._device_address(), ENDPOINT.address)
        self.assertIsNone(self.app._adb_preferred_window)
        self.assertIn('connect on Start', self.app.device_notice.get())

    def test_loopback_alias_maps_label_to_actual_connected_serial(self):
        self.app.device.set('127.0.0.1:5556')
        self.apply(['localhost:5556'])
        self.assertEqual(self.app._device_address(), 'localhost:5556')
        self.assertEqual(len(self.app.device_labels), 1)
        self.assertEqual(self.app.connected_devices, ['localhost:5556'])

    def test_changed_port_clears_stale_choice_with_several_instances(self):
        self.app.device.set('127.0.0.1:5556')
        self.apply(['localhost:6520'], (AdbEndpoint(PLAYER, '127.0.0.1:5560'),))
        self.assertEqual(self.app.device.get(), '')
        self.assertNotIn('127.0.0.1:5556', self.app.device_labels.values())

    def test_fresh_profile_without_selection_cannot_start_using_implicit_port(self):
        self.app.control_mode = Value('ADB')
        self.app.device.set('')
        with self.assertRaisesRegex(ValueError, 'Choose the emulator'):
            self.gui.RefreshGui._settings(self.app)

    def test_permission_retry_dialog_reports_uncertainty_and_never_autostarts(self):
        self.app._close = Mock()
        self.app.save_settings = Mock()
        with patch.object(self.gui.messagebox, 'askyesno', return_value=False) as ask, patch.object(self.gui, 'restart_as_administrator') as restart:
            self.gui.RefreshGui._offer_administrator_restart(self.app, None, reason='Windows denied access (error 5).')
        self.assertIn('Windows denied access', ask.call_args.args[1])
        self.assertIn('No session starts automatically', ask.call_args.args[1])
        self.assertNotIn('selected game runs as administrator', ask.call_args.args[1])
        restart.assert_not_called()
        self.app.save_settings.assert_not_called()


if __name__ == '__main__':
    unittest.main()
