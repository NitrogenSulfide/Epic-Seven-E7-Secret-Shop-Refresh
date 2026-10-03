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
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import font as tkfont, messagebox, ttk
from e7_process import launch_engine
from e7_appearance import Scenery, ThemeHint, currency_icons, theme_icon
from e7_about import AboutDialog

PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_ENGINE_DIR = Path.home() / "Downloads" / "E7 Secret Shop Refresh"
ENGINE_LOCATION_FILE = PROJECT_DIR / "engine-location.ini"
APP_DIR = DEFAULT_ENGINE_DIR
ENGINE_EXE = APP_DIR / "E7ADBShopRefresh.exe"
ADB_EXE = APP_DIR / "adb-assets" / "platform-tools" / "adb.exe"
CONFIG_FILE = APP_DIR / "ADBconfig.ini"
GUI_CONFIG_FILE = APP_DIR / "ShopRefreshGUI.ini"
HISTORY_FILE = APP_DIR / "ShopRefreshHistory" / "ADB_History.csv"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
ASSET_DIR = PROJECT_DIR / "e7_gui_assets"
STOP_KEY_CHARACTERS = "0123456789abcdefghijklmnopqrstuvwxyz/.,';[]`"


def captured_stop_key(keysym, character, state=0):
    # Control/Alt combinations are not supported by the engine's single-key setting.
    # Windows Tk: Control=0x4, Alt/Mod2=0x10 (also ALT_MASK=0x20000).
    # Mod1=0x8 is Num Lock, not Alt; lock states must not reject input.
    if state & (0x4 | 0x10 | 0x20000):
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
                raise ValueError(f"Cannot read engine folder from {location_file}: {error}") from error
    if selected is None:
        return DEFAULT_ENGINE_DIR
    selected = selected.strip()
    if not selected:
        raise ValueError("The selected engine folder is empty. Set directory to the installed engine folder.")
    directory = Path(os.path.expandvars(selected)).expanduser()
    if not directory.is_absolute():
        directory = location_file.parent / directory
    return directory.resolve()


def configure_engine_directory(directory):
    """Validate before redirecting any device scans, settings or history."""
    global APP_DIR, ENGINE_EXE, ADB_EXE, CONFIG_FILE, GUI_CONFIG_FILE, HISTORY_FILE
    directory = Path(directory)
    engine = directory / "E7ADBShopRefresh.exe"
    adb = directory / "adb-assets" / "platform-tools" / "adb.exe"
    missing = [str(path.relative_to(directory)) for path in (engine, adb) if not path.is_file()]
    if missing:
        raise ValueError(
            f"Engine folder: {directory}\nMissing: {', '.join(missing)}\n"
            "Select the installed engine folder with --engine-dir, E7_ENGINE_DIR, "
            "or engine-location.ini."
        )
    APP_DIR = directory
    ENGINE_EXE, ADB_EXE = engine, adb
    CONFIG_FILE = directory / "ADBconfig.ini"
    GUI_CONFIG_FILE = directory / "ShopRefreshGUI.ini"
    HISTORY_FILE = directory / "ShopRefreshHistory" / "ADB_History.csv"


@dataclass(frozen=True)
class RunSettings:
    device: str
    budget: float
    tap_sleep: float
    stop_key: str
    random_offset: bool
    debug: bool


def validate_settings(device, budget, delay, stop_key, random_offset, debug):
    try:
        amount, sleep = float(budget), float(delay)
    except ValueError:
        raise ValueError("Enter numbers for the skystone budget and tap delay.") from None
    if not math.isfinite(amount) or amount < 3:
        raise ValueError("The skystone budget must be a finite number of at least 3.")
    if not math.isfinite(sleep) or sleep <= 0:
        raise ValueError("The tap delay must be a finite number greater than zero.")
    device = device.strip() or "localhost:5555"
    key = stop_key.strip().lower() or "esc"
    if any(c in device for c in "\r\n"):
        raise ValueError("The device must be a single ADB address.")
    if key != "esc" and (len(key) != 1 or key not in STOP_KEY_CHARACTERS):
        raise ValueError("Use Esc or a single letter, number, or / . , ' ; [ ] ` as the stop key.")
    return RunSettings(device, amount, sleep, key, bool(random_offset), bool(debug))


def duration_text(value):
    try:
        seconds = max(0, int(float(value)))
        if seconds >= 3600:
            return f"{seconds // 3600}h {(seconds % 3600) // 60:02d}m {seconds % 60:02d}s"
        return f"{seconds // 60}m {seconds % 60:02d}s"
    except (ValueError, OverflowError, TypeError):
        return "—"


def number_text(value):
    try:
        n = float(value)
        return f"{n:,.0f}" if math.isfinite(n) else "—"
    except (ValueError, TypeError):
        return "—"


def history_mode(row, fieldnames):
    # The engine has two inventory schemas: debug adds a Friendship count.
    # Existing files retain their first header, so mixed runs may place that
    # count in DictReader's extra-field list instead of a named column.
    if 'Friendship bookmark' in fieldnames:
        return 'Debug' if row.get('Friendship bookmark') is not None else 'Normal'
    standard = ['Duration', 'Skystone spent', 'Gold spent', 'Covenant bookmark', 'Mystic medal']
    if fieldnames == standard:
        extra = row.get(None, [])
        if len(extra) == 1 and str(extra[0]).isdigit():
            return 'Debug'
        if not extra:
            return 'Normal'
    return 'Unknown'


class EngineProtocol:
    """Answer observed prompts: the engine skips device selection with one device.

    Never send a timed, positional answer list. A skipped prompt otherwise shifts
    every subsequent setting and can start a run with the wrong budget.
    """
    def __init__(self, settings):
        self.settings = settings
        self.pending = ""
        self.started = False

    def feed(self, text):
        self.pending = (self.pending + text)[-12000:]
        s = self.settings
        prompts = (
            ("when you finish reading, press enter to continue!", ""),
            ("Device: ", s.device),
            ("leave blank for yes, or type (yes/no): ", "no"),
            ("Launch in debug mode? leave bank for no (yes/no): ", "yes" if s.debug else "no"),
            ("Key: ", s.stop_key),
            ("Enable randomize click (yes/no): ", "yes" if s.random_offset else "no"),
            ("Tap sleep(in seconds) Recommend - leave blank for 0.3 sec : ", str(s.tap_sleep)),
            ("Amount of skystone that you want to spend: ", str(s.budget)),
            ("Press enter to start!", ""),
            ("press enter to exit...", ""),
            ("Press enter to exit ...", ""),
        )
        answers = []
        while True:
            matches = [(self.pending.find(prompt), prompt, answer) for prompt, answer in prompts if prompt in self.pending]
            if not matches:
                break
            at, prompt, answer = min(matches)
            self.pending = self.pending[at + len(prompt):]
            if prompt == "Press enter to start!":
                self.started = True
            answers.append(answer)
        return answers


