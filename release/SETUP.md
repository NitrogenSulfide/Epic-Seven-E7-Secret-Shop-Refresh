# E7 Shop Refresh — NitrogenSulfide (Blue Natto)

## Download and open

Download **E7ShopRefresh-0.1.0-rc46.zip**, then extract the whole ZIP into a new
folder such as `Documents\E7 Shop Refresh`. Double-click **E7 Secret Shop Refresh.exe**.
The EXE includes Python, Tk and Pillow: players do not install Python or an image
library. Keep the entire folder together, including artwork and `runtime`.
The separate Source ZIP is optional for developers.

The relative engine path is already configured. The package includes the matching
engine, ADB tools, item templates and licences. It contains no personal settings,
game screenshots or personal recognition images. Generic English shop-label
templates are included for automatic recognition. Check the optional release checksum:

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath '.\E7ShopRefresh-0.1.0-rc46.zip'
```

## Emulator setup

**ADB** remains the default mode for refreshing. **Mouse** automates the visible
game in STOVE or an emulator, including Google Play Games Developer Emulator.

Use [Google Play Games on PC Developer Emulator](https://developer.android.com/games/playgames/emulator),
English Epic Seven and a **1920 × 1080 Android display**. STOVE and visible emulator windows can also use Mouse mode;
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

## Mouse automation — visible game windows

Open English Epic Seven in STOVE or your emulator (including Google Play Games
Developer Emulator), with the home controls or Secret Shop visible. Choose **Control mode → Mouse**, select its
window and check your budget, delay and Stop key. Press **Start Refresh**. The app
brings the game forward, opens the recognized Secret Shop menu, buys detected
Covenant/Mystic items, scrolls and refreshes using your actual mouse pointer.
Leave the PC alone while it runs. Your Stop key and Stop Session remain available;
focus or coverage changes pause input for up to 10 seconds. Moving or resizing
the game stops it. A prepared click is cancelled if focus changed before input.
The game keeps its current size. Debug/calibration is disabled in Mouse modes
and is available only in ADB mode.
The pointer glides smoothly between targets. Tap delay still applies between
shop actions. **Randomize tap offsets** also adds a small variation to Refresh
clicks, bounded inside its observed button; turn it off for the fixed label point.
The recommended checkbox enables the **Timing variation** slider in both modes.
It adjusts extra delay or speed-up from ±0.00 to ±0.10 seconds; for very short base
delays the variation is capped at half the baseline. Turning randomization off
restores fixed timing. ADB calibration always keeps a fixed delay.
Budget is a whole number, and the spending card shows used/total. Recent sessions
reload automatically; **Clear** archives all recorded sessions before clearing
them and is disabled during a run. Archives remain in `ShopRefreshHistory/archive`.
Use **Estimate & calibration help** to expand those details in the compact sidebar.
The blue-bean header button opens the existing About & Credits dialog.
Shop scrolling uses a short upward mouse drag. The same checkbox adds small
position and timing variations while keeping the vertical travel consistent.
Stop or lost focus releases the drag button immediately. Begin with a small
supervised run to verify the new drag reaches the bottom shop items.
If the game or emulator runs as administrator, right-click **E7 Secret Shop Refresh.exe**
and choose **Run as administrator**, accepting the Windows prompt yourself.
The app checks this permission mismatch before bringing the game forward.
Normal game launches do not require an elevated refresh app.
Start from the English home screen or an already open Secret Shop. Mouse mode
locates the home Secret Shop label using templates and local Windows OCR. A locally saved known hidden-home image at
`runtime/adb-assets/native-home/hidden.png` (or a separate verified Google home
reference at `google-hidden.png` in that folder) permits a hover and one verified reveal click.
Unknown screens receive no pointer input. Emulator launchers, hidden controls
without a matching reference, and unsupported layouts must be opened manually.
The game area must fill the client or have clearly identifiable symmetric black
bars. Google's observed dark custom title bar is also excluded; colored emulator
toolbars and arbitrary crops are not inferred. The initial Google crop stays
fixed during the session, including dimmed confirmation dialogs. Actual window
moves and resizes still stop input. Restored Google windows with a thin light
frame above the header are supported. Set the window size before pressing Start;
you can begin directly in the open Secret Shop.
Google developer-emulator live actions in rc46 remain unverified.

The app checks each confirmation before clicking it and stops on unexpected text
or an insufficient-currency message. Keep English confirmation text readable.
If a native currency icon does not match, the app also checks its full summon
name, gold price and Buy label on the same row. A recognized currency with an
uncertain price or button stops the run before Refresh. A partly hidden bottom
row is checked again after scrolling. Keep the item names and prices readable.
Live counters describe completed action sequences rather than balance readings.
A supervised elevated check opened the native shop from home and completed one
three-Skystone refresh without purchases. Native purchases and long runs remain
unverified; begin with a small supervised budget and check Stop and your Stop key.
Save Settings retains your control mode and other preferences. Reopening the app
scans that mode without starting a session. ADB remains the fresh-install default.
No ADB connection is made by a Mouse session.

Native stops show their actual reason on the main screen. Detailed text logs stay
private under `runtime/mouse-session-logs`. The app checks that the pointer reaches the game before clicking. A missing confirmation also saves central game crops under `runtime/mouse-failures`; keep both folders out of shared ZIPs. Focus pauses discard stale captures and restart the recognition timeout.

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

## Quickstart and tested clients

About & Credits contains Quickstart and bundled Release notes tabs. The main
screen’s Buy me a coffee button opens https://ko-fi.com/bluenatto only when clicked.

For this upcoming first full release, testing has been limited to Google Play
Games on PC Developer Emulator and the official STOVE client of Epic Seven.
Other emulators and methods have not been tested. Both modes buy only Covenant
Bookmarks and Mystic Medals; Friendship purchases are removed from calibration too.
