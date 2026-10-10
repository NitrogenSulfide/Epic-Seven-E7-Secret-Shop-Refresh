"""Fake Win32 message queues, event callbacks and key state; no desktop input."""
import ctypes
import unittest
from unittest.mock import Mock
from unittest.mock import patch
from types import SimpleNamespace
import threading
from e7_stop_key import WindowsStopKey,virtual_stop_key,HOTKEY_ID,WM_HOTKEY,MOD_NOREPEAT,KeyboardEvent,WM_KEYDOWN,WM_KEYUP,WM_SYSKEYDOWN

class StopKeyTests(unittest.TestCase):
    def test_stop_during_monitor_start_acknowledges_without_reserving_a_key(self):
        from E7ADBShopRefresh import E7ADBShopRefresh
        ready=threading.Event();app=SimpleNamespace(loop_active=False,end_of_refresh=False,_stop_key_ready=ready)
        with patch('E7ADBShopRefresh.stop_key_monitor') as factory:E7ADBShopRefresh.checkKeyPress(app)
        self.assertTrue(ready.is_set());factory.assert_not_called()

    def api(self):
        api=Mock();api.RegisterHotKey.return_value=True
        api.SetWindowsHookExW.return_value=123;api.CallNextHookEx.return_value=0
        api.PeekMessageW.return_value=False;api.GetAsyncKeyState.return_value=0
        api.VkKeyScanW.side_effect=lambda key:ord(key.upper()) if key.isalnum() else {'`':192,'/':191,';':186,'+':0x1BB}[key]
        return api

    def test_global_message_stops_with_key_released_and_no_focus_query(self):
        api=self.api()
        def message(pointer,*args):
            pointer._obj.message=WM_HOTKEY;pointer._obj.wParam=HOTKEY_ID
            return True
        api.PeekMessageW.side_effect=message
        with WindowsStopKey('esc',api=api) as monitor:
            api.GetAsyncKeyState.reset_mock()
            self.assertTrue(monitor.pressed())
        api.RegisterHotKey.assert_called_once_with(None,HOTKEY_ID,MOD_NOREPEAT,27)
        api.UnregisterHotKey.assert_called_once_with(None,HOTKEY_ID)
        api.GetForegroundWindow.assert_not_called();api.GetAsyncKeyState.assert_not_called()
        api.UnhookWindowsHookEx.assert_called_once_with(123)

    def test_registration_conflict_is_explicit_and_never_releases_another_owner(self):
        api=self.api();api.RegisterHotKey.return_value=False
        with self.assertRaisesRegex(ValueError,'global Stop key.*1409'):
            with WindowsStopKey('esc',api=api,last_error=lambda:1409):pass
        api.UnregisterHotKey.assert_not_called()

    def test_only_high_down_bit_is_used_and_chord_requires_modifiers(self):
        api=self.api()
        with WindowsStopKey('ctrl+q',api=api) as monitor:
            api.GetAsyncKeyState.return_value=1
            self.assertFalse(monitor.pressed())
            api.GetAsyncKeyState.side_effect=lambda vk:0x8000 if vk==ord('Q') else 0
            self.assertFalse(monitor.pressed())
            api.GetAsyncKeyState.side_effect=lambda vk:0x8000
            self.assertTrue(monitor.pressed())
        api.RegisterHotKey.assert_called_once_with(None,HOTKEY_ID,MOD_NOREPEAT|2,ord('Q'))

    def test_settings_map_esc_letters_digits_and_layout_specific_punctuation(self):
        api=self.api()
        for key,vk,mods in [('esc',27,0),('a',65,0),('2',50,0),('`',192,0),('/',191,0),(';',186,0),('+',187,4),('f10',121,0)]:
            self.assertEqual(virtual_stop_key(key,api.VkKeyScanW),(vk,mods))
        for key in ('f12','invalid-key','unknown+x'):
            with self.assertRaises(ValueError):virtual_stop_key(key,api.VkKeyScanW)

    def test_hotkey_is_released_on_session_error(self):
        api=self.api()
        with self.assertRaises(RuntimeError):
            with WindowsStopKey('`',api=api):raise RuntimeError('Fake session error')
        api.UnregisterHotKey.assert_called_once_with(None,HOTKEY_ID)
        api.UnhookWindowsHookEx.assert_called_once_with(123)

    def event(self,monitor,vk,message=WM_KEYDOWN,flags=0x12,code=0):
        data=KeyboardEvent(vk,0,flags,0,0)
        return monitor._hook_callback(code,message,ctypes.addressof(data))

    def test_brief_injected_streamed_key_is_latched_after_release_without_hotkey_or_down_state(self):
        api=self.api()
        with WindowsStopKey('esc',api=api) as monitor:
            self.event(monitor,27);self.event(monitor,27,WM_KEYUP)
            self.assertTrue(monitor.pressed())
            self.assertEqual(monitor.detected_by,'injected keyboard event')
            self.assertTrue(monitor.injected)
        self.assertEqual(api.CallNextHookEx.call_count,2)
        api.GetForegroundWindow.assert_not_called()

    def test_hook_pumps_messages_and_does_not_log_or_stop_for_other_keys(self):
        api=self.api()
        with WindowsStopKey('esc',api=api) as monitor:
            self.event(monitor,65);self.event(monitor,27,code=-1)
            self.assertFalse(monitor.pressed())
            self.assertEqual(monitor._down,set());self.assertEqual(monitor.detected_by,'')
            def pump(pointer,*unused):
                self.event(monitor,27,flags=0)
                return False
            api.PeekMessageW.side_effect=pump
            self.assertTrue(monitor.pressed());self.assertEqual(monitor.detected_by,'keyboard event')

    def test_injected_chords_track_right_modifiers_and_releases_without_async_state(self):
        api=self.api()
        with WindowsStopKey('ctrl+q',api=api) as monitor:
            self.event(monitor,81);self.assertFalse(monitor.pressed())
            self.event(monitor,163);self.event(monitor,163,WM_KEYUP)
            self.event(monitor,81);self.assertFalse(monitor.pressed())
            self.event(monitor,163);self.event(monitor,81)
            self.assertTrue(monitor.pressed())
        with WindowsStopKey('win+q',api=api) as monitor:
            self.event(monitor,92);self.event(monitor,81,WM_SYSKEYDOWN)
            self.assertTrue(monitor.pressed())

    def test_hook_failure_cleans_own_hotkey_and_blocks_session(self):
        api=self.api();api.SetWindowsHookExW.return_value=0
        with self.assertRaisesRegex(ValueError,'event listener.*5'):
            with WindowsStopKey('esc',api=api,last_error=lambda:5):pass
        api.UnregisterHotKey.assert_called_once_with(None,HOTKEY_ID)
        api.UnhookWindowsHookEx.assert_not_called()
