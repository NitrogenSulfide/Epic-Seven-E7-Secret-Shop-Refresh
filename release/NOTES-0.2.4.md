# v0.2.4 — Windowed games no longer miss clicks; recovers from ignored clicks

> ⚠️ **Only tested on my own PCs.** Steam (Windows 11 and Linux), the STOVE client and
> Google Play Games Developer Emulator work for me. Other PCs, emulators and settings
> may hit edge cases I haven't seen. Start with a small Skystone budget, and if
> something breaks, report it on [GitHub Issues](https://github.com/NitrogenSulfide/Epic-Seven-E7-Secret-Shop-Refresh/issues)
> or Reddit with the log line the app shows.

**Fix for windowed games on Windows failing at the start.** In windowed mode the game
cancels a Background click while your mouse rests anywhere on its window: the shop
icon was pressed but the shop never opened ("The Secret Shop did not open after
selecting its menu"). Background now pauses while the mouse is over a windowed game
and resumes as soon as you move it off, onto the taskbar or another screen.
Fullscreen is unchanged; a still mouse over a fullscreen game is fine.

**Copy report.** When a run stops with a problem, press **Copy report** under the
message and paste it into your Reddit comment or GitHub issue. It has everything
needed to look into it (version, system, game window setup, the stop reason and the
last log lines), with your Windows user name hidden. **Open pictures** opens the
screenshots the app saved when it stopped, so you can attach them too.

**Fix for runs stopping when the wanted item is in the last row of the shop.** Right
after a purchase from the bottom of the scrolled list, the game sometimes ignores
the next click. A Confirm dialog stayed open ("The shop did not return after
confirmation") or a Buy click opened nothing, and the run stopped.

- If the **same** Confirm dialog is still open and settled 5 seconds after the click,
  the app confirms once more. One dialog is one purchase or one refresh, so this
  cannot charge twice.
- If a Buy click opens no dialog, the app clicks Buy once more, only when the shop is
  fully visible with the same item and Buy button. Buy spends nothing by itself.
- If a Refresh click opens no dialog ("The refresh confirmation was not recognized"),
  the app clicks Refresh once more, only when the shop is fully visible with the
  Refresh button where it was. Refresh spends nothing by itself.
- A short 0.6 second pause after a purchase from the scrolled list, before Refresh.
- Each retry happens at most once. A second miss stops the run as before.

Settings and history carry over: extract **E7ShopRefresh-0.2.4.zip** into a fresh
folder and copy `runtime/ShopRefreshGUI.ini`, `runtime/ADBconfig.ini` and
`runtime/ShopRefreshHistory/` from your old folder if you want them.
