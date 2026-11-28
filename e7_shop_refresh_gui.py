from __future__ import annotations

import argparse
import configparser
import json
import csv
import math
import os
import queue
import re
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
import tkinter as tk
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from tkinter import font as tkfont, messagebox, ttk, filedialog
from e7_process import launch_engine
from e7_i18n import LANGUAGES, current_locale, set_locale, supported_locale, t
from e7_timing import MIN_TAP_DELAY
from e7_engine_protocol import MAX_BUDGET, MAX_GOLD_CAP, RunSettings, validate_settings, EngineProtocol
from e7_history import history_mode, read_sessions, export_sessions
from e7_input_trace import BoundedSessionLog, format_trace_line
from e7_session_estimate import SessionEstimate
from e7_appearance import Scenery, ThemeHint, currency_icons, theme_icon, avatar_icon, coffee_icon, github_icon, bug_icon
from e7_links import PROFILE, release_url, bug_report_url
from e7_about import AboutDialog
from e7_tracker import CompactTracker, remaining_label
from e7_report import build_report, anonymize, latest_failure, system_name
from e7_setup import missing_references, has_builtin_references, RecognitionSetup, verify_setup_engine
from e7_native_mouse import activate_native_target, release_native_button, MouseElevationRequired
from e7_elevation import restart_as_administrator, restart_command, ElevationCancelled
from e7_connection import check_connection, ConnectionCheck, endpoint_key
from e7_windows_capture import WindowsCapture
from e7_user_data import (prepare_data_directory, ENVIRONMENT_VARIABLE as DATA_DIR_VARIABLE, needs_import_choice,
                          find_older_installs, default_search_roots, record_fresh_start, import_older_install,
                          has_user_data, ImportRefused)

PROJECT_DIR = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
# Windows uses the installed player folder; elsewhere the source folder is the engine.
DEFAULT_ENGINE_DIR = Path.home() / "Downloads" / "E7 Secret Shop Refresh" if os.name == "nt" else PROJECT_DIR
ENGINE_NAME = "E7ADBShopRefresh.exe" if os.name == "nt" else "E7ADBShopRefresh.py"
# Control modes this platform supports. Background drives Epic Seven on Steam
# (directly on Windows, under Proton on Linux) without the real pointer.
CONTROL_MODES = ('Background', 'Mouse', 'ADB') if os.name == "nt" else ('Background',)
# Background is the default everywhere: most players run Steam or STOVE, and it
# leaves the pointer free. Emulators get a one-click switch to Mouse.
DEFAULT_CONTROL_MODE = 'Background'
# A Background pause that the pointer causes; the engine (e7_background.PAUSE_LIMIT)
# stops the session if it has not cleared after this many seconds.
POINTER_PAUSE_LIMIT = 10
POINTER_PAUSE_REASONS = ('The pointer is moving over the game window',  # engines before 0.2.4 (Windows, moving only)
                         'Move your mouse off the game window')         # any pointer over the game (Linux and Windows)


def pointer_pause_text(reason, seconds_left):
    """The red line shown while the pointer is pausing a Background run."""
    where = t('tracker.pointer_moving') if reason.startswith(POINTER_PAUSE_REASONS[0]) else t('tracker.pointer_over_game')
    return t('tracker.pointer_countdown', where=where, seconds=max(0, seconds_left))


# A plain next step under the compact bar for the situations players hit most.
# Each maps an engine message to what is happening and what (if anything) to do.
COMPACT_HINT_SECONDS = 15
NAVIGATION_HINTS = (
    ('Waiting for visible game controls.', 'tracker.close_game_popups'),
    ('The Secret Shop did not open', 'tracker.shop_click_missed'),
    ('The pointer passed over the game and the same confirmation',
     'tracker.confirm_click_missed'),
    ('The game did not take the Confirm click', 'tracker.confirm_retry'),
    ('The game did not open the Buy dialog', 'tracker.buy_retry'),
    ('The game did not open the Refresh dialog', 'tracker.refresh_retry'),
    ('Looking for the home Secret Shop menu', 'tracker.finding_shop'),
    ('Visibility restored', 'tracker.visibility_restored'),
)
CLEAR_HINT_NAVIGATION = ('Secret Shop screen verified',)


def pause_hint(reason):
    """What to do while a Background run is paused."""
    if reason.startswith(POINTER_PAUSE_REASONS[0]):
        return t('tracker.park_mouse')
    if reason.startswith(POINTER_PAUSE_REASONS):
        return t('tracker.move_mouse_away')
    if 'minimized or hidden' in reason:
        return t('tracker.restore_game')
    return ''


def navigation_hint(message):
    """The hint for a Navigation line, '' to clear it, or None to keep the current one."""
    for prefix, key in NAVIGATION_HINTS:
        if message.startswith(prefix):
            return t(key)
    return '' if message.startswith(CLEAR_HINT_NAVIGATION) else None


def mode_label(mode):
    """What the Control mode list shows; settings keep the plain mode name."""
    return {'Background': ('Background · Steam / STOVE (recommended)' if os.name == "nt"
                           else 'Background · Steam (recommended)'),
            'Mouse': 'Mouse · emulators, takes over your pointer',
            'ADB': 'ADB · emulators'}.get(mode, mode)


def mode_title(mode):
    return t('mode.background_title') if mode == 'Background' else mode


# One short line under each mode card; the hint shows the full mode_label.
MODE_CARD_NOTES = {'Background': 'mode.recommended', 'Mouse': 'mode.uses_pointer', 'ADB': 'mode.emulators'}
STATUS_LABELS = {
    'Ready': 'status.ready', 'Checking connection': 'status.checking_connection',
    'Not ready': 'status.not_ready', 'Not connected': 'status.not_connected',
    'Setup required': 'status.setup_required', 'Starting': 'status.starting',
    'Failed': 'status.failed', 'Calibrating': 'status.calibrating', 'Running': 'status.running',
    'Stopped': 'status.stopped', 'Needs attention': 'status.needs_attention', 'Paused': 'status.paused',
    'Waiting for game': 'status.waiting_for_game', 'Waiting for game window': 'status.waiting_for_game_window',
    'Stopping': 'status.stopping', 'Finished': 'status.finished',
}
# Expected buys of each item per skystone spent, for the budget estimates.
COVENANT_RATE, MYSTIC_RATE = 0.006602509, 0.001700646
AUTOSAVE_DELAY_MS = 700


def whole_number_up_to(maximum):
    """Key validator: blank, or digits no longer than the maximum and no larger."""
    digits = len(str(maximum))
    return lambda value: not value or (re.fullmatch(r'[0-9]+', value) is not None and len(value) <= digits
                                       and int(value) <= maximum)


def clamp_saved_amount(text, maximum):
    """Normalize a whole number read from a settings file, lowered to the limit; keep anything else.

    Leading zeros go too, so the box never holds more digits than it lets you type.
    """
    text = str(text).strip()
    if not re.fullmatch(r'[0-9]+', text):
        return text
    if len(text.lstrip('0')) > len(str(maximum)):  # also avoids int() on huge strings
        return str(maximum)
    return str(min(int(text), maximum))


ENGINE_LOCATION_FILE = PROJECT_DIR / "engine-location.ini"
APP_DIR = DEFAULT_ENGINE_DIR
ENGINE_EXE = APP_DIR / ENGINE_NAME
ADB_EXE = APP_DIR / "adb-assets" / "platform-tools" / "adb.exe"
CONFIG_FILE = APP_DIR / "ADBconfig.ini"
GUI_CONFIG_FILE = APP_DIR / "ShopRefreshGUI.ini"
HISTORY_FILE = APP_DIR / "ShopRefreshHistory" / "ADB_History.csv"
# Settings and history; main() points this at the per-user folder (e7_user_data).
DATA_DIR = None
DATA_EVENTS = []
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def engine_command():
    """The engine program: the player EXE on Windows, the source script elsewhere."""
    return [str(ENGINE_EXE)] if ENGINE_EXE.suffix.lower() == '.exe' else [sys.executable, str(ENGINE_EXE)]


ASSET_DIR = PROJECT_DIR / "e7_gui_assets"
try:
    APP_VERSION = (PROJECT_DIR / 'VERSION').read_text(encoding='utf-8-sig').strip()
except OSError:
    APP_VERSION = 'unknown'
STOP_KEY_CHARACTERS = "0123456789abcdefghijklmnopqrstuvwxyz/.,';[]`"
# Tk event.state bits that mean Control or Alt. Windows Tk: Control=0x4,
# Alt=0x10 (also ALT_MASK=0x20000); Mod1=0x8 is Num Lock there. X11: Control=0x4,
# Alt=Mod1=0x8; Mod2=0x10 is Num Lock. Lock states must not reject input.
STOP_KEY_REJECT_MASK = 0x4 | 0x10 | 0x20000 if os.name == "nt" else 0x4 | 0x8
# Saved-settings schema. 2 (0.2.6): timing moved under Advanced; older custom
# timing is reset once to the recommended values below.
SETTINGS_VERSION = 2
RECOMMENDED_TAP_DELAY = "0.3"
RECOMMENDED_TAP_JITTER = 0.03
# The purchase clips run about 0.65 s; a second callout waits for the first.
PURCHASE_SOUND_GAP_MS = 750


def captured_stop_key(keysym, character, state=0):
    # Control/Alt combinations are not supported by the engine's single-key setting.
    if state & STOP_KEY_REJECT_MASK:
        return None
    if keysym == "Escape":
        return "esc"
    key = character.lower()
    return key if len(key) == 1 and key in STOP_KEY_CHARACTERS else None


def resolve_engine_directory(override=None, *, environ=None, location_file=None):
    """Choose CLI, environment, saved location, then the existing default."""
    environment = os.environ if environ is None else environ
    location_file = ENGINE_LOCATION_FILE if location_file is None else Path(location_file)
    selected = override if override is not None else environment.get("E7_ENGINE_DIR")
    if selected is None or (override is None and not selected.strip()):
        selected = None
        if location_file.exists():
            config = configparser.ConfigParser(interpolation=None)
            try:
                with location_file.open(encoding="utf-8-sig") as stream:
                    config.read_file(stream)
                selected = config.get("engine", "directory")
            except (OSError, configparser.Error) as error:
                raise ValueError(t('startup.engine_folder_read_error', file=location_file, error=error)) from error
    if selected is None:
        return DEFAULT_ENGINE_DIR
    selected = selected.strip()
    if not selected:
        raise ValueError(t('startup.engine_folder_empty'))
    # %VAR% is the Windows form; accept it everywhere so one saved setting works on both.
    selected = re.sub(r"%([A-Za-z_][A-Za-z0-9_]*)%", lambda m: os.environ.get(m.group(1), m.group(0)), selected)
    directory = Path(os.path.expandvars(selected)).expanduser()
    if not directory.is_absolute():
        directory = location_file.parent / directory
    return directory.resolve()


def configure_engine_directory(directory):
    """Validate before redirecting any device scans, settings or history."""
    global APP_DIR, ENGINE_EXE, ADB_EXE, CONFIG_FILE, GUI_CONFIG_FILE, HISTORY_FILE
    directory = Path(directory)
    engine = directory / ENGINE_NAME
    adb = directory / "adb-assets" / "platform-tools" / "adb.exe"
    # ADB mode (Windows only) needs the bundled adb.exe; Background needs only the engine.
    required = (engine, adb) if 'ADB' in CONTROL_MODES else (engine,)
    missing = [str(path.relative_to(directory)) for path in required if not path.is_file()]
    if missing:
        raise ValueError(
            t('startup.engine_files_missing', directory=directory, files=', '.join(missing))
        )
    APP_DIR = directory
    ENGINE_EXE, ADB_EXE = engine, adb
    CONFIG_FILE = directory / "ADBconfig.ini"
    GUI_CONFIG_FILE = directory / "ShopRefreshGUI.ini"
    HISTORY_FILE = directory / "ShopRefreshHistory" / "ADB_History.csv"


def configure_data_directory(directory, events=()):
    """Point settings and history at directory; the engine gets it as E7_DATA_DIR."""
    global DATA_DIR, DATA_EVENTS, CONFIG_FILE, GUI_CONFIG_FILE, HISTORY_FILE
    DATA_DIR = Path(directory)
    DATA_EVENTS = list(events)
    CONFIG_FILE = DATA_DIR / "ADBconfig.ini"
    GUI_CONFIG_FILE = DATA_DIR / "ShopRefreshGUI.ini"
    HISTORY_FILE = DATA_DIR / "ShopRefreshHistory" / "ADB_History.csv"


def _read_gui_preferences(path):
    parser = configparser.ConfigParser()
    try:
        # A failed read must not turn into an empty file on the next save.
        with path.open(encoding='utf-8-sig') as stream:
            parser.read_file(stream)
    except FileNotFoundError:
        pass
    return parser


def _write_gui_preferences(path, parser):
    temp = path.with_suffix('.ini.tmp')
    with temp.open('w', encoding='utf-8') as stream:
        parser.write(stream)
    temp.replace(path)


def load_language(path):
    try:
        return supported_locale(_read_gui_preferences(path).get('GUI', 'language', raw=True, fallback='en'))
    except (OSError, UnicodeError, configparser.Error):
        return 'en'


def save_language(path, locale):
    parser = _read_gui_preferences(path)
    if not parser.has_section('GUI'):
        parser.add_section('GUI')
    parser.set('GUI', 'language', supported_locale(locale))
    _write_gui_preferences(path, parser)


def _same_place(first, second):
    try:
        return Path(first).resolve() == Path(second).resolve()
    except OSError:
        return Path(first).absolute() == Path(second).absolute()


def older_installs(data_dir=None):
    """Older versions beside this one, on the Desktop or in Downloads (bounded search)."""
    data_dir = data_dir or DATA_DIR or APP_DIR
    return find_older_installs(default_search_roots(PROJECT_DIR), exclude=(APP_DIR, data_dir))


def apply_import_choice(choice, data_dir):
    """Carry out the import dialog's answer; returns Activity-log lines. Never raises."""
    if choice is None:
        return []  # cancelled
    action, install = choice
    if action == 'fresh':
        try:
            record_fresh_start(data_dir)
        except OSError as error:
            return [f'Could not record the choice to start fresh ({error}); you will be asked again next start.']
        return ['Started with default settings. To bring settings from an older version later, use '
                'Settings › Advanced › Import settings from an older version.']
    try:
        return import_older_install(install.runtime, data_dir)
    except (ImportRefused, OSError, RecursionError) as error:
        return [f'Import from {install.folder} failed: {error} Default settings are used; '
                f'{install.folder} was not changed.']


def relaunch_app():
    """Start this app again with the same engine folder (not elevated); raises OSError."""
    if os.name == 'nt':
        executable, arguments, directory = restart_command(APP_DIR)
        subprocess.Popen(f'"{executable}" {arguments}', cwd=directory, close_fds=True)
        return
    script = Path(__file__).resolve()
    command = [sys.executable] if getattr(sys, 'frozen', False) else [sys.executable, str(script)]
    subprocess.Popen([*command, '--engine-dir', str(Path(APP_DIR).resolve())], cwd=str(script.parent),
                     start_new_session=True, close_fds=True)


def offer_older_settings(data_dir):
    """First start of a fresh extract: offer the settings and history of an older version.

    Closing the question counts as Start fresh: the first start saves the GUI
    settings anyway, after which the question could not be asked again, and
    the Settings button stays available.
    """
    try:
        enable_dpi_awareness()
        root = tk.Tk()
    except tk.TclError:
        return []  # no display: nothing searched, ask next start
    try:
        root.withdraw()
        try:
            root.iconbitmap(default=str(ASSET_DIR / 'shopkeeper-v2.ico'))
        except tk.TclError:
            pass
        from e7_import_dialog import ImportDialog
        dialog = ImportDialog(root, older_installs(data_dir), startup=True)
        root.wait_window(dialog)
        choice = dialog.choice
    except tk.TclError as error:
        return [f'Could not show the question about older settings ({error}); you will be asked next start.']
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass
    return apply_import_choice(choice or ('fresh', None), data_dir)


def engine_environment():
    """Engines from 0.2.8 write session history under E7_DATA_DIR; older ones ignore it."""
    return None if DATA_DIR is None else {**os.environ, DATA_DIR_VARIABLE: str(Path(DATA_DIR).absolute())}


def session_log_folder(mode):
    return {'Mouse': 'mouse-session-logs', 'Background': 'background-session-logs'}.get(mode, 'input-session-logs')


@dataclass(frozen=True)
class BackgroundTarget:
    """The running game (Steam or STOVE), shaped like a Mouse-mode window choice."""
    title: str
    label: str
    handle: int
    pid: int
    rectangle: tuple
    render_handle: int = 0


def list_background_games():
    """Read-only: find Epic Seven (Steam, or STOVE on Windows) and its game window. No input."""
    if os.name == "nt":
        from e7_background import WinGameWindow
        window = WinGameWindow()
        width, height = window.size()
        name = f'Epic Seven ({window.game_client})'
        return [BackgroundTarget(name, name, window.hwnd, window.pid, (0, 0, width, height))]
    from e7_background import XGameWindow, find_proton_session
    find_proton_session()
    window = XGameWindow()
    try:
        width, height = window.size()
        return [BackgroundTarget('Epic Seven (Steam)', 'Epic Seven (Steam)', window.window.id, 0, (0, 0, width, height))]
    finally:
        window.display.close()


def suggested_mode(background, windows, error):
    """Read-only, Windows only: the control mode that suits the game the scan
    found, or None. Background drives Epic Seven on Steam and STOVE; Google
    Play Games and emulators need Mouse mode. Never sends input."""
    if os.name != "nt":
        return None
    try:
        if background:
            if 'supports Epic Seven on Steam' in error:
                return 'Mouse'
            # Only "the game is not running" plus another game window means an
            # emulator or other client. Other errors (two windows, elevation) keep
            # their own instructions.
            if 'is not running' not in error:
                return None
            return 'Mouse' if WindowsCapture().list_windows() else None
        from e7_background import WINDOWS_GAME_EXES
        from e7_native_mouse import process_name
        for window in windows:
            try:
                if process_name(window.pid).lower() in WINDOWS_GAME_EXES:
                    return 'Background'
            except (OSError, ValueError):
                continue
    except Exception:  # a hint only: a failed check never blocks the scan
        return None
    return None


def duration_text(value):
    try:
        seconds = max(0, int(float(value)))
        if seconds >= 3600:
            return f"{seconds // 3600}h {(seconds % 3600) // 60:02d}m {seconds % 60:02d}s"
        return f"{seconds // 60}m {seconds % 60:02d}s"
    except (ValueError, OverflowError, TypeError):
        return "—"


def localized_number(value, spec):
    text = format(value, spec)
    return text.translate(str.maketrans(',.', '.,')) if current_locale() == 'pt_BR' else text


def number_text(value, *, localized=False):
    try:
        n = float(value)
    except (ValueError, TypeError):
        return "—"
    if not math.isfinite(n):
        return "—"
    return localized_number(n, ',.0f') if localized else f"{n:,.0f}"


