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

The current GUI expects the installed engine under
`%USERPROFILE%\Downloads\E7 Secret Shop Refresh`. It reads and writes settings
and history in that existing installation. Configurable engine paths and a
portable release package are follow-up work.

The copied `E7 Secret Shop Refresh.exe` launcher is available locally and remains
ignored by Git. It requires Python's Windows launcher and the adjacent GUI source;
it is not a self-contained application. The existing desktop shortcut still uses
the original General/scripts copy. No shortcut or installed engine was changed.

## Checks

Non-GUI protocol and validation checks:

```powershell
py -3 -m unittest test_e7_shop_refresh_gui.ProtocolTests -v
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
