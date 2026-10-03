"""Engine selection checks using temporary installations, with no GUI or ADB."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import e7_shop_refresh_gui as gui


class EngineLocationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="e7 location ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.saved = self.root / "engine-location.ini"
        names = ("APP_DIR", "ENGINE_EXE", "ADB_EXE", "CONFIG_FILE", "GUI_CONFIG_FILE", "HISTORY_FILE")
        globals_patch = patch.multiple(gui, **{name: getattr(gui, name) for name in names})
        globals_patch.start()
        self.addCleanup(globals_patch.stop)

    def installation(self, name="engine folder 日本語"):
        directory = self.root / name
        adb = directory / "adb-assets" / "platform-tools" / "adb.exe"
        adb.parent.mkdir(parents=True)
        adb.write_bytes(b"fixture only; never execute")
        (directory / "E7ADBShopRefresh.exe").write_bytes(b"fixture only; never execute")
        return directory

    def resolve(self, override=None, environ=None):
        return gui.resolve_engine_directory(override, environ={} if environ is None else environ,
                                            location_file=self.saved)

    def test_default_and_selection_precedence(self):
        self.assertEqual(self.resolve(), gui.DEFAULT_ENGINE_DIR)
        self.saved.write_text("[engine]\ndirectory = saved folder\n", encoding="utf-8")
        self.assertEqual(self.resolve(), self.root / "saved folder")
        environment = {"E7_ENGINE_DIR": str(self.root / "environment")}
        self.assertEqual(self.resolve(environ=environment), self.root / "environment")
        self.assertEqual(self.resolve(str(self.root / "CLI"), environment), self.root / "CLI")
        self.assertEqual(self.resolve(environ={"E7_ENGINE_DIR": "  "}), self.root / "saved folder")

    def test_saved_percent_variables_and_utf8_bom(self):
        folder = self.root / "engine folder 日本語"
        self.saved.write_text("[engine]\ndirectory = %E7_TEST_ROOT%/engine folder 日本語\n", encoding="utf-8-sig")
        with patch.dict(gui.os.environ, {"E7_TEST_ROOT": str(self.root)}):
            self.assertEqual(self.resolve(), folder)

    def test_malformed_or_empty_setting_does_not_fall_back(self):
        for text in ("not an ini", "[other]\ndirectory = wrong", "[engine]\ndirectory =\n"):
            self.saved.write_text(text, encoding="utf-8")
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.resolve()
        with self.assertRaises(ValueError):
            self.resolve("  ")

    def test_missing_installation_leaves_runtime_paths_unchanged(self):
        original = (gui.APP_DIR, gui.CONFIG_FILE, gui.HISTORY_FILE)
        with self.assertRaisesRegex(ValueError, "E7ADBShopRefresh.exe"):
            gui.configure_engine_directory(self.root / "missing")
        folder = self.installation()
        (folder / "adb-assets" / "platform-tools" / "adb.exe").unlink()
        with self.assertRaisesRegex(ValueError, "adb.exe"):
            gui.configure_engine_directory(folder)
        self.assertEqual((gui.APP_DIR, gui.CONFIG_FILE, gui.HISTORY_FILE), original)

    def test_all_runtime_data_follows_selected_installation(self):
        folder = self.installation()
        assets = gui.ASSET_DIR
        gui.configure_engine_directory(folder)
        self.assertEqual(gui.ENGINE_EXE, folder / "E7ADBShopRefresh.exe")
        self.assertEqual(gui.ADB_EXE, folder / "adb-assets" / "platform-tools" / "adb.exe")
        self.assertEqual(gui.CONFIG_FILE, folder / "ADBconfig.ini")
        self.assertEqual(gui.GUI_CONFIG_FILE, folder / "ShopRefreshGUI.ini")
        self.assertEqual(gui.HISTORY_FILE, folder / "ShopRefreshHistory" / "ADB_History.csv")
        self.assertEqual(gui.ASSET_DIR, assets)

    def test_cli_configures_before_constructing_gui(self):
        folder = self.installation()
        observed = []

        class FakeGui:
            def __init__(self):
                observed.append(gui.APP_DIR)

            def mainloop(self):
                observed.append("mainloop")

        with patch.object(gui, "RefreshGui", FakeGui):
            self.assertEqual(gui.main(["--engine-dir", str(folder)]), 0)
        self.assertEqual(observed, [folder, "mainloop"])

    def test_invalid_cli_aborts_before_gui_or_device_scan(self):
        with patch.object(gui, "RefreshGui") as window, contextlib.redirect_stderr(io.StringIO()) as output:
            with self.assertRaises(SystemExit) as result:
                gui.main(["--engine-dir", str(self.root / "missing")])
        self.assertEqual(result.exception.code, 2)
        window.assert_not_called()
        self.assertIn("Missing:", output.getvalue())

    def test_fake_engine_runs_in_selected_folder(self):
        folder = self.installation()
        gui.configure_engine_directory(folder)
        fake = self.root / "fake_engine.py"
        fake.write_text(
            "import json\nfrom pathlib import Path\n"
            "Path('ADBconfig.ini').write_text('temporary fake settings')\n"
            "Path('ShopRefreshHistory').mkdir()\n"
            "Path('ShopRefreshHistory/ADB_History.csv').write_text('temporary fake history')\n"
            "print(json.dumps(str(Path.cwd())))\n", encoding="utf-8")
        process, tree = gui.launch_engine([sys.executable, str(fake)], cwd=gui.APP_DIR,
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                         text=True, creationflags=gui.NO_WINDOW)
        try:
            output, errors = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0, errors)
            self.assertEqual(Path(json.loads(output)), folder)
            self.assertEqual(gui.CONFIG_FILE.read_text(), "temporary fake settings")
            self.assertEqual(gui.HISTORY_FILE.read_text(), "temporary fake history")
            self.assertFalse((self.root / "ADBconfig.ini").exists())
        finally:
            if process.poll() is None:
                tree.terminate()
                process.wait(timeout=5)
            tree.close()

    def test_windowed_launcher_reports_invalid_folder_without_starting_gui(self):
        with patch.object(gui.sys, "stderr", None), patch.object(gui.tk, "Tk") as root, \
                patch.object(gui.messagebox, "showerror") as dialog, \
                patch.object(gui, "RefreshGui") as window:
            self.assertEqual(gui.main(["--engine-dir", str(self.root / "missing")]), 2)
        root.return_value.withdraw.assert_called_once()
        root.return_value.destroy.assert_called_once()
        self.assertIn("Missing:", dialog.call_args.args[1])
        window.assert_not_called()


if __name__ == "__main__":
    unittest.main()
