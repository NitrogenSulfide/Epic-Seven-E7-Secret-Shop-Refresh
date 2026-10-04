# E7 Shop Refresh — NitrogenSulfide (Blue Natto)

Version **0.1.0-rc22** is a local candidate. The previous rc20 public preview is unchanged.
Players need only **E7ShopRefresh-0.1.0-rc22.zip**.

Extract the whole ZIP and open **E7 Secret Shop Refresh.exe**. Python, Tk and
Pillow are included in this EXE. Artwork, the matching compiled engine, ADB tools
and templates are arranged beside it, with the runtime path configured.
Follow [START-HERE.md](START-HERE.md) or [SETUP.md](SETUP.md) for the emulator and
automatic shop recognition. A guided recognition helper is offered only when
startup recognition fails. The optional Source ZIP is for developers.

Use Google Play Games on PC Developer Emulator, English Epic Seven and a
1920 × 1080 Android display. Native STOVE is unsupported; other emulators are
unverified. Press Start to try the built-in English templates. If the helper is
needed, it only reads screenshots; press Start again after it succeeds.
Start checks the selected ADB connection first. A red banner explains missing
connections without launching the refresh engine; open the emulator, enable ADB
and press Start again. Idle scans update every 10 seconds.
Normal fresh settings are 12 skystones, 0.3-second
delay, backtick stop key and randomized offsets; saved settings take precedence.

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
