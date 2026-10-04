"""One-time, user-directed read-only recognition setup. Never sends game taps."""
import io
import hashlib
from pathlib import Path
import queue
import subprocess
import threading
import tkinter as tk
from tkinter import ttk
import uuid
from e7_appearance import Image

REFERENCE_NAMES = ('menu-secret-shop.png', 'shop-title.png', 'refresh-label.png')
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def verify_setup_engine(engine):
    engine = Path(engine)
    receipt = engine.with_suffix('.sha256')
    if not receipt.is_file():
        raise ValueError('Use the matching bundled engine for recognition setup. This older installation has no setup-engine receipt.')
    with engine.open('rb') as stream:
        actual = hashlib.file_digest(stream, 'sha256').hexdigest()
    if receipt.read_text(encoding='utf-8-sig').strip().lower() != actual:
        raise ValueError('The setup engine does not match this package. Extract a fresh player ZIP.')


def missing_references(runtime):
    folder = Path(runtime) / 'adb-assets/gui-navigation'
    return [name for name in REFERENCE_NAMES if not (folder/name).is_file() or (folder/name).stat().st_size == 0]


def has_builtin_references(runtime):
    folder = Path(runtime)/'adb-assets/builtin-navigation'
    return all((folder/name).is_file() and (folder/name).stat().st_size > 0 for name in REFERENCE_NAMES)


def capture_frame(adb, device, destination, runner=subprocess.run):
    if Image is None:
        raise RuntimeError('Use the included app EXE for image support, or install Pillow for a source launch.')
    result = runner([str(adb), '-s', device, 'exec-out', 'screencap', '-p'],
                    capture_output=True, timeout=25, creationflags=NO_WINDOW)
    if result.returncode:
        raise RuntimeError('Screenshot failed. Check that the selected emulator is connected and authorized.')
    with Image.open(io.BytesIO(result.stdout)) as frame:
        if frame.format != 'PNG' or frame.width<640 or frame.height<360 or abs(frame.width/frame.height-16/9)>.035:
            raise ValueError('Use a landscape 16:9 Android display of at least 640 × 360.')
        frame.verify()
    Path(destination).write_bytes(result.stdout)


def prepare_captured_references(engine, runtime, captures, runner=subprocess.run):
    verify_setup_engine(engine)
    runtime, captures = Path(runtime).resolve(), Path(captures).resolve()
    if not captures.is_relative_to(runtime):
        raise ValueError('Setup captures must remain in the selected private runtime.')
    prepared = captures / ('references-' + uuid.uuid4().hex)
    result = runner([str(engine), '--prepare-navigation-references', '--home', str(captures/'home.png'),
                     '--shop', str(captures/'shop.png'), '--output', str(prepared)],
                    capture_output=True, text=True, timeout=60, creationflags=NO_WINDOW)
    if result.returncode:
        raise RuntimeError('The screenshots did not pass recognition checks. Capture the visible English home menu and normal Secret Shop list again.')
    if any(not (prepared/name).is_file() for name in REFERENCE_NAMES):
        raise RuntimeError('The engine did not produce all three recognition images.')
    target = runtime / 'adb-assets/gui-navigation'
    if not target.parent.resolve().is_relative_to(runtime):
        raise ValueError('The reference folder must remain in the selected runtime.')
    backup = None
    if target.exists():
        backup = target.with_name('gui-navigation-backup-' + uuid.uuid4().hex)
        target.rename(backup)
    try:
        prepared.rename(target)
    except OSError:
        if backup is not None:
            backup.rename(target)
        raise


