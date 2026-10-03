import importlib.util
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import ctypes
import shutil
import wave
from types import SimpleNamespace
from unittest.mock import patch

import e7_shop_refresh_gui as gui
PACKAGED_ASSETS = gui.ASSET_DIR
DEVICE_SCAN = gui.RefreshGui.refresh_devices


class ProtocolTests(unittest.TestCase):
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
prompt("Amount of skystone that you want to spend: ", "30.0")
print("Press enter to start!", flush=True)
assert input() == ""
print("Progress:", flush=True)
print("50% Cove: 1 Myst: 0", end="\\r", flush=True)
if "--stall" in sys.argv:
    time.sleep(30)
print("100% Cove: 1 Myst: 1", flush=True)
Path(sys.argv[1]).write_text("Duration,Skystone spent,Gold spent,Covenant bookmark,Mystic medal\\n10.3,30,464000,1,1\\n")
print("---Result---\\nCovenant bookmark:1\\nMystic medal:1\\nSkystone spent:30", flush=True)
prompt("press enter to exit...", "")
'''


class GuiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.fake = self.root / "fake_engine.py"
        self.fake.write_text(FAKE)
        self.config = self.root / "ADBconfig.ini"
        self.gui_config = self.root / "ShopRefreshGUI.ini"
        self.assets = self.root / 'assets'
        self.assets.mkdir()
        for name in ('start.wav', 'end.wav'):
            shutil.copyfile(PACKAGED_ASSETS / name, self.assets / name)
        self.history = self.root / "history.csv"
        self.patches = [patch.object(gui, "CONFIG_FILE", self.config), patch.object(gui, "GUI_CONFIG_FILE", self.gui_config), patch.object(gui, "ASSET_DIR", self.assets), patch.object(gui, "HISTORY_FILE", self.history), patch.object(gui, "ENGINE_EXE", self.fake), patch.object(gui.RefreshGui, "refresh_devices", lambda _: None), patch("winsound.PlaySound")]
        for p in self.patches:
            p.start()
        import winsound
        self.sound_mock = winsound.PlaySound
        self.app = gui.RefreshGui()
        self.app.withdraw()
        self.app.budget.set("30")
        self.app.tap_sleep.set("0.3")
        self.app.stop_key.set("`")
        self.app.random_offset.set(True)

    def tearDown(self):
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

    def start_fake(self, stall=False):
        real_popen = subprocess.Popen
        def fake_popen(*args, **kwargs):
            return real_popen([sys.executable, "-u", str(self.fake), str(self.history)] + (["--stall"] if stall else []), **kwargs)
        with patch.object(gui.subprocess, "Popen", fake_popen):
            self.app.start_refresh()

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

    def test_end_to_end(self):
        self.start_fake()
        self.pump_until(lambda: self.app.status.get() == "Finished")
        self.assertEqual(self.app.process.returncode, 0)
        self.assertEqual(self.app.spent.get(), "30")
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

    def test_device_scan_waits_before_enabling_start(self):
        with patch.object(gui.threading, 'Thread'):
            DEVICE_SCAN(self.app)
        self.assertEqual(str(self.app.start_button.cget('state')), 'disabled')
        self.app._apply_devices(['localhost:6520'], 'Connected.', '')
        self.assertEqual(str(self.app.start_button.cget('state')), 'normal')
        self.assertEqual(self.app._device_address(), 'localhost:6520')

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
