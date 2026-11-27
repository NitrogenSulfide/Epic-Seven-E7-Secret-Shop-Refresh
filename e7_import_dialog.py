"""The "found your old settings, import?" dialog.

Thin on purpose: the search, the decision to ask and the import itself are
plain functions in e7_user_data. This window only shows what was found and
returns the player's choice in `choice`:

* ('import', OlderInstall)  import from that install
* ('fresh', None)           start with default settings (startup only)
* None                      closed or cancelled (at startup the caller treats this as Start fresh)
"""
import datetime
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from e7_user_data import describe_install
from e7_i18n import t

LIST_WIDTH_LIMIT = 110  # characters; longer paths are cut in the middle, not the dialog widened


def _when(install):
    try:
        if install.last_used:
            return datetime.datetime.fromtimestamp(install.last_used).strftime('%Y-%m-%d %H:%M')
    except (OSError, OverflowError, ValueError):  # a 1970 or far-future time from an unzip tool
        pass
    return t('import_settings.date_unknown')


def _shorten(text, limit=LIST_WIDTH_LIMIT):
    if len(text) <= limit:
        return text
    keep = (limit - 1) // 2
    return f'{text[:keep]}…{text[-(limit - 1 - keep):]}'


def describe(installs):
    """The question for these search results (kept apart from Tk for tests)."""
    if not installs:
        return (t('import_settings.none_found'),
                t('import_settings.choose_folder_hint'))
    if len(installs) == 1:
        install = installs[0]
        return (t('import_settings.one_found', name=install.name, location=install.location),
                t('import_settings.last_used', date=_when(install)))
    return (t('import_settings.several_found', count=len(installs)),
            t('import_settings.most_recent_selected'))


class ImportDialog(tk.Toplevel):
    def __init__(self, master, installs, *, startup=True, scale=None):
        super().__init__(master)
        self.installs = list(installs)
        self.choice = None
        ratio = self.winfo_fpixels('1i') / 96.0
        dp = scale or (lambda value: max(1, round(value * ratio)))
        self.withdraw()  # shown once laid out and centred: no flicker in a corner
        self.title(t('import_settings.title'))
        self.resizable(False, False)
        if master.winfo_viewable():
            self.transient(master)
        body = ttk.Frame(self, padding=dp(18))
        body.grid(sticky='nsew')
        question, detail = describe(self.installs)
        ttk.Label(body, text=question, wraplength=dp(540), font=('Segoe UI', 11, 'bold')).grid(
            row=0, column=0, sticky='w')
        ttk.Label(body, text=detail, wraplength=dp(540)).grid(row=1, column=0, sticky='w', pady=(dp(6), 0))
        self.listbox = None
        if len(self.installs) > 1:
            lines = [
                _shorten(t('import_settings.install_row', name=install.name,
                           location=install.location, date=_when(install)))
                for install in self.installs
            ]
            self.listbox = tk.Listbox(body, height=min(len(lines), 6), width=max(60, max(map(len, lines)) + 2),
                                      activestyle='none', exportselection=False)
            for line in lines:
                self.listbox.insert('end', line)
            self.listbox.selection_set(0)  # newest first
            self.listbox.grid(row=2, column=0, sticky='ew', pady=(dp(10), 0))
            self.listbox.bind('<Double-Button-1>', lambda _event: self._import())
        buttons = ttk.Frame(body)
        buttons.grid(row=3, column=0, sticky='e', pady=(dp(16), 0))
        column = 0
        if self.installs:
            self.import_button = ttk.Button(buttons, text=t('import_settings.import'), command=self._import, default='active')
            self.import_button.grid(row=0, column=column, padx=(0, dp(6)))
            column += 1
            self.bind('<Return>', self._on_return)
        ttk.Button(buttons, text=t('import_settings.choose_another_folder'), command=self._choose).grid(
            row=0, column=column, padx=(0, dp(6)))
        closing = (t('import_settings.start_fresh'), self._fresh) if startup else (t('common.cancel'), self.destroy)
        ttk.Button(buttons, text=closing[0], command=closing[1]).grid(row=0, column=column + 1)
        self.bind('<Escape>', lambda _event: self.destroy())
        self.protocol('WM_DELETE_WINDOW', self.destroy)
        self.update_idletasks()
        self._center(master)
        self.deiconify()
        try:
            if self.tk.call('tk', 'windowingsystem') == 'x11':
                self.wait_visibility()  # X11 maps windows asynchronously; a grab needs a viewable window
            self.grab_set()  # modal: the main window waits for the answer
        except tk.TclError:
            pass  # still usable without the grab
        self.focus_set()

    def _on_return(self, event):
        """Enter presses the focused button; elsewhere it means Import."""
        if isinstance(event.widget, ttk.Button):
            event.widget.invoke()
        else:
            self._import()

    def _center(self, master):
        if master.winfo_viewable():
            x = master.winfo_rootx() + (master.winfo_width() - self.winfo_reqwidth()) // 2
            y = master.winfo_rooty() + (master.winfo_height() - self.winfo_reqheight()) // 3
        else:
            x = (self.winfo_screenwidth() - self.winfo_reqwidth()) // 2
            y = (self.winfo_screenheight() - self.winfo_reqheight()) // 3
        self.geometry(f'+{max(x, 0)}+{max(y, 0)}')

    def selected(self):
        if not self.installs:
            return None
        if self.listbox is None:
            return self.installs[0]
        chosen = self.listbox.curselection()
        return self.installs[chosen[0]] if chosen else None

    def _import(self):
        install = self.selected()
        if install is not None:
            self.choice = ('import', install)
            self.destroy()

    def _fresh(self):
        self.choice = ('fresh', None)
        self.destroy()

    def _choose(self):
        folder = filedialog.askdirectory(parent=self, title=t('import_settings.choose_folder'), mustexist=True)
        if not folder:
            return
        install = describe_install(folder, require_gui_settings=False)
        if install is None:
            messagebox.showwarning(t('import_settings.title'), t('import_settings.no_data_found', folder=folder),
                                   parent=self)
            return
        self.choice = ('import', install)
        self.destroy()