class RecognitionSetup(tk.Toplevel):
    def __init__(self, app, runtime, adb, engine, device):
        verify_setup_engine(engine)
        super().__init__(app)
        self.app, self.runtime, self.adb, self.engine, self.device = app, Path(runtime), adb, engine, device
        self.title('Help recognize Secret Shop')
        self.transient(app)
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.jobs = queue.Queue()
        self.closed = self.busy = False
        self.poll_job = None
        self.captures = self.runtime / 'setup-captures' / uuid.uuid4().hex
        self.captures.mkdir(parents=True)
        dark = app.dark_mode.get()
        bg, fg = ('#111827', '#e2e8f0') if dark else ('#f3f5f8', '#1e293b')
        self.configure(bg=bg)
        self.columnconfigure(0, weight=1)
        dp = app._dp
        tk.Label(self, text='Help recognize your shop', bg=bg, fg=fg,
                 font=app.heading_font, anchor='w').grid(row=0,column=0,sticky='ew',padx=dp(20),pady=(dp(20),dp(12)))
        tk.Label(self, text='Use this helper when automatic recognition needs help.\n'
                 'These buttons only read screenshots. They do not tap, buy or refresh.\n'
                 'Use English Epic Seven with a landscape 16:9 Android display of at least 640 × 360.\n\n'
                 '1. Open the game’s home screen. Click the game once if its UI is hidden.\n'
                 '2. Capture the visible home menu below.\n'
                 '3. Open Secret Shop yourself, then capture its normal item list.',
                 bg=bg,fg=fg,font=app.ui_font,anchor='w',justify='left',wraplength=dp(610)
                 ).grid(row=1,column=0,sticky='ew',padx=dp(20))
        buttons = ttk.Frame(self)
        buttons.grid(row=2,column=0,sticky='ew',padx=dp(20),pady=dp(16))
        self.home_button = ttk.Button(buttons,text='Capture home menu',command=lambda:self.capture('home'))
        self.home_button.pack(side='left',padx=(0,dp(10)))
        self.shop_button = ttk.Button(buttons,text='Capture shop & finish',command=lambda:self.capture('shop'),state='disabled')
        self.shop_button.pack(side='left')
        self.notice = tk.StringVar(value='Ready to capture the home menu. Screenshots stay private in this runtime.')
        tk.Label(self,textvariable=self.notice,bg=bg,fg='#fbbf24' if dark else '#92400e',font=app.ui_font,
                 justify='left',anchor='w',wraplength=dp(610)
                 ).grid(row=3,column=0,sticky='ew',padx=dp(20),pady=(0,dp(16)))
        ttk.Button(self,text='Close',command=self.close).grid(row=4,column=0,sticky='e',padx=dp(20),pady=(0,dp(20)))
        self.resizable(False, False)

    def capture(self, name):
        if self.busy:
            return
        self.busy = True
        self.home_button.configure(state='disabled'); self.shop_button.configure(state='disabled')
        self.notice.set('Reading a screenshot…' if name == 'home' else 'Reading the shop and checking recognition…')
        def work():
            try:
                capture_frame(self.adb,self.device,self.captures/f'{name}.png')
                if name == 'shop':
                    prepare_captured_references(self.engine,self.runtime,self.captures)
                self.jobs.put((name,None))
            except Exception as error:
                self.jobs.put((name,str(error)))
        threading.Thread(target=work,daemon=True).start()
        self.poll_job = self.after(100,self.poll)

    def poll(self):
        self.poll_job = None
        try:
            name,error = self.jobs.get_nowait()
        except queue.Empty:
            self.poll_job = self.after(100,self.poll)
            return
        self.busy = False
        self.home_button.configure(state='normal')
        self.shop_button.configure(state='normal' if (self.captures/'home.png').is_file() else 'disabled')
        if error:
            self.notice.set(error)
        elif name == 'home':
            self.notice.set('Home captured. Open Secret Shop yourself, then choose Capture shop & finish.')
        else:
            self.notice.set('Recognition is ready. Close this window, check your budget, then press Start refresh.')
            self.app.status.set('Ready')
            self.app.detail.set('Recognition prepared. Check your budget and stop key before starting.')
            self.app._event('Recognition setup completed. No game taps or spending performed.')

    def close(self):
        if self.busy:
            self.notice.set('Please wait for this read-only capture/check to finish before closing.')
            return
        self.closed = True
        if self.poll_job is not None:
            self.after_cancel(self.poll_job)
        self.app.setup_window = None
        self.destroy()
