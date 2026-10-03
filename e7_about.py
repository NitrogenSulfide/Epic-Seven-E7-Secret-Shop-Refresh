"""Local welcome, attribution and licence view; links open only on user clicks."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk
import webbrowser


class AboutDialog(tk.Toplevel):
    def __init__(self, app, project, first_time=False):
        super().__init__(app)
        self.app = app
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
        for text, font in (('E7 Secret Shop Refresh', ('Segoe UI',18,'bold')),
                           ('by Blue Natto', app.heading_font),
                           (f'{read_document(project / "VERSION").strip()} · Windows', app.ui_font)):
            label = tk.Label(header, text=text, font=font, anchor='w')
            label.pack(fill='x', pady=(0,dp(3)))
            self.colored.append(label)
        notebook = ttk.Notebook(self)
        notebook.grid(row=1, column=0, sticky='nsew', padx=dp(20))
        self.notebook = notebook
        overview = (
            'Welcome! Open Epic Seven’s Secret Shop, select your device, '
            'and check the budget and stop key before starting.\n\n'
            'GUI and enhancements: Blue Natto\n'
            'GitHub identity: NitrogenSulfide\n'
            'Original refresh engine: Solunium\n'
            'Epic Seven artwork: Smilegate and respective rights holders\n'
            'Start/end sounds: Robin Lamb · CC0\n\n'
            'Software licence: GNU GPL-3.0\n'
            'Independent community tool.'
        )
        for title, contents in (('Overview',overview),
                                ('Full credits',read_document(project/'CREDITS.txt')),
                                ('Software licence',read_document(project/'LICENSE'))):
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
        ttk.Button(links,text='GitHub profile',command=lambda: webbrowser.open('https://github.com/NitrogenSulfide')).pack(side='left',padx=(0,dp(8)))
        ttk.Button(links,text='Upstream project',command=lambda: webbrowser.open('https://github.com/Solunium/Epic-Seven-E7-Secret-Shop-Refresh')).pack(side='left')
        self.continue_button = ttk.Button(footer,text='Continue' if first_time else 'Close',command=self.close,style='Accent.TButton')
        self.continue_button.grid(row=1,column=2,sticky='e',padx=(dp(8),0))
        self.apply_theme(app.dark_mode.get())
        left,top,width,height = app._screen_work_area()
        w,h = min(dp(700),width-dp(48)),min(dp(650),height-dp(48))
        self.minsize(min(dp(600),w),min(dp(420),h))
        x = max(left,min(app.winfo_rootx()+(app.winfo_width()-w)//2,left+width-w))
        y = max(top,min(app.winfo_rooty()+(app.winfo_height()-h)//2,top+height-h))
        self.geometry(f'{w}x{h}+{x}+{y}')

    def apply_theme(self,dark):
        bg,field,fg = ('#111827','#1e293b','#e2e8f0') if dark else ('#f3f5f8','#ffffff','#1e293b')
        self.configure(bg=bg)
        for widget in self.colored:
            widget.configure(bg=bg)
            if isinstance(widget,tk.Label):
                widget.configure(fg=fg)
        for reader in self.readers:
            reader.configure(bg=field,fg=fg,insertbackground=fg,selectbackground='#2563eb',selectforeground='white')

    def close(self):
        self.app.credits_seen.set(True)
        self.app._save_credits_preference()
        self.app.about_window = None
        self.destroy()


def read_document(path: Path):
    try:
        return path.read_text(encoding='utf-8-sig')
    except (OSError,UnicodeError):
        return f'{path.name} is unavailable in this installation.'
