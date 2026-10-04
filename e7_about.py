"""Local welcome, attribution and licence view; links open only on user clicks."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk
import webbrowser
from e7_appearance import profile_avatar, github_icon, ThemeHint

TESTED_CLIENTS = (
    'First release testing: Google Play Games on PC Developer Emulator and the '
    'official STOVE client of Epic Seven. Other emulators and methods have not '
    'been tested.'
)
QUICKSTART = (
    'Mouse mode\n\n'
    '1. Open English Epic Seven at home or in Secret Shop. Close popups.\n'
    '2. Mouse is selected by default. Select your game window; use Scan if needed.\n'
    '3. Press Start Refresh. The app opens the shop if needed. Leave the PC '
    'alone; keep the game visible and its window still.\n\n'
    'ADB mode\n\n'
    '1. Enable/authorize emulator ADB debugging. Use English Epic Seven and a '
    'landscape 16:9 game view of at least 640 × 360.\n'
    '2. Choose ADB → select your device. Google Developer Emulator: '
    'localhost:6520. Use Scan if needed.\n'
    '3. Start from home or Secret Shop. The app reveals idle home controls and opens the shop. '
    'You can use your PC mouse while ADB runs.\n\n'
    'Before Start: check budget, delay and stop key. Keep calibration off for '
    'ordinary sessions. Both modes buy only Covenant Bookmarks and Mystic Medals.\n'
    'To stop: press your stop key or use Stop Session.\n\n'
    'Mouse: resize before Start; game view must be at least 640 × 360. If the '
    'game runs as administrator, Start offers to restart the app with Windows\' '
    'permission prompt. After reopening, select the game and press Start again. '
    'Cancelling leaves this app open without sending Mouse input.\n\n'
    + TESTED_CLIENTS
)


class AboutDialog(tk.Toplevel):
    def __init__(self, app, project, first_time=False):
        super().__init__(app)
        self.app = app
        self.app_asset_dir = project/'e7_gui_assets'
        self.title('Welcome · About & Credits' if first_time else 'About & Credits')
        self.transient(app)
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.bind('<Escape>', lambda _: self.close())
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self.colored = []
        self.readers = []
        dp = app._dp
        header = tk.Frame(self, padx=dp(20), pady=dp(16))
        header.grid(row=0, column=0, sticky='ew')
        self.colored.append(header)
        self.avatar_image = profile_avatar(self,project/'e7_gui_assets',dp(72))
        text_column = 1 if self.avatar_image else 0
        header.columnconfigure(text_column,weight=1)
        if self.avatar_image:
            avatar = tk.Label(header,image=self.avatar_image,borderwidth=0)
            avatar.grid(row=0,column=0,rowspan=3,padx=(0,dp(16)),sticky='n')
            self.colored.append(avatar)
        for row, (text, font) in enumerate((('E7 Secret Shop Refresh', ('Segoe UI',18,'bold')),
                           ('by NitrogenSulfide (Blue Natto)', app.heading_font),
                           (f'{read_document(project / "VERSION").strip()} · Windows', app.ui_font))):
            label = tk.Label(header, text=text, font=font, anchor='w')
            label.grid(row=row,column=text_column,sticky='ew',pady=(0,dp(3)))
            self.colored.append(label)
        notebook = ttk.Notebook(self)
        notebook.grid(row=1, column=0, sticky='nsew', padx=dp(20))
        self.notebook = notebook
        overview = (
            'Welcome! Choose Mouse or ADB, then check the budget and stop key. '
            'See Quickstart for the basic steps.\n\n'
            f'{TESTED_CLIENTS}\n\n'
            'GUI and enhancements: NitrogenSulfide (Blue Natto)\n'
            'Original refresh engine: Solunium\n'
            'Epic Seven artwork: Smilegate and respective rights holders\n'
            'Start/end sounds: Robin Lamb · CC0\n\n'
            'Software licence: GNU GPL-3.0\n'
            'Independent community tool.'
        )
        for title, contents in (('Overview',overview),
                                ('Quickstart',QUICKSTART),
                                ('Release notes',read_document(project/'CHANGELOG.txt')),
                                ('Full credits',read_document(project/'CREDITS.txt')),
                                ('Licence',read_document(project/'LICENSE'))):
            panel = ttk.Frame(notebook, padding=dp(8))
            panel.columnconfigure(0, weight=1)
            panel.rowconfigure(0, weight=1)
            reader = tk.Text(panel, wrap='word', font=app.ui_font,
                             relief='flat', borderwidth=0, padx=dp(8), pady=dp(8),
                             width=40, height=8, takefocus=True)
            reader.grid(row=0,column=0,sticky='nsew')
            scrollbar = ttk.Scrollbar(panel,command=reader.yview)
            scrollbar.grid(row=0,column=1,sticky='ns')
            reader.configure(yscrollcommand=scrollbar.set)
            reader.insert('1.0',contents)
            reader.configure(state='disabled')
            self.readers.append(reader)
            notebook.add(panel,text=title)
        footer = ttk.Frame(self,padding=dp(20))
        footer.grid(row=2,column=0,sticky='ew')
        footer.columnconfigure(0,weight=1)
        self.startup_check = ttk.Checkbutton(footer,text='Show this on startup',
                                             variable=app.credits_on_startup,
                                             command=app._save_credits_preference,
                                             style='Large.TCheckbutton')
        self.startup_check.grid(row=0,column=0,columnspan=3,sticky='w',pady=(0,dp(8)))
        links = ttk.Frame(footer)
        links.grid(row=1,column=0,sticky='w')
        self.github_button = ttk.Button(links, text='', padding=dp(8), cursor='hand2', takefocus=True,
            command=lambda: webbrowser.open('https://github.com/NitrogenSulfide'))
        self.github_button.pack(side='left',padx=(0,dp(8)))
        self.github_hint = ThemeHint(self.github_button, lambda: 'GitHub profile · NitrogenSulfide')
        ttk.Button(links,text='Upstream project',command=lambda: webbrowser.open('https://github.com/Solunium/Epic-Seven-E7-Secret-Shop-Refresh')).pack(side='left')
        self.continue_button = ttk.Button(footer,text='Continue' if first_time else 'Close',command=self.close,style='Accent.TButton')
        self.continue_button.grid(row=1,column=2,sticky='e',padx=(dp(8),0))
        self.apply_theme(app.dark_mode.get())
        left,top,width,height = app._screen_work_area()
        w,h = min(dp(700),width-dp(48)),min(dp(720),height-dp(48))
        self.minsize(min(dp(600),w),min(dp(420),h))
        x = max(left,min(app.winfo_rootx()+(app.winfo_width()-w)//2,left+width-w))
        y = max(top,min(app.winfo_rooty()+(app.winfo_height()-h)//2,top+height-h))
        self.geometry(f'{w}x{h}+{x}+{y}')

    def apply_theme(self,dark):
        self.github_image = github_icon(self, self.app_asset_dir, self.app._dp(24), dark)
        self.github_button.configure(image=self.github_image or '', text='' if self.github_image else 'GitHub')
        bg,field,fg = ('#111827','#1e293b','#e2e8f0') if dark else ('#f3f5f8','#ffffff','#1e293b')
        self.configure(bg=bg)
        for widget in self.colored:
            widget.configure(bg=bg)
            if isinstance(widget,tk.Label):
                widget.configure(fg=fg)
        for reader in self.readers:
            reader.configure(bg=field,fg=fg,insertbackground=fg,selectbackground='#2563eb',selectforeground='white')

    def close(self):
        self.github_hint.hide()
        self.app.credits_seen.set(True)
        self.app._save_credits_preference()
        self.app.about_window = None
        self.destroy()


def read_document(path: Path):
    try:
        return path.read_text(encoding='utf-8-sig')
    except (OSError,UnicodeError):
        return f'{path.name} is unavailable in this installation.'
