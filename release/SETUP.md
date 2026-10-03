# Set up E7 Shop Refresh — NitrogenSulfide (Blue Natto)

This is a Windows GUI for Solunium's ADB refresh engine. Setup requires
Python and locally prepared recognition images. It is not a one-click installer.
Use Google Play Games on PC **Developer Emulator**, English Epic Seven and a
1920 x 1080 Android display. Native STOVE is unsupported; other emulators are
unverified. Different home-screen artwork is fine: recognition uses UI text.

## Download and extract

Download **E7ShopRefresh-0.1.0-rc17.zip** and extract the whole ZIP into a new
folder such as `Documents\E7 Shop Refresh`. Players need only this download.
The separate **E7Source** ZIP is for developers and is not needed to run the app.
Check the player ZIP against the release's `SHA256SUMS.txt` if desired:

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath '.\E7ShopRefresh-0.1.0-rc17.zip'
```

The GUI, engine, ADB tools and item templates are already arranged together.
`engine-location.ini` points to the included `runtime` folder using a relative
path, so you do not need to copy files or edit an installation path. Keep the
whole extracted folder together. Use a new folder when trying a candidate;
do not overwrite an existing app or copy personal settings yet.

Install Python **3.13** from [Python's Windows downloads](https://www.python.org/downloads/windows/)
if needed, including Tcl/Tk. For the EXE shortcut, use the Python 3.13 full
installer with its **legacy Windows launcher** option. The checks used Python
3.13.5. The compiled engine includes its Python; the GUI still needs it.
To enable the backgrounds, avatar and counter artwork, run this optional step:

```powershell
py -3.13 -m pip install --user "Pillow==11.3.0"
```

This installs Pillow into your user Python environment. If you skip it, the
app uses a plain light/dark appearance. We do not run this installation for you.

```text
E7 Shop Refresh/
  E7 Secret Shop Refresh.exe          (GUI launcher)
  e7_shop_refresh_gui.py              (GUI source)
  engine-location.ini                (already points to runtime)
  e7_gui_assets/
  START-HERE.md
  runtime/
    E7ADBShopRefresh.exe              (matching compiled engine)
    adb-assets/
      cov.png, mys.png, fb.png        (item templates)
      platform-tools/                (ADB tools and notices)
      gui-navigation/                (created in the next step)
```

## Prepare recognition once

Install/configure the [Google developer emulator](https://developer.android.com/games/playgames/emulator),
enable ADB debugging, and set its Android display to 1920 x 1080. The preserved
upstream instructions are background context; this beta uses the setup here.
Open Epic Seven and close news/dispatch/popups. If the home controls are hidden,
click once inside the game to reveal them.

The following commands read screenshots; they do not tap, refresh or purchase.
Run PowerShell **inside the extracted `runtime` folder**. Google's documented developer-emulator
endpoint is `localhost:6520`; see its [connection guide](https://developer.android.com/games/playgames/pg-emulator#installing-a-game).
Use that endpoint first, then the actual connected identifier shown by `devices`:

```powershell
.\adb-assets\platform-tools\adb.exe connect localhost:6520
.\adb-assets\platform-tools\adb.exe devices
```

If your emulator uses another port, replace `localhost:6520` below with the
connected device identifier shown by `devices`. Continue only when it is listed
as `device`, not `offline` or `unauthorized`.

While the **home menu** is visible:

```powershell
.\adb-assets\platform-tools\adb.exe -s localhost:6520 shell screencap -p /sdcard/e7-home.png
.\adb-assets\platform-tools\adb.exe -s localhost:6520 pull /sdcard/e7-home.png .\home.png
```

Open **Secret Shop manually**, then capture its normal list screen:

```powershell
.\adb-assets\platform-tools\adb.exe -s localhost:6520 shell screencap -p /sdcard/e7-shop.png
.\adb-assets\platform-tools\adb.exe -s localhost:6520 pull /sdcard/e7-shop.png .\shop.png
.\E7ADBShopRefresh.exe --prepare-navigation-references --home .\home.png --shop .\shop.png --output .\adb-assets\gui-navigation
```

The last command works offline. It crops just the menu/title/Refresh text and
checks those crops against the supplied images. It needs no separate Python.
Use raw game PNGs, with visible English controls and no desktop window borders.
Keep screenshots/references private. Existing reference directories are never
overwritten; if recalibrating, preserve the old directory under another name
before creating the replacement. A failed check means setup is incomplete.

## Open and try it

Double-click `E7 Secret Shop Refresh.exe` **in the extracted app folder**. Alternatively:

```powershell
py -3.13 .\e7_shop_refresh_gui.py
```

The EXE currently recognizes only the legacy launcher's standard installation
paths. With the newer Python install manager, use the command above or the
included `E7 Secret Shop Refresh GUI.cmd` instead; that CMD uses `pyw` on PATH.
The EXE/CMD select the latest installed Python. If several versions are installed,
use the `py -3.13` command above to match the documented Pillow installation.

Opening the GUI discovers ADB devices. Spending begins only after **Start
refresh**. Select the connected device (normally `localhost:6520` for Google's
developer emulator); do not retain an unrelated manual address. Leave
**Debug / calibration mode** unchecked for this normal test: it uses a separate
100-skystone budget after confirmation and is not the offline image-preparation
utility. Check the settings first. New normal defaults are a
12-skystone budget, 0.3-second delay, backtick stop key and randomized offsets.
Counters count Covenant/Mystic **buys**, not individual bookmarks/medals awarded.

For your first small supervised run, verify shop entry, a refresh/count update,
the Stop button and the selected stop key. Observe a Covenant/Mystic purchase
when one naturally appears. You do not need to empty your balances to test this
beta. Insufficient-currency stopping remains unverified. If the home UI fades,
click the game once or open the shop; the app waits up to 60 seconds without
guessing a navigation tap. Stop remains available.

## If something is missing

- **Nothing opens:** run the Python command above in PowerShell to see the error.
  Check `py -3.13 --version` and `py -3.13 -c "import tkinter"`.
- **Engine folder unavailable:** check the saved path and presence of both
  `E7ADBShopRefresh.exe` and `adb-assets\platform-tools\adb.exe`.
- **Navigation reference missing:** complete the screenshot preparation step.
- **Shop unverified:** check English UI, Android display size, visible controls
  and unobstructed title/Refresh button. Do not disable recognition to continue.
- **No scenery:** check `py -3.13 -c "import PIL; print(PIL.__version__)"`.

Settings and CSV history stay in the included `runtime` folder. Before updating,
stop/close the old app and preserve its runtime settings, history and locally
prepared references. Extract updates into a new folder; no updater or automatic
migration exists. Before deleting the extracted app folder, back up any settings
and history you want to keep.

## Credits and source

GUI/enhancements: NitrogenSulfide (Blue Natto). Original engine: Solunium,
GNU GPL-3.0. The player ZIP includes matching engine source/build instructions under
`runtime`, executable GUI source and original notices. The optional Source ZIP
contains the full tracked checkout, builders and tests. ADB notices remain in
`runtime/adb-assets/platform-tools/NOTICE.txt`.
Epic Seven artwork retains its own rights holders; the GPL does not relicense
it. Full GUI credits and licence are readable offline in About & Credits.
