# E7 Secret Shop Refresh GUI

Windows GUI by NitrogenSulfide for Solunium's Epic Seven Secret Shop Refresh ADB
engine. This is version **0.1.0-rc2**, a local release candidate. It has not been
published or cleared for live-game use by the release workflow.

## Requirements

- Windows with Python 3 and Tkinter, plus Python's Windows launcher (`py`/`pyw`).
  Automated candidate checks use Python 3.13; other versions are not yet verified.
- A separately installed Solunium ADB engine folder containing
  `E7ADBShopRefresh.exe` and `adb-assets\platform-tools\adb.exe`.
- A compatible emulator/game setup as described in
  [Solunium's preserved instructions](docs/UPSTREAM-README.md).

This package contains the GUI source and a small launcher. Python, the engine,
ADB and emulator are separate dependencies. The launcher is not a self-contained
application, and this package does not install them or configure the emulator.

## Start

Extract the whole ZIP into its own folder. Keep the launcher, Python files and
`e7_gui_assets` together. Double-click **E7 Secret Shop Refresh.exe**, or run:

```powershell
py -3 .\e7_shop_refresh_gui.py
```

The default engine folder is `%USERPROFILE%\Downloads\E7 Secret Shop Refresh`.
To choose another folder, copy `engine-location.example.ini` to
`engine-location.ini` beside the GUI and edit `directory`, without surrounding
quotes. Use the folder containing the engine EXE and `adb-assets` directory.
For a one-time override:

```powershell
py -3 .\e7_shop_refresh_gui.py --engine-dir "D:\Games\E7 Secret Shop Refresh"
```

Selection order is `--engine-dir`, environment variable `E7_ENGINE_DIR`, saved
`engine-location.ini`, then the Downloads default. Relative paths resolve beside
the GUI. The saved file also works with the EXE launcher. An invalid engine
folder stops startup before device discovery. Starting the real GUI with a valid
folder performs ADB device discovery; pressing Start runs the real refresh engine.

To select a stop key, click the Stop key box and press Esc or another supported
single key. Tab moves to the next control. Unsupported keys and Ctrl/Alt
combinations leave the previous selection unchanged and show a message.

The engine's `ADBconfig.ini`, `ShopRefreshGUI.ini` and `ShopRefreshHistory` stay
inside the selected engine installation. Existing settings/history are reused;
the GUI does not migrate the installation. Do not share these personal files.

## Candidate limitations

Fake-engine/source checks do not establish real engine prompt compatibility,
emulator behavior, purchasing, stopping a real refresh, or final visual behavior.
Live and desktop verification remain separate checks. Review the candidate
record before using it for a real spending session. There is no automatic updater.

To remove the GUI, close it after stopping any active session and remove only
its extracted folder. The separately installed engine and its settings/history
remain. Do not delete the engine folder when removing the GUI.

## Source and credits

GUI Python modules and `E7ShopLauncher.cs` are included as source. See
[BUILDING.md](BUILDING.md) to rebuild the launcher. Development tests remain in
the maintained source checkout; they are not included in this player package.
The full engine is not bundled; [UPSTREAM.md](UPSTREAM.md) records its relationship
to Solunium's source and the previously installed binary.

Software is GPL-3.0; see [LICENSE](LICENSE) and [CREDITS.txt](CREDITS.txt).
Artwork and sounds retain their own rights and credits under `e7_gui_assets`.
The supplied Epic Seven icon is retained as requested, with its provenance record.
