# v0.2.4 (beta) — A mouse resting on the game no longer cancels clicks; recovers from ignored clicks

> ⚠️ **Beta, only tested on my own PCs.** Steam (Windows 11 and Linux), the STOVE client and
> Google Play Games Developer Emulator work for me. Other PCs, emulators and settings
> may hit edge cases I haven't seen. Start with a small Skystone budget, and if
> something breaks, report it on [GitHub Issues](https://github.com/NitrogenSulfide/Epic-Seven-E7-Secret-Shop-Refresh/issues)
> or Reddit with the log line the app shows.

**Fix for runs failing at the start on Windows.** The game cancels a Background click
while your mouse rests anywhere on it, windowed or fullscreen: the shop icon was
pressed but the shop never opened ("The Secret Shop did not open after selecting its
menu"). Background now pauses while the mouse is over the game and resumes as soon
as you move it off, onto the compact tracker bar, the taskbar or another screen. With
one fullscreen monitor, park the mouse on the compact bar.

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

**Fix for runs stopping when two wanted items are on the same page.** After buying
the first, the app looked for the second while the list was still moving and stopped
with "The selected item changed before Buy". It now waits for the list to come to
rest after each purchase before looking for the next item.

**Fix for skipped items in windowed mode.** A mouse crossing the game during the
app's scroll could cancel it, so the second half of the shop was never checked and a
wanted item there was skipped. The app now checks that the list actually moved and
drags once more if it did not. If it still did not, it drags the other way (a shop
left scrolled to the bottom then shows its top rows), and if the list never moves the
run stops before Refresh. A drag spends nothing.

**Fix for items you already bought before starting.** If you bought a Covenant or
Mystic from the current shop by hand and then started a run, the app could try to buy
it again and stop at the Buy dialog. It now also recognizes the greyed-out row the
game shows for a bought item and skips it.

**Fix for Mouse mode stopping right after it starts.** The compact tracker bar stays
on top of other windows, and in Mouse mode it could sit over the game, where Mouse mode
reads the screen, so it lost track of the shop. Mouse mode now keeps the normal app
window instead of the bar. Background mode is unchanged.

**Tap delay is now at least 0.3 seconds**, the default. Lower values, including ones
saved by older versions, are raised to 0.3, because the game ignores faster clicks.
Random timing never goes below 0.3 either.

**Item list still moving before Buy.** Right after a refresh the list can still be settling; the run used to stop with "The selected item changed before Buy". It now waits for the list to come to rest and checks again, and stops (no click sent) only if the item is really gone. The same goes for "its price and Buy button could not be verified on the same row" when it was caused by the moving list.

**Steadier, a little slower.** Mouse and Background now wait until every row of the item list has stopped moving, not just the list on average, before reading it. After a refresh the wait can last up to 2.5 seconds; it ends sooner once the list is still.

**Fewer stops from a single unlucky frame.** Each of these happens before any click, so waiting is safe: right before Buy the app looks up to three times, settling in between, before stopping; a frame where a fade or toast hides the shop title is read again; a Refresh button covered by a toast gets 5 seconds instead of 2.5; a momentarily blank game capture is taken again once.

**Fixes found in testing.** A Confirm dialog with an animated glow no longer stops the run while its button stays put (its item and price are still checked). On STOVE, Windows OCR read the coin icon beside the Covenant price as an extra 0, and the dialog was rejected as the wrong price; prices are now compared as numbers. In windowed mode, a scroll cancelled by a passing pointer could be mistaken for a scrolled list; the app now confirms it is looking at the shop before deciding. If a run stops just after a Confirm click, that refresh or purchase is counted and the log says to check it in the game.

Settings and history carry over: extract **E7ShopRefresh-0.2.4.zip** into a fresh
folder and copy `runtime/ShopRefreshGUI.ini`, `runtime/ADBconfig.ini` and
`runtime/ShopRefreshHistory/` from your old folder if you want them.