class RefreshGui(tk.Tk):
    def __init__(self):
        enable_dpi_awareness()
        super().__init__()
        self.title("E7 Secret Shop Refresh")
        self._configure_scaling()
        self._layout_job = None
        self._icon_job = None
        self._native_icons = None
        self._finalized_run_id = None
        self.stop_key_pressed = False
        self.sound_enabled = tk.BooleanVar(value=True)
        self.dark_mode = tk.BooleanVar(value=False)
        self.credits_seen = tk.BooleanVar(value=False)
        self.credits_on_startup = tk.BooleanVar(value=False)
        self.about_window = None
        self._live_stats_seen = False
        self.process = None
        self.process_tree = None
        self._exit_seen = False
        self._session_started = False
        self.launch_started_at = None
        self.run_id = 0
        self.log_queue = queue.Queue()
        self.run_settings = None
        self.started_at = None
        self.stopping = False
        self.finished = False
        self.partial_line = ""
        self.raw_output = ""
        self.budget = tk.StringVar(value="12")
        self.tap_sleep = tk.StringVar(value="0.3")
        self.stop_key = tk.StringVar(value="`")
        self.device = tk.StringVar(value="localhost:5555")
        self.device_labels = {}
        self.connected_devices = []
        self.debug_mode = tk.BooleanVar(value=False)
        self.random_offset = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="Ready")
        self.detail = tk.StringVar(value="Open Epic Seven’s Secret Shop, then start a session.")
        self.home_ui_hint = tk.StringVar(value="Hidden home UI? Click the game once before Start.")
        self.setting_notice = tk.StringVar(value="")
        self.device_notice = tk.StringVar(value="Checking ADB devices…")
        self.history_notice = tk.StringVar(value="")
        self.elapsed = tk.StringVar(value="0m 00s")
        self.spent = tk.StringVar(value="—")
        self.covenant = tk.StringVar(value="—")
        self.mystic = tk.StringVar(value="—")
        self.friendship = tk.StringVar(value="—")
        self.progress_text = tk.StringVar(value="Waiting for a session")
        self.ev = tk.StringVar()
        self._load_config()
        self._build_ui()
        self.scenery = Scenery(self, ASSET_DIR)
        self._apply_theme()
        self._load_icon()
        self._fit_initial_window()
        self.bind('<Map>', self._schedule_native_icon, add='+')
        self._schedule_native_icon()
        self.refresh_devices()
        self.refresh_history()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(100, self._drain_log_queue)
        self.after(300, self._maybe_show_credits)

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
        self.settings_canvas.configure(scrollregion=self.settings_canvas.bbox("all"))
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
        style.configure('Status.TLabel', foreground=('#fbbf24' if dark else '#92400e') if self.status.get() == 'Waiting for game' else ('#60a5fa' if dark else '#2563eb'))
        self.home_ui_notice.configure(bg='#422006' if dark else '#fff4d6', fg='#fbbf24' if dark else '#92400e', highlightbackground='#b45309' if dark else '#f59e0b')
        for name in ('TEntry', 'TCombobox'):
            style.configure(name, background=field, fieldbackground=field, foreground=fg, insertcolor=fg, bordercolor=border, lightcolor=border, darkcolor=border, arrowcolor=fg)
            style.map(name, background=[('disabled', bg), ('readonly', field)], fieldbackground=[('disabled', bg), ('readonly', field)], foreground=[('disabled', muted), ('readonly', fg)], arrowcolor=[('disabled', muted), ('!disabled', fg)])
        for name in ('TButton', 'Treeview.Heading'):
            style.configure(name, background=active, foreground=fg, bordercolor=border, lightcolor=border, darkcolor=border)
            style.map(name, background=[('active', border)], foreground=[('disabled', muted)])
        style.configure('Accent.TButton', background='#2563eb', foreground='#ffffff')
        style.map('Accent.TButton', background=[('disabled', active), ('active', '#1d4ed8')], foreground=[('disabled', muted), ('!disabled', '#ffffff')])
        style.map('Large.TCheckbutton', foreground=[('disabled', muted)], background=[('active', bg)])
        style.configure('Treeview', background=field, fieldbackground=field, foreground=fg, bordercolor=border)
        style.map('Treeview', background=[('selected', '#2563eb')], foreground=[('selected', '#ffffff')])
        self.history.tag_configure('even', background=bg, foreground=fg)
        self.history.tag_configure('debug', background='#422006' if dark else '#fff4d6', foreground='#fcd34d' if dark else '#92400e')
        style.configure('TNotebook', background=bg, bordercolor=border)
        tabs = [('selected', bg), ('active', active), ('!selected', field)]
        style.map('TNotebook.Tab', background=tabs, lightcolor=tabs, darkcolor=tabs, foreground=[('selected', fg), ('!selected', muted)])
        for name in ('TScrollbar', 'Horizontal.TScrollbar', 'Vertical.TScrollbar'):
            style.configure(name, background=active, troughcolor=bg, arrowcolor=fg, bordercolor=border, lightcolor=border, darkcolor=border)
            style.map(name, background=[('active', border), ('!disabled', active)], arrowcolor=[('disabled', muted), ('!disabled', fg)])
        style.configure('Horizontal.TProgressbar', troughcolor=active, bordercolor=border)
        self.log.configure(bg=field, fg=fg, insertbackground=fg, selectbackground='#2563eb', selectforeground='#ffffff')
        for option, color in (('background', field), ('foreground', fg), ('selectBackground', '#2563eb'), ('selectForeground', '#ffffff')):
            self.option_add('*TCombobox*Listbox.' + option, color)
        self._build_checkbox_style(style)
        style.configure('Large.TCheckbutton', background=bg, foreground=fg)
        target = 'Switch to light mode' if dark else 'Switch to dark mode'
        self.theme_image = theme_icon(self, self._dp(25), dark)
        self.theme_button.configure(text=target if self.theme_image else ('☀' if dark else '☾'), image=self.theme_image or '', compound='none')
        if hasattr(self, 'scenery'):
            self.scenery.schedule()
        if self.about_window is not None and self.about_window.winfo_exists():
            self.about_window.apply_theme(dark)

    def _maybe_show_credits(self):
        if self.winfo_viewable() and (not self.credits_seen.get() or self.credits_on_startup.get()):
            self._show_about()

    def _show_about(self):
        if self.about_window is not None and self.about_window.winfo_exists():
            self.about_window.lift()
            return
        self.about_window = AboutDialog(self, PROJECT_DIR, first_time=not self.credits_seen.get())

    def _save_credits_preference(self):
        try:
            self._write_sound_preference()
        except (OSError,configparser.Error) as exc:
            self.setting_notice.set('Credits preference changed for this session; it could not be saved.')
            self._append_log(f'Credits preference save failed: {exc}\n')

    def _toggle_dark_mode(self):
        self.dark_mode.set(not self.dark_mode.get())
        self._apply_theme()
        try:
            self._write_sound_preference()
        except (OSError, configparser.Error) as exc:
            self.setting_notice.set('Theme changed for this session; preference could not be saved.')
            self._append_log(f'Theme preference save failed: {exc}\n')

    def _update_home_ui_hint(self, *_):
        waiting = self.status.get() == 'Waiting for game'
        self.home_ui_hint.set('Click the game once to reveal controls and continue.' if waiting else
                              'Hidden home UI? Click the game once before Start.')
        dark = self.dark_mode.get()
        ttk.Style(self).configure('Status.TLabel', foreground=('#fbbf24' if dark else '#92400e') if waiting else ('#60a5fa' if dark else '#2563eb'))

    def _schedule_layout(self, _event=None):
        if self._layout_job is not None:
            self.after_cancel(self._layout_job)
        self._layout_job = self.after(35, self._layout_dashboard)

    def _layout_dashboard(self):
        self._layout_job = None
        width = self.right_panel.winfo_width()
        self.home_ui_notice.configure(wraplength=max(self._dp(250), width-self._dp(30)))
        self.detail_label.configure(wraplength=max(self._dp(250), width-self._dp(12)))
        self.diagnostics_label.configure(wraplength=max(self._dp(250), width-self._dp(60)))
        self.history_label.configure(wraplength=max(self._dp(250), width-self._dp(12)))
        # Four cards on wide windows, two per row when the viewport is narrower.
        minimum_card = max(self.heading_font.measure("Skystone spent ≈") + self._dp(38), self.value_font.measure("12h 59m 59s")) + self._dp(32)
        columns = 4 if width >= minimum_card*4 + self._dp(18) else 2
        for i in range(4):
            self.metrics.columnconfigure(i, weight=1 if i < columns else 0, minsize=0, uniform="metrics" if i < columns else "")
        for i, card in enumerate(self.metric_cards):
            card.grid(row=i//columns, column=i%columns, sticky="nsew", padx=(0 if i%columns == 0 else self._dp(6), 0), pady=(0, self._dp(6) if columns == 2 else 0))
        # Measure both messages even when detail is hidden in a short window,
        # so hiding it cannot flip the layout back and forth on the next pass.
        messages_height = self.home_ui_notice.winfo_reqheight() + self.detail_label.winfo_reqheight() + self._dp(6)
        required_height = sum(widget.winfo_reqheight() for widget in (self.session_title, self.metrics, self.progress_frame, self.history_header, self.history_label)) + messages_height + self.table_rowheight*6 + self._dp(160)
        compact = self.right_panel.winfo_height() < required_height
        if compact != self.compact_history:
            self.compact_history = compact
            for widget in (self.history_header, self.history_frame, self.history_label):
                widget.grid_forget()
            if compact:
                self.notebook.add(self.history_tab, text="History")
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
        condensed = compact and self.right_panel.winfo_height() < top_height + self.table_rowheight*2 + self._dp(90)
        for widget in (self.session_title, self.detail_label):
            widget.grid_remove() if condensed else widget.grid()
        content_selected = compact and self.notebook.select() != self.notebook.tabs()[0]
        for widget in (self.metrics, self.progress_frame):
            widget.grid_remove() if content_selected else widget.grid()
        self.right_panel.rowconfigure(4, minsize=self.table_rowheight*(2 if condensed else 3)+self._dp(55))

    def _play_session_sound(self, outcome):
        if not self.sound_enabled.get():
            return
        try:
            if os.name == "nt":
                import winsound
                sound = ASSET_DIR / ("start.wav" if outcome == "started" else "end.wav")
                if sound.is_file():
                    winsound.PlaySound(str(sound), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
                else:
                    alias = "SystemAsterisk" if outcome == "started" else "SystemExclamation"
                    winsound.PlaySound(alias, winsound.SND_ALIAS | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
            else:
                self.bell()
        except (OSError, RuntimeError):
            self._append_log("\nThe session sound could not be played.\n")

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
        header = ttk.Frame(self, padding=(dp(24), dp(16), dp(24), dp(12)))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Secret Shop", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, text="Refresh sessions · Epic Seven · Blue Natto", style="Muted.TLabel").grid(row=1, column=0, sticky="w")
        ttk.Label(header, textvariable=self.status, font=("Segoe UI", 12, "bold"), style='Status.TLabel').grid(row=0, column=1, sticky="e")
        header_actions = ttk.Frame(header)
        header_actions.grid(row=1,column=1,sticky='e')
        self.about_button = ttk.Button(header_actions, text='ⓘ', command=self._show_about, width=3, padding=dp(8), cursor='hand2', takefocus=True)
        self.about_button.pack(side='left',padx=(0,dp(6)))
        self.about_hint = ThemeHint(self.about_button, lambda: 'About & Credits')
        self.theme_button = ttk.Button(header_actions, command=self._toggle_dark_mode, width=3, padding=dp(8), cursor='hand2', takefocus=True)
        self.theme_button.pack(side='left')
        self.theme_hint = ThemeHint(self.theme_button, lambda: 'Switch to light mode' if self.dark_mode.get() else 'Switch to dark mode')
        body = ttk.Frame(self, padding=(dp(24), 0, dp(24), dp(20)))
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)
        sidebar = ttk.Frame(body, padding=(0, 0, dp(20), 0))
        sidebar.grid(row=0, column=0, sticky="nsw")
        sidebar.rowconfigure(0, weight=1)
        self.settings_canvas = settings_canvas = tk.Canvas(sidebar, width=dp(370), bg="#f3f5f8", highlightthickness=0)
        settings_canvas.grid(row=0, column=0, sticky="ns")
        self.settings_scroll = settings_scroll = ttk.Scrollbar(sidebar, command=settings_canvas.yview)
        settings_canvas.configure(yscrollcommand=settings_scroll.set)
        action_dock = ttk.Frame(sidebar, padding=(0, dp(10), dp(10), 0))
        action_dock.grid(row=1, column=0, columnspan=2, sticky="ew")
        action_dock.columnconfigure((0, 1), weight=1, uniform="actions")
        self.settings_controls = controls = ttk.Frame(settings_canvas, padding=(0, 0, dp(10), 0))
        controls_window = settings_canvas.create_window((0, 0), window=controls, anchor="nw")
        controls.bind("<Configure>", self._update_settings_scroll)
        def resize_settings(event):
            settings_canvas.itemconfigure(controls_window, width=event.width)
            self._update_settings_scroll()
        settings_canvas.bind("<Configure>", resize_settings)
        controls.columnconfigure(0, weight=1)
        self.settings_widgets = []
        ttk.Label(controls, text="SESSION SETTINGS", style="Muted.TLabel").grid(row=0, column=0, sticky="w", pady=(0, dp(8)))
        ttk.Label(controls, text="Emulator / ADB device").grid(row=1, column=0, sticky="w")
        device_row = ttk.Frame(controls)
        device_row.grid(row=2, column=0, sticky="ew", pady=(4, 0))
        device_row.columnconfigure(0, weight=1)
        self.device_box = ttk.Combobox(device_row, textvariable=self.device, width=19, font=self.ui_font)
        self.device_box.grid(row=0, column=0, sticky="ew")
        self.device_button = ttk.Button(device_row, text="Scan", width=7, command=self.refresh_devices)
        self.device_button.grid(row=0, column=1, padx=(dp(12), 0))
        self.settings_widgets.extend([self.device_box, self.device_button])
        ttk.Label(controls, textvariable=self.device_notice, style="Muted.TLabel", wraplength=dp(350)).grid(row=3, column=0, sticky="w", pady=(dp(4), dp(10)))
        for row, label, var in ((4, "Skystone budget", self.budget), (6, "Tap delay · seconds", self.tap_sleep), (8, "Stop key", self.stop_key)):
            if var is self.stop_key:
                label = "Stop key · click the box, then press a key"
            ttk.Label(controls, text=label).grid(row=row, column=0, sticky="w")
            entry = ttk.Entry(controls, textvariable=var, font=self.ui_font)
            if var is self.stop_key:
                self.stop_key_entry = entry
                entry.state(["readonly"])
                entry.bind("<KeyPress>", self._capture_stop_key)
            entry.grid(row=row+1, column=0, sticky="ew", pady=(dp(4), dp(8)))
            self.settings_widgets.append(entry)
        random = ttk.Checkbutton(controls, text="Randomize tap offsets", variable=self.random_offset, style="Large.TCheckbutton")
        random.grid(row=10, column=0, sticky="w")
        debug = ttk.Checkbutton(controls, text="Debug / calibration mode", variable=self.debug_mode, style="Large.TCheckbutton")
        debug.grid(row=11, column=0, sticky="w", pady=(6, 0))
        self.settings_widgets.extend([random, debug])
        ttk.Label(controls, text="Debug includes Friendship Points.\nPress a key (not Esc) in each image to continue.", style="Muted.TLabel", wraplength=dp(350)).grid(row=12, column=0, sticky="w", pady=(dp(4), dp(12)))
        self.start_button = ttk.Button(action_dock, text="Start Refresh", style="Accent.TButton", command=self.start_refresh)
        self.start_button.grid(row=0, column=0, sticky="ew", padx=(0, dp(4)))
        self.stop_button = ttk.Button(action_dock, text="Stop Session", command=self.stop_refresh, state=tk.DISABLED)
        self.stop_button.grid(row=0, column=1, sticky="ew", padx=(dp(4), 0))
        self.save_button = ttk.Button(action_dock, text="Save Settings", command=self.save_settings)
        self.save_button.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(dp(6), 0))
        self.settings_widgets.append(self.save_button)
        self.sound_button = ttk.Checkbutton(action_dock, text="Sounds on start and end", variable=self.sound_enabled, style="Large.TCheckbutton", command=self._save_sound_preference)
        self.sound_button.grid(row=2, column=0, columnspan=2, sticky="w", pady=(dp(6), 0))
        ttk.Label(action_dock, textvariable=self.setting_notice, style="Muted.TLabel", wraplength=dp(350)).grid(row=3, column=0, columnspan=2, sticky="w", pady=(dp(4), 0))
        estimate = ttk.LabelFrame(controls, text="Budget estimate", padding=dp(12))
        estimate.grid(row=13, column=0, sticky="ew", pady=(dp(4), 0))
        ttk.Label(estimate, textvariable=self.ev, wraplength=dp(320), justify=tk.LEFT).grid(sticky="w")
        ttk.Label(estimate, text="Statistical estimate; results vary.", style="Muted.TLabel", wraplength=dp(320)).grid(sticky="w", pady=(dp(8), 0))
        self.budget.trace_add("write", lambda *_: self._update_ev())
        self._update_ev()
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

        self.right_panel = right = ttk.Frame(body)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(4, weight=1, minsize=self.table_rowheight * 3 + dp(55))
        right.rowconfigure(6, weight=2, minsize=self.table_rowheight * 3 + dp(55))
        self.session_title = ttk.Label(right, text="Current session", font=("Segoe UI", 13, "bold"))
        self.session_title.grid(row=0, column=0, sticky="w")
        self.session_messages = ttk.Frame(right)
        self.session_messages.grid(row=1, column=0, sticky="ew", pady=(dp(4), dp(12)))
        self.session_messages.columnconfigure(0, weight=1)
        self.home_ui_notice = tk.Label(self.session_messages, textvariable=self.home_ui_hint,
                                      font=self.heading_font, anchor='w', justify='left',
                                      wraplength=dp(620), padx=dp(10), pady=dp(8),
                                      borderwidth=0, highlightthickness=dp(1))
        self.home_ui_notice.grid(row=0, column=0, sticky='ew', pady=(0,dp(6)))
        self.status.trace_add('write', self._update_home_ui_hint)
        self.detail_label = ttk.Label(self.session_messages, textvariable=self.detail, style="Muted.TLabel", wraplength=dp(620))
        self.detail_label.grid(row=1, column=0, sticky="w")
        self.metrics = metrics = ttk.Frame(right)
        metrics.bind("<Configure>", self._schedule_layout)
        metrics.grid(row=2, column=0, sticky="ew")
        self.metric_cards = []
        self.metric_captions = []
        self.currency_images = currency_icons(self, ASSET_DIR, dp(34))
        self.currency_labels = {}
        for i, (label, var, key) in enumerate((("Elapsed", self.elapsed, None), ("Skystone spent ≈", self.spent, 'spent'), ("Covenant buys", self.covenant, 'covenant'), ("Mystic buys", self.mystic, 'mystic'))):
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
        self.progress_frame = progress = ttk.Frame(right)
        progress.grid(row=3, column=0, sticky="ew", pady=(12, 12))
        progress.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(progress, maximum=100)
        self.progress.grid(row=0, column=0, sticky="ew")
        ttk.Label(progress, textvariable=self.progress_text, style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.notebook = notebook = ttk.Notebook(right)
        notebook.bind("<<NotebookTabChanged>>", self._schedule_layout)
        notebook.grid(row=4, column=0, sticky="nsew")
        activity_tab = ttk.Frame(notebook, padding=8)
        diagnostics_tab = ttk.Frame(notebook, padding=8)
        # Transparent label backing gives both buttons the same measured size.
        self.tab_spacer = tk.PhotoImage(master=self, width=self.ui_font.measure('Diagnostics'), height=self.ui_font.metrics('linespace'))
        notebook.add(activity_tab, text="Activity", image=self.tab_spacer, compound='center')
        notebook.add(diagnostics_tab, text="Diagnostics", image=self.tab_spacer, compound='center')
        self.history_tab = ttk.Frame(notebook, padding=dp(8))
        self.history_tab.columnconfigure(0, weight=1)
        self.history_tab.rowconfigure(1, weight=1)
        self.compact_history = False
        activity_tab.columnconfigure(0, weight=1)
        activity_tab.rowconfigure(0, weight=1)
        self.activity = ttk.Treeview(activity_tab, columns=("time", "event"), show="headings", height=4, selectmode="none")
        self.activity.heading("time", text="Time")
        self.activity.heading("event", text="Session activity", anchor=tk.W)
        time_width = max(self.ui_font.measure("23:59:59"), self.heading_font.measure("Time")) + dp(24)
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
        self.diagnostics_label = ttk.Label(diagnostics_tab, text="Full engine output · startup prompts are handled automatically", style="Muted.TLabel", wraplength=dp(600))
        self.diagnostics_label.grid(row=0, column=0, sticky="w", pady=(0, dp(6)))
        self.log = tk.Text(diagnostics_tab, wrap=tk.WORD, height=3, bg="#111827", fg="#e5e7eb", font=("Consolas", 11), relief=tk.FLAT, state=tk.DISABLED)
        self.log.grid(row=1, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(diagnostics_tab, command=self.log.yview)
        scroll.grid(row=1, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scroll.set)
        ttk.Button(diagnostics_tab, text="Copy Diagnostics", command=self._copy_diagnostics).grid(row=2, column=0, sticky="e", pady=(6, 0))
        self.history_header = history_header = ttk.Frame(right)
        history_header.grid(row=5, column=0, sticky="ew", pady=(16, 6))
        history_header.columnconfigure(0, weight=1)
        ttk.Label(history_header, text="Recent sessions", font=("Segoe UI", 13, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Button(history_header, text="Reload", command=self.refresh_history).grid(row=0, column=1)
        self.history_frame = history_frame = ttk.Frame(right)
        history_frame.grid(row=6, column=0, sticky="nsew")
        history_frame.columnconfigure(0, weight=1)
        history_frame.rowconfigure(0, weight=1)
        self.history = ttk.Treeview(history_frame, columns=("mode", "duration", "skystone", "gold", "cov", "mys"), show="headings", height=6)
        for key, label, width in (("mode", "Mode", 80), ("duration", "Duration", 125), ("skystone", "Skystone", 95), ("gold", "Gold", 120), ("cov", "Covenant buys", 115), ("mys", "Mystic buys", 105)):
            self.history.heading(key, text=label, anchor=tk.W if key in ("mode", "duration") else tk.E)
            samples = {"mode": "Unknown", "duration": "12h 59m 59s", "skystone": "99,999", "gold": "999,999,999", "cov": "9,999", "mys": "9,999"}
            column_width = max(self.heading_font.measure(label), self.ui_font.measure(samples[key])) + dp(24)
            self.history.column(key, width=column_width, minwidth=column_width, anchor=tk.W if key in ("mode", "duration") else tk.E, stretch=key != 'mode')
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
        self._event("Ready. Session updates will appear here.")

    def _load_config(self):
        try:
            parser = configparser.ConfigParser()
            parser.read(CONFIG_FILE)
            if parser.has_section("Settings"):
                settings = parser["Settings"]
                for key, var in (("tap_sleep", self.tap_sleep), ("budget", self.budget), ("stop_refresh_key", self.stop_key)):
                    var.set(settings.get(key, var.get()))
                self.random_offset.set(settings.get("random_offset", str(self.random_offset.get())).lower() == "true")
        except (OSError, ValueError, configparser.Error) as exc:
            self.setting_notice.set(f"Settings could not be read: {exc}")
        try:
            parser = configparser.ConfigParser()
            parser.read(GUI_CONFIG_FILE)
            self.sound_enabled.set(parser.getboolean("GUI", "sound_enabled", fallback=True))
            self.dark_mode.set(parser.getboolean("GUI", "dark_mode", fallback=False))
            self.credits_seen.set(parser.getboolean("GUI", "credits_seen", fallback=False))
            self.credits_on_startup.set(parser.getboolean("GUI", "show_credits_on_startup", fallback=False))
            self.device.set(parser.get("GUI", "device", fallback=self.device.get()))
        except (OSError, ValueError, configparser.Error) as exc:
            self.setting_notice.set(f"Sound preference could not be read: {exc}")

    def _write_sound_preference(self):
        # The original engine rewrites ADBconfig.ini, so GUI preferences need
        # their own file to survive a real refresh session.
        parser = configparser.ConfigParser()
        parser.read(GUI_CONFIG_FILE)
        if not parser.has_section("GUI"):
            parser.add_section("GUI")
        parser["GUI"]["sound_enabled"] = str(self.sound_enabled.get())
        parser["GUI"]["dark_mode"] = str(self.dark_mode.get())
        parser["GUI"]["credits_seen"] = str(self.credits_seen.get())
        parser["GUI"]["show_credits_on_startup"] = str(self.credits_on_startup.get())
        parser["GUI"]["device"] = self._device_address()
        temp = GUI_CONFIG_FILE.with_suffix(".ini.tmp")
        with temp.open("w", encoding="utf-8") as fh:
            parser.write(fh)
        temp.replace(GUI_CONFIG_FILE)

    def _save_sound_preference(self):
        try:
            self._write_sound_preference()
            self.setting_notice.set("Sound alerts on." if self.sound_enabled.get() else "Sound alerts off.")
        except (OSError, configparser.Error) as exc:
            self.setting_notice.set("Sound changed for this session; preference could not be saved.")
            self._append_log(f"Sound preference save failed: {exc}\n")

    def _capture_stop_key(self, event):
        if self.stop_key_entry.instate(["disabled"]):
            return "break"
        if event.keysym in ("Tab", "ISO_Left_Tab"):
            return None  # Preserve keyboard navigation.
        if event.keysym in ("Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R", "Caps_Lock", "Super_L", "Super_R", "Win_L", "Win_R"):
            return "break"
        key = captured_stop_key(event.keysym, event.char, event.state)
        if key is None:
            self.setting_notice.set("Choose Esc, a letter, number, or / . , ' ; [ ] `. No Ctrl/Alt combinations.")
        else:
            self.stop_key.set(key)
            self.setting_notice.set(f"Stop key: {'Esc' if key == 'esc' else key}.")
        return "break"

    def _settings(self):
        if len(self.connected_devices) > 1 and not self.device.get().strip():
            raise ValueError("Choose the emulator you want to use from the device list.")
        return validate_settings(self._device_address(), self.budget.get(), self.tap_sleep.get(), self.stop_key.get(), self.random_offset.get(), self.debug_mode.get())

    def _device_address(self):
        value = self.device.get().strip()
        return self.device_labels.get(value, value)

    def _apply_devices(self, devices, note, raw):
        previous = self._device_address()
        self.connected_devices = list(dict.fromkeys(devices))
        labels = [f"{address} (default)" if len(self.connected_devices) == 1 else address for address in self.connected_devices]
        self.device_labels = dict(zip(labels, self.connected_devices))
        self.device_box.configure(values=labels)
        running = self.process is not None and self.process.poll() is None
        if self.connected_devices:
            if len(self.connected_devices) == 1:
                if not running:
                    self.device.set(labels[0])
                note = "Default: the only connected emulator.\nEmulator ports can change."
            elif previous in self.connected_devices:
                if not running:
                    self.device.set(previous)
                note = "Several emulators connected. Your previous choice is selected."
            else:
                if not running:
                    self.device.set("")
                note = "Several emulators connected. Choose one from the list."
        self.device_notice.set(note)
        if not running:
            self.device_button.configure(state=tk.NORMAL)
            self.start_button.configure(state=tk.NORMAL)
        if not self.process:
            self._append_log(raw + "\n")

    def save_settings(self):
        try:
            settings = self._settings()
            parser = configparser.ConfigParser()
            parser.read(CONFIG_FILE)
            if not parser.has_section("Settings"):
                parser.add_section("Settings")
            parser["Settings"].update({"tap_sleep": str(settings.tap_sleep), "budget": str(settings.budget), "stop_refresh_key": settings.stop_key, "random_offset": str(settings.random_offset)})
            temp = CONFIG_FILE.with_suffix(".ini.tmp")
            with temp.open("w", encoding="utf-8") as fh:
                parser.write(fh)
            temp.replace(CONFIG_FILE)
            self._write_sound_preference()
        except (ValueError, OSError, configparser.Error) as exc:
            messagebox.showerror("Settings not saved", str(exc), parent=self)
            return None
        self.setting_notice.set("Settings saved.")
        return settings

    def refresh_devices(self):
        if self.process and self.process.poll() is None:
            return
        self.device_button.configure(state=tk.DISABLED)
        self.start_button.configure(state=tk.DISABLED)
        self.device_notice.set("Checking ADB devices…")
        def scan():
            try:
                result = subprocess.run([str(ADB_EXE), "devices"], cwd=APP_DIR, capture_output=True, text=True, errors="replace", timeout=8, creationflags=NO_WINDOW)
                devices = [p[0] for line in result.stdout.splitlines() if len(p := line.split()) >= 2 and p[1] == "device"]
                note = f"{len(devices)} connected device(s)." if devices else "No connected device found. You can enter an address."
                if result.returncode:
                    note = "ADB scan failed. Check Diagnostics."
                self.log_queue.put((None, "devices", (devices, note, result.stdout + result.stderr)))
            except (OSError, subprocess.SubprocessError) as exc:
                self.log_queue.put((None, "devices", ([], "ADB unavailable. Check Diagnostics.", str(exc))))
        threading.Thread(target=scan, daemon=True).start()

    def start_refresh(self):
        if self.process and self.process.poll() is None:
            return
        if not ENGINE_EXE.is_file():
            messagebox.showerror("Missing engine", f"Could not find {ENGINE_EXE}", parent=self)
            return
        if self.debug_mode.get():
            message = "Debug uses a fixed 100-skystone test budget, the Esc stop key, and randomized offsets. It includes Friendship Points when detected, and pauses BEFORE each click. Check each image, then press a key other than Esc in that image to continue. Buy and confirmation each have a pause. Continue?"
            if not messagebox.askyesno("Start calibration?", message, parent=self):
                return
        settings = self.save_settings()
        if settings is None:
            return
        if settings.debug:
            settings = RunSettings(settings.device, 100.0, settings.tap_sleep, "esc", True, True)
        self.run_settings = settings
        self.run_id += 1
        run_id = self.run_id
        self.stopping = self.finished = False
        self._exit_seen = False
        self._session_started = False
        self.stop_key_pressed = False
        self._finalized_run_id = None
        self.started_at = None
        self.launch_started_at = time.monotonic()
        self.elapsed.set("0m 00s")
        self.raw_output = self.partial_line = ""
        self._live_stats_seen = False
        self.metric_captions[1].configure(text='Skystone spent ≈')
        self.log.configure(state=tk.NORMAL)
        self.log.delete("1.0", tk.END)
        self.log.configure(state=tk.DISABLED)
        self.activity.delete(*self.activity.get_children())
        for var in (self.spent, self.covenant, self.mystic, self.friendship):
            var.set("—")
        self.progress.configure(value=0)
        self.progress_text.set("Connecting and preparing the engine…")
        self.status.set("Starting")
        self.detail.set("Preparing your session. Open the Secret Shop at 1920 × 1080.")
        self._set_controls(True)
        self._event(f"Starting on {settings.device} · budget {settings.budget:,.0f} skystone.")
        try:
            process, self.process_tree = launch_engine([str(ENGINE_EXE)], cwd=APP_DIR, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace", bufsize=1, creationflags=NO_WINDOW)
        except OSError as exc:
            self.status.set("Failed")
            self.detail.set("The engine could not start. Check Diagnostics.")
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
                    self.log_queue.put((run_id, "output", chunk))
                    chunk = ""
                if char in "\r\n" or len(chunk) >= 256:
                    self.log_queue.put((run_id, "output", chunk))
                    chunk = ""
        except (OSError, ValueError) as exc:
            self.log_queue.put((run_id, "io_error", str(exc)))
        finally:
            if chunk:
                self.log_queue.put((run_id, "output", chunk))
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
        self._session_started = True
        self.started_at = time.monotonic()
        self.status.set("Calibrating" if self.run_settings.debug else "Running")
        self.detail.set("Debug pauses before every click, including Buy and confirmation. Check the red rectangle, then press a key other than Esc in the image window. Esc stops the test." if self.run_settings.debug else "Refreshing the Secret Shop. Use Stop Session or your stop key to end.")
        self.progress_text.set("Calibration in progress · engine uses 100 skystone" if self.run_settings.debug else "Waiting for the engine’s first progress update…")
        self._event("Calibration started. Check the image window." if self.run_settings.debug else "Engine ready. Refreshing started.")
        self._play_session_sound("started")

    def _freeze_elapsed(self):
        if self.started_at is not None:
            self.elapsed.set(duration_text(time.monotonic() - self.started_at))
            self.started_at = None

    def _handle_output(self, text):
        self._append_log(text)
        self.partial_line += text
        lines = re.split(r"[\r\n]", self.partial_line)
        self.partial_line = lines.pop()[-12000:]
        for line in lines:
            self._handle_line(line.strip())

    def _handle_line(self, line):
        if not line:
            return
        if line.startswith('Navigation: '):
            message = line[len('Navigation: '):]
            self.detail.set(message)
            if not self.stopping and not self.stop_key_pressed:
                if message.startswith('Waiting for visible game controls.'):
                    self.status.set('Waiting for game')
                    self.progress_text.set('Reveal the game controls · no taps or spending while waiting')
                elif self.status.get() == 'Waiting for game':
                    self.status.set('Calibrating' if self.run_settings.debug else 'Running')
                    self.progress_text.set('Waiting for the engine’s first progress update…')
            self._event(line)
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
            for key, var in (('skystone_spent', self.spent), ('covenant', self.covenant), ('mystic', self.mystic), ('friendship', self.friendship)):
                value = number_text(stats[key])
                if var.get() != value:
                    if key in ('covenant', 'mystic') and stats[key] > 0:
                        self._event(f"{'Covenant' if key == 'covenant' else 'Mystic'} purchases: {value}.")
                    var.set(value)
            percent = min(100, stats['skystone_spent'] / self.run_settings.budget * 100)
            self.progress.configure(value=percent)
            self.progress_text.set(f"{stats['refreshes']:,} refreshes · {stats['skystone_spent']:,} skystone spent · engine reported")
            self.metric_captions[1].configure(text='Skystone spent')
            return
        if "Shop refresh terminated!" in line:
            self.stop_key_pressed = True
            self.status.set("Stopping")
            self.detail.set("Stop key detected. Recording the session results.")
            self._event("Stop key pressed. Refresh stopped.")
            self._freeze_elapsed()
            self.after(1500, lambda process=self.process, run_id=self.run_id: self._end_stopped_engine(process, run_id))
        if "Progress:" in line and not self.stopping and not self.stop_key_pressed:
            self._engine_started()
        if (match := re.match(r"^(\d{1,3})%", line)) and not self._live_stats_seen:
            percent = min(int(match[1]), 100)
            self.progress.configure(value=percent)
            self.progress_text.set(f"{percent}% of budget used · engine reported")
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
            self._freeze_elapsed()
            self._event("Refresh ended. Recording session results.")
        for label, var in (("Covenant bookmark", self.covenant), ("Mystic medal", self.mystic), ("Friendship bookmark", self.friendship), ("Skystone spent", self.spent)):
            if match := re.match(rf"{label}\s*:\s*(\d+)", line):
                var.set(number_text(match[1]))
                if label == "Friendship bookmark" and int(match[1]) > 0:
                    self._event(f"Friendship Points purchases: {match[1]}.")
        if re.search(r"Traceback|Error:|Exception:|Fail to connect|folder is missing|screen.*(?:wrong|incorrect)", line, re.I):
            self._event(line[:350])
            self.detail.set("The engine reported a problem. Check Diagnostics for details.")
        if "to stop debug" in line or "check image - find it in taskbar" in line:
            self._event("Calibration image open. Check the highlighted area before continuing.")

    def stop_refresh(self):
        process = self.process
        if not process:
            return
        if process.poll() is not None:
            self._finish_process(process, self.run_id)
            return
        if self.stopping:
            return
        self.stopping = True
        self._freeze_elapsed()
        self.status.set("Stopping")
        self.detail.set("Stopping the engine. A forced stop may not save a history entry.")
        self.progress_text.set("Stopping this session’s engine and calibration windows…")
        self.stop_button.configure(state=tk.DISABLED)
        self._event("Stop requested.")
        try:
            self.process_tree.stop(process) if self.process_tree else process.terminate()
        except OSError as exc:
            self._append_log(f"Stop failed: {exc}\n")
        self.after(2500, lambda: self._kill_if_needed(process))

    def _end_stopped_engine(self, process, run_id):
        if process is self.process and run_id == self.run_id and self.stop_key_pressed and process.poll() is None:
            self.stop_refresh()

    def _kill_if_needed(self, process):
        if process is self.process and process.poll() is None:
            try:
                self.process_tree.close() if self.process_tree else process.kill()
            except OSError as exc:
                self._append_log(f"Stop failed: {exc}\n")

    def _watch_process(self, process, run_id):
        if run_id != self.run_id:
            return
        if self.started_at:
            self.elapsed.set(duration_text(time.monotonic() - self.started_at))
        if process.poll() is None:
            if self.status.get() == "Starting" and time.monotonic() - self.launch_started_at > 30:
                self.detail.set("Startup is taking longer than expected. Check the emulator and Diagnostics.")
            self.after(500, lambda: self._watch_process(process, run_id))
            return
        if not self._exit_seen:
            self._exit_seen = True
            if self.process_tree:
                self.process_tree.close()
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
            self._handle_line(self.partial_line.strip())
            self.partial_line = ""
        self._finalized_run_id = self.run_id
        self._freeze_elapsed()
        if self.process_tree:
            self.process_tree.close()
        if self.stopping or self.stop_key_pressed or (process.returncode == 0 and self.run_settings and self.run_settings.debug and self._session_started and not self.finished):
            self.status.set("Stopped")
            self.detail.set("Session stopped. History contains only runs recorded by the engine.")
            self.progress_text.set("Stopped")
            self._play_session_sound("stopped")
        elif process.returncode == 0 and self.finished:
            self.status.set("Finished")
            self.detail.set("Session finished. Results are shown below.")
            self.progress_text.set("Session complete")
            self._play_session_sound("finished")
        else:
            self.status.set("Needs attention")
            self.detail.set(f"Engine exited (code {process.returncode}). Check Diagnostics before retrying.")
            self.progress_text.set("Engine exited")
        self._event(self.detail.get())
        self._set_controls(False)
        self.refresh_history()

    def _set_controls(self, running):
        for widget in self.settings_widgets:
            widget.state(["disabled"] if running else ["!disabled"])
        self.start_button.configure(state=tk.DISABLED if running else tk.NORMAL)
        self.stop_button.configure(state=tk.NORMAL if running else tk.DISABLED)

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
                output.append(value)
                if sum(map(len, output)) >= 16384:
                    break
                continue
            if output:
                self._handle_output(''.join(output))
                output.clear()
            if kind == "eof":
                self._finish_process()
            elif kind == "started":
                self._engine_started()
            elif kind == "io_error":
                self._append_log(f"\nEngine I/O ended: {value}\n")
            elif kind == "devices":
                devices, note, raw = value
                self._apply_devices(devices, note, raw)
        if output:
            self._handle_output(''.join(output))
        self.after(100, self._drain_log_queue)

    def _append_log(self, text):
        self.raw_output = (self.raw_output + text)[-150000:]
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
        item = self.activity.insert("", tk.END, values=(time.strftime("%H:%M:%S"), text))
        items = self.activity.get_children()
        if len(items) > 100:
            self.activity.delete(items[0])
        self.activity.see(item)

    def _copy_diagnostics(self):
        self.clipboard_clear()
        self.clipboard_append(f"Engine: {ENGINE_EXE}\nState: {self.status.get()}\n\n{self.raw_output}")

    def _update_history_xscroll(self, first, last):
        self.history_xscroll.set(first, last)
        if float(first) <= 0 and float(last) >= 1:
            self.history_xscroll.grid_remove()
        else:
            self.history_xscroll.grid()

    def refresh_history(self):
        try:
            if not HISTORY_FILE.exists():
                rows = []
                fieldnames = []
            else:
                with HISTORY_FILE.open(newline="", encoding="utf-8-sig") as fh:
                    reader = csv.DictReader(fh)
                    rows = list(reader)[-25:]
                    fieldnames = reader.fieldnames or []
        except (OSError, csv.Error, UnicodeError) as exc:
            self.history_notice.set("History could not be read. Check Diagnostics.")
            self._append_log(f"History read failed: {exc}\n")
            return
        self.history.delete(*self.history.get_children())
        for i, row in enumerate(reversed(rows)):
            mode = history_mode(row, fieldnames)
            tags = ('debug',) if mode == 'Debug' else ('even',) if i % 2 == 0 else ()
            self.history.insert("", tk.END, tags=tags, values=(mode, duration_text(row.get("Duration")), *(number_text(row.get(key)) for key in ("Skystone spent", "Gold spent", "Covenant bookmark", "Mystic medal"))))
        self.history_notice.set(f"{len(rows)} recent sessions · newest first · bookmark/medal columns count purchases" if rows else "No recorded sessions yet.")

    def _update_ev(self):
        try:
            budget = float(self.budget.get())
            if not math.isfinite(budget) or budget < 0:
                raise ValueError
            self.ev.set(f"Gold needed ≈ {int(budget * 1691.04536):,}\nCovenant buys ≈ {budget * 0.006602509:.1f}\nMystic buys ≈ {budget * 0.001700646:.1f}")
        except (ValueError, OverflowError):
            self.ev.set("Enter a valid budget to see the estimate.")

    def _close(self):
        if self.process and self.process.poll() is None:
            if not messagebox.askyesno("Stop and close?", "A refresh session is active. Stop it and close the app? The engine may not record an interrupted session.", parent=self):
                return
            self.stop_refresh()
            self.after(100, self._close_when_stopped)
        else:
            self.destroy()

    def _close_when_stopped(self):
        if self.process and self.process.poll() is None:
            self.after(100, self._close_when_stopped)
        else:
            self.destroy()

    def destroy(self):
        if self.process_tree:
            self.process_tree.close()
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
    parser = argparse.ArgumentParser(description="E7 Secret Shop Refresh GUI")
    parser.add_argument("--engine-dir", metavar="FOLDER", help="installed ADB engine folder")
    args = parser.parse_args(argv)
    try:
        configure_engine_directory(resolve_engine_directory(args.engine_dir))
    except ValueError as error:
        # Windowed Python launchers have no stderr; keep their errors visible.
        if sys.stderr is None:
            root = tk.Tk()
            root.withdraw()
            try:
                messagebox.showerror("Engine folder unavailable", str(error), parent=root)
            finally:
                root.destroy()
            return 2
        parser.error(str(error))
    RefreshGui().mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
