# E7 Secret Shop Refresh GUI

Windows GUI by NitrogenSulfide (Blue Natto) for Solunium's Epic Seven Secret Shop Refresh ADB
engine. This is version **0.1.0-rc17**, a local release candidate. It has not been
published or cleared for live-game use by the release workflow.

## Requirements

**Start with [START-HERE.md](START-HERE.md)** (also supplied as [SETUP.md](SETUP.md)).
Players need only **E7ShopRefresh-0.1.0-rc17.zip**. It includes the GUI, matching
compiled engine, ADB tools and item templates, with the engine path configured.
Recognition images must still be prepared locally from your game. The separate
Source ZIP is available for developers; it is not a player dependency.

- Windows with Python 3 and Tkinter, plus Python's Windows launcher (`py`/`pyw`).
  The EXE requires the legacy launcher's standard installation path. With the
  newer Python install manager, use the included CMD or Python command instead.
  Pillow 11.3 or newer enables the scenery and currency artwork. Without Pillow
  the GUI uses its plain light/dark palette. The prepared owner test launcher uses
  the existing private environment with Pillow; system Python is unchanged.
  Automated candidate checks use Python 3.13; other versions are not yet verified.
- The included `runtime` folder, containing the matching engine and ADB tools.
  Keep it beside the GUI; no separate engine download is needed.
- Google Play Games on PC Developer Emulator, with ADB debugging enabled,
  English game UI and a 1920 x 1080 Android display. Other emulators are unverified;
  the native STOVE client is not supported by this ADB version.

This package includes the GUI source, launcher, compiled engine and ADB tools.
Python and the emulator are external requirements. The GUI launcher does not
embed Python; the package does not install Python or configure the emulator.

## Start

Extract the whole ZIP into its own folder. Keep the launcher, Python files and
`e7_gui_assets` together. Double-click **E7 Secret Shop Refresh.exe**, or run:

```powershell
py -3 .\e7_shop_refresh_gui.py
```

The supplied `engine-location.ini` selects the included `runtime` folder.
It uses a relative path, so moving the whole app folder preserves that choice.
To select a separate existing installation, edit `directory` without quotes or
use a one-time override:

```powershell
py -3.13 .\e7_shop_refresh_gui.py --engine-dir "D:\Games\E7 Secret Shop Refresh"
```

Selection order is `--engine-dir`, environment variable `E7_ENGINE_DIR`, saved
`engine-location.ini`, then the Downloads default. Relative paths resolve beside
the GUI. The saved file also works with the EXE launcher. An invalid engine
folder stops startup before device discovery. Starting the real GUI with a valid
folder performs ADB device discovery; pressing Start runs the real refresh engine.

To select a stop key, click the Stop key box and press Esc or another supported
single key. Tab moves to the next control. Unsupported keys and Ctrl/Alt
combinations leave the previous selection unchanged and show a message.

Use **Dark mode** in the top-right header to switch appearance. It is remembered
in the selected engine folder's GUI preferences and remains available during a
session. It does not change Windows' appearance settings.

With the matching [live-counter engine candidate](ENGINE.md), Covenant/Mystic
buys update after each engine-completed buy sequence, and skystone spent updates
after each completed refresh. These are engine-reported actions, not a balance
verification. The original installed engine remains supported but only reports
totals at 10% budget milestones. The GUI alone cannot make that engine emit more
frequent reports. The rebuilt engine sleeps between stop-key checks to reduce
CPU/GIL contention with foreground typing.

The matching engine uses private visual references to locate Secret Shop
on the home screen and verify its title plus Refresh button. It removes the
old three fixed menu taps. Unknown, missing or ambiguous references stop the
engine rather than guessing. See [reference preparation](ENGINE.md). These
checks are only supplied by the matching engine; an old external engine retains
its own original navigation behavior.

The engine's `ADBconfig.ini`, `ShopRefreshGUI.ini` and `ShopRefreshHistory` stay
inside the selected engine installation. Existing settings/history are reused;
the GUI does not migrate the installation. Do not share these personal files.

## Candidate limitations

Fake-engine/source checks do not establish real engine prompt compatibility,
emulator behavior, purchasing, stopping a real refresh, or final visual behavior.
Live and desktop verification remain separate checks. Review the candidate
record before using it for a real spending session. There is no automatic updater.
Insufficient-gold and insufficient-skystone live checks are deferred; automatic
stopping in those cases is unverified. Counters report completed engine actions,
not confirmed game balances. First-use defaults are 12 skystones, 0.3-second tap
delay, backtick stop key and randomized offsets; saved settings take precedence.

To remove the app, stop/close it first. Back up any settings, recognition images
and CSV history you want to keep from `runtime`, then remove the extracted app
folder. A separately selected external engine folder is not removed with it.

## Source and credits

GUI Python modules and `E7ShopLauncher.cs` are included as source. See
[BUILDING.md](BUILDING.md) to rebuild the launcher. Development tests remain in
the maintained source checkout; they are not included in this player package.
The matching engine, corresponding source and build instructions are in
`runtime`; [UPSTREAM.md](UPSTREAM.md) records its relationship to Solunium's source.
The optional full Source ZIP includes the maintained checkout, builders and tests.

Software is GPL-3.0; see [LICENSE](LICENSE) and [CREDITS.txt](CREDITS.txt).
Artwork and sounds retain their own rights and credits under `e7_gui_assets`.
The supplied Epic Seven icon is retained as requested, with its provenance record.
