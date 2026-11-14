# E7 Shop Refresh — NitrogenSulfide (Blue Natto)

## Download and open

Download the **E7ShopRefresh ZIP** for your chosen version, then extract it into a new
folder such as `Documents\E7 Shop Refresh`. Double-click **E7 Secret Shop Refresh.exe**.
If Windows 11 shows **Windows protected your PC**, click **More info**, then **Run
anyway**; the app is not code-signed. Then choose **Yes** at the administrator
prompt, which appears every time the app opens.
The EXE includes Python, Tk and Pillow: players do not install Python or an image
library. Keep the entire folder together, including artwork and `runtime`.
The separate Source ZIP is optional for developers.

The relative engine path is already configured. The package includes the matching
engine, ADB tools, item templates and licences. It contains no personal settings,
game screenshots or personal recognition images. Generic English shop-label
templates are included for automatic recognition. Check the optional release checksum:

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath '.\E7ShopRefresh-<version>.zip'
```

## Steam and STOVE · Background mode

Most players use Epic Seven on **Steam** or **STOVE**. Keep **Control mode →
Background** (the default for new settings), select the game window and press
**Start Refresh**. Clicks go to the game window directly and frames are read
from it, so your pointer is never moved and other windows may cover the game.
The app always opens as administrator, because the game runs as administrator
and Windows blocks normal apps from controlling it. Windows asks for permission
each time you open the app; choose Yes. You can keep using the PC: input
waits while the pointer moves over the game, and a red line counts down to an
automatic stop if it stays there. Park the pointer elsewhere or on the taskbar.
Don't minimize or resize the game during a run. Only one Epic Seven window may
be open.

**Tips for a smooth Background run**

- **Two monitors work best:** game on one, everything else on the other.
- **One monitor:** leave the game open behind your other windows. Covering it is
  fine, but **never minimize it**; a minimized game stops drawing and the run stops.
- Keep your pointer off the game window (park it on the other monitor or the
  taskbar). A pointer moving over the game pauses input.
- Start from the home screen or an open Secret Shop, with no Refresh or Buy dialog
  left open.
- Don't resize the game, switch it to or from fullscreen, or open a second Epic
  Seven window during a run.
- Keep the PC awake: don't let it sleep or lock during a run.
- Try a small budget first. The Stop key (default `` ` ``) works from any window.

For an emulator, including Google Play Games Developer Emulator, use **Mouse**
(it takes over your pointer) or the optional **ADB** setup below; when Background
finds one of those, its banner offers **Switch to Mouse**.

## Start refreshing

Check your budget and stop key, then press **Start refresh**. The app tries its
built-in English shop recognition automatically; fresh users normally do not
need to capture reference screens. Saved personal references remain supported.
The menu must be recognized before a navigation tap, and both shop markers must
be verified before purchases or refreshes.

Start from home or an already open Secret Shop. If home controls are hidden,
normal ADB and Mouse sessions can try one center click to reveal them, then
recognize the menu and verify shop entry. Close popups first. Unknown screens,
blank captures and recognized dialog/loading controls stop without a shop action.
If startup recognition fails, the recognition helper is available.

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

## Mouse automation — emulators and visible game windows

Open English Epic Seven in STOVE or your emulator (including Google Play Games
Developer Emulator), on home (including hidden idle controls) or Secret Shop. Close popups. Choose **Control mode → Mouse**, select its
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
show the latest 25 saved runs; **Export Excel** includes every saved session,
including older entries. The workbook contains numeric counters, totals and
available timestamps, outcomes and reasons. Tap delay must be above zero and no
more than two seconds, including randomized timing. Sessions reload automatically;
**Clear** archives all recorded sessions before clearing
them and is disabled during a run. Archives remain in `ShopRefreshHistory/archive`.
Use **Estimate & calibration help** to expand those details in the compact sidebar.
The blue-bean header button opens the existing About & Credits dialog.
Shop scrolling uses a short upward mouse drag. The same checkbox adds small
position and timing variations while keeping the vertical travel consistent.
Stop or lost focus releases the drag button immediately. Begin with a small
supervised run to verify the new drag reaches the bottom shop items.
The app always opens as administrator (Windows asks each time you open it), so
games and emulators that run as administrator need no extra restart. If an older
copy or a source run is not elevated, **Start Refresh** offers to save settings and
restart through Windows' administrator prompt; after reopening, select your game
and press Start Refresh again. The permission check happens before bringing the
game forward.
Start from the English home screen or an already open Secret Shop. If no home
controls are recognized, Mouse mode can click the game center once, wait briefly,
then find the Secret Shop icon. No saved wallpaper is required. Animation,
dark/sparse artwork and incidental lettering do not block this reveal attempt.
Blank captures and known dialog/loading controls do. It rechecks freshly visible
controls before input, never repeats the reveal, and verifies shop entry before
refreshing or buying. Other game pages and emulator launchers are unsupported.
The game area must fill the client or have clearly identifiable symmetric black
bars. Google's observed dark custom title bar is also excluded; colored emulator
toolbars and arbitrary crops are not inferred. The initial Google crop stays
fixed during the session, including dimmed confirmation dialogs. Actual window
moves and resizes still stop input. Restored Google windows with a thin light
frame above the header are supported. Set the window size before pressing Start;
you can begin directly in the open Secret Shop.
The owner regression-tested Mouse and ADB with the rc3 candidate used for v0.1.3.
The saved Mouse run completed 133 refreshes (399 Skystones), buying four Covenant
items and one Mystic item. This does not establish reliability for every setup
or arbitrarily long runs.

