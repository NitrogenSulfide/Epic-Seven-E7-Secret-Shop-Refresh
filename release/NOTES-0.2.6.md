# v0.2.6 (beta) — Waits out a blank confirmation while the game waits on the server

> ⚠️ **Beta, only tested on my own PCs.** Steam (Windows 11 and Linux), the STOVE client and
> Google Play Games Developer Emulator work for me. Other PCs, emulators and settings
> may hit edge cases I haven't seen. Start with a small Skystone budget, and if
> something breaks, report it on [GitHub Issues](https://github.com/NitrogenSulfide/Epic-Seven-E7-Secret-Shop-Refresh/issues)
> or Reddit with **Copy report**.

**Fix for "The refresh confirmation was not recognized" after many refreshes.** On
Steam (3840 × 2019, Background) a run stopped after 76 refreshes: the game had
darkened the shop and opened the confirmation, but left it as an empty band for more
than 5 seconds, probably while it waited on the server. While a blank confirmation
like that is open, the app now keeps reading it for up to 10 more seconds (15 in all)
and says so in the activity log. It still clicks Confirm only after reading the full
dialog: the action, item and cost must match. If the dialog stays blank, the run stops
without a click and the message says it stayed blank.

Settings and history carry over: extract **E7ShopRefresh-0.2.6.zip** into a fresh
folder and copy `runtime/ShopRefreshGUI.ini`, `runtime/ADBconfig.ini` and
`runtime/ShopRefreshHistory/` from your old folder if you want them.
