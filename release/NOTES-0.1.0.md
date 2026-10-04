# E7 Secret Shop Refresh — v0.1.0

First release by **NitrogenSulfide (Blue Natto)**, based on Solunium's GPL-3.0
Epic Seven refresh engine.

Download **E7ShopRefresh-0.1.0.zip**, extract the whole ZIP, and open
**E7 Secret Shop Refresh.exe**. Python is included. Follow **START-HERE.md** in
the ZIP. **E7Source-0.1.0.zip** is optional for developers; **SHA256SUMS.txt**
contains the download checksums.

| Client | Mouse mode | ADB mode |
| --- | --- | --- |
| Google Play Games on PC **Developer Emulator** | Supported | Supported |
| Official native STOVE client | Supported | Unavailable |

First-release testing is limited to these two clients. Other emulators and
methods have not been tested. Use English Epic Seven and a readable landscape
16:9 game view, at least 640 × 360. ADB calibration requires 1920 × 1080.

- Automatic home-to-shop entry, including a bounded attempt to reveal idle home UI.
- Covenant Bookmark and Mystic Medal purchases, two-page shop scanning and budgeted refreshes.
- Smooth Mouse movement and dragging, bounded tap offsets and adjustable timing variation up to ±0.10 seconds.
- Whole Skystone budgets, used/total counters, configurable Stop key and Stop Session.
- Recent session history, day/night themes, Quickstart, release notes and Blue Natto credits.

Mouse uses your actual pointer: keep the game visible, resize before Start and
leave the PC alone while it runs. If the game runs as administrator, run the app
with the same permission. ADB uses the selected emulator and leaves your pointer
available. Both modes buy only Covenant Bookmarks and Mystic Medals; Mouse preview
and Friendship purchases are removed. Calibration is ADB-only.

This release preserves rc51's automation code. The owner reports the ordinary
live cases pass on both game clients. Automated checks of the rebuilt release
packages are recorded separately. Long runs, universal wallpaper/layout support
and insufficient-currency stopping have not been live-verified. Begin with a
small supervised budget and close game popups before Start.

Back up settings, history and private recognition captures under `runtime` when
updating. There is no automatic updater or migration. Personal runtime data is
excluded from the downloads.

Original engine: **Solunium**. Software is **GPL-3.0**; source, upstream notices,
dependency licences and artwork/audio credits are included. Third-party artwork
retains its respective rights. Independent community tool; no official endorsement.

Optional support: [Buy me a coffee](https://ko-fi.com/bluenatto).
