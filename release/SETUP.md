# E7 Shop Refresh — NitrogenSulfide (Blue Natto)

## Download and open

Download **E7ShopRefresh-0.1.0-rc20.zip**, then extract the whole ZIP into a new
folder such as `Documents\E7 Shop Refresh`. Double-click **E7 Secret Shop Refresh.exe**.
The EXE includes Python, Tk and Pillow: players do not install Python or an image
library. Keep the entire folder together, including artwork and `runtime`.
The separate Source ZIP is optional for developers.

The relative engine path is already configured. The package includes the matching
engine, ADB tools, item templates and licences. It contains no personal settings,
game screenshots or recognition images. Check the optional release checksum:

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath '.\E7ShopRefresh-0.1.0-rc20.zip'
```

## Emulator setup

Use [Google Play Games on PC Developer Emulator](https://developer.android.com/games/playgames/emulator),
English Epic Seven and a **1920 × 1080 Android display**. Native STOVE is unsupported;
other emulators are unverified. Different home-screen artwork is fine.
Enable/authorize ADB debugging in the emulator. ADB is the connection that lets
the tool interact with the game while leaving your PC mouse free.
The main screen shows an amber reminder until you dismiss it with ×; that ADB
acknowledgement is saved. The hidden-UI reminder returns when the app restarts.

Select the connected emulator in the app. Google's documented endpoint is
`localhost:6520`; see the [official connection guide](https://developer.android.com/games/playgames/pg-emulator#installing-a-game).
If it is missing from Scan, run PowerShell inside the included `runtime` folder:

```powershell
.\adb-assets\platform-tools\adb.exe connect localhost:6520
.\adb-assets\platform-tools\adb.exe devices
```

Continue only when its actual identifier is listed as `device`, rather than
`offline` or `unauthorized`. Choose that identifier in the app.

## Prepare recognition once

On a fresh runtime, **Start refresh** opens recognition setup instead of starting
the engine. Follow the two capture buttons:

1. Open the game's home screen and close popups. Click once inside the game if
   its home controls have faded. Choose **Capture home menu**.
2. Open **Secret Shop manually** and leave its normal item list visible.
   Choose **Capture shop & finish**.
3. After the recognition checks pass, close setup. Check the budget and stop key,
   then press **Start refresh** again when you are ready.

Setup reads two ADB screenshots and runs the matching engine's offline image
utility. It sends no taps, refreshes or purchases. Screenshots stay private under
`runtime/setup-captures`; recognition images stay in `runtime/adb-assets/gui-navigation`.
Any replaced calibration folder is preserved as a backup. Keep these files private.
Recognition checks must pass before the engine is started.

## First supervised run

Normal defaults are **12 skystones**, **0.3 seconds**, **backtick** as the stop key,
and randomized tap offsets. Saved settings take precedence. Leave Debug / calibration
unchecked: it uses a separate 100-skystone test budget after confirmation.
Verify shop entry, one refresh and its counter update, Stop Session and the chosen
stop key. Observe a Covenant/Mystic buy when one naturally appears; the counters
count buys, not the number of medals/bookmarks awarded. You do not need to empty
your account. Insufficient-currency automatic stopping remains unverified.

If home controls fade, click the game once or open the shop. The app waits up to
60 seconds without guessing a navigation tap; Stop remains available.
Theme backgrounds and currency artwork are included in the EXE's image support;
the sun/moon button switches between the supplied day/night artwork.

## Updates and troubleshooting

Stop/close the old app before updating. Extract the new ZIP into a new folder and
preserve your old runtime settings, CSV history and locally prepared recognition
images. No updater or automatic migration exists. Back up anything you want to
keep before deleting an extracted app folder.

- **Missing recognition:** press Start to open the guided setup; the engine is
  not launched until all three reference files are present.
- **Setup cannot verify the screen:** check English UI, 1920 × 1080 Android
  resolution, visible home controls and a normal unobstructed shop list.
- **No backgrounds:** use the included **EXE** with the complete extracted folder.
  Older shortcuts and source launches can use a different Python installation.
- **Engine unavailable:** keep `runtime` beside the GUI, with its engine and ADB
  files. Do not replace the bundled engine with a different EXE.
- **No device:** use Scan and the connection commands above.

## Source and credits

GUI/enhancements: **NitrogenSulfide (Blue Natto)**. Original engine: **Solunium**,
GNU GPL-3.0. GUI Python source and engine source/build instructions are included.
The optional full Source ZIP also includes builders and tests. Dependency notices
are under `runtime/third-party-licenses`; ADB notices are in
`runtime/adb-assets/platform-tools/NOTICE.txt`. About & Credits remains available
through the app's information button. Game/artwork and audio credits remain
preserved; the software GPL does not relicense third-party artwork.
