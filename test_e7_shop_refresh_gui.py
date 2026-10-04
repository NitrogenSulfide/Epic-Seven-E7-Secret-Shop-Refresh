import importlib.util
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import threading
import unittest
import ctypes
import shutil
import wave
from types import SimpleNamespace
from unittest.mock import patch

import e7_shop_refresh_gui as gui
from e7_setup import REFERENCE_NAMES
from e7_window_preview import GameWindow
PACKAGED_ASSETS = gui.ASSET_DIR
DEVICE_SCAN = gui.RefreshGui.refresh_devices
CONNECTION_CHECK = gui.RefreshGui._start_connection_check
CREDITS_AUTO = gui.RefreshGui._maybe_show_credits
BUILTIN_ASSETS = gui.PROJECT_DIR/'adb-assets/builtin-navigation'
if not BUILTIN_ASSETS.is_dir():
    BUILTIN_ASSETS = gui.PROJECT_DIR/'runtime/adb-assets/builtin-navigation'


class ProtocolTests(unittest.TestCase):
    def test_navigation_evidence_is_shown_without_starting_a_gui(self):
        details, events = [], []
        app = SimpleNamespace(detail=SimpleNamespace(set=details.append), _event=events.append,
                              stopping=False, stop_key_pressed=False,
                              status=SimpleNamespace(get=lambda: 'Ready'))
        gui.RefreshGui._handle_line(app, 'Navigation: Secret Shop screen verified.')
        self.assertEqual(details, ['Secret Shop screen verified.'])
        self.assertEqual(events, ['Navigation: Secret Shop screen verified.'])

    def test_physical_stop_key_mapping(self):
        self.assertEqual(gui.captured_stop_key("Escape", "\x1b"), "esc")
        self.assertEqual(gui.captured_stop_key("A", "A", 1), "a")
        for key in "1/,;'[]`":
            self.assertEqual(gui.captured_stop_key(key, key), key)
        for keysym, char, state in (("F1", "", 0), ("space", " ", 0),
                                   ("a", "\x01", 4), ("Escape", "\x1b", 0x10),
                                   ("a", "a", 0x20000), ("exclam", "!", 1)):
            with self.subTest(keysym=keysym):
                self.assertIsNone(gui.captured_stop_key(keysym, char, state))

    def test_windows_lock_flags_do_not_reject_stop_keys(self):
        for state in (0x8, 0x2, 0x20, 0x8 | 0x2 | 0x20):
            with self.subTest(state=state):
                self.assertEqual(gui.captured_stop_key("Escape", "\x1b", state), "esc")
                for key in gui.STOP_KEY_CHARACTERS:
                    self.assertEqual(gui.captured_stop_key(key, key, state), key)
                self.assertIsNone(gui.captured_stop_key("Escape", "\x1b", state | 0x10))
                self.assertIsNone(gui.captured_stop_key("a", "\x01", state | 0x4))

    def setUp(self):
        self.settings = gui.validate_settings("localhost:5555", "30", "0.3", "`", True, False)

    def drive(self, text):
        protocol = gui.EngineProtocol(self.settings)
        answers = []
        for char in text:
            answers.extend(protocol.feed(char))
        return answers

    def test_single_device_skips_selection(self):
        text = "when you finish reading, press enter to continue!\nLast Saved Setting:\nleave blank for yes, or type (yes/no): Launch in debug mode? leave bank for no (yes/no): Key: Enable randomize click (yes/no): Tap sleep(in seconds) Recommend - leave blank for 0.3 sec : Amount of skystone that you want to spend: Press enter to start!\nProgress:\npress enter to exit..."
        self.assertEqual(self.drive(text), ["", "no", "no", "`", "yes", "0.3", "30.0", "", ""])

    def test_multiple_devices_and_retried_device_prompt(self):
        self.assertEqual(self.drive("Device: Fail to connect, try again\nDevice: "), ["localhost:5555"] * 2)

    def test_debug_skips_key_random_and_budget(self):
        protocol = gui.EngineProtocol(gui.validate_settings("x", "30", "0.3", "esc", False, True))
        self.assertEqual(protocol.feed("Launch in debug mode? leave bank for no (yes/no): Tap sleep(in seconds) Recommend - leave blank for 0.3 sec : Press enter to start!"), ["yes", "0.3", ""])

    def test_invalid_values(self):
        for amount, delay, key in (("nan", "0.3", "esc"), ("inf", "0.3", "esc"), ("2", "0.3", "esc"), ("30", "-1", "esc"), ("30", "nan", "esc"), ("30", "0.3", "hello")):
            with self.assertRaises(ValueError):
                gui.validate_settings("x", amount, delay, key, False, False)

    def test_formatting(self):
        self.assertEqual(gui.duration_text("5536.52"), "1h 32m 16s")
        self.assertEqual(gui.number_text("7656000"), "7,656,000")
        self.assertEqual(gui.duration_text("nan"), "—")

    def test_debug_first_history_header_distinguishes_missing_zero_and_positive_counts(self):
        columns = ['Duration', 'Skystone spent', 'Gold spent', 'Covenant bookmark', 'Mystic medal', 'Friendship bookmark']
        for count in ('0', '1'):
            self.assertEqual(gui.history_mode({'Friendship bookmark': count}, columns), 'Debug')
        self.assertEqual(gui.history_mode({'Friendship bookmark': None}, columns), 'Normal')

    def test_unknown_history_schema_does_not_guess_mode(self):
        self.assertEqual(gui.history_mode({'Duration': '100'}, ['Duration']), 'Unknown')


FAKE = '''import sys, time
from pathlib import Path
def prompt(text, expected):
    print(text, end="", flush=True)
    actual = input()
    if actual != expected:
        print("Error: expected", repr(expected), "got", repr(actual), flush=True)
        sys.exit(9)
print("when you finish reading, press enter to continue!", flush=True)
assert input() == ""
prompt("leave blank for yes, or type (yes/no): ", "no")
prompt("Launch in debug mode? leave bank for no (yes/no): ", "no")
prompt("Key: ", "`")
prompt("Enable randomize click (yes/no): ", "yes")
prompt("Tap sleep(in seconds) Recommend - leave blank for 0.3 sec : ", "0.3")
prompt("Amount of skystone that you want to spend: ", "12.0")
print("Press enter to start!", flush=True)
assert input() == ""
print("Progress:", flush=True)
print("50% Cove: 1 Myst: 0", end="\\r", flush=True)
if "--stall" in sys.argv:
    time.sleep(30)
print("100% Cove: 1 Myst: 1", flush=True)
Path(sys.argv[1]).write_text("Duration,Skystone spent,Gold spent,Covenant bookmark,Mystic medal\\n10.3,12,464000,1,1\\n")
print("---Result---\\nCovenant bookmark:1\\nMystic medal:1\\nSkystone spent:12", flush=True)
prompt("press enter to exit...", "")
'''


class GuiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.fake = self.root / "fake_engine.py"
        self.fake.write_text(FAKE)
        self.fake.with_suffix('.sha256').write_text(hashlib.sha256(self.fake.read_bytes()).hexdigest())
        references = self.root / 'adb-assets/gui-navigation'
        references.mkdir(parents=True)
        for name in ('menu-secret-shop.png', 'shop-title.png', 'refresh-label.png'):
            (references/name).write_bytes(b'Fake-engine fixture; not a game reference')
        self.config = self.root / "ADBconfig.ini"
        self.gui_config = self.root / "ShopRefreshGUI.ini"
        self.assets = self.root / 'assets'
        self.assets.mkdir()
        for name in ('start.wav', 'end.wav'):
            shutil.copyfile(PACKAGED_ASSETS / name, self.assets / name)
        self.history = self.root / "history.csv"
        def connected(app, settings):
            app._checking_connection = True
            app._complete_connection_check(app._connection_check_id, settings,
                gui.ConnectionCheck((settings.device,), '', '', True))
        self.patches = [patch.object(gui, "APP_DIR", self.root), patch.object(gui, "CONFIG_FILE", self.config), patch.object(gui, "GUI_CONFIG_FILE", self.gui_config), patch.object(gui, "ASSET_DIR", self.assets), patch.object(gui, "HISTORY_FILE", self.history), patch.object(gui, "ENGINE_EXE", self.fake), patch.object(gui.RefreshGui, "refresh_devices", lambda _: None), patch.object(gui.RefreshGui, '_start_connection_check', connected), patch("winsound.PlaySound")]
        for p in self.patches:
            p.start()
        self.credits_auto_patch = patch.object(gui.RefreshGui, '_maybe_show_credits', lambda _: None)
        self.credits_auto_patch.start()
        import winsound
        self.sound_mock = winsound.PlaySound
        self.app = gui.RefreshGui()
        self.app.withdraw()

    def tearDown(self):
        self.credits_auto_patch.stop()
        if self.app.process and self.app.process.poll() is None:
            self.app.process.kill()
            self.app.process.wait(timeout=5)
        self.app.destroy()
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def pump_until(self, predicate, timeout=8):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.update()
            if predicate():
                return
            time.sleep(0.01)
        self.fail(f"Timed out: {self.app.status.get()}\n{self.app.raw_output}")

    def test_missing_references_opens_setup_without_launching_engine(self):
        (self.root/'adb-assets/gui-navigation/menu-secret-shop.png').unlink()
        with patch.object(gui, 'launch_engine') as launch:
            self.app.start_button.invoke()
        launch.assert_not_called()
        self.assertIsNone(self.app.process)
        self.assertEqual(self.app.status.get(), 'Setup required')
        self.assertIsNotNone(self.app.setup_window)
        self.assertIn('Screenshots stay private', self.app.setup_window.notice.get())
        self.app.setup_window.close()

    def use_fresh_builtin_references(self):
        for name in REFERENCE_NAMES:
            (self.root/'adb-assets/gui-navigation'/name).unlink()
        shutil.copytree(BUILTIN_ASSETS,self.root/'adb-assets/builtin-navigation')

    def test_fresh_install_uses_builtin_recognition_without_setup(self):
        self.use_fresh_builtin_references()
        self.start_fake()
        self.pump_until(lambda:self.app.status.get() == 'Finished')
        self.assertIsNone(self.app.setup_window)
        self.assertFalse((self.root/'setup-captures').exists())

    def test_recognition_failure_offers_setup_only_after_engine_exits(self):
        self.use_fresh_builtin_references()
        self.fake.write_text('print("E7GUI_SETUP_REQUIRED Cannot recognize shop",flush=True)\nraise SystemExit(3)\n')
        self.fake.with_suffix('.sha256').write_text(hashlib.sha256(self.fake.read_bytes()).hexdigest())
        self.start_fake()
        self.pump_until(lambda:self.app.setup_window is not None)
        self.assertEqual(self.app.process.poll(),3)
        self.assertEqual(self.app.status.get(),'Setup required')
        self.assertEqual(self.app.spent.get(),'—')
        with patch.object(gui,'launch_engine') as launch:
            self.app.start_button.invoke()
        launch.assert_not_called()
        self.app.setup_window.close()

    def test_stop_suppresses_pending_recognition_setup(self):
        self.use_fresh_builtin_references()
        self.fake.write_text('import time\nprint("E7GUI_SETUP_REQUIRED Cannot recognize shop",flush=True)\ntime.sleep(30)\n')
        self.start_fake()
        self.pump_until(lambda:self.app._recognition_setup_needed)
        self.assertIsNone(self.app.setup_window)
        self.app.stop_refresh()
        self.pump_until(lambda:self.app.status.get() == 'Stopped')
        self.assertIsNone(self.app.setup_window)

    def test_late_recognition_output_still_offers_setup_once(self):
        self.use_fresh_builtin_references()
        self.fake.write_text('raise SystemExit(3)\n')
        self.fake.with_suffix('.sha256').write_text(hashlib.sha256(self.fake.read_bytes()).hexdigest())
        self.start_fake()
        self.pump_until(lambda:self.app.status.get() == 'Needs attention')
        self.app._handle_line('E7GUI_SETUP_REQUIRED Late fixture output')
        self.pump_until(lambda:self.app.setup_window is not None)
        window = self.app.setup_window
        self.app._handle_line('E7GUI_SETUP_REQUIRED Late fixture output')
        self.app.update()
        self.assertIs(self.app.setup_window,window)
        window.close()

    def test_supplied_backgrounds_render_in_both_themes(self):
        import e7_appearance
        if e7_appearance.Image is None:
            self.skipTest('Source launch has no Pillow; packaged EXE must include it')
        self.app.destroy()
        with patch.object(gui, 'ASSET_DIR', PACKAGED_ASSETS):
            self.app = gui.RefreshGui()
        self.app.deiconify()
        self.app.update()
        self.assertEqual(set(self.app.scenery.sources), {False, True})
        for dark in (False, True):
            self.app.dark_mode.set(dark)
            self.app._apply_theme()
            self.app.update()
            self.app.scenery.render()
            self.assertTrue(self.app.scenery.layer.cget('image'))
            self.assertTrue(any(high > low for low, high in self.app.scenery.backdrop.getextrema()))

    def test_setup_completion_requires_another_explicit_start(self):
        (self.root/'adb-assets/gui-navigation/menu-secret-shop.png').unlink()
        self.app.start_button.invoke()
        wizard = self.app.setup_window
        def capture(adb, device, path):
            path.write_bytes(b'Fixture screenshot; not a real game frame')
        def prepare(engine, runtime, captures):
            (runtime/'adb-assets/gui-navigation/menu-secret-shop.png').write_bytes(b'Fixture reference')
        with patch('e7_setup.capture_frame', capture), patch('e7_setup.prepare_captured_references', prepare), patch.object(gui, 'launch_engine') as launch:
            wizard.home_button.invoke()
            self.pump_until(lambda: not wizard.busy)
            self.assertFalse(wizard.shop_button.instate(['disabled']))
            wizard.shop_button.invoke()
            self.pump_until(lambda: not wizard.busy)
        launch.assert_not_called()
        self.assertIsNone(self.app.process)
        self.assertEqual(self.app.status.get(), 'Ready')
        wizard.close()

    def start_fake(self, stall=False):
        real_popen = subprocess.Popen
        def fake_popen(*args, **kwargs):
            return real_popen([sys.executable, "-u", str(self.fake), str(self.history)] + (["--stall"] if stall else []), **kwargs)
        with patch.object(gui.subprocess, "Popen", fake_popen):
            self.app.start_button.invoke()

    def test_fresh_defaults_match_owner_test_settings(self):
        settings = self.app._settings()
        self.assertEqual((settings.budget, settings.tap_sleep, settings.stop_key, settings.random_offset),
                         (12.0, 0.3, "`", True))

    def choose_mouse_fixture(self):
        self.app.control_mode.set('Mouse (preview)')
        self.app._change_control_mode()
        target=GameWindow(123,456,'Epic Seven',(0,0,1920,1080))
        self.app.mouse_windows={target.label:target}
        self.app.mouse_target.set(target.label)
        self.app._select_mouse_window()
        return target

    def test_mouse_single_window_is_readable_selected_and_ready(self):
        self.app.control_mode.set('Mouse (preview)'); self.app._change_control_mode()
        target = GameWindow(123,456,'Epic Seven',(0,0,3840,2019))
        with patch.object(gui,'capture_selected') as capture, patch.object(gui,'launch_engine') as launch:
            self.app._apply_mouse_windows([target], '')
        self.assertEqual(self.app.mouse_target.get(), 'Epic Seven')
        self.assertEqual(self.app.mouse_windows['Epic Seven'], target)
        self.assertIn('3840 × 2019', self.app.device_notice.get())
        self.assertIn('countdown', self.app.device_notice.get())
        self.assertFalse(self.app.start_button.instate(['disabled']))
        capture.assert_not_called(); launch.assert_not_called()

    def test_mouse_rescan_preserves_identity_when_labels_and_size_change(self):
        self.app.control_mode.set('Mouse (preview)'); self.app._change_control_mode()
        first = GameWindow(123,456,'Epic Seven',(0,0,1920,1080))
        other = GameWindow(124,457,'Epic Seven',(0,0,1920,1080))
        self.app._apply_mouse_windows([first,other], '')
        self.assertEqual(self.app.mouse_target.get(), '')
        self.assertTrue(self.app.start_button.instate(['disabled']))
        self.assertEqual(len(self.app.mouse_windows), 2)
        self.app.mouse_target.set(first.label); self.app._select_mouse_window()
        moved = GameWindow(123,456,'Epic Seven',(10,20,3850,2039))
        self.app._apply_mouse_windows([moved], '')
        self.assertEqual(self.app.mouse_target.get(), 'Epic Seven')
        self.assertEqual(self.app.mouse_windows['Epic Seven'], moved)
        self.assertIn('3840 × 2019', self.app.device_notice.get())
        self.app._apply_mouse_windows([other,moved], '')
        self.assertEqual(self.app.mouse_target.get(), moved.label)

    def test_mouse_closed_selection_clears_and_requires_new_choice(self):
        self.choose_mouse_fixture()
        others = [GameWindow(124,457,'Other Epic Seven',(0,0,1920,1080)),
                  GameWindow(125,458,'Google Play Games',(0,0,1920,1080))]
        self.app._apply_mouse_windows(others, '')
        self.assertEqual(self.app.mouse_target.get(), '')
        self.assertTrue(self.app.start_button.instate(['disabled']))
        self.app._apply_mouse_windows([], '')
        self.assertIn('No game window found', self.app.connection_warning)
        self.assertTrue(self.app.start_button.instate(['disabled']))

    def test_mouse_background_scan_keeps_preparation_guidance(self):
        target = self.choose_mouse_fixture()
        before = self.app.device_notice.get()
        self.app._background_scan = True
        with patch.object(gui.WindowsCapture,'list_windows',return_value=[target]), \
                patch.object(gui,'check_connection') as adb:
            self.app._scan_game_windows()
            self.assertEqual(self.app.device_notice.get(), before)
            self.pump_until(lambda:not self.app._mouse_scan_busy)
        self.assertEqual(self.app.mouse_target.get(), 'Epic Seven')
        self.assertEqual(self.app.device_notice.get(), before)
        adb.assert_not_called()

    def test_switch_from_empty_mouse_selector_restores_adb_start(self):
        before = self.app._device_address()
        self.app.control_mode.set('Mouse (preview)'); self.app._change_control_mode()
        self.app._apply_mouse_windows([], '')
        self.assertTrue(self.app.start_button.instate(['disabled']))
        self.app.control_mode.set('ADB'); self.app._change_control_mode()
        self.assertFalse(self.app.start_button.instate(['disabled']))
        self.assertEqual(self.app._device_address(), before)

    def test_mouse_preview_captures_without_adb_or_refresh_session(self):
        target=self.choose_mouse_fixture()
        report=dict(read_only=True,state='home',targets=[dict(label='Secret Shop menu',point=[86,548])],detections=[])
        def capture(window,path,**kwargs):
            from PIL import Image,ImageDraw
            image=Image.new('RGB',(1920,1080),'#334155')
            ImageDraw.Draw(image).rectangle((50,500,150,580),outline='white',width=5)
            image.save(path)
        with patch.object(gui,'capture_selected',side_effect=capture) as grab, patch.object(gui,'wait_for_window',return_value=target), patch.object(gui,'analyze_capture',return_value=report), \
                patch.object(gui,'launch_engine') as launch, patch.object(gui,'check_connection') as adb:
            self.app.start_button.invoke()
            self.app._mouse_preview_countdown(self.app._preview_token,target,0)
            self.pump_until(lambda:self.app.status.get()=='Preview complete')
        self.assertEqual(grab.call_count,1);launch.assert_not_called();adb.assert_not_called()
        self.assertIsNone(self.app.process);self.assertEqual(self.app.run_id,0)
        self.assertFalse(self.history.exists());self.assertFalse(self.config.exists())
        self.assertIn('no clicks',self.app.preview_window.title())
        self.assertEqual(self.app.start_button.cget('text'),'Preview targets')
        self.app.preview_window.close()

    def test_mouse_preview_cancelled_before_capture_and_late_result_ignored(self):
        target=self.choose_mouse_fixture()
        with patch.object(gui,'capture_selected') as capture, patch.object(gui,'launch_engine') as launch:
            self.app.start_button.invoke();token=self.app._preview_token
            self.assertEqual(self.app.stop_button.cget('text'), 'Cancel preview')
            self.assertIn('Ready check in', self.app.detail.get())
            self.app.stop_refresh()
            self.app._mouse_preview_countdown(token,target,0)
            self.app._finish_mouse_preview(token,None,None,'')
        capture.assert_not_called();launch.assert_not_called()
        self.assertIsNone(self.app.preview_window)
        self.assertEqual(self.app.status.get(),'Preview cancelled')
        self.assertEqual(self.app.stop_button.cget('text'), 'Stop Session')

    def test_mouse_waiting_can_be_cancelled_without_capture_or_engine(self):
        target=self.choose_mouse_fixture();entered=threading.Event();exited=threading.Event()
        def wait(window,cancel):
            entered.set();cancel.wait(3);exited.set()
            raise ValueError('Cancelled')
        with patch.object(gui,'wait_for_window',side_effect=wait),patch.object(gui,'capture_selected') as capture, \
                patch.object(gui,'analyze_capture') as analyze,patch.object(gui,'launch_engine') as launch:
            self.app.start_button.invoke()
            self.app._mouse_preview_countdown(self.app._preview_token,target,0)
            self.pump_until(entered.is_set)
            self.assertEqual(self.app.status.get(),'Waiting for game window')
            self.assertIn('20 seconds',self.app.home_ui_hint.get())
            self.app.stop_refresh();self.pump_until(exited.is_set)
        capture.assert_not_called();analyze.assert_not_called();launch.assert_not_called()
        self.assertEqual(self.app.status.get(),'Preview cancelled')
        self.assertIsNone(self.app.preview_window)

    def test_mouse_scan_results_and_switch_back_preserve_adb_choice(self):
        before=self.app._device_address()
        target=self.choose_mouse_fixture()
        self.app.log_queue.put((None,'windows',(self.app._connection_check_id,[target],'')))
        self.app._drain_log_queue()
        self.assertEqual(self.app.device_box.cget('textvariable'),str(self.app.mouse_target))
        self.app.control_mode.set('ADB');self.app._change_control_mode()
        self.assertEqual(self.app._device_address(),before)
        self.assertEqual(self.app.start_button.cget('text'),'Start Refresh')
        self.assertEqual(self.app.device_box.cget('textvariable'),str(self.app.device))

    def test_missing_mouse_target_blocks_capture_and_red_warning_is_clear(self):
        self.app.control_mode.set('Mouse (preview)');self.app._change_control_mode()
        with patch.object(gui,'capture_selected') as capture, patch.object(gui,'launch_engine') as launch:
            self.assertTrue(self.app.start_button.instate(['disabled']))
            self.app._start_mouse_preview()
        capture.assert_not_called();launch.assert_not_called()
        self.assertIn('Choose an open game window',self.app.home_ui_hint.get())

    def test_stale_adb_scan_cannot_override_mouse_mode_notice(self):
        old=self.app._connection_check_id
        self.choose_mouse_fixture()
        self.app.log_queue.put((None,'devices',(old,gui.ConnectionCheck((),'No emulator',''),False)))
        self.app._drain_log_queue()
        self.assertEqual(self.app.connection_warning,'')
        self.assertIn('Mouse preview only',self.app.home_ui_hint.get())

    def test_real_mouse_start_uses_native_cli_and_same_settings_without_adb(self):
        target = self.choose_mouse_fixture()
        self.app.control_mode.set('Mouse'); self.app._change_control_mode()
        self.app._apply_mouse_windows([target],'')
        self.fake.write_text('print("E7GUI_STARTED",flush=True)\nprint(\'E7GUI_STATS {"refreshes":4,"skystone_spent":12,"covenant":0,"mystic":0,"friendship":0}\',flush=True)\nprint("---Result---\\nCovenant bookmark:0\\nMystic medal:0\\nSkystone spent:12",flush=True)\n')
        self.fake.with_suffix('.sha256').write_text(hashlib.sha256(self.fake.read_bytes()).hexdigest())
        with patch.object(gui.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='native mouse v2')), \
                patch.object(gui,'activate_native_target',return_value=target) as activate, \
                patch.object(gui,'check_connection') as adb,patch.object(gui,'launch_engine',wraps=gui.launch_engine) as launch:
            self.start_fake()
            self.pump_until(lambda:self.app.status.get()=='Finished')
        args = launch.call_args.args[0]
        self.assertIn('--mouse-session',args)
        self.assertEqual(json.loads(args[args.index('--mouse-session')+1])['handle'],target.handle)
        self.assertEqual(args[args.index('--budget')+1],'12.0')
        self.assertEqual(args[args.index('--stop-key')+1],'`')
        self.assertEqual(args[args.index('--random-offset')+1],'yes')
        activate.assert_called_once(); adb.assert_not_called()
        self.assertEqual(self.app.spent.get(),'12')
        self.assertEqual(self.app.start_button.cget('text'),'Start Refresh')

    def test_old_engine_cannot_launch_adb_when_mouse_is_selected(self):
        self.choose_mouse_fixture(); self.app.control_mode.set('Mouse'); self.app._change_control_mode()
        with patch.object(gui.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='older engine')), \
                patch.object(gui,'activate_native_target') as activate,patch.object(gui,'launch_engine') as launch:
            self.app.start_refresh()
        activate.assert_not_called(); launch.assert_not_called()
        self.assertIn('matching rc30',self.app.connection_warning)

    def test_native_focus_failure_stays_visible_and_is_saved_without_stop_key_claim(self):
        target=self.choose_mouse_fixture()
        self.app.control_mode.set('Mouse');self.app._change_control_mode()
        self.app._apply_mouse_windows([target],'')
        reason='The selected game lost focus. No input sent.'
        self.fake.write_text('print("E7GUI_STARTED",flush=True)\nprint(\'E7GUI_MOUSE_STOPPED {"reason":"The selected game lost focus. No input sent."}\',flush=True)\nprint("---Result---\\nSkystone spent:0",flush=True)\n')
        self.fake.with_suffix('.sha256').write_text(hashlib.sha256(self.fake.read_bytes()).hexdigest())
        with patch.object(gui.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='native mouse v2')),patch.object(gui,'activate_native_target',return_value=target):
            self.start_fake()
            self.pump_until(lambda:self.app.status.get()=='Needs attention' and self.app.process.poll() is not None)
            self.pump_until(lambda:self.app._finalized_run_id==self.app.run_id)
        self.assertEqual(self.app.detail.get(),reason)
        self.assertFalse(self.app.stop_key_pressed)
        self.assertIn('E7GUI_MOUSE_STOPPED',self.app._session_log_path.read_text(encoding='utf-8'))

    def test_native_pause_and_resume_show_actual_state(self):
        self.app._handle_line('E7GUI_MOUSE_PAUSED {"reason":"The mouse target is covered."}')
        self.assertEqual(self.app.status.get(),'Paused')
        self.assertIn('target is covered',self.app.detail.get())
        self.assertFalse(self.app.stop_key_pressed)
        self.app._handle_line('E7GUI_MOUSE_RESUMED')
        self.assertEqual(self.app.status.get(),'Running')
        self.assertIn('Checking the current screen',self.app.detail.get())

    def test_saved_mouse_mode_restores_without_starting_session(self):
        self.app.control_mode.set('Mouse'); self.app._change_control_mode()
        self.app.save_settings()
        self.app.control_mode.set('ADB')
        with patch.object(gui,'activate_native_target') as activate,patch.object(gui,'launch_engine') as launch:
            self.app.destroy()
            self.app = gui.RefreshGui()
        self.assertEqual(self.app.control_mode.get(),'Mouse')
        self.assertEqual(self.app.start_button.cget('text'),'Start Refresh')
        self.assertEqual(self.app.device_box.cget('textvariable'),str(self.app.mouse_target))
        activate.assert_not_called(); launch.assert_not_called()

    def test_credits_first_launch_dismissal_and_startup_opt_in_persist(self):
        with patch.object(self.app,'winfo_viewable',return_value=True), patch.object(self.app,'_show_about') as show:
            CREDITS_AUTO(self.app)
            show.assert_called_once()
        self.app.about_button.invoke()
        dialog = self.app.about_window
        self.assertEqual(dialog.title(), 'Welcome · About & Credits')
        self.assertFalse(self.app.credits_on_startup.get())
        dialog.continue_button.invoke()
        self.assertTrue(self.app.credits_seen.get())
        with patch.object(self.app,'winfo_viewable',return_value=True), patch.object(self.app,'_show_about') as show:
            CREDITS_AUTO(self.app)
            show.assert_not_called()
        self.app.about_button.invoke()
        self.app.about_window.startup_check.invoke()
        self.app.about_window.close()
        self.app.credits_seen.set(False)
        self.app.credits_on_startup.set(False)
        self.app._load_config()
        self.assertTrue(self.app.credits_seen.get())
        self.assertTrue(self.app.credits_on_startup.get())
        with patch.object(self.app,'winfo_viewable',return_value=True), patch.object(self.app,'_show_about') as show:
            CREDITS_AUTO(self.app)
            show.assert_called_once()

    def test_about_reopens_once_and_remains_available_during_session(self):
        self.app._set_controls(True)
        self.assertFalse(self.app.about_button.instate(['disabled']))
        self.app.about_button.invoke()
        dialog = self.app.about_window
        self.app.about_button.invoke()
        self.assertIs(self.app.about_window,dialog)
        contents = '\n'.join(reader.get('1.0','end') for reader in dialog.readers)
        for credit in ('NitrogenSulfide (Blue Natto)','Solunium','Robin Lamb','GNU GENERAL PUBLIC LICENSE'):
            self.assertIn(credit,contents)
        import e7_appearance
        if e7_appearance.Image is not None:
            self.assertIsNotNone(dialog.avatar_image)
            self.assertEqual(dialog.avatar_image.width(),self.app._dp(72))
        self.app.theme_button.invoke()
        self.assertEqual(dialog.readers[0].cget('foreground'),'#e2e8f0')
        dialog.close()
        self.assertTrue(self.app.stop_key_entry.instate(['disabled']))

    def test_hidden_ui_wait_state_resumes_and_does_not_override_stop(self):
        self.app.run_settings = self.app._settings()
        self.assertIn('ADB enabled', self.app.home_ui_hint.get())
        waiting = 'Navigation: Waiting for visible game controls. Click the game to reveal its UI.'
        self.app._handle_line(waiting)
        self.assertEqual(self.app.status.get(), 'Waiting for game')
        self.assertIn('reveal controls and continue', self.app.home_ui_hint.get())
        self.assertIn('no taps or spending', self.app.progress_text.get())
        self.app._handle_line('Navigation: Opening the recognized Secret Shop menu.')
        self.assertEqual(self.app.status.get(), 'Running')
        self.assertIn('ADB enabled', self.app.home_ui_hint.get())
        self.app.stopping = True
        self.app.status.set('Stopping')
        self.app._handle_line(waiting)
        self.assertEqual(self.app.status.get(), 'Stopping')

    def test_dismissed_home_ui_reminder_stays_hidden_without_hiding_wait_status(self):
        self.assertEqual(self.app.home_ui_banner.winfo_manager(),'grid')
        self.assertIn('Use an emulator with ADB enabled', self.app.home_ui_hint.get())
        self.app.home_ui_dismiss.invoke()
        self.app.adb_hint_dismissed.set(False)
        self.app._load_config()
        self.assertTrue(self.app.adb_hint_dismissed.get())
        self.app._update_home_ui_hint()
        self.assertNotIn('ADB enabled', self.app.home_ui_hint.get())
        self.assertIn('before Start', self.app.home_ui_hint.get())
        self.assertEqual(self.app.home_ui_banner.winfo_manager(),'')
        self.app.theme_button.invoke()
        self.app.run_settings = self.app._settings()
        self.app._handle_line('Navigation: Waiting for visible game controls. Click the game to reveal its UI.')
        self.app._layout_dashboard()
        self.assertEqual(self.app.home_ui_banner.winfo_manager(),'')
        self.assertEqual(self.app.status.get(),'Waiting for game')
        self.assertIn('no taps or spending',self.app.progress_text.get())
        self.app._handle_line('Navigation: Opening the recognized Secret Shop menu.')
        self.assertEqual(self.app.status.get(),'Running')
        self.assertEqual(self.app.home_ui_banner.winfo_manager(),'')

    def test_stop_key_capture_and_rejection(self):
        self.app._capture_stop_key(SimpleNamespace(keysym="Escape", char="\x1b", state=0))
        self.assertEqual(self.app.stop_key.get(), "esc")
        self.app._capture_stop_key(SimpleNamespace(keysym="comma", char=",", state=0))
        self.assertEqual(self.app.stop_key.get(), ",")
        for keysym, char, state in (("F1", "", 0), ("a", "\x01", 4)):
            self.app._capture_stop_key(SimpleNamespace(keysym=keysym, char=char, state=state))
            self.assertEqual(self.app.stop_key.get(), ",")
            self.assertIn("Choose Esc", self.app.setting_notice.get())

    def test_stop_key_capture_preserves_navigation_and_disabled_state(self):
        for keysym in ("Tab", "ISO_Left_Tab"):
            self.assertIsNone(self.app._capture_stop_key(SimpleNamespace(keysym=keysym)))
        self.app._set_controls(True)
        self.app._capture_stop_key(SimpleNamespace(keysym="Escape", char="\x1b", state=0))
        self.assertEqual(self.app.stop_key.get(), "`")
        self.app._set_controls(False)
        self.assertTrue(self.app.stop_key_entry.instate(["readonly", "!disabled"]))

    def test_stop_key_entry_binds_escape_press(self):
        self.app.deiconify()
        self.app.update()
        self.app.stop_key_entry.focus_force()
        self.app.update()
        self.app.stop_key_entry.event_generate("<KeyPress-Escape>")
        self.app.update()
        self.assertEqual(self.app.stop_key.get(), "esc")
        self.assertEqual(self.app._settings().stop_key, "esc")

    def test_stop_key_click_then_key_with_num_lock(self):
        self.app.deiconify()
        self.app.update()
        # Focus the window, then let the ordinary entry click binding focus it.
        self.app.focus_force()
        self.app.update()
        entry = self.app.stop_key_entry
        entry.event_generate('<ButtonPress-1>', x=10, y=10)
        entry.event_generate('<ButtonRelease-1>', x=10, y=10)
        self.app.update()
        self.assertEqual(self.app.focus_get(), entry)
        for keysym, expected in (('q', 'q'), ('Escape', 'esc'), ('a', 'a')):
            entry.event_generate('<KeyPress>', keysym=keysym, state=0x8)
            self.app.update()
            self.assertEqual(self.app.stop_key.get(), expected)
        entry.event_generate('<KeyPress>', keysym='F1', state=0x8)
        self.app.update()
        self.assertEqual(self.app.stop_key.get(), 'a')

    def test_live_counters_update_before_session_end_and_ignore_old_percent(self):
        self.app.run_settings = gui.validate_settings('localhost:5555', '33', '.3', 'esc', False, False)
        def stats(refreshes, cov, mys):
            return 'E7GUI_STATS ' + gui.json.dumps(dict(refreshes=refreshes, skystone_spent=3*refreshes, covenant=cov, mystic=mys, friendship=0)) + '\n'
        # Fragmented stream: no final result or history is needed for live cards.
        message = stats(1, 1, 0)
        self.app._handle_output(message[:19])
        self.app._handle_output(message[19:])
        self.assertEqual((self.app.spent.get(), self.app.covenant.get(), self.app.mystic.get()), ('3', '1', '0'))
        self.app._handle_output(stats(1, 1, 1))
        self.app._handle_output('10% Cove: 0 Myst: 0\r')
        self.assertEqual((self.app.spent.get(), self.app.covenant.get(), self.app.mystic.get()), ('3', '1', '1'))
        self.app._handle_output(stats(2, 1, 1))
        self.assertEqual(self.app.spent.get(), '6')
        self.assertFalse(self.app.finished)

    def test_invalid_live_stats_do_not_change_cards(self):
        self.app.run_settings = gui.validate_settings('localhost:5555', '30', '.3', 'esc', False, False)
        for text in ('not json', '{}', '[1]', '{"refreshes":true}', '{"refreshes":1,"skystone_spent":6,"covenant":0,"mystic":0,"friendship":0}'):
            self.app._handle_line('E7GUI_STATS ' + text)
        self.assertFalse(self.app._live_stats_seen)
        self.assertEqual(self.app.spent.get(), '—')

    def test_dark_mode_persists_without_disabling_during_session(self):
        self.app.theme_button.invoke()
        self.assertTrue(self.app.dark_mode.get())
        self.assertEqual(self.app.settings_canvas.cget('background'), '#111827')
        self.assertIn('dark_mode = True', self.gui_config.read_text())
        self.app._set_controls(True)
        self.assertFalse(self.app.theme_button.instate(['disabled']))
        self.app.theme_button.invoke()
        self.assertFalse(self.app.dark_mode.get())
        self.assertTrue(self.app.stop_key_entry.instate(['readonly', 'disabled']))
        self.app._set_controls(False)
        self.app.theme_button.invoke()
        self.app.dark_mode.set(False)
        self.app._load_config()
        self.assertTrue(self.app.dark_mode.get())

    def test_currency_art_preserves_transparency_and_fits_counter_size(self):
        from e7_appearance import currency_icons
        images = currency_icons(self.app, PACKAGED_ASSETS, 40)
        self.assertEqual(set(images), {'spent', 'covenant', 'mystic'})
        for image in images.values():
            self.assertEqual((image.width(),image.height()), (40,40))

    def test_output_queue_batches_diagnostics_but_preserves_counter_order(self):
        self.app.run_settings = gui.validate_settings('localhost:5555', '30', '.3', 'esc', False, False)
        for i in range(30):
            self.app.log_queue.put((self.app.run_id, 'output', f'{i}% Cove: {i} Myst: 0\n'))
        with patch.object(self.app, '_append_log', wraps=self.app._append_log) as log:
            self.app._drain_log_queue()
        self.assertEqual(log.call_count, 1)
        self.assertEqual(self.app.covenant.get(), '29')

    def test_end_to_end(self):
        self.start_fake()
        self.pump_until(lambda: self.app.status.get() == "Finished")
        self.assertEqual(self.app.process.returncode, 0)
        self.assertEqual(self.app.spent.get(), "12")
        self.assertEqual(self.app.covenant.get(), "1")
        self.assertEqual(self.app.mystic.get(), "1")
        self.assertEqual(len(self.app.history.get_children()), 1)
        self.assertEqual(str(self.app.start_button.cget("state")), "normal")
        self.assertTrue(self.config.exists())
        events = [self.app.activity.item(i, "values")[1] for i in self.app.activity.get_children()]
        self.assertFalse(any("leave blank" in e for e in events))
        self.assertEqual(self.sound_mock.call_count, 2)
        self.assertEqual([Path(call.args[0]).name for call in self.sound_mock.call_args_list], ["start.wav", "end.wav"])

    def test_stop_preserves_history_and_restart(self):
        self.history.write_text("Duration,Skystone spent,Gold spent,Covenant bookmark,Mystic medal\n5536.52,2799,7656000,34,5\n")
        original = self.history.read_bytes()
        self.start_fake(stall=True)
        self.pump_until(lambda: self.app.status.get() == "Running")
        self.app.stop_refresh()
        self.pump_until(lambda: self.app.status.get() == "Stopped")
        self.assertEqual(self.history.read_bytes(), original)
        self.start_fake()
        self.pump_until(lambda: self.app.status.get() == "Finished")

    def test_invalid_settings_do_not_launch(self):
        self.app.budget.set("nan")
        with patch.object(gui.messagebox, "showerror") as error, patch.object(gui.subprocess, "Popen") as popen:
            self.app.start_refresh()
            popen.assert_not_called()
            error.assert_called_once()

    def test_save_preserves_other_config(self):
        self.config.write_text("[Other]\nkeep = yes\n[Settings]\nextra = retained\n")
        self.app.save_settings()
        saved = self.config.read_text()
        self.assertIn("keep = yes", saved)
        self.assertIn("extra = retained", saved)

    def test_launch_failure_recovers_controls(self):
        with patch.object(gui.subprocess, "Popen", side_effect=OSError("test launch failure")):
            self.app.start_refresh()
        self.assertEqual(self.app.status.get(), "Failed")
        self.assertEqual(str(self.app.start_button.cget("state")), "normal")
        self.assertIsNone(self.app.started_at)

    def test_nonzero_exit_is_not_success(self):
        self.fake.write_text('print("Traceback: test failure", flush=True)\nraise SystemExit(7)\n')
        self.start_fake()
        self.pump_until(lambda: self.app.status.get() == "Needs attention")
        self.assertEqual(self.app.process.returncode, 7)
        self.assertIn("Traceback", self.app.raw_output)
        self.sound_mock.assert_not_called()

    def test_stop_key_gets_stopped_status_and_one_sound(self):
        self.fake.write_text(FAKE.replace('print("100% Cove: 1 Myst: 1", flush=True)', 'print("Shop refresh terminated!", flush=True)'))
        self.start_fake()
        self.pump_until(lambda: self.app.status.get() == "Stopped")
        self.assertTrue(self.app.stop_key_pressed)
        self.assertEqual(self.sound_mock.call_count, 2)
        self.assertEqual(Path(self.sound_mock.call_args.args[0]).name, "end.wav")
        self.app._finish_process()
        self.assertEqual(self.sound_mock.call_count, 2)

    def test_sound_can_be_disabled(self):
        self.app.sound_enabled.set(False)
        self.start_fake()
        self.pump_until(lambda: self.app.status.get() == "Finished")
        self.sound_mock.assert_not_called()
        parser = gui.configparser.ConfigParser()
        parser.read(self.gui_config)
        self.assertFalse(parser.getboolean("GUI", "sound_enabled"))
        self.app.sound_enabled.set(True)
        self.app._load_config()
        self.assertFalse(self.app.sound_enabled.get())

    def test_sound_preference_survives_engine_rewriting_settings(self):
        self.app.sound_enabled.set(False)
        self.app._save_sound_preference()
        self.config.write_text('[Settings]\nbudget = 30\n')
        self.app.sound_enabled.set(True)
        self.app._load_config()
        self.assertFalse(self.app.sound_enabled.get())

    def test_stop_button_has_sound(self):
        self.start_fake(stall=True)
        self.pump_until(lambda: self.app.status.get() == "Running")
        self.app.stop_refresh()
        self.pump_until(lambda: self.app.status.get() == "Stopped")
        self.assertEqual(self.sound_mock.call_count, 2)
        self.assertEqual(Path(self.sound_mock.call_args.args[0]).name, "end.wav")

    def test_late_stop_callback_does_not_kill_new_run(self):
        old, current = unittest.mock.Mock(), unittest.mock.Mock()
        self.app.process = current
        self.app._kill_if_needed(old)
        old.kill.assert_not_called()
        current.kill.assert_not_called()
        self.app.process = None

    def test_layout_moves_history_and_restores_it_after_resize(self):
        self.app.deiconify()
        scale = self.app.ui_scale
        self.app.minsize(1, 1)
        self.app.geometry(f'{round(1500*scale)}x{round(1100*scale)}')
        self.app.update()
        self.assertFalse(self.app.compact_history)
        self.app.geometry(f'{round(1150*scale)}x{round(700*scale)}')
        self.app.update()
        self.assertTrue(self.app.compact_history)
        self.app.notebook.select(self.app.history_tab)
        self.app.update()
        self.app.geometry(f'{round(1500*scale)}x{round(1100*scale)}')
        self.app.update()
        self.assertFalse(self.app.compact_history)
        self.assertTrue(self.app.metrics.winfo_ismapped())
        self.assertTrue(self.app.history.winfo_ismapped())

    def test_buffered_debug_enters_calibration_and_stop_recovers(self):
        self.fake.write_text('''import time
print("when you finish reading, press enter to continue!", flush=True)
assert input() == ""
print("leave blank for yes, or type (yes/no): ", end="", flush=True)
assert input() == "no"
print("Launch in debug mode? leave bank for no (yes/no): ", end="", flush=True)
assert input() == "yes"
print("Tap sleep(in seconds) Recommend - leave blank for 0.3 sec : ", end="", flush=True)
assert input() == "0.3"
print("Press enter to start!", flush=True)
assert input() == ""
print("Progress:")  # Deliberately buffered while a calibration window waits.
time.sleep(30)
''')
        self.app.debug_mode.set(True)
        with patch.object(gui.messagebox, 'askyesno', return_value=True):
            self.start_fake()
        self.pump_until(lambda: self.app.status.get() == 'Calibrating')
        self.assertIn('red rectangle', self.app.detail.get())
        self.assertNotIn('longer than expected', self.app.detail.get())
        self.app.stop_refresh()
        elapsed = self.app.elapsed.get()
        self.pump_until(lambda: self.app.status.get() == 'Stopped')
        self.assertEqual(self.app.elapsed.get(), elapsed)
        self.assertEqual(str(self.app.start_button.cget('state')), 'normal')
        self.assertIsNone(self.app.started_at)

    def test_shutdown_kills_child_holding_output_pipe(self):
        child_pid = self.root / 'child.pid'
        self.fake.write_text(FAKE.replace('    time.sleep(30)', f'''    import subprocess
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], stdout=sys.stdout, stderr=sys.stdout, stdin=subprocess.DEVNULL)
    Path({str(child_pid)!r}).write_text(str(child.pid))
    time.sleep(30)'''))
        self.start_fake(stall=True)
        self.pump_until(lambda: child_pid.exists())
        self.app.stop_refresh()
        self.pump_until(lambda: self.app.status.get() == 'Stopped', timeout=5)
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, int(child_pid.read_text()))
        if handle:
            try:
                code = wintypes.DWORD()
                self.assertTrue(kernel.GetExitCodeProcess(handle, ctypes.byref(code)))
                self.assertNotEqual(code.value, 259)
            finally:
                kernel.CloseHandle(handle)
        self.assertEqual(str(self.app.start_button.cget('state')), 'normal')

    def test_exit_recovers_without_reader_eof(self):
        process = unittest.mock.Mock()
        process.poll.return_value = 0
        process.returncode = 0
        self.app.process = process
        self.app.finished = True
        self.app._watch_process(process, self.app.run_id)
        self.pump_until(lambda: self.app.status.get() == 'Finished')
        process.stdout.close.assert_not_called()
        self.assertEqual(str(self.app.start_button.cget('state')), 'normal')

    def test_manual_debug_exit_freezes_timer_and_clears_startup_message(self):
        process = unittest.mock.Mock()
        process.poll.return_value = 0
        process.returncode = 0
        self.app.process = process
        self.app.run_settings = gui.validate_settings('localhost:5555', '30', '0.3', 'esc', True, True)
        self.app._session_started = True
        self.app.started_at = time.monotonic() - 65
        self.app.detail.set('Startup is taking longer than expected.')
        self.app._set_controls(True)
        self.app._finish_process()
        self.assertEqual(self.app.status.get(), 'Stopped')
        self.assertEqual(self.app.elapsed.get(), '1m 05s')
        self.assertIsNone(self.app.started_at)
        self.assertNotIn('Startup', self.app.detail.get())
        self.assertEqual(str(self.app.start_button.cget('state')), 'normal')
        self.sound_mock.assert_called_once()
        self.assertEqual(Path(self.sound_mock.call_args.args[0]).name, 'end.wav')

    def test_single_device_default_label_never_reaches_engine(self):
        self.app._apply_devices(['localhost:6520'], 'Connected.', '')
        self.assertEqual(self.app.device.get(), 'localhost:6520 (default)')
        settings = self.app._settings()
        self.assertEqual(settings.device, 'localhost:6520')
        self.assertEqual(gui.EngineProtocol(settings).feed('Device: '), ['localhost:6520'])
        self.app.save_settings()
        parser = gui.configparser.ConfigParser()
        parser.read(self.gui_config)
        self.assertEqual(parser.get('GUI', 'device'), 'localhost:6520')

    def test_multiple_devices_require_choice_and_preserve_previous_choice(self):
        self.app.device.set('localhost:5555')
        self.app._apply_devices(['localhost:6520', 'localhost:6530'], 'Connected.', '')
        self.assertEqual(self.app.device.get(), '')
        with self.assertRaises(ValueError):
            self.app._settings()
        self.app.device.set('localhost:6530')
        self.app._apply_devices(['localhost:6520', 'localhost:6530'], 'Connected.', '')
        self.assertEqual(self.app._settings().device, 'localhost:6530')

    def test_default_label_remains_correct_after_rescan(self):
        self.app._apply_devices(['localhost:6520'], 'Connected.', '')
        self.app._apply_devices(['localhost:6520', 'localhost:6530'], 'Connected.', '')
        self.assertEqual(self.app.device.get(), 'localhost:6520')
        self.assertEqual(self.app._device_address(), 'localhost:6520')

    def test_debug_results_accept_engine_spacing_and_record_friendship_points(self):
        self.app._handle_line('Covenant bookmark : 2')
        self.app._handle_line('Mystic medal : 1')
        self.app._handle_line('Friendship bookmark : 3')
        self.assertEqual(self.app.covenant.get(), '2')
        self.assertEqual(self.app.mystic.get(), '1')
        self.assertEqual(self.app.friendship.get(), '3')
        events = [self.app.activity.item(item)['values'][1] for item in self.app.activity.get_children()]
        self.assertIn('Friendship Points purchases: 3.', events)

    def test_owned_engine_runs_below_normal_priority(self):
        self.start_fake(stall=True)
        self.pump_until(lambda: self.app.status.get() == 'Running')
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetPriorityClass.argtypes = [wintypes.HANDLE]
        kernel.GetPriorityClass.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, self.app.process.pid)
        self.assertTrue(handle)
        try:
            self.assertEqual(kernel.GetPriorityClass(handle), 0x4000)
        finally:
            kernel.CloseHandle(handle)
        self.app.stop_refresh()
        self.pump_until(lambda: self.app.status.get() == 'Stopped')

    def test_device_scan_keeps_start_available_to_retry(self):
        with patch.object(gui.threading, 'Thread'):
            DEVICE_SCAN(self.app)
        self.assertEqual(str(self.app.start_button.cget('state')), 'normal')
        self.app._apply_devices(['localhost:6520'], 'Connected.', '')
        self.assertEqual(str(self.app.start_button.cget('state')), 'normal')
        self.assertEqual(self.app._device_address(), 'localhost:6520')

    def test_no_emulator_warning_blocks_engine_but_keeps_start_blue(self):
        result = gui.ConnectionCheck((), 'No connected emulator detected. Open it with ADB enabled.', '')
        with patch.object(gui, 'check_connection', return_value=result), patch.object(gui, 'launch_engine') as launch:
            CONNECTION_CHECK(self.app, self.app._settings())
            self.pump_until(lambda: self.app.status.get() == 'Not connected')
        launch.assert_not_called()
        self.assertIsNone(self.app.setup_window)
        self.assertIsNone(self.app.process)
        self.assertEqual(self.app.run_id, 0)
        self.assertFalse(self.history.exists())
        self.assertFalse(self.config.exists())
        self.assertEqual(str(self.app.start_button.cget('state')), 'normal')
        for dark, background in ((False, '#fff1f2'), (True, '#450a0a')):
            self.app.dark_mode.set(dark)
            self.app._apply_theme()
            self.assertEqual(self.app.home_ui_banner.cget('bg'), background)
            self.assertIn('No connected emulator', self.app.home_ui_hint.get())
        self.app._dismiss_home_ui_hint()
        self.assertFalse(self.app.adb_hint_dismissed.get())
        self.app._set_connection_warning(result.warning, reveal=True)
        self.assertFalse(self.app.home_ui_hint_dismissed)
        self.start_fake()
        self.pump_until(lambda: self.app.status.get() == 'Finished')
        self.assertEqual(self.app.connection_warning, '')

    def test_cancelled_connection_check_cannot_launch_or_open_setup(self):
        settings = self.app._settings()
        with patch.object(gui.threading, 'Thread'), patch.object(gui, 'launch_engine') as launch:
            CONNECTION_CHECK(self.app, settings)
            token = self.app._connection_check_id
            self.app.stop_refresh()
            self.app._complete_connection_check(token, settings, gui.ConnectionCheck((settings.device,), '', '', True))
        launch.assert_not_called()
        self.assertIsNone(self.app.setup_window)
        self.assertEqual(self.app.status.get(), 'Stopped')

    def test_connected_background_emulator_shows_warning_and_launches_nothing(self):
        settings = self.app._settings()
        result = gui.ConnectionCheck((settings.device,), 'Emulator connected in the background. Open its window and Epic Seven, then press Start.', '')
        with patch.object(gui, 'check_connection', return_value=result), patch.object(gui, 'launch_engine') as launch:
            CONNECTION_CHECK(self.app, settings)
            self.pump_until(lambda:self.app.status.get() == 'Not ready')
        launch.assert_not_called()
        self.assertIsNone(self.app.process)
        self.assertIsNone(self.app.setup_window)
        self.assertIn('background',self.app.home_ui_hint.get())
        self.assertEqual(str(self.app.start_button.cget('state')), 'normal')

    def test_stale_scan_cannot_replace_new_connection_result(self):
        self.app._connection_check_id = 2
        self.app.log_queue.put((None, 'devices', (1, gui.ConnectionCheck((), 'Old failed scan', ''), False)))
        self.app._drain_log_queue()
        self.assertEqual(self.app.connection_warning, '')
        self.assertEqual(str(self.app.start_button.cget('state')), 'normal')

    def test_background_scan_does_not_overwrite_manual_address(self):
        self.app._apply_devices(['localhost:6520'], 'Connected.', '')
        self.app.device.set('localhost:6530')
        self.app.log_queue.put((None, 'devices', (self.app._connection_check_id,
            gui.ConnectionCheck(('localhost:6520',), '', ''), True)))
        self.app._drain_log_queue()
        self.assertEqual(self.app._device_address(), 'localhost:6530')

    def test_async_success_checks_connection_before_launch(self):
        settings = self.app._settings()
        success = gui.ConnectionCheck((settings.device,), '', '', True)
        with patch.object(gui, 'check_connection', return_value=success), patch.object(self.app, '_begin_refresh') as begin:
            CONNECTION_CHECK(self.app, settings)
            self.pump_until(lambda: not self.app._checking_connection)
        begin.assert_called_once_with(settings)
        self.assertEqual(self.app.connection_warning, '')

    def test_mixed_history_labels_debug_without_rewriting_csv(self):
        self.history.write_text('Duration,Skystone spent,Gold spent,Covenant bookmark,Mystic medal\n10,9,0,0,0\n20,6,0,0,0,0\n30,3,18000,0,0,1\n')
        original = self.history.read_bytes()
        self.app.refresh_history()
        rows = self.app.history.get_children()
        self.assertEqual([self.app.history.item(row, 'values')[0] for row in rows], ['Debug', 'Debug', 'Normal'])
        self.assertIn('debug', self.app.history.item(rows[0], 'tags'))
        self.assertIn('debug', self.app.history.item(rows[1], 'tags'))
        self.assertNotIn('debug', self.app.history.item(rows[2], 'tags'))
        self.assertEqual(self.history.read_bytes(), original)

    def test_history_scrollbar_follows_actual_overflow(self):
        self.app.deiconify()
        self.app.update()
        if self.app.compact_history:
            self.app.notebook.select(self.app.history_tab)
            self.app.update()
        # Make all columns fit, then simulate a genuinely oversized column.
        columns = self.app.history['columns']
        for key in columns:
            self.app.history.column(key, minwidth=10, width=10, stretch=True)
        self.app.update()
        self.assertEqual(self.app.history.xview(), (0.0, 1.0))
        self.assertFalse(self.app.history_xscroll.winfo_ismapped())
        self.app.history.column('duration', minwidth=self.app.history.winfo_width()*2)
        self.app.update()
        self.assertLess(self.app.history.xview()[1], 1)
        self.assertTrue(self.app.history_xscroll.winfo_ismapped())
        self.app.history.xview_moveto(1)
        self.app.update()
        self.assertGreater(self.app.history.xview()[0], 0)
        self.app.history.column('duration', minwidth=10, width=10)
        self.app.history.xview_moveto(0)
        self.app.update()
        self.assertEqual(self.app.history.xview(), (0.0, 1.0))
        self.assertFalse(self.app.history_xscroll.winfo_ismapped())

    def test_activity_diagnostics_tabs_have_equal_stable_dimensions(self):
        self.app.deiconify()
        self.app.update()
        notebook = self.app.notebook
        tabs = notebook.tabs()[:2]
        def dimensions():
            y = self.app.ui_font.metrics('linespace') // 2 + self.app._dp(8)
            xs = {0: [], 1: []}
            for x in range(notebook.winfo_width()):
                try:
                    index = notebook.index(f'@{x},{y}')
                except gui.tk.TclError:
                    continue
                if index in xs:
                    xs[index].append(x)
            bounds = []
            for index in (0, 1):
                self.assertTrue(xs[index])
                x = xs[index][len(xs[index])//2]
                ys = []
                for y in range(self.app._dp(80)):
                    try:
                        if notebook.index(f'@{x},{y}') == index:
                            ys.append(y)
                    except gui.tk.TclError:
                        pass
                bounds.append((len(xs[index]), len(ys)))
            return bounds
        notebook.select(tabs[0])
        self.app.update()
        before = dimensions()
        notebook.select(tabs[1])
        self.app.update()
        after = dimensions()
        self.assertEqual(before, after)
        self.assertEqual(before[0], before[1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
