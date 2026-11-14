"""Compact tracker: the main window shrinks to a short, always-on-top bar
while a refresh session runs, then returns to its full size and position.

The bar reuses the main window rather than opening a new one, so showing it
never takes keyboard focus away from the game (Mouse mode pauses when the
game loses focus). It only shows existing Tk variables, so it adds no work
per refresh.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from e7_appearance import ThemeHint, currency_icons

# Statuses that end compact view: the session is stopping, has ended or
# needs the user. Paused and Waiting for game stay compact and show on the bar.
RESTORE_STATUSES = frozenset({'Stopping', 'Stopped', 'Finished', 'Needs attention', 'Failed'})


def short_remaining(text):
    value = text.removeprefix('Time remaining: ')
    return f'{value[1:]} left' if value.startswith('~') else value


class CompactTracker:
    def __init__(self, root, assets, full_widgets):
        self.root = root
        self.full_widgets = full_widgets
        self.active = False
        self._saved = None
        dp = root._dp
        self.frame = frame = ttk.Frame(root, padding=(dp(12), dp(8)))
        self.icons = currency_icons(root, assets, dp(22))
        column = 0
        status = ttk.Label(frame, textvariable=root.status, style='Status.TLabel', font=root.heading_font, width=10)
        status.grid(row=0, column=column, sticky='w', padx=(0, dp(10)))
        column += 1
        self.counters = {}
        for key, var, text in (('covenant', root.covenant, 'Covenant'), ('mystic', root.mystic, 'Mystic'),
                               ('friendship', root.friendship, 'Friendship'), ('spent', root.spent_display, 'Skystones')):
            cell = ttk.Frame(frame)
            cell.grid(row=0, column=column, sticky='w', padx=(0, dp(14)))
            if key in self.icons:
                ttk.Label(cell, image=self.icons[key]).pack(side='left', padx=(0, dp(5)))
            else:
                ttk.Label(cell, text=f'{text}', style='Muted.TLabel').pack(side='left', padx=(0, dp(5)))
            ttk.Label(cell, textvariable=var, font=root.heading_font).pack(side='left')
            self.counters[key] = cell
            column += 1
        # "Time remaining: ~4m 10s" becomes "~4m 10s left" to keep the bar short.
        self.remaining = tk.StringVar(value='')
        root.remaining_time.trace_add('write', lambda *_: self.remaining.set(short_remaining(root.remaining_time.get())))
        ttk.Label(frame, textvariable=self.remaining, style='Muted.TLabel').grid(row=0, column=column, sticky='w', padx=(0, dp(14)))
        frame.columnconfigure(column, weight=1)
        column += 1
        self.stop_button = ttk.Button(frame, text='Stop', command=root.stop_refresh, padding=(dp(10), dp(4)))
        self.stop_button.grid(row=0, column=column, sticky='e', padx=(0, dp(6)))
        column += 1
        self.expand_button = ttk.Button(frame, text='⤢', width=3, command=self.restore, padding=(dp(6), dp(4)))
        self.expand_button.grid(row=0, column=column, sticky='e')
        ThemeHint(self.expand_button, lambda: 'Show the full window')
        # Red line under the bar while the pointer pauses a Background run.
        self.alert = ttk.Label(frame, textvariable=root.pointer_alert, style='Alert.TLabel', font=root.heading_font)
        self.alert.grid(row=1, column=0, columnspan=column+1, sticky='w', pady=(dp(4), 0))
        self.alert.grid_remove()
        root.pointer_alert.trace_add('write', lambda *_: self.alert.grid() if root.pointer_alert.get() else self.alert.grid_remove())
        # Muted line: what is happening and what the player can do about it.
        self.hint = ttk.Label(frame, textvariable=root.compact_hint, style='Muted.TLabel', wraplength=dp(660), justify='left')
        self.hint.grid(row=2, column=0, columnspan=column+1, sticky='w', pady=(dp(2), 0))
        self.hint.grid_remove()
        root.compact_hint.trace_add('write', lambda *_: self.hint.grid() if root.compact_hint.get() else self.hint.grid_remove())

    def enter(self, *, friendship):
        root = self.root
        if self.active:
            return
        # A minimized or hidden window stays as the user left it.
        if not root.winfo_viewable() or root.state() not in ('normal', 'zoomed'):
            return
        zoomed = root.state() == 'zoomed'
        if zoomed:
            root.state('normal')
        geometry = root.geometry()
        position = geometry[geometry.index('+'):] if '+' in geometry else ''
        self._saved = {'geometry': geometry, 'zoomed': zoomed, 'minsize': root.minsize(), 'position': position}
        self.active = True
        if friendship:
            self.counters['friendship'].grid()
        else:
            self.counters['friendship'].grid_remove()
        for widget in self.full_widgets:
            widget.grid_remove()
        root.rowconfigure(0, weight=1)
        self.frame.grid(row=0, column=0, sticky='nsew')
        self.remaining.set(short_remaining(root.remaining_time.get()))
        root.minsize(1, 1)
        root.resizable(False, False)
        # An empty geometry lets the bar follow its content, so growing counts
        # never push the Stop button out of view.
        root.geometry('')
        root.geometry(self._saved['position'])
        root.attributes('-topmost', True)

    def restore(self):
        root = self.root
        if not self.active:
            return
        self.active = False
        saved = self._saved
        root.attributes('-topmost', False)
        self.frame.grid_remove()
        root.rowconfigure(0, weight=0)
        for widget in self.full_widgets:
            widget.grid()
        root.resizable(True, True)
        root.minsize(*saved['minsize'])
        root.geometry(saved['geometry'])
        if saved['zoomed']:
            root.state('zoomed')
        if hasattr(root, 'scenery'):
            root.scenery.schedule()
        root._schedule_layout()

    def status_changed(self):
        if self.active and self.root.status.get() in RESTORE_STATUSES:
            self.restore()
