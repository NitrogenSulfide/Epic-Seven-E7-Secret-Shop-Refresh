# v0.2.5 (beta) — Works on Windows without English text recognition; maximized windows; says why OCR failed

> ⚠️ **Beta, only tested on my own PCs.** Steam (Windows 11 and Linux), the STOVE client and
> Google Play Games Developer Emulator work for me. Other PCs, emulators and settings
> may hit edge cases I haven't seen. Start with a small Skystone budget, and if
> something breaks, report it on [GitHub Issues](https://github.com/NitrogenSulfide/Epic-Seven-E7-Secret-Shop-Refresh/issues)
> or Reddit with **Copy report**.

**Fix for Background stopping at once on non-English Windows.** On a Windows set up
in another language, runs stopped right away with "Windows could not read the
confirmation. No confirmation click sent." (GitHub #2 and #3). The app reads the
game with Windows' built-in text recognition (OCR), and those PCs had no English
OCR installed. The app now uses any English OCR that is installed, and otherwise
another Latin-script OCR language such as Portuguese or Spanish. Item names, prices
and buttons are still checked strictly, so a misread stops the run without a click.

**The real reason when OCR fails.** If Windows OCR still can't be used, the stop
message now says why, for example which OCR languages Windows has and how to add
English, instead of the generic message. Error text from a non-English Windows no
longer crashes the reader.

**Fix for maximized and other wide windows.** A maximized game window is wider than
16:9 (for example 1920 × 1009 or 3840 × 2019). The game keeps its buttons and labels
the same shape, but the app squeezed the whole window into 16:9 before comparing it
with its 16:9 pictures, so the shop title only just passed. Runs could stop with "The
Secret Shop did not open" or "The shop did not return after confirmation", and
Covenant/Mystic icons were found only by their names. The app now also compares
against the squeezed shape, so wide windows match as well as 16:9 ones.

If "The shop did not return after confirmation" still happens, the app now saves
pictures of the shop title, Refresh label and dialog area, and the stop message says
how well each matched. **Open pictures** shows them.

**Steadier shop rows.** A stock count that OCR reads in pieces ("1" and "/1") is
joined back together, and a small category label ("Currency") that OCR lost is read
again from its own strip, so a fully visible row no longer stops the run. A row that
shows two category, price or Buy words in any read is still refused.

Settings and history carry over: extract **E7ShopRefresh-0.2.5.zip** into a fresh
folder and copy `runtime/ShopRefreshGUI.ini`, `runtime/ADBconfig.ini` and
`runtime/ShopRefreshHistory/` from your old folder if you want them.