class RefreshGui(tk.Tk):
    def __init__(self):
        enable_dpi_awareness()
        super().__init__()
        self.title(t('app.window_title'))
        self._configure_scaling()
        self._layout_job = None
        self._icon_job = None
        self._native_icons = None
        self._finalized_run_id = None
        self.stop_key_pressed = False
        self.sound_enabled = tk.BooleanVar(value=True)
        self.sound_covenant = tk.BooleanVar(value=True)
        self.sound_mystic = tk.BooleanVar(value=True)
        self._purchase_counts = {}
        self._purchase_sound_free_at = 0.0
        self.compact_tracker = tk.BooleanVar(value=True)
        self.dark_mode = tk.BooleanVar(value=False)
        self.credits_seen = tk.BooleanVar(value=False)
        self.credits_on_startup = tk.BooleanVar(value=False)
        self.adb_hint_dismissed = tk.BooleanVar(value=False)
        self.about_window = None
        self._live_stats_seen = False
        self._legacy_progress_seen = False
        self.process = None
        self.process_tree = None
        self._exit_seen = False
        self._session_started = False
        self.launch_started_at = None
        self.run_id = 0
        self.log_queue = queue.Queue()
        self.run_settings = None
        self.setup_window = None
        self._recognition_setup_needed = False
        self._connection_check_id = 0
        self._checking_connection = False
        self._device_scan_busy = False
        self._background_scan = False
        self.connection_warning = ''
        # The control mode a scan suggests switching to; the banner offers it.
        self.mode_suggestion = None
        self.control_mode = tk.StringVar(value=DEFAULT_CONTROL_MODE)
        self.mouse_target = tk.StringVar(value='')
        self.mouse_windows = {}
        self._mouse_scan_busy = False
        self.started_at = None
        self.stopping = False
        self.finished = False
        self._mouse_failure = None
        self._gold_stop_reason = None
        self._native_mouse_run = False
        self._structured_adb = False
        self._graceful_stop = False
        self.session_estimate = SessionEstimate()
        self._session_log_path = None
        self.partial_line = ""
        self.raw_output = ""
        self.budget = tk.StringVar(value="12")
        self.gold_cap = tk.StringVar()
        self.tap_sleep = tk.StringVar(value="0.3")
        self.stop_key = tk.StringVar(value="`")
        self.device = tk.StringVar(value="")
        self.device_labels = {}
        self.connected_devices = []
        self.debug_mode = tk.BooleanVar(value=False)
        self.trace_input = tk.BooleanVar(value=False)
        self.buy_friendship = tk.BooleanVar(value=False)
        self.buy_covenant = tk.BooleanVar(value=True)
        self.buy_mystic = tk.BooleanVar(value=True)
        self.random_offset = tk.BooleanVar(value=True)
        self.tap_jitter = tk.DoubleVar(value=0.03)
        self.tap_jitter_text = tk.StringVar()
        self.details_expanded = False
        self._history_signature = None
        self.status = tk.StringVar(value="Ready")
        self.status_label = tk.StringVar(value=t('status.ready'))
        self.status.trace_add('write', self._update_status_label)
        self.detail = tk.StringVar(value=t('session.open_shop'))
        self.home_ui_hint = tk.StringVar(value=t('session.home_or_shop'))
        self.home_ui_hint_dismissed = False
        self.setting_notice = tk.StringVar(value="")
        self.device_notice = tk.StringVar(value=t('connection.checking_devices'))
        self.history_notice = tk.StringVar(value="")
        self.elapsed = tk.StringVar(value="0m 00s")
        self.remaining_time = tk.StringVar(value='Time remaining: —')
        self.remaining_display = tk.StringVar(value=remaining_label(self.remaining_time.get()))
        self.remaining_time.trace_add('write', lambda *_: self.remaining_display.set(
            remaining_label(self.remaining_time.get())))
        self.spent = tk.StringVar(value="—")
        self.spent_display = tk.StringVar(value="0 / 12")
        self.spent.trace_add('write', lambda *_: self._update_spent_display())
        self.covenant = tk.StringVar(value="—")
        self.mystic = tk.StringVar(value="—")
        self.friendship = tk.StringVar(value="—")
        self.diagnostics_summary=tk.StringVar(value=t('diagnostics.initial_purchases'))
        for var in (self.covenant,self.mystic,self.friendship,self.buy_friendship,self.buy_covenant,self.buy_mystic):
            var.trace_add('write',lambda *_:self._update_diagnostics_summary())
        self.progress_text = tk.StringVar(value=t('session.waiting_for_session'))
        # Red line in the full view and the compact bar while the pointer pauses a Background run.
        self.pointer_alert = tk.StringVar(value='')
        self._pointer_reason = ''
        self._pointer_deadline = None
        self._pointer_job = None
        self._background_run = False
        # One muted line under the compact bar: what is happening and what to do.
        self.compact_hint = tk.StringVar(value='')
        self._hint_job = None
        self.ev = tk.StringVar()
        self._load_config()
        self._build_ui()
        self.scenery = Scenery(self, ASSET_DIR)
        self.tracker = CompactTracker(self, ASSET_DIR, (self.header_frame, self.body_frame))
        self.status.trace_add('write', lambda *_: self.tracker.status_changed())
        self.status.trace_add('write', lambda *_: self._update_compact_button())
        self.status.trace_add('write', lambda *_: self.status.get() != 'Paused' and self._clear_pointer_alert())
        self._apply_theme()
        self._update_home_ui_hint()
        self._load_icon()
        self._fit_initial_window()
        self.bind('<Map>', self._schedule_native_icon, add='+')
        self._schedule_native_icon()
        if self.control_mode.get() == 'ADB':
            self.refresh_devices()
        else:
            self._change_control_mode()
        self.refresh_history()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(100, self._drain_log_queue)
        self.after(300, self._maybe_show_credits)
        self.after(10000, self._rescan_idle_devices)
        self.after(3000, self._poll_history)
        self._autosave_saved = self._autosave_snapshot()  # startup tidying is not an edit
        for text in DATA_EVENTS:
            self._event(text)

    def _update_status_label(self, *_):
        state = self.status.get()
        key = STATUS_LABELS.get(state)
        self.status_label.set(t(key) if key else state)

    def _configure_scaling(self):
        self.ui_scale = self.winfo_fpixels("1i") / 96.0

    def _load_icon(self):
        try:
            if os.name == "nt":
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("E7.SecretShopRefresh.GUI")
            frames = sorted((ASSET_DIR / "window-icons").glob("*.png"), key=lambda p: int(p.stem))
            if frames:
                self._icon_images = [tk.PhotoImage(master=self, data=frame.read_bytes()) for frame in frames]
                self.iconphoto(True, *self._icon_images)
                return
            png = ASSET_DIR / "shopkeeper-window.png"
            if not png.is_file():
                png = ASSET_DIR / "shopkeeper.png"
            if png.is_file():
                self._icon_image = tk.PhotoImage(master=self, data=png.read_bytes())
                self.iconphoto(True, self._icon_image)
        except (OSError, tk.TclError, AttributeError):
            pass

    def _update_settings_scroll(self, _event=None):
        if hasattr(self, '_settings_redraw'):
            self.settings_canvas.coords(self._settings_redraw, 0, 0, 1, 1)
        self.settings_canvas.configure(scrollregion=self.settings_canvas.bbox(self.settings_controls_window))
        if self.settings_controls.winfo_reqheight() > self.settings_canvas.winfo_height() + self._dp(2):
            self.settings_scroll.grid(row=0, column=1, sticky="ns")
        else:
            self.settings_scroll.grid_remove()
            self.settings_canvas.yview_moveto(0)

    def _schedule_native_icon(self, event=None):
        if os.name != 'nt' or (event is not None and event.widget is not self):
            return
        if self._icon_job is None:
            self._icon_job = self.after_idle(self._apply_native_icon)

    def _apply_native_icon(self):
        self._icon_job = None
        icon_path = ASSET_DIR / 'shopkeeper-v2.ico'
        if not icon_path.is_file():
            return
        try:
            import ctypes
            from ctypes import wintypes
            from e7_windows_icon import WindowIcons
            user = ctypes.WinDLL('user32', use_last_error=True)
            user.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
            user.GetAncestor.restype = wintypes.HWND
            hwnd = user.GetAncestor(self.winfo_id(), 2)  # GA_ROOT
            replacement = WindowIcons(hwnd, icon_path.read_bytes())
            if self._native_icons:
                self._native_icons.close()
            self._native_icons = replacement
        except (OSError, ValueError, AttributeError, ImportError) as exc:
            self._append_log(f'\nNative window icon could not be set: {exc}\n')

    def _dp(self, value):
        return max(1, round(value * self.ui_scale))

    def _screen_work_area(self):
        if os.name == "nt":
            try:
                import ctypes
                from ctypes import wintypes
                rect = wintypes.RECT()
                if ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(rect), 0):
                    return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top
            except (AttributeError, OSError):
                pass
        return 0, 0, self.winfo_screenwidth(), self.winfo_screenheight()

    def _fit_initial_window(self):
        left, top, screen_width, screen_height = self._screen_work_area()
        margin = self._dp(24)
        width = min(self._dp(1500), screen_width - margin * 2)
        height = min(self._dp(940), screen_height - margin * 2 - self._dp(32))
        # Small work areas remain usable through scrolling rather than a minimum
        # window size that extends beyond the monitor.
        self.minsize(min(self._dp(1100), width), min(self._dp(700), height))
        self.geometry(f"{width}x{height}+{left + (screen_width-width)//2}+{top + margin}")

    def _build_timing_slider_style(self, style, dark, trough, border):
        # Clam's stock slider ignores sliderthickness. Image elements establish
        # a real 32px minimum height for both the thumb and its trough.
        if not hasattr(self, '_timing_slider_palettes'):
            self._timing_slider_palettes = {}
        prefix = 'DarkTapTiming' if dark else 'LightTapTiming'
        if prefix not in self._timing_slider_palettes:
            width, height, edge = self._dp(26), self._dp(32), self._dp(2)
            images = []
            for color, outline, grip in (('#60a5fa' if dark else '#2563eb', '#1d4ed8', '#ffffff'),
                                          ('#3b82f6', '#1d4ed8', '#ffffff'),
                                          ('#475569' if dark else '#cbd5e1', border, '#94a3b8')):
                image = tk.PhotoImage(master=self, width=width, height=height)
                image.put(outline, to=(0, 0, width, height))
                image.put(color, to=(edge, edge, width-edge, height-edge))
                for offset in (-3, 3):
                    x = width//2 + round(offset*self.ui_scale)
                    image.put(grip, to=(x, self._dp(8), x+self._dp(1), height-self._dp(8)))
                images.append(image)
            self._timing_slider_palettes[prefix] = images
            style.element_create(prefix+'.slider', 'image', images[0], ('disabled', images[2]),
                                 ('active', images[1]))
        style.layout('TapTiming.Horizontal.TScale', [('Horizontal.Scale.trough', {'sticky': 'nswe',
            'children': [(prefix+'.slider', {'side': 'left', 'sticky': 'ns'})]})])
        style.configure('TapTiming.Horizontal.TScale', troughcolor=trough, bordercolor=border,
                        lightcolor=border, darkcolor=border)

    def _build_checkbox_style(self, style):
        side = self._dp(20)
        border = self._dp(2)
        dark = self.dark_mode.get()
        prefix = 'DarkCheck' if dark else 'LargeCheck'
        if not hasattr(self, '_checkbox_palettes'):
            self._checkbox_palettes = {}
        if prefix in self._checkbox_palettes:
            style.layout("Large.TCheckbutton", self._checkbox_palettes[prefix])
            return
        images = []
        for selected, disabled in ((False, False), (True, False), (False, True), (True, True)):
            image = tk.PhotoImage(master=self, width=side + self._dp(10), height=side)
            image.put("#475569" if dark and disabled else "#94a3b8" if disabled else "#64748b", to=(0, 0, side, side))
            image.put("#334155" if dark and disabled else "#cbd5e1" if disabled else "#2563eb" if selected else "#1e293b" if dark else "#ffffff", to=(border, border, side-border, side-border))
            if selected:
                for x in range(self._dp(4), side-self._dp(4)):
                    y = round(side * (0.55 + (x/side - 0.2) if x < side*0.43 else 0.78 - (x/side - 0.43)))
                    for dy in range(-border//2, border//2+1):
                        if 0 <= y+dy < side:
                            image.put("#ffffff", to=(x, y+dy))
            images.append(image)
        if not hasattr(self, 'checkbox_images'):
            self.checkbox_images = []
        self.checkbox_images.extend(images)
        off, on, disabled_off, disabled_on = images
        style.element_create(prefix + ".indicator", "image", off, ("disabled", "selected", disabled_on), ("disabled", disabled_off), ("selected", on), sticky="w")
        layout = [("Checkbutton.padding", {"sticky": "nswe", "children": [(prefix + ".indicator", {"side": "left", "sticky": "w"}), ("Checkbutton.focus", {"side": "left", "sticky": "w", "children": [("Checkbutton.label", {"sticky": "nswe"})]})]})]
        self._checkbox_palettes[prefix] = layout
        style.layout("Large.TCheckbutton", layout)
        style.configure("Large.TCheckbutton", background="#f3f5f8", font=self.ui_font, padding=(0, self._dp(5)))

    def _style_settings_tiles(self, style, dark, bg, field, fg, muted, border, active):
        """Card look for the mode and item toggles, chips, keycap and Start."""
        chosen_bg, chosen_border = ('#1e3a8a', '#60a5fa') if dark else ('#dbeafe', '#2563eb')
        layout = [('Toolbutton.border', {'sticky': 'nswe', 'children': [('Toolbutton.focus', {'sticky': 'nswe', 'children': [
            ('Toolbutton.padding', {'sticky': 'nswe', 'children': [('Toolbutton.label', {'sticky': 'nswe'})]})]})]})]
        for name in ('Tile.TCheckbutton', 'Tile.TRadiobutton', 'Tile.Pill.TCheckbutton'):
            style.layout(name, layout)
            style.configure(name, background=field, foreground=fg, bordercolor=border, lightcolor=field, darkcolor=field,
                            relief='raised', borderwidth=self._dp(2), padding=(self._dp(4), self._dp(5)),
                            anchor='center', justify='center', font=self.ui_font, focuscolor=chosen_border)
            style.map(name, background=[('disabled', bg), ('selected', chosen_bg), ('active', active)],
                      bordercolor=[('selected', chosen_border), ('active', chosen_border)],
                      lightcolor=[('selected', chosen_bg), ('active', active)],
                      darkcolor=[('selected', chosen_bg), ('active', active)],
                      foreground=[('disabled', muted)], relief=[('pressed', 'raised')])
        style.configure('Tile.Pill.TCheckbutton', padding=(self._dp(6), self._dp(7)))
        style.configure('Section.TLabel', font=self.heading_font)
        style.configure('Keycap.TEntry', padding=(self._dp(6), self._dp(6)))
        style.configure('Start.Accent.TButton', font=self.heading_font, padding=(self._dp(10), self._dp(12)))
        style.configure('Stop.TButton', padding=(self._dp(8), self._dp(12)))

    def _apply_theme(self):
        dark = self.dark_mode.get()
        bg, field, fg, muted, border, active = (
            ('#111827', '#1e293b', '#e2e8f0', '#94a3b8', '#475569', '#334155') if dark else
            ('#f3f5f8', '#ffffff', '#1e293b', '#64748b', '#cbd5e1', '#e2e8f0'))
        style = ttk.Style(self)
        self.configure(bg=bg)
        self.settings_canvas.configure(bg=bg)
        for name in ('TFrame', 'TLabel', 'TLabelframe', 'TLabelframe.Label', 'Large.TCheckbutton'):
            style.configure(name, background=bg, foreground=fg, bordercolor=border)
        style.configure('Muted.TLabel', foreground=muted)
        style.configure('Placeholder.TLabel', background=field, foreground=muted, font=self.ui_font)
        style.map('Placeholder.TLabel', background=[('disabled', bg)])
        style.configure('Alert.TLabel', foreground='#fca5a5' if dark else '#b91c1c')
        style.configure('Status.TLabel', foreground=('#fbbf24' if dark else '#92400e') if self.status.get() in ('Waiting for game','Waiting for game window') else ('#60a5fa' if dark else '#2563eb'))
        self._style_home_ui_banner()
        for name in ('TEntry', 'TCombobox'):
            style.configure(name, background=field, fieldbackground=field, foreground=fg, insertcolor=fg, bordercolor=border, lightcolor=border, darkcolor=border, arrowcolor=fg)
            style.map(name, background=[('disabled', bg), ('readonly', field)], fieldbackground=[('disabled', bg), ('readonly', field)], foreground=[('disabled', muted), ('readonly', fg)], arrowcolor=[('disabled', muted), ('!disabled', fg)])
        for name in ('TButton', 'Treeview.Heading'):
            style.configure(name, background=active, foreground=fg, bordercolor=border, lightcolor=border, darkcolor=border)
            style.map(name, background=[('active', border)], foreground=[('disabled', muted)])
        style.configure('Coffee.TButton', space=self._dp(10), anchor='w')
        style.configure('Accent.TButton', background='#2563eb', foreground='#ffffff')
        style.map('Accent.TButton', background=[('disabled', active), ('active', '#1d4ed8')], foreground=[('disabled', muted), ('!disabled', '#ffffff')])
        style.map('Large.TCheckbutton', foreground=[('disabled', muted)], background=[('active', bg)])
        self._style_settings_tiles(style, dark, bg, field, fg, muted, border, active)
        style.configure('Treeview', background=field, fieldbackground=field, foreground=fg, bordercolor=border)
        style.map('Treeview', background=[('selected', '#2563eb')], foreground=[('selected', '#ffffff')])
        self.history.tag_configure('even', background=bg, foreground=fg)
        self.history.tag_configure('debug', background='#422006' if dark else '#fff4d6', foreground='#fcd34d' if dark else '#92400e')
        for tag, color in (('covenant', '#67e8f9' if dark else '#0e7490'),
                           ('mystic', '#c4b5fd' if dark else '#6d28d9'),
                           ('friendship', '#f9a8d4' if dark else '#be185d'),
                           ('success', '#86efac' if dark else '#166534'),
                           ('warning', '#fcd34d' if dark else '#92400e'),
                           ('error', '#fca5a5' if dark else '#b91c1c')):
            self.activity.tag_configure(tag, foreground=color)
        style.configure('TNotebook', background=bg, bordercolor=border)
        tabs = [('selected', bg), ('active', active), ('!selected', field)]
        style.map('TNotebook.Tab', background=tabs, lightcolor=tabs, darkcolor=tabs, foreground=[('selected', fg), ('!selected', muted)])
        for name in ('TScrollbar', 'Horizontal.TScrollbar', 'Vertical.TScrollbar'):
            style.configure(name, background=active, troughcolor=bg, arrowcolor=fg, bordercolor=border, lightcolor=border, darkcolor=border)
            style.map(name, background=[('active', border), ('!disabled', active)], arrowcolor=[('disabled', muted), ('!disabled', fg)])
        style.configure('Horizontal.TProgressbar', troughcolor=active, bordercolor=border)
        self._build_timing_slider_style(style, dark, active, border)
        self.log.configure(bg=field, fg=fg, insertbackground=fg, selectbackground='#2563eb', selectforeground='#ffffff')
        for option, color in (('background', field), ('foreground', fg), ('selectBackground', '#2563eb'), ('selectForeground', '#ffffff')):
            self.option_add('*TCombobox*Listbox.' + option, color)
        self._build_checkbox_style(style)
        style.configure('Large.TCheckbutton', background=bg, foreground=fg)
        target = t('theme.switch_light') if dark else t('theme.switch_dark')
        self.theme_image = theme_icon(self, self._dp(25), dark)
        self.theme_button.configure(text=target if self.theme_image else ('☀' if dark else '☾'), image=self.theme_image or '', compound='none')
        self.github_image = github_icon(self, ASSET_DIR, self._dp(24), dark, color='#60a5fa' if dark else '#2563eb')
        self.github_button.configure(image=self.github_image or '', text='' if self.github_image else t('app.github'))
        if hasattr(self, 'scenery'):
            self.scenery.schedule()
        if self.about_window is not None and self.about_window.winfo_exists():
            self.about_window.apply_theme(dark)

    def _maybe_show_credits(self):
        if self.winfo_viewable() and (not self.credits_seen.get() or self.credits_on_startup.get()):
            self._show_about()

    def _import_older_settings(self):
        """Settings › Advanced: import settings and history from an older version, after the first start."""
        if self.process and self.process.poll() is None:
            messagebox.showinfo(t('import_settings.action'), t('import_settings.stop_first'), parent=self)
            return
        if DATA_DIR is None or _same_place(DATA_DIR, APP_DIR):
            messagebox.showinfo(t('import_settings.action'), t('import_settings.unavailable',
                directory=APP_DIR), parent=self)
            return
        from e7_import_dialog import ImportDialog
        dialog = ImportDialog(self, older_installs(), startup=False, scale=self._dp)
        self.wait_window(dialog)
        if dialog.choice is None:
            return
        install = dialog.choice[1]
        try:
            self._flush_autosave()  # first, so the check below and the backup see the latest settings
            replace = has_user_data(DATA_DIR)
        except OSError as error:
            messagebox.showerror(t('import_settings.action'), t('import_settings.failed', error=error), parent=self)
            return
        if replace and not messagebox.askyesno(
                t('import_settings.replace_title'),
                t('import_settings.replace_confirm',
                    folder=install.folder,
                    backup=Path(DATA_DIR) / 'legacy-backup'), parent=self):
            return
        self._autosave_suspended = True
        try:
            events = import_older_install(install.runtime, DATA_DIR, replace=replace)
        except (ImportRefused, OSError, RecursionError) as error:
            self._autosave_suspended = False
            self._event(f'Import from {install.folder} failed: {error}')
            messagebox.showerror(t('import_settings.action'), t('import_settings.failed', error=error), parent=self)
            return
        # The imported files are loaded by a fresh start, not into this window:
        # a reload here would mix them with what this window already holds
        # (control mode and its target, settings the import did not include).
        # Until then nothing is saved over them and no session starts.
        self._restart_required = True
        job = getattr(self, '_autosave_job', None)
        if job is not None:
            self.after_cancel(job)
            self._autosave_job = None
        for text in events:
            self._event(text)
        messagebox.showinfo(t('import_settings.action'), t('import_settings.restart_now',
            folder=install.folder), parent=self)
        try:
            relaunch_app()
        except OSError as error:
            self._event(f'The app could not restart itself ({error}). Close and reopen it to use the imported settings.')
            messagebox.showinfo(t('import_settings.action'), t('import_settings.restart_failed'), parent=self)
            return
        self.destroy()

    def _restart_pending(self):
        if not getattr(self, '_restart_required', False):
            return False
        messagebox.showinfo(t('import_settings.restart_needed_title'), t('import_settings.restart_needed'), parent=self)
        return True

    def _show_about(self):
        if self.about_window is not None and self.about_window.winfo_exists():
            self.about_window.lift()
            return
        self.about_window = AboutDialog(self, PROJECT_DIR, first_time=not self.credits_seen.get())

    def _save_credits_preference(self):
        try:
            self._write_sound_preference()
        except (OSError, UnicodeError, configparser.Error) as exc:
            self.setting_notice.set(t('settings.credits_unsaved'))
            self._append_log(f'Credits preference save failed: {exc}\n')

    def _toggle_dark_mode(self):
        self.dark_mode.set(not self.dark_mode.get())
        self._apply_theme()
        try:
            self._write_sound_preference()
        except (OSError, UnicodeError, configparser.Error) as exc:
            self.setting_notice.set(t('settings.theme_unsaved'))
            self._append_log(f'Theme preference save failed: {exc}\n')

    def _update_home_ui_hint(self, *_):
        waiting = self.status.get() in ('Waiting for game','Waiting for game window')
        reminder = (t('session.reveal_controls') if waiting else
                    t('session.home_or_shop_reminder'))
        if not self.adb_hint_dismissed.get() and not waiting:
            reminder = t('connection.use_adb_emulator')
        if self.control_mode.get() == 'Mouse':
            reminder = t('mode.mouse_pointer_hint')
        elif self.control_mode.get() == 'Background':
            reminder = t('mode.background_pointer_hint')
        suggestion = self.mode_suggestion
        if suggestion == 'Background' and not self.connection_warning:
            reminder = t('mode.background_detected')
        self.home_ui_hint.set(self.connection_warning or reminder)
        if suggestion:
            self.home_ui_action.configure(text=t('mode.switch_to', mode=mode_title(suggestion)))
            self.home_ui_action.grid()
        else:
            self.home_ui_action.grid_remove()
        self._style_home_ui_banner()
        dark = self.dark_mode.get()
        ttk.Style(self).configure('Status.TLabel', foreground=('#fbbf24' if dark else '#92400e') if waiting else ('#60a5fa' if dark else '#2563eb'))
        if hasattr(self, 'right_panel'):
            self._schedule_layout()

    def _style_home_ui_banner(self):
        dark = self.dark_mode.get()
        error = bool(self.connection_warning)
        bg, fg, border, hover = (('#450a0a', '#fecaca', '#ef4444', '#7f1d1d') if dark else
                                 ('#fff1f2', '#991b1b', '#dc2626', '#ffe4e6')) if error else (
                                 ('#422006', '#fbbf24', '#b45309', '#78350f') if dark else
                                 ('#fff4d6', '#92400e', '#f59e0b', '#fde68a'))
        self.home_ui_banner.configure(bg=bg, highlightbackground=border)
        self.home_ui_notice.configure(bg=bg, fg=fg)
        style = ttk.Style(self)
        style.configure('Dismiss.TButton', background=bg, foreground=fg, bordercolor=bg,
                        lightcolor=bg, darkcolor=bg, borderwidth=0, padding=0, font=self.heading_font)
        style.map('Dismiss.TButton', background=[('active', hover)], foreground=[('active', fg)])
        style.configure('BannerAction.TButton', background=bg, foreground=fg, bordercolor=border,
                        lightcolor=bg, darkcolor=bg, borderwidth=1, font=self.heading_font)
        style.map('BannerAction.TButton', background=[('active', hover)], foreground=[('active', fg)])

    def _set_connection_warning(self, warning, *, reveal=False):
        changed = warning != self.connection_warning
        self.connection_warning = warning
        if warning and (changed or reveal):
            self.home_ui_hint_dismissed = False
            self.home_ui_banner.grid()
        self._update_home_ui_hint()
        self._schedule_layout()

    def _dismiss_home_ui_hint(self):
        if self.control_mode.get() == 'ADB' and not self.connection_warning and not self.adb_hint_dismissed.get() and self.status.get() != 'Waiting for game':
            self.adb_hint_dismissed.set(True)
            try:
                self._write_sound_preference()
            except (OSError, UnicodeError, configparser.Error) as exc:
                self.setting_notice.set(t('settings.reminder_unsaved'))
                self._append_log(f'ADB reminder preference save failed: {exc}\n')
        self.home_ui_hint_dismissed = True
        self.home_ui_banner.grid_remove()
        self._schedule_layout()

    def _schedule_layout(self, _event=None):
        if getattr(self, 'tracker', None) is not None and self.tracker.active:
            return  # Hidden widgets report 1-pixel sizes; lay out after restore.
        if self._layout_job is not None:
            self.after_cancel(self._layout_job)
        self._layout_job = self.after(35, self._layout_dashboard)

    def _layout_dashboard(self):
        self._layout_job = None
        left, top, right, bottom = self._dashboard_pad
        width = self.right_panel.winfo_width() - left - right  # inside the card's padding
        self.home_ui_notice.configure(wraplength=max(self._dp(200), width-self._dp(75)))
        self.detail_label.configure(wraplength=max(self._dp(250), width-self._dp(12)))
        self.diagnostics_label.configure(wraplength=max(self._dp(250), width-self._dp(60)))
        self.remaining_label.configure(wraplength=max(self._dp(250), width-self._dp(12)))
        inline_logs = width-self._dp(28) >= sum(widget.winfo_reqwidth() for widget in (
            self.trace_check, self.open_logs_button, self.copy_diagnostics_button)) + self._dp(20)
        self.trace_check.grid(columnspan=1 if inline_logs else 3)
        self.open_logs_button.grid(row=0 if inline_logs else 1, column=1 if inline_logs else 0,
                                   padx=(self._dp(6), self._dp(6)) if inline_logs else (0, 0),
                                   pady=(0 if inline_logs else self._dp(6), 0))
        self.copy_diagnostics_button.grid(row=0 if inline_logs else 1, column=2,
                                          pady=(0 if inline_logs else self._dp(6), 0))
        self.history_label.configure(wraplength=max(self._dp(250), width-self._dp(12)))
        # Keep Mystic and Friendship adjacent even when the cards wrap.
        minimum_card = max(self.heading_font.measure(t('session.skystone_spent_estimated')) + self._dp(38), self.value_font.measure("12h 59m 59s")) + self._dp(32)
        columns = 5 if width >= minimum_card*5+self._dp(24) else 3 if width >= minimum_card*3+self._dp(12) else 2
        for i in range(len(self.metric_cards)):
            self.metrics.columnconfigure(i, weight=1 if i < columns else 0, minsize=0, uniform="metrics" if i < columns else "")
        for i, card in enumerate(self.metric_cards):
            row,column,span=(0,0,2) if columns==2 and i==0 else ((i+1)//2,(i+1)%2,1) if columns==2 else (i//columns,i%columns,1)
            card.grid(row=row,column=column,columnspan=span,sticky="nsew",padx=(0 if column==0 else self._dp(6),0),pady=(0,self._dp(6) if columns<5 else 0))
        # Measure both messages even when detail is hidden in a short window,
        # so hiding it cannot flip the layout back and forth on the next pass.
        banner_height = 0 if self.home_ui_hint_dismissed else self.home_ui_banner.winfo_reqheight() + self._dp(6)
        messages_height = banner_height + self.detail_label.winfo_reqheight()
        required_height = sum(widget.winfo_reqheight() for widget in (self.session_title, self.metrics, self.progress_frame, self.history_header, self.history_label)) + messages_height + self.table_rowheight*6 + self._dp(160)
        inner_height = self.right_panel.winfo_height() - top - bottom
        compact = inner_height < required_height
        if compact != self.compact_history:
            self.compact_history = compact
            for widget in (self.history_header, self.history_frame, self.history_label):
                widget.grid_forget()
            if compact:
                self.notebook.add(self.history_tab, text=t('history.tab'))
                self.history_header.grid(in_=self.history_tab, row=0, column=0, sticky="ew", pady=(0, self._dp(6)))
                self.history_frame.grid(in_=self.history_tab, row=1, column=0, sticky="nsew")
                self.history_label.grid(in_=self.history_tab, row=2, column=0, sticky="w", pady=(self._dp(6), 0))
                self.right_panel.rowconfigure(6, weight=0, minsize=0)
            else:
                self.notebook.forget(self.history_tab)
                self.history_header.grid(row=5, column=0, sticky="ew", pady=(self._dp(16), self._dp(6)))
                self.history_frame.grid(row=6, column=0, sticky="nsew")
                self.history_label.grid(row=7, column=0, sticky="w", pady=(self._dp(6), 0))
                self.right_panel.rowconfigure(6, weight=2, minsize=self.table_rowheight*3+self._dp(55))
        top_height = sum(widget.winfo_reqheight() for widget in (self.session_title, self.metrics, self.progress_frame)) + messages_height + self._dp(40)
        condensed = compact and inner_height < top_height + self.table_rowheight*2 + self._dp(90)
        self.session_title.grid_remove() if condensed else self.session_title.grid()
        critical_detail = self.status.get() in ('Needs attention', 'Paused', 'Waiting for game', 'Not ready', 'Not connected', 'Failed')
        self.detail_label.grid_remove() if condensed and not critical_detail else self.detail_label.grid()
        content_selected = compact and self.notebook.select() != self.notebook.tabs()[0]
        for widget in (self.metrics, self.progress_frame):
            widget.grid_remove() if content_selected else widget.grid()
        self.right_panel.rowconfigure(4, minsize=self.table_rowheight*(2 if condensed else 3)+self._dp(55))

    def _play_session_sound(self, outcome):
        if not self.sound_enabled.get():
            return
        try:
            try:
                import winsound
            except ImportError:
                import e7_sound as winsound
            sound = ASSET_DIR / ("start.wav" if outcome == "started" else "end.wav")
            if sound.is_file():
                winsound.PlaySound(str(sound), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
            else:
                alias = "SystemAsterisk" if outcome == "started" else "SystemExclamation"
                winsound.PlaySound(alias, winsound.SND_ALIAS | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        except (OSError, RuntimeError):
            self._append_log("\nThe session sound could not be played.\n")

    def _announce_purchases(self, stats):
        """Say "Covenant!"/"Mystic!" once per confirmed purchase count increase."""
        due = []
        for key, enabled in (('covenant', self.sound_covenant), ('mystic', self.sound_mystic)):
            before = self._purchase_counts.get(key, 0)
            self._purchase_counts[key] = stats[key]
            if stats[key] > before and enabled.get():
                due.append(key)
        if not due:
            return
        # SND_ASYNC cuts off a playing sound, so each callout, from this
        # update or a later one, waits for the one queued before it.
        now = time.monotonic()
        for key in due:
            start = max(now, self._purchase_sound_free_at)
            self._purchase_sound_free_at = start + PURCHASE_SOUND_GAP_MS / 1000
            self.after(round((start - now) * 1000), lambda key=key, run_id=self.run_id: self._play_purchase_sound(key, run_id))

    def _play_purchase_sound(self, key, run_id):
        enabled = self.sound_covenant if key == 'covenant' else self.sound_mystic
        # A finished session has played its end chime; a late callout would cut it off.
        if run_id != self.run_id or self._finalized_run_id == run_id or not enabled.get():
            return
        sound = ASSET_DIR / f'purchase-{key}.wav'
        if not sound.is_file():
            return
        try:
            try:
                import winsound
            except ImportError:
                import e7_sound as winsound
            winsound.PlaySound(str(sound), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        except (OSError, RuntimeError):
            self._append_log(f"\nThe {key} purchase sound could not be played.\n")

    def _build_ui(self):
        dp = self._dp
        self.ui_font = tkfont.Font(self, family="Segoe UI", size=12)
        self.heading_font = tkfont.Font(self, family="Segoe UI", size=12, weight="bold")
        self.value_font = tkfont.Font(self, family="Segoe UI", size=20, weight="bold")
        for name in ("TkDefaultFont", "TkTextFont"):
            tkfont.nametofont(name, root=self).configure(family="Segoe UI", size=12)
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#f3f5f8")
        style.configure("TLabel", background="#f3f5f8", foreground="#1e293b", font=self.ui_font)
        style.configure("Title.TLabel", font=("Segoe UI", 22, "bold"))
        style.configure("Muted.TLabel", foreground="#64748b")
        style.configure("Value.TLabel", font=self.value_font)
        style.configure("TButton", font=self.ui_font, padding=(dp(12), dp(7)))
        style.configure("TEntry", font=self.ui_font, padding=dp(5))
        style.configure("TCombobox", font=self.ui_font, padding=dp(5), arrowsize=dp(20))
        style.configure("TScrollbar", arrowsize=dp(16))
        style.configure("TNotebook", background="#e2e8f0", bordercolor="#cbd5e1", tabmargins=(dp(2), dp(2), dp(2), 0))
        style.configure("TNotebook.Tab", font=self.ui_font, padding=(dp(12), dp(6)), foreground="#1e293b", bordercolor="#94a3b8")
        tab_colors = [("selected", "#f3f5f8"), ("active", "#e2e8f0"), ("!selected", "#cbd5e1")]
        style.map("TNotebook.Tab", background=tab_colors, lightcolor=tab_colors, darkcolor=tab_colors,
                  foreground=[("selected", "#1e293b"), ("!selected", "#1e293b")],
                  padding=[('selected', (dp(12), dp(6))), ('!selected', (dp(12), dp(6)))])
        style.configure("Accent.TButton", background="#2563eb", foreground="white")
        style.map("Accent.TButton", background=[("disabled", "#cbd5e1"), ("active", "#1d4ed8")])
        self.table_rowheight = self.ui_font.metrics("linespace") + dp(12)
        style.configure("Treeview", font=self.ui_font, rowheight=self.table_rowheight, background="white", fieldbackground="white")
        style.configure("Treeview.Heading", font=self.heading_font, padding=(dp(8), dp(7)))
        self._build_checkbox_style(style)
        style.configure("Horizontal.TProgressbar", background="#2563eb", troughcolor="#e2e8f0", bordercolor="#e2e8f0", lightcolor="#2563eb", darkcolor="#2563eb")
        style.configure("TLabelframe", background="#f3f5f8")
        style.configure("TLabelframe.Label", background="#f3f5f8", font=self.heading_font)
        self.configure(bg="#f3f5f8")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self.header_frame = header = ttk.Frame(self, padding=(dp(24), dp(16), dp(24), dp(12)))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text=t('app.header'), style="Title.TLabel").grid(row=0, column=0, sticky="w")
        byline = ttk.Frame(header)
        byline.grid(row=1, column=0, sticky='w')
        ttk.Label(byline, text=t('app.byline'), style='Muted.TLabel').pack(side='left')
        self.version_button = ttk.Button(byline, text=f'v{APP_VERSION}', padding=(dp(6), 0),
                                         command=lambda: webbrowser.open(release_url(APP_VERSION)), cursor='hand2')
        self.version_button.pack(side='left', padx=(dp(10), 0))
        self.version_hint = ThemeHint(self.version_button, lambda: t('app.release_history') if '-rc' in APP_VERSION else t('app.release_notes_hint'))
        ttk.Label(header, textvariable=self.status_label, font=("Segoe UI", 12, "bold"), style='Status.TLabel').grid(row=0, column=1, sticky="e")
        header_actions = ttk.Frame(header)
        header_actions.grid(row=1,column=1,sticky='e')
        self.coffee_image = coffee_icon(self, dp(20))
        self.coffee_button = ttk.Button(header_actions, text=t('app.buy_coffee'), image=self.coffee_image or '', compound='left',
            style='Coffee.TButton', padding=(dp(5), dp(6), dp(12), dp(6)),
            command=lambda: webbrowser.open('https://ko-fi.com/bluenatto'), cursor='hand2', takefocus=True)
        self.coffee_button.pack(side='left', padx=(0, dp(8)))
        # Shown only while a session runs, to return to the compact tracker after expanding.
        self.compact_button = ttk.Button(header_actions, text=t('tracker.compact_action'), padding=(dp(10), dp(6)),
                                         command=self._enter_compact, cursor='hand2')
        ThemeHint(self.compact_button, lambda: t('tracker.compact_hint'))
        self.github_button = ttk.Button(header_actions, text=t('app.github'), padding=dp(6), cursor='hand2',
                                         command=lambda: webbrowser.open(PROFILE))
        self.github_button.pack(side='left', padx=(0, dp(6)))
        self.github_hint = ThemeHint(self.github_button, lambda: t('app.github_hint'))
        self.bug_image = bug_icon(self, dp(24))
        self.bug_button = ttk.Button(header_actions, image=self.bug_image or '',
                                     text='' if self.bug_image else t('app.bug'),
                                     padding=dp(6), cursor='hand2',
                                     command=lambda: webbrowser.open(bug_report_url(APP_VERSION, self.control_mode.get())))
        self.bug_button.pack(side='left', padx=(0, dp(6)))
        self.bug_hint = ThemeHint(self.bug_button, lambda: t('app.bug_report_hint'))
        self.about_image = avatar_icon(self, ASSET_DIR, dp(28))
        self.about_button = ttk.Button(header_actions, image=self.about_image, text='' if self.about_image else t('about.credits'), command=self._show_about, padding=dp(6), cursor='hand2', takefocus=True)
        self.about_button.pack(side='left',padx=(0,dp(6)))
        self.about_hint = ThemeHint(self.about_button, lambda: t('about.title'))
        self.theme_button = ttk.Button(header_actions, command=self._toggle_dark_mode, width=3, padding=dp(8), cursor='hand2', takefocus=True)
        self.theme_button.pack(side='left')
        self.theme_hint = ThemeHint(self.theme_button, lambda: t('theme.switch_light') if self.dark_mode.get() else t('theme.switch_dark'))
        self.body_frame = body = ttk.Frame(self, padding=(dp(24), 0, dp(24), dp(20)))
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)
        # The sidebar is one solid rounded card (Scenery draws its outline):
        # content inside it uses the plain panel colour, so scrolling has no
        # background slices to re-cut and cannot tear.
        self.sidebar_card = sidebar = ttk.Frame(body, padding=(dp(14), dp(12), dp(6), dp(14)))
        sidebar.grid(row=0, column=0, sticky="nsw", padx=(0, dp(20)))
        sidebar.rowconfigure(0, weight=1)
        self.settings_canvas = settings_canvas = tk.Canvas(sidebar, width=dp(370), bg="#f3f5f8", highlightthickness=0)
        settings_canvas.grid(row=0, column=0, sticky="ns")
        self.settings_scroll = settings_scroll = ttk.Scrollbar(sidebar, command=settings_canvas.yview)
        settings_canvas.configure(yscrollcommand=settings_scroll.set)
        action_dock = ttk.Frame(sidebar, padding=(0, dp(10), dp(10), 0))
        action_dock.grid(row=1, column=0, columnspan=2, sticky="ew")
        action_dock.columnconfigure((0, 1), weight=1, uniform="actions")
        self.settings_controls = controls = ttk.Frame(settings_canvas, padding=(0, 0, dp(10), 0))
        self.settings_controls_window = controls_window = settings_canvas.create_window((0, 0), window=controls, anchor="nw")
        controls.bind("<Configure>", self._update_settings_scroll)
        def resize_settings(event):
            settings_canvas.itemconfigure(controls_window, width=event.width)
            self._update_settings_scroll()
        # Tk applies a window item's forced width only when the canvas redraws
        # the area under it; after the controls grow, nothing did, so they kept
        # their natural, wider size and were clipped. Touching this invisible
        # item in _update_settings_scroll requests that redraw.
        self._settings_redraw = settings_canvas.create_rectangle(0, 0, 1, 1, width=0, fill='')
        settings_canvas.tag_lower(self._settings_redraw)
        settings_canvas.bind("<Configure>", resize_settings)
        controls.columnconfigure(0, weight=1)
        self.settings_widgets = []
        ttk.Label(controls, text=t('settings.session_heading'), style="Muted.TLabel").grid(row=0, column=0, sticky="w", pady=(0, dp(8)))
        self.target_label = ttk.Label(controls, text=t('connection.adb_target'))
        self.target_label.grid(row=1, column=0, sticky="w")
        device_row = ttk.Frame(controls)
        device_row.grid(row=2, column=0, sticky="ew", pady=(4, 0))
        device_row.columnconfigure(0, weight=1)
        self.device_box = ttk.Combobox(device_row, textvariable=self.device, width=19, font=self.ui_font)
        self.device_box.grid(row=0, column=0, sticky="ew")
        self.device_box.bind('<<ComboboxSelected>>', self._select_mouse_window)
        self.device_button = ttk.Button(device_row, text=t('connection.scan'), width=7, command=self.refresh_devices)
        self.device_button.grid(row=0, column=1, padx=(dp(12), 0))
        self.settings_widgets.extend([self.device_box, self.device_button])
        ttk.Label(controls, textvariable=self.device_notice, style="Muted.TLabel", wraplength=dp(350)).grid(row=3, column=0, sticky="w", pady=(dp(4), dp(10)))
        # Everyday settings stay visible: budget, stop key and what to buy.
        # Timing and calibration live under Advanced with a reset to the
        # recommended values, so a stray edit is easy to undo. Every change
        # saves itself shortly after the last edit (see _schedule_autosave).
        self.buy_icons = currency_icons(self, ASSET_DIR, dp(30))
        amounts = ttk.Frame(controls)
        amounts.grid(row=4, column=0, sticky='ew', pady=(0, dp(10)))
        for column in (0, 1):
            amounts.columnconfigure(column, weight=1, uniform='amounts')
        ttk.Label(amounts, text=t('budget.skystone_budget'), image=self.buy_icons.get('spent', ''), compound='left',
                  style='Section.TLabel').grid(row=0, column=0, sticky='w')
        self.budget_entry = entry = ttk.Entry(amounts, textvariable=self.budget, font=self.heading_font, width=7, justify='center',
                                              validate='key', validatecommand=(self.register(whole_number_up_to(MAX_BUDGET)), '%P'))
        entry.grid(row=1, column=0, sticky='ew', pady=(dp(4), 0))
        self.settings_widgets.append(entry)
        # The round coin fills its icon tile, so it gets a small gap of its own
        # before the text (the narrow Skystone gem has that space built in).
        gold_heading = ttk.Frame(amounts)
        gold_heading.grid(row=0, column=1, sticky='w', padx=(dp(10), 0))
        if self.buy_icons.get('gold'):
            ttk.Label(gold_heading, image=self.buy_icons['gold'], style='Section.TLabel').pack(side='left', padx=(0, dp(5)))
        ttk.Label(gold_heading, text=t('budget.gold_limit'), style='Section.TLabel').pack(side='left')
        self.gold_cap_entry = ttk.Entry(amounts, textvariable=self.gold_cap, font=self.heading_font, width=7, justify='center',
                                        validate='key', validatecommand=(self.register(whole_number_up_to(MAX_GOLD_CAP)), '%P'))
        self.gold_cap_entry.grid(row=1, column=1, sticky='ew', padx=(dp(10), 0), pady=(dp(4), 0))
        ThemeHint(self.gold_cap_entry, lambda: t('budget.gold_limit_hint'))
        # Grey "No limit" inside the empty box; the box itself stays empty.
        self.gold_placeholder = ttk.Label(self.gold_cap_entry, text=t('budget.gold_no_limit'),
                                          style='Placeholder.TLabel', cursor='xterm')
        self.gold_placeholder.bind('<Button-1>', lambda _event: self.gold_cap_entry.focus_set())
        ThemeHint(self.gold_placeholder, lambda: t('budget.gold_limit_hint'))
        self.gold_cap_entry.bind('<FocusIn>', self._update_gold_placeholder, add='+')
        self.gold_cap_entry.bind('<FocusOut>', self._update_gold_placeholder, add='+')
        self.gold_cap.trace_add('write', self._update_gold_placeholder)
        self._update_gold_placeholder()
        self.settings_widgets.extend([self.gold_cap_entry, self.gold_placeholder])
        self.budget_summary = tk.StringVar()
        ttk.Label(amounts, textvariable=self.budget_summary, style='Muted.TLabel', wraplength=dp(350)).grid(
            row=2, column=0, columnspan=2, sticky='w', pady=(dp(6), 0))
        buys = ttk.Frame(controls)
        buys.grid(row=5, column=0, sticky='ew', pady=(0, dp(10)))
        ttk.Label(buys, text=t('item.buy'), style='Section.TLabel').grid(row=0, column=0, columnspan=3, sticky='w', pady=(0, dp(4)))
        tiles = (('covenant_check', t('item.covenant'), t('item.covenant_gold_short'), 'covenant', self.buy_covenant,
                  t('item.covenant_gold_hint')),
                 ('mystic_check', t('item.mystic'), t('item.mystic_gold_short'), 'mystic', self.buy_mystic,
                  t('item.mystic_gold_hint')),
                 ('friendship_check', t('item.friendship'), t('item.friendship_gold_short'), 'friendship', self.buy_friendship,
                  t('item.friendship_gold_hint')))
        for column, (name, title, cost, icon, variable, hint) in enumerate(tiles):
            buys.columnconfigure(column, weight=1, uniform='tiles')
            tile = ttk.Checkbutton(buys, text=f'{title}\n{cost}', variable=variable, style='Tile.TCheckbutton',
                                   image=self.buy_icons.get(icon, ''), compound='top', cursor='hand2')
            tile.grid(row=1, column=column, sticky='nsew', padx=(0 if column == 0 else dp(6), 0))
            ThemeHint(tile, lambda hint=hint: hint)
            setattr(self, name, tile)
        self.settings_widgets.extend([self.covenant_check, self.mystic_check, self.friendship_check])
        stop_row = ttk.Frame(controls)
        stop_row.grid(row=6, column=0, sticky='ew', pady=(0, dp(4)))
        stop_row.columnconfigure(1, weight=1)
        self.stop_key_entry = ttk.Entry(stop_row, textvariable=self.stop_key, font=self.heading_font, width=4,
                                        justify='center', style='Keycap.TEntry', cursor='hand2')
        self.stop_key_entry.state(['readonly'])
        self.stop_key_entry.bind('<KeyPress>', self._capture_stop_key)
        self.stop_key_entry.grid(row=0, column=0, sticky='w')
        ttk.Label(stop_row, text=t('settings.stop_key_hint'), style='Muted.TLabel',
                  wraplength=dp(280)).grid(row=0, column=1, sticky='w', padx=(dp(10), 0))
        self.settings_widgets.append(self.stop_key_entry)
        self.details_button = ttk.Button(controls, text=t('settings.advanced_collapsed'), command=self._toggle_settings_details)
        self.details_button.grid(row=8, column=0, sticky='ew', pady=(dp(10), dp(12)))
        self.settings_details = advanced = ttk.Frame(controls)
        self.settings_details.grid(row=9, column=0, sticky='ew', pady=(dp(6), 0))
        self.settings_details.columnconfigure(0, weight=1)
        ttk.Label(advanced, text=t('settings.timing_recommendation'),
                  style='Muted.TLabel', wraplength=dp(350)).grid(row=0, column=0, sticky='w', pady=(0, dp(6)))
        delay_row = ttk.Frame(advanced)
        delay_row.grid(row=1, column=0, sticky='ew', pady=(0, dp(6)))
        ttk.Label(delay_row, text=t('settings.tap_delay')).grid(row=0, column=0, sticky='w')
        entry = ttk.Entry(delay_row, textvariable=self.tap_sleep, font=self.ui_font, width=10)
        entry.grid(row=1, column=0, sticky='w', pady=(dp(3), 0))
        self.settings_widgets.append(entry)
        self.delay_hint = ThemeHint(entry, lambda: t('settings.delay_range_hint',
            minimum=localized_number(MIN_TAP_DELAY, '.2f'),
            floor=localized_number(MIN_TAP_DELAY, '.2f')))
        self.random_check = ttk.Checkbutton(advanced, text=t('settings.randomize_taps'), variable=self.random_offset, style="Large.TCheckbutton")
        self.random_check.configure(command=self._update_tap_jitter)
        self.random_check.grid(row=2, column=0, sticky="w")
        timing = ttk.Frame(advanced)
        timing.grid(row=3, column=0, sticky='ew', pady=(0, dp(5)))
        timing.columnconfigure(0, weight=1)
        ttk.Label(timing, textvariable=self.tap_jitter_text).grid(row=0, column=0, sticky='w')
        self.tap_jitter_slider = ttk.Scale(timing, from_=0, to=0.1, variable=self.tap_jitter, command=self._update_tap_jitter,
                                          style='TapTiming.Horizontal.TScale')
        self.tap_jitter_slider.grid(row=1, column=0, sticky='ew', pady=(dp(2), 0))
        self.tap_jitter_slider.bind('<Left>', lambda _event: self._step_tap_jitter(-0.01))
        self.tap_jitter_slider.bind('<Right>', lambda _event: self._step_tap_jitter(0.01))
        self.settings_widgets.append(self.tap_jitter_slider)
        self.tap_timing_hint = ttk.Label(timing, text=t('settings.tap_variation_hint'), style="Muted.TLabel", wraplength=dp(350))
        self.tap_timing_hint.grid(row=2, column=0, sticky='w')
        self.debug_check = ttk.Checkbutton(advanced, text=t('settings.calibration'), variable=self.debug_mode, style="Large.TCheckbutton")
        self.debug_check.grid(row=4, column=0, sticky="w")
        ttk.Label(advanced, text=t('settings.calibration_hint'), style="Muted.TLabel", wraplength=dp(350)).grid(row=5, column=0, sticky="w", pady=(0, dp(6)))
        self.reset_timing_button = ttk.Button(advanced, text=t('settings.reset_timing'), command=self._reset_recommended_timing)
        self.reset_timing_button.grid(row=6, column=0, sticky='w', pady=(0, dp(8)))
        self.import_settings_button = ttk.Button(advanced, text=t('import_settings.open'),
                                                 command=self._import_older_settings)
        self.import_settings_button.grid(row=7, column=0, sticky='w', pady=(0, dp(8)))
        self.settings_widgets.extend([self.random_check, self.debug_check, self.reset_timing_button,
                                      self.import_settings_button])
        # Settings save themselves, so the dock holds only Start and Stop.
        action_dock.columnconfigure(0, weight=3, uniform='')
        action_dock.columnconfigure(1, weight=2, uniform='')
        self.start_button = ttk.Button(action_dock, text=t('session.start'), style="Start.Accent.TButton", command=self.start_refresh, cursor='hand2')
        self.start_button.grid(row=0, column=0, sticky="ew", padx=(0, dp(4)))
        self.stop_button = ttk.Button(action_dock, text=t('session.stop'), style='Stop.TButton', command=self.stop_refresh, state=tk.DISABLED)
        self.stop_button.grid(row=0, column=1, sticky="nsew", padx=(dp(4), 0))
        # Sound and tracker preferences: a 2 x 2 grid of toggle pills in the
        # same card style as Buy. Each pill is independent of the others.
        extras = ttk.Frame(action_dock)
        extras.grid(row=2, column=0, columnspan=2, sticky='ew', pady=(dp(10), 0))
        extras.columnconfigure((0, 1), weight=1, uniform='extras')
        pills = (('sound_button', t('settings.session_sound'), self.sound_enabled, self._save_sound_preference, 0, 0,
                  t('settings.session_sound_hint')),
                 ('tracker_button', t('tracker.preference'), self.compact_tracker, self._save_tracker_preference, 0, 1,
                  t('tracker.preference_hint')),
                 ('sound_covenant_check', t('settings.covenant_sound'), self.sound_covenant, self._save_sound_preference, 1, 0,
                  t('settings.covenant_sound_hint')),
                 ('sound_mystic_check', t('settings.mystic_sound'), self.sound_mystic, self._save_sound_preference, 1, 1,
                  t('settings.mystic_sound_hint')))
        for name, text, variable, command, row, column, hint in pills:
            pill = ttk.Checkbutton(extras, text=text, variable=variable, command=command,
                                   style='Tile.Pill.TCheckbutton', cursor='hand2')
            pill.grid(row=row, column=column, sticky='ew', padx=(0 if column == 0 else dp(6), 0),
                      pady=(0 if row == 0 else dp(6), 0))
            ThemeHint(pill, lambda hint=hint: hint)
            setattr(self, name, pill)
        ttk.Label(action_dock, textvariable=self.setting_notice, style="Muted.TLabel", wraplength=dp(350)).grid(row=5, column=0, columnspan=2, sticky="w", pady=(dp(4), 0))
        estimate = ttk.LabelFrame(self.settings_details, text=t('budget.estimate'), padding=dp(8))
        estimate.grid(row=7, column=0, sticky="ew")
        ttk.Label(estimate, textvariable=self.ev, wraplength=dp(320), justify=tk.LEFT).grid(sticky="w")
        ttk.Label(estimate, text=t('budget.estimate_hint'), style="Muted.TLabel", wraplength=dp(320)).grid(sticky="w", pady=(dp(8), 0))
        self.budget.trace_add("write", lambda *_: self._update_ev())
        for var in (self.buy_friendship, self.buy_covenant, self.buy_mystic):
            var.trace_add('write', lambda *_: self._update_ev())
        self.tap_sleep.trace_add('write', lambda *_: self._update_tap_jitter())
        self.random_offset.trace_add('write', lambda *_: self._update_tap_jitter())
        self.debug_mode.trace_add('write', lambda *_: self._update_tap_jitter())
        self._update_ev()
        self._update_tap_jitter()
        for var in (self.budget, self.gold_cap, self.stop_key, self.buy_covenant, self.buy_mystic, self.buy_friendship,
                    self.tap_sleep, self.random_offset, self.tap_jitter, self.control_mode):
            var.trace_add('write', lambda *_: self._schedule_autosave())
        # Insert one compact mode section; existing session fields retain their
        # order and use the existing scrolling layout on smaller screens.
        for widget in controls.winfo_children():
            row = int(widget.grid_info().get('row',0))
            if row >= 1: widget.grid_configure(row=row+1)
        mode_panel = ttk.Frame(controls)
        mode_panel.grid(row=1,column=0,sticky='ew',pady=(0,dp(10)))
        mode_panel.columnconfigure(0,weight=1)
        ttk.Label(mode_panel,text=t('mode.heading'),style='Section.TLabel').grid(row=0,column=0,sticky='w')
        # The cards show who each mode is for; control_mode keeps the plain name.
        self.mode_label = tk.StringVar(value=mode_label(self.control_mode.get()))
        self.control_mode.trace_add('write', lambda *_: self.mode_label.set(mode_label(self.control_mode.get())))
        # mode_box keeps the full labels (and the existing selection code) but
        # is not shown: one card per mode replaces the drop-down.
        self.mode_box = ttk.Combobox(mode_panel,textvariable=self.mode_label,
            values=[mode_label(mode) for mode in CONTROL_MODES],state='readonly',font=self.ui_font)
        self.mode_box.bind('<<ComboboxSelected>>',self._select_control_mode)
        cards = ttk.Frame(mode_panel)
        cards.grid(row=1,column=0,sticky='ew',pady=(dp(4),0))
        self.mode_cards = {}
        for column, mode in enumerate(CONTROL_MODES):
            cards.columnconfigure(column, weight=1, uniform='modes')
            note = MODE_CARD_NOTES.get(mode)
            card = ttk.Radiobutton(cards, text=f'{mode_title(mode)}\n{t(note) if note else ""}'.rstrip(),
                                   value=mode_label(mode),
                                   variable=self.mode_label, command=self._select_control_mode,
                                   style='Tile.TRadiobutton', cursor='hand2')
            card.grid(row=0, column=column, sticky='nsew', padx=(0 if column == 0 else dp(6), 0))
            ThemeHint(card, lambda mode=mode: mode_label(mode))
            self.mode_cards[mode] = card
        self.settings_widgets.extend([self.mode_box, *self.mode_cards.values()])
        language = ttk.Frame(advanced)
        language.grid(row=8, column=0, sticky='ew', pady=(dp(8), 0))
        ttk.Label(language, text=t('settings.language')).grid(row=0, column=0, sticky='w')
        self.language_box = ttk.Combobox(language, values=tuple(LANGUAGES.values()),
                                         state='readonly', width=18, font=self.ui_font)
        self._saved_language = current_locale()
        self.language_box.current(tuple(LANGUAGES).index(self._saved_language))
        self.language_box.grid(row=1, column=0, sticky='w', pady=(dp(3), 0))
        self.language_notice = tk.StringVar(value='')
        ttk.Label(language, textvariable=self.language_notice, style='Muted.TLabel',
                  wraplength=dp(325)).grid(row=2, column=0, sticky='w')
        self.language_box.bind('<<ComboboxSelected>>', self._save_language_choice)
        self.settings_widgets.append(self.language_box)
        self.settings_details.grid_remove()
        def bind_wheel(widget):
            def scroll_settings(event):
                settings_canvas.yview_scroll(-int(event.delta / 120), "units")
                if hasattr(self, 'scenery'):
                    self.scenery.schedule()
                return "break"
            widget.bind("<MouseWheel>", scroll_settings)
            for child in widget.winfo_children():
                bind_wheel(child)
        bind_wheel(controls)

        # The dashboard is a solid rounded card too, matching the sidebar.
        self._dashboard_pad = (dp(16), dp(12), dp(16), dp(14))
        self.right_panel = right = ttk.Frame(body, padding=self._dashboard_pad)
        right.grid(row=0, column=1, sticky="nsew")
        self.scenery_cards = (self.sidebar_card, right)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(4, weight=1, minsize=self.table_rowheight * 3 + dp(55))
        right.rowconfigure(6, weight=2, minsize=self.table_rowheight * 3 + dp(55))
        self.session_title = ttk.Label(right, text=t('session.heading'), font=("Segoe UI", 13, "bold"))
        self.session_title.grid(row=0, column=0, sticky="w")
        self.session_messages = ttk.Frame(right)
        self.session_messages.grid(row=1, column=0, sticky="ew", pady=(dp(4), dp(12)))
        self.session_messages.columnconfigure(0, weight=1)
        self.home_ui_banner = tk.Frame(self.session_messages, borderwidth=0, highlightthickness=dp(1))
        self.home_ui_banner.grid(row=0, column=0, sticky='ew', pady=(0,dp(6)))
        self.home_ui_banner.columnconfigure(0, weight=1)
        self.home_ui_notice = tk.Label(self.home_ui_banner, textvariable=self.home_ui_hint,
                                      font=self.heading_font, anchor='w', justify='left',
                                      wraplength=dp(620), padx=dp(10), pady=dp(6),
                                      borderwidth=0, highlightthickness=0)
        self.home_ui_notice.grid(row=0, column=0, sticky='ew')
        self.home_ui_action = ttk.Button(self.home_ui_banner, style='BannerAction.TButton', cursor='hand2',
                                         padding=(dp(10), dp(3)), command=self._take_mode_suggestion)
        # Its own line under the message, so the text keeps the banner's full width.
        self.home_ui_action.grid(row=1, column=0, sticky='w', padx=dp(10), pady=(0, dp(8)))
        self.home_ui_action.grid_remove()
        self.home_ui_dismiss = ttk.Button(self.home_ui_banner, text='×', style='Dismiss.TButton',
                                        width=2, padding=0,
                                        cursor='hand2', command=self._dismiss_home_ui_hint)
        self.home_ui_dismiss.grid(row=0, column=1, sticky='ne', padx=(0,dp(4)), pady=dp(4))
        ThemeHint(self.home_ui_dismiss, lambda: t('session.dismiss_reminder_hint'))
        self.status.trace_add('write', self._update_home_ui_hint)
        self.detail_label = ttk.Label(self.session_messages, textvariable=self.detail, style="Muted.TLabel", wraplength=dp(620))
        self.detail_label.grid(row=1, column=0, sticky="w")
        # After a run stops with a problem: one click copies everything a helper needs.
        self.report_actions = ttk.Frame(self.session_messages)
        self.report_actions.grid(row=2, column=0, sticky='w', pady=(dp(6), 0))
        self.copy_report_button = ttk.Button(self.report_actions, text=t('diagnostics.copy_report'), command=self._copy_report, cursor='hand2')
        self.copy_report_button.pack(side='left')
        ThemeHint(self.copy_report_button, lambda: t('diagnostics.copy_report_hint'))
        self.open_failure_button = ttk.Button(self.report_actions, text=t('diagnostics.open_pictures'), command=self._open_failure_folder, cursor='hand2')
        ThemeHint(self.open_failure_button, lambda: t('diagnostics.open_pictures_hint'))
        self.report_actions.grid_remove()
        self.status.trace_add('write', lambda *_: self._show_report_actions())
        self.metrics = metrics = ttk.Frame(right)
        metrics.bind("<Configure>", self._schedule_layout)
        metrics.grid(row=2, column=0, sticky="ew")
        self.metric_cards = []
        self.metric_captions = []
        self.currency_images = currency_icons(self, ASSET_DIR, dp(34))
        self.currency_labels = {}
        for i, (label, var, key) in enumerate(((t('session.elapsed'), self.elapsed, None), (t('session.skystone_spent'), self.spent_display, 'spent'), (t('session.covenant_buys'), self.covenant, 'covenant'), (t('session.mystic_buys'), self.mystic, 'mystic'),(t('session.friendship_buys'),self.friendship,'friendship'))):
            metrics.columnconfigure(i, weight=1, uniform="metrics")
            card = ttk.Frame(metrics, padding=dp(10))
            card.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 6, 0))
            column = 0
            if key in self.currency_images:
                icon = ttk.Label(card, image=self.currency_images[key])
                icon.grid(row=0, column=0, rowspan=2, sticky='w', padx=(0,dp(8)))
                self.currency_labels[key] = icon
                column = 1
            caption = ttk.Label(card, text=label, font=self.heading_font)
            caption.grid(row=0,column=column,sticky='w')
            self.metric_captions.append(caption)
            ttk.Label(card, textvariable=var, style="Value.TLabel").grid(row=1,column=column,sticky="w",pady=(dp(3),0))
            self.metric_cards.append(card)
        if 'friendship' in self.currency_labels:
            ThemeHint(self.currency_labels['friendship'],lambda:t('item.friendship_points_hint'))
        self.progress_frame = progress = ttk.Frame(right)
        progress.grid(row=3, column=0, sticky="ew", pady=(12, 12))
        progress.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(progress, maximum=100)
        self.progress.grid(row=0, column=0, sticky="ew")
        ttk.Label(progress, textvariable=self.progress_text, style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.remaining_label = ttk.Label(progress, textvariable=self.remaining_display, style='Muted.TLabel')
        self.remaining_label.grid(row=2, column=0, sticky='w', pady=(dp(3), 0))
        self.pointer_alert_label = ttk.Label(progress, textvariable=self.pointer_alert, style='Alert.TLabel',
                                             font=self.heading_font)
        self.pointer_alert_label.grid(row=3, column=0, sticky='w', pady=(dp(3), 0))
        self.pointer_alert_label.grid_remove()
        self.pointer_alert.trace_add('write', lambda *_: self.pointer_alert_label.grid()
                                     if self.pointer_alert.get() else self.pointer_alert_label.grid_remove())
        ThemeHint(self.remaining_label, lambda: t('session.remaining_hint'))
        self.notebook = notebook = ttk.Notebook(right)
        notebook.bind("<<NotebookTabChanged>>", self._schedule_layout)
        notebook.grid(row=4, column=0, sticky="nsew")
        activity_tab = ttk.Frame(notebook, padding=8)
        diagnostics_tab = ttk.Frame(notebook, padding=8)
        # Transparent label backing gives both buttons the same measured size.
        self.tab_spacer = tk.PhotoImage(master=self, width=self.ui_font.measure(t('diagnostics.title')), height=self.ui_font.metrics('linespace'))
        notebook.add(activity_tab, text=t('diagnostics.activity'), image=self.tab_spacer, compound='center')
        notebook.add(diagnostics_tab, text=t('diagnostics.title'), image=self.tab_spacer, compound='center')
        self.history_tab = ttk.Frame(notebook, padding=dp(8))
        self.history_tab.columnconfigure(0, weight=1)
        self.history_tab.rowconfigure(1, weight=1)
        self.compact_history = False
        activity_tab.columnconfigure(0, weight=1)
        activity_tab.rowconfigure(0, weight=1)
        self.activity = ttk.Treeview(activity_tab, columns=("time", "event"), show="headings", height=4, selectmode="none")
        self.activity.heading("time", text=t('diagnostics.time'))
        self.activity.heading("event", text=t('diagnostics.activity_heading'), anchor=tk.W)
        time_width = max(self.ui_font.measure("23:59:59"), self.heading_font.measure(t('diagnostics.time'))) + dp(24)
        self.activity.column("time", width=time_width, minwidth=time_width, stretch=False, anchor="center")
        self.activity.column("event", width=dp(480), minwidth=dp(240), anchor=tk.W)
        self.activity.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(activity_tab, command=self.activity.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.activity.configure(yscrollcommand=scroll.set)
        activity_xscroll = ttk.Scrollbar(activity_tab, orient=tk.HORIZONTAL, command=self.activity.xview)
        activity_xscroll.grid(row=1, column=0, sticky="ew")
        self.activity.configure(xscrollcommand=activity_xscroll.set)
        diagnostics_tab.columnconfigure(0, weight=1)
        diagnostics_tab.rowconfigure(1, weight=1)
        self.diagnostics_label = ttk.Label(diagnostics_tab,textvariable=self.diagnostics_summary,style="Muted.TLabel",wraplength=dp(600))
        self.diagnostics_label.grid(row=0, column=0, sticky="w", pady=(0, dp(6)))
        self.log = tk.Text(diagnostics_tab, wrap=tk.WORD, height=3, bg="#111827", fg="#e5e7eb", font=("Consolas", 11), relief=tk.FLAT, state=tk.DISABLED)
        self.log.grid(row=1, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(diagnostics_tab, command=self.log.yview)
        scroll.grid(row=1, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scroll.set)
        diagnostics_actions = ttk.Frame(diagnostics_tab)
        diagnostics_actions.grid(row=2, column=0, columnspan=2, sticky='ew', pady=(6, 0))
        diagnostics_actions.columnconfigure(0, weight=1)
        self.trace_check = ttk.Checkbutton(diagnostics_actions, text=t('diagnostics.log_clicks'),
                                          variable=self.trace_input, command=self._save_trace_preference,
                                          style='Large.TCheckbutton')
        self.trace_check.grid(row=0, column=0, columnspan=2, sticky='w')
        self.settings_widgets.append(self.trace_check)
        ThemeHint(self.trace_check, lambda: t('diagnostics.log_clicks_hint'))
        self.open_logs_button = ttk.Button(diagnostics_actions, text=t('diagnostics.open_logs'), command=self._open_logs_folder)
        self.open_logs_button.grid(row=1, column=0, sticky='w', pady=(dp(6), 0))
        ThemeHint(self.open_logs_button, lambda: t('diagnostics.open_logs_hint'))
        self.copy_diagnostics_button = ttk.Button(diagnostics_actions, text=t('diagnostics.copy'), command=self._copy_diagnostics)
        self.copy_diagnostics_button.grid(row=1, column=2, sticky="e", pady=(dp(6), 0))
        self.history_header = history_header = ttk.Frame(right)
        history_header.grid(row=5, column=0, sticky="ew", pady=(16, 6))
        history_header.columnconfigure(0, weight=1)
        ttk.Label(history_header, text=t('history.title'), font=("Segoe UI", 13, "bold")).grid(row=0, column=0, sticky="w")
        self.clear_history_button = ttk.Button(history_header, text=t('history.clear'), command=self._clear_history)
        self.clear_history_button.grid(row=0, column=2)
        self.export_history_button = ttk.Button(history_header, text=t('history.export_excel'), command=self._export_history)
        self.export_history_button.grid(row=0, column=1, padx=(dp(8), dp(8)))
        self.export_history_hint = ThemeHint(self.export_history_button, lambda: t('history.export_hint'))
        self.clear_history_hint = ThemeHint(self.clear_history_button, lambda: t('history.clear_hint'))
        self.history_frame = history_frame = ttk.Frame(right)
        history_frame.grid(row=6, column=0, sticky="nsew")
        history_frame.columnconfigure(0, weight=1)
        history_frame.rowconfigure(0, weight=1)
        self.history = ttk.Treeview(history_frame, columns=("mode", "duration", "skystone", "gold", "cov", "mys", "friend", "started", "control", "outcome"), show="headings", height=6)
        for key, label, sample in (
            ('mode', t('history.column_mode'), 'Unknown'),
            ('duration', t('history.column_duration'), '12h 59m 59s'),
            ('skystone', t('history.column_skystone'), '99,999'),
            ('gold', t('history.column_gold'), '999,999,999'),
            ('cov', t('history.column_covenant'), '9,999'),
            ('mys', t('history.column_mystic'), '9,999'),
            ('friend', t('history.column_friendship'), '9,999'),
        ):
            self.history.heading(key, text=label, anchor=tk.W if key in ("mode", "duration") else tk.E)
            column_width = max(self.heading_font.measure(label), self.ui_font.measure(sample)) + dp(24)
            self.history.column(key, width=column_width, minwidth=column_width, anchor=tk.W if key in ("mode", "duration") else tk.E, stretch=key != 'mode')
        for key, label, sample in (
            ('started', t('history.column_started'), '2026-10-05 14:30:00'),
            ('control', t('history.column_control'), 'Unknown'),
            ('outcome', t('history.column_outcome'), 'Unknown (legacy)'),
        ):
            width = max(self.heading_font.measure(label), self.ui_font.measure(sample)) + dp(24)
            self.history.heading(key, text=label, anchor=tk.W)
            self.history.column(key, width=width, minwidth=width, anchor=tk.W, stretch=False)
        self.history.bind('<<TreeviewSelect>>', self._history_selected)
        self.history.tag_configure("even", background="#f1f5f9")
        self.history.tag_configure('debug', background='#fff4d6', foreground='#92400e')
        self.history.grid(row=0, column=0, sticky="nsew")
        yscroll = ttk.Scrollbar(history_frame, orient=tk.VERTICAL, command=self.history.yview)
        yscroll.grid(row=0, column=1, sticky="ns")
        self.history_xscroll = ttk.Scrollbar(history_frame, orient=tk.HORIZONTAL, command=self.history.xview)
        self.history_xscroll.grid(row=1, column=0, sticky="ew")
        self.history.configure(yscrollcommand=yscroll.set, xscrollcommand=self._update_history_xscroll)
        self.history_label = ttk.Label(right, textvariable=self.history_notice, style="Muted.TLabel", wraplength=dp(650))
        self.history_label.grid(row=7, column=0, sticky="w", pady=(dp(6), 0))
        right.bind("<Configure>", self._schedule_layout)
        self._event(t('diagnostics.ready'))

    def _update_gold_placeholder(self, *_):
        label = getattr(self, 'gold_placeholder', None)
        if label is None:
            return
        try:
            focused = self.focus_get() is self.gold_cap_entry
        except (KeyError, tk.TclError):  # focus on a widget Tk cannot name, e.g. a menu
            focused = False
        if self.gold_cap.get() or focused:
            label.place_forget()
        else:
            label.place(relx=0.5, rely=0.5, anchor='center')

    def _save_language_choice(self, _event=None):
        languages = tuple(LANGUAGES)
        selection = self.language_box.current()
        if selection < 0:
            return
        locale = languages[selection]
        if locale != self._saved_language:
            try:
                if getattr(self, '_restart_required', False):
                    self.language_notice.set(t('import_settings.restart_needed'))
                    self.language_box.current(languages.index(self._saved_language))
                    return
                save_language(GUI_CONFIG_FILE, locale)
            except (OSError, UnicodeError, configparser.Error) as error:
                self.language_box.current(languages.index(self._saved_language))
                self.language_notice.set(t('settings.save_error', error=error))
                return
            self._saved_language = locale
        self.language_notice.set(t('settings.language_restart') if locale != current_locale() else '')

    def _load_config(self):
        # Loading is not an edit: keep autosave quiet while values arrive.
        self._autosave_suspended = True
        try:
            self._read_config()
        finally:
            self._autosave_suspended = False
            self._autosave_saved = self._autosave_snapshot()

    def _read_config(self):
        try:
            parser = configparser.ConfigParser()
            parser.read(CONFIG_FILE)
            if parser.has_section("Settings"):
                settings = parser["Settings"]
                for key, var in (("tap_sleep", self.tap_sleep), ("budget", self.budget), ("stop_refresh_key", self.stop_key)):
                    var.set(settings.get(key, var.get()))
                # Migrate whole-valued budgets written by older float-based releases.
                self._raise_tap_delay_floor()
                legacy_budget = float(self.budget.get())
                if math.isfinite(legacy_budget) and legacy_budget.is_integer():
                    self.budget.set(str(int(legacy_budget)))
                self.budget.set(clamp_saved_amount(self.budget.get(), MAX_BUDGET))
                self.random_offset.set(settings.get("random_offset", str(self.random_offset.get())).lower() == "true")
        except (OSError, ValueError, configparser.Error) as exc:
            self.setting_notice.set(t('settings.read_error', error=exc))
        try:
            parser = configparser.ConfigParser()
            parser.read(GUI_CONFIG_FILE)
            self.gold_cap.set(clamp_saved_amount(parser.get('GUI', 'gold_cap', raw=True, fallback=''), MAX_GOLD_CAP))
            self.sound_enabled.set(parser.getboolean("GUI", "sound_enabled", fallback=True))
            self.trace_input.set(parser.getboolean('GUI', 'trace_input', fallback=False))
            self.compact_tracker.set(parser.getboolean('GUI', 'compact_tracker', fallback=True))
            self.buy_friendship.set(parser.getboolean('GUI', 'buy_friendship', fallback=False))
            self.dark_mode.set(parser.getboolean("GUI", "dark_mode", fallback=False))
            self.credits_seen.set(parser.getboolean("GUI", "credits_seen", fallback=False))
            self.credits_on_startup.set(parser.getboolean("GUI", "show_credits_on_startup", fallback=False))
            self.adb_hint_dismissed.set(parser.getboolean("GUI", "adb_hint_dismissed", fallback=False))
            self.device.set(parser.get("GUI", "device", fallback=self.device.get()))
            mode = parser.get('GUI','control_mode',fallback=DEFAULT_CONTROL_MODE)
            self.control_mode.set(mode if mode in CONTROL_MODES else DEFAULT_CONTROL_MODE)
            try:
                legacy_jitter = min(float(self.tap_sleep.get()) * .1, .05)
            except ValueError:
                # A malformed tap delay must not skip the item toggles or the
                # one-time timing reset below, which replaces it.
                legacy_jitter = RECOMMENDED_TAP_JITTER
            jitter = parser.getfloat('GUI', 'tap_jitter', fallback=legacy_jitter)
            self.tap_jitter.set(jitter if math.isfinite(jitter) and 0 <= jitter <= .1 else .03)
            self.buy_covenant.set(parser.getboolean('GUI', 'buy_covenant', fallback=True))
            self.buy_mystic.set(parser.getboolean('GUI', 'buy_mystic', fallback=True))
            self.sound_covenant.set(parser.getboolean('GUI', 'sound_covenant', fallback=True))
            self.sound_mystic.set(parser.getboolean('GUI', 'sound_mystic', fallback=True))
            # Before 0.2.7 "Sounds" off also silenced the callouts. Now they are
            # separate pills; keep an older all-quiet choice quiet, once.
            if not parser.getboolean('GUI', 'sound_callouts_separate', fallback=False) and not self.sound_enabled.get():
                self.sound_covenant.set(False); self.sound_mystic.set(False)
            settings_version = parser.getint('GUI', 'settings_version', fallback=0)
        except (OSError, ValueError, configparser.Error) as exc:
            self.setting_notice.set(t('settings.sound_read_error', error=exc))
            return
        self._loaded_settings_version = settings_version
        if settings_version < SETTINGS_VERSION:
            self._migrate_recommended_timing()

    def _migrate_recommended_timing(self):
        """0.2.6 moved timing under Advanced: reset older custom timing once."""
        # Until ADBconfig.ini holds the reset timing, no preference save may
        # record the new settings_version, or a failed write would skip the
        # reset for good.
        self._timing_migration_pending = True
        changed = self._reset_recommended_timing(save=False)
        try:
            self._write_engine_timing()
            self._write_sound_preference()  # records SETTINGS_VERSION so this runs once
        except (OSError, UnicodeError, configparser.Error) as exc:
            # Runs before the log exists; the notice line is the only output.
            self.setting_notice.set(t('settings.timing_save_error', error=exc))
            return
        if changed:
            self.setting_notice.set(t('settings.timing_migrated'))

    def _reset_recommended_timing(self, save=True):
        """Recommended tap delay, offsets and jitter; returns whether anything changed."""
        try:
            tap = float(self.tap_sleep.get())  # "0.30" is the same delay as "0.3"
        except ValueError:
            tap = None
        before = (tap, self.random_offset.get(), round(self.tap_jitter.get(), 2), self.debug_mode.get())
        self.tap_sleep.set(RECOMMENDED_TAP_DELAY)
        self.random_offset.set(True)
        self.tap_jitter.set(RECOMMENDED_TAP_JITTER)
        self.debug_mode.set(False)
        self._update_tap_jitter()
        changed = before != (float(RECOMMENDED_TAP_DELAY), True, RECOMMENDED_TAP_JITTER, False)
        if save:
            try:
                self._write_engine_timing()
                self._write_sound_preference()
                self.setting_notice.set(t('settings.timing_reset'))
            except (OSError, UnicodeError, configparser.Error) as exc:
                self.setting_notice.set(t('settings.timing_reset_unsaved'))
                self._append_log(f'Recommended timing could not be saved: {exc}\n')
        return changed

    def _write_engine_timing(self):
        """Store only the timing keys in ADBconfig.ini, leaving budget and stop key alone."""
        if getattr(self, '_restart_required', False):
            return  # imported files wait for the restart
        parser = configparser.ConfigParser()
        try:
            # read_file, not read: read() swallows open errors, and an empty
            # parser written back would erase budget, stop key and the rest.
            with CONFIG_FILE.open(encoding='utf-8-sig') as fh:
                parser.read_file(fh)
        except FileNotFoundError:
            # Nothing saved yet, so no older timing to reset; the next
            # Save or Start writes the full file.
            self._timing_migration_pending = False
            return
        if not parser.has_section('Settings'):
            parser.add_section('Settings')
        parser['Settings'].update({'tap_sleep': self.tap_sleep.get(), 'random_offset': str(self.random_offset.get())})
        temp = CONFIG_FILE.with_suffix('.ini.tmp')
        with temp.open('w', encoding='utf-8') as fh:
            parser.write(fh)
        temp.replace(CONFIG_FILE)
        self._timing_migration_pending = False

    def _write_sound_preference(self, settings=None):
        if getattr(self, '_restart_required', False):
            return  # imported files wait for the restart
        # The original engine rewrites ADBconfig.ini, so GUI preferences need
        # their own file to survive a real refresh session.
        parser = _read_gui_preferences(GUI_CONFIG_FILE)
        if not parser.has_section("GUI"):
            parser.add_section("GUI")
        parser["GUI"]["sound_enabled"] = str(self.sound_enabled.get())
        if settings is not None:
            parser['GUI']['gold_cap'] = '' if settings.gold_cap is None else str(settings.gold_cap)
        parser['GUI']['trace_input'] = str(self.trace_input.get())
        parser['GUI']['compact_tracker'] = str(self.compact_tracker.get())
        parser['GUI']['buy_friendship'] = str(self.buy_friendship.get())
        parser['GUI']['buy_covenant'] = str(self.buy_covenant.get())
        parser['GUI']['buy_mystic'] = str(self.buy_mystic.get())
        parser['GUI']['sound_covenant'] = str(self.sound_covenant.get())
        parser['GUI']['sound_mystic'] = str(self.sound_mystic.get())
        parser['GUI']['sound_callouts_separate'] = 'True'
        pending = getattr(self, '_timing_migration_pending', False)
        parser['GUI']['settings_version'] = str(getattr(self, '_loaded_settings_version', 0) if pending else SETTINGS_VERSION)
        parser["GUI"]["dark_mode"] = str(self.dark_mode.get())
        parser["GUI"]["credits_seen"] = str(self.credits_seen.get())
        parser["GUI"]["show_credits_on_startup"] = str(self.credits_on_startup.get())
        parser["GUI"]["adb_hint_dismissed"] = str(self.adb_hint_dismissed.get())
        parser["GUI"]["device"] = self._device_address()
        parser['GUI']['control_mode'] = self.control_mode.get()
        parser['GUI']['tap_jitter'] = str(round(self.tap_jitter.get(), 2))
        _write_gui_preferences(GUI_CONFIG_FILE, parser)

    def _save_sound_preference(self):
        try:
            self._write_sound_preference()
            self.setting_notice.set(t('settings.sound_saved'))
        except (OSError, UnicodeError, configparser.Error) as exc:
            self.setting_notice.set(t('settings.sound_unsaved'))
            self._append_log(f"Sound preference save failed: {exc}\n")

    def _enter_compact(self):
        if self.run_settings is not None and self._session_started and not self._native_mouse_run:
            self.tracker.enter(friendship=self.run_settings.buy_friendship)

    def _update_compact_button(self):
        running = (self._session_started and self.run_settings is not None and not self.run_settings.debug
                   and not self._native_mouse_run and self.status.get() in ('Running', 'Paused', 'Waiting for game'))
        if running and not self.compact_button.winfo_manager():
            self.compact_button.pack(side='left', padx=(0, self._dp(8)), before=self.coffee_button)
        elif not running and self.compact_button.winfo_manager():
            self.compact_button.pack_forget()

    def _save_tracker_preference(self):
        try:
            self._write_sound_preference()
            self.setting_notice.set(t('tracker.enabled') if self.compact_tracker.get() else t('tracker.disabled'))
        except (OSError, UnicodeError, configparser.Error) as exc:
            self.setting_notice.set(t('tracker.unsaved'))
            self._append_log(f"Tracker preference save failed: {exc}\n")

    def _save_trace_preference(self):
        try:
            self._write_sound_preference()
            self._append_log('Detailed input logging '+('enabled' if self.trace_input.get() else 'disabled')+' for the next session.\n')
        except (OSError, UnicodeError, configparser.Error) as exc:
            self._append_log(f'Logging preference could not be saved: {exc}\n')

    def _capture_stop_key(self, event):
        if self.stop_key_entry.instate(["disabled"]):
            return "break"
        if event.keysym in ("Tab", "ISO_Left_Tab"):
            return None  # Preserve keyboard navigation.
        if event.keysym in ("Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R", "Caps_Lock", "Super_L", "Super_R", "Win_L", "Win_R"):
            return "break"
        key = captured_stop_key(event.keysym, event.char, event.state)
        if key is None:
            self.setting_notice.set(t('settings.stop_key_choices'))
        else:
            self.stop_key.set(key)
            self.setting_notice.set(t('settings.stop_key_selected', key='Esc' if key == 'esc' else key))
        return "break"

    def _settings(self):
        if self.control_mode.get() == 'ADB' and not self.device.get().strip():
            raise ValueError(t('connection.choose_emulator'))
        device = self._device_address() or ('native-mouse' if self.control_mode.get() != 'ADB' else '')
        self._raise_tap_delay_floor()
        return validate_settings(device, self.budget.get(), self.tap_sleep.get(), self.stop_key.get(), self.random_offset.get(), self.debug_mode.get(), round(self.tap_jitter.get(), 2), self.trace_input.get(), self.buy_friendship.get(),
                                 self.buy_covenant.get(), self.buy_mystic.get(), gold_cap=self.gold_cap.get())

    def _raise_tap_delay_floor(self):
        """Show the raised value in the box; validation applies the same floor."""
        try:
            delay = float(self.tap_sleep.get())
        except (TypeError, ValueError):
            return
        if math.isfinite(delay) and 0 < delay < MIN_TAP_DELAY:
            self.tap_sleep.set(f'{MIN_TAP_DELAY:g}')

    def _device_address(self):
        value = self.device.get().strip()
        return self.device_labels.get(value, value)

    def _apply_devices(self, devices, note, raw, endpoints=()):
        previous = self._device_address()
        self.connected_devices = list(dict.fromkeys(devices))
        self.discovered_endpoints = tuple(endpoints)
        named = {}
        for endpoint in endpoints:
            serial = next((address for address in self.connected_devices if endpoint_key(address) == endpoint_key(endpoint.address)), endpoint.address)
            named[f'{endpoint.name} · {serial.rsplit(":", 1)[-1]}'] = serial
        named_keys = {endpoint_key(address) for address in named.values()}
        other = [address for address in self.connected_devices if endpoint_key(address) not in named_keys]
        total = len(named) + len(other)
        self.device_labels = {**named, **{f'{address} (default)' if total == 1 else address: address for address in other}}
        labels = list(self.device_labels)
        self.device_box.configure(values=labels)
        running = self._checking_connection or (self.process is not None and self.process.poll() is None)
        if labels:
            preferred = getattr(self, '_adb_preferred_window', None)
            match = next((label for label, address in self.device_labels.items() if endpoint_key(address) == endpoint_key(previous)), None)
            preferred_matches = [label for label, address in named.items() if any(endpoint.name == preferred and endpoint_key(endpoint.address) == endpoint_key(address) for endpoint in endpoints)]
            if not running and len(preferred_matches) == 1:
                self.device.set(preferred_matches[0])
                self._adb_preferred_window = None
                note = t('connection.same_bluestacks')
            elif len(labels) == 1:
                if not running:
                    self.device.set(labels[0])
                note = (t('connection.bluestacks_connect_hint') if named and not self.connected_devices else
                        t('connection.only_emulator_hint'))
            elif match is not None:
                if not running:
                    self.device.set(match)
                note = t('connection.previous_emulator')
            else:
                if not running:
                    self.device.set("")
                note = t('connection.choose_from_list')
        if self._device_address():
            state = t('connection.connected') if self._device_address() in self.connected_devices else t('connection.connect_on_start')
            note += t('connection.selected_detail', address=self._device_address(), state=state)
        self.device_notice.set(note)
        if not running:
            self.device_button.configure(state=tk.NORMAL)
            self.start_button.configure(state=tk.NORMAL)
        if not self.process:
            self._append_log(raw + "\n")

    def save_settings(self, settings=None):
        if getattr(self, '_restart_required', False):
            return None  # imported files wait for the restart; nothing is written over them
        try:
            settings = settings or self._settings()
            parser = configparser.ConfigParser()
            parser.read(CONFIG_FILE)
            if not parser.has_section("Settings"):
                parser.add_section("Settings")
            parser["Settings"].update({"tap_sleep": str(settings.tap_sleep), "budget": str(settings.budget), "stop_refresh_key": settings.stop_key, "random_offset": str(settings.random_offset)})
            temp = CONFIG_FILE.with_suffix(".ini.tmp")
            with temp.open("w", encoding="utf-8") as fh:
                parser.write(fh)
            temp.replace(CONFIG_FILE)
            self._timing_migration_pending = False  # the full file now holds the current timing
            self._write_sound_preference(settings)
        except (ValueError, OSError, configparser.Error) as exc:
            messagebox.showerror(t('settings.save_error_title'), str(exc), parent=self)
            return None
        if hasattr(self, '_autosave_saved'):
            self._autosave_saved = self._autosave_snapshot()  # autosave compares against this
        self.setting_notice.set(t('settings.saved'))
        return settings

    def refresh_devices(self):
        if self.control_mode.get() != 'ADB':
            self._scan_game_windows()
            return
        if self._device_scan_busy or self._checking_connection or (self.process and self.process.poll() is None):
            return
        if self.setup_window is not None and self.setup_window.winfo_exists():
            return
        self._device_scan_busy = True
        token = self._connection_check_id
        background = self._background_scan
        self.device_button.configure(state=tk.DISABLED)
        self.device_notice.set(t('connection.checking_devices'))
        def scan():
            result = check_connection(ADB_EXE, APP_DIR)
            self.log_queue.put((None, 'devices', (token, result, background)))
        threading.Thread(target=scan, daemon=True).start()

    def _rescan_idle_devices(self):
        self._background_scan = True
        try:
            self.refresh_devices()
        finally:
            self._background_scan = False
        self.after(10000, self._rescan_idle_devices)

    def _select_control_mode(self, _event=None):
        chosen = next((mode for mode in CONTROL_MODES if mode_label(mode) == self.mode_label.get()), None)
        if chosen is None or (self._checking_connection or (self.process and self.process.poll() is None)):
            self.mode_label.set(mode_label(self.control_mode.get()))
            return
        self.control_mode.set(chosen)
        self._change_control_mode()

    def _change_control_mode(self, _event=None):
        if self._checking_connection or (self.process and self.process.poll() is None):
            return
        self._connection_check_id += 1
        self._device_scan_busy = self._mouse_scan_busy = False
        mouse = self.control_mode.get() != 'ADB'
        if not mouse:
            previous_game = self.mouse_windows.get(self.mouse_target.get())
            self._adb_preferred_window = previous_game.title if previous_game is not None else None
        self._update_debug_availability()
        self.device_box.configure(textvariable=self.mouse_target if mouse else self.device,
                                  values=list(self.mouse_windows) if mouse else list(self.device_labels),
                                  state='readonly' if mouse else 'normal')
        self.target_label.configure(text=t('connection.game_target') if mouse else t('connection.adb_target'))
        self.start_button.configure(text=t('session.start'), state=tk.NORMAL)
        self.mode_suggestion = None
        self._set_connection_warning('')
        self.home_ui_hint_dismissed = False
        self.home_ui_banner.grid()
        self.status.set('Ready')
        self.detail.set(t('mode.start_background_hint')
                        if self.control_mode.get() == 'Background' else
                        t('mode.start_mouse_hint') if mouse else
                        t('session.open_shop'))
        if mouse:
            self._update_mouse_selection()
        self.refresh_devices()

    def _select_mouse_window(self, _event=None):
        if self.control_mode.get() == 'ADB':
            self._adb_preferred_window = None
            address = self._device_address()
            state = t('connection.connected') if address in self.connected_devices else t('connection.connect_on_start')
            self.device_notice.set(t('connection.selected', address=address, state=state))
            self._set_connection_warning('')
            return
        if self.mouse_windows.get(self.mouse_target.get()) is not None:
            self._set_connection_warning('')
        self._update_mouse_selection()

    def _update_mouse_selection(self):
        target = self.mouse_windows.get(self.mouse_target.get())
        if target is not None:
            left, top, right, bottom = target.rectangle
            next_step = (t('mode.background_shop_hint') if self.control_mode.get() == 'Background' else
                         t('mode.mouse_shop_hint'))
            self.device_notice.set(t('connection.selected_window', title=target.title,
                                     width=right-left, height=bottom-top) + next_step)
        elif self.mouse_windows:
            self.device_notice.set(t('connection.choose_game_window'))
        else:
            self.device_notice.set(t('connection.open_game_window'))
        self.start_button.configure(state=tk.NORMAL if target is not None else tk.DISABLED)

    def _take_mode_suggestion(self):
        mode = self.mode_suggestion
        if mode not in CONTROL_MODES or self._checking_connection or (self.process and self.process.poll() is None):
            return
        self.control_mode.set(mode)
        self._change_control_mode()
        try:
            self._write_sound_preference()
        except (OSError, UnicodeError, configparser.Error) as exc:
            self._append_log(f'Control mode preference save failed: {exc}\n')

    def _apply_mouse_windows(self, windows, error, suggestion=None, *, notice_key=None):
        selected = self.mouse_windows.get(self.mouse_target.get())
        titles = [window.title for window in windows]
        choices = {}
        for window in windows:
            label = window.title if titles.count(window.title) == 1 else window.label
            # Keep distinct handles distinct even if a title resembles an ID label.
            while label in choices:
                label += ' ·'
            choices[label] = window
        self.mouse_windows = choices
        selection = next((label for label, window in choices.items()
                          if selected is not None and (window.handle, window.pid, window.title) ==
                          (selected.handle, selected.pid, selected.title)), '')
        if not selection and len(choices) == 1:
            selection = next(iter(choices))
        self.mouse_target.set(selection)
        self.device_box.configure(values=list(choices))
        self.device_button.configure(state=tk.NORMAL)
        notice = t(notice_key) if notice_key else error
        warning = notice or (t('connection.no_game_window') if not windows else '')
        previous = self.mode_suggestion
        self.mode_suggestion = (suggestion if suggestion in CONTROL_MODES and suggestion != self.control_mode.get()
                                else None)
        if self.mode_suggestion == 'Mouse':
            warning = (t('mode.unsupported_background_client') if 'supports Epic Seven on Steam' in error else
                       t('mode.background_client_not_running'))
        if self.mode_suggestion and self.mode_suggestion != previous:
            self.home_ui_hint_dismissed = False
            self.home_ui_banner.grid()
        self._set_connection_warning(warning)
        self._update_mouse_selection()
        if notice:
            self.device_notice.set(notice)

    def _scan_game_windows(self):
        if self._mouse_scan_busy or (self.process and self.process.poll() is None):
            return
        self._mouse_scan_busy = True
        token = self._connection_check_id
        self.device_button.configure(state=tk.DISABLED)
        if not self._background_scan:
            self.device_notice.set(t('connection.scanning_windows'))
        background = self.control_mode.get() == 'Background'  # read Tk state on this thread only
        def scan():
            notice_key = None
            try:
                windows, error = (list_background_games() if background
                                  else WindowsCapture().list_windows()), ''
            except Exception as exc:  # e.g. Xlib BadWindow when the game closes mid-scan
                windows, error = [], str(exc) or type(exc).__name__
                if (background and os.name == 'nt' and isinstance(exc, ValueError)
                        and error == 'Epic Seven (Steam or STOVE) is not running. Start the game, then try again.'):
                    notice_key = 'connection.windows_game_not_running'
            suggestion = suggested_mode(background, windows, error)
            self.log_queue.put((None,'windows',(token,windows,error,suggestion,notice_key)))
        threading.Thread(target=scan,daemon=True).start()

    def _start_connection_check(self, settings):
        self._connection_check_id += 1
        token = self._connection_check_id
        self._checking_connection = True
        self._set_controls(True)
        self.status.set('Checking connection')
        self.detail.set(t('connection.checking_before_start'))
        def check():
            result = check_connection(ADB_EXE, APP_DIR, settings.device)
            structured = False
            if result.ready:
                try:
                    verify = subprocess.run([*engine_command(), '--verify'], stdin=subprocess.DEVNULL, cwd=APP_DIR, capture_output=True,
                                            text=True, timeout=15, creationflags=NO_WINDOW)
                    structured = verify.returncode == 0 and 'gui session v1' in verify.stdout
                except (OSError, subprocess.SubprocessError):
                    pass  # Older engines retain the existing prompt adapter.
            self.log_queue.put((None, 'connection', (token, settings, result, structured)))
        threading.Thread(target=check, daemon=True).start()

    def _complete_connection_check(self, token, settings, result, structured=False):
        if token != self._connection_check_id or not self._checking_connection:
            return
        self._checking_connection = False
        self._structured_adb = structured
        self._set_controls(False)
        self._apply_devices(result.devices, result.warning, result.diagnostics, result.endpoints)
        self._set_connection_warning(result.warning, reveal=True)
        if not result.ready:
            self.status.set('Not ready' if settings.device in result.devices else 'Not connected')
            self.detail.set(result.warning)
            self._event(t('connection.not_ready_event'))
            return
        if self.setup_window is not None and self.setup_window.winfo_exists():
            self.setup_window.lift()
            return
        if missing_references(ENGINE_EXE.parent) and not has_builtin_references(ENGINE_EXE.parent):
            self._show_recognition_setup()
            return
        self._begin_refresh(settings)

    def _show_recognition_setup(self):
        if self.process and self.process.poll() is None:
            return
        if self.setup_window is not None and self.setup_window.winfo_exists():
            self.setup_window.lift()
            return
        try:
            settings = self._settings()
            self.setup_window = RecognitionSetup(self, ENGINE_EXE.parent, ADB_EXE, ENGINE_EXE, settings.device)
        except (ValueError, OSError) as error:
            messagebox.showerror(t('setup.unavailable'), str(error), parent=self)
            return
        self.status.set('Setup required')
        self.detail.set(t('setup.start_hint'))
        self._event(t('setup.offered'))

    def _offer_recognition_setup(self, run_id):
        if run_id != self.run_id or not self._recognition_setup_needed or self.stopping or self.stop_key_pressed:
            return
        if self.process and self.process.poll() is None:
            return
        self._recognition_setup_needed = False
        self._show_recognition_setup()

    def start_refresh(self):
        if self._restart_pending():
            return
        if self.control_mode.get() == 'Mouse':
            self._start_mouse_refresh()
            return
        if self.control_mode.get() == 'Background':
            self._start_background_refresh()
            return
        if self._checking_connection or (self.process and self.process.poll() is None):
            return
        if not ENGINE_EXE.is_file():
            messagebox.showerror(t('startup.engine_missing_title'), t('startup.engine_missing', engine=ENGINE_EXE), parent=self)
            return
        if self.setup_window is not None and self.setup_window.winfo_exists():
            self.setup_window.lift()
            return
        try:
            settings = self._settings()
        except ValueError as error:
            messagebox.showerror(t('settings.check_title'), str(error), parent=self)
            return
        self._start_connection_check(settings)

    def _start_mouse_refresh(self):
        if self._checking_connection or (self.process and self.process.poll() is None):
            return
        if self.setup_window is not None and self.setup_window.winfo_exists():
            self.setup_window.lift()
            return
        target = self.mouse_windows.get(self.mouse_target.get())
        try:
            settings = self._settings()
            if settings.debug:
                raise ValueError(t('mode.mouse_calibration_unavailable'))
            if target is None:
                raise ValueError(t('connection.select_window_first'))
            verify_setup_engine(ENGINE_EXE)
            check = subprocess.run([*engine_command(), '--verify'], stdin=subprocess.DEVNULL,cwd=APP_DIR,capture_output=True,text=True,
                                   timeout=15,creationflags=NO_WINDOW)
            if check.returncode or 'window mouse v9' not in check.stdout or 'tap timing v2' not in check.stdout or 'global stop key v2' not in check.stdout:
                raise ValueError(t('mode.mouse_engine_required'))
            if settings.buy_friendship and 'friendship purchases v1' not in check.stdout:
                raise ValueError(t('item.friendship_engine_required'))
            target = activate_native_target(target)
        except MouseElevationRequired as error:
            self._set_connection_warning(str(error), reveal=True)
            self._offer_administrator_restart(settings, reason=str(error))
            return
        except (ValueError,OSError,RuntimeError,subprocess.SubprocessError) as error:
            self._set_connection_warning(str(error),reveal=True)
            return
        self._set_connection_warning('')
        self._begin_refresh(settings,mouse_target=target)

    def _start_background_refresh(self):
        if self._checking_connection or (self.process and self.process.poll() is None):
            return
        target = self.mouse_windows.get(self.mouse_target.get())
        try:
            settings = self._settings()
            if settings.debug:
                raise ValueError(t('mode.background_calibration_unavailable'))
            if target is None:
                raise ValueError(t('mode.start_game_first'))
            if not ENGINE_EXE.is_file():
                raise ValueError(t('startup.engine_missing_at_path', engine=ENGINE_EXE))
            from e7_background import HELPER_NAME, require_background_permissions
            helper = Path(os.environ.get('E7_WINE_INPUT') or APP_DIR/HELPER_NAME)
            if not helper.is_file():
                raise ValueError(t('mode.background_helper_missing', helper=helper)
                                 + (t('mode.player_folder_hint') if os.name == 'nt' else t('mode.build_background_helper')))
            if os.name == 'nt':
                check = subprocess.run([*engine_command(), '--verify'], stdin=subprocess.DEVNULL, cwd=APP_DIR,
                                       capture_output=True, text=True, timeout=15, creationflags=NO_WINDOW)
                if check.returncode or 'background session v1' not in check.stdout:
                    raise ValueError(t('mode.background_engine_required'))
                require_background_permissions(target.pid)
        except MouseElevationRequired as error:
            self._set_connection_warning(str(error), reveal=True)
            self._offer_administrator_restart(settings, reason=str(error))
            return
        except (ValueError, OSError, subprocess.SubprocessError) as error:
            self._set_connection_warning(str(error), reveal=True)
            return
        self._set_connection_warning('')
        self._begin_refresh(settings, mouse_target=target)

    def _offer_administrator_restart(self, settings, *, reason=None):
        if not messagebox.askyesno(
                t('startup.elevation_title'),
                (reason or t('startup.elevation_reason')) + '\n\n' +
                t('startup.elevation_confirm'),
                parent=self):
            return
        if self.save_settings(settings) is None:
            return
        try:
            restart_as_administrator(APP_DIR, parent=self.winfo_id())
        except ElevationCancelled as error:
            self._set_connection_warning(str(error) + t('startup.elevation_retry'), reveal=True)
            return
        except OSError as error:
            self._set_connection_warning(
                t('startup.elevation_failed', error=error),
                reveal=True)
            return
        self._close()

    def _begin_refresh(self, settings, *, mouse_target=None):
        if DATA_DIR is not None and DATA_DIR != APP_DIR:
            # Older engines write history beside themselves, where this GUI no longer reads it.
            try:
                check = subprocess.run([*engine_command(), '--verify'], stdin=subprocess.DEVNULL, cwd=APP_DIR, capture_output=True,
                                       text=True, timeout=15, creationflags=NO_WINDOW)
                if check.returncode or 'user data folder v1' not in check.stdout:
                    raise ValueError(t('startup.engine_user_data_required', runtime=APP_DIR, data=DATA_DIR))
            except (ValueError, OSError, subprocess.SubprocessError) as error:
                self._set_connection_warning(str(error), reveal=True)
                return
        if not (settings.buy_covenant and settings.buy_mystic):
            try:
                check = subprocess.run([*engine_command(), '--verify'], stdin=subprocess.DEVNULL, cwd=APP_DIR, capture_output=True,
                                       text=True, timeout=15, creationflags=NO_WINDOW)
                if check.returncode or 'item choice v1' not in check.stdout:
                    raise ValueError(t('item.choice_engine_required'))
                if mouse_target is None and not self._structured_adb:
                    raise ValueError(t('item.choice_protocol_required'))
            except (ValueError, OSError, subprocess.SubprocessError) as error:
                self._set_connection_warning(str(error), reveal=True)
                return
        if settings.buy_friendship or settings.gold_cap is not None:
            try:
                check = subprocess.run([*engine_command(), '--verify'], stdin=subprocess.DEVNULL, cwd=APP_DIR, capture_output=True,
                                       text=True, timeout=15, creationflags=NO_WINDOW)
                if settings.gold_cap is not None:
                    if check.returncode or not re.search(r'\bgold limit v1\b', check.stdout):
                        raise ValueError(t('budget.gold_limit_engine_required'))
                    if mouse_target is None and not self._structured_adb:
                        raise ValueError(t('budget.gold_limit_protocol_required'))
                if settings.buy_friendship:
                    if check.returncode or 'friendship purchases v1' not in check.stdout:
                        raise ValueError(t('item.friendship_engine_required'))
                    if mouse_target is None and not self._structured_adb:
                        raise ValueError(t('item.friendship_protocol_required'))
            except (ValueError, OSError, subprocess.SubprocessError) as error:
                self._set_connection_warning(str(error), reveal=True)
                return
        if settings.debug:
            message = t('setup.calibration_confirm')
            if not messagebox.askyesno(t('setup.calibration_title'), message, parent=self):
                return
        settings = self.save_settings(settings)
        if settings is None:
            return
        if settings.debug:
            # Calibration overrides only these; the chosen items stay as set.
            settings = replace(settings, budget=100, stop_key="esc", random_offset=True, debug=True)
        self.run_settings = settings
        self.session_estimate.reset(settings.budget, enabled=not settings.debug)
        self.remaining_time.set('Time remaining: Starting…' if not settings.debug else 'Time remaining: Unavailable during calibration')
        self.run_id += 1
        run_id = self.run_id
        self.stopping = self.finished = False
        self._mouse_failure = None
        self._gold_stop_reason = None
        self._finish_report_reason = None
        self._report_since = time.time()-1
        self._show_report_actions()
        background = self.control_mode.get() == 'Background' and mouse_target is not None
        self._background_run = background
        self._clear_pointer_alert()
        self._set_compact_hint("")
        self._native_mouse_run = mouse_target is not None and not background
        self._graceful_stop = mouse_target is not None or self._structured_adb
        self._session_log_path = None
        self._session_log_writer = None
        self._trace_ready = False
        self._stop_key_status = 'Starting'
        self._stop_key_detection = ''
        if mouse_target or settings.trace_input:
            try:
                folder = APP_DIR/session_log_folder(self.control_mode.get() if mouse_target else 'ADB')
                folder.mkdir(exist_ok=True)
                self._session_log_path = folder/f'{time.time_ns()}-{uuid.uuid4().hex}.log'
                self._session_log_writer = BoundedSessionLog(self._session_log_path)
            except OSError:
                self._session_log_path = None
        self._exit_seen = False
        self._session_started = False
        self.stop_key_pressed = False
        self._finalized_run_id = None
        self._recognition_setup_needed = False
        self.started_at = None
        self.launch_started_at = time.monotonic()
        self.elapsed.set("0m 00s")
        self.raw_output = self.partial_line = ""
        self._live_stats_seen = False
        self._purchase_counts = {}
        self._purchase_sound_free_at = 0.0
        self._legacy_progress_seen = False
        self.metric_captions[1].configure(text=t('session.skystone_spent_estimated'))
        self.log.configure(state=tk.NORMAL)
        self.log.delete("1.0", tk.END)
        self.log.configure(state=tk.DISABLED)
        self.activity.delete(*self.activity.get_children())
        for var in (self.spent, self.covenant, self.mystic, self.friendship):
            var.set("—")
        self._update_spent_display()
        self.progress.configure(value=0)
        self.progress_text.set(t('mode.preparing_background') if background else
                               t('mode.preparing_mouse') if mouse_target else t('session.preparing_engine'))
        self.status.set("Starting")
        self.detail.set(t('mode.background_starting') if background else
                        t('mode.mouse_starting') if mouse_target else
                        t('session.preparing'))
        self._set_controls(True)
        self._event(f"Starting on {mouse_target.title if mouse_target else settings.device} · budget {settings.budget:,.0f} skystone.")
        arguments = engine_command()
        skip_items = (['--skip-covenant'] if not settings.buy_covenant else []) + (['--skip-mystic'] if not settings.buy_mystic else [])
        if background:
            arguments += ['--background-session','--budget',str(settings.budget),'--delay',str(settings.tap_sleep),
                          '--stop-key',settings.stop_key,'--random-offset','yes' if settings.random_offset else 'no',
                          '--tap-jitter',str(settings.tap_jitter)]
            arguments += ['--trace-input'] if settings.trace_input else []
            arguments += ['--buy-friendship'] if settings.buy_friendship else []
            arguments += skip_items
        elif mouse_target is not None:
            arguments += ['--mouse-session',json.dumps(dict(handle=mouse_target.handle,pid=mouse_target.pid,
                          title=mouse_target.title,rectangle=mouse_target.rectangle,render_handle=mouse_target.render_handle,
                          trace_input=settings.trace_input)),
                          '--budget',str(settings.budget),'--delay',str(settings.tap_sleep),
                          '--stop-key',settings.stop_key,'--random-offset','yes' if settings.random_offset else 'no',
                          '--tap-jitter',str(settings.tap_jitter)]
            if settings.buy_friendship:
                arguments.append('--buy-friendship')
            arguments += skip_items
        elif self._structured_adb:
            payload = asdict(settings)
            if settings.gold_cap is None:
                del payload['gold_cap']
            arguments += ['--gui-session', json.dumps(payload)]
        else:
            arguments += ['--tap-jitter',str(settings.tap_jitter)]
        if mouse_target is not None and settings.gold_cap is not None:
            arguments += ['--gold-cap', str(settings.gold_cap)]
        try:
            process, self.process_tree = launch_engine(arguments, cwd=APP_DIR, env=engine_environment(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace", bufsize=1, creationflags=NO_WINDOW)
        except OSError as exc:
            self.status.set("Failed")
            self.remaining_time.set('Time remaining: —')
            self.session_estimate.enabled = False
            self.detail.set(t('session.engine_launch_error'))
            self._append_log(str(exc))
            self._event("Engine launch failed.")
            self.started_at = None
            self._set_controls(False)
            return
        self.process = process
        threading.Thread(target=self._read_engine, args=(process, run_id, settings), daemon=True).start()
        self.after(500, lambda: self._watch_process(process, run_id))

    def _read_engine(self, process, run_id, settings):
        protocol = EngineProtocol(settings)
        chunk = ""
        try:
            while char := process.stdout.read(1):
                chunk += char
                for answer in protocol.feed(char):
                    if process.poll() is None:
                        process.stdin.write(answer + "\n")
                        process.stdin.flush()
                    if protocol.started:
                        self.log_queue.put((run_id, "started", None))
                        protocol.started = False
                    self.log_queue.put((run_id, "output", (chunk, time.monotonic())))
                    chunk = ""
                if char in "\r\n" or len(chunk) >= 256:
                    self.log_queue.put((run_id, "output", (chunk, time.monotonic())))
                    chunk = ""
        except (OSError, ValueError) as exc:
            self.log_queue.put((run_id, "io_error", str(exc)))
        finally:
            if chunk:
                self.log_queue.put((run_id, "output", (chunk, time.monotonic())))
            self.log_queue.put((run_id, "eof", None))
            for pipe in (process.stdin, process.stdout):
                if pipe:
                    try:
                        pipe.close()
                    except OSError:
                        pass

    def _engine_started(self):
        if self._session_started or self.stopping or self._finalized_run_id == self.run_id:
            return
        if self.run_settings.trace_input and not getattr(self, '_trace_ready', False):
            self._append_log('This engine did not enable detailed input logging. Use the matching bundled engine.\n')
        self._session_started = True
        self._update_remaining_time()
        self.started_at = time.monotonic()
        self.status.set("Calibrating" if self.run_settings.debug else "Running")
        self.detail.set(t('setup.calibration_running') if self.run_settings.debug else t('session.refreshing'))
        self.progress_text.set(t('setup.calibration_progress') if self.run_settings.debug else t('session.waiting_for_progress'))
        self._event(t('setup.calibration_started') if self.run_settings.debug else t('session.engine_ready'))
        self._play_session_sound("started")
        # Calibration needs the full window beside its image windows. Mouse mode
        # reads the real screen, so an always-on-top bar over the game would hide
        # what it reads (the shop title, W11 STOVE 2026-11-14); Background
        # captures the game window itself and is unaffected.
        if self.compact_tracker.get() and not self.run_settings.debug and not self._native_mouse_run:
            self.tracker.enter(friendship=self.run_settings.buy_friendship)

    def _freeze_elapsed(self):
        if self.started_at is not None:
            self.elapsed.set(duration_text(time.monotonic() - self.started_at))
            self.started_at = None

    def _start_pointer_alert(self, reason, observed_at=None):
        self._pointer_reason = reason
        self._pointer_deadline = (time.monotonic() if observed_at is None else observed_at)+POINTER_PAUSE_LIMIT
        self._tick_pointer_alert()

    def _tick_pointer_alert(self):
        self._pointer_job = None
        if self._pointer_deadline is None or self.status.get() != 'Paused':
            self._clear_pointer_alert()
            return
        left = math.ceil(self._pointer_deadline-time.monotonic())
        self.pointer_alert.set(pointer_pause_text(self._pointer_reason, left))
        self._pointer_job = self.after(250, self._tick_pointer_alert)

    def _set_compact_hint(self, text):
        """Show a hint; it clears by itself unless the run stays paused."""
        if self._hint_job is not None:
            try:
                self.after_cancel(self._hint_job)
            except tk.TclError:
                pass
            self._hint_job = None
        self.compact_hint.set(text)
        if text:
            self._hint_job = self.after(COMPACT_HINT_SECONDS*1000, self._expire_compact_hint)

    def _expire_compact_hint(self):
        self._hint_job = None
        if self.status.get() == 'Paused' or self.status.get() in ('Waiting for game', 'Waiting for game window'):
            self._hint_job = self.after(COMPACT_HINT_SECONDS*1000, self._expire_compact_hint)
        else:
            self.compact_hint.set('')

    def _clear_pointer_alert(self):
        self._pointer_deadline = None
        if self._pointer_job is not None:
            try:
                self.after_cancel(self._pointer_job)
            except tk.TclError:
                pass
            self._pointer_job = None
        if self.pointer_alert.get():
            self.pointer_alert.set('')

    def _update_remaining_time(self, observed_at=None):
        if not self._session_started or self.finished or self.stopping or self.stop_key_pressed or self._mouse_failure or self._gold_stop_reason:
            return
        estimate = self.session_estimate
        if self.run_settings.debug:
            text = t('session.estimate_calibration')
        elif self.status.get() in ('Waiting for game', 'Waiting for game window'):
            text = t('session.estimate_waiting_for_game')
        elif self._legacy_progress_seen and not self._live_stats_seen:
            text = t('session.estimate_engine_unavailable')
        elif estimate.finishing:
            text = t('session.estimate_finishing')
        else:
            seconds = estimate.remaining(observed_at)
            text = t('session.estimate_pending') if seconds is None else f'~{duration_text(math.ceil(seconds))}'
        if estimate.paused_at is not None:
            text = t('session.estimate_paused') + text
        display = 'Time remaining: ' + text
        if self.remaining_time.get() != display:
            self.remaining_time.set(display)

    def _handle_output(self, text, observed_at=None):
        self._handle_output_batch([(text, observed_at)])

    def _handle_output_batch(self, chunks):
        lines = []
        for text, observed_at in chunks:
            self.partial_line += text
            complete = re.split(r"[\r\n]", self.partial_line)
            self.partial_line = complete.pop()[-12000:]
            lines.extend((line, observed_at) for line in complete)
        if lines:
            self._append_log(''.join(format_trace_line(line)+'\n' for line, _ in lines))
        for line, observed_at in lines:
            self._handle_line(line.strip(), observed_at=observed_at)

    def _handle_line(self, line, observed_at=None):
        if not line:
            return
        if line == 'E7GUI_TRACE_READY':
            self._trace_ready = True
            self._append_log('Detailed input logging enabled. Coordinates use the 1920×1080 recognition frame; mapped coordinates use screen/device pixels.\n')
            return
        if line == 'E7GUI_STARTED':
            self._engine_started()
            return
        if line.startswith(('E7GUI_MOUSE_PAUSED ', 'E7GUI_MOUSE_STOPPED ', 'E7GUI_STOPPED ', 'E7GUI_GOLD_LIMIT_REACHED ')):
            try:
                reason = str(json.loads(line.split(' ',1)[1])['reason'])
            except (ValueError,KeyError,TypeError):
                return
            if not line.startswith('E7GUI_MOUSE_PAUSED '):
                if line.startswith('E7GUI_GOLD_LIMIT_REACHED '):
                    self._gold_stop_reason = reason
                    self.status.set('Stopped')
                else:
                    self._mouse_failure = reason
                    self.status.set('Needs attention')
                self.remaining_time.set('Time remaining: Session stopped')
                self._freeze_elapsed()
                self._set_compact_hint('')
            else:
                self._set_compact_hint(pause_hint(reason))
                self.status.set('Paused')
                self.session_estimate.pause(observed_at)
                self._update_remaining_time(observed_at)
                if reason.startswith(POINTER_PAUSE_REASONS):
                    self.progress_text.set(t('tracker.pointer_pause_detail'))
                    self._start_pointer_alert(reason, observed_at)
                else:
                    self._clear_pointer_alert()
                    self.progress_text.set(t('tracker.pause_reason_hint') if self._background_run else
                                           t('tracker.covered_pause_detail'))
            self.detail.set(reason)
            self._event(reason)
            return
        if line == 'E7GUI_MOUSE_RESUMED':
            if not self.stopping and not self.stop_key_pressed:
                self.session_estimate.resume(observed_at)
                self.status.set('Running')
                self._update_remaining_time(observed_at)
                self.detail.set(t('session.game_visible'))
                self.progress_text.set(t('session.checking_game'))
                self._set_compact_hint(t('tracker.visibility_restored'))
            return
        if line.startswith('E7GUI_SETUP_REQUIRED '):
            if not self.stopping and not self.stop_key_pressed:
                self._recognition_setup_needed = True
                if self._finalized_run_id == self.run_id:
                    self.after_idle(lambda run_id=self.run_id: self._offer_recognition_setup(run_id))
            self._event('Automatic shop recognition needs help. Stopped before purchases or refreshes.')
            return
        if line.startswith('Navigation: '):
            message = line[len('Navigation: '):]
            self.detail.set(message)
            if not self.stopping and not self.stop_key_pressed:
                if message.startswith('Waiting for visible game controls.'):
                    self.status.set('Waiting for game')
                    self.progress_text.set(t('tracker.reveal_game_controls'))
                elif self.status.get() == 'Waiting for game':
                    self.status.set('Calibrating' if self.run_settings.debug else 'Running')
                    self.progress_text.set(t('session.waiting_for_progress'))
                if hasattr(self, 'session_estimate'):
                    self._update_remaining_time(observed_at)
                hint = navigation_hint(message)
                if hint is not None:
                    self._set_compact_hint(hint)
            self._event(line)
            return
        if line.startswith('E7GUI_STOP_KEY '):
            try:
                hotkey=json.loads(line[len('E7GUI_STOP_KEY '):])
                if hotkey['status']=='ready':
                    self._stop_key_status=f"{hotkey['key']} · {hotkey['backend']}"
                    self._event(f"Global Stop key ready: {hotkey['key']}.")
                elif hotkey['status']=='failed':
                    self._stop_key_status=hotkey['reason']
                    self.detail.set(hotkey['reason']);self._event(hotkey['reason'])
                elif hotkey['status']=='pressed':
                    self._stop_key_detection=str(hotkey['source'])
                    self._stop_key_status=f"{hotkey['key']} · {self._stop_key_detection}"
                    self._event(f"Stop key detected: {hotkey['key']} via {self._stop_key_detection}.")
                elif hotkey['status']=='released':
                    self._stop_key_status=t('session.stop_key_released', key=hotkey['key'])
                    detection=getattr(self,'_stop_key_detection','')
                    if detection:self._stop_key_status+=f" · {detection}"
                self._update_diagnostics_summary()
            except (ValueError,KeyError,TypeError):pass
            return
        if line.startswith('E7GUI_STATS '):
            try:
                stats = json.loads(line[len('E7GUI_STATS '):])
                keys = ('refreshes', 'skystone_spent', 'covenant', 'mystic', 'friendship')
                if not isinstance(stats, dict) or any(type(stats.get(key)) is not int or stats[key] < 0 for key in keys):
                    raise ValueError('Invalid live counters')
                if stats['skystone_spent'] != stats['refreshes'] * 3:
                    raise ValueError('Invalid refresh spending')
            except (ValueError, TypeError):
                return
            self._live_stats_seen = True
            self._announce_purchases(stats)
            self.session_estimate.observe(stats['refreshes'], observed_at)
            self._update_remaining_time(observed_at)
            for key, var in (('skystone_spent', self.spent), ('covenant', self.covenant), ('mystic', self.mystic), ('friendship', self.friendship)):
                value = number_text(stats[key])
                if var.get() != value:
                    if key in ('covenant', 'mystic', 'friendship') and stats[key] > 0:
                        self._event(f"{key.capitalize()} purchases: {value}.")
                    var.set(value)
            percent = min(100, stats['skystone_spent'] / self.run_settings.budget * 100)
            self.progress.configure(value=percent)
            self.progress_text.set(t('session.reported_spend',
                refreshes=localized_number(stats['refreshes'], ','),
                amount=localized_number(stats['skystone_spent'], ',')))
            if self.run_settings.buy_friendship:
                self.progress_text.set(self.progress_text.get()+t('session.reported_friendship',
                    count=localized_number(stats['friendship'], ',')))
            self.metric_captions[1].configure(text=t('session.skystone_spent'))
            return
        if "Shop refresh terminated!" in line:
            self.stop_key_pressed = True
            self.status.set("Stopping")
            self.remaining_time.set('Time remaining: Session stopped')
            self.detail.set(t('session.stop_key_recording'))
            self._event("Stop key pressed. Refresh stopped.")
            self._freeze_elapsed()
            self.after(1500, lambda process=self.process, run_id=self.run_id: self._end_stopped_engine(process, run_id))
        if "Progress:" in line and not self.stopping and not self.stop_key_pressed:
            self._engine_started()
        if (match := re.match(r"^(\d{1,3})%", line)) and not self._live_stats_seen:
            self._legacy_progress_seen = True
            self._update_remaining_time(observed_at)
            percent = min(int(match[1]), 100)
            self.progress.configure(value=percent)
            self.progress_text.set(t('session.reported_budget_percent', percent=percent))
            self.spent.set(f"{self.run_settings.budget * percent / 100:,.0f}")
            for label, var in (("Cove", self.covenant), ("Myst", self.mystic)):
                found = re.search(rf"\b{label}\w*:\s*(\d+)", line, re.I)
                if found:
                    value = found[1]
                    if var.get() != value:
                        if int(value) > 0:
                            self._event(f"{'Covenant' if label == 'Cove' else 'Mystic'} purchases: {value}.")
                        var.set(value)
        if "---Result---" in line:
            self.finished = True
            self.remaining_time.set('Time remaining: Session stopped' if self.stopping or self.stop_key_pressed or self._mouse_failure or self._gold_stop_reason else 'Time remaining: Complete')
            self._freeze_elapsed()
            self._event("Refresh ended. Recording session results.")
        for label, var in (("Covenant bookmark", self.covenant), ("Mystic medal", self.mystic), ('Friendship points', self.friendship), ("Skystone spent", self.spent)):
            if match := re.match(rf"{label}\s*:\s*(\d+)", line):
                var.set(number_text(match[1]))
        if re.search(r"Traceback|Error:|Exception:|Fail to connect|folder is missing|screen.*(?:wrong|incorrect)", line, re.I):
            self._event(line[:350])
            self.detail.set(t('session.engine_problem'))
        if "to stop debug" in line or "check image - find it in taskbar" in line:
            self._event(t('setup.calibration_image_open'))

    def stop_refresh(self):
        if self._checking_connection:
            self._connection_check_id += 1
            self._checking_connection = False
            self._set_controls(False)
            self.status.set('Stopped')
            self.detail.set(t('connection.check_cancelled'))
            return
        process = self.process
        if not process:
            return
        if process.poll() is not None:
            self._finish_process(process, self.run_id)
            return
        if self.stopping:
            return
        self.stopping = True
        self.remaining_time.set('Time remaining: Session stopped')
        self._freeze_elapsed()
        self.status.set("Stopping")
        self.detail.set(t('session.stop_engine_warning'))
        self.progress_text.set(t('session.stopping_engine'))
        self.stop_button.configure(state=tk.DISABLED)
        self._event("Stop requested.")
        if self._graceful_stop or self._native_mouse_run:
            try:
                process.stdin.write('STOP\n')
                process.stdin.flush()
                # Capture/OCR calls have bounded 10-second timeouts. Do not kill
                # their result-writing cleanup after only 2.5 seconds.
                self.after(12000,lambda:self._kill_if_needed(process))
                return
            except (OSError,ValueError):
                pass
        try:
            self.process_tree.stop(process) if self.process_tree else process.terminate()
            if self._native_mouse_run:
                release_native_button()
        except OSError as exc:
            self._append_log(f"Stop failed: {exc}\n")
        self.after(2500, lambda: self._kill_if_needed(process))

    def _end_stopped_engine(self, process, run_id):
        if process is self.process and run_id == self.run_id and self.stop_key_pressed and process.poll() is None:
            self.stop_refresh()

    def _kill_if_needed(self, process):
        if process is self.process and process.poll() is None:
            try:
                if self.process_tree and self.process_tree.handle:
                    self.process_tree.close()  # Windows: KILL_ON_JOB_CLOSE ends the whole job
                else:
                    process.kill()
                if self._native_mouse_run:
                    release_native_button()
            except OSError as exc:
                self._append_log(f"Stop failed: {exc}\n")

    def _watch_process(self, process, run_id):
        if run_id != self.run_id:
            return
        if self.started_at:
            self.elapsed.set(duration_text(time.monotonic() - self.started_at))
        self._update_remaining_time()
        if process.poll() is None:
            if self.status.get() == "Starting" and time.monotonic() - self.launch_started_at > 30:
                self.detail.set(t('session.slow_startup'))
            self.after(500, lambda: self._watch_process(process, run_id))
            return
        if not self._exit_seen:
            self._exit_seen = True
            if self.process_tree:
                self.process_tree.close()
            if self._native_mouse_run:
                release_native_button()
            self.after(150, lambda: self._finish_process(process, run_id))

    def _finish_process(self, process=None, run_id=None):
        process = process or self.process
        run_id = self.run_id if run_id is None else run_id
        if not process or process is not self.process or run_id != self.run_id:
            return
        if self._finalized_run_id == self.run_id:
            return
        if process.poll() is None:
            return
        if self.partial_line:
            self._append_log(format_trace_line(self.partial_line)+'\n')
            self._handle_line(self.partial_line.strip())
            self.partial_line = ""
        self._finalized_run_id = self.run_id
        self._freeze_elapsed()
        if self.process_tree:
            self.process_tree.close()
        reason = None
        detail_key = None
        detail_values = {}
        if self._mouse_failure and not self.stopping and not self.stop_key_pressed:
            self.status.set('Needs attention')
            reason = self._mouse_failure
            self.progress_text.set(t('session.stopped_reason_hint'))
        elif self.stopping or self.stop_key_pressed or (process.returncode == 0 and (
                self._gold_stop_reason or (self.run_settings and self.run_settings.debug and self._session_started and not self.finished))):
            self.status.set("Stopped")
            reason = self._gold_stop_reason
            detail_key = 'session.finish_stopped'
            self.progress_text.set(t('session.progress_stopped'))
            self._play_session_sound("stopped")
        elif process.returncode == 0 and self.finished:
            self.status.set("Finished")
            detail_key = 'session.finish_complete'
            self.progress_text.set(t('session.complete'))
            self._play_session_sound("finished")
        else:
            self.status.set("Needs attention")
            detail_key = 'session.finish_error'
            detail_values = {'code': process.returncode}
            self.progress_text.set(t('session.engine_exited'))
        # Activity tags and diagnostic reports use the original English or engine reason.
        self._finish_report_reason = reason or t(detail_key, 'en', **detail_values)
        self.detail.set(reason or t(detail_key, **detail_values))
        self._event(self._finish_report_reason)
        self.remaining_time.set('Time remaining: Complete' if self.status.get() == 'Finished' else 'Time remaining: Session stopped')
        self.session_estimate.enabled = False
        self._set_controls(False)
        self.refresh_history()
        self._offer_recognition_setup(self.run_id)

    def _update_debug_availability(self, running=False):
        mouse = self.control_mode.get() != 'ADB'
        if mouse:
            self.debug_mode.set(False)
        self.debug_check.state(['disabled'] if running or mouse else ['!disabled'])

    def _set_controls(self, running):
        for widget in self.settings_widgets:
            widget.state(["disabled"] if running else ["!disabled"])
        self._update_debug_availability(running)
        self._update_tap_jitter(running=running)
        self.clear_history_button.state(['disabled'] if running else ['!disabled'])
        self.export_history_button.state(['disabled'] if running else ['!disabled'])
        self.open_logs_button.state(['disabled'] if running and self.control_mode.get() != 'ADB' else ['!disabled'])
        self.start_button.configure(state=tk.DISABLED if running else tk.NORMAL)
        self.stop_button.configure(state=tk.NORMAL if running else tk.DISABLED)
        if not running and self.control_mode.get() != 'ADB':
            self.device_box.state(['readonly'])
            self._update_mouse_selection()
        if not running:
            self.stop_button.configure(text=t('session.stop'))

    def _drain_log_queue(self):
        output = []
        deadline = time.perf_counter() + 0.008
        for _ in range(300):
            if time.perf_counter() >= deadline:
                break
            try:
                run_id, kind, value = self.log_queue.get_nowait()
            except queue.Empty:
                break
            if run_id is not None and run_id != self.run_id:
                continue
            if kind == "output":
                output.append(value if isinstance(value, tuple) else (value, None))
                if sum(len(text) for text, _ in output) >= 16384:
                    break
                continue
            if output:
                self._handle_output_batch(output)
                output.clear()
            if kind == "eof":
                self._finish_process()
            elif kind == "started":
                self._engine_started()
            elif kind == "io_error":
                self._append_log(f"\nEngine I/O ended: {value}\n")
            elif kind == "devices":
                self._device_scan_busy = False
                token, value, background = value
                if token == self._connection_check_id and self.control_mode.get() == 'ADB' and not self._checking_connection and not (self.process and self.process.poll() is None):
                    if (not background or list(value.devices) != self.connected_devices or
                            value.endpoints != getattr(self, 'discovered_endpoints', ())):
                        self._apply_devices(value.devices, value.warning, value.diagnostics, value.endpoints)
                    else:
                        self.device_button.configure(state=tk.NORMAL)
                        self.device_notice.set(value.warning or t('connection.device_count',
                            count=len(value.devices)))
                    self._set_connection_warning(value.warning)
            elif kind == 'connection':
                self._complete_connection_check(*value)
            elif kind == 'windows':
                token, windows, error, suggestion, notice_key = value
                self._mouse_scan_busy = False
                if token == self._connection_check_id and self.control_mode.get() != 'ADB':
                    self._apply_mouse_windows(windows, error, suggestion, notice_key=notice_key)
        if output:
            self._handle_output_batch(output)
        self.after(100, self._drain_log_queue)

    def _append_log(self, text):
        if self._session_log_path:
            try:
                writer = getattr(self, '_session_log_writer', None)
                if writer is not None:
                    writer.append(text)
            except OSError:
                self._session_log_path = None
        had_output = bool(self.raw_output)
        self.raw_output = (self.raw_output + text)[-150000:]
        if not had_output:
            # A launch failure sets Failed before its error reaches the log.
            self._show_report_actions()
        at_bottom = self.log.yview()[1] >= 0.99
        self.log.configure(state=tk.NORMAL)
        # Normalize carriage-return progress updates for readable diagnostics.
        self.log.insert(tk.END, text.replace("\r", "\n"))
        if int(self.log.index("end-1c").split(".")[0]) > 2000:
            self.log.delete("1.0", "501.0")
        if at_bottom:
            self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _event(self, text):
        required = self.ui_font.measure(text) + self._dp(24)
        if required > self.activity.column("event", "minwidth"):
            self.activity.column("event", minwidth=required, width=required)
        tag = ('covenant' if text.startswith('Covenant purchases:') else
               'mystic' if text.startswith('Mystic purchases:') else
               'friendship' if text.startswith('Friendship purchases:') else
               'error' if re.search(r'failed|error|exception|traceback|not recognized|could not|cannot', text, re.I) else
               'warning' if re.search(r'stop|pause|waiting|cancel|needs help', text, re.I) else
               'success' if re.search(r'completed|finished|refresh ended|resumed', text, re.I) else '')
        item = self.activity.insert("", tk.END, tags=(tag,) if tag else (), values=(time.strftime("%H:%M:%S"), text))
        items = self.activity.get_children()
        if len(items) > 100:
            self.activity.delete(items[0])
        self.activity.see(item)

    def _update_diagnostics_summary(self):
        settings=self.run_settings

        def state_label(name):
            active = getattr(settings, name) if settings else getattr(self, name).get()
            return t('common.on') if active else t('common.off')

        self.diagnostics_summary.set(t('diagnostics.purchase_summary',
            covenant=self.covenant.get(),
            covenant_state=state_label('buy_covenant'),
            mystic=self.mystic.get(),
            mystic_state=state_label('buy_mystic'),
            friendship=self.friendship.get(),
            friendship_state=state_label('buy_friendship'),
            stop_key=self._stop_key_status if hasattr(self, '_stop_key_status') else t('diagnostics.no_active_session')))

    def _copy_diagnostics(self):
        self.clipboard_clear()
        settings=self.run_settings
        on=lambda name:'on' if (getattr(settings,name) if settings else getattr(self,name).get()) else 'off'
        stop_status=self._stop_key_status if hasattr(self, '_stop_key_status') else t('diagnostics.no_active_session', 'en')
        self.clipboard_append(anonymize(f"App: v{APP_VERSION}\nSystem: {system_name()}\nControl: {self.control_mode.get()}\nEngine: {ENGINE_EXE}\nState: {self.status.get()}\n"
            f"Stop key: {stop_status}\nBuying: Covenant {on('buy_covenant')} · Mystic {on('buy_mystic')} · Friendship Points {on('buy_friendship')}\n"
            f"Purchases: Covenant {self.covenant.get()} · Mystic {self.mystic.get()} · Friendship {self.friendship.get()}\n\n{self.raw_output}"))

    def _report_text(self):
        target = '' if self.control_mode.get() == 'ADB' else self.mouse_target.get()
        reason = self._mouse_failure or ''
        if not reason and self.status.get() in ('Needs attention', 'Failed'):
            reason = getattr(self, '_finish_report_reason', None) or self.detail.get()
        return build_report(version=APP_VERSION, mode=self.control_mode.get(), target=target, state=self.status.get(),
                            reason=reason, log=self.raw_output, app_dir=APP_DIR, since=getattr(self, '_report_since', None))

    def _failure_folder(self):
        since = getattr(self, '_report_since', None)
        return None if since is None else latest_failure(APP_DIR, since)

    def _show_report_actions(self):
        if not hasattr(self, 'report_actions'):
            return
        if self.status.get() in ('Needs attention', 'Failed') and self.raw_output:
            if self._failure_folder() is not None:
                self.open_failure_button.pack(side='left', padx=(self._dp(8), 0))
            else:
                self.open_failure_button.pack_forget()
            self.report_actions.grid()
        else:
            self.report_actions.grid_remove()

    def _copy_report(self):
        self.clipboard_clear()
        self.clipboard_append(self._report_text())
        self.copy_report_button.configure(text=t('diagnostics.report_copied'))
        self.after(2500, lambda: self.copy_report_button.winfo_exists() and self.copy_report_button.configure(text=t('diagnostics.copy_report')))

    def _open_failure_folder(self):
        folder = self._failure_folder()
        if folder is None:
            return
        try:
            if hasattr(os, 'startfile'):
                os.startfile(str(folder.resolve()), 'open')
            else:
                subprocess.Popen(['xdg-open', str(folder.resolve())], stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        except OSError as error:
            messagebox.showerror(t('diagnostics.open_pictures_error'), str(error), parent=self)

    def _open_logs_folder(self):
        if self.control_mode.get() != 'ADB' and (self._checking_connection or (self.process and self.process.poll() is None)):
            return
        folder = self._session_log_path.parent if self._session_log_path else APP_DIR / (
            session_log_folder(self.control_mode.get()))
        try:
            folder.mkdir(parents=True, exist_ok=True)
            if hasattr(os, 'startfile'):
                os.startfile(str(folder.resolve()), 'open')
            else:
                subprocess.Popen(['xdg-open', str(folder.resolve())], stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        except OSError as error:
            messagebox.showerror(t('diagnostics.open_logs_error'), str(error), parent=self)

    def _update_history_xscroll(self, first, last):
        self.history_xscroll.set(first, last)
        if float(first) <= 0 and float(last) >= 1:
            self.history_xscroll.grid_remove()
        else:
            self.history_xscroll.grid()

    def refresh_history(self):
        try:
            rows = read_sessions(HISTORY_FILE, limit=25)
        except (OSError, csv.Error, UnicodeError) as exc:
            self.history_notice.set(t('history.read_error'))
            self._append_log(f"History read failed: {exc}\n")
            return
        self._history_reasons = {}
        self.history.delete(*self.history.get_children())
        for i, row in enumerate(reversed(rows)):
            mode = row['Mode']
            tags = ('debug',) if mode == 'Debug' else ('even',) if i % 2 == 0 else ()
            counts = (number_text(row.get(key), localized=True) for key in (
                'Skystone spent', 'Gold spent', 'Covenant bookmark', 'Mystic medal', 'Friendship points'))
            item = self.history.insert('', tk.END, tags=tags, values=(
                mode, duration_text(row.get('Duration')), *counts,
                row.get('Started at', '').replace('T', ' ').replace('+00:00', ''),
                row.get('Control mode', 'Unknown'), row.get('Outcome', 'Unknown (legacy)')))
            if not hasattr(self, '_history_reasons'):
                self._history_reasons = {}
            self._history_reasons[item] = row.get('Reason', '')
        if len(rows) == 1:
            notice = t('history.recent_single')
        elif rows:
            notice = t('history.recent_count', count=len(rows))
        else:
            notice = t('history.empty')
        self.history_notice.set(notice)
        self._history_signature = self._get_history_signature()

    def _history_selected(self, _event=None):
        selected = self.history.selection()
        if selected:
            reason = self._history_reasons.get(selected[0], '')
            self.history_notice.set(reason or t('history.no_end_reason'))

    def _export_history(self):
        if self._checking_connection or (self.process and self.process.poll() is None):
            return
        try:
            rows = read_sessions(HISTORY_FILE)
            if not rows:
                self.history_notice.set(t('history.nothing_to_export'))
                return
            destination = filedialog.asksaveasfilename(parent=self, title=t('history.export_title'),
                defaultextension='.xlsx', filetypes=[(t('history.excel_workbook'), '*.xlsx')],
                initialfile=f'E7-sessions-{time.strftime("%Y-%m-%d_%H-%M-%S")}-{uuid.uuid4().hex[:8]}.xlsx')
            if destination:
                export_sessions(destination, rows)
                self.history_notice.set(t('history.exported_count', count=len(rows)))
        except (OSError, csv.Error, UnicodeError, ValueError) as error:
            messagebox.showerror(t('history.export_error'), str(error), parent=self)

    def _get_history_signature(self):
        try:
            stat = HISTORY_FILE.stat()
            return stat.st_mtime_ns, stat.st_size
        except FileNotFoundError:
            return None
        except OSError:
            return self._history_signature

    def _poll_history(self):
        if self._get_history_signature() != self._history_signature:
            self.refresh_history()
        self.after(3000, self._poll_history)

    def _clear_history(self):
        if self._checking_connection or (self.process and self.process.poll() is None):
            return
        if not HISTORY_FILE.exists() or not self.history.get_children():
            return
        if not messagebox.askyesno(t('history.clear_title'), t('history.clear_confirm',
            folder=HISTORY_FILE.parent / 'archive'), parent=self):
            return
        try:
            original = HISTORY_FILE.read_bytes()
            # Keep the exact old CSV, including its debug/normal header schema.
            header = original.splitlines(keepends=True)[0]
            folder = HISTORY_FILE.parent/'archive'
            folder.mkdir(exist_ok=True)
            archive = folder/f'{HISTORY_FILE.stem}-{time.time_ns()}-{uuid.uuid4().hex}.csv'
            with archive.open('xb') as file:
                file.write(original)
            temporary = HISTORY_FILE.with_suffix('.csv.tmp')
            temporary.write_bytes(header)
            temporary.replace(HISTORY_FILE)
        except (OSError, IndexError) as exc:
            self._append_log(f'History clear failed: {exc}\n')
            messagebox.showerror(t('history.clear_error'), str(exc), parent=self)
            return
        self.refresh_history()
        self._event(t('history.archived'))

    def _toggle_settings_details(self):
        self.details_expanded = not self.details_expanded
        if self.details_expanded:
            self.settings_details.grid()
        else:
            self.settings_details.grid_remove()
        self.details_button.configure(text=('▾' if self.details_expanded else '▸')+t('settings.advanced_label'))
        self.update_idletasks()
        self._update_settings_scroll()

    def _step_tap_jitter(self, step):
        if not self.tap_jitter_slider.instate(['disabled']):
            self.tap_jitter.set(max(0, min(.1, round(self.tap_jitter.get()+step, 2))))
            self._update_tap_jitter()
        return 'break'

    def _update_tap_jitter(self, _value=None, *, running=None):
        if not hasattr(self, 'tap_jitter_slider'):
            return
        selected = max(0, min(.1, round(self.tap_jitter.get(), 2)))
        self.tap_jitter.set(selected)
        enabled = self.random_offset.get() and not self.debug_mode.get()
        if running is None:
            running = self._checking_connection or (self.process and self.process.poll() is None)
        self.tap_jitter_slider.state(['disabled'] if running or not enabled else ['!disabled'])
        try:
            baseline = float(self.tap_sleep.get())
            effective = min(selected, baseline * .5) if math.isfinite(baseline) and baseline > 0 else selected
        except ValueError:
            effective = selected
        digits = 3 if 0 < effective < .01 else 2
        self.tap_jitter_text.set(t('settings.tap_variation', value=localized_number(effective, f'.{digits}f'))
                                 if enabled else t('settings.tap_variation_off'))

    def _update_spent_display(self):
        try:
            total = self.run_settings.budget if self.run_settings else int(self.budget.get())
            count = '0' if self.spent.get() == '—' else self.spent.get()
            self.spent_display.set(f'{count} / {total:,}' if total >= 3 else '—')
        except ValueError:
            self.spent_display.set('—')

    def _update_ev(self):
        def display(text):
            # Localize separators in the computed estimate without touching its values or templates.
            if current_locale() == 'pt_BR':
                return re.sub(r'(?<=\d)[,.](?=\d)', lambda match: '.' if match[0] == ',' else ',', text)
            return text

        try:
            budget = int(self.budget.get())
            if budget < 3:
                raise ValueError
            covenant, mystic = self.buy_covenant.get(), self.buy_mystic.get()
            gold = budget * (COVENANT_RATE * 184000 * covenant + MYSTIC_RATE * 280000 * mystic)
            lines = [t('budget.estimated_gold', amount=int(gold))]
            lines += [t('budget.estimated_covenant', count=budget * COVENANT_RATE)] if covenant else []
            lines += [t('budget.estimated_mystic', count=budget * MYSTIC_RATE)] if mystic else []
            self.ev.set(display('\n'.join(lines)))
            if self.buy_friendship.get():
                self.ev.set(self.ev.get()+t('budget.friendship_extra_gold'))
            expected = [t('budget.summary_covenant', count=budget * COVENANT_RATE)] if covenant else []
            expected += [t('budget.summary_mystic', count=budget * MYSTIC_RATE)] if mystic else []
            summary = t('budget.summary_refreshes', count=budget // 3)
            summary += t('budget.summary_expect') + t('budget.summary_and').join(expected) if expected else ''
            summary += t('budget.summary_gold', amount=int(gold)) if gold else ''
            if hasattr(self, 'budget_summary'):
                self.budget_summary.set(display(summary))
        except (ValueError, OverflowError):
            self.ev.set(t('budget.invalid'))
            if hasattr(self, 'budget_summary'):
                self.budget_summary.set(t('budget.minimum'))
        self._update_spent_display()

    def _schedule_autosave(self):
        """Save shortly after the last settings change; there is no Save button."""
        if getattr(self, '_autosave_suspended', False) or not hasattr(self, '_autosave_saved'):
            return
        job = getattr(self, '_autosave_job', None)
        if job is not None:
            self.after_cancel(job)
        self._autosave_job = self.after(AUTOSAVE_DELAY_MS, self._autosave)

    def _autosave_snapshot(self):
        return (self.budget.get(), self.gold_cap.get(), self.stop_key.get(), self.buy_covenant.get(), self.buy_mystic.get(),
                self.buy_friendship.get(), self.tap_sleep.get(), self.random_offset.get(), round(self.tap_jitter.get(), 2),
                self.control_mode.get())

    def _flush_autosave(self):
        """Save a change still waiting out the autosave delay (used on close)."""
        job = getattr(self, '_autosave_job', None)
        if job is not None:
            self.after_cancel(job)
            self._autosave()

    def _autosave(self):
        self._autosave_job = None
        if getattr(self, '_restart_required', False):
            return  # imported files wait for the restart
        if self._checking_connection:
            # Start is checking the connection; if that fails, Start saves
            # nothing, so try again once it is over.
            self._autosave_job = self.after(AUTOSAVE_DELAY_MS, self._autosave)
            return
        if self.process and self.process.poll() is None:
            return  # settings are locked while running; Start already saved them
        snapshot = self._autosave_snapshot()
        if snapshot == self._autosave_saved:
            # e.g. a value rewritten unchanged, or an edit undone
            if self.setting_notice.get().startswith('Not saved yet'):
                self.setting_notice.set('')
            return
        try:
            # Same checks as Start, without needing a device: an unfinished
            # budget or no item chosen keeps the engine file as it was.
            settings = validate_settings('autosave', self.budget.get(), self.tap_sleep.get(), self.stop_key.get(),
                                         self.random_offset.get(), False, round(self.tap_jitter.get(), 2),
                                         self.trace_input.get(), self.buy_friendship.get(),
                                         self.buy_covenant.get(), self.buy_mystic.get(), gold_cap=self.gold_cap.get())
            problem = ''
        except ValueError as exc:
            settings, problem = None, str(exc)
        if settings is None:
            # Nothing is written, the GUI file included: it holds the Buy
            # choices too, and an all-off choice must not be reloaded.
            self.setting_notice.set(f'Not saved yet: {problem}')
            return
        try:
            self._write_engine_settings(settings)
            self._write_sound_preference(settings)
        except (OSError, UnicodeError, configparser.Error) as exc:
            self.setting_notice.set(t('settings.save_error', error=exc))
            return
        self._autosave_saved = snapshot
        self.setting_notice.set(t('settings.saved'))

    def _write_engine_settings(self, settings):
        """Update ADBconfig.ini in place; an unreadable file is never replaced."""
        if getattr(self, '_restart_required', False):
            return  # imported files wait for the restart
        parser = configparser.ConfigParser()
        try:
            with CONFIG_FILE.open(encoding='utf-8-sig') as fh:
                parser.read_file(fh)
        except FileNotFoundError:
            pass
        if not parser.has_section('Settings'):
            parser.add_section('Settings')
        parser['Settings'].update({'tap_sleep': str(settings.tap_sleep), 'budget': str(settings.budget),
                                   'stop_refresh_key': settings.stop_key, 'random_offset': str(settings.random_offset)})
        temp = CONFIG_FILE.with_suffix('.ini.tmp')
        with temp.open('w', encoding='utf-8') as fh:
            parser.write(fh)
        temp.replace(CONFIG_FILE)
        self._timing_migration_pending = False

    def _close(self):
        if self.tracker.active:
            self.tracker.restore()  # Closing the bar shows the full window; it does not stop the session.
            return
        self._connection_check_id += 1
        self._checking_connection = False
        if self.process and self.process.poll() is None:
            if not messagebox.askyesno(t('session.stop_and_close_title'), t('session.stop_and_close_confirm'), parent=self):
                return
            self.stop_refresh()
            self.after(100, self._close_when_stopped)
        else:
            self._flush_autosave()
            self.destroy()

    def _close_when_stopped(self):
        if self.process and self.process.poll() is None:
            self.after(100, self._close_when_stopped)
        else:
            self.destroy()

    def destroy(self):
        native_running = self._native_mouse_run and self.process and self.process.poll() is None
        if self.process_tree:
            self.process_tree.close()
        if native_running:
            release_native_button()
        # Cancel scheduled callbacks before Tcl commands are destroyed.
        for callback in self.tk.splitlist(self.tk.call("after", "info")):
            self.after_cancel(callback)
        super().destroy()
        if self._native_icons:
            self._native_icons.close()


def enable_dpi_awareness():
    if os.name == "nt":
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass


def main(argv=None):
    parser = argparse.ArgumentParser(description=t('startup.cli_description'))
    parser.add_argument("--engine-dir", metavar="FOLDER", help=t('startup.cli_engine_dir'))
    parser.add_argument('--verify', action='store_true', help=t('startup.cli_verify'))
    parser.add_argument('--verification-report', metavar='FILE', help=t('startup.cli_verification_report'))
    args = parser.parse_args(argv)
    try:
        configure_engine_directory(resolve_engine_directory(args.engine_dir))
        if not args.verify:  # the offline check never creates or migrates user data
            location = prepare_data_directory(APP_DIR)
            events = list(location.events)
            preferences = location.directory / 'ShopRefreshGUI.ini'
            set_locale(load_language(preferences))
            if needs_import_choice(location):
                events += offer_older_settings(location.directory)
                set_locale(load_language(preferences))
            configure_data_directory(location.directory, events)
        if args.verify:
            from e7_appearance import Image
            if Image is None:
                raise ValueError('Pillow image support is missing. Use the bundled player EXE.')
            for name in ('background-day-hd.png', 'background-night-hd.png', 'mystic-medal.png',
                         'covenant-bookmark.png', 'skystone.png', 'blue-natto-avatar.png',
                         'github-black.png', 'github-white.png'):
                with Image.open(ASSET_DIR/name) as artwork:
                    artwork.verify()
            if args.verification_report:
                Path(args.verification_report).write_text(json.dumps(dict(
                    frozen=bool(getattr(sys, 'frozen', False)), artwork='verified', pillow=Image.__version__,
                    tcl=tk.Tcl().eval('info patchlevel'),
                    engine_directory=str(APP_DIR), missing_references=missing_references(APP_DIR),
                    builtin_recognition=has_builtin_references(APP_DIR),
                    recognition_ready=not missing_references(APP_DIR) or has_builtin_references(APP_DIR),
                    gui_or_adb_started=False), indent=2), encoding='utf-8')
            return 0
    except (ValueError, OSError, tk.TclError, ImportError) as error:
        if args.verify:
            if args.verification_report:
                Path(args.verification_report).write_text(json.dumps(dict(
                    frozen=bool(getattr(sys, 'frozen', False)), error=str(error),
                    project_directory=str(PROJECT_DIR), gui_or_adb_started=False), indent=2), encoding='utf-8')
            return 2
        # Windowed Python launchers have no stderr; keep their errors visible.
        if sys.stderr is None:
            root = tk.Tk()
            root.withdraw()
            try:
                messagebox.showerror(t('startup.engine_unavailable_title'), str(error), parent=root)
            finally:
                root.destroy()
            return 2
        parser.error(str(error))
    RefreshGui().mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
