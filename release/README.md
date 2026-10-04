# E7 Shop Refresh — NitrogenSulfide (Blue Natto)

Version **0.1.0-rc44** is a local candidate. The previous rc20 public preview is unchanged.
Players need only **E7ShopRefresh-0.1.0-rc44.zip**.

Extract the whole ZIP and open **E7 Secret Shop Refresh.exe**. Python, Tk and
Pillow are included in this EXE. Artwork, the matching compiled engine, ADB tools
and templates are arranged beside it, with the runtime path configured.
Follow [START-HERE.md](START-HERE.md) or [SETUP.md](SETUP.md) for the emulator and
automatic shop recognition. A guided recognition helper is offered only when
startup recognition fails. The optional Source ZIP is for developers.

Use Google Play Games on PC Developer Emulator, English Epic Seven and a
1920 × 1080 Android display for ADB refreshing. STOVE and visible emulator windows have
Mouse automation described below; other emulators are unverified. Press Start in ADB
mode to try the built-in English templates. If the helper is
needed, it only reads screenshots; press Start again after it succeeds.
Start checks the selected ADB connection first. A red banner explains missing
connections without launching the refresh engine; open the emulator, enable ADB
and press Start again. Idle scans update every 10 seconds.
An ADB connection alone is not enough: Epic Seven must be active inside the
emulator, and the Google Play Games window must be open. Its background VM can
stay connected after closing the window. Other PC apps can retain focus.
Normal fresh settings are 12 skystones, 0.3-second
delay, backtick stop key and randomized offsets; saved settings take precedence.

For STOVE or Google Play Games Developer Emulator, choose **Control mode → Mouse**, select Epic Seven and press
**Start Refresh**. The app brings that game forward and uses your actual pointer
to open its recognized shop, buy Covenant/Mystic items, scroll and refresh.
If idle controls are hidden, startup can click the artwork-only view once to
reveal them, then locate the Secret Shop icon. No saved wallpaper is required.
Your budget, delay, randomized offsets, counters and Stop key apply. Leave the PC
alone until it stops. Focus or coverage changes pause input for up to 10 seconds;
a changed window or an unrecognized confirmation stops the session. The game keeps its current size. Use normal settings; Debug
remains an ADB feature. Saving settings also saves your control mode without
starting a session next time. Native checks succeeded in earlier candidates. Google developer-emulator live
actions in rc44 remain unverified; begin with a small supervised budget. Keep English game text readable.

Live counters report engine-completed buys/refreshes, not confirmed balances.
Insufficient-currency stopping remains unverified. Keep initial runs supervised.
Settings, history and private recognition captures stay under `runtime`; back
them up before updating or removing the extracted folder. No updater exists.

GUI source is supplied beside the EXE, and matching engine source is in `runtime`.
See [BUILDING.md](BUILDING.md), [ENGINE.md](ENGINE.md) and [UPSTREAM.md](UPSTREAM.md).
Source launches require a developer Python environment with Tk and Pillow; the
player EXE does not use the system Python launcher. Old CMD/PowerShell/C# launchers
remain in the full source history and are not player entry points.

Software is GPL-3.0; see [LICENSE](LICENSE) and [CREDITS.txt](CREDITS.txt). Solunium's
original notices and the artwork/audio credits are retained. Dependency licences
are under `runtime/third-party-licenses`, with ADB notices in its tool folder.

## Quickstart and tested clients

About & Credits contains Quickstart and bundled Release notes tabs. The main
screen’s Buy me a coffee button opens https://ko-fi.com/bluenatto only when clicked.

For this upcoming first full release, testing has been limited to Google Play
Games on PC Developer Emulator and the official STOVE client of Epic Seven.
Other emulators and methods have not been tested. Both modes buy only Covenant
Bookmarks and Mystic Medals; Friendship purchases are removed from calibration too.