The app checks each confirmation before clicking it and stops on unexpected text
or an insufficient-currency message. Keep English confirmation text readable.
If brief coverage clears before a click is delivered, it discards that prepared
click and recognizes the current screen again. Repeated visibility failures,
window movement/resizing and visibility loss after mouse-down still stop input.
It checks the prompt again on a fresh capture and allows small OCR shifts in
the observed button bounds. Animated artwork behind the dialog does not need
to stay still. Changed confirmations save both private dialog crops for diagnosis.
If a native currency icon does not match, the app also checks its full summon
name, gold price and Buy label on the same row. A recognized currency with an
uncertain price or button stops the run before Refresh. A partly hidden bottom
row is checked again after scrolling. Keep the item names and prices readable.
Live counters describe completed action sequences rather than balance readings.
The owner reports passing Mouse and ADB regression runs with the rc3 candidate.
Insufficient-currency stopping remains unverified;
begin with a small supervised budget and check Stop and your Stop key.
Save Settings retains your control mode and other preferences. Reopening the app
scans that mode without starting a session. Background is the fresh-install default;
an existing saved Mouse or ADB preference is preserved, and Mouse mode offers
**Switch to Background** when it sees Epic Seven on Steam or STOVE.
No ADB connection is made by a Mouse session.

Native stops show their actual reason on the main screen. Detailed text logs stay
private under `runtime/mouse-session-logs`. The app checks that the pointer reaches the game before clicking. A missing confirmation also saves central game crops under `runtime/mouse-failures`; keep both folders out of shared ZIPs. Focus pauses discard stale captures and restart the recognition timeout.

## ADB setup · optional, emulators only

