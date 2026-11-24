# v0.2.7 (beta) — A settings panel that saves itself; choose what to buy; "Covenant!"/"Mystic!" callouts; waits out a blank confirmation

> ⚠️ **Beta, only tested on my own PCs.** Steam (Windows 11 and Linux), the STOVE client and
> Google Play Games Developer Emulator work for me. Other PCs, emulators and settings
> may hit edge cases I haven't seen. Start with a small Skystone budget, and if
> something breaks, report it on [GitHub Issues](https://github.com/NitrogenSulfide/Epic-Seven-E7-Secret-Shop-Refresh/issues)
> or Reddit with **Copy report**.

0.2.6 was not released on its own, so this release includes its changes too.

**A more visual settings panel.** Control mode is a row of cards (Background, Mouse,
ADB). The **Skystone budget** can be typed, dragged on a slider or picked from 150 /
300 / 1,000 / 3,000, and a line underneath shows the refreshes, the expected Covenant
and Mystic buys and the gold needed. The sidebar and the session dashboard sit on
rounded cards, so scrolling the sidebar no longer tears the background picture.

**Settings save themselves.** A moment after each change your settings are saved,
so the Save Settings button is gone. An unfinished budget (below 3) or no item chosen
keeps the last good values and says "Not saved yet". Nothing is written while a
session runs.

**Choose what to buy.** Covenant bookmarks, Mystic medals and Friendship Points are
tiles under **Buy**, with the gold per buy. Covenant and Mystic are on by default;
turn one off to farm only what you need. Items that are off are left in the shop.

**"Covenant!" / "Mystic!" callouts.** A voice calls out each confirmed purchase.
**Start/Stop SFX**, **Compact tracker** and the two callouts are four toggle pills
under Start, each on its own: turning off Start/Stop SFX no longer silences the
callouts. If Sounds was off in an older version, the callouts start off too.
Voice: ElevenLabs "Laura".

**Simpler timing.** Tap delay, offsets, timing variation and calibration moved into a
collapsed **Advanced** section with **Reset to recommended**. On first start, older
custom timing is reset once to the recommended values (0.3 s tap delay, offsets on,
±0.03 s) and the app says so; budget and stop key are kept.

**Fix for "The refresh confirmation was not recognized" after many refreshes.** On
Steam (3840 × 2019, Background) a run stopped after 76 refreshes: the game had
darkened the shop and opened the confirmation, but left it as an empty band for more
than 5 seconds, probably while it waited on the server. While a blank confirmation
like that is open, the app now keeps reading it for up to 10 more seconds (15 in all)
and says so in the activity log. It still clicks Confirm only after reading the full
dialog: the action, item and cost must match. If the dialog stays blank, the run stops
without a click and the message says it stayed blank.

Settings and history carry over: extract **E7ShopRefresh-0.2.7.zip** into a fresh
folder and copy `runtime/ShopRefreshGUI.ini`, `runtime/ADBconfig.ini` and
`runtime/ShopRefreshHistory/` from your old folder if you want them.
