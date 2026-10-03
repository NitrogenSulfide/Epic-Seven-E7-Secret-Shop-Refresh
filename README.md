# E7 Secret Shop Refresh GUI

Windows GUI maintained by NitrogenSulfide, using Solunium's Epic Seven Secret
Shop Refresh ADB engine. The original upstream source and Git history are
preserved, alongside the imported GUI, launchers, tests, sounds and icon.

This is a local development project. No GitHub fork or release has been published.

## Run the imported GUI

Use Python 3 with Tkinter and the separately installed upstream ADB engine:

```powershell
py -3 .\e7_shop_refresh_gui.py
```

The default engine folder is `%USERPROFILE%\Downloads\E7 Secret Shop Refresh`.
To use another existing installation, choose its folder:

```powershell
py -3 .\e7_shop_refresh_gui.py --engine-dir "D:\Games\E7 Secret Shop Refresh"
```

To save the choice for double-click launches, copy `engine-location.example.ini`
to `engine-location.ini` beside the GUI and edit its `directory` value. Use the
folder containing `E7ADBShopRefresh.exe` and `adb-assets\platform-tools\adb.exe`,
without surrounding quotes. The saved file is ignored by Git. Relative paths
are resolved beside the GUI; Windows environment variables such as
`%USERPROFILE%` can be used. The GUI does not move or copy an installation.

Selection order is `--engine-dir`, the `E7_ENGINE_DIR` environment variable,
`engine-location.ini`, then the Downloads default. An invalid selection stops
startup with an error before scanning devices or writing settings. Settings and
history remain inside the selected installation; GUI artwork stays beside the
GUI. The PowerShell and CMD launchers also accept `--engine-dir`; the copied EXE
uses the saved file or environment variable.

For the Stop key setting, click its box and press Esc or another supported
single key. Tab remains navigation; unsupported keys leave the selection intact.

**Dark mode** in the top-right header switches appearance and remembers the
choice in `ShopRefreshGUI.ini`. It remains available during a session.

The separately built [live-counter engine](ENGINE.md) sleeps between
stop-key checks and emits counts after each completed buy/refresh. The GUI consumes
those reports immediately. The original engine remains supported with its older
10% milestone updates. Build candidates from recorded source; preserve the
installed binary and test a separate runtime folder first.

The copied `E7 Secret Shop Refresh.exe` launcher is available locally and remains
ignored by Git. It requires Python's Windows launcher and the adjacent GUI source;
it is not a self-contained application. The existing desktop shortcut still uses
the original General/scripts copy. No shortcut or installed engine was changed.

## Checks

Non-GUI protocol and validation checks:

```powershell
py -3 -m unittest test_e7_shop_refresh_gui.ProtocolTests test_e7_engine_location -v
```

The following tests create GUI windows and should run in a suitable coordinated
desktop session. They use fixtures; passing them does not establish live-engine
or emulator correctness:

```powershell
py -3 test_e7_shop_refresh_gui.py
py -3 test_e7_shop_refresh_layout.py
py -3 test_e7_shop_refresh_icons.py
```

No dependencies were installed and the upstream engine source was not rebuilt
during project extraction. Read [UPSTREAM.md](UPSTREAM.md) for the source and
installed-engine distinction, and [the preserved upstream README](docs/UPSTREAM-README.md)
for Solunium's original setup and build instructions.

## Local release candidate

The maintained builder creates a GUI-only ZIP with source, assets, user
instructions and a launcher compiled from the same clean commit:

```powershell
.\build_release.ps1
```

The output is under ignored `dist/candidates/<VERSION>/` with a build manifest.
Existing candidate directories are never overwritten. Python and a separately
installed engine remain required. See [RELEASES.md](RELEASES.md) for checks and
publication gates, and [the packaged instructions](release/README.md).

## Ownership and licensing

The new project directory is the maintained source workspace. The previous
General/scripts files and their backups are retained as recovery copies.

Software in this project is released under GPL-3.0; retain the upstream notices
and [LICENSE](LICENSE). Artwork and sounds retain their respective rights and
licences; see [CREDITS.txt](CREDITS.txt) and [asset provenance](e7_gui_assets/provenance.json).
The supplied icon is retained at the owner's request and is not asserted to be
original project artwork or covered by the software licence.

For a future GitHub fork, create the fork under NitrogenSulfide and add it as
`origin`. The existing `upstream` fetch remote points to Solunium. This checkout
has upstream ancestry, so the GUI work can be pushed to the fork without
rewriting Solunium's history. Public hosting is a separate approval step.