ADB is for emulators only; Steam and STOVE players can skip this section.
Use [Google Play Games on PC Developer Emulator](https://developer.android.com/games/playgames/emulator),
English Epic Seven and a **landscape 16:9 game view of at least 640 × 360**. Native STOVE Mouse mode also accepts its wider maximized client area. ADB calibration requires 1920 × 1080. STOVE and visible emulator windows can also use Mouse mode;
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

## BlueStacks 5

Enable ADB in the intended BlueStacks player and leave its window open. In ADB
mode, use **Scan** and select that player by name. The number shown beside it is
its current port; Player 2 can use a different port from Player 1. The selected
full address and connection state appear below the selector. Scan does not
connect; **Start Refresh** connects only the selected endpoint and checks that
Epic Seven is active before launching the refresh engine.

Mouse mode uses the player's verified game surface, excluding emulator toolbars
and advertising. If Windows denies the permission check, the app offers an
administrator retry. That retry does not start a session automatically. If the
check remains denied, use ADB or reopen the player without administrator
privileges. Use the complete matching new player folder with the v9 Mouse engine.

The owner reports rc4 ADB and Mouse working at maximized and smaller sizes,
including hidden home controls. The rc6 streamed/global Stop key needs its own live
check. Stop is registered for the active session regardless of ordinary window
focus; if the key is reserved by another app, startup stops and asks for another
key. Rc6 also listens to keyboard events, including brief injected streaming
presses. Diagnostics record how Stop was detected. Finishing the session releases
the listener and registration. Moonlight must forward the key to the host;
client-consumed keys cannot reach the app.

The heart-icon Friendship buys counter sits to the right of Mystic buys.
Diagnostics show its count and whether buying is enabled. Excel exports put
Friendship buys beside Mystic buys and show points gained (50 per buy), with
legacy Friendship Bookmarks in a separate column. Buying remains optional.

The green leaf-heart icon is a cutout generated from the supplied game image.
Purchased/sold-out rows are skipped, including purchases made before this session.
Only purchases completed by this session contribute to its counters and spending.

Rc7 recognizes 0/1 stock beside Buy on a pre-purchased row, even when the button,
price and “Only 1 available” remain visible. A verified 1/1 row still follows
normal purchase checks. Stock recognition uses item and control positions;
your shop wallpaper does not need to match the supplied example. Rc8 also handles
that row at the bottom of the scrolled list. Rc9 also works with warm display tints such as f.lux or Night light.
Use the whole rc9 folder with its matching runtime. Enable Also buy Friendship Points if you
want new Friendship purchases; its default remains off.

## Optional detailed diagnostics

In **Diagnostics**, enable **Log click coordinates and timing** before starting
to see applied click offsets, mapped screen/device coordinates, sampled tap
pacing and measured waits. It works in Mouse and ADB, independently of calibration.
Cycle totals include scanning, purchases, settling and pauses; initial/final
scans and interrupted intervals are labelled separately. Coordinates labelled
1920 × 1080 refer to the recognition frame, not your monitor resolution.

Use the release's matching bundled engine. Detailed events and saved logs have
size limits; reaching one does not stop the session. Logs stay local. **Copy
Diagnostics** copies the retained output for a report you choose to share.

## Remaining time and session shortcuts (0.1.4 trial)

**Time remaining** starts with “Estimating…” until three intervals between
confirmed refreshes are available. It then uses the latest eight intervals to
show an approximate countdown. Purchases and recognition speed can change the
estimate. Startup is excluded, and focus pauses freeze the countdown. At the
last budgeted refresh it shows “Finishing final scan…” while the engine checks
the remaining items. Calibration and older engines without live refresh
counters do not receive a time estimate. Detailed logging can remain off.

**Open Logs Folder** in Diagnostics opens the current or last session's saved
log folder, otherwise the selected mode's folder. For Mouse it becomes available
after the session ends, so opening Explorer cannot cover the running game.
ADB logs are saved when detailed diagnostics are enabled.

Excel export suggests a name such as
`E7-sessions-2026-10-07_09-15-04-a1b2c3d4.xlsx`. The date/time use the PC's local
clock; the suffix distinguishes exports even within the same second. You can
still choose your own filename in the save dialog.

## Updates and troubleshooting

Stop/close the old app before updating. Extract the new ZIP into a new folder and
preserve your old runtime settings, CSV history and locally prepared recognition
images. No updater or automatic transfer between release folders exists. When a new
session is recorded in an older CSV history, its schema is migrated with the original preserved in
`ShopRefreshHistory/schema-backups`. Back up anything you want to
keep before deleting an extracted app folder.

- **Recognition needs help:** reveal the game controls or manually open Secret
  Shop. If startup recognition fails, use the offered helper and press Start again.
- **Setup cannot verify the screen:** check English UI, a supported landscape 16:9 Android
  resolution, visible home controls and a normal unobstructed shop list.
- **No backgrounds:** use the included **EXE** with the complete extracted folder.
  Older shortcuts and source launches can use a different Python installation.
- **Engine unavailable:** keep `runtime` beside the GUI, with its engine and ADB
  files. Do not replace the bundled engine with a different EXE.
- **No device:** use Scan and the connection commands above.

## Quickstart and tested clients

About & Credits contains Quickstart and bundled Release notes tabs. The main
screen’s Buy me a coffee button opens https://ko-fi.com/bluenatto only when clicked.

Testing has been limited to Epic Seven on Steam (Background mode, Windows 11 and
Linux), the official STOVE client (Background since 0.2.1, and Mouse) and Google
Play Games on PC Developer Emulator (Mouse and ADB).
Other emulators and methods have not been tested. Both modes buy Covenant
Bookmarks and Mystic Medals by default. Optionally enable **Also buy Friendship
Points** for the current heart item (50 points for 18,000 gold per buy), using
this trial's matching engine. Calibration excludes Friendship. Friendship
purchases have been verified live in Background mode on Steam.

## Source and credits

GUI/enhancements: **NitrogenSulfide (Blue Natto)**. Original engine: **Solunium**,
GNU GPL-3.0. GUI Python source and engine source/build instructions are included.
The optional full Source ZIP also includes builders and tests. Dependency notices
are under `runtime/third-party-licenses`; ADB notices are in
`runtime/adb-assets/platform-tools/NOTICE.txt`. About & Credits remains available
through the app's information button. Game/artwork and audio credits remain
preserved; the software GPL does not relicense third-party artwork.
