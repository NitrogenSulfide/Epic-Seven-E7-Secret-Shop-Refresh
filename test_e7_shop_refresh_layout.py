import json
import sys
from pathlib import Path
import tempfile
import time
from unittest.mock import patch

import e7_shop_refresh_gui as gui

MATRIX = [(1920, 1080, 1), (1920, 1080, 1.25), (1920, 1080, 1.5), (1920, 1080, 2), (2560, 1440, 1), (2560, 1440, 1.5), (2560, 1440, 2), (3840, 2160, 1.5), (3840, 2160, 2), (3840, 2160, 2.5), (3840, 2160, 3)]
results = []
def settle(app):
    # Let the existing 35ms layout and 140ms scenery debounce timers run.
    deadline = time.monotonic() + .35
    while time.monotonic() < deadline:
        app.update()
        time.sleep(.01)
with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    history = root / "history.csv"
    history.write_text("Duration,Skystone spent,Gold spent,Covenant bookmark,Mystic medal\n5536.52,2799,7656000,34,5\n" * 1)
    for width, height, scale in MATRIX:
        def scaling(app):
            app.tk.call('tk', 'scaling', scale * 96 / 72)
            app.ui_scale = scale
        with patch.object(gui.RefreshGui, '_maybe_show_credits', lambda _: None), patch.object(gui.RefreshGui, '_configure_scaling', scaling), patch.object(gui.RefreshGui, '_screen_work_area', lambda _: (0, 0, width, height-48)), patch.object(gui.RefreshGui, 'refresh_devices', lambda _: None), patch.object(gui, 'CONFIG_FILE', root / 'config.ini'), patch.object(gui, 'GUI_CONFIG_FILE', root / 'gui.ini'), patch.object(gui, 'HISTORY_FILE', history):
            app = gui.RefreshGui()
        app._apply_devices(['localhost:6520'], 'Connected.', '')
        app._event('Engine ready. Refreshing started.')
        app.elapsed.set('12h 59m 59s')
        settle(app)
        if app.compact_history:
            app.notebook.select(app.history_tab)
            settle(app)
        problems = []
        for widget in (app.random_check, app.debug_check, app.tap_timing_hint):
            if widget.winfo_reqwidth() > app.settings_controls.winfo_width():
                problems.append('randomization/debug settings clipped')
        if app.device_button.winfo_width() < app.ui_font.measure('Scan') + app._dp(32):
            problems.append('Scan too narrow')
        device_gap = app.device_button.winfo_rootx() - (app.device_box.winfo_rootx() + app.device_box.winfo_width())
        if device_gap < app._dp(10):
            problems.append('Scan gap too narrow')
        if app.settings_controls.winfo_reqheight() <= app.settings_canvas.winfo_height() + app._dp(2) and app.settings_scroll.winfo_ismapped():
            problems.append('unnecessary settings scrollbar')
        if app.device_box.winfo_width() < app.ui_font.measure('localhost:6520 (default)') + app._dp(32):
            problems.append('device too narrow')
        if app.sound_button.winfo_reqwidth() > app.settings_canvas.winfo_width() - app._dp(10):
            problems.append('sound checkbox clipped')
        if app.stop_button.winfo_rooty() + app.stop_button.winfo_height() > app.winfo_rooty() + app.winfo_height() - app._dp(8):
            problems.append('stop button below window')
        if app.activity.column('time', 'width') < app.ui_font.measure('23:59:59') + app._dp(16):
            problems.append('timestamp clipped')
        if app.table_rowheight < app.ui_font.metrics('linespace') + app._dp(8):
            problems.append('text clipped vertically')
        for card in app.metric_cards:
            if card.winfo_width() < card.winfo_reqwidth():
                problems.append('metric card clipped')
        if app.history_label.winfo_rooty() + app.history_label.winfo_height() > app.winfo_rooty() + app.winfo_height() - app._dp(8):
            problems.append('history footer below window')
        if app.history.winfo_height() < app.table_rowheight * 2:
            problems.append('history viewport too short')
        first, last = app.history.xview()
        overflow = first > 0 or last < 1
        if bool(app.history_xscroll.winfo_ismapped()) != overflow:
            problems.append('history horizontal scrollbar does not match overflow')
        result = dict(resolution=f'{width}x{height}', scale=scale, window=app.winfo_geometry(), sidebar=app.settings_canvas.winfo_width(), device_width=app.device_box.winfo_width(), rowheight=app.table_rowheight, font_height=app.ui_font.metrics('linespace'), compact_history=app.compact_history, activity_height=app.activity.winfo_height(), history_height=app.history.winfo_height(), problems=problems)
        result['settings_scrollbar'] = bool(app.settings_scroll.winfo_ismapped())
        results.append(result)
        print(json.dumps(result), flush=True)
        app.destroy()
if len(sys.argv) > 1:
    Path(sys.argv[1]).write_text(json.dumps(results, indent=2))
if any(r['problems'] for r in results):
    raise SystemExit(1)
