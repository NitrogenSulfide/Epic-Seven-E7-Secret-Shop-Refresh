# E7 Shop Refresh — NitrogenSulfide (Blue Natto)

## Download and open

Download **E7ShopRefresh-0.1.0-rc26.zip**, then extract the whole ZIP into a new
folder such as `Documents\E7 Shop Refresh`. Double-click **E7 Secret Shop Refresh.exe**.
The EXE includes Python, Tk and Pillow: players do not install Python or an image
library. Keep the entire folder together, including artwork and `runtime`.
The separate Source ZIP is optional for developers.

The relative engine path is already configured. The package includes the matching
engine, ADB tools, item templates and licences. It contains no personal settings,
game screenshots or personal recognition images. Generic English shop-label
templates are included for automatic recognition. Check the optional release checksum:

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath '.\E7ShopRefresh-0.1.0-rc26.zip'
```

## Emulator setup

**ADB** remains the default mode for refreshing. **Mouse (preview)** is a separate
experimental, read-only option described below; it cannot refresh or buy items.

Use [Google Play Games on PC Developer Emulator](https://developer.android.com/games/playgames/emulator),
English Epic Seven and a **1920 × 1080 Android display**. Native STOVE is unsupported;
other emulators are unverified. Different home-screen artwork is fine.
Enable/authorize ADB debugging in the emulator. ADB is the connection that lets
the tool interact with the game while leaving your PC mouse free.
The main screen shows an amber reminder until you dismiss it with ×; that ADB
acknowledgement is saved. The hidden-UI reminder returns when the app restarts.

Select the connected emulator in the app. Google's documented endpoint is
`localhost:6520`; see the [official connection guide](https://developer.android.com/games/playgames/pg-emulator#installing-a-game).
Start checks the selected connection and can connect the entered ADB endpoint.
With no usable connection, a red banner explains how to fix it; the engine does
not launch. Start remains available to retry. Idle scans update every 10 seconds
and do not connect or send game actions. An open emulator still needs ADB enabled
and authorized; `offline` and `unauthorized` devices are not ready.
Open Epic Seven inside the emulator. For Google Play Games, keep its game window
open too: its ADB connection can remain alive after you close the window. The app
checks that window and Epic Seven's current Android activity before starting.
You may keep using other PC windows; the tool does not take keyboard/mouse focus.
If needed, run PowerShell inside the included `runtime` folder:

```powershell
.\adb-assets\platform-tools\adb.exe connect localhost:6520
.\adb-assets\platform-tools\adb.exe devices
```

Continue only when its actual identifier is listed as `device`, rather than
`offline` or `unauthorized`. Choose that identifier in the app.

## Start refreshing

Check your budget and stop key, then press **Start refresh**. The app tries its
built-in English shop recognition automatically; fresh users normally do not
need to capture reference screens. Saved personal references remain supported.
The menu must be recognized before a navigation tap, and both shop markers must
be verified before purchases or refreshes.

If controls are hidden, click the game once to reveal them. The app waits up to
60 seconds without guessing a tap. If startup recognition still fails, the
engine stops before purchases or refreshes and opens the helper below.

## Recognition helper — only if needed

Follow the two capture buttons if automatic recognition could not verify your UI:

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
Completing this helper never starts refreshing automatically. Close it and press
Start again when ready. Built-in templates are kept separate from these private files.

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

## Mouse preview — experimental

This checks capture and recognition before adding mouse controls for the regular
Google Play Games or native STOVE client. Neither client has passed live Mouse
mode testing yet. No ADB connection is needed for this preview.

1. Open English Epic Seven, reveal its home controls or open Secret Shop manually.
   Keep a 16:9 game view, at least 640 × 360 pixels, visible and unobstructed.
   The outer window can have a different shape: plain symmetric black bars are
   cropped automatically when they surround a recognizable 16:9 image.
2. Choose **Control mode → Mouse (preview)**, press **Scan** and select the game
   window. Press **Preview targets**, then click the game during the three-second
   countdown. If it is not ready yet, the app waits up to 20 more seconds for
   the selected game to be in front and unobstructed. Keep it still until capture
   finishes. The app never brings the game forward or moves your mouse for you.
3. Return to this app. Yellow markers show the recognized Secret Shop menu or
   Refresh button; cyan boxes show detected Covenant/Mystic item icons in the
   visible list. An unknown screen shows no guessed targets.

The tool does not move the pointer, click, refresh, buy or install hooks in this
mode. Stop cancels the countdown/window wait and ignores late preview results. Captures
and reports stay private under `runtime/mouse-previews`; keep them out of shared
ZIPs. A closed, covered, unfocused, moved or blank window fails with an explanation.
The app opens in ADB mode each time; switching back preserves your ADB address.

## Updates and troubleshooting

Stop/close the old app before updating. Extract the new ZIP into a new folder and
preserve your old runtime settings, CSV history and locally prepared recognition
images. No updater or automatic migration exists. Back up anything you want to
keep before deleting an extracted app folder.

- **Recognition needs help:** reveal the game controls or manually open Secret
  Shop. If startup recognition fails, use the offered helper and press Start again.
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
